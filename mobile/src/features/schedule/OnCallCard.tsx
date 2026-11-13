import { Card, Text } from '../../components/ui';
import { fmtUtcDate } from '../../lib/time';
import { useOnCall } from './hooks';

/** Upcoming on-call (standby) days for the next 30 days. Hidden when there are none. */
export function OnCallCard() {
  const q = useOnCall();
  const days = q.data ?? [];
  if (days.length === 0) return null;
  return (
    <Card testID="on-call-card" style={{ gap: 4 }}>
      <Text weight="700">On-call · next 30 days</Text>
      {days.map((d) => (
        <Text key={d.id} testID={`on-call-${d.id}`} size={14}>
          {`${fmtUtcDate(d.work_date)}  ${d.start_time}–${d.end_time} UTC${d.is_overnight ? ' (+1 day)' : ''}${d.note ? ` · ${d.note}` : ''}`}
        </Text>
      ))}
    </Card>
  );
}
