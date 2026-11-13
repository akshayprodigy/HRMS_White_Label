import { Modal, ScrollView, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Text } from '../../components/ui';
import { useTheme } from '../../theme';
import { isCritical } from './api';
import { BroadcastResponse } from './BroadcastResponse';
import { useMyBroadcasts } from './hooks';

/**
 * Full-screen emergency modal for the newest unresolved CRITICAL broadcast. It cannot be dismissed
 * (Android back is swallowed, no close button) until the required response is sent. Mounted at the root.
 */
export function BroadcastModal() {
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const q = useMyBroadcasts();
  const pending = (q.data ?? []).filter((b) => b.pending && isCritical(b));
  const current = pending[0];
  if (!current) return null;
  return (
    <Modal visible transparent={false} animationType="fade" presentationStyle="fullScreen" statusBarTranslucent onRequestClose={() => undefined}>
      <View testID="broadcast-modal" style={{ flex: 1, backgroundColor: colors.background, paddingTop: insets.top + 16, paddingBottom: insets.bottom + 16, paddingHorizontal: 20 }}>
        <ScrollView contentContainerStyle={{ gap: 14, flexGrow: 1, justifyContent: 'center' }} keyboardShouldPersistTaps="handled">
          <Text weight="700" size={13} style={{ color: colors.danger }} accessibilityRole="header">EMERGENCY ALERT</Text>
          <Text testID="broadcast-modal-title" weight="700" size={26}>{current.title}</Text>
          <Text testID="broadcast-modal-message" size={18}>{current.message}</Text>
          {pending.length > 1 ? <Text muted size={13}>{pending.length - 1} more alert{pending.length > 2 ? 's' : ''} after this one</Text> : null}
          <BroadcastResponse key={current.id} broadcast={current} />
        </ScrollView>
      </View>
    </Modal>
  );
}
