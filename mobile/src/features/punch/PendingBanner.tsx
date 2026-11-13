import { useState } from 'react';
import { View } from 'react-native';
import { Button, Card, Text } from '../../components/ui';
import { useTheme } from '../../theme';
import { usePunchQueue, useSyncNow } from './hooks';
import { isStale } from './queue';

/** "Pending sync (N)" with manual Sync now, stale-item warning and rejected-punch reasons. Renders nothing when empty. */
export function PendingBanner({ compact = false }: { compact?: boolean }) {
  const { colors } = useTheme();
  const { queue, items, rejected, notice, needsAttention } = usePunchQueue();
  const syncNowRun = useSyncNow();
  const [busy, setBusy] = useState(false);
  const [now, setNow] = useState(() => Date.now());
  const [note, setNote] = useState<string | null>(null);
  if (!items.length && !rejected.length && !notice) return null;
  const stale = items.some((i) => isStale(i, now));

  const syncNow = async () => {
    setBusy(true);
    setNow(Date.now());
    try {
      const o = await syncNowRun(true);
      setNote(o.failed ? "Couldn't sync yet. We'll retry automatically." : o.selfieDropped ? "A selfie couldn't be uploaded, so that punch was sent without it." : null);
    } finally {
      setBusy(false);
    }
  };

  return (
    <View style={{ gap: 8 }}>
      {notice ? (
        <Card testID="queue-notice" accessibilityRole="alert" style={{ borderColor: colors.danger, gap: 4 }}>
          <Text size={14}>{notice}</Text>
          <Button variant="secondary" title="OK" onPress={() => queue.dismissNotice()} />
        </Card>
      ) : null}
      {needsAttention ? (
        <Card testID="needs-attention" accessibilityRole="alert" style={{ borderColor: colors.danger, gap: 4 }}>
          <Text size={14}>{"One punch couldn't be sent. Please contact HR to correct your attendance."}</Text>
        </Card>
      ) : null}
      {items.length ? (
        <Card testID="pending-sync" accessibilityRole="summary" accessibilityLiveRegion="polite" style={{ borderColor: stale ? colors.danger : colors.primary, gap: 6 }}>
          <Text weight="600" testID="pending-sync-title">{`Pending sync (${items.length})`}</Text>
          {!compact ? <Text size={13} muted>Saved on this phone; they will upload when you are back online.</Text> : null}
          {items.some((i) => i.selfie_dropped) ? <Text size={13} testID="pending-selfie-dropped">A selfie could not be uploaded; that punch will be sent without it.</Text> : null}
          {stale ? <Text size={13} testID="pending-stale" style={{ color: colors.danger }}>Some punches are over 10 hours old. Sync soon: the server rejects punches older than its offline limit.</Text> : null}
          {note ? <Text size={13} muted>{note}</Text> : null}
          <Button testID="sync-now" variant="secondary" title="Sync now" loading={busy} onPress={() => void syncNow()} />
        </Card>
      ) : null}
      {rejected.map((r) => (
        <Card key={r.client_uuid} testID="rejected-punch" accessibilityRole="alert" style={{ borderColor: colors.danger, gap: 4 }}>
          <Text weight="600">{`Punch ${r.kind} not accepted`}</Text>
          <Text size={13}>{r.reason}</Text>
          <Text size={12} muted>{new Date(r.captured_at).toLocaleString()}</Text>
          <Button variant="secondary" title="Dismiss" onPress={() => void queue.dismissRejected(r.client_uuid)} />
        </Card>
      ))}
    </View>
  );
}
