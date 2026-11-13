import Constants from 'expo-constants';
import { Platform } from 'react-native';

/** iOS uses Apple Maps (no key). Android's Google Maps SDK crashes at mount without a key, so the map is only offered when
 * app.config.ts found GOOGLE_MAPS_API_KEY at build time; otherwise the Field team screen is list-only. */
export function mapsAvailable(): boolean {
  if (Platform.OS === 'ios') return true;
  return (Constants.expoConfig?.extra as { mapsEnabled?: boolean } | undefined)?.mapsEnabled === true;
}
