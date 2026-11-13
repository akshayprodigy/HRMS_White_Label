import { ApiError } from '../../api/errors';
import { memoryStore, type PersistentStore } from '../punch/store';
import type { PingResult, WirePing } from './api';

export type QueuedPing = WirePing & {
  /** Owner. Other users' pings are discarded, never uploaded (shared devices). */
  user_id: number;
  poison_attempts?: number;
};

export const MAX_BATCH = 200; // backend lt.MAX_BATCH
export const MAX_QUEUED = 5000;
export const MAX_AGE_MS = 23 * 3_600_000; // backend rejects pings older than 24h
const MAX_BATCHES_PER_SYNC = 10;
export const BACKOFF_BASE_MS = 30_000;
export const BACKOFF_MAX_MS = 15 * 60_000;
export const POISON_DROP_AFTER = 3;
const VALIDATION = new Set([400, 413, 422]);

export function backoffDelay(attempts: number): number {
  return Math.min(BACKOFF_BASE_MS * 2 ** Math.max(0, attempts - 1), BACKOFF_MAX_MS);
}

const optNum = (v: unknown) => v === null || (typeof v === 'number' && Number.isFinite(v));
export function isValidPing(x: unknown): x is QueuedPing {
  const p = x as Partial<QueuedPing> | null;
  return !!p && typeof p.user_id === 'number' && typeof p.captured_at === 'string' && !Number.isNaN(Date.parse(p.captured_at))
    && typeof p.lat === 'number' && Number.isFinite(p.lat) && p.lat >= -90 && p.lat <= 90
    && typeof p.lng === 'number' && Number.isFinite(p.lng) && p.lng >= -180 && p.lng <= 180
    && optNum(p.accuracy) && optNum(p.speed) && optNum(p.battery);
}

/** Server-side drop reasons that mean "stop sending": the user is no longer tracked / consented / inside the window. */
export type StopSignal = 'not_required' | 'no_consent' | 'outside_window';
export type SyncOutcome = {
  skipped: 'backoff' | 'empty' | 'busy' | 'no-user' | 'user-changed' | null;
  sent: number;
  accepted: number;
  dropped: Record<string, number>;
  /** A transport/server failure: items were kept and the backoff grew. */
  failed: boolean;
  stop: StopSignal | null;
};
export type SyncDeps = { postPings(pings: WirePing[]): Promise<PingResult> };

type State = { items: QueuedPing[]; attempts: number; nextAttemptAt: number };

export class PingQueue {
  private state: State | null = null;
  private tail: Promise<unknown> = Promise.resolve();
  private syncing = false;
  private current: Promise<unknown> | null = null;
  private userId: number | null = null;

  constructor(private store: PersistentStore = memoryStore(), private now: () => number = Date.now) {}

  /** Bumped by clear(). A producer captures it before its awaits and passes it to enqueue(), so a fix that was in
   * flight while the data was erased (logout, revoke) is refused instead of recreating the file. */
  get generation() { return this.gen; }
  private gen = 0;

  setUser(id: number | null) { this.userId = id; }
  getUser() { return this.userId; }

  private run<T>(fn: () => Promise<T>): Promise<T> {
    const p = this.tail.then(fn, fn);
    this.tail = p.catch(() => undefined);
    return p;
  }
  private async load(): Promise<State> {
    if (this.state) return this.state;
    let s: State = { items: [], attempts: 0, nextAttemptAt: 0 };
    let raw: string | null = null;
    try { raw = await this.store.read(); } catch { raw = null; }
    if (raw) {
      try {
        const j = JSON.parse(raw) as Partial<State>;
        if (Array.isArray(j.items)) {
          s = { items: j.items.filter(isValidPing), attempts: typeof j.attempts === 'number' ? j.attempts : 0, nextAttemptAt: typeof j.nextAttemptAt === 'number' ? j.nextAttemptAt : 0 };
        }
      } catch {
        try { await this.store.quarantine?.(); } catch { /* ignore */ }
      }
    }
    this.state = s;
    return s;
  }
  private save() { return this.store.write(JSON.stringify(this.state)); }

  async ready() { await this.run(async () => void (await this.load())); }
  /** Current user's pending pings (for tests / diagnostics). */
  async pending(): Promise<QueuedPing[]> {
    return this.run(async () => (await this.load()).items.filter((i) => i.user_id === this.userId));
  }
  async size(): Promise<number> { return (await this.pending()).length; }

  enqueue(pings: WirePing[], opts: { generation?: number } = {}): Promise<number> {
    return this.run(async () => {
      if (opts.generation !== undefined && opts.generation !== this.gen) return 0;
      const s = await this.load();
      const uid = this.userId;
      if (uid == null) return 0;
      // Another user's leftovers are personal data with no purpose here: drop them as soon as we touch the queue.
      s.items = s.items.filter((i) => i.user_id === uid);
      const have = new Set(s.items.map((i) => i.captured_at));
      let added = 0;
      for (const p of pings) {
        const item = { ...p, user_id: uid };
        if (!isValidPing(item) || have.has(item.captured_at)) continue;
        have.add(item.captured_at);
        s.items.push(item);
        added += 1;
      }
      s.items.sort((a, b) => Date.parse(a.captured_at) - Date.parse(b.captured_at));
      if (s.items.length > MAX_QUEUED) s.items.splice(0, s.items.length - MAX_QUEUED); // oldest go first
      await this.save();
      return added;
    });
  }

  /** Remove everything (logout, consent revoked, tracking disabled): location data must not outlive the permission. */
  clear(): Promise<void> {
    this.gen += 1; // synchronously, so anything already past its checks is refused when it reaches the chain
    return this.run(async () => {
      this.state = { items: [], attempts: 0, nextAttemptAt: 0 };
      // Delete, don't write an empty state: a write would turn the previous pings into the .bak copy.
      await this.store.destroy();
    });
  }

  async sync(deps: SyncDeps, opts: { force?: boolean } = {}): Promise<SyncOutcome> {
    const out: SyncOutcome = { skipped: null, sent: 0, accepted: 0, dropped: {}, failed: false, stop: null };
    // A forced sync (final flush at the window end, manual retry) must not be lost to an in-flight one: wait for it, then run.
    while (this.syncing) {
      if (!opts.force) return { ...out, skipped: 'busy' };
      await this.current?.catch(() => undefined);
    }
    this.syncing = true;
    const p = this.run(() => this.doSync(deps, !!opts.force, out));
    this.current = p;
    try {
      return await p;
    } finally {
      if (this.current === p) { this.syncing = false; this.current = null; }
    }
  }

  private addDropped(out: SyncOutcome, d: Record<string, number>) {
    for (const [k, n] of Object.entries(d)) if (n > 0) out.dropped[k] = (out.dropped[k] ?? 0) + n;
  }
  private applyResult(out: SyncOutcome, r: PingResult) {
    out.accepted += r.accepted;
    this.addDropped(out, r.dropped);
  }
  private finalizeStop(out: SyncOutcome) {
    if (out.dropped.no_consent) out.stop = 'no_consent';
    else if (out.dropped.not_required) out.stop = 'not_required';
    else if (out.dropped.outside_window && out.accepted === 0) out.stop = 'outside_window';
  }

  private async doSync(deps: SyncDeps, force: boolean, out: SyncOutcome): Promise<SyncOutcome> {
    const s = await this.load();
    const uid = this.userId;
    if (uid == null) return { ...out, skipped: 'no-user' };
    const before = s.items.length;
    s.items = s.items.filter((i) => i.user_id === uid);
    // The server refuses pings older than 24h: do not keep retrying what can never be accepted.
    const cutoff = this.now() - MAX_AGE_MS;
    const stale = s.items.filter((i) => Date.parse(i.captured_at) < cutoff).length;
    if (stale) { s.items = s.items.filter((i) => Date.parse(i.captured_at) >= cutoff); out.dropped.too_old = stale; }
    if (before !== s.items.length) await this.save();
    if (!s.items.length) return { ...out, skipped: 'empty' };
    if (!force && this.now() < s.nextAttemptAt) return { ...out, skipped: 'backoff' };

    const wire = ({ user_id: _u, poison_attempts: _p, ...w }: QueuedPing): WirePing => w;
    const fail = async () => {
      s.attempts += 1;
      s.nextAttemptAt = this.now() + backoffDelay(s.attempts);
      out.failed = true;
      await this.save();
      this.finalizeStop(out);
      return out;
    };
    const remove = (items: QueuedPing[]) => { s.items = s.items.filter((i) => !items.includes(i)); };

    for (let n = 0; n < MAX_BATCHES_PER_SYNC; n += 1) {
      if (this.userId !== uid) { await this.save(); this.finalizeStop(out); return { ...out, skipped: 'user-changed' }; }
      const batch = s.items.filter((i) => i.user_id === uid).slice(0, MAX_BATCH);
      if (!batch.length) break;
      out.sent += batch.length;
      try {
        const r = await deps.postPings(batch.map(wire));
        this.applyResult(out, r); // 200 = the whole batch was judged: accepted or dropped with a reason
        remove(batch);
        s.attempts = 0;
        s.nextAttemptAt = 0;
        await this.save();
        // Nothing more to say to a server that refuses this user: leave the rest queued for the controller to clear/keep.
        if (out.dropped.no_consent || out.dropped.not_required || (out.dropped.outside_window && out.accepted === 0)) break;
      } catch (e) {
        // Only a validation-shaped status can mean a bad item; 401/403/404/405/408/409/425/5xx/network are request-level.
        if (!(e instanceof ApiError && VALIDATION.has(e.status))) return fail();
        const poison: QueuedPing[] = [];
        let verdicts = 0;
        for (const item of batch) {
          try {
            this.applyResult(out, await deps.postPings([wire(item)]));
            remove([item]);
            verdicts += 1;
          } catch (e2) {
            if (!(e2 instanceof ApiError && VALIDATION.has(e2.status))) { await this.save(); return fail(); }
            poison.push(item);
          }
        }
        for (const item of poison) item.poison_attempts = (item.poison_attempts ?? 0) + 1;
        if (verdicts > 0) {
          // The server judged other pings individually, so the leftovers are genuinely invalid: drop them now.
          remove(poison);
          out.dropped.invalid = (out.dropped.invalid ?? 0) + poison.length;
        } else {
          const gone = poison.filter((i) => (i.poison_attempts ?? 0) >= POISON_DROP_AFTER);
          remove(gone);
          if (gone.length) out.dropped.invalid = (out.dropped.invalid ?? 0) + gone.length;
          return fail();
        }
        await this.save();
      }
    }
    this.finalizeStop(out);
    return out;
  }
}
