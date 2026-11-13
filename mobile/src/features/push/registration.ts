import Constants from 'expo-constants';
import * as Device from 'expo-device';
import * as Notifications from 'expo-notifications';
import * as SecureStore from 'expo-secure-store';
import { Alert, Platform } from 'react-native';
import { api, getTokens } from '../../api/client';
import { getTenant } from '../../config/tenant';
import { setupCategories, setupChannels } from './categories';

let registeredToken: string | null = null;
let inflight: { promise: Promise<string | null>; epoch: number } | null = null;
/** Bumped by unregisterPush (logout). A registration that started under an older epoch must not record or keep its token. */
let sessionEpoch = 0;

export function getRegisteredToken() {
  return registeredToken;
}
export function resetRegistrationForTests() {
  registeredToken = null;
  inflight = null;
  sessionEpoch = 0;
}

function projectId(): string | undefined {
  const extra = Constants.expoConfig?.extra as { eas?: { projectId?: string } } | undefined;
  return extra?.eas?.projectId ?? (Constants as { easConfig?: { projectId?: string } }).easConfig?.projectId;
}

const DECLINED_KEY = 'hrms.push_declined_at';
export const RATIONALE_COOLDOWN_MS = 7 * 24 * 3600 * 1000;
async function declinedRecently(): Promise<boolean> {
  const raw = await SecureStore.getItemAsync(DECLINED_KEY).catch(() => null);
  const at = raw ? Number(raw) : NaN;
  return Number.isFinite(at) && Date.now() - at < RATIONALE_COOLDOWN_MS;
}

/** Rationale first, then the OS prompt, so the system dialog never appears cold. */
function askRationale(): Promise<boolean> {
  return new Promise((resolve) => {
    Alert.alert(
      'Stay in the loop',
      'Allow notifications so you get shift changes, approval requests and emergency alerts even when the app is closed.',
      [
        { text: 'Not now', style: 'cancel', onPress: () => resolve(false) },
        { text: 'Allow', onPress: () => resolve(true) },
      ],
      { cancelable: false },
    );
  });
}

async function ensurePermission(): Promise<boolean> {
  const cur = await Notifications.getPermissionsAsync();
  if (cur.granted) return true;
  if (!cur.canAskAgain) return false;
  if (await declinedRecently()) return false;
  if (!(await askRationale())) {
    await SecureStore.setItemAsync(DECLINED_KEY, String(Date.now())).catch(() => undefined);
    return false;
  }
  return (await Notifications.requestPermissionsAsync()).granted;
}

async function doRegister(epoch: number): Promise<string | null> {
  const stale = () => epoch !== sessionEpoch || !getTokens();
  const pid = projectId();
  if (!pid) {
    console.warn('[push] No EAS projectId in app config; skipping push registration (expected in local dev).');
    return null;
  }
  if (!Device.isDevice) {
    console.warn('[push] Push tokens need a physical device; skipping registration.');
    return null;
  }
  await setupChannels(); // Android 13+ needs the channel before the permission prompt
  await setupCategories();
  if (!(await ensurePermission())) return null;
  const { data: token } = await Notifications.getExpoPushTokenAsync({ projectId: pid });
  if (stale()) return null; // logged out while the prompt / token fetch was in flight
  await api.post('/devices', {
    token,
    platform: Platform.OS === 'ios' ? 'ios' : 'android',
    app_version: Constants.expoConfig?.version ?? undefined,
    tenant: getTenant().id,
  });
  if (stale()) {
    // Logout raced the POST: undo it now (unregisterPush is waiting on us, so the session is still valid) and don't record it.
    await api.delete(`/devices/${encodeURIComponent(token)}`, { timeout: 4000 }).catch(() => undefined);
    return null;
  }
  registeredToken = token;
  return token;
}

/** Single-flight per session (a registration begun under an older session is awaited, then redone); never throws (push must not break login). */
export function registerForPush(): Promise<string | null> {
  if (inflight && inflight.epoch === sessionEpoch) return inflight.promise;
  const prior = inflight?.promise;
  const epoch = sessionEpoch;
  const promise: Promise<string | null> = (prior ?? Promise.resolve(null))
    .then(() => doRegister(epoch))
    .catch((e) => {
      console.warn('[push] registration failed', e instanceof Error ? e.message : e);
      return null;
    })
    .finally(() => {
      if (inflight?.promise === promise) inflight = null;
    });
  inflight = { promise, epoch };
  return promise;
}

/** Best-effort revoke; MUST run while the access token is still set. Never throws, never blocks long. */
export async function unregisterPush(): Promise<void> {
  sessionEpoch += 1; // invalidates any registration still in flight...
  await inflight?.promise.catch(() => undefined); // ...and lets it finish its own undo while the session is still valid
  const token = registeredToken;
  registeredToken = null;
  if (!token) return;
  try {
    await api.delete(`/devices/${encodeURIComponent(token)}`, { timeout: 4000 });
  } catch {
    /* logout must not depend on it; the backend also revokes dead tokens */
  }
}

/** Logout hygiene: A's tray entries and any undelivered tap must not be actionable by the next user. Best-effort. */
export function clearNotificationState(): void {
  void Notifications.dismissAllNotificationsAsync().catch(() => undefined);
  try {
    Notifications.clearLastNotificationResponse();
  } catch {
    /* not available on this platform */
  }
}
