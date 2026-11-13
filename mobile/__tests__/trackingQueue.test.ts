import { ApiError } from '../src/api/errors';
import { memoryStore } from '../src/features/punch/store';
import type { PingResult, WirePing } from '../src/features/tracking/api';
import { backoffDelay, MAX_BATCH, MAX_QUEUED, PingQueue, POISON_DROP_AFTER } from '../src/features/tracking/queue';

const NOW = Date.parse('2026-11-13T12:00:00Z');
const ping = (i: number, over: Partial<WirePing> = {}): WirePing => ({
  captured_at: new Date(NOW - 3_600_000 + i * 1000).toISOString(), lat: 12.9 + i / 1e5, lng: 77.6, accuracy: 10, speed: 0, battery: null, ...over,
});
const many = (n: number) => Array.from({ length: n }, (_, i) => ping(i));
const ok = (accepted: number, dropped: Record<string, number> = {}): PingResult => ({ accepted, dropped });
let clock = NOW;
const mk = (store = memoryStore()) => { const q = new PingQueue(store, () => clock); q.setUser(1); return { q, store }; };
beforeEach(() => { clock = NOW; });

describe('enqueue', () => {
  it('persists, sorts oldest first, dedupes by captured_at and rejects invalid points', async () => {
    const { q, store } = mk();
    expect(await q.enqueue([ping(5), ping(1), ping(1), ping(2, { lat: 95 }), ping(3, { lng: NaN })])).toBe(2);
    expect((await q.pending()).map((p) => p.captured_at)).toEqual([ping(1).captured_at, ping(5).captured_at]);
    expect(JSON.parse(store.data!).items).toHaveLength(2);
  });
  it('survives a restart (new instance, same store)', async () => {
    const { q, store } = mk();
    await q.enqueue(many(3));
    const again = new PingQueue(store, () => clock); again.setUser(1);
    expect(await again.size()).toBe(3);
  });
  it('ignores pings when nobody is signed in and caps the queue, dropping the oldest', async () => {
    const q = new PingQueue(memoryStore(), () => clock);
    expect(await q.enqueue(many(2))).toBe(0);
    q.setUser(1);
    await q.enqueue(many(MAX_QUEUED + 5));
    const items = await q.pending();
    expect(items).toHaveLength(MAX_QUEUED);
    expect(items[0].captured_at).toBe(ping(5).captured_at);
  });
  it('discards another user\'s pings as soon as the new user enqueues, and never uploads them', async () => {
    const { q } = mk();
    await q.enqueue(many(3));
    q.setUser(2);
    expect(await q.size()).toBe(0);
    const post = jest.fn(async () => ok(0));
    expect((await q.sync({ postPings: post })).skipped).toBe('empty');
    expect(post).not.toHaveBeenCalled();
    await q.enqueue([ping(9)]);
    q.setUser(1);
    expect(await q.size()).toBe(0); // user 2's enqueue purged user 1's leftovers
  });
  it('clear() empties the persisted queue', async () => {
    const { q, store } = mk();
    await q.enqueue(many(3));
    await q.clear();
    expect(await q.size()).toBe(0);
    expect(JSON.parse(store.data!).items).toEqual([]);
  });
});

describe('sync batching', () => {
  it('sends in batches of at most MAX_BATCH (200), oldest first, without internal fields', async () => {
    const { q } = mk();
    await q.enqueue(many(450));
    const sizes: number[] = [];
    const bodies: WirePing[][] = [];
    const out = await q.sync({ postPings: async (p) => { sizes.push(p.length); bodies.push(p); return ok(p.length); } });
    expect(MAX_BATCH).toBe(200);
    expect(sizes).toEqual([200, 200, 50]);
    expect(out).toMatchObject({ sent: 450, accepted: 450, failed: false, stop: null });
    expect(Object.keys(bodies[0][0]).sort()).toEqual(['accuracy', 'battery', 'captured_at', 'lat', 'lng', 'speed']);
    expect(bodies[0][0].captured_at).toBe(ping(0).captured_at);
    expect(await q.size()).toBe(0);
  });
  it('removes dropped-by-server pings too (a 200 judges the whole batch) and tallies reasons', async () => {
    const { q } = mk();
    await q.enqueue(many(5));
    const out = await q.sync({ postPings: async () => ok(3, { duplicate: 2 }) });
    expect(out.accepted).toBe(3);
    expect(out.dropped).toEqual({ duplicate: 2 });
    expect(out.stop).toBeNull();
    expect(await q.size()).toBe(0);
  });
  it('drops pings older than 23h locally (server limit 24h) without sending them', async () => {
    const { q } = mk();
    await q.enqueue([ping(0, { captured_at: new Date(NOW - 25 * 3_600_000).toISOString() }), ping(1)]);
    const post = jest.fn(async (p: WirePing[]) => ok(p.length));
    const out = await q.sync({ postPings: post });
    expect(post.mock.calls[0][0]).toHaveLength(1);
    expect(out.dropped.too_old).toBe(1);
  });
});

describe('stop signals from the server', () => {
  it.each([['no_consent'], ['not_required']])('%s drops the batch and signals stop', async (reason) => {
    const { q } = mk();
    await q.enqueue(many(3));
    const out = await q.sync({ postPings: async (p) => ok(0, { [reason]: p.length }) });
    expect(out.stop).toBe(reason);
    expect(await q.size()).toBe(0);
  });
  it('outside_window with nothing accepted signals stop; a mixed batch does not', async () => {
    const a = mk();
    await a.q.enqueue(many(3));
    expect((await a.q.sync({ postPings: async () => ok(0, { outside_window: 3 }) })).stop).toBe('outside_window');
    const b = mk();
    await b.q.enqueue(many(3));
    expect((await b.q.sync({ postPings: async () => ok(2, { outside_window: 1 }) })).stop).toBeNull();
  });
});

describe('request-level failures keep the pings and back off', () => {
  it.each([[0], [401], [403], [404], [405], [408], [409], [425], [429], [500], [503]])('status %i', async (status) => {
    const { q } = mk();
    await q.enqueue(many(3));
    const post = jest.fn(async () => { throw new ApiError('x', status); });
    const out = await q.sync({ postPings: post });
    expect(out.failed).toBe(true);
    expect(await q.size()).toBe(3);
    expect(post).toHaveBeenCalledTimes(1); // no per-item fallback
    expect((await q.sync({ postPings: post })).skipped).toBe('backoff');
    clock += backoffDelay(1) + 1;
    expect((await q.sync({ postPings: async (p) => ok(p.length) })).accepted).toBe(3);
  });
  it('force ignores the backoff and success resets it', async () => {
    const { q } = mk();
    await q.enqueue(many(2));
    await q.sync({ postPings: async () => { throw new ApiError('x', 500); } });
    expect((await q.sync({ postPings: async (p) => ok(p.length) }, { force: true })).accepted).toBe(2);
    await q.enqueue([ping(50)]);
    expect((await q.sync({ postPings: async (p) => ok(p.length) })).skipped).toBeNull();
  });
  it('backoff doubles up to the cap', () => {
    expect(backoffDelay(1)).toBe(30_000);
    expect(backoffDelay(3)).toBe(120_000);
    expect(backoffDelay(30)).toBe(15 * 60_000);
  });
  it('a failure in the middle keeps the batches not yet sent', async () => {
    const { q } = mk();
    await q.enqueue(many(250));
    let n = 0;
    const out = await q.sync({ postPings: async (p) => { if (n++ === 0) return ok(p.length); throw new ApiError('x', 503); } });
    expect(out.failed).toBe(true);
    expect(await q.size()).toBe(50);
  });
});

describe('validation-shaped statuses (400/413/422)', () => {
  it('splits the batch: judged pings go, the invalid one is dropped only if others got a verdict', async () => {
    const { q } = mk();
    await q.enqueue(many(3));
    const bad = ping(1).captured_at;
    const post = jest.fn(async (p: WirePing[]) => {
      if (p.length > 1 || p[0].captured_at === bad) throw new ApiError('bad', 422);
      return ok(1);
    });
    const out = await q.sync({ postPings: post });
    expect(out.accepted).toBe(2);
    expect(out.dropped.invalid).toBe(1);
    expect(out.failed).toBe(false);
    expect(await q.size()).toBe(0);
  });
  it('keeps everything when nothing got a verdict (likely a request-level problem), and drops after repeated attempts', async () => {
    const { q } = mk();
    await q.enqueue(many(2));
    const post = async () => { throw new ApiError('bad', 422); };
    for (let i = 1; i < POISON_DROP_AFTER; i += 1) {
      const out = await q.sync({ postPings: post }, { force: true });
      expect(out.failed).toBe(true);
      expect(await q.size()).toBe(2);
    }
    const last = await q.sync({ postPings: post }, { force: true });
    expect(last.dropped.invalid).toBe(2);
    expect(await q.size()).toBe(0);
  });
  it('a request-level error during the split keeps the remaining pings', async () => {
    const { q } = mk();
    await q.enqueue(many(3));
    let calls = 0;
    const out = await q.sync({ postPings: async (p) => { calls += 1; if (calls === 1) throw new ApiError('bad', 413); if (calls === 2) return ok(p.length); throw new ApiError('x', 500); } });
    expect(out.failed).toBe(true);
    expect(await q.size()).toBe(2);
  });
});

describe('guards', () => {
  it('skips when nobody is signed in, and is single-flight', async () => {
    const q = new PingQueue(memoryStore(), () => clock);
    expect((await q.sync({ postPings: async () => ok(0) })).skipped).toBe('no-user');
    const { q: q2 } = mk();
    await q2.enqueue(many(2));
    let release!: () => void;
    const gate = new Promise<void>((r) => { release = r; });
    const first = q2.sync({ postPings: async (p) => { await gate; return ok(p.length); } });
    expect((await q2.sync({ postPings: async () => ok(0) })).skipped).toBe('busy');
    release();
    expect((await first).accepted).toBe(2);
  });
  it('stops before the next request if the user changed mid-sync', async () => {
    const { q } = mk();
    await q.enqueue(many(250));
    const post = jest.fn(async (p: WirePing[]) => { q.setUser(2); return ok(p.length); });
    const out = await q.sync({ postPings: post });
    expect(post).toHaveBeenCalledTimes(1);
    expect(out.skipped).toBe('user-changed');
  });
  it('quarantines an unreadable file and starts empty', async () => {
    const store = memoryStore('{not json');
    const { q } = mk(store);
    expect(await q.size()).toBe(0);
    expect(store.quarantined).toBe('{not json');
  });
});
