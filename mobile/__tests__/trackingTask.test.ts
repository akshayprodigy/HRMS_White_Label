import axios from 'axios';
import MockAdapter from 'axios-mock-adapter';
import { getTokens, setAdapter, setTokens } from '../src/api/client';
import { tokenStorage } from '../src/auth/tokenStorage';
import { memoryStore } from '../src/features/punch/store';
import type { MyStatus } from '../src/features/tracking/api';
import { PingQueue } from '../src/features/tracking/queue';
import { applyStatus, beginRevoke, endRevoke, enforceWindowEnd, flushPings, OUTSIDE_WINDOW_COOLDOWN_MS, resetTrackingForTests, handleLocations, LOCATION_TASK, readMeta, setMetaStore, setPingQueue, stopTracking, toWirePings } from '../src/features/tracking/tracking';
import '../src/features/tracking/task';

jest.mock('../src/config/tenant', () => ({ getTenant: () => ({ id: 'dev' }), getApiBaseUrl: () => 'http://test/api/v1' }));
// defineTask runs at import time, before module-level consts exist: record on globalThis.
jest.mock('expo-task-manager', () => ({ defineTask: (...a: unknown[]) => ((globalThis as { __tasks?: unknown[][] }).__tasks ??= []).push(a) }));
jest.mock('expo-notifications', () => ({ getPermissionsAsync: async () => ({ granted: true }), requestPermissionsAsync: async () => ({ granted: true }) }));
const mockLoc = {
  started: false,
  fg: { granted: true } as { granted: boolean },
  bg: { granted: true } as { granted: boolean },
  start: jest.fn(async () => { mockLoc.started = true; }),
  stop: jest.fn(async () => { mockLoc.started = false; }),
  watch: jest.fn(async (_o: unknown, _cb: (l: unknown) => void) => ({ remove: jest.fn() })),
};
jest.mock('expo-location', () => ({
  Accuracy: { Balanced: 3 },
  ActivityType: { Other: 4 },
  getForegroundPermissionsAsync: async () => mockLoc.fg,
  getBackgroundPermissionsAsync: async () => mockLoc.bg,
  requestForegroundPermissionsAsync: async () => mockLoc.fg,
  requestBackgroundPermissionsAsync: async () => mockLoc.bg,
  hasStartedLocationUpdatesAsync: async () => mockLoc.started,
  startLocationUpdatesAsync: (...a: unknown[]) => mockLoc.start(...(a as [])),
  stopLocationUpdatesAsync: () => mockLoc.stop(),
  watchPositionAsync: (o: unknown, cb: (l: unknown) => void) => mockLoc.watch(o, cb),
}));

const taskDefinedAtImport = (globalThis as { __tasks?: unknown[][] }).__tasks ?? [];
const NOW = Date.parse('2026-11-13T12:00:00Z');
const END = Date.parse('2026-11-13T18:30:00Z');
const loc = (ts: number, over: object = {}) => ({ coords: { latitude: 12.97, longitude: 77.59, accuracy: 12, speed: 1.5, ...over }, timestamp: ts });
const status = (over: Partial<MyStatus> = {}): MyStatus => ({
  required: true, consented: true, consented_at: '2026-11-01T00:00:00+00:00', active: true,
  window: { work_date: '2026-11-13', start: '2026-11-13T08:30:00+00:00', end: '2026-11-13T18:30:00+00:00', shift_start: '2026-11-13T09:00:00+00:00', shift_end: '2026-11-13T18:00:00+00:00', in_window: true },
  interval_seconds: 300, distance_filter_m: 100, ...over,
});

let mock: MockAdapter;
let queue: PingQueue;
beforeEach(async () => {
  mock = new MockAdapter(axios);
  setAdapter(mock.adapter());
  setTokens(null);
  await tokenStorage.save({ accessToken: 'stored-a', refreshToken: 'stored-r' });
  await tokenStorage.saveMe({ id: 1 });
  setMetaStore(memoryStore());
  resetTrackingForTests();
  queue = new PingQueue(memoryStore());
  setPingQueue(queue);
  mockLoc.started = false;
  mockLoc.fg = { granted: true };
  mockLoc.bg = { granted: true };
  mockLoc.start.mockClear(); mockLoc.stop.mockClear(); mockLoc.watch.mockClear();
  jest.spyOn(console, 'warn').mockImplementation(() => undefined);
});
afterEach(() => { setAdapter(undefined); setTokens(null); jest.restoreAllMocks(); });

describe('task definition', () => {
  it('defines the location task at module load (JS startup)', () => {
    expect(taskDefinedAtImport.some((a) => a[0] === LOCATION_TASK)).toBe(true);
  });
});

describe('toWirePings', () => {
  it('maps fixes and nulls out-of-range accuracy/speed (iOS reports -1)', () => {
    const [p] = toWirePings([loc(NOW, { speed: -1, accuracy: -1 })]);
    expect(p).toEqual({ captured_at: '2026-11-13T12:00:00.000Z', lat: 12.97, lng: 77.59, accuracy: null, speed: null, battery: null });
    expect(toWirePings([loc(NOW, { speed: 3 }), { coords: { latitude: NaN, longitude: 1 }, timestamp: NOW }])).toHaveLength(1);
  });
});

describe('headless handleLocations', () => {
  beforeEach(async () => {
    await applyStatus(status(), 1, NOW); // writes the meta the headless task relies on
    setTokens(null); // simulate a killed app: nothing in memory
    mock.onPost('/tracking/pings').reply(200, { accepted: 1, dropped: {} });
  });

  it('loads the stored session, queues and uploads with its token (no AuthProvider)', async () => {
    expect(getTokens()).toBeNull();
    await handleLocations({ locations: [loc(NOW)] }, NOW);
    const req = mock.history.post.find((r) => r.url === '/tracking/pings')!;
    expect(req.headers?.Authorization).toBe('Bearer stored-a');
    expect(JSON.parse(req.data).pings).toHaveLength(1);
    expect(await queue.size()).toBe(0);
  });
  it('keeps pings queued when the upload fails (backoff) and does not stop tracking', async () => {
    mock.onPost('/tracking/pings').reply(503);
    await handleLocations({ locations: [loc(NOW)] }, NOW);
    expect(await queue.size()).toBe(1);
    expect(await readMeta()).not.toBeNull();
  });
  it('does nothing without locations', async () => {
    await handleLocations({ locations: [] }, NOW);
    expect(mock.history.post).toHaveLength(0);
  });
  it('stops and records nothing when nothing is supposed to be running', async () => {
    await stopTracking();
    await handleLocations({ locations: [loc(NOW)] }, NOW);
    expect(mock.history.post).toHaveLength(0);
    expect(await queue.size()).toBe(0);
  });
  it('signed out: stops tracking and clears the queue', async () => {
    await tokenStorage.clear();
    await handleLocations({ locations: [loc(NOW)] }, NOW);
    expect(mockLoc.stop).toHaveBeenCalled();
    expect(mock.history.post).toHaveLength(0);
    expect(await readMeta()).toBeNull();
  });
  it('a different user signed in: stops, clears and never uploads as them', async () => {
    queue.setUser(1);
    await queue.enqueue(toWirePings([loc(NOW - 1000)]));
    await tokenStorage.saveMe({ id: 2 });
    await handleLocations({ locations: [loc(NOW)] }, NOW);
    expect(mock.history.post).toHaveLength(0);
    expect(await readMeta()).toBeNull();
    expect(await queue.size()).toBe(0);
  });
  it('an unknown profile (cannot verify the user) is treated as a mismatch', async () => {
    await tokenStorage.saveMe(null);
    await handleLocations({ locations: [loc(NOW)] }, NOW);
    expect(mock.history.post).toHaveLength(0);
  });
  it('discards fixes captured after the window end; after the end it flushes once and stops, keeping a failed remainder', async () => {
    mock.onPost('/tracking/pings').reply(503);
    await handleLocations({ locations: [loc(END - 1000), loc(END + 60_000)] }, END + 120_000);
    expect(mockLoc.stop).toHaveBeenCalled();
    expect(await readMeta()).toBeNull();
    const kept = await queue.pending();
    expect(kept).toHaveLength(1); // only the in-window fix
    expect(kept[0].captured_at).toBe(new Date(END - 1000).toISOString());
  });
  it('server says no_consent: stops and erases the queue', async () => {
    mock.onPost('/tracking/pings').reply(200, { accepted: 0, dropped: { no_consent: 1 } });
    await handleLocations({ locations: [loc(NOW)] }, NOW);
    expect(await readMeta()).toBeNull();
    expect(mockLoc.stop).toHaveBeenCalled();
    expect(await queue.size()).toBe(0);
  });
  it('server says outside_window: stops (queue is already judged)', async () => {
    mock.onPost('/tracking/pings').reply(200, { accepted: 0, dropped: { outside_window: 1 } });
    await handleLocations({ locations: [loc(NOW)] }, NOW);
    expect(await readMeta()).toBeNull();
    expect(mockLoc.stop).toHaveBeenCalled();
  });
});

describe('applyStatus (start/stop wiring)', () => {
  it('starts background updates with battery-aware options and the foreground-service text', async () => {
    const r = await applyStatus(status({ interval_seconds: 600, distance_filter_m: 250 }), 1, NOW);
    expect(r).toEqual({ running: true, mode: 'background', reason: 'in_window' });
    expect(mockLoc.start).toHaveBeenCalledWith(LOCATION_TASK, expect.objectContaining({
      accuracy: 3, distanceInterval: 250, deferredUpdatesInterval: 600_000, timeInterval: 600_000,
      foregroundService: expect.objectContaining({ notificationTitle: 'Shift location sharing on' }),
    }));
    expect(await readMeta()).toMatchObject({ user_id: 1, window_end: END, mode: 'background' });
  });
  it('is idempotent, and restarts when the policy changes', async () => {
    await applyStatus(status(), 1, NOW);
    await applyStatus(status(), 1, NOW + 60_000);
    expect(mockLoc.start).toHaveBeenCalledTimes(1);
    await applyStatus(status({ distance_filter_m: 500 }), 1, NOW + 120_000);
    expect(mockLoc.start).toHaveBeenCalledTimes(2);
  });
  it('stops when the window has ended, but keeps queued pings', async () => {
    queue.setUser(1);
    await queue.enqueue(toWirePings([loc(NOW)]));
    await applyStatus(status(), 1, NOW);
    const r = await applyStatus(status(), 1, END + 1000);
    expect(r).toMatchObject({ running: false, reason: 'after_window' });
    expect(mockLoc.stop).toHaveBeenCalled();
    expect(await readMeta()).toBeNull();
    expect(await queue.size()).toBe(1);
  });
  it.each([[{ required: false }, 'disabled'], [{ consented: false }, 'no_consent']])('%j: stops and erases the queue', async (over, reason) => {
    queue.setUser(1);
    await queue.enqueue(toWirePings([loc(NOW)]));
    await applyStatus(status(), 1, NOW);
    const r = await applyStatus(status(over as Partial<MyStatus>), 1, NOW);
    expect(r.reason).toBe(reason);
    expect(await queue.size()).toBe(0);
    expect(mockLoc.started).toBe(false);
  });
  it('does not start before the window', async () => {
    expect(await applyStatus(status(), 1, Date.parse('2026-11-13T07:00:00Z'))).toMatchObject({ running: false, reason: 'before_window' });
    expect(mockLoc.start).not.toHaveBeenCalled();
  });
  it('without background permission it watches in the foreground only', async () => {
    mockLoc.bg = { granted: false };
    const r = await applyStatus(status(), 1, NOW);
    expect(r).toEqual({ running: true, mode: 'foreground', reason: 'in_window' });
    expect(mockLoc.start).not.toHaveBeenCalled();
    expect(mockLoc.watch).toHaveBeenCalledWith(expect.objectContaining({ accuracy: 3, distanceInterval: 100 }), expect.any(Function));
  });
  it('without location permission it does not run at all', async () => {
    mockLoc.fg = { granted: false };
    mockLoc.bg = { granted: false };
    expect(await applyStatus(status(), 1, NOW)).toMatchObject({ running: false, reason: 'no_permission' });
    expect(mockLoc.start).not.toHaveBeenCalled();
    expect(mockLoc.watch).not.toHaveBeenCalled();
  });
  it('stopTracking({clear}) is what logout uses: stops updates and erases queued locations', async () => {
    queue.setUser(1);
    await queue.enqueue(toWirePings([loc(NOW)]));
    await applyStatus(status(), 1, NOW);
    await stopTracking({ clear: true });
    expect(mockLoc.started).toBe(false);
    expect(await readMeta()).toBeNull();
    expect(await queue.size()).toBe(0);
  });
  it('stopping leaves no tracking-meta backup (the old user id must not linger in .bak)', async () => {
    const meta = memoryStore();
    setMetaStore(meta);
    await applyStatus(status(), 1, NOW);
    await applyStatus(status(), 1, NOW); // second write: first becomes .bak
    expect(meta.bak).not.toBeNull();
    await stopTracking({ clear: true });
    expect(meta).toMatchObject({ data: null, bak: null, tmp: null, quarantined: null });
  });
});

describe('window-end heartbeat and safety net', () => {
  it('uses the policy interval for timeInterval (no separate heartbeat)', async () => {
    await applyStatus(status({ interval_seconds: 3600 }), 1, NOW);
    expect((mockLoc.start.mock.calls[0] as unknown[])[1]).toMatchObject({ timeInterval: 3_600_000, deferredUpdatesInterval: 3_600_000 });
  });
  it('enforceWindowEnd is serialized with applyStatus: a concurrent start is not stopped by a stale check', async () => {
    let release!: () => void;
    mockLoc.start.mockImplementationOnce(() => new Promise<void>((r) => { release = () => { mockLoc.started = true; r(); }; }));
    const apply = applyStatus(status(), 1, NOW);
    const enforce = enforceWindowEnd(NOW + 1000); // inside the window: must wait for the start, then see meta and do nothing
    await new Promise((r) => setTimeout(r, 10));
    release();
    await apply;
    expect(await enforce).toBe(false);
    expect(mockLoc.started).toBe(true);
    expect(await readMeta()).not.toBeNull();
  });
  it('enforceWindowEnd stops a session still running past the window end, before any network call', async () => {
    await applyStatus(status(), 1, NOW);
    expect(await enforceWindowEnd(NOW)).toBe(false);
    expect(mockLoc.started).toBe(true);
    expect(await enforceWindowEnd(END + 1000)).toBe(true);
    expect(mockLoc.started).toBe(false);
    expect(await readMeta()).toBeNull();
    expect(mock.history).toMatchObject({ get: [], post: [] });
  });
  it('enforceWindowEnd also stops a native session whose meta is gone', async () => {
    mockLoc.started = true;
    expect(await enforceWindowEnd(NOW)).toBe(true);
    expect(mockLoc.started).toBe(false);
  });
});

describe('start failure, revoke race, outside_window cooldown', () => {
  it('a failed start does not leave meta behind', async () => {
    mockLoc.start.mockRejectedValueOnce(new Error('boom'));
    await expect(applyStatus(status(), 1, NOW)).rejects.toThrow('boom');
    expect(await readMeta()).toBeNull();
  });
  it('does not (re)start tracking while a revoke is in flight, and resumes after it ends', async () => {
    beginRevoke();
    expect(await applyStatus(status(), 1, NOW)).toMatchObject({ running: false, reason: 'revoking' });
    expect(mockLoc.start).not.toHaveBeenCalled();
    endRevoke();
    expect((await applyStatus(status(), 1, NOW)).running).toBe(true);
  });
  it('revoke interleaving: stale consented status arriving mid-revoke cannot restart; the fresh one keeps it off', async () => {
    await applyStatus(status(), 1, NOW);
    beginRevoke();
    await stopTracking({ clear: true });
    await applyStatus(status(), 1, NOW + 1000); // lifecycle tick with the stale status
    expect(mockLoc.started).toBe(false);
    endRevoke();
    await applyStatus(status({ consented: false }), 1, NOW + 2000);
    expect(mockLoc.started).toBe(false);
    expect(mockLoc.start).toHaveBeenCalledTimes(1);
  });
  it('after the server rejects pings as outside_window, restart is blocked for 5 minutes', async () => {
    await applyStatus(status(), 1, NOW);
    queue.setUser(1);
    await queue.enqueue(toWirePings([loc(NOW)]));
    mock.onPost('/tracking/pings').reply(200, { accepted: 0, dropped: { outside_window: 1 } });
    setTokens({ accessToken: 't', refreshToken: 'r' });
    const real = Date.now;
    Date.now = () => NOW;
    try {
      await flushPings();
      expect(mockLoc.started).toBe(false);
      expect(await applyStatus(status(), 1, NOW + 60_000)).toMatchObject({ running: false, reason: 'cooling_down' });
      expect((await applyStatus(status(), 1, NOW + OUTSIDE_WINDOW_COOLDOWN_MS + 1)).running).toBe(true);
    } finally {
      Date.now = real;
    }
  });
});
