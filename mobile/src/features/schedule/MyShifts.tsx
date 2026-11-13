import { useMemo, useState } from 'react';
import { Pressable, View } from 'react-native';
import { normalizeError } from '../../api/client';
import type { RosterDay } from '../../api/types';
import { Button, Card, Chip, Text } from '../../components/ui';
import { fmtUtcDate } from '../../lib/time';
import { useTheme } from '../../theme';
import { GateInline } from '../attendance/GateNotice';
import { isGateError, useAttendanceGate } from '../attendance/gate';
import { RunningLateCard } from '../punch/RunningLateCard';
import { AcksBanner } from './AcksBanner';
import { CalendarFeedCard } from './CalendarFeedCard';
import { addDays, canActOnDay, dayLabel, isWeekOffDay, monthName, monthWeekStarts, shiftMonth, weekStartOf } from './dates';
import { GiveawayDialog } from './GiveawayDialog';
import { useMonthWeeks, useUtcToday, useWeek } from './hooks';
import { OnCallCard } from './OnCallCard';
import { SwapDialog } from './SwapDialog';
import { ErrorText } from './ui';

const WD = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const dayNum = (iso: string) => String(Number(iso.slice(8, 10)));

function DayDetail({ d, today, onSwap, onGive }: { d: RosterDay; today: string; onSwap: () => void; onGive: () => void }) {
  const l = dayLabel(d);
  const act = canActOnDay(d, today);
  return (
    <Card testID={`day-detail-${d.date}`} style={{ gap: 6 }}>
      <Text weight="700">{fmtUtcDate(d.date)}</Text>
      <Text testID={`day-title-${d.date}`} weight="600">{l.title}</Text>
      {l.times ? <Text testID={`day-times-${d.date}`} muted size={14}>{l.times}</Text> : null}
      {l.transport ? <Text testID={`day-transport-${d.date}`} size={13} weight="600">Cab/transport arranged</Text> : null}
      {d.holiday_name ? <Text muted size={13}>{d.holiday_name}</Text> : null}
      {act ? (
        <View style={{ gap: 8 }}>
          <Button testID={`swap-${d.date}`} variant="secondary" title="Swap shift" onPress={onSwap} />
          <Button testID={`give-${d.date}`} variant="secondary" title="Give away" onPress={onGive} />
        </View>
      ) : null}
    </Card>
  );
}

function WeekView({ focus, onAction }: { focus?: string; onAction: (kind: 'swap' | 'give', d: RosterDay) => void }) {
  const { colors, radius } = useTheme();
  const today = useUtcToday();
  const [start, setStart] = useState(weekStartOf(focus ?? today));
  const [sel, setSel] = useState<string | null>(focus ?? null);
  const q = useWeek(start);
  const days = q.data?.days ?? [];
  const selected = days.find((d) => d.date === sel) ?? days.find((d) => d.is_today) ?? days[0];
  const isThisWeek = start === weekStartOf(today);

  if (q.error && isGateError(q.error)) return <GateInline />;
  return (
    <View style={{ gap: 10 }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
        <Button testID="week-prev" accessibilityLabel="Previous week" variant="secondary" title="‹" onPress={() => { setStart(addDays(start, -7)); setSel(null); }} />
        <Text testID="week-label" weight="600">{`${fmtUtcDate(start)} – ${fmtUtcDate(addDays(start, 6))}`}</Text>
        <Button testID="week-next" accessibilityLabel="Next week" variant="secondary" title="›" onPress={() => { setStart(addDays(start, 7)); setSel(null); }} />
      </View>
      {!isThisWeek ? <Button testID="week-today" variant="secondary" title="This week" onPress={() => { setStart(weekStartOf(today)); setSel(null); }} /> : null}
      {q.isPending ? <Text muted testID="week-loading">Loading…</Text> : null}
      {q.error ? (
        <Card style={{ gap: 8 }}>
          <ErrorText testID="week-error">{normalizeError(q.error).message}</ErrorText>
          <Button variant="secondary" title="Try again" onPress={() => void q.refetch()} />
        </Card>
      ) : null}
      {days.length ? (
        <View style={{ flexDirection: 'row', gap: 4 }}>
          {days.map((d) => {
            const l = dayLabel(d);
            const on = selected?.date === d.date;
            return (
              <Pressable
                key={d.date}
                testID={`strip-${d.date}`}
                accessibilityRole="button"
                accessibilityState={{ selected: on }}
                accessibilityLabel={`${fmtUtcDate(d.date)}, ${l.title}${l.times ? `, ${l.times}` : ''}`}
                onPress={() => setSel(d.date)}
                style={{ flex: 1, alignItems: 'center', paddingVertical: 8, paddingHorizontal: 2, borderRadius: radius, borderWidth: 1, borderColor: on ? colors.primary : colors.border, backgroundColor: d.is_today ? colors.surface : 'transparent' }}
              >
                <Text size={11} muted>{WD[(new Date(`${d.date}T00:00:00Z`).getUTCDay() + 6) % 7]}</Text>
                <Text size={16} weight="700">{dayNum(d.date)}</Text>
                <Text size={10} muted={l.muted} numberOfLines={2} style={{ textAlign: 'center' }}>{isWeekOffDay(d) ? 'Off' : d.on_leave ? 'Leave' : d.shift.name}</Text>
                {l.transport ? <Text size={10} weight="700">Cab</Text> : null}
              </Pressable>
            );
          })}
        </View>
      ) : null}
      {selected ? <DayDetail d={selected} today={today} onSwap={() => onAction('swap', selected)} onGive={() => onAction('give', selected)} /> : null}
    </View>
  );
}

function MonthView({ onPick }: { onPick: (date: string) => void }) {
  const today = useUtcToday();
  const [ym, setYm] = useState(today.slice(0, 7));
  const starts = useMemo(() => monthWeekStarts(ym), [ym]);
  const results = useMonthWeeks(starts, true);
  const gate = results.find((r) => r.error && isGateError(r.error));
  if (gate) return <GateInline />;
  const days = results.flatMap((r) => r.data?.days ?? []).filter((d) => d.date.startsWith(ym)).sort((a, b) => a.date.localeCompare(b.date));
  const failed = results.map((r, i) => (r.error ? starts[i] : null)).filter((x): x is string => !!x);
  const loading = results.some((r) => r.isPending);
  return (
    <View style={{ gap: 8 }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
        <Button testID="month-prev" accessibilityLabel="Previous month" variant="secondary" title="‹" onPress={() => setYm(shiftMonth(ym, -1))} />
        <Text testID="month-label" weight="600">{monthName(ym)}</Text>
        <Button testID="month-next" accessibilityLabel="Next month" variant="secondary" title="›" onPress={() => setYm(shiftMonth(ym, 1))} />
      </View>
      {loading ? <Text muted testID="month-loading">Loading…</Text> : null}
      {failed.map((w) => <ErrorText key={w} testID={`month-error-${w}`}>{`Could not load the week of ${fmtUtcDate(w)}.`}</ErrorText>)}
      {failed.length ? <Button testID="month-retry" variant="secondary" title="Try again" onPress={() => results.forEach((r) => { if (r.error) void r.refetch(); })} /> : null}
      {days.map((d) => {
        const l = dayLabel(d);
        return (
          <Pressable key={d.date} testID={`month-${d.date}`} accessibilityRole="button" onPress={() => onPick(d.date)}>
            <Card style={{ flexDirection: 'row', justifyContent: 'space-between', gap: 8 }}>
              <View style={{ flexShrink: 1 }}>
                <Text weight="600">{`${fmtUtcDate(d.date)} · ${l.title}`}</Text>
                {l.times ? <Text muted size={13}>{l.times}</Text> : null}
                {d.holiday_name ? <Text muted size={12}>{d.holiday_name}</Text> : null}
              </View>
              {l.transport ? <Text size={12} weight="700">Cab</Text> : null}
            </Card>
          </Pressable>
        );
      })}
    </View>
  );
}

export type SwapDone = (what: 'swap' | 'give') => void;

export function MyShifts({ onDone, feedUrl, onFeedUrl }: { onDone: SwapDone; feedUrl: string | null; onFeedUrl: (u: string | null) => void }) {
  const { today: att } = useAttendanceGate();
  const [mode, setMode] = useState<'week' | 'month'>('week');
  const [dialog, setDialog] = useState<{ kind: 'swap' | 'give'; day: RosterDay } | null>(null);
  const [focus, setFocus] = useState<string | undefined>(undefined);

  if (dialog) {
    const d = dialog.day;
    return dialog.kind === 'swap' ? (
      <SwapDialog
        day={{ date: d.date, shiftName: d.shift.name, shiftTemplateId: d.shift.shift_template_id ?? null, isWeekOff: isWeekOffDay(d) }}
        onClose={() => setDialog(null)}
        onDone={() => { setDialog(null); onDone('swap'); }}
      />
    ) : (
      <GiveawayDialog date={d.date} shiftName={d.shift.name} onClose={() => setDialog(null)} onDone={() => { setDialog(null); onDone('give'); }} />
    );
  }
  return (
    <View style={{ gap: 12 }}>
      <AcksBanner />
      <RunningLateCard isMarked={att?.is_marked} />
      <View style={{ flexDirection: 'row', gap: 8 }}>
        <Chip testID="mode-week" label="Week" selected={mode === 'week'} onPress={() => { setFocus(undefined); setMode('week'); }} />
        <Chip testID="mode-month" label="Month" selected={mode === 'month'} onPress={() => { setFocus(undefined); setMode('month'); }} />
      </View>
      {mode === 'week' ? (
        <WeekView key={focus ?? 'now'} focus={focus} onAction={(kind, day) => setDialog({ kind, day })} />
      ) : (
        <MonthView onPick={(date) => { setFocus(date); setMode('week'); }} />
      )}
      <OnCallCard />
      <CalendarFeedCard url={feedUrl} onUrl={onFeedUrl} />
    </View>
  );
}
