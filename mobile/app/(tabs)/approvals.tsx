import { GatedScreen } from '../../src/features/attendance/GateNotice';
import { ApprovalsScreen } from '../../src/features/approvals/ApprovalsScreen';

export default function ApprovalsTab() {
  return (
    <GatedScreen>
      <ApprovalsScreen />
    </GatedScreen>
  );
}
