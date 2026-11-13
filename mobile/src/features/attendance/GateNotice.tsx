import { useRouter } from 'expo-router';
import { Button, Card, Screen, Text } from '../../components/ui';
import { useAttendanceGate } from './gate';

export function GateInline({ testID = 'gate-notice' }: { testID?: string }) {
  const router = useRouter();
  return (
    <Card style={{ gap: 8 }} >
      <Text weight="600" testID={testID}>Punch in to see this</Text>
      <Text muted size={14}>Your attendance for today is needed before this information is available.</Text>
      <Button testID={`${testID}-punch`} variant="secondary" title="Go to Punch" onPress={() => router.navigate('/punch')} />
    </Card>
  );
}

/** Full-screen gate for tabs whose data is gated (navigation itself is never blocked). */
export function GatedScreen({ children, forceGate }: { children: React.ReactNode; forceGate?: boolean }) {
  const { gated } = useAttendanceGate();
  if (gated || forceGate) {
    return (
      <Screen>
        <GateInline />
      </Screen>
    );
  }
  return <>{children}</>;
}
