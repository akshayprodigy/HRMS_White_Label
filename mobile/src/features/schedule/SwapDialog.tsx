import { useRef, useState } from 'react';
import { Pressable, Switch, View } from 'react-native';
import { normalizeError } from '../../api/client';
import { Button, Card, Text, TextInput } from '../../components/ui';
import { useTheme } from '../../theme';
import { fmtUtcDate } from '../../lib/time';
import { GateInline } from '../attendance/GateNotice';
import { isGateError } from '../attendance/gate';
import { cellText } from './api';
import { isIsoDate, sameShift, validateSwap, validateReturnDate, type MyCell } from './dates';
import { useCreateSwap, useOrgToday, useSwapCandidates } from './hooks';
import { ErrorText } from './ui';

export type SwapDay = MyCell & { date: string };

/** Propose a swap of my published shift with a same-department colleague (they accept, then the approver confirms). */
export function SwapDialog({ day, today: todayProp, onClose, onDone }: { day: SwapDay; today?: string; onClose: () => void; onDone: () => void }) {
  const orgNow = useOrgToday();
  const today = todayProp ?? orgNow;
  const { colors, radius } = useTheme();
  const cands = useSwapCandidates(day.date);
  const create = useCreateSwap();
  const [pick, setPick] = useState<number | null>(null);
  const [otherDay, setOtherDay] = useState(false);
  const [returnDate, setReturnDate] = useState('');
  const [reason, setReason] = useState('');
  const [err, setErr] = useState<string | null>(null);
  const submitting = useRef(false);

  const rd = otherDay && isIsoDate(returnDate.trim()) && !validateReturnDate(day.date, returnDate.trim(), today) ? returnDate.trim() : null;
  const retCands = useSwapCandidates(rd);
  const list = cands.data ?? [];
  const chosen = list.find((c) => c.user_id === pick);
  const retCell = rd && chosen ? retCands.data?.find((c) => c.user_id === chosen.user_id) : undefined;

  const submit = async () => {
    if (submitting.current) return;
    const bad = validateSwap({ date: day.date, today, pick, cands: list, mine: day, otherDay, returnDate });
    setErr(bad);
    if (bad || pick == null) return;
    submitting.current = true;
    try {
      await create.mutateAsync({ counterparty_id: pick, requester_date: day.date, counterparty_date: otherDay ? rd : null, reason: reason.trim() || null });
      onDone();
    } catch (e) {
      setErr(normalizeError(e).message);
    } finally {
      submitting.current = false;
    }
  };

  if (cands.error && isGateError(cands.error)) return <GateInline />;
  return (
    <Card testID="swap-dialog" style={{ gap: 10 }}>
      <Text weight="700">Swap shift</Text>
      <Text muted size={13}>{`Your ${day.isWeekOff ? 'week off' : day.shiftName || 'shift'} on ${fmtUtcDate(day.date)}. A colleague must accept, then your approver confirms.`}</Text>

      <Text size={14} weight="600">Swap with (your department)</Text>
      {cands.isPending ? <Text muted testID="cands-loading">Loading colleagues…</Text> : null}
      {cands.error ? <ErrorText testID="cands-error">{normalizeError(cands.error).message}</ErrorText> : null}
      {cands.data && list.length === 0 ? <Text muted testID="cands-empty">No colleagues found in your department.</Text> : null}
      {list.map((c) => {
        const same = sameShift(c, day);
        const selected = pick === c.user_id;
        const what = same ? `${cellText(c)} · same shift, nothing to swap` : !c.is_week_off && !c.shift_name ? 'Off / no shift, they take your shift' : cellText(c);
        return (
          <Pressable
            key={c.user_id}
            testID={`cand-${c.user_id}`}
            accessibilityRole="button"
            accessibilityState={{ selected, disabled: same }}
            accessibilityLabel={`${c.name ?? 'Colleague'}, ${what}`}
            disabled={same}
            onPress={() => setPick(c.user_id)}
            style={{ padding: 12, borderRadius: radius, borderWidth: 1, borderColor: selected ? colors.primary : colors.border, opacity: same ? 0.5 : 1 }}
          >
            <Text weight="600">{c.name ?? 'Colleague'}</Text>
            <Text muted size={13}>{what}</Text>
          </Pressable>
        );
      })}

      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
        <Text style={{ flex: 1 }} weight="600" size={14}>Take their shift on a different day in return</Text>
        <Switch testID="swap-other-day" accessibilityLabel="Take their shift on a different day in return" value={otherDay} onValueChange={setOtherDay} />
      </View>
      {otherDay ? (
        <View>
          <TextInput label="Return date (YYYY-MM-DD)" testID="swap-return-date" value={returnDate} onChangeText={setReturnDate} placeholder={today} autoCapitalize="none" autoCorrect={false} keyboardType="numbers-and-punctuation" />
          {rd && chosen ? <Text testID="swap-return-hint" muted size={13}>{`${chosen.name ?? 'They'} works ${retCell ? cellText(retCell) : '…'} on ${fmtUtcDate(rd)}.`}</Text> : null}
        </View>
      ) : null}
      <TextInput label="Reason (optional)" testID="swap-reason" value={reason} onChangeText={setReason} maxLength={500} multiline />

      {err ? <ErrorText testID="swap-error">{err}</ErrorText> : null}
      <Button testID="swap-submit" title="Request swap" loading={create.isPending} onPress={() => void submit()} />
      <Button testID="swap-cancel" variant="secondary" title="Cancel" disabled={create.isPending} onPress={onClose} />
    </Card>
  );
}
