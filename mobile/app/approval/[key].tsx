import { Stack } from 'expo-router';
import { ApprovalDetail } from '../../src/features/approvals/ApprovalDetail';

export default function ApprovalDetailRoute() {
  return (
    <>
      <Stack.Screen options={{ headerShown: true, title: 'Approval' }} />
      <ApprovalDetail />
    </>
  );
}
