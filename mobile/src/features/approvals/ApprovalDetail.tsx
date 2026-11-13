import { useLocalSearchParams, useRouter } from 'expo-router';
import { useState } from 'react';
import { View } from 'react-native';
import { normalizeError } from '../../api/client';
import { Button, Card, Screen, Text, TextInput } from '../../components/ui';
import { useTheme } from '../../theme';
import { fmtInr, fmtUtcDate, fmtUtcTime } from '../../lib/time';
import { useApprovalAction, useApprovals } from './hooks';
import { Badge } from './ApprovalsScreen';

export function ApprovalDetail() {
  const { key } = useLocalSearchParams<{ key: string }>();
  const router = useRouter();
  const { colors } = useTheme();
  const q = useApprovals();
  const act = useApprovalAction();
  const [comment, setComment] = useState('');
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const card = q.data?.items.find((c) => c.key === key);
  if (!card) {
    return (
      <Screen>
        <Card style={{ gap: 12 }}>
          <Text testID="detail-missing" weight="600">{q.isLoading ? 'Loading…' : 'This request is no longer pending.'}</Text>
          <Button variant="secondary" title="Back to approvals" onPress={() => router.back()} />
        </Card>
      </Screen>
    );
  }

  const run = async (action: 'approve' | 'reject') => {
    setError(null);
    try {
      await act.mutateAsync({ card, action, comment });
      router.back();
    } catch (e) {
      // SoD / permission 403s and validation errors arrive here as readable ApiError messages.
      setError(normalizeError(e).message);
      setConfirming(false);
    }
  };

  return (
    <Screen scroll>
      <View style={{ gap: 12 }}>
        <Card style={{ gap: 6 }}>
          <View style={{ flexDirection: 'row', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
            <Text size={12} weight="600" muted>{card.kind.toUpperCase()}</Text>
            {card.overdue ? <Badge tone="danger" label="Overdue" /> : null}
            {card.actingFor ? <Badge tone="info" label={`Acting for ${card.actingFor}`} /> : null}
          </View>
          <Text testID="detail-title" weight="700" size={20}>{card.title}</Text>
          {card.subtitle ? <Text muted>{card.subtitle}</Text> : null}
          {card.requester ? <Text size={14}>Requested by {card.requester}</Text> : null}
          <Text size={14}>Submitted {fmtUtcDate(card.createdAt)}</Text>
          {card.dueAt ? <Text size={14}>Due {fmtUtcDate(card.dueAt)} {fmtUtcTime(card.dueAt)}</Text> : null}
          {card.amountPaise != null ? <Text size={14} weight="600">Amount {fmtInr(card.amountPaise)}</Text> : null}
          {card.meta ? <Text size={14}>{card.meta}</Text> : null}
        </Card>
        {card.steps?.length ? (
          <Card style={{ gap: 4 }}>
            <Text weight="600">Steps</Text>
            {card.steps.map((s) => (
              <Text key={s.step_number} size={14} muted>Step {s.step_number}: {s.status}</Text>
            ))}
          </Card>
        ) : null}
        <TextInput label="Comment (optional)" value={comment} onChangeText={setComment} multiline placeholder="Add a note the requester will see" />
        {error ? <Text testID="detail-error" accessibilityRole="alert" style={{ color: colors.danger }}>{error}</Text> : null}
        {confirming ? (
          <Card style={{ gap: 8 }}>
            <Text testID="reject-confirm-text" weight="600">Reject this request?</Text>
            <Button testID="reject-confirm" title="Confirm reject" loading={act.isPending} onPress={() => void run('reject')} />
            <Button testID="reject-cancel" variant="secondary" title="Cancel" onPress={() => setConfirming(false)} />
          </Card>
        ) : (
          <View style={{ gap: 8 }}>
            <Button testID="approve" title="Approve" loading={act.isPending} onPress={() => void run('approve')} />
            <Button testID="reject" variant="secondary" title="Reject" disabled={act.isPending} onPress={() => setConfirming(true)} />
          </View>
        )}
      </View>
    </Screen>
  );
}
