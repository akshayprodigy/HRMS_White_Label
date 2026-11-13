import { useState } from 'react';
import { View } from 'react-native';
import { Button, Card, Text } from '../../components/ui';
import { useTheme } from '../../theme';
import { syncDeps } from './api';
import { usePunchQueue, useInvalidateAfterPunch } from './hooks';
import { isStale } from './queue';

/** "Pending sync (N)" with manual Sync now, stale-item warning and rejected-punch reasons. Renders nothing when empty. */
export function PendingBanner({ compact = false }: { compact?: boolean }) {
  const { colors } = useTheme();
  const { queue, items, rejected } = usePunchQueue();
  const invalidate = useInvalidateAfterPunch();
  const [busy, setBusy] = useState(false);
  const [now, setNow] = useState(() => Date.now());
  const [note, setNote] = useState<string | null>(null);
  if (!items.length && !rejected.length) return null;
  const stale = items.some((i) => isStale(i, now));

  const syncNow = async () => {
    setBusy(true);
    setNow(Date.now());
    try {
      const o = await queue.sync(syncDeps, { force: true });
      setNote(o.failed ? "Couldn't sync yet. We'll retry automatically." : null);
      if (o.created + o.duplicate + o.rejected > 0) await invalidate();
    } finally {
      setBusy(false);
    }
  };

  return (
    <View style={{ gap: 8 }}>
      {items.length ? (
        <Card testID="pending-sync" style={{ borderColor: stale ? colors.danger : colors.primary, gap: 6 }}>
          <Text weight="600" testID="pending-sync-title">{`Pending sync (${items.length})`}</Text>
          {!compact ? <Text size={13} muted>Saved on this phone; they will upload when you are back online.</Text> : null}
          {stale ? <Text size={13} testID="pending-stale" style={{ color: colors.danger }}>Some punches are over 10 hours old. Sync soon: the server rejects punches older than its offline limit.</Text> : null}
          {note ? <Text size={13} muted>{note}</Text> : null}
          <Button testID="sync-now" variant="secondary" title="Sync now" loading={busy} onPress={() => void syncNow()} />
        </Card>
      ) : null}
      {rejected.map((r) => (
        <Card key={r.client_uuid} testID="rejected-punch" style={{ borderColor: colors.danger, gap: 4 }}>
          <Text weight="600">{`Punch ${r.kind} not accepted`}</Text>
          <Text size={13}>{r.reason}</Text>
          <Text size={12} muted>{new Date(r.captured_at).toLocaleString()}</Text>
          <Button variant="secondary" title="Dismiss" onPress={() => void queue.dismissRejected(r.client_uuid)} />
        </Card>
      ))}
    </View>
  );
}
