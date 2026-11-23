import { useState } from 'react';
import { RefreshControl, View } from 'react-native';
import { normalizeError } from '../../api/client';
import { Button, Card, Chip, Screen, Text, TextInput } from '../../components/ui';
import { fmtUtcDate } from '../../lib/time';
import { useOrgTime } from '../../lib/org-time';
import { useTheme } from '../../theme';
import type { MyHoliday } from './api';
import { useCancelPick, useMyHolidays, usePickHoliday } from './hooks';
import { isPast, PICK_LABEL, pickAction } from './logic';

function HolidayRow({ h, today, remaining, ready }: { h: MyHoliday; today: string; remaining: number; ready: boolean }) {
  const { colors } = useTheme();
  const pick = usePickHoliday();
  const cancel = useCancelPick();
  const [mode, setMode] = useState<'pick' | 'cancel' | null>(null);
  const [reason, setReason] = useState('');
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const act = pickAction(h, today, remaining, ready);
  const past = ready && isPast(h, today);

  const doPick = async () => {
    setErr(null);
    try {
      await pick.mutateAsync({ holidayId: h.id, reason });
      setMode(null);
      setReason('');
      setMsg('Request sent for approval. The holiday is not yours until it is approved.');
    } catch (e) {
      setErr(normalizeError(e).message);
    }
  };
  const doCancel = async () => {
    setErr(null);
    try {
      if (h.pick) await cancel.mutateAsync(h.pick.id);
      setMode(null);
      setMsg('Pick cancelled.');
    } catch (e) {
      setErr(normalizeError(e).message);
    }
  };

  return (
    <Card testID={`holiday-${h.id}`} style={{ gap: 6 }}>
      <Text weight="600">{h.name}</Text>
      <Text muted size={13}>{`${fmtUtcDate(h.date)} · ${h.location}${past ? ' · Past' : ''}`}</Text>
      {h.is_optional && h.pick ? <Text testID={`pick-status-${h.id}`} size={13} weight="600">{PICK_LABEL[h.pick.status] ?? h.pick.status}</Text> : null}
      {h.pick?.status === 'rejected' && h.pick.decision_note ? <Text testID={`pick-note-${h.id}`} size={13} style={{ color: colors.danger }}>{`Note: ${h.pick.decision_note}`}</Text> : null}
      {msg ? <Text testID={`pick-msg-${h.id}`} size={13}>{msg}</Text> : null}
      {act.kind && !mode ? (
        <Button
          testID={`${act.kind === 'cancel' ? 'cancel' : 'pick'}-${h.id}`}
          variant={act.kind === 'cancel' ? 'secondary' : 'primary'}
          title={act.kind === 'cancel' ? 'Cancel pick' : act.kind === 'pick_again' ? 'Pick again' : 'Pick'}
          disabled={act.disabled}
          onPress={() => { setMsg(null); setErr(null); setMode(act.kind === 'cancel' ? 'cancel' : 'pick'); }}
        />
      ) : null}
      {mode === 'pick' ? (
        <>
          <Text size={13}>This sends a request to your approver; the day is not taken until it is approved.</Text>
          <TextInput label="Reason (optional)" value={reason} onChangeText={setReason} maxLength={1000} testID={`pick-reason-${h.id}`} />
          <Button testID={`pick-confirm-${h.id}`} title="Request" loading={pick.isPending} onPress={() => void doPick()} />
          <Button testID={`pick-close-${h.id}`} variant="secondary" title="Close" onPress={() => setMode(null)} />
        </>
      ) : null}
      {mode === 'cancel' ? (
        <>
          <Text testID={`cancel-text-${h.id}`}>{`Cancel your ${h.pick?.status === 'approved' ? 'approved' : 'pending'} pick of ${h.name}?`}</Text>
          <Button testID={`cancel-confirm-${h.id}`} title="Cancel pick" loading={cancel.isPending} onPress={() => void doCancel()} />
          <Button testID={`cancel-keep-${h.id}`} variant="secondary" title="Keep it" onPress={() => setMode(null)} />
        </>
      ) : null}
      {err ? <Text testID={`holiday-error-${h.id}`} accessibilityRole="alert" size={13} style={{ color: colors.danger }}>{err}</Text> : null}
    </Card>
  );
}

export function HolidaysScreen() {
  const { colors } = useTheme();
  const { today, ready } = useOrgTime();
  const [yearSel, setYearSel] = useState<number | null>(null);
  const q = useMyHolidays(yearSel);
  const data = q.data;
  const year = yearSel ?? data?.year ?? Number(today.slice(0, 4));
  const years = [year - 1, year, year + 1];
  const mandatory = data?.holidays.filter((h) => !h.is_optional) ?? [];
  const optional = data?.holidays.filter((h) => h.is_optional) ?? [];

  return (
    <Screen scroll refreshControl={<RefreshControl refreshing={q.isRefetching} onRefresh={() => void q.refetch()} />} style={{ gap: 12 }}>
      <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
        {years.map((y) => <Chip key={y} testID={`year-${y}`} label={String(y)} selected={y === year} onPress={() => setYearSel(y)} />)}
      </View>
      {data ? (
        <Card style={{ gap: 4 }}>
          <Text testID="quota-chip" weight="600">{`${data.used} of ${data.quota} optional used`}</Text>
          <Text muted size={13}>Pending picks count toward your quota until a decision.</Text>
        </Card>
      ) : null}
      {q.error && !data ? (
        <Card style={{ gap: 8 }}>
          <Text testID="holidays-error" accessibilityRole="alert" style={{ color: colors.danger }}>{normalizeError(q.error).message}</Text>
          <Button variant="secondary" title="Try again" onPress={() => void q.refetch()} />
        </Card>
      ) : null}
      {data ? (
        <>
          <Text weight="700">{`Company holidays (${mandatory.length})`}</Text>
          {mandatory.length === 0 ? <Text muted>No company holidays this year.</Text> : mandatory.map((h) => <HolidayRow key={h.id} h={h} today={today} remaining={data.remaining} ready={ready} />)}
          <Text weight="700">{`Optional holidays (${optional.length})`}</Text>
          {optional.length === 0 ? <Text muted>No optional holidays this year.</Text> : optional.map((h) => <HolidayRow key={h.id} h={h} today={today} remaining={data.remaining} ready={ready} />)}
        </>
      ) : q.isLoading ? <Text muted>Loading holidays…</Text> : null}
    </Screen>
  );
}
