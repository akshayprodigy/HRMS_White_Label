import { useState } from 'react';
import { RefreshControl, View } from 'react-native';
import { normalizeError } from '../../api/client';
import { Button, Card, Screen, Text } from '../../components/ui';
import { useTheme } from '../../theme';
import { fmtUtcDate } from '../../lib/time';
import { GateInline } from '../attendance/GateNotice';
import { isGateError } from '../attendance/gate';
import { Badge } from '../approvals/ApprovalsScreen';
import { proofOwed, type LeaveRequest } from './api';
import { ApplyLeaveForm } from './ApplyLeaveForm';
import { useBalances, useCancelLeave, useLeaveTypes, useMyLeaves, useSubmitProof } from './hooks';
import { ProofPicker } from './ProofPicker';
import { validateAttachment } from './validation';

const STATUS_LABEL: Record<string, string> = { submitted: 'Pending', approved: 'Approved', rejected: 'Rejected', cancelled: 'Cancelled', draft: 'Draft' };

function RequestCard({ r }: { r: LeaveRequest }) {
  const { colors } = useTheme();
  const cancel = useCancelLeave();
  const proof = useSubmitProof();
  const [confirm, setConfirm] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const owed = proofOwed(r);

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
  const upload = async (file: Parameters<typeof proof.mutateAsync>[0]['file']) => {
    setErr(null);
    const bad = validateAttachment(file);
    if (bad) return setErr(bad);
    try {
      await proof.mutateAsync({ id: r.id, file });
    } catch (e) {
      setErr(normalizeError(e).message);
    }
  };

  return (
    <Card testID={`leave-${r.id}`} style={{ gap: 6 }}>
      <View style={{ flexDirection: 'row', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
        <Text weight="600">{r.leave_type?.name ?? 'Leave'}</Text>
        <Badge label={STATUS_LABEL[r.status] ?? r.status} tone={r.status === 'rejected' ? 'danger' : 'info'} testID={`leave-status-${r.id}`} />
        {r.is_emergency ? <Badge label="Emergency" tone="danger" testID={`leave-emergency-${r.id}`} /> : null}
      </View>
      <Text muted size={13}>
        {fmtUtcDate(r.start_date)} → {fmtUtcDate(r.end_date)}
        {r.is_half_day ? ` · Half day${r.half_day_session ? ` (${r.half_day_session})` : ''}` : ''} · {r.total_days}d
      </Text>
      {r.reason ? <Text muted size={13} numberOfLines={2}>{r.reason}</Text> : null}

      {owed ? (
        <View style={{ gap: 8 }}>
          <Badge testID={`proof-due-${r.id}`} tone="danger" label={`Proof due by ${r.proof_due_date}`} />
          {proof.isPending ? <Text muted testID={`proof-uploading-${r.id}`}>Uploading proof…</Text> : <ProofPicker testIDPrefix={`proof-${r.id}`} onPick={(f) => void upload(f)} />}
        </View>
      ) : null}
      {r.converted_to_lop_at ? <Text testID={`leave-lop-${r.id}`} size={13} style={{ color: colors.danger }}>Proof was not submitted in time: converted to loss of pay.</Text> : null}
      {r.is_emergency && r.proof_submitted_at && !r.converted_to_lop_at ? <Text muted size={13}>Proof submitted</Text> : null}

      {r.status === 'submitted' ? (
        confirm ? (
          <>
            <Text testID={`cancel-confirm-text-${r.id}`}>Cancel this leave request?</Text>
            <Button testID={`cancel-confirm-${r.id}`} title="Yes, cancel request" loading={cancel.isPending} onPress={() => void doCancel()} />
            <Button testID={`cancel-keep-${r.id}`} variant="secondary" title="Keep it" onPress={() => setConfirm(false)} />
          </>
        ) : (
          <Button testID={`cancel-${r.id}`} variant="secondary" title="Cancel request" onPress={() => setConfirm(true)} />
        )
      ) : null}
      {err ? <Text testID={`leave-error-${r.id}`} accessibilityRole="alert" size={13} style={{ color: colors.danger }}>{err}</Text> : null}
    </Card>
  );
}

export function LeaveScreen({ now }: { now?: () => Date } = {}) {
  const { colors } = useTheme();
  const balances = useBalances();
  const types = useLeaveTypes();
  const my = useMyLeaves();
  const [applying, setApplying] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const firstError = [balances, types, my].find((q) => q.error)?.error;
  if (firstError && isGateError(firstError)) {
    return (
      <Screen>
        <GateInline />
      </Screen>
    );
  }
  const refreshing = balances.isRefetching || my.isRefetching;
  const refresh = () => void Promise.all([balances.refetch(), types.refetch(), my.refetch()]);
  const history = my.data ?? [];

  return (
    <Screen scroll refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} />} style={{ gap: 12 }}>
      <Text weight="700" size={20}>Leave</Text>
      {notice ? <Card><Text testID="leave-notice" accessibilityLiveRegion="polite">{notice}</Text></Card> : null}
      {firstError && !(balances.data && my.data) ? (
        <Card style={{ gap: 8 }}>
          <Text testID="leave-error" accessibilityRole="alert" style={{ color: colors.danger }}>{normalizeError(firstError).message}</Text>
          <Button variant="secondary" title="Try again" onPress={refresh} />
        </Card>
      ) : null}

      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
        {(balances.data ?? []).map((b) => (
          <Card key={b.leave_type.id} testID={`balance-${b.leave_type.id}`} style={{ minWidth: 140, flexGrow: 1 }}>
            <Text size={12} weight="600" muted numberOfLines={1}>{b.leave_type.name}</Text>
            <Text size={24} weight="700">{b.remaining.toFixed(1)}</Text>
            <Text size={12} muted>{`of ${b.total.toFixed(1)} days`}</Text>
          </Card>
        ))}
      </View>
      {balances.data && balances.data.length === 0 ? <Text muted testID="balances-empty">No leave balance assigned yet.</Text> : null}

      {applying ? (
        <ApplyLeaveForm
          types={types.data ?? []}
          now={now}
          onCancel={() => setApplying(false)}
          onDone={(m) => {
            setApplying(false);
            setNotice(m);
          }}
        />
      ) : (
        <Button testID="apply-leave" title="Apply for leave" disabled={!types.data} onPress={() => { setNotice(null); setApplying(true); }} />
      )}

      <Text weight="700" size={18}>My requests</Text>
      {my.isPending ? <Text muted>Loading…</Text> : null}
      {my.data && history.length === 0 ? <Text testID="leave-empty" muted>No leave requests yet.</Text> : null}
      {history.map((r) => (
        <RequestCard key={r.id} r={r} />
      ))}
    </Screen>
  );
}
