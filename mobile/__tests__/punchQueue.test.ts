import { ApiError } from '../src/api/errors';
import { friendlyReason, BACKOFF_BASE_MS, BACKOFF_MAX_MS, PunchQueue, backoffDelay, isStale, type SyncDeps, type SyncResult } from '../src/features/punch/queue';
import { memorySelfieFiles, memoryStore } from '../src/features/punch/store';

const mkQ = (...a: ConstructorParameters<typeof PunchQueue>) => { const q = new PunchQueue(...a); q.setUser(1); return q; };
const base = { kind: 'in' as const, latitude: 12.9, longitude: 77.6, accuracy: 10, is_mock_location: false, liveness_passed: null, liveness_score: null };
const mk = (id: string, at: string, extra = {}) => ({ ...base, client_uuid: id, captured_at: at, ...extra });

function deps(over: Partial<SyncDeps> = {}): SyncDeps & { sent: unknown[][] } {
  const sent: unknown[][] = [];
  return {
    sent,
    uploadSelfie: jest.fn(async () => 99),
    syncPunches: jest.fn(async (p) => {
      sent.push(p);
      return p.map((x) => ({ client_uuid: x.client_uuid, kind: x.kind, status: 'created' as const }));
    }),
    ...over,
  };
}

describe('PunchQueue', () => {
  it('persists across instances and keeps captured_at order', async () => {
    const store = memoryStore();
    const q1 = mkQ(store, memorySelfieFiles());
    await q1.enqueue(mk('uuid-0002', '2026-11-13T10:00:00Z'));
    await q1.enqueue(mk('uuid-0001', '2026-11-13T09:00:00Z'));
    const q2 = mkQ(store, memorySelfieFiles());
    await q2.ready();
    expect(q2.getSnapshot().items.map((i) => i.client_uuid)).toEqual(['uuid-0001', 'uuid-0002']);
  });

  it('survives a corrupt store', async () => {
    const q = mkQ(memoryStore('{nope'), memorySelfieFiles());
    await q.ready();
    expect(q.getSnapshot().items).toEqual([]);
  });

  it('created/duplicate are removed; rejected moves to the rejected list with its reason', async () => {
    const files = memorySelfieFiles();
    const q = mkQ(memoryStore(), files);
    await q.enqueue({ ...mk('uuid-0001', '2026-11-13T09:00:00Z'), selfie_uri: 'file:///c/a.jpg' });
    await q.enqueue(mk('uuid-0002', '2026-11-13T09:05:00Z'));
    await q.enqueue(mk('uuid-0003', '2026-11-13T09:10:00Z'));
    expect(files.files.size).toBe(1);
    const d = deps({
      syncPunches: jest.fn(async () => [
        { client_uuid: 'uuid-0001', kind: 'in', status: 'created' },
        { client_uuid: 'uuid-0002', kind: 'in', status: 'duplicate' },
        { client_uuid: 'uuid-0003', kind: 'in', status: 'rejected', reason: 'Punch is older than 12 hours' },
      ] as SyncResult[]),
    });
    const out = await q.sync(d);
    expect(out).toMatchObject({ created: 1, duplicate: 1, rejected: 1, failed: false });
    const snap = q.getSnapshot();
    expect(snap.items).toEqual([]);
    expect(snap.rejected).toHaveLength(1);
    expect(snap.rejected[0]).toMatchObject({ client_uuid: 'uuid-0003', reason: 'Punch is older than 12 hours' });
    expect(files.files.size).toBe(0);
    await q.dismissRejected('uuid-0003');
    expect(q.getSnapshot().rejected).toEqual([]);
  });

  it('uploads the selfie first and sends selfie_id (no local path) in the punch', async () => {
    const q = mkQ(memoryStore(), memorySelfieFiles());
    await q.enqueue({ ...mk('uuid-0001', '2026-11-13T09:00:00Z'), selfie_uri: 'file:///c/a.jpg' });
    const d = deps();
    await q.sync(d);
    expect(d.uploadSelfie).toHaveBeenCalledTimes(1);
    expect(d.sent[0][0]).toMatchObject({ client_uuid: 'uuid-0001', selfie_id: 99 });
    expect(d.sent[0][0]).not.toHaveProperty('selfie_path');
  });

  it('network failure keeps items, grows the backoff exponentially and skips until it elapses', async () => {
    let now = 1_000_000;
    const q = mkQ(memoryStore(), memorySelfieFiles(), () => now);
    await q.enqueue(mk('uuid-0001', '2026-11-13T09:00:00Z'));
    const fail = deps({ syncPunches: jest.fn(async () => { throw new ApiError('net', 0, 'network_error'); }) });
    expect((await q.sync(fail)).failed).toBe(true);
    expect(q.getSnapshot().nextAttemptAt).toBe(now + BACKOFF_BASE_MS);
    expect((await q.sync(fail)).skipped).toBe('backoff');
    expect(fail.syncPunches).toHaveBeenCalledTimes(1);
    now += BACKOFF_BASE_MS;
    await q.sync(fail);
    expect(q.getSnapshot().nextAttemptAt).toBe(now + BACKOFF_BASE_MS * 2);
    // force (manual Sync now / network regain) ignores the backoff
    await q.sync(fail, { force: true });
    expect(fail.syncPunches).toHaveBeenCalledTimes(3);
    expect(q.getSnapshot().items).toHaveLength(1);
    // success resets the backoff
    await q.sync(deps(), { force: true });
    expect(q.getSnapshot().nextAttemptAt).toBe(0);
    expect(q.getSnapshot().items).toHaveLength(0);
  });

  it('backoff delay is capped', () => {
    expect(backoffDelay(1)).toBe(BACKOFF_BASE_MS);
    expect(backoffDelay(3)).toBe(BACKOFF_BASE_MS * 4);
    expect(backoffDelay(30)).toBe(BACKOFF_MAX_MS);
  });

  it('a failed selfie upload on the network keeps everything and does not call offline-sync', async () => {
    const q = mkQ(memoryStore(), memorySelfieFiles());
    await q.enqueue({ ...mk('uuid-0001', '2026-11-13T09:00:00Z'), selfie_uri: 'file:///c/a.jpg' });
    const d = deps({ uploadSelfie: jest.fn(async () => { throw new ApiError('net', 0); }) });
    const out = await q.sync(d);
    expect(out.failed).toBe(true);
    expect(d.syncPunches).not.toHaveBeenCalled();
    expect(q.getSnapshot().items[0].selfie_path).not.toBeNull();
  });

  it('keeps an already-uploaded selfie_id after a partial failure (no re-upload)', async () => {
    const q = mkQ(memoryStore(), memorySelfieFiles());
    await q.enqueue({ ...mk('uuid-0001', '2026-11-13T09:00:00Z'), selfie_uri: 'file:///c/a.jpg' });
    const d = deps({ syncPunches: jest.fn(async () => { throw new ApiError('net', 0); }) });
    await q.sync(d, { force: true });
    await q.sync(d, { force: true });
    expect(d.uploadSelfie).toHaveBeenCalledTimes(1);
  });

  it('items the server gave no verdict for stay queued', async () => {
    const q = mkQ(memoryStore(), memorySelfieFiles());
    await q.enqueue(mk('uuid-0001', '2026-11-13T09:00:00Z'));
    await q.sync(deps({ syncPunches: jest.fn(async () => []) }));
    expect(q.getSnapshot().items).toHaveLength(1);
  });

  it('friendly reasons and already-recorded rejections count as success', async () => {
    const q = mkQ(memoryStore(), memorySelfieFiles());
    await q.enqueue(mk('uuid-0001', '2026-11-13T09:00:00Z'));
    await q.enqueue(mk('uuid-0002', '2026-11-13T09:05:00Z'));
    const out = await q.sync(deps({ syncPunches: jest.fn(async () => [
      { client_uuid: 'uuid-0001', kind: 'in', status: 'rejected', reason: 'already_punched_in' },
      { client_uuid: 'uuid-0002', kind: 'in', status: 'rejected', reason: 'payroll_locked' },
    ] as SyncResult[]) }));
    expect(out).toMatchObject({ duplicate: 1, rejected: 1 });
    expect(q.getSnapshot().rejected[0].reason).toMatch(/locked for payroll/);
    expect(friendlyReason('captured_too_old')).toMatch(/too long ago/);
  });

  it('a concurrent sync returns busy; an enqueue during a sync is kept for the next one', async () => {
    const q = mkQ(memoryStore(), memorySelfieFiles());
    await q.enqueue(mk('uuid-0001', '2026-11-13T09:00:00Z'));
    let release: () => void = () => undefined;
    const gate = new Promise<void>((r) => { release = r; });
    const slow = deps({ syncPunches: jest.fn(async (p) => { await gate; return p.map((x) => ({ client_uuid: x.client_uuid, kind: x.kind, status: 'created' as const })); }) });
    const first = q.sync(slow);
    await Promise.resolve();
    expect((await q.sync(deps())).skipped).toBe('busy');
    const added = q.enqueue(mk('uuid-0002', '2026-11-13T09:30:00Z'));
    release();
    await first; await added;
    expect(q.getSnapshot().items.map((i) => i.client_uuid)).toEqual(['uuid-0002']);
    await q.sync(deps());
    expect(q.getSnapshot().items).toEqual([]);
  });

  it('isolates a poison item on a non-retryable envelope error so the rest proceed', async () => {
    const q = mkQ(memoryStore(), memorySelfieFiles());
    await q.enqueue(mk('uuid-0001', '2026-11-13T09:00:00Z'));
    await q.enqueue(mk('uuid-0002', '2026-11-13T09:05:00Z'));
    await q.enqueue(mk('uuid-0003', '2026-11-13T09:10:00Z'));
    const d = deps({ syncPunches: jest.fn(async (p) => {
      if (p.length > 1 || p[0].client_uuid === 'uuid-0002') throw new ApiError('Invalid coordinates', 422, 'validation_error');
      return p.map((x) => ({ client_uuid: x.client_uuid, kind: x.kind, status: 'created' as const }));
    }) });
    const out = await q.sync(d);
    expect(out).toMatchObject({ created: 2, rejected: 1, failed: false });
    expect(q.getSnapshot().rejected[0]).toMatchObject({ client_uuid: 'uuid-0002', reason: 'Invalid coordinates' });
    expect(q.getSnapshot().items).toEqual([]);
  });

  it('401/5xx envelope errors are transient: keep everything and back off', async () => {
    const q = mkQ(memoryStore(), memorySelfieFiles());
    await q.enqueue(mk('uuid-0001', '2026-11-13T09:00:00Z'));
    for (const status of [401, 503, 429]) {
      const out = await q.sync(deps({ syncPunches: jest.fn(async () => { throw new ApiError('x', status); }) }), { force: true });
      expect(out.failed).toBe(true);
    }
    expect(q.getSnapshot().items).toHaveLength(1);
    expect(q.getSnapshot().rejected).toHaveLength(0);
  });

  it('a permanently rejected selfie is dropped, persisted and reported', async () => {
    const store = memoryStore();
    const q = mkQ(store, memorySelfieFiles());
    await q.enqueue({ ...mk('uuid-0001', '2026-11-13T09:00:00Z'), selfie_uri: 'file:///c/a.jpg' });
    const d = deps({ uploadSelfie: jest.fn(async () => { throw new ApiError('too big', 413); }), syncPunches: jest.fn(async () => { throw new ApiError('x', 0); }) });
    const out = await q.sync(d, { force: true });
    expect(out.selfieDropped).toBe(1);
    const saved = JSON.parse(store.data!);
    expect(saved.items[0]).toMatchObject({ selfie_path: null, selfie_dropped: true });
  });

  it('is scoped per user: only the current user items are shown or sent; user switch', async () => {
    const store = memoryStore();
    const q = mkQ(store, memorySelfieFiles());
    await q.enqueue(mk('uuid-0001', '2026-11-13T09:00:00Z'));
    q.setUser(2);
    expect(q.getSnapshot().items).toEqual([]);
    await q.enqueue(mk('uuid-0002', '2026-11-13T09:05:00Z'));
    const d = deps();
    await q.sync(d);
    expect(d.sent[0].map((p) => (p as { client_uuid: string }).client_uuid)).toEqual(['uuid-0002']);
    q.setUser(1);
    expect(q.getSnapshot().items.map((i) => i.client_uuid)).toEqual(['uuid-0001']);
    q.setUser(null);
    expect((await q.sync(d)).skipped).toBe('no-user');
  });

  it('purges other users items (and selfies) older than 72h', async () => {
    let now = Date.parse('2026-11-13T12:00:00Z');
    const files = memorySelfieFiles();
    const q = new PunchQueue(memoryStore(), files, () => now);
    q.setUser(1);
    await q.enqueue({ ...mk('uuid-0001', '2026-11-13T09:00:00Z'), selfie_uri: 'file:///c/a.jpg' });
    q.setUser(2);
    await q.enqueue(mk('uuid-0002', '2026-11-13T09:05:00Z'));
    now += 73 * 3_600_000;
    await q.sync(deps());
    expect(q.foreignCount()).toBe(0);
    expect(files.files.size).toBe(0);
  });

  it('notifies listeners after the initial load and quarantines an unreadable file with a notice', async () => {
    const store = memoryStore('{broken');
    const q = mkQ(store, memorySelfieFiles());
    const l = jest.fn();
    q.subscribe(l);
    await q.ready();
    expect(l).toHaveBeenCalled();
    expect(store.quarantined).toBe('{broken');
    expect(q.getSnapshot().notice).toMatch(/set aside/);
  });

  it('drops malformed items but keeps valid ones', async () => {
    const good = { ...mk('uuid-0001', '2026-11-13T09:00:00Z'), user_id: 1, selfie_path: null, selfie_id: null };
    const q = mkQ(memoryStore(JSON.stringify({ items: [good, { client_uuid: 'x' }], rejected: [] })), memorySelfieFiles());
    await q.ready();
    expect(q.getSnapshot().items).toHaveLength(1);
  });

  it('flags items older than 10 hours', () => {
    const now = Date.parse('2026-11-13T20:00:00Z');
    expect(isStale({ captured_at: '2026-11-13T09:00:00Z' }, now)).toBe(true);
    expect(isStale({ captured_at: '2026-11-13T12:00:00Z' }, now)).toBe(false);
  });
});
