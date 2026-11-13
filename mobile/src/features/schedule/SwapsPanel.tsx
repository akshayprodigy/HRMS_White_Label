import { View } from 'react-native';
import { normalizeError } from '../../api/client';
import { Button, Card, Text } from '../../components/ui';
import { fmtUtcDate } from '../../lib/time';
import type { Swap } from '../../api/types';
import { GateInline } from '../attendance/GateNotice';
import { isGateError } from '../attendance/gate';
import { cellText } from './api';
import { useCancelDrop, useDrops, useGuardedRun, useSwapAction, useSwaps } from './hooks';
import { ConfirmAction, ErrorText, StatusBadge } from './ui';

function SwapRow({ s, run, isBusy, act }: { s: Swap; run: ReturnType<typeof useGuardedRun>['run']; isBusy: (k: string) => boolean; act: ReturnType<typeof useSwapAction> }) {
  const mine = s.direction === 'outgoing';
  const other = mine ? s.counterparty_name : s.requester_name;
  const myCell = mine ? s.requester_cell : s.counterparty_cell;
  const theirCell = mine ? s.counterparty_cell : s.requester_cell;
  const myDate = mine ? s.requester_date : s.counterparty_date;
  const theirDate = mine ? s.counterparty_date : s.requester_date;
  const go = (key: string, action: 'accept' | 'decline' | 'cancel') => void run(`${key}${s.id}`, () => act.mutateAsync({ id: s.id, action }));
  return (
    <Card testID={`swap-${s.id}`} style={{ gap: 6 }}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
        <Text weight="600" style={{ flexShrink: 1 }}>{mine ? `You ⇄ ${other || 'Colleague'}` : `${other || 'Colleague'} ⇄ You`}</Text>
        <StatusBadge testID={`swap-status-${s.id}`} status={s.status} />
      </View>
      <Text muted size={13}>{`You give ${cellText(myCell)} on ${fmtUtcDate(myDate)} · you get ${cellText(theirCell)} on ${fmtUtcDate(theirDate)}`}</Text>
      {s.reason ? <Text muted size={13}>{`"${s.reason}"`}</Text> : null}
      {s.decision_note ? <Text muted size={13}>{`Note: ${s.decision_note}`}</Text> : null}
      {!mine && s.status === 'pending_peer' ? (
        <View style={{ gap: 8 }}>
          <Button testID={`swap-accept-${s.id}`} title="Accept" loading={isBusy(`a${s.id}`)} disabled={isBusy(`d${s.id}`)} onPress={() => go('a', 'accept')} />
          <Button testID={`swap-decline-${s.id}`} variant="secondary" title="Decline" loading={isBusy(`d${s.id}`)} disabled={isBusy(`a${s.id}`)} onPress={() => go('d', 'decline')} />
        </View>
      ) : null}
      {mine && (s.status === 'pending_peer' || s.status === 'pending_approval') ? (
        <ConfirmAction id={`swap-cancel-${s.id}`} label="Cancel request" prompt="Cancel this swap request?" busy={isBusy(`c${s.id}`)} onConfirm={() => go('c', 'cancel')} />
      ) : null}
    </Card>
  );
}

/** Incoming/outgoing swap requests plus my give-away requests. */
export function SwapsPanel() {
  const swaps = useSwaps();
  const drops = useDrops();
  const act = useSwapAction();
  const cancelDrop = useCancelDrop();
  const { run, error, isBusy } = useGuardedRun();

  const gate = [swaps, drops].find((q) => q.error && isGateError(q.error));
  if (gate) return <GateInline />;
  const loadErr = [swaps, drops].find((q) => q.error)?.error;
  const incoming = (swaps.data ?? []).filter((s) => s.direction === 'incoming');
  const outgoing = (swaps.data ?? []).filter((s) => s.direction === 'outgoing');

  return (
    <View style={{ gap: 10 }}>
      <Text muted size={13}>Start a swap or give-away from a day on My shifts.</Text>
      {error ? <ErrorText testID="swaps-error">{error}</ErrorText> : null}
      {loadErr ? (
        <Card style={{ gap: 8 }}>
          <ErrorText testID="swaps-load-error">{normalizeError(loadErr).message}</ErrorText>
          <Button variant="secondary" title="Try again" onPress={() => void Promise.all([swaps.refetch(), drops.refetch()])} />
        </Card>
      ) : null}
      {swaps.isPending ? <Text muted>Loading…</Text> : null}

      <Text weight="700">{`Incoming (${incoming.length})`}</Text>
      {swaps.data && incoming.length === 0 ? <Text muted testID="swaps-incoming-empty">No incoming requests.</Text> : null}
      {incoming.map((s) => <SwapRow key={s.id} s={s} run={run} isBusy={isBusy} act={act} />)}

      <Text weight="700">{`Outgoing (${outgoing.length})`}</Text>
      {swaps.data && outgoing.length === 0 ? <Text muted testID="swaps-outgoing-empty">No outgoing requests.</Text> : null}
      {outgoing.map((s) => <SwapRow key={s.id} s={s} run={run} isBusy={isBusy} act={act} />)}

      <Text weight="700">My give-away requests</Text>
      {drops.data && drops.data.length === 0 ? <Text muted testID="drops-empty">No give-away requests.</Text> : null}
      {(drops.data ?? []).map((d) => (
        <Card key={d.id} testID={`drop-${d.id}`} style={{ gap: 6 }}>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
            <Text weight="600" style={{ flexShrink: 1 }}>{`${d.shift_name || 'Shift'} · ${fmtUtcDate(d.work_date)}`}</Text>
            <StatusBadge testID={`drop-status-${d.id}`} status={d.status} />
          </View>
          <Text muted size={13}>{`"${d.reason}"`}</Text>
          {d.decision_note ? <Text muted size={13}>{`Note: ${d.decision_note}`}</Text> : null}
          {d.status === 'pending' ? (
            <ConfirmAction id={`drop-cancel-${d.id}`} label="Cancel request" prompt="Cancel this give-away request?" busy={isBusy(`x${d.id}`)} onConfirm={() => void run(`x${d.id}`, () => cancelDrop.mutateAsync(d.id))} />
          ) : null}
        </Card>
      ))}
    </View>
  );
}
