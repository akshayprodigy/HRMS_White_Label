import type MockAdapter from 'axios-mock-adapter';
import { submitPunch, type PunchInput } from '../src/features/punch/api';
import { PunchQueue } from '../src/features/punch/queue';
import { memorySelfieFiles, memoryStore } from '../src/features/punch/store';
import { setupApiMock, teardownApiMock } from '../test-utils';

jest.mock('../src/config/tenant', () => ({ getTenant: () => ({ features: {} }), getApiBaseUrl: () => 'http://test/api/v1' }));
jest.mock('expo-file-system', () => ({ File: class {}, Directory: class {}, Paths: {} }));
jest.mock('expo-image-manipulator', () => ({ manipulateAsync: jest.fn(), SaveFormat: { JPEG: 'jpeg' } }));

let mock: MockAdapter;
let q: PunchQueue;
beforeEach(() => { mock = setupApiMock(); q = new PunchQueue(memoryStore(), memorySelfieFiles()); });
afterEach(teardownApiMock);

const fix = { latitude: 12.9, longitude: 77.6, accuracy: 12, isMock: true };
const input = (over: Partial<PunchInput> = {}): PunchInput => ({ kind: 'in', fix, uuid: () => 'uuid-1234-abcd', ...over });
const selfie = { uri: 'file:///s.jpg', liveness_passed: null, liveness_score: null };

describe('submitPunch', () => {
  it('uploads the selfie (multipart file) then punches with selfie_id and liveness', async () => {
    let sentForm: FormData | undefined;
    let sentType = '';
    mock.onPost('/attendance/selfie').reply((cfg) => {
      sentForm = cfg.data as FormData;
      sentType = String(cfg.headers?.['Content-Type'] ?? '');
      return [200, { selfie_id: 7 }];
    });
    mock.onPost('/attendance/mark').reply(200, { id: 1, captured_at: 'x', punch_out_time: null, geo_flag: 'OUTSIDE_FENCE_FLAGGED' });
    const out = await submitPunch(input({ selfie: { ...selfie, liveness_passed: true, liveness_score: 0.9 } }), q);
    expect(sentForm).toBeInstanceOf(FormData);
    expect(sentForm!.has('file')).toBe(true);
    expect(sentType).toMatch(/multipart\/form-data/);
    expect(out).toMatchObject({ status: 'ok', flag: 'OUTSIDE_FENCE_FLAGGED' });
    const body = JSON.parse(mock.history.post.find((r) => r.url === '/attendance/mark')!.data);
    expect(body).toEqual({ mode: 'mobile', latitude: 12.9, longitude: 77.6, accuracy: 12, is_mock_location: true, selfie_id: 7, liveness_passed: true, liveness_score: 0.9 });
    expect(mock.history.post.map((r) => r.url)).toEqual(['/attendance/selfie', '/attendance/mark']);
  });

  it('punch-out goes to /attendance/punch-out', async () => {
    mock.onPost('/attendance/punch-out').reply(200, { id: 1, captured_at: 'x', punch_out_time: 'y' });
    expect((await submitPunch(input({ kind: 'out' }), q)).status).toBe('ok');
  });

  it('shows the 422 geofence rejection message and code, and does not queue', async () => {
    mock.onPost('/attendance/mark').reply(422, { detail: { error: 'OUTSIDE_GEOFENCE', message: 'You are 420 m from Head Office.' } });
    const out = await submitPunch(input(), q);
    expect(out).toMatchObject({ status: 'error', error: { status: 422, code: 'OUTSIDE_GEOFENCE', message: 'You are 420 m from Head Office.' } });
    expect(q.getSnapshot().items).toHaveLength(0);
  });

  it('a missing-selfie 400 asks for a selfie and is not queued', async () => {
    mock.onPost('/attendance/mark').reply(400, { detail: 'A selfie is required to punch in.' });
    const out = await submitPunch(input(), q);
    expect(out).toMatchObject({ status: 'error', needsSelfie: true });
    expect(q.getSnapshot().items).toHaveLength(0);
  });

  it('other 4xx (403/409) are not queued', async () => {
    mock.onPost('/attendance/mark').reply(409, { detail: 'Concurrent update; retry' });
    expect((await submitPunch(input(), q)).status).toBe('error');
    expect(q.getSnapshot().items).toHaveLength(0);
  });

  it('a network error queues the punch with device time, coords and a client uuid', async () => {
    mock.onPost('/attendance/selfie').reply(200, { selfie_id: 3 });
    mock.onPost('/attendance/mark').networkError();
    const out = await submitPunch(input({ selfie }), q);
    expect(out.status).toBe('queued');
    const item = q.getSnapshot().items[0];
    expect(item).toMatchObject({ client_uuid: 'uuid-1234-abcd', kind: 'in', latitude: 12.9, is_mock_location: true, liveness_passed: null });
    expect(item.selfie_path).toContain('uuid-1234-abcd');
    expect(item.selfie_id).toBe(3); // already uploaded: not re-uploaded on sync
    expect(Date.now() - Date.parse(item.captured_at)).toBeLessThan(5000);
  });

  it('a 5xx queues; a selfie upload network failure queues with the local selfie', async () => {
    mock.onPost('/attendance/mark').reply(503);
    expect((await submitPunch(input(), q)).status).toBe('queued');
    mock.reset();
    mock.onPost('/attendance/selfie').networkError();
    const out = await submitPunch(input({ selfie, uuid: () => 'uuid-5678-efgh' }), q);
    expect(out.status).toBe('queued');
    expect(mock.history.post.some((r) => r.url === '/attendance/mark')).toBe(false);
    expect(q.getSnapshot().items.find((i) => i.client_uuid === 'uuid-5678-efgh')?.selfie_id).toBeNull();
  });

  it('a selfie upload 4xx is an error, not queued', async () => {
    mock.onPost('/attendance/selfie').reply(413, { detail: 'Selfie exceeds the 3 MB limit' });
    const out = await submitPunch(input({ selfie }), q);
    expect(out).toMatchObject({ status: 'error', error: { status: 413 } });
    expect(q.getSnapshot().items).toHaveLength(0);
  });
});
