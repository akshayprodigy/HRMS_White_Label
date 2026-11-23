import { useQuery } from '@tanstack/react-query';
import { useRouter } from 'expo-router';
import { useState } from 'react';
import { RefreshControl, View } from 'react-native';
import { api, ApiError } from '../../api/client';
import type { RosterWeek } from '../../api/types';
import { useAuth } from '../../auth/AuthProvider';
import { Button, Card, Screen, Text } from '../../components/ui';
import { fmtOrgTime, useOrgTime } from '../../lib/org-time';
import { fmtShiftTime } from '../../lib/time';
import { useTheme } from '../../theme';
import { useApprovalsAccess } from '../approvals/hooks';
import { BroadcastBanner } from '../broadcast/BroadcastBanner';
import { useMyBroadcasts } from '../broadcast/hooks';
import { GateInline } from '../attendance/GateNotice';
import { PendingBanner } from '../punch/PendingBanner';
import { isGateError, retryUnlessGate, useAttendanceGate } from '../attendance/gate';

async function fetchRosterWeek(): Promise<RosterWeek> {
  return (await api.get<RosterWeek>('/roster/my/week')).data;
}
function greeting(now = new Date()) {
  const h = now.getHours();
  return h < 12 ? 'Good morning' : h < 17 ? 'Good afternoon' : 'Good evening';
}

export function HomeScreen() {
  useOrgTime(); // re-render once org time loads
  const router = useRouter();
  const { colors } = useTheme();
  const { user, unverified } = useAuth();
  const { gated, ready, today, query: todayQ, pendingQuery: pending } = useAttendanceGate();
  const approvals = useApprovalsAccess();

  // Gated endpoints wait for the gate answer; the pending count doubles as the gate probe (see useAttendanceGate).
  const roster = useQuery({ queryKey: ['roster-week'], queryFn: fetchRosterWeek, enabled: !!user && ready && !gated, retry: retryUnlessGate });
  const broadcasts = useMyBroadcasts();
  const [refreshing, setRefreshing] = useState(false);

  const refresh = async () => {
    setRefreshing(true);
    try {
      await Promise.allSettled([todayQ.refetch(), broadcasts.refetch(), pending.refetch(), ...(gated ? [] : [roster.refetch()])]);
    } finally {
      setRefreshing(false);
    }
  };

  const offline = [todayQ, roster, pending, broadcasts].some((q) => q.error instanceof ApiError && q.error.status === 0);
  const todayShift = roster.data?.days.find((d) => d.is_today) ?? null;
  const att = today?.attendance ?? null;
  const activeBroadcasts = (broadcasts.data ?? []).filter((b) => b.pending && b.severity !== 'critical');
  const punchState = !today ? null : !att ? 'out-none' : att.punch_out_time ? 'done' : 'in';

  return (
    <Screen scroll refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => void refresh()} />} style={{ gap: 12 }}>
      <View>
        <Text muted size={14}>{greeting()}</Text>
        <Text weight="700" size={22} testID="home-user">{user?.full_name || user?.email}</Text>
      </View>

      {unverified || offline ? (
        <Card testID="offline-banner" style={{ borderColor: colors.danger }}>
          <Text size={14}>
            {unverified ? "Offline: showing your last saved session. Some data may be out of date." : "Can't reach the server. Showing the last loaded data."}
          </Text>
        </Card>
      ) : null}

      <PendingBanner compact />

      <BroadcastBanner broadcasts={activeBroadcasts} />

      <Card style={{ gap: 4 }}>
        <Text weight="600">Attendance</Text>
        {!today ? (
          <Text muted testID="punch-status">{todayQ.isError ? 'Status unavailable' : 'Checking…'}</Text>
        ) : punchState === 'in' ? (
          <Text testID="punch-status">Punched in at {fmtOrgTime(att?.captured_at)}</Text>
        ) : punchState === 'done' ? (
          <Text testID="punch-status">Punched in {fmtOrgTime(att?.captured_at)} · out {fmtOrgTime(att?.punch_out_time)}</Text>
        ) : (
          <Text testID="punch-status">Not punched in yet today</Text>
        )}
      </Card>

      {gated || (roster.error && isGateError(roster.error)) ? (
        <GateInline testID="gate-notice" />
      ) : (
        <Card style={{ gap: 4 }}>
          <Text weight="600">{"Today's shift"}</Text>
          {roster.isPending ? (
            <Text muted>Loading…</Text>
          ) : todayShift ? (
            <>
              <Text testID="shift-name">{todayShift.on_leave ? `On leave${todayShift.leave_type ? ` (${todayShift.leave_type})` : ''}` : todayShift.holiday_name ? `Holiday: ${todayShift.holiday_name}` : todayShift.shift.name}</Text>
              {todayShift.shift.start_time ? (
                <Text testID="shift-times" muted>
                  {fmtShiftTime(todayShift.shift.start_time)} – {fmtShiftTime(todayShift.shift.end_time)}
                  {todayShift.shift.is_overnight ? ' (overnight)' : ''}
                </Text>
              ) : null}
              {todayShift.shift.transport_required ? <Text size={13} muted>Transport required</Text> : null}
            </>
          ) : (
            <Text muted>{roster.error ? "Couldn't load your shift" : 'No shift information'}</Text>
          )}
        </Card>
      )}

      {!gated && !isGateError(pending.error) ? (
        <Card style={{ gap: 4 }}>
          <Text weight="600">Pending</Text>
          <Text testID="pending-count" muted>
            {pending.data != null ? `${pending.data} pending request${pending.data === 1 ? '' : 's'}` : pending.isError ? 'Unavailable' : '…'}
          </Text>
          {approvals.show ? <Text testID="approvals-count" muted>{approvals.queueCount} awaiting your approval</Text> : null}
        </Card>
      ) : null}

      <Card style={{ gap: 8 }}>
        <Text weight="600">Quick actions</Text>
        <Button testID="qa-punch" title="Punch" onPress={() => router.navigate('/punch')} />
        <Button testID="qa-leave" variant="secondary" title="Apply for leave" onPress={() => router.navigate('/leave')} />
        <Button testID="qa-schedule" variant="secondary" title="My schedule" onPress={() => router.navigate('/schedule')} />
        {approvals.show ? <Button testID="qa-approvals" variant="secondary" title="Approvals" onPress={() => router.navigate('/approvals' as never)} /> : null}
      </Card>
    </Screen>
  );
}
