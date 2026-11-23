import { Stack } from 'expo-router';
import { HolidaysScreen } from '../src/features/holidays/HolidaysScreen';

export default function HolidaysRoute() {
  return (
    <>
      <Stack.Screen options={{ headerShown: true, title: 'Holidays' }} />
      <HolidaysScreen />
    </>
  );
}
