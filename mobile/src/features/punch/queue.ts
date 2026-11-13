import { ApiError } from '../../api/errors';
import { memorySelfieFiles, memoryStore, type PersistentStore, type SelfieFiles } from './store';

export type PunchKind = 'in' | 'out';

export type QueuedPunch = {
  client_uuid: string;
  kind: PunchKind;
  /** Device clock, ISO. The server only accepts it within offline_max_hours and not in the future. */
  captured_at: string;
  latitude: number | null;
  longitude: number | null;
  accuracy: number | null;
  is_mock_location: boolean;
  /** Local selfie file kept until the punch is synced. */
  selfie_path: string | null;
  /** Set once the selfie is uploaded (never re-uploaded after a partial sync). */
  selfie_id: number | null;
  liveness_passed: boolean | null;
  liveness_score: number | null;
};
export type RejectedPunch = QueuedPunch & { reason: string; rejected_at: string };

export type SyncResult = { client_uuid: string; kind: string; status: 'created' | 'duplicate' | 'rejected'; reason?: string | null; attendance_id?: number | null };

export type SyncDeps = {
  /** Upload a local selfie, return selfie_id. Throws ApiError. */
  uploadSelfie(path: string): Promise<number>;
  /** POST /attendance/offline-sync. Throws ApiError. */
  syncPunches(punches: Omit<QueuedPunch, 'selfie_path'>[]): Promise<SyncResult[]>;
};

export type SyncOutcome = {
  skipped: 'backoff' | 'empty' | 'busy' | null;
  created: number;
  duplicate: number;
  rejected: number;
  /** A transport/server failure: items were kept and the backoff grew. */
  failed: boolean;
};

export type Snapshot = { items: QueuedPunch[]; rejected: RejectedPunch[]; nextAttemptAt: number };
type State = { items: QueuedPunch[]; rejected: RejectedPunch[]; attempts: number; nextAttemptAt: number };

export const BACKOFF_BASE_MS = 30_000;
export const BACKOFF_MAX_MS = 15 * 60_000;
export const STALE_WARN_HOURS = 10;
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

export class PunchQueue {
  private state: State | null = null;
  private tail: Promise<unknown> = Promise.resolve();
  private listeners = new Set<() => void>();
  private syncing = false;
  /** Immutable snapshot, replaced on every change so useSyncExternalStore sees a stable reference. */
  private snap: Snapshot = { items: [], rejected: [], nextAttemptAt: 0 };

  constructor(
    private store: PersistentStore = memoryStore(),
    private files: SelfieFiles = memorySelfieFiles(),
    private now: () => number = Date.now,
  ) {}

  private run<T>(fn: () => Promise<T>): Promise<T> {
    const p = this.tail.then(fn, fn);
    this.tail = p.catch(() => undefined);
    return p;
  }
  private async load(): Promise<State> {
    if (this.state) return this.state;
    let s: State = { items: [], rejected: [], attempts: 0, nextAttemptAt: 0 };
    try {
      const raw = await this.store.read();
      if (raw) {
        const j = JSON.parse(raw) as Partial<State>;
        s = { items: j.items ?? [], rejected: j.rejected ?? [], attempts: j.attempts ?? 0, nextAttemptAt: j.nextAttemptAt ?? 0 };
      }
    } catch {
      /* corrupt file: start empty rather than crash the app */
    }
    this.state = s;
    this.refresh();
    return s;
  }
  private refresh() {
    const s = this.state!;
    this.snap = { items: [...s.items], rejected: [...s.rejected], nextAttemptAt: s.nextAttemptAt };
  }
  private async save() {
    this.refresh();
    await this.store.write(JSON.stringify(this.state));
    this.listeners.forEach((l) => l());
  }

  subscribe(l: () => void) {
    this.listeners.add(l);
    return () => void this.listeners.delete(l);
  }
  async ready() { await this.run(async () => void (await this.load())); }
  getSnapshot(): Snapshot {
    return this.snap;
  }

  /** Oldest first (the server also processes in captured_at order). `selfieUri` is copied somewhere durable. */
  enqueue(p: Omit<QueuedPunch, 'selfie_path' | 'selfie_id'> & { selfie_uri?: string | null; selfie_id?: number | null }): Promise<QueuedPunch> {
    return this.run(async () => {
      const s = await this.load();
      const { selfie_uri, selfie_id, ...rest } = p;
      let selfie_path: string | null = null;
      if (selfie_uri) {
        try { selfie_path = await this.files.persist(selfie_uri, p.client_uuid); } catch { selfie_path = null; }
      }
      const item: QueuedPunch = { ...rest, selfie_path, selfie_id: selfie_id ?? null };
      s.items.push(item);
      s.items.sort((a, b) => Date.parse(a.captured_at) - Date.parse(b.captured_at));
      await this.save();
      return item;
    });
  }

  dismissRejected(client_uuid?: string): Promise<void> {
    return this.run(async () => {
      const s = await this.load();
      s.rejected = client_uuid ? s.rejected.filter((r) => r.client_uuid !== client_uuid) : [];
      await this.save();
    });
  }

  /** Reset backoff (manual "Sync now" and network regain should retry immediately). */
  async sync(deps: SyncDeps, opts: { force?: boolean } = {}): Promise<SyncOutcome> {
    if (this.syncing) return { skipped: 'busy', created: 0, duplicate: 0, rejected: 0, failed: false };
    this.syncing = true;
    try {
      return await this.run(() => this.doSync(deps, !!opts.force));
    } finally {
      this.syncing = false;
    }
  }

  private async doSync(deps: SyncDeps, force: boolean): Promise<SyncOutcome> {
    const s = await this.load();
    const out: SyncOutcome = { skipped: null, created: 0, duplicate: 0, rejected: 0, failed: false };
    if (!s.items.length) return { ...out, skipped: 'empty' };
    if (!force && this.now() < s.nextAttemptAt) return { ...out, skipped: 'backoff' };

    const fail = async () => {
      s.attempts += 1;
      s.nextAttemptAt = this.now() + backoffDelay(s.attempts);
      out.failed = true;
      await this.save();
      return out;
    };

    const batch = [...s.items].slice(0, BATCH);
    for (const item of batch) {
      if (item.selfie_path && item.selfie_id == null) {
        try {
          item.selfie_id = await deps.uploadSelfie(item.selfie_path);
          await this.save();
        } catch (e) {
          if (isRetryable(e)) return fail();
          // Selfie rejected for good (bad file etc.): let the server judge the punch without it (it rejects if required).
          item.selfie_path = null;
        }
      }
    }

    let results: SyncResult[];
    try {
      results = await deps.syncPunches(batch.map(({ selfie_path: _p, ...wire }) => wire));
    } catch {
      // Any request-level failure (network, 5xx, 401 pending refresh, 422 on the envelope) says nothing about the
      // individual punches, so they stay queued; per-item rejections come back inside a 200.
      return fail();
    }

    const byId = new Map(results.map((r) => [r.client_uuid, r]));
    const toDelete: string[] = [];
    for (const item of batch) {
      const r = byId.get(item.client_uuid);
      if (!r) continue; // no verdict: keep
      if (r.status === 'created' || r.status === 'duplicate') {
        out[r.status] += 1;
      } else {
        out.rejected += 1;
        s.rejected.push({ ...item, reason: r.reason || 'Rejected by the server', rejected_at: new Date(this.now()).toISOString() });
      }
      s.items = s.items.filter((i) => i.client_uuid !== item.client_uuid);
      if (item.selfie_path) toDelete.push(item.selfie_path);
    }
    s.attempts = 0;
    s.nextAttemptAt = 0;
    await this.save();
    await Promise.all(toDelete.map((p) => this.files.remove(p)));
    return out;
  }
}
