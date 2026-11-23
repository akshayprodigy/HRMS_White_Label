import { useState } from 'react';
import { RefreshControl } from 'react-native';
import { normalizeError } from '../../api/client';
import { Button, Card, Screen, Text } from '../../components/ui';
import { useOrgTime } from '../../lib/org-time';
import { useTheme } from '../../theme';
import type { WorkLocationRequest } from './api';
import { useCancelRequest, useMyRequests } from './hooks';
import { canCancel, fmtRange, KIND_LABEL, STATUS_LABEL } from './logic';
import { RequestForm } from './RequestForm';

function RequestCard({ r, today, ready }: { r: WorkLocationRequest; today: string; ready: boolean }) {
  const { colors } = useTheme();
  const cancel = useCancelRequest();
  const [confirm, setConfirm] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const active = r.status === 'pending' || r.status === 'approved';
  const doCancel = async () => {
    setErr(null);
    try {
      await cancel.mutateAsync(r.id);
    } catch (e) {
      setErr(normalizeError(e).message);
    } finally {
      setConfirm(false);
    }
  };
  return (
    <Card testID={`wl-${r.id}`} style={{ gap: 4 }}>
      <Text weight="600">{`${KIND_LABEL[r.kind] ?? r.kind}${r.place ? ` · ${r.place}` : ''}`}</Text>
      <Text testID={`wl-status-${r.id}`} size={13} weight="600">{STATUS_LABEL[r.status] ?? r.status}</Text>
      <Text muted size={13}>{fmtRange(r)}</Text>
      <Text muted size={13}>{r.purpose}</Text>
      {(r.status === 'rejected' || r.status === 'approved') && r.decision_note ? (
        <Text testID={`wl-note-${r.id}`} size={13} style={r.status === 'rejected' ? { color: colors.danger } : undefined}>{`Note: ${r.decision_note}`}</Text>
      ) : null}
      {active ? (
        confirm ? (
          <>
            <Text>Cancel this request?</Text>
            <Button testID={`wl-cancel-confirm-${r.id}`} title="Yes, cancel request" loading={cancel.isPending} onPress={() => void doCancel()} />
            <Button testID={`wl-cancel-keep-${r.id}`} variant="secondary" title="Keep it" onPress={() => setConfirm(false)} />
          </>
        ) : (
          <>
            <Button testID={`wl-cancel-${r.id}`} variant="secondary" title="Cancel request" disabled={!ready || !canCancel(r, today)} onPress={() => setConfirm(true)} />
            {ready && !canCancel(r, today) ? <Text muted size={12}>A request that has already started cannot be cancelled here. Ask HR.</Text> : null}
          </>
        )
      ) : null}
      {err ? <Text testID={`wl-error-${r.id}`} accessibilityRole="alert" size={13} style={{ color: colors.danger }}>{err}</Text> : null}
    </Card>
  );
}

export function WorkLocationScreen() {
  const { colors } = useTheme();
  const { today, ready } = useOrgTime();
  const q = useMyRequests();
  const [creating, setCreating] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const items = q.data ?? [];
  return (
    <Screen scroll refreshControl={<RefreshControl refreshing={q.isRefetching} onRefresh={() => void q.refetch()} />} style={{ gap: 12 }}>
      <Text weight="700" size={20}>Work location</Text>
      {notice ? <Card><Text testID="wl-notice" accessibilityLiveRegion="polite">{notice}</Text></Card> : null}
      {creating ? (
        <RequestForm onCancel={() => setCreating(false)} onDone={(m) => { setCreating(false); setNotice(m); }} />
      ) : (
        <Button testID="wl-new" title="New request" onPress={() => { setNotice(null); setCreating(true); }} />
      )}
      {q.error && !q.data ? (
        <Card style={{ gap: 8 }}>
          <Text testID="wl-load-error" accessibilityRole="alert" style={{ color: colors.danger }}>{normalizeError(q.error).message}</Text>
          <Button variant="secondary" title="Try again" onPress={() => void q.refetch()} />
        </Card>
      ) : null}
      <Text weight="700">My requests</Text>
      {q.data && items.length === 0 ? <Text muted testID="wl-empty">No work-location requests yet.</Text> : null}
      {items.map((r) => <RequestCard key={r.id} r={r} today={today} ready={ready} />)}
    </Screen>
  );
}
