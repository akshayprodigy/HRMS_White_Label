import { Card, Text } from '../../components/ui';
import type { MyBroadcast } from '../../api/types';
import { useTheme } from '../../theme';
import { BroadcastResponse } from './BroadcastResponse';

/** Home banner for non-critical pending broadcasts (critical ones are handled by the root modal). */
export function BroadcastBanner({ broadcasts }: { broadcasts: MyBroadcast[] }) {
  const { colors } = useTheme();
  const b = broadcasts[0];
  if (!b) return null;
  return (
    <Card testID="broadcast-banner" style={{ borderColor: b.severity === 'critical' ? colors.danger : colors.primary, gap: 8 }}>
      <Text weight="700">{b.title}</Text>
      <Text size={14} numberOfLines={3}>{b.message}</Text>
      {broadcasts.length > 1 ? <Text muted size={12}>+{broadcasts.length - 1} more</Text> : null}
      <BroadcastResponse key={b.id} broadcast={b} />
    </Card>
  );
}
