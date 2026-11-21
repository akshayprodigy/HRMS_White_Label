import { useQuery } from '@tanstack/react-query';
import { useMemo, useState } from 'react';
import { Pressable, RefreshControl, View } from 'react-native';
import { ApiError, normalizeError } from '../../api/client';
import { Button, Card, Chip, Screen, Text } from '../../components/ui';
import { fmtUtcTime } from '../../lib/time';
import { useTheme } from '../../theme';
import { fetchFieldNow, fetchTrail, FIELD_NOW_KEY, type FieldRow } from './api';
import { FieldMap } from './FieldMap';
import { lastSeen, statusMeta, utcDay } from './fieldFormat';
import { mapsAvailable } from './maps';

const REFRESH_MS = 60_000;
const isScopeError = (e: unknown) => e instanceof ApiError && e.status === 403;
const shiftText = (r: FieldRow) => (r.shift_name ? `${r.shift_name} ${r.start_hhmm ?? ''}-${r.end_hhmm ?? ''}` : 'No shift today');

/** Whether the signed-in user may see the field team: the backend answers 403 when they have no roster scope. */
export function useFieldTeamAccess() {
  const q = useQuery({
    queryKey: [...FIELD_NOW_KEY, 'access'],
    // A 403 is an answer, not an error: stored as {allowed:false} and never re-asked this session (queryClient.clear on
    // logout resets it). field-now has no limit parameter, so a granted probe still reads the board; cached for 5 minutes.
    queryFn: async () => {
      try {
        await fetchFieldNow();
        return { allowed: true };
      } catch (e) {
        if (isScopeError(e)) return { allowed: false };
        throw e;
      }
    },
    staleTime: (query) => (query.state.data?.allowed === false ? Infinity : 5 * 60_000),
    retry: 1,
  });
  return { allowed: q.data?.allowed === true, checking: q.isPending };
}

export function FieldTeamScreen() {
  const { colors } = useTheme();
  const [department, setDepartment] = useState('');
  const [selected, setSelected] = useState<number | null>(null);
  const [dayOffset, setDayOffset] = useState(0);
  const [openedAt] = useState(() => Date.now());
  const date = utcDay(openedAt, dayOffset);

  const q = useQuery({
    queryKey: [...FIELD_NOW_KEY, department],
    queryFn: () => fetchFieldNow(department || undefined),
    refetchInterval: REFRESH_MS,
    retry: (n, e) => !isScopeError(e) && n < 1,
  });
  const trailQ = useQuery({
    queryKey: ['tracking', 'trail', selected, date],
    queryFn: () => fetchTrail(selected!, date),
    enabled: selected != null,
    refetchInterval: dayOffset === 0 ? REFRESH_MS : false,
    retry: (n, e) => !isScopeError(e) && n < 1,
  });
  const [depts, setDepts] = useState<string[]>([]);
  const seen = q.data && !department ? Array.from(new Set(q.data.rows.map((r) => r.department).filter((d): d is string => !!d))).sort() : null;
  if (seen && seen.join('|') !== depts.join('|')) setDepts(seen);

  const rows = useMemo(
    () => [...(q.data?.rows ?? [])].sort((a, b) => Number(!!b.ping) - Number(!!a.ping) || a.name.localeCompare(b.name)),
    [q.data],
  );
  const selectedRow = rows.find((r) => r.user_id === selected) ?? null;
  const trail = trailQ.data && trailQ.data.user_id === selected && trailQ.data.date === date ? trailQ.data : null;
  const pick = (id: number) => setSelected((cur) => (cur === id ? null : id));

  if (q.error && isScopeError(q.error)) {
    return <Screen><Card><Text testID="field-no-scope" accessibilityRole="alert">You don&apos;t have a team scope, so the field team is not available to you.</Text></Card></Screen>;
  }
  if (q.isPending) return <Screen><Text muted testID="field-loading">Loading field team…</Text></Screen>;
  if (q.error && !q.data) {
    return (
      <Screen>
        <Card style={{ gap: 8 }}>
          <Text testID="field-error" accessibilityRole="alert" style={{ color: colors.danger }}>{normalizeError(q.error).message}</Text>
          <Button variant="secondary" title="Try again" onPress={() => void q.refetch()} />
        </Card>
      </Screen>
    );
  }
  const data = q.data!;
  const showBoard = data.tracked > 0 || !!department;

  return (
    <Screen scroll refreshControl={<RefreshControl refreshing={q.isRefetching} onRefresh={() => void q.refetch()} />} style={{ gap: 12 }}>
      <Text muted size={13}>Latest location of tracked employees on shift. Shared only during rostered shifts by employees who consented; views are audit-logged. Shift times are UTC.</Text>
      {depts.length > 0 || department ? (
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
          <Chip testID="field-dept-all" label="All departments" selected={!department} onPress={() => { setDepartment(''); setSelected(null); }} />
          {depts.map((d) => <Chip key={d} testID={`field-dept-${d}`} label={d} selected={department === d} onPress={() => { setDepartment(d); setSelected(null); }} />)}
        </View>
      ) : null}
      {q.error ? <Text testID="field-refresh-error" accessibilityRole="alert" style={{ color: colors.danger }}>{normalizeError(q.error).message}</Text> : null}

      {!showBoard ? (
        <Card style={{ gap: 4 }}>
          <Text testID="field-empty" weight="600">No one is being tracked</Text>
          <Text muted size={13}>Tracking is off by default. HR can enable it per role in Tracking settings, and employees must consent.</Text>
        </Card>
      ) : (
        <>
          <Text testID="field-counts" muted>{data.tracked} tracked · {data.with_location} with recent location</Text>
          {mapsAvailable() ? (
            <FieldMap rows={rows} selected={selected} trail={trail?.points ?? []} onSelect={pick} />
          ) : (
            <Text testID="field-no-map" muted size={13}>The map is not available in this build. Locations are listed below.</Text>
          )}
          {rows.map((r) => {
            const m = statusMeta(r.status);
            const on = r.user_id === selected;
            return (
              <Pressable key={r.user_id} testID={`field-row-${r.user_id}`} accessibilityRole="button" accessibilityState={{ selected: on }} onPress={() => pick(r.user_id)}>
                <Card style={{ gap: 4, borderColor: on ? colors.primary : colors.border }}>
                  <View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: 8 }}>
                    <Text weight="600" style={{ flex: 1 }}>{r.name}</Text>
                    <Text size={13} weight="600" style={{ color: m.color }}>{m.label}</Text>
                  </View>
                  <Text muted size={13}>{[r.department, shiftText(r)].filter(Boolean).join(' · ')}</Text>
                  <Text size={13}>{r.ping ? `Last seen ${lastSeen(r.ping.captured_at)}${r.ping.battery != null ? ` · ${Math.round(r.ping.battery)}% battery` : ''}` : 'No recent location'}</Text>
                </Card>
              </Pressable>
            );
          })}
          {selectedRow ? (
            <Card style={{ gap: 8 }} testID="field-trail-card">
              <Text weight="600">Trail: {selectedRow.name}</Text>
              <View style={{ flexDirection: 'row', gap: 8 }}>
                <Chip testID="field-trail-today" label="Today" selected={dayOffset === 0} onPress={() => setDayOffset(0)} />
                <Chip testID="field-trail-yesterday" label="Yesterday" selected={dayOffset === 1} onPress={() => setDayOffset(1)} />
              </View>
              {trailQ.isPending ? (
                <Text muted testID="field-trail-loading">Loading trail…</Text>
              ) : trailQ.error ? (
                <Text testID="field-trail-error" accessibilityRole="alert" style={{ color: colors.danger }}>{normalizeError(trailQ.error).message}</Text>
              ) : trail && trail.points.length === 0 ? (
                <Text testID="field-trail-empty" muted>No location points recorded on {trail.date}.</Text>
              ) : trail ? (
                <Text testID="field-trail-summary" muted>
                  {trail.points.length} point{trail.points.length === 1 ? '' : 's'} from {fmtUtcTime(trail.points[0].captured_at)} to {fmtUtcTime(trail.points[trail.points.length - 1].captured_at)}
                  {trail.truncated ? ' (first points only: trail truncated)' : ''}
                </Text>
              ) : null}
              <Button variant="secondary" title="Clear selection" onPress={() => setSelected(null)} />
            </Card>
          ) : null}
        </>
      )}
    </Screen>
  );
}
