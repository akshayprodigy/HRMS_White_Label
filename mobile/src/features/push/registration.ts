import Constants from 'expo-constants';
import * as Device from 'expo-device';
import * as Notifications from 'expo-notifications';
import { Alert, Platform } from 'react-native';
import { api } from '../../api/client';
import { getTenant } from '../../config/tenant';
import { setupCategories, setupChannels } from './categories';

let registeredToken: string | null = null;
let inflight: Promise<string | null> | null = null;

export function getRegisteredToken() {
  return registeredToken;
}
export function resetRegistrationForTests() {
  registeredToken = null;
  inflight = null;
}

function projectId(): string | undefined {
  const extra = Constants.expoConfig?.extra as { eas?: { projectId?: string } } | undefined;
  return extra?.eas?.projectId ?? (Constants as { easConfig?: { projectId?: string } }).easConfig?.projectId;
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
  if (!(await askRationale())) return false;
  return (await Notifications.requestPermissionsAsync()).granted;
}

async function doRegister(): Promise<string | null> {
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
  await api.post('/devices', {
    token,
    platform: Platform.OS === 'ios' ? 'ios' : 'android',
    app_version: Constants.expoConfig?.version ?? undefined,
    tenant: getTenant().id,
  });
  registeredToken = token;
  return token;
}

/** Idempotent + single-flight; never throws (push must not break login). */
export function registerForPush(): Promise<string | null> {
  if (!inflight) {
    inflight = doRegister()
      .catch((e) => {
        console.warn('[push] registration failed', e instanceof Error ? e.message : e);
        return null;
      })
      .finally(() => {
        inflight = null;
      });
  }
  return inflight;
}

/** Best-effort revoke; MUST run while the access token is still set. Never throws, never blocks long. */
export async function unregisterPush(): Promise<void> {
  const token = registeredToken;
  registeredToken = null;
  if (!token) return;
  try {
    await api.delete(`/devices/${encodeURIComponent(token)}`, { timeout: 4000 });
  } catch {
    /* logout must not depend on it; the backend also revokes dead tokens */
  }
}
