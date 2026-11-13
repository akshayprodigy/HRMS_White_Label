import { useState } from 'react';
import { View } from 'react-native';
import { Badge } from '../approvals/ApprovalsScreen';
import { Button, Text } from '../../components/ui';
import { useTheme } from '../../theme';
import { STATUS_LABEL } from './api';

const NEG = new Set(['rejected', 'declined', 'expired']);
export function StatusBadge({ status, testID }: { status: string; testID?: string }) {
  return <Badge testID={testID} tone={NEG.has(status) ? 'danger' : 'info'} label={STATUS_LABEL(status)} />;
}

/** Two-step destructive/irreversible action (no native confirm dialogs: they are not testable on every platform). */
export function ConfirmAction({ id, label, confirmLabel, prompt, busy, onConfirm }: { id: string; label: string; confirmLabel?: string; prompt: string; busy?: boolean; onConfirm: () => void }) {
  const [open, setOpen] = useState(false);
  if (!open) return <Button testID={`${id}`} variant="secondary" title={label} disabled={busy} onPress={() => setOpen(true)} />;
  return (
    <View style={{ gap: 8 }}>
      <Text testID={`${id}-prompt`}>{prompt}</Text>
      <Button testID={`${id}-confirm`} title={confirmLabel ?? label} loading={busy} onPress={() => { setOpen(false); onConfirm(); }} />
      <Button testID={`${id}-keep`} variant="secondary" title="Keep it" onPress={() => setOpen(false)} />
    </View>
  );
}

export function ErrorText({ testID, children }: { testID?: string; children: React.ReactNode }) {
  const { colors } = useTheme();
  return <Text testID={testID} accessibilityRole="alert" size={13} style={{ color: colors.danger }}>{children}</Text>;
}
