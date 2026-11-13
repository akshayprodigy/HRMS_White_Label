import { useEffect, useMemo, useRef } from 'react';
import MapView, { Marker, Polyline } from 'react-native-maps';
import type { FieldPing, FieldRow } from './api';
import { STATUS_META } from './fieldFormat';

type Props = { rows: FieldRow[]; selected: number | null; trail: FieldPing[]; onSelect: (id: number) => void };

export function FieldMap({ rows, selected, trail, onSelect }: Props) {
  const ref = useRef<MapView>(null);
  const located = useMemo(() => rows.filter((r) => r.ping), [rows]);
  const points = trail.length ? trail : located.map((r) => r.ping!);
  // Re-fit only when the set of things shown changes, not on every 60 s poll.
  const token = `${selected ?? ''}|${trail.length}|${selected == null ? located.length : ''}`;
  useEffect(() => {
    if (!points.length) return;
    ref.current?.fitToCoordinates(points.map((p) => ({ latitude: p.lat, longitude: p.lng })), { edgePadding: { top: 48, right: 48, bottom: 48, left: 48 }, animated: false });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);
  return (
    <MapView ref={ref} testID="field-map" style={{ height: 320, borderRadius: 12 }} initialRegion={{ latitude: 20.5937, longitude: 78.9629, latitudeDelta: 25, longitudeDelta: 25 }}>
      {trail.length > 1 ? <Polyline coordinates={trail.map((p) => ({ latitude: p.lat, longitude: p.lng }))} strokeColor="#4F46E5" strokeWidth={4} /> : null}
      {located.map((r) => (
        <Marker
          key={r.user_id}
          testID={`field-marker-${r.user_id}`}
          coordinate={{ latitude: r.ping!.lat, longitude: r.ping!.lng }}
          title={r.name}
          description={STATUS_META[r.status].label}
          pinColor={STATUS_META[r.status].color}
          opacity={selected == null || selected === r.user_id ? 1 : 0.5}
          onPress={() => onSelect(r.user_id)}
        />
      ))}
    </MapView>
  );
}
