import { Placeholder } from '../../src/components/Placeholder';
import { GatedScreen } from '../../src/features/attendance/GateNotice';

export default function ScheduleTab() {
  return (
    <GatedScreen>
      <Placeholder title="Schedule" />
    </GatedScreen>
  );
}
