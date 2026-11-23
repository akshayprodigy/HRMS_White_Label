import { useEffect, useRef, useState } from 'react';
import { View } from 'react-native';
import { normalizeError } from '../../api/client';
import { Button, Card, Chip, Text, TextInput } from '../../components/ui';
import { useOrgTime } from '../../lib/org-time';
import { useTheme } from '../../theme';
import type { DayPortion, WorkLocationKind } from './api';
import { useCreateRequest } from './hooks';
import { KIND_LABEL, needsPlace } from './logic';
import { buildRequestPayload, isIsoDate, validateRequest, type RequestFormErrors, type RequestFormValues } from './validation';

const PORTIONS: [DayPortion, string][] = [['full', 'Full day'], ['first_half', 'First half'], ['second_half', 'Second half']];

export function RequestForm({ onDone, onCancel }: { onDone: (message: string) => void; onCancel: () => void }) {
  const { colors } = useTheme();
  const { today, ready } = useOrgTime();
  const create = useCreateRequest();
  const [v, setV] = useState<RequestFormValues>({ kind: 'wfh', start: ready ? today : '', end: ready ? today : '', portion: 'full', place: '', purpose: '' });
  const [errors, setErrors] = useState<RequestFormErrors>({});
  const [serverError, setServerError] = useState<string | null>(null);
  const inFlight = useRef(false);
  const edited = useRef(false); // the user has typed a date: never overwrite it
  const set = (p: Partial<RequestFormValues>) => setV((cur) => ({ ...cur, ...p }));
  // Org time arrives after mount on a cold start: pre-fill then, not with the UTC fallback.
  useEffect(() => {
    if (ready && !edited.current) setV((cur) => ({ ...cur, start: today, end: today }));
  }, [ready, today]);
  const onStart = (s: string) => {
    edited.current = true;
    setV((cur) => {
      // Only follow the start with the end when start is a complete, valid date (not while it is half typed).
      const end = isIsoDate(s) && (cur.end === cur.start || (isIsoDate(cur.end) && cur.end < s)) ? s : cur.end;
      return { ...cur, start: s, end, portion: s === end ? cur.portion : 'full' };
    });
  };
  const onEnd = (s: string) => {
    edited.current = true;
    setV((cur) => ({ ...cur, end: s, portion: s === cur.start ? cur.portion : 'full' }));
  };
  const single = !!v.start && v.start === v.end;

  const submit = async () => {
    if (inFlight.current) return;
    setServerError(null);
    const e = validateRequest(v);
    setErrors(e);
    if (Object.keys(e).length) return;
    inFlight.current = true;
    try {
      await create.mutateAsync(buildRequestPayload(v));
      onDone('Request sent for approval. It is not granted until someone approves it.');
    } catch (err) {
      setServerError(normalizeError(err).message); // e.g. 409 "You have approved leave on these dates"
    } finally {
      inFlight.current = false;
    }
  };

  return (
    <Card testID="wl-form" style={{ gap: 8 }}>
      <Text weight="600">Work location request</Text>
      <Text muted size={13}>Approved by your manager or HR. Until then it stays pending and nothing changes.</Text>
      <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
        {(Object.keys(KIND_LABEL) as WorkLocationKind[]).map((k) => (
          <Chip key={k} testID={`kind-${k}`} label={KIND_LABEL[k]} selected={v.kind === k} onPress={() => set({ kind: k })} />
        ))}
      </View>
      <TextInput testID="wl-start" label="From (YYYY-MM-DD)" value={v.start} error={errors.start} autoCapitalize="none" autoCorrect={false}
        onChangeText={onStart} />
      <TextInput testID="wl-end" label="To (YYYY-MM-DD)" value={v.end} error={errors.end} autoCapitalize="none" autoCorrect={false} onChangeText={onEnd} />
      {single ? (
        <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
          {PORTIONS.map(([p, label]) => <Chip key={p} testID={`portion-${p}`} label={label} selected={v.portion === p} onPress={() => set({ portion: p })} />)}
        </View>
      ) : <Text muted size={13}>Half days are for a single date.</Text>}
      {errors.portion ? <Text size={13} accessibilityRole="alert" style={{ color: colors.danger }}>{errors.portion}</Text> : null}
      <TextInput testID="wl-place" label={`Place${needsPlace(v.kind) ? ' (required)' : ' (optional)'}`} value={v.place} error={errors.place} maxLength={200} onChangeText={(s) => set({ place: s })} />
      <TextInput testID="wl-purpose" label="Purpose" value={v.purpose} error={errors.purpose} maxLength={1000} multiline onChangeText={(s) => set({ purpose: s })} />
      {serverError ? <Text testID="wl-server-error" accessibilityRole="alert" size={13} style={{ color: colors.danger }}>{serverError}</Text> : null}
      <Button testID="wl-submit" title="Send for approval" loading={create.isPending} disabled={!ready} onPress={() => void submit()} />
      <Button testID="wl-close" variant="secondary" title="Close" onPress={onCancel} />
    </Card>
  );
}
