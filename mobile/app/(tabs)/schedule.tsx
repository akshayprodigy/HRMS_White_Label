import { GatedScreen } from '../../src/features/attendance/GateNotice';
import { ScheduleScreen } from '../../src/features/schedule/ScheduleScreen';

export default function ScheduleTab() {
  return (
    <GatedScreen>
      <ScheduleScreen />
    </GatedScreen>
  );
}
