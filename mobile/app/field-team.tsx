import { Stack } from 'expo-router';
import { FieldTeamScreen } from '../src/features/tracking/FieldTeamScreen';

export default function FieldTeamRoute() {
  return (
    <>
      <Stack.Screen options={{ headerShown: true, title: 'Field team' }} />
      <FieldTeamScreen />
    </>
  );
}
