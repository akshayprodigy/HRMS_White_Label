import { Stack } from 'expo-router';
import { WorkLocationScreen } from '../src/features/work-location/WorkLocationScreen';

export default function WorkLocationRoute() {
  return (
    <>
      <Stack.Screen options={{ headerShown: true, title: 'Work location' }} />
      <WorkLocationScreen />
    </>
  );
}
