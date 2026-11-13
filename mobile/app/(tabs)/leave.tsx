import { GatedScreen } from '../../src/features/attendance/GateNotice';
import { LeaveScreen } from '../../src/features/leave/LeaveScreen';

export default function LeaveTab() {
  return (
    <GatedScreen>
      <LeaveScreen />
    </GatedScreen>
  );
}
