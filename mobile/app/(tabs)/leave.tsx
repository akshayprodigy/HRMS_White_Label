import { Placeholder } from '../../src/components/Placeholder';
import { GatedScreen } from '../../src/features/attendance/GateNotice';

export default function LeaveTab() {
  return (
    <GatedScreen>
      <Placeholder title="Leave" />
    </GatedScreen>
  );
}
