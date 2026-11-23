import { useRef, useState } from 'react';
import { View } from 'react-native';
import { normalizeError } from '../../api/client';
import { Button, Card, Chip, Text, TextInput } from '../../components/ui';
import { GateInline } from '../attendance/GateNotice';
import { isGateError } from '../attendance/gate';
import { WEEKDAYS } from './api';
import { EMPTY_AVAILABILITY, ruleText, toAvailabilityInput, validateAvailability, type AvailabilityForm } from './availability';
import { useAddAvailability, useOrgToday, useAvailability, useDeleteAvailability, useGuardedRun, useShiftOptions } from './hooks';
import { ConfirmAction, ErrorText } from './ui';

function AddRule({ onDone, onCancel }: { onDone: () => void; onCancel: () => void }) {
  const shifts = useShiftOptions();
  const add = useAddAvailability();
  const today = useOrgToday();
  const [f, setF] = useState<AvailabilityForm>(EMPTY_AVAILABILITY);
  const [err, setErr] = useState<string | null>(null);
  const submitting = useRef(false);
  const set = (p: Partial<AvailabilityForm>) => setF((v) => ({ ...v, ...p }));

  const submit = async () => {
    if (submitting.current) return;
    const bad = validateAvailability(f, today);
    setErr(bad);
    if (bad) return;
    submitting.current = true;
    try {
      await add.mutateAsync(toAvailabilityInput(f));
      onDone();
    } catch (e) {
      const n = normalizeError(e);
      setErr(n.status === 409 ? 'You already have this rule.' : n.message);
    } finally {
      submitting.current = false;
    }
  };
  const row = { flexDirection: 'row', flexWrap: 'wrap', gap: 8 } as const;
  return (
    <Card testID="avail-form" style={{ gap: 10 }}>
      <Text weight="700">Add availability rule</Text>
      <View style={row}>
        <Chip testID="avail-kind-unavailable" label="Unavailable" selected={f.kind === 'unavailable'} onPress={() => set({ kind: 'unavailable' })} />
        <Chip testID="avail-kind-preferred" label="Preferred" selected={f.kind === 'preferred'} onPress={() => set({ kind: 'preferred' })} />
      </View>
      <View style={row}>
        <Chip testID="avail-mode-weekday" label="Every week" selected={f.mode === 'weekday'} onPress={() => set({ mode: 'weekday' })} />
        <Chip testID="avail-mode-date" label="One date" selected={f.mode === 'date'} onPress={() => set({ mode: 'date' })} />
      </View>
      {f.mode === 'weekday' ? (
        <>
          <View style={row}>
            {WEEKDAYS.map((w, i) => <Chip key={w} testID={`avail-day-${i}`} label={w.slice(0, 3)} selected={f.weekday === i} onPress={() => set({ weekday: i })} />)}
          </View>
          <TextInput label="From (optional, YYYY-MM-DD)" testID="avail-from" value={f.validFrom} onChangeText={(s) => set({ validFrom: s })} autoCapitalize="none" autoCorrect={false} keyboardType="numbers-and-punctuation" />
          <TextInput label="Until (optional, YYYY-MM-DD)" testID="avail-to" value={f.validTo} onChangeText={(s) => set({ validTo: s })} autoCapitalize="none" autoCorrect={false} keyboardType="numbers-and-punctuation" />
        </>
      ) : (
        <TextInput label="Date (YYYY-MM-DD)" testID="avail-date" value={f.specificDate} onChangeText={(s) => set({ specificDate: s })} autoCapitalize="none" autoCorrect={false} keyboardType="numbers-and-punctuation" />
      )}
      <Text size={14} weight="600">{f.kind === 'preferred' ? 'Shift (required)' : 'Shift (optional, blank = any shift)'}</Text>
      <View style={row}>
        {f.kind === 'unavailable' ? <Chip testID="avail-shift-any" label="Any" selected={f.shiftId == null} onPress={() => set({ shiftId: null })} /> : null}
        {(shifts.data ?? []).map((s) => <Chip key={s.id} testID={`avail-shift-${s.id}`} label={s.name} selected={f.shiftId === s.id} onPress={() => set({ shiftId: s.id })} />)}
      </View>
      <TextInput label="Note (optional)" testID="avail-note" value={f.note} onChangeText={(s) => set({ note: s })} maxLength={255} />
      {err ? <ErrorText testID="avail-error">{err}</ErrorText> : null}
      <Button testID="avail-submit" title="Add rule" loading={add.isPending} onPress={() => void submit()} />
      <Button testID="avail-cancel" variant="secondary" title="Cancel" disabled={add.isPending} onPress={onCancel} />
    </Card>
  );
}

/** Tell the scheduler when I cannot work, or which shifts I prefer (advisory input to rostering). */
export function AvailabilityPanel() {
  const rules = useAvailability();
  const shifts = useShiftOptions();
  const del = useDeleteAvailability();
  const { run, error, isBusy } = useGuardedRun();
  const [adding, setAdding] = useState(false);

  if (rules.error && isGateError(rules.error)) return <GateInline />;
  return (
    <View style={{ gap: 10 }}>
      <Text muted size={13}>Tell your scheduler when you cannot work or which shifts you prefer. Dates and times are in organisation time.</Text>
      {error ? <ErrorText testID="avail-del-error">{error}</ErrorText> : null}
      {rules.error ? <ErrorText testID="avail-load-error">{normalizeError(rules.error).message}</ErrorText> : null}
      {adding ? <AddRule onDone={() => setAdding(false)} onCancel={() => setAdding(false)} /> : <Button testID="avail-add" title="Add rule" onPress={() => setAdding(true)} />}
      {rules.isPending ? <Text muted>Loading…</Text> : null}
      {rules.data && rules.data.length === 0 ? <Text muted testID="avail-empty">No availability rules yet.</Text> : null}
      {(rules.data ?? []).map((r) => (
        <Card key={r.id} testID={`rule-${r.id}`} style={{ gap: 6 }}>
          <Text>{ruleText(r, shifts.data ?? [])}</Text>
          {r.note ? <Text muted size={13}>{r.note}</Text> : null}
          <ConfirmAction id={`rule-del-${r.id}`} label="Delete" prompt="Delete this rule?" busy={isBusy(`r${r.id}`)} onConfirm={() => void run(`r${r.id}`, () => del.mutateAsync(r.id))} />
        </Card>
      ))}
    </View>
  );
}
