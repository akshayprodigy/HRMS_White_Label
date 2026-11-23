import { useMutation, useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { View } from 'react-native';
import { normalizeError } from '../../api/errors';
import { Button, Card, Text, TextInput } from '../../components/ui';
import { clearRunningLate, canShowRunningLate, fetchRunningLate, postRunningLate, RUNNING_LATE_KEY, validateRunningLate } from './runningLate';
import { useInvalidateAfterPunch } from './hooks';

const CHOICES = [15, 30, 60];

export function RunningLateCard({ isMarked }: { isMarked: boolean | undefined }) {
  const q = useQuery({ queryKey: RUNNING_LATE_KEY, queryFn: fetchRunningLate, enabled: isMarked === false });
  const invalidate = useInvalidateAfterPunch();
  const [minutes, setMinutes] = useState(15);
  const [reason, setReason] = useState('');
  const [err, setErr] = useState<string | null>(null);
  const post = useMutation({
    mutationFn: (v: { m: number; r: string }) => postRunningLate(v.m, v.r),
    onSuccess: () => { setErr(null); void invalidate(); },
    onError: (e) => setErr(normalizeError(e).message),
  });
  const clear = useMutation({ mutationFn: clearRunningLate, onSuccess: () => void invalidate(), onError: (e) => setErr(normalizeError(e).message) });

  const notice = q.data?.notice;
  if (!notice && !canShowRunningLate(q.data, isMarked)) return null;
  if (notice) {
    return (
      <Card testID="running-late-notice" style={{ gap: 6 }}>
        <Text weight="600">{`Running late, expected by ${notice.eta_hhmm}`}</Text>
        {notice.reason ? <Text muted size={14}>{notice.reason}</Text> : null}
        {err ? <Text size={13}>{err}</Text> : null}
        <Button testID="running-late-clear" variant="secondary" title="Cancel notice" loading={clear.isPending} onPress={() => clear.mutate()} />
      </Card>
    );
  }
  const submit = () => {
    const v = validateRunningLate(minutes, reason);
    setErr(v);
    if (!v) post.mutate({ m: minutes, r: reason });
  };
  return (
    <Card testID="running-late-form" style={{ gap: 8 }}>
      <Text weight="600">Running late?</Text>
      <Text muted size={14}>Let your scheduler know. Your shift has started and you have not punched in.</Text>
      <View style={{ flexDirection: 'row', gap: 8 }}>
        {CHOICES.map((m) => (
          <View key={m} style={{ flex: 1 }}>
            <Button testID={`late-${m}`} variant={minutes === m ? 'primary' : 'secondary'} title={`${m} min`} onPress={() => setMinutes(m)} />
          </View>
        ))}
      </View>
      <TextInput label="Reason (optional)" value={reason} onChangeText={setReason} maxLength={255} />
      {err ? <Text testID="running-late-error" size={13}>{err}</Text> : null}
      <Button testID="running-late-submit" title="I'm running late" loading={post.isPending} onPress={submit} />
    </Card>
  );
}
