import * as Location from 'expo-location';
import * as Notifications from 'expo-notifications';
import { Platform } from 'react-native';
import { getTokens, setTokens } from '../../api/client';
import { tokenStorage } from '../../auth/tokenStorage';
import { fileStore, memoryStore, type PersistentStore } from '../punch/store';
import { postPings, type MyStatus, type WirePing } from './api';
import { PingQueue, type SyncOutcome } from './queue';
import { decideTracking, type Decision } from './window';

export const LOCATION_TASK = 'hrms-shift-location-task';
export const FOREGROUND_NOTIFICATION = {
  notificationTitle: 'Shift location sharing on',
  notificationBody: 'Your location is shared with your scheduler during your rostered shift.',
};

// --- singletons / test hooks ---------------------------------------------------------------------------------------

let queue: PingQueue | null = null;
export function getPingQueue(): PingQueue {
  return (queue ??= new PingQueue(fileStore('ping-queue.json')));
}
export function setPingQueue(q: PingQueue | null) { queue = q; }

/** What the headless task needs to know without any React state or network: who is being tracked and until when. */
export type TrackingMeta = { user_id: number; window_end: number; interval_seconds: number; distance_filter_m: number; mode: 'background' | 'foreground' };
let metaStore: PersistentStore | null = null;
function meta(): PersistentStore { return (metaStore ??= fileStore('tracking-meta.json')); }
export function setMetaStore(s: PersistentStore | null) { metaStore = s; }
export { memoryStore };
export async function readMeta(): Promise<TrackingMeta | null> {
  try {
    const raw = await meta().read();
    const m = raw ? (JSON.parse(raw) as Partial<TrackingMeta>) : null;
    return m && typeof m.user_id === 'number' && typeof m.window_end === 'number' ? (m as TrackingMeta) : null;
  } catch {
    return null;
  }
}
async function writeMeta(m: TrackingMeta | null) {
  try {
    if (m) await meta().write(JSON.stringify(m));
    else await meta().destroy(); // not write(''): that would leave the previous user id in .bak
  } catch { /* best effort */ }
}

// --- permissions ---------------------------------------------------------------------------------------------------

export type PermissionLevel = 'none' | 'foreground' | 'background';
export async function getPermissionLevel(): Promise<PermissionLevel> {
  const fg = await Location.getForegroundPermissionsAsync();
  if (!fg.granted) return 'none';
  const bg = await Location.getBackgroundPermissionsAsync().catch(() => null);
  return bg?.granted ? 'background' : 'foreground';
}
/** Android 13+: the foreground-service notification ("Shift location sharing on") needs POST_NOTIFICATIONS, otherwise the
 * service runs invisibly. Push registration asks too, but only on a device with a project id and after a rationale, so the
 * consent flow makes sure. Never throws. */
export async function ensureNotificationPermission(): Promise<void> {
  if (Platform.OS !== 'android' || Number(Platform.Version) < 33) return;
  try {
    const cur = await Notifications.getPermissionsAsync();
    if (!cur.granted && cur.canAskAgain) await Notifications.requestPermissionsAsync();
  } catch { /* the service still works; only its notification is hidden */ }
}

/** Foreground first (the OS requires that order), then background ("Allow all the time" / "Always"). Call only after the
 * explanation screen. A denied background step is fine: tracking then runs only while the app is open. */
export async function requestPermissions(): Promise<PermissionLevel> {
  await ensureNotificationPermission();
  const fg = await Location.requestForegroundPermissionsAsync();
  if (!fg.granted) return 'none';
  const bg = await Location.requestBackgroundPermissionsAsync().catch(() => null);
  return bg?.granted ? 'background' : 'foreground';
}

// --- start / stop --------------------------------------------------------------------------------------------------

let fgSub: { remove(): void } | null = null;
/** >0 while a consent revoke is in flight: the lifecycle must not (re)start tracking on a stale "consented" status. */
let revoking = 0;
export function beginRevoke() { revoking += 1; }
export function endRevoke() { revoking = Math.max(0, revoking - 1); }
/** After the server rejects pings as outside the window, do not restart for a while (clock skew would flap). */
export const OUTSIDE_WINDOW_COOLDOWN_MS = 5 * 60_000;
let restartBlockedUntil = 0;
/** Test hook. */
export function resetTrackingForTests() { revoking = 0; restartBlockedUntil = 0; fgSub = null; starting = Promise.resolve(); }
let starting: Promise<unknown> = Promise.resolve();

async function stopNative() {
  fgSub?.remove();
  fgSub = null;
  try {
    if (await Location.hasStartedLocationUpdatesAsync(LOCATION_TASK)) await Location.stopLocationUpdatesAsync(LOCATION_TASK);
  } catch { /* not started */ }
}

/** Stop location updates. `clear` also erases the persisted queue (logout, consent revoked, tracking disabled): location
 * data must not outlive the permission. A window simply ending keeps the queue so late uploads still go out. */
export function stopTracking(opts: { clear?: boolean } = {}): Promise<void> {
  const p = starting.then(async () => {
    await stopNative();
    await writeMeta(null);
    if (opts.clear) { restartBlockedUntil = 0; await getPingQueue().clear(); }
  });
  starting = p.catch(() => undefined);
  return p;
}

export type ApplyResult = { running: boolean; mode: 'background' | 'foreground' | null; reason: Decision['reason'] | 'no_permission' | 'revoking' | 'cooling_down' };

/** Local-only safety net, run before any network on app start / foreground: if updates are still running (or meta is gone)
 * after the window ended, stop them now. */
export function enforceWindowEnd(now: number = Date.now()): Promise<boolean> {
  // Same chain as applyStatus/stopTracking: it must not stop tracking that a concurrent apply is just starting.
  const p = starting.then(async () => {
    const m = await readMeta();
    const native = fgSub != null || (await Location.hasStartedLocationUpdatesAsync(LOCATION_TASK).catch(() => false));
    if (!(m ? now > m.window_end : native)) return false;
    await stopNative();
    await writeMeta(null);
    return true;
  });
  starting = p.catch(() => undefined);
  return p;
}

/** Make the device match the decision for `status` at `now`. Idempotent. */
export function applyStatus(status: MyStatus | null | undefined, userId: number, now: number = Date.now()): Promise<ApplyResult> {
  const p = starting.then(() => doApply(status, userId, now));
  starting = p.catch(() => undefined);
  return p;
}

async function doApply(status: MyStatus | null | undefined, userId: number, now: number): Promise<ApplyResult> {
  const d = decideTracking(status, now);
  if (!d.run || !status) {
    await stopNative();
    await writeMeta(null);
    // Without a required+consented policy nothing may stay on the device. A missing status (unknown) changes nothing else.
    if (d.reason === 'disabled' || d.reason === 'no_consent') await getPingQueue().clear();
    return { running: false, mode: null, reason: d.reason };
  }
  if (revoking > 0) { await stopNative(); await writeMeta(null); return { running: false, mode: null, reason: 'revoking' }; }
  if (now < restartBlockedUntil) { await stopNative(); await writeMeta(null); return { running: false, mode: null, reason: 'cooling_down' }; }
  const level = await getPermissionLevel();
  if (level === 'none') {
    await stopNative();
    await writeMeta(null);
    return { running: false, mode: null, reason: 'no_permission' };
  }
  const mode = level === 'background' ? 'background' : 'foreground';
  const next: TrackingMeta = { user_id: userId, window_end: d.windowEnd!, interval_seconds: status.interval_seconds, distance_filter_m: status.distance_filter_m, mode };
  const cur = await readMeta();
  const running = mode === 'background' ? await Location.hasStartedLocationUpdatesAsync(LOCATION_TASK).catch(() => false) : fgSub != null;
  const same = cur && cur.user_id === userId && cur.mode === mode && cur.interval_seconds === next.interval_seconds && cur.distance_filter_m === next.distance_filter_m;
  await writeMeta(next); // the window end can move (re-rostered) without a restart
  if (running && same) return { running: true, mode, reason: 'in_window' };
  await stopNative();
  const ms = next.interval_seconds * 1000;
  try {
  if (mode === 'background') {
    await Location.startLocationUpdatesAsync(LOCATION_TASK, {
      accuracy: Location.Accuracy.Balanced, // battery-aware: no continuous GPS
      distanceInterval: next.distance_filter_m,
      timeInterval: ms, // Android only
      deferredUpdatesInterval: ms, // batch deliveries to the JS side
      deferredUpdatesDistance: next.distance_filter_m,
      pausesUpdatesAutomatically: true, // iOS: pause when stationary
      activityType: Location.ActivityType.Other,
      showsBackgroundLocationIndicator: true,
      foregroundService: { ...FOREGROUND_NOTIFICATION, killServiceOnDestroy: false },
    });
  } else {
    fgSub = await Location.watchPositionAsync(
      { accuracy: Location.Accuracy.Balanced, distanceInterval: next.distance_filter_m, timeInterval: ms },
      (loc) => void handleLocations({ locations: [loc] }).catch(() => undefined),
    );
  }
  } catch (e) {
    await writeMeta(null); // meta was written first (a fix can arrive immediately); a failed start must not leave it behind
    throw e;
  }
  return { running: true, mode, reason: 'in_window' };
}

// --- ingestion (headless-safe: no React, no AuthProvider) -------------------------------------------------------------

type LocLike = { coords: { latitude: number; longitude: number; accuracy?: number | null; speed?: number | null }; timestamp: number };

/** Server ranges: accuracy 0..5000, speed 0..200; both can be -1 / absent on a device. */
const inRange = (v: number | null | undefined, max: number) => (typeof v === 'number' && Number.isFinite(v) && v >= 0 && v <= max ? v : null);
export function toWirePings(locations: LocLike[]): WirePing[] {
  return locations
    .filter((l) => l && l.coords && Number.isFinite(l.coords.latitude) && Number.isFinite(l.coords.longitude) && Number.isFinite(l.timestamp))
    .map((l) => ({
      captured_at: new Date(l.timestamp).toISOString(),
      lat: l.coords.latitude,
      lng: l.coords.longitude,
      accuracy: inRange(l.coords.accuracy, 5000),
      speed: inRange(l.coords.speed, 200),
      battery: null, // no battery module in the app yet; the field is optional server-side
    }));
}

/** Upload what is queued for the current user; honours the stop signals the server sends back. */
export async function flushPings(opts: { force?: boolean } = {}): Promise<SyncOutcome> {
  const q = getPingQueue();
  const out = await q.sync({ postPings }, opts);
  if (out.stop === 'no_consent' || out.stop === 'not_required') await stopTracking({ clear: true });
  else if (out.stop === 'outside_window') { restartBlockedUntil = Date.now() + OUTSIDE_WINDOW_COOLDOWN_MS; await stopTracking(); }
  return out;
}

/** Make sure API calls can authenticate when no React tree is mounted (killed app / headless task). */
async function ensureSession(): Promise<boolean> {
  if (getTokens()) return true;
  const stored = await tokenStorage.load().catch(() => null);
  if (!stored) return false;
  setTokens(stored);
  return true;
}

/**
 * Handles a batch of locations from the TaskManager task (or the foreground watcher). Verifies the signed-in user is the
 * one being tracked, discards anything after the window end (and stops there), enqueues, then uploads.
 */
export async function handleLocations(payload: unknown, now: number = Date.now()): Promise<void> {
  const locations = ((payload as { locations?: LocLike[] } | null)?.locations ?? []) as LocLike[];
  if (!locations.length) return;
  const gen = getPingQueue().generation; // before any await: a clear() after this point must win over this fix
  const m = await readMeta();
  if (!m) { await stopTracking(); return; } // nothing is supposed to be running
  if (!(await ensureSession())) { await stopTracking({ clear: true }); return; } // signed out
  const me = await tokenStorage.loadMe<{ id?: number }>();
  if (typeof me?.id !== 'number' || me.id !== m.user_id) { await stopTracking({ clear: true }); return; } // different user
  const q = getPingQueue();
  q.setUser(m.user_id);
  // Never record past the window end, whatever the OS delivers late.
  const inside = locations.filter((l) => l.timestamp <= m.window_end);
  await q.enqueue(toWirePings(inside), { generation: gen });
  if (now > m.window_end) {
    await flushPings({ force: true }).catch(() => undefined); // last chance to send what was captured inside the window
    await stopTracking(); // keep any failed remainder queued for the next foreground flush
    return;
  }
  await flushPings().catch(() => undefined);
}
