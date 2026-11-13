import { ApiError } from '../src/api/errors';
import { BACKOFF_BASE_MS, BACKOFF_MAX_MS, PunchQueue, backoffDelay, isStale, type SyncDeps, type SyncResult } from '../src/features/punch/queue';
import { memorySelfieFiles, memoryStore } from '../src/features/punch/store';

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
    const q1 = new PunchQueue(store, memorySelfieFiles());
    await q1.enqueue(mk('uuid-0002', '2026-11-13T10:00:00Z'));
    await q1.enqueue(mk('uuid-0001', '2026-11-13T09:00:00Z'));
    const q2 = new PunchQueue(store, memorySelfieFiles());
    await q2.ready();
    expect(q2.getSnapshot().items.map((i) => i.client_uuid)).toEqual(['uuid-0001', 'uuid-0002']);
  });

  it('survives a corrupt store', async () => {
    const q = new PunchQueue(memoryStore('{nope'), memorySelfieFiles());
    await q.ready();
    expect(q.getSnapshot().items).toEqual([]);
  });

  it('created/duplicate are removed; rejected moves to the rejected list with its reason', async () => {
    const files = memorySelfieFiles();
    const q = new PunchQueue(memoryStore(), files);
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
    const q = new PunchQueue(memoryStore(), memorySelfieFiles());
    await q.enqueue({ ...mk('uuid-0001', '2026-11-13T09:00:00Z'), selfie_uri: 'file:///c/a.jpg' });
    const d = deps();
    await q.sync(d);
    expect(d.uploadSelfie).toHaveBeenCalledTimes(1);
    expect(d.sent[0][0]).toMatchObject({ client_uuid: 'uuid-0001', selfie_id: 99 });
    expect(d.sent[0][0]).not.toHaveProperty('selfie_path');
  });

  it('network failure keeps items, grows the backoff exponentially and skips until it elapses', async () => {
    let now = 1_000_000;
    const q = new PunchQueue(memoryStore(), memorySelfieFiles(), () => now);
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
    const q = new PunchQueue(memoryStore(), memorySelfieFiles());
    await q.enqueue({ ...mk('uuid-0001', '2026-11-13T09:00:00Z'), selfie_uri: 'file:///c/a.jpg' });
    const d = deps({ uploadSelfie: jest.fn(async () => { throw new ApiError('net', 0); }) });
    const out = await q.sync(d);
    expect(out.failed).toBe(true);
    expect(d.syncPunches).not.toHaveBeenCalled();
    expect(q.getSnapshot().items[0].selfie_path).not.toBeNull();
  });

  it('keeps an already-uploaded selfie_id after a partial failure (no re-upload)', async () => {
    const q = new PunchQueue(memoryStore(), memorySelfieFiles());
    await q.enqueue({ ...mk('uuid-0001', '2026-11-13T09:00:00Z'), selfie_uri: 'file:///c/a.jpg' });
    const d = deps({ syncPunches: jest.fn(async () => { throw new ApiError('net', 0); }) });
    await q.sync(d, { force: true });
    await q.sync(d, { force: true });
    expect(d.uploadSelfie).toHaveBeenCalledTimes(1);
  });

  it('items the server gave no verdict for stay queued', async () => {
    const q = new PunchQueue(memoryStore(), memorySelfieFiles());
    await q.enqueue(mk('uuid-0001', '2026-11-13T09:00:00Z'));
    await q.sync(deps({ syncPunches: jest.fn(async () => []) }));
    expect(q.getSnapshot().items).toHaveLength(1);
  });

  it('flags items older than 10 hours', () => {
    const now = Date.parse('2026-11-13T20:00:00Z');
    expect(isStale({ captured_at: '2026-11-13T09:00:00Z' }, now)).toBe(true);
    expect(isStale({ captured_at: '2026-11-13T12:00:00Z' }, now)).toBe(false);
  });
});
