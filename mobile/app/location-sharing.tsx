import { Stack } from 'expo-router';
import { ConsentScreen } from '../src/features/tracking/ConsentScreen';

export default function LocationSharingRoute() {
  return (
    <>
      <Stack.Screen options={{ headerShown: true, title: 'Shift location sharing' }} />
      <ConsentScreen />
    </>
  );
}
