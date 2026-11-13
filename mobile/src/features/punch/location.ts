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
export async function getFix(): Promise<Fix> {
  const pos = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.High });
  return { latitude: pos.coords.latitude, longitude: pos.coords.longitude, accuracy: pos.coords.accuracy ?? null, isMock: pos.mocked === true };
}
