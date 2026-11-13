import { ApiError } from '../../api/errors';
import { memorySelfieFiles, memoryStore, type PersistentStore, type SelfieFiles } from './store';

export type PunchKind = 'in' | 'out';

export type QueuedPunch = {
  client_uuid: string;
  /** Owner. Items of other users are never synced from this session (shared devices). */
  user_id: number;
  kind: PunchKind;
  /** Device clock at the moment the user tapped Punch, ISO. The server only accepts it within offline_max_hours. */
  captured_at: string;
  latitude: number | null;
  longitude: number | null;
  accuracy: number | null;
  is_mock_location: boolean;
  /** Local selfie file kept until the punch is synced. */
  selfie_path: string | null;
  /** Set once the selfie is uploaded (never re-uploaded after a partial sync). */
  selfie_id: number | null;
  /** The selfie could not be uploaded (rejected for good) and the punch is sent without it. */
  selfie_dropped?: boolean;
  liveness_passed: boolean | null;
  liveness_score: number | null;
};
export type RejectedPunch = QueuedPunch & { reason: string; rejected_at: string };
export type WirePunch = Omit<QueuedPunch, 'selfie_path' | 'user_id' | 'selfie_dropped'>;

export type SyncResult = { client_uuid: string; kind: string; status: 'created' | 'duplicate' | 'rejected'; reason?: string | null; attendance_id?: number | null };

export type SyncDeps = {
  /** Upload a local selfie, return selfie_id. Throws ApiError. */
  uploadSelfie(path: string): Promise<number>;
  /** POST /attendance/offline-sync. Throws ApiError. */
  syncPunches(punches: WirePunch[]): Promise<SyncResult[]>;
};

export type SyncOutcome = {
  skipped: 'backoff' | 'empty' | 'busy' | 'no-user' | null;
  created: number;
  duplicate: number;
  rejected: number;
  selfieDropped: number;
  /** A transport/server failure: items were kept and the backoff grew. */
  failed: boolean;
};

export type Snapshot = {
  /** Current user's pending items only. */
  items: QueuedPunch[];
  rejected: RejectedPunch[];
  nextAttemptAt: number;
  /** One-off message, e.g. an unreadable queue file was set aside. */
  notice: string | null;
};
type State = { items: QueuedPunch[]; rejected: RejectedPunch[]; attempts: number; nextAttemptAt: number };

export const BACKOFF_BASE_MS = 30_000;
export const BACKOFF_MAX_MS = 15 * 60_000;
export const STALE_WARN_HOURS = 10;
export const FOREIGN_PURGE_HOURS = 72;
const BATCH = 50;

export function backoffDelay(attempts: number): number {
  return Math.min(BACKOFF_BASE_MS * 2 ** Math.max(0, attempts - 1), BACKOFF_MAX_MS);
}
/** Items close to the server's offline_max_hours (default 12) window; warn the user before they are rejected. */
export function isStale(item: Pick<QueuedPunch, 'captured_at'>, now: number, hours = STALE_WARN_HOURS): boolean {
  return now - Date.parse(item.captured_at) > hours * 3_600_000;
}
/** Transport failure or server trouble: the punch itself was not judged, so it is safe to queue and retry. */
export function isRetryable(e: unknown): boolean {
  return e instanceof ApiError && (e.status === 0 || e.status >= 500 || e.status === 429);
}
/** Request-level failures that say nothing about the punches (network, 5xx, 429, and 401 = session being refreshed). */
function isTransient(e: unknown): boolean {
  return !(e instanceof ApiError) || isRetryable(e) || e.status === 401;
}

const REASONS: Record<string, string> = {
  captured_too_old: 'This punch was saved too long ago for the server to accept it. Ask HR to correct your attendance.',
  captured_in_future: "Your phone's clock was ahead of the server time. Check your date and time settings.",
  payroll_locked: 'This period is already locked for payroll. Ask HR to correct your attendance.',
  invalid_client_uuid: 'This punch was damaged on the phone and could not be sent.',
  already_punched_in: 'Already recorded.',
  outside_geofence: 'You were outside the allowed punch location.',
  OUTSIDE_GEOFENCE: 'You were outside the allowed punch location.',
};
export function friendlyReason(reason: string | null | undefined): string {
  if (!reason) return 'Rejected by the server';
  return REASONS[reason] ?? reason;
}
/** "Already recorded" outcomes are success, not failure. */
export function isAlreadyRecorded(reason: string | null | undefined): boolean {
  return !!reason && /already[_ ]punched|already recorded/i.test(reason);
}

const isNum = (v: unknown) => v === null || typeof v === 'number';
export function isValidItem(x: unknown): x is QueuedPunch {
  const i = x as Partial<QueuedPunch> | null;
  return !!i && typeof i.client_uuid === 'string' && i.client_uuid.length >= 8 && typeof i.user_id === 'number'
    && (i.kind === 'in' || i.kind === 'out') && typeof i.captured_at === 'string' && !Number.isNaN(Date.parse(i.captured_at))
    && isNum(i.latitude) && isNum(i.longitude) && isNum(i.accuracy) && typeof i.is_mock_location === 'boolean';
}

export class PunchQueue {
  private state: State | null = null;
  private tail: Promise<unknown> = Promise.resolve();
  private listeners = new Set<() => void>();
  private syncing = false;
  private userId: number | null = null;
  private notice: string | null = null;
  /** Immutable snapshot, replaced on every change so useSyncExternalStore sees a stable reference. */
  private snap: Snapshot = { items: [], rejected: [], nextAttemptAt: 0, notice: null };

  constructor(
    private store: PersistentStore = memoryStore(),
    private files: SelfieFiles = memorySelfieFiles(),
    private now: () => number = Date.now,
  ) {}

  /** The signed-in user; only their items are shown/synced. */
  setUser(id: number | null) {
    if (this.userId === id) return;
    this.userId = id;
    if (this.state) this.refresh();
    this.emit();
  }

  private run<T>(fn: () => Promise<T>): Promise<T> {
    const p = this.tail.then(fn, fn);
    this.tail = p.catch(() => undefined);
    return p;
  }
  private parse(raw: string): State | null {
    try {
      const j = JSON.parse(raw) as Partial<State>;
      if (!Array.isArray(j.items)) return null;
      return {
        items: j.items.filter(isValidItem),
        rejected: Array.isArray(j.rejected) ? j.rejected.filter((r) => isValidItem(r) && typeof (r as RejectedPunch).reason === 'string') : [],
        attempts: typeof j.attempts === 'number' ? j.attempts : 0,
        nextAttemptAt: typeof j.nextAttemptAt === 'number' ? j.nextAttemptAt : 0,
      };
    } catch {
      return null;
    }
  }
  private async load(): Promise<State> {
    if (this.state) return this.state;
    let s: State = { items: [], rejected: [], attempts: 0, nextAttemptAt: 0 };
    let raw: string | null = null;
    try { raw = await this.store.read(); } catch { raw = null; }
    if (raw) {
      const parsed = this.parse(raw);
      if (parsed) {
        s = parsed;
      } else {
        // Unreadable: set the file aside (never overwrite evidence), fall back to the last good copy, tell the user.
        try { await this.store.quarantine?.(); } catch { /* ignore */ }
        let bak: State | null = null;
        try { const b = await this.store.readBackup?.(); bak = b ? this.parse(b) : null; } catch { bak = null; }
        if (bak) s = bak;
        this.notice = bak
          ? 'Saved punches could not be read; the last good copy was restored.'
          : "Some saved punches couldn't be read and were set aside. Check your attendance for today.";
      }
    }
    this.state = s;
    this.refresh();
    this.emit(); // listeners (UI) that rendered before the load finished must update
    return s;
  }
  private refresh() {
    const s = this.state!;
    const mine = this.userId;
    this.snap = {
      items: s.items.filter((i) => i.user_id === mine),
      rejected: s.rejected.filter((r) => r.user_id === mine),
      nextAttemptAt: s.nextAttemptAt,
      notice: this.notice,
    };
  }
  private emit() { this.listeners.forEach((l) => l()); }
  private async save() {
    this.refresh();
    await this.store.write(JSON.stringify(this.state));
    this.emit();
  }

  subscribe(l: () => void) {
    this.listeners.add(l);
    return () => void this.listeners.delete(l);
  }
  async ready() { await this.run(async () => void (await this.load())); }
  getSnapshot(): Snapshot { return this.snap; }
  dismissNotice() { this.notice = null; if (this.state) this.refresh(); this.emit(); }

  /** Items belonging to other users on this device, for the logout warning's counterpart and tests. */
  foreignCount(): number {
    return (this.state?.items ?? []).filter((i) => i.user_id !== this.userId).length;
  }

  /** Oldest first (the server also processes in captured_at order). `selfie_uri` is copied somewhere durable. */
  enqueue(p: Omit<QueuedPunch, 'selfie_path' | 'selfie_id' | 'user_id'> & { selfie_uri?: string | null; selfie_id?: number | null }): Promise<QueuedPunch> {
    return this.run(async () => {
      const s = await this.load();
      if (this.userId == null) throw new Error('No signed-in user');
      const { selfie_uri, selfie_id, ...rest } = p;
      let selfie_path: string | null = null;
      if (selfie_uri) {
        try { selfie_path = await this.files.persist(selfie_uri, p.client_uuid); } catch { selfie_path = null; }
      }
      const item: QueuedPunch = { ...rest, user_id: this.userId, selfie_path, selfie_id: selfie_id ?? null };
      s.items.push(item);
      s.items.sort((a, b) => Date.parse(a.captured_at) - Date.parse(b.captured_at));
      await this.save();
      return item;
    });
  }

  dismissRejected(client_uuid?: string): Promise<void> {
    return this.run(async () => {
      const s = await this.load();
      s.rejected = s.rejected.filter((r) => r.user_id !== this.userId || (client_uuid != null && r.client_uuid !== client_uuid));
      await this.save();
    });
  }

  /** Force = ignore the backoff (manual "Sync now" and network regain). */
  async sync(deps: SyncDeps, opts: { force?: boolean } = {}): Promise<SyncOutcome> {
    const out: SyncOutcome = { skipped: null, created: 0, duplicate: 0, rejected: 0, selfieDropped: 0, failed: false };
    if (this.syncing) return { ...out, skipped: 'busy' };
    this.syncing = true;
    try {
      return await this.run(() => this.doSync(deps, !!opts.force, out));
    } finally {
      this.syncing = false;
    }
  }

  private async purgeForeign(s: State) {
    const cutoff = this.now() - FOREIGN_PURGE_HOURS * 3_600_000;
    const old = s.items.filter((i) => i.user_id !== this.userId && Date.parse(i.captured_at) < cutoff);
    if (!old.length) return;
    s.items = s.items.filter((i) => !old.includes(i));
    await this.save();
    await Promise.all(old.map((i) => (i.selfie_path ? this.files.remove(i.selfie_path) : undefined)));
  }

  private async doSync(deps: SyncDeps, force: boolean, out: SyncOutcome): Promise<SyncOutcome> {
    const s = await this.load();
    if (this.userId == null) return { ...out, skipped: 'no-user' };
    await this.purgeForeign(s);
    const mine = () => s.items.filter((i) => i.user_id === this.userId);
    if (!mine().length) return { ...out, skipped: 'empty' };
    if (!force && this.now() < s.nextAttemptAt) return { ...out, skipped: 'backoff' };

    const fail = async () => {
      s.attempts += 1;
      s.nextAttemptAt = this.now() + backoffDelay(s.attempts);
      out.failed = true;
      await this.save();
      return out;
    };
    const finish = async (item: QueuedPunch, r: SyncResult | { status: 'rejected'; reason: string }) => {
      if (r.status === 'rejected' && !isAlreadyRecorded(r.reason)) {
        out.rejected += 1;
        s.rejected.push({ ...item, reason: friendlyReason(r.reason), rejected_at: new Date(this.now()).toISOString() });
      } else {
        out[r.status === 'created' ? 'created' : 'duplicate'] += 1;
      }
      s.items = s.items.filter((i) => i.client_uuid !== item.client_uuid);
    };

    const batch = mine().slice(0, BATCH);
    for (const item of batch) {
      if (item.selfie_path && item.selfie_id == null) {
        try {
          item.selfie_id = await deps.uploadSelfie(item.selfie_path);
        } catch (e) {
          if (isTransient(e)) return fail();
          // Selfie rejected for good: send the punch without it (the server rejects it if a selfie is required) and say so.
          await this.files.remove(item.selfie_path);
          item.selfie_path = null;
          item.selfie_dropped = true;
          out.selfieDropped += 1;
        }
        await this.save(); // persist selfie_id / the dropped selfie
      }
    }

    const wire = ({ selfie_path: _p, user_id: _u, selfie_dropped: _d, ...w }: QueuedPunch): WirePunch => w;
    const toDelete: string[] = [];
    const settle = (item: QueuedPunch) => { if (item.selfie_path) toDelete.push(item.selfie_path); };

    let results: SyncResult[] | null = null;
    try {
      results = await deps.syncPunches(batch.map(wire));
    } catch (e) {
      if (isTransient(e)) return fail();
      // A non-retryable envelope error (422/413/403...) means at least one "poison" item; find it by sending one at a time.
      for (const item of batch) {
        try {
          const [r] = await deps.syncPunches([wire(item)]);
          if (r) { await finish(item, r); settle(item); }
        } catch (e2) {
          if (isTransient(e2)) { await this.save(); return fail(); }
          await finish(item, { status: 'rejected', reason: (e2 as Error).message });
          settle(item);
        }
      }
    }
    if (results) {
      const byId = new Map(results.map((r) => [r.client_uuid, r]));
      for (const item of batch) {
        const r = byId.get(item.client_uuid);
        if (!r) continue; // no verdict: keep
        await finish(item, r);
        settle(item);
      }
    }
    s.attempts = 0;
    s.nextAttemptAt = 0;
    await this.save();
    await Promise.all(toDelete.map((p) => this.files.remove(p)));
    return out;
  }
}
