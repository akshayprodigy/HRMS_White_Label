import * as Location from 'expo-location';
import type { Fix } from './api';

export type PermState = 'unknown' | 'granted' | 'denied' | 'blocked';

export async function checkPermission(): Promise<PermState> {
  const p = await Location.getForegroundPermissionsAsync();
  return p.granted ? 'granted' : p.canAskAgain === false && p.status === 'denied' ? 'blocked' : 'unknown';
}
export async function requestPermission(): Promise<PermState> {
  const p = await Location.requestForegroundPermissionsAsync();
  return p.granted ? 'granted' : p.canAskAgain === false ? 'blocked' : 'denied';
}
/** `mocked` is Android only; iOS cannot tell, so isMock is false there (the server treats the flag as untrusted anyway). */
export const FIX_TIMEOUT_MS = 15_000;
/** Always a fresh reading: never falls back to an old position. Rejects after the timeout. */
export async function getFix(timeoutMs = FIX_TIMEOUT_MS): Promise<Fix> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  const timeout = new Promise<never>((_, rej) => { timer = setTimeout(() => rej(new Error('location timeout')), timeoutMs); });
  try {
    return await Promise.race([readFix(), timeout]);
  } finally {
    clearTimeout(timer);
  }
}
async function readFix(): Promise<Fix> {
  const pos = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.High, mayShowUserSettingsDialog: false });
  return { latitude: pos.coords.latitude, longitude: pos.coords.longitude, accuracy: pos.coords.accuracy ?? null, isMock: pos.mocked === true };
}
