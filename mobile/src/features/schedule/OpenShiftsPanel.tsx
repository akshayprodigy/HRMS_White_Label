import { useState } from 'react';
import { View } from 'react-native';
import { normalizeError } from '../../api/client';
import { Button, Card, Text } from '../../components/ui';
import { fmtUtcDate } from '../../lib/time';
import { GateInline } from '../attendance/GateNotice';
import { isGateError } from '../attendance/gate';
import { fmtRange } from './api';
import { useClaim, useGuardedRun, useOpenShifts, useWithdraw } from './hooks';
import { ConfirmAction, ErrorText, StatusBadge } from './ui';

/** Unfilled shifts in the next 60 days the backend says I may claim (it already drops ineligible ones, e.g. my own posts), plus my pending claims. */
export function OpenShiftsPanel() {
  const q = useOpenShifts();
  const claim = useClaim();
  const withdraw = useWithdraw();
  const { run, error, isBusy } = useGuardedRun();
  const [notice, setNotice] = useNotice();

  if (q.error && isGateError(q.error)) return <GateInline />;
  const rows = q.data ?? [];

  const doClaim = (id: number) =>
    run(`c${id}`, async () => {
      setNotice('', []);
      const r = await claim.mutateAsync(id);
      setNotice(r?.my_claim_status === 'approved' ? 'Claim confirmed: the shift is yours.' : 'Claim submitted, awaiting confirmation.', r?.warnings ?? []);
    });
  const doWithdraw = (id: number, claimId: number) =>
    run(`w${id}`, async () => {
      setNotice('', []);
      await withdraw.mutateAsync(claimId);
      setNotice('Claim withdrawn.', []);
    });

  return (
    <View style={{ gap: 10 }}>
      <Text muted size={13}>Unfilled shifts in the next 60 days that you are eligible for. Your scheduler confirms claims. Times are in organisation time.</Text>
      {notice.msg ? <Card testID="open-notice" accessibilityLiveRegion="polite"><Text>{notice.msg}</Text>{notice.warnings.map((w) => <Text key={w} muted size={13}>{w}</Text>)}</Card> : null}
      {error ? <ErrorText testID="open-error">{error}</ErrorText> : null}
      {q.isPending ? <Text muted>Loading…</Text> : null}
      {q.error ? (
        <Card style={{ gap: 8 }}>
          <ErrorText testID="open-load-error">{normalizeError(q.error).message}</ErrorText>
          <Button variant="secondary" title="Try again" onPress={() => void q.refetch()} />
        </Card>
      ) : null}
      {q.data && rows.length === 0 ? <Text muted testID="open-empty">No open shifts right now.</Text> : null}
      {rows.map((o) => {
        const cs = o.my_claim_status;
        const canClaim = !cs || cs === 'withdrawn';
        return (
          <Card key={o.id} testID={`open-${o.id}`} style={{ gap: 6 }}>
            <Text weight="600">{`${fmtUtcDate(o.work_date)} · ${o.shift_name || 'Shift'}`}</Text>
            {o.shift_start ? <Text muted size={13}>{fmtRange(o.shift_start, o.shift_end)}</Text> : null}
            <Text muted size={13}>{`${[o.department, o.location].filter(Boolean).join(' · ') || 'Any department'} · ${o.filled}/${o.slots} filled`}</Text>
            {o.note ? <Text muted size={13}>{`"${o.note}"`}</Text> : null}
            {cs ? <View style={{ flexDirection: 'row' }}><StatusBadge testID={`open-status-${o.id}`} status={cs} /></View> : null}
            {canClaim ? <Button testID={`claim-${o.id}`} title="Claim" loading={isBusy(`c${o.id}`)} onPress={() => void doClaim(o.id)} /> : null}
            {cs === 'pending' && o.my_claim_id ? (
              <ConfirmAction id={`withdraw-${o.id}`} label="Withdraw claim" prompt="Withdraw your claim?" busy={isBusy(`w${o.id}`)} onConfirm={() => void doWithdraw(o.id, o.my_claim_id as number)} />
            ) : null}
          </Card>
        );
      })}
    </View>
  );
}

function useNotice() {
  const [s, set] = useState<{ msg: string | null; warnings: string[] }>({ msg: null, warnings: [] });
  return [s, (msg: string, warnings: string[]) => set({ msg, warnings })] as const;
}
