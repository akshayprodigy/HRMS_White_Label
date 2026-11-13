import { useRef, useState } from 'react';
import { normalizeError } from '../../api/client';
import { Button, Card, Text, TextInput } from '../../components/ui';
import { fmtUtcDate } from '../../lib/time';
import { useCreateDrop } from './hooks';
import { ErrorText } from './ui';

/** Ask to be released from a published shift; the approver may post it as an open shift. Reason >= 3 chars (backend rule). */
export function GiveawayDialog({ date, shiftName, onClose, onDone }: { date: string; shiftName?: string; onClose: () => void; onDone: () => void }) {
  const create = useCreateDrop();
  const [reason, setReason] = useState('');
  const [err, setErr] = useState<string | null>(null);
  const submitting = useRef(false);

  const submit = async () => {
    if (submitting.current) return;
    if (reason.trim().length < 3) return setErr('Please give a reason (at least 3 characters).');
    setErr(null);
    submitting.current = true;
    try {
      await create.mutateAsync({ work_date: date, reason });
      onDone();
    } catch (e) {
      setErr(normalizeError(e).message);
    } finally {
      submitting.current = false;
    }
  };
  return (
    <Card testID="giveaway-dialog" style={{ gap: 10 }}>
      <Text weight="700">Give away shift</Text>
      <Text muted size={13}>{`Your ${shiftName || 'shift'} on ${fmtUtcDate(date)}. If approved you are released from it.`}</Text>
      <TextInput label="Reason (required)" testID="giveaway-reason" value={reason} onChangeText={setReason} maxLength={500} multiline />
      {err ? <ErrorText testID="giveaway-error">{err}</ErrorText> : null}
      <Button testID="giveaway-submit" title="Request give-away" loading={create.isPending} onPress={() => void submit()} />
      <Button testID="giveaway-cancel" variant="secondary" title="Cancel" disabled={create.isPending} onPress={onClose} />
    </Card>
  );
}
