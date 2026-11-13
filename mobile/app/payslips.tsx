import { Stack } from 'expo-router';
import { GatedScreen } from '../src/features/attendance/GateNotice';
import { PayslipsScreen } from '../src/features/payslips/PayslipsScreen';

export default function PayslipsRoute() {
  return (
    <>
      <Stack.Screen options={{ headerShown: true, title: 'Payslips' }} />
      <GatedScreen>
        <PayslipsScreen />
      </GatedScreen>
    </>
  );
}
