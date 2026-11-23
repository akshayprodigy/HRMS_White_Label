import { useRouter } from 'expo-router';
import { memo, useCallback, useState } from 'react';
import { FlatList, Pressable, RefreshControl, View } from 'react-native';
import { normalizeError } from '../../api/client';
import type { BulkResult } from '../../api/types';
import { Button, Card, Screen, Text, TextInput } from '../../components/ui';
import { useTheme } from '../../theme';
import { fmtInr, fmtUtcDate } from '../../lib/time';
import { GateInline } from '../attendance/GateNotice';
import { isGateError } from '../attendance/gate';
import type { ApprovalCard } from './api';
import { TeamRequests } from '../team-requests/TeamRequests';
import { useApprovals, useBulkAction } from './hooks';

export function Badge({ label, tone, testID }: { label: string; tone: 'danger' | 'info'; testID?: string }) {
  const { colors } = useTheme();
  const bg = tone === 'danger' ? colors.danger : colors.primary;
  return (
    <View testID={testID} accessible accessibilityLabel={label} style={{ backgroundColor: bg, borderRadius: 8, paddingHorizontal: 8, paddingVertical: 2 }}>
      <Text size={12} weight="600" style={{ color: colors.primaryText }}>{label}</Text>
    </View>
  );
}

export const MAX_BULK = 100;
/** Toggle `id`; adding beyond `max` is ignored (the backend accepts at most 100 items per request). */
export function toggleSelection(prev: Set<number>, id: number, max = MAX_BULK): Set<number> {
  const n = new Set(prev);
  if (n.has(id)) n.delete(id);
  else if (n.size < max) n.add(id);
  return n;
}
const Separator = () => <View style={{ height: 12 }} />;

const Row = memo(function Row({ card, selected, onToggle, onOpen }: { card: ApprovalCard; selected: boolean; onToggle: (id: number) => void; onOpen: (key: string) => void }) {
  const { colors } = useTheme();
  return (
    <Card style={{ flexDirection: 'row', gap: 12, alignItems: 'flex-start' }}>
      {card.source === 'legacy' ? (
        <Pressable
          testID={`select-${card.key}`}
          accessibilityRole="checkbox"
          accessibilityState={{ checked: selected }}
          accessibilityLabel={`Select ${card.title}`}
          onPress={() => onToggle(card.refId)}
          hitSlop={12}
          style={{ width: 32, height: 32, borderRadius: 8, borderWidth: 2, borderColor: colors.primary, backgroundColor: selected ? colors.primary : 'transparent', alignItems: 'center', justifyContent: 'center' }}
        >
          {selected ? <Text size={14} style={{ color: colors.primaryText }}>✓</Text> : null}
        </Pressable>
      ) : null}
      <Pressable testID={`open-${card.key}`} accessibilityRole="button" accessibilityLabel={`Open ${card.title}`} onPress={() => onOpen(card.key)} style={{ flex: 1, gap: 2 }}>
        <View style={{ flexDirection: 'row', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
          <Text size={11} weight="600" muted>{card.kind.toUpperCase()}</Text>
          {card.overdue ? <Badge testID={`overdue-${card.key}`} tone="danger" label="Overdue" /> : null}
          {card.actingFor ? <Badge testID={`acting-${card.key}`} tone="info" label={`Acting for ${card.actingFor}`} /> : null}
        </View>
        <Text weight="600">{card.title}</Text>
        {card.subtitle ? <Text muted size={13}>{card.subtitle}</Text> : null}
        <Text muted size={12}>
          Submitted {fmtUtcDate(card.createdAt)}
          {card.meta ? ` · ${card.meta}` : ''}
          {card.amountPaise != null ? ` · ${fmtInr(card.amountPaise)}` : ''}
        </Text>
      </Pressable>
    </Card>
  );
});

function summarize(r: BulkResult, verb: string): string {
  return `${r.ok_count} ${verb}${r.failed_count ? `, ${r.failed_count} failed` : ''}`;
}

export function ApprovalsScreen() {
  const router = useRouter();
  const { colors } = useTheme();
  const q = useApprovals();
  const bulk = useBulkAction();
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [comment, setComment] = useState('');
  const [confirmReject, setConfirmReject] = useState(false);
  const [result, setResult] = useState<{ text: string; failures: string[] } | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const items = q.data?.items ?? [];
  // Drop selections that disappeared from the list (e.g. acted on elsewhere).
  const legacyIds = new Set(items.filter((c) => c.source === 'legacy').map((c) => c.refId));
  const sel = [...selected].filter((id) => legacyIds.has(id));
  const selectedSet = new Set(sel);

  const toggle = useCallback((id: number) => {
    setSelected((prev) => toggleSelection(prev, id));
  }, []);
  const open = useCallback((key: string) => router.push(`/approval/${key}` as never), [router]);

  const run = async (action: 'approve' | 'reject') => {
    setActionError(null);
    setResult(null);
    try {
      const r = await bulk.mutateAsync({ ids: sel, action, comment });
      setResult({
        text: summarize(r, action === 'approve' ? 'approved' : 'rejected'),
        failures: r.results.filter((x) => !x.ok).map((x) => `#${x.id}: ${x.error ?? 'failed'}`),
      });
      setSelected(new Set());
      setComment('');
    } catch (e) {
      setActionError(normalizeError(e).message);
    } finally {
      setConfirmReject(false);
    }
  };

  if (q.error && isGateError(q.error)) {
    return (
      <Screen>
        <GateInline />
      </Screen>
    );
  }

  const header = (
    <View style={{ gap: 12, marginBottom: 12 }}>
      <Text weight="700" size={20}>Approvals</Text>
      {q.data?.partialError ? (
        <Text testID="approvals-partial-error" accessibilityRole="alert" size={13} style={{ color: colors.danger }}>
          Some requests could not be loaded: {q.data.partialError}
        </Text>
      ) : null}
      {q.error && !q.data ? <Text testID="approvals-error" accessibilityRole="alert" style={{ color: colors.danger }}>{normalizeError(q.error).message}</Text> : null}
      {result ? (
        <Card style={{ gap: 4 }}>
          <Text testID="bulk-summary" accessibilityLiveRegion="polite" weight="600">{result.text}</Text>
          {result.failures.map((f) => (
            <Text key={f} muted size={13}>{f}</Text>
          ))}
        </Card>
      ) : null}
      {actionError ? <Text testID="bulk-error" accessibilityRole="alert" style={{ color: colors.danger }}>{actionError}</Text> : null}
      {sel.length > 0 ? (
        <Card style={{ gap: 8 }}>
          <Text weight="600" testID="bulk-count">{sel.length} selected</Text>
          {sel.length >= MAX_BULK ? <Text testID="bulk-limit-hint" muted size={13}>{`You can act on up to ${MAX_BULK} requests at a time.`}</Text> : null}
          <TextInput label="Comment (optional)" value={comment} onChangeText={setComment} multiline />
          {confirmReject ? (
            <>
              <Text testID="bulk-reject-confirm-text">{`Reject ${sel.length} request${sel.length > 1 ? 's' : ''}? This cannot be undone.`}</Text>
              <Button testID="bulk-reject-confirm" title="Confirm reject" loading={bulk.isPending} onPress={() => void run('reject')} />
              <Button testID="bulk-reject-cancel" variant="secondary" title="Cancel" onPress={() => setConfirmReject(false)} />
            </>
          ) : (
            <>
              <Button testID="bulk-approve" title="Approve selected" loading={bulk.isPending} onPress={() => void run('approve')} />
              <Button testID="bulk-reject" variant="secondary" title="Reject selected" disabled={bulk.isPending} onPress={() => setConfirmReject(true)} />
            </>
          )}
        </Card>
      ) : null}
      <TeamRequests />
    </View>
  );

  return (
    <Screen style={{ paddingBottom: 0 }}>
      <FlatList
        testID="approvals-list"
        data={items}
        keyExtractor={(c) => c.key}
        ListHeaderComponent={header}
        ItemSeparatorComponent={Separator}
        initialNumToRender={10}
        refreshControl={<RefreshControl refreshing={q.isRefetching} onRefresh={() => void q.refetch()} />}
        ListEmptyComponent={q.isLoading ? <Text muted>Loading…</Text> : <Text testID="approvals-empty" muted>Nothing to approve</Text>}
        renderItem={({ item }) => (
          <Row card={item} selected={item.source === 'legacy' && selectedSet.has(item.refId)} onToggle={toggle} onOpen={open} />
        )}
        extraData={selected}
      />
    </Screen>
  );
}
