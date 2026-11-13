import { useRef, useState } from 'react';
import { View } from 'react-native';
import { normalizeError } from '../../api/client';
import type { MyBroadcast } from '../../api/types';
import { Button, Text, TextInput } from '../../components/ui';
import { useTheme } from '../../theme';
import { requiredResponse } from './api';
import { useBroadcastRespond } from './hooks';

/** The response controls a broadcast is waiting for: safe / need help (+ optional note), acknowledge, or just "Got it". */
export function BroadcastResponse({ broadcast }: { broadcast: MyBroadcast }) {
  const { colors } = useTheme();
  const respond = useBroadcastRespond();
  const [note, setNote] = useState('');
  const [error, setError] = useState<string | null>(null);
  const inflight = useRef(false); // double-tap guard: state updates are async, a ref is not
  const kind = requiredResponse(broadcast);

  const send = async (input: Parameters<typeof respond.mutateAsync>[0]) => {
    if (inflight.current) return;
    inflight.current = true;
    setError(null);
    try {
      await respond.mutateAsync(input);
    } catch (e) {
      setError(normalizeError(e).message);
    } finally {
      inflight.current = false;
    }
  };
  const id = broadcast.id;
  const busy = respond.isPending;

  return (
    <View style={{ gap: 10 }}>
      {kind === 'safety' ? (
        <>
          <TextInput label="Note (optional)" value={note} onChangeText={setNote} maxLength={500} multiline testID={`bc-note-${id}`} />
          <Button testID={`bc-safe-${id}`} title="I'm safe" disabled={busy} loading={busy && respond.variables?.kind === 'safety' && respond.variables.status === 'safe'} onPress={() => void send({ id, kind: 'safety', status: 'safe', note })} />
          <Button testID={`bc-help-${id}`} variant="secondary" title="I need help" disabled={busy} loading={busy && respond.variables?.kind === 'safety' && respond.variables.status === 'need_help'} onPress={() => void send({ id, kind: 'safety', status: 'need_help', note })} />
        </>
      ) : kind === 'ack' ? (
        <Button testID={`bc-ack-${id}`} title="Acknowledge" loading={busy} onPress={() => void send({ id, kind: 'ack' })} />
      ) : (
        <Button testID={`bc-read-${id}`} title="Got it" loading={busy} onPress={() => void send({ id, kind: 'read' })} />
      )}
      {error ? <Text testID={`bc-error-${id}`} size={14} style={{ color: colors.danger }} accessibilityLiveRegion="polite">{error}</Text> : null}
    </View>
  );
}
