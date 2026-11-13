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
  skipped: 'backoff' | 'empty' | 'busy' | 'no-user' | 'user-changed' | null;
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
/** Only validation-shaped statuses can mean "this payload is bad". Everything else (401, 403, 404, 405, 408, 409, 425,
 * 5xx, network...) is about the request/route/gateway, not the punches, so items are kept and retried with backoff. */
const PUNCH_VALIDATION = new Set([400, 413, 422]);
const SELFIE_DROP = new Set([400, 413, 415, 422]);
const isStatusIn = (e: unknown, set: Set<number>) => e instanceof ApiError && set.has(e.status);

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
  private parse(raw: string): { state: State; dropped: number } | null {
    try {
      const j = JSON.parse(raw) as Partial<State>;
      if (!Array.isArray(j.items)) return null;
      const rej = Array.isArray(j.rejected) ? j.rejected : [];
      const items = j.items.filter(isValidItem);
      const rejected = rej.filter((r) => isValidItem(r) && typeof (r as RejectedPunch).reason === 'string') as RejectedPunch[];
      return {
        state: {
          items,
          rejected,
          attempts: typeof j.attempts === 'number' ? j.attempts : 0,
          nextAttemptAt: typeof j.nextAttemptAt === 'number' ? j.nextAttemptAt : 0,
        },
        dropped: j.items.length - items.length + rej.length - rejected.length,
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
        s = parsed.state;
        if (parsed.dropped > 0) {
          // Some entries failed validation (e.g. written by an older build): keep the original file for inspection.
          try { await this.store.quarantine?.(); } catch { /* ignore */ }
          try { await this.store.write(JSON.stringify(s)); } catch { /* ignore */ }
          this.notice = `${parsed.dropped} saved punch${parsed.dropped === 1 ? '' : 'es'} couldn't be read and ${parsed.dropped === 1 ? 'was' : 'were'} set aside. Check your attendance for today.`;
        }
      } else {
        // Unreadable: set the file aside (never overwrite evidence), fall back to the last good copy, tell the user.
        try { await this.store.quarantine?.(); } catch { /* ignore */ }
        const bak = await this.recover();
        if (bak) s = bak;
        this.notice = bak
          ? 'Saved punches could not be read; the last good copy was restored.'
          : "Some saved punches couldn't be read and were set aside. Check your attendance for today.";
      }
    } else {
      // Main file missing: a crash between "delete main" and "move tmp into place" leaves only .tmp/.bak.
      const rec = await this.recover();
      if (rec) {
        s = rec;
        this.notice = 'Saved punches were recovered after the app was interrupted.';
      }
    }
    this.state = s;
    this.refresh();
    this.emit(); // listeners (UI) that rendered before the load finished must update
    return s;
  }
  /** First parseable candidate among the store's recovery copies (newest first: .tmp, then .bak). */
  private async recover(): Promise<State | null> {
    let cands: string[] = [];
    try { cands = (await this.store.readRecovery?.()) ?? []; } catch { cands = []; }
    for (const c of cands) {
      const parsed = c ? this.parse(c) : null;
      if (parsed) return parsed.state;
    }
    return null;
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
    const uid = this.userId;
    if (uid == null) return { ...out, skipped: 'no-user' };
    await this.purgeForeign(s);
    const mine = () => s.items.filter((i) => i.user_id === uid);
    if (!mine().length) return { ...out, skipped: 'empty' };
    if (!force && this.now() < s.nextAttemptAt) return { ...out, skipped: 'backoff' };
    /** The signed-in user changed mid-sync: stop before any further request is made with the new user's token. */
    const switched = () => this.userId !== uid;
    const abort = async () => { await this.save(); return { ...out, skipped: 'user-changed' as const }; };

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
        if (switched()) return abort();
        try {
          item.selfie_id = await deps.uploadSelfie(item.selfie_path);
        } catch (e) {
          if (!isStatusIn(e, SELFIE_DROP)) return fail();
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
    let unjudged = 0; // items that got no server verdict this round

    if (switched()) return abort();
    let results: SyncResult[] | null = null;
    try {
      results = await deps.syncPunches(batch.map(wire));
    } catch (e) {
      // Only a validation-shaped envelope error can mean a "poison" item. Anything else is a request-level problem
      // (wrong route, WAF, auth, outage): keep every punch and back off.
      if (!isStatusIn(e, PUNCH_VALIDATION)) return fail();
      const poison: { item: QueuedPunch; reason: string }[] = [];
      let verdicts = 0;
      for (const item of batch) {
        if (switched()) { await this.save(); return { ...out, skipped: 'user-changed' }; }
        try {
          const [r] = await deps.syncPunches([wire(item)]);
          if (r && r.client_uuid === item.client_uuid) { await finish(item, r); settle(item); verdicts += 1; await this.save(); } else unjudged += 1;
        } catch (e2) {
          if (!isStatusIn(e2, PUNCH_VALIDATION)) { await this.save(); return fail(); }
          poison.push({ item, reason: (e2 as Error).message });
        }
      }
      if (verdicts === 0) return fail(); // nothing was judged individually: not enough evidence to discard anything
      for (const { item, reason } of poison) { await finish(item, { status: 'rejected', reason }); settle(item); }
    }
    if (results) {
      const byId = new Map(results.map((r) => [r.client_uuid, r]));
      for (const item of batch) {
        const r = byId.get(item.client_uuid);
        if (!r) { unjudged += 1; continue; } // no verdict: keep
        await finish(item, r);
        settle(item);
      }
    }
    // Persist the verdicts right away (no network call between applying results and saving).
    if (unjudged > 0) {
      s.attempts += 1;
      s.nextAttemptAt = this.now() + backoffDelay(s.attempts);
      out.failed = true;
    } else {
      s.attempts = 0;
      s.nextAttemptAt = 0;
    }
    await this.save();
    await Promise.all(toDelete.map((p) => this.files.remove(p)));
    return out;
  }
}
