import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { View } from 'react-native';
import { normalizeError } from '../../api/client';
import { Card, Chip, Text } from '../../components/ui';
import { fmtUtcTime } from '../../lib/time';
import { useTheme } from '../../theme';
import { fetchMyTrail } from './api';
import { FieldMap } from './FieldMap';
import { utcDay } from './fieldFormat';
import { mapsAvailable } from './maps';

/** The employee's own trail (Today / Yesterday): a map polyline when maps are available, else a time-ordered list. */
export function MyHistory() {
  const { colors } = useTheme();
  const [dayOffset, setDayOffset] = useState(0);
  const [openedAt] = useState(() => Date.now());
  const date = utcDay(openedAt, dayOffset);
  const q = useQuery({ queryKey: ['tracking', 'my-trail', date], queryFn: () => fetchMyTrail(date), retry: 1 });
  const pts = q.data && q.data.date === date ? q.data.points : null;
  return (
    <Card style={{ gap: 8 }} testID="my-history">
      <Text weight="600">My location history</Text>
      <View style={{ flexDirection: 'row', gap: 8 }}>
        <Chip testID="history-today" label="Today" selected={dayOffset === 0} onPress={() => setDayOffset(0)} />
        <Chip testID="history-yesterday" label="Yesterday" selected={dayOffset === 1} onPress={() => setDayOffset(1)} />
      </View>
      {q.isPending ? <Text muted testID="history-loading">Loading…</Text> : null}
      {q.error ? <Text testID="history-error" accessibilityRole="alert" style={{ color: colors.danger }}>{normalizeError(q.error).message}</Text> : null}
      {pts && pts.length === 0 ? <Text muted testID="history-empty">No location points recorded on {date}.</Text> : null}
      {pts && pts.length > 0 ? (
        <>
          <Text muted testID="history-summary">{pts.length} point{pts.length === 1 ? '' : 's'}{q.data!.truncated ? ' (first points only)' : ''}</Text>
          {mapsAvailable() ? (
            <FieldMap rows={[]} selected={null} trail={pts} onSelect={() => undefined} />
          ) : (
            <View testID="history-list" style={{ gap: 2 }}>
              {pts.map((p) => (
                <Text key={p.captured_at} size={13}>{fmtUtcTime(p.captured_at)} · {p.lat.toFixed(5)}, {p.lng.toFixed(5)}</Text>
              ))}
            </View>
          )}
        </>
      ) : null}
    </Card>
  );
}
