import { useLocalSearchParams } from 'expo-router';
import { GatedScreen } from '../../src/features/attendance/GateNotice';
import { ScheduleScreen } from '../../src/features/schedule/ScheduleScreen';

export default function ScheduleTab() {
  // `?section=open` comes from a push deep link; keyed so a different link re-selects the sub-view.
  const { section } = useLocalSearchParams<{ section?: string }>();
  return (
    <GatedScreen>
      <ScheduleScreen key={section ?? ''} initialSection={section} />
    </GatedScreen>
  );
}
