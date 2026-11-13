import { Stack } from 'expo-router';
import { GatedScreen } from '../src/features/attendance/GateNotice';
import { DocumentsScreen } from '../src/features/documents/DocumentsScreen';

export default function DocumentsRoute() {
  return (
    <>
      <Stack.Screen options={{ headerShown: true, title: 'Documents' }} />
      <GatedScreen>
        <DocumentsScreen />
      </GatedScreen>
    </>
  );
}
