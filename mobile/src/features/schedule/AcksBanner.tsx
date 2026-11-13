import { View } from 'react-native';
import { Button, Card, Text } from '../../components/ui';
import { fmtUtcDate } from '../../lib/time';
import type { ScheduleAck } from '../../api/types';
import { useAcks, useAckChange, useGuardedRun } from './hooks';
import { ErrorText } from './ui';

const cell = (name: string | null, off: boolean) => (off ? 'Week off' : name || '—');

/** Emergency (lock-window) roster changes the employee still has to acknowledge. Renders nothing when there are none. */
export function AcksBanner() {
  const q = useAcks();
  const ack = useAckChange();
  const { run, error, isBusy, anyBusy } = useGuardedRun();
  const acks: ScheduleAck[] = q.data ?? [];
  if (acks.length === 0) return null;
  return (
    <Card testID="acks-banner" accessibilityRole="alert" style={{ gap: 8 }}>
      <Text weight="700">Your schedule changed</Text>
      {acks.map((a) => (
        <View key={a.id} testID={`ack-${a.id}`} style={{ gap: 6 }}>
          <Text size={14}>
            <Text size={14} weight="700">{fmtUtcDate(a.work_date)}</Text>
            {` ${cell(a.old_shift_name, a.old_is_week_off)} → `}
            <Text size={14} weight="700">{cell(a.new_shift_name, a.new_is_week_off)}</Text>
            {a.reason ? ` · ${a.reason}` : ''}
          </Text>
          <Button testID={`ack-btn-${a.id}`} title="Acknowledge" loading={isBusy(`k${a.id}`)} disabled={anyBusy} onPress={() => void run(`k${a.id}`, () => ack.mutateAsync(a.id))} />
        </View>
      ))}
      {error ? <ErrorText testID="ack-error">{error}</ErrorText> : null}
    </Card>
  );
}
