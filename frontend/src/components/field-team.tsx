import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { MapContainer, TileLayer, CircleMarker, Popup, Polyline, useMap } from 'react-leaflet';
import type { LatLngBoundsExpression } from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { MapPin, RefreshCw, ShieldCheck } from 'lucide-react';
import { Card, Button, Badge } from './ui-elements';
import { useVisiblePoll } from '../hooks/use-visible-poll';
import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';
import { errMsg, parseServerDate, todayIso } from './schedule-delegations-utils';

type Status =
  | 'off' | 'on_leave' | 'upcoming' | 'not_arrived' | 'no_show'
  | 'running_late' | 'on_shift' | 'completed' | 'remote';

interface Ping {
  captured_at: string;
  lat: number;
  lng: number;
  accuracy: number | null;
  speed: number | null;
  battery: number | null;
}

interface FieldRow {
  user_id: number;
  name: string;
  department: string | null;
  status: Status;
  late_minutes: number;
  shift_name: string | null;
  start_hhmm: string | null;
  end_hhmm: string | null;
  ping: Ping | null;
}

interface FieldNow {
  now: string;
  tracked: number;
  with_location: number;
  rows: FieldRow[];
}

interface Trail {
  user_id: number;
  date: string;
  points: Ping[];
  truncated: boolean;
}

const STATUS_META: Record<
  Status,
  { label: string; color: string; variant: 'success' | 'warning' | 'error' | 'info' | 'neutral' }
> = {
  no_show: { label: 'No-show', color: '#DC2626', variant: 'error' },
  running_late: { label: 'Running late', color: '#2563EB', variant: 'info' },
  not_arrived: { label: 'Not arrived', color: '#D97706', variant: 'warning' },
  on_shift: { label: 'On shift', color: '#16A34A', variant: 'success' },
  upcoming: { label: 'Upcoming', color: '#2563EB', variant: 'info' },
  completed: { label: 'Completed', color: '#64748B', variant: 'neutral' },
  on_leave: { label: 'On leave', color: '#64748B', variant: 'neutral' },
  remote: { label: 'Remote', color: '#0891B2', variant: 'info' },
  off: { label: 'Off', color: '#64748B', variant: 'neutral' },
};

/** Unknown status strings from a newer server must never crash the map. */
const metaFor = (s: string) => STATUS_META[s as Status] ?? STATUS_META.off;

const REFRESH_MS = 60_000;
// OpenStreetMap's public tile servers are for light use only
// (https://operations.osmfoundation.org/policies/tiles/). Production should
// point VITE_MAP_TILE_URL (and VITE_MAP_ATTRIBUTION) at a tile provider with an
// API key / suitable usage policy, e.g. https://tiles.example.com/{z}/{x}/{y}.png?key=...
const TILE_URL: string =
  (import.meta as any).env?.VITE_MAP_TILE_URL || 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';
const TILE_ATTRIBUTION: string =
  (import.meta as any).env?.VITE_MAP_ATTRIBUTION ||
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';
const DEFAULT_CENTER: [number, number] = [20.5937, 78.9629];

export const lastSeen = (iso: string, now: Date = new Date()): string => {
  const mins = Math.max(0, Math.round((now.getTime() - parseServerDate(iso).getTime()) / 60_000));
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins} min ago`;
  const h = Math.floor(mins / 60);
  return `${h} h ${mins % 60} min ago`;
};

const hhmmUtc = (iso: string) => parseServerDate(iso).toISOString().slice(11, 16);

const shiftText = (r: FieldRow) =>
  r.shift_name ? `${r.shift_name} ${r.start_hhmm ?? ''}–${r.end_hhmm ?? ''} UTC` : 'No shift today';

const FitBounds: React.FC<{ bounds: LatLngBoundsExpression | null; token: string }> = ({ bounds, token }) => {
  const map = useMap();
  useEffect(() => {
    if (bounds) {
      map.closePopup();
      map.fitBounds(bounds, { padding: [40, 40], maxZoom: 16, animate: false });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, map]);
  return null;
};

export const FieldTeam: React.FC = () => {
  const [data, setData] = useState<FieldNow | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [noScope, setNoScope] = useState(false);
  const [updated, setUpdated] = useState<Date | null>(null);
  const [department, setDepartment] = useState('');
  const [deptOpts, setDeptOpts] = useState<string[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const [date, setDate] = useState(todayIso());
  const [trail, setTrail] = useState<Trail | null>(null);
  const [trailErr, setTrailErr] = useState<string | null>(null);
  const [trailLoading, setTrailLoading] = useState(false);
  const reqRef = useRef(0);
  const trailReq = useRef(0);

  const load = useCallback(
    async (background: boolean) => {
      const reqId = ++reqRef.current;
      if (background) setRefreshing(true);
      else setLoading(true);
      try {
        const qs = department ? `?department=${encodeURIComponent(department)}` : '';
        const res = await client.get<FieldNow>(ENDPOINTS.TRACKING.FIELD_NOW + qs);
        if (reqId !== reqRef.current) return;
        setData(res.data);
        setUpdated(new Date());
        setError(null);
        setNoScope(false);
        if (!department) {
          setDeptOpts(
            Array.from(new Set(res.data.rows.map((r) => r.department).filter((d): d is string => !!d))).sort()
          );
        }
      } catch (err: any) {
        if (reqId !== reqRef.current) return;
        if (err?.response?.status === 403) {
          setNoScope(true);
          setError(null);
        } else {
          setError(errMsg(err, 'Failed to load the field team'));
        }
        if (!background) setData(null);
      } finally {
        if (reqId === reqRef.current) {
          setLoading(false);
          setRefreshing(false);
        }
      }
    },
    [department]
  );

  const loadedFor = useRef<typeof load | null>(null);
  const poll = useCallback(() => {
    const background = loadedFor.current === load;
    loadedFor.current = load;
    return load(background);
  }, [load]);
  useVisiblePoll(poll, REFRESH_MS);

  // Trail: fetched once per (employee, date) and re-polled only for today.
  const trailKey = useRef<string | null>(null);
  const loadTrail = useCallback(async () => {
    const id = ++trailReq.current; // also invalidates any in-flight response
    if (selected == null) {
      trailKey.current = null;
      setTrail(null);
      setTrailErr(null);
      setTrailLoading(false);
      return;
    }
    const key = `${selected}|${date}`;
    const changed = trailKey.current !== key;
    if (!changed && date !== todayIso()) return; // a past day will not change
    if (changed) {
      trailKey.current = key;
      setTrail(null);
      setTrailErr(null);
      setTrailLoading(true);
    }
    try {
      const res = await client.get<Trail>(
        `${ENDPOINTS.TRACKING.TRAIL}?user_id=${selected}&date=${date}`
      );
      if (id !== trailReq.current) return;
      setTrail(res.data);
      setTrailErr(null);
    } catch (err: any) {
      if (id !== trailReq.current) return;
      if (changed) setTrail(null);
      setTrailErr(errMsg(err, 'Could not load the trail'));
    } finally {
      if (id === trailReq.current) setTrailLoading(false);
    }
  }, [selected, date]);
  useVisiblePoll(loadTrail, REFRESH_MS);

  const rows = useMemo(
    () =>
      [...(data?.rows ?? [])].sort(
        (a, b) => Number(!!b.ping) - Number(!!a.ping) || a.name.localeCompare(b.name)
      ),
    [data]
  );
  const located = rows.filter((r) => r.ping);
  const selectedRow = rows.find((r) => r.user_id === selected) ?? null;
  // Only ever draw a trail that belongs to the current selection + date.
  const trailOk = !!trail && selected != null && trail.user_id === selected && trail.date === date;
  const trailPts: [number, number][] = trailOk ? trail!.points.map((p) => [p.lat, p.lng]) : [];

  const bounds: LatLngBoundsExpression | null = useMemo(() => {
    const pts: [number, number][] = trailPts.length
      ? trailPts
      : located.map((r) => [r.ping!.lat, r.ping!.lng] as [number, number]);
    return pts.length ? pts : null;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [trail, trailOk, data]);
  // Re-fit only when the set of things shown changes, not on every poll.
  const fitToken = `${selected ?? ''}|${date}|${department}|${trailOk ? trail!.user_id : ''}|${
    trailOk ? trail!.points.length : ''
  }|${selected == null ? located.length : ''}`;

  const pick = (id: number) => setSelected((cur) => (cur === id ? null : id));
  const mapShown = !!data && (data.tracked > 0 || !!department);

  const selectCls =
    'h-9 px-2 border border-gray-200 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500';

  if (noScope) {
    return (
      <div className="p-8">
        <Card className="p-8 text-center text-sm text-gray-600" role="alert">
          You don't have a team scope.
        </Card>
      </div>
    );
  }

  return (
    <div className="p-8 space-y-5">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2">
          <MapPin className="w-5 h-5 text-indigo-600" />
          <div>
            <h2 className="text-lg font-semibold text-gray-900">Field Team</h2>
            <p className="text-sm text-gray-500 mt-0.5">
              Latest location of tracked employees on shift. Shift times shown in UTC.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3 flex-wrap">
          <select
            aria-label="Department"
            className={selectCls}
            value={department}
            onChange={(e) => {
              setDepartment(e.target.value);
              setSelected(null);
            }}
          >
            <option value="">All departments</option>
            {deptOpts.map((d) => (
              <option key={d} value={d}>{d}</option>
            ))}
          </select>
          <span className="text-xs text-gray-500" aria-live="polite">
            {updated ? `Updated ${updated.toISOString().slice(11, 19)} UTC` : ''}
          </span>
          <Button variant="outline" size="sm" onClick={() => load(true)} disabled={loading || refreshing}>
            <RefreshCw className={`w-4 h-4 mr-1 ${refreshing ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
        </div>
      </div>

      <p className="flex items-center gap-2 text-xs text-gray-500">
        <ShieldCheck className="w-4 h-4 text-green-600 shrink-0" />
        Location is shared only during rostered shifts by employees who consented. Views of locations are audit-logged.
      </p>

      {error && (
        <div role="alert" className="p-3 rounded-lg bg-red-50 text-sm text-red-700">{error}</div>
      )}

      {loading && !data ? (
        <p className="py-12 text-center text-sm text-gray-500">Loading field team…</p>
      ) : data && !mapShown ? (
        <Card className="p-10 text-center">
          <p className="text-sm font-medium text-gray-800">No one is being tracked</p>
          <p className="text-sm text-gray-500 mt-1">
            Tracking is off by default; HR can enable it per role in Tracking settings
            (Attendance Control → Workforce Activity → Time Rules tab).
          </p>
        </Card>
      ) : data ? (
        <>
          <div className="flex gap-3 flex-wrap">
            {data.tracked === 0 && (
              <Card className="px-4 py-2 text-sm text-gray-600">
                No tracked employees in this department.
              </Card>
            )}
            <Card className="px-4 py-2 text-sm">
              <span className="text-gray-500">Tracked</span>{' '}
              <span className="font-semibold text-gray-900">{data.tracked}</span>
            </Card>
            <Card className="px-4 py-2 text-sm">
              <span className="text-gray-500">With recent location</span>{' '}
              <span className="font-semibold text-gray-900">{data.with_location}</span>
            </Card>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            <Card className="lg:col-span-2 p-0">
              <div
                style={{ height: 520, position: 'relative' }}
                data-testid="field-map"
                role="region"
                aria-label="Map of tracked employees' latest locations"
              >
                {(loading || refreshing) && (
                  <div
                    className="absolute top-2 right-2 text-xs bg-white rounded px-2 py-1 shadow"
                    style={{ zIndex: 1000 }}
                    role="status"
                  >
                    Updating…
                  </div>
                )}
                <MapContainer
                  center={DEFAULT_CENTER}
                  zoom={4}
                  scrollWheelZoom
                  style={{ height: '100%', width: '100%' }}
                >
                  <TileLayer
                    attribution={TILE_ATTRIBUTION}
                    url={TILE_URL}
                  />
                  <FitBounds bounds={bounds} token={fitToken} />
                  {trailPts.length > 1 && (
                    <Polyline positions={trailPts} pathOptions={{ color: '#4F46E5', weight: 4, opacity: 0.8 }} />
                  )}
                  {trailPts.length >= 1 && (
                    <CircleMarker
                      center={trailPts[0]}
                      radius={5}
                      pathOptions={{ color: '#FFFFFF', weight: 2, fillColor: '#4F46E5', fillOpacity: 1 }}
                    >
                      <Popup>Trail start {hhmmUtc(trail!.points[0].captured_at)} UTC</Popup>
                    </CircleMarker>
                  )}
                  {located.map((r) => (
                    <CircleMarker
                      key={r.user_id}
                      center={[r.ping!.lat, r.ping!.lng]}
                      radius={r.user_id === selected ? 12 : 9}
                      pathOptions={{
                        color: r.user_id === selected ? '#111827' : '#FFFFFF',
                        weight: 2,
                        fillColor: metaFor(r.status).color,
                        fillOpacity: 0.95,
                      }}
                      eventHandlers={{ click: () => setSelected(r.user_id) }}
                    >
                      <Popup>
                        <div className="text-sm">
                          <div className="font-semibold">{r.name}</div>
                          <div>{metaFor(r.status).label} · {shiftText(r)}</div>
                          <div>
                            Last seen {lastSeen(r.ping!.captured_at)}
                            {r.ping!.battery != null ? ` · battery ${Math.round(r.ping!.battery)}%` : ''}
                          </div>
                        </div>
                      </Popup>
                    </CircleMarker>
                  ))}
                </MapContainer>
              </div>
            </Card>

            <Card className="p-0 flex flex-col" style={{ maxHeight: 520 }}>
              <ul className="divide-y divide-gray-100 overflow-y-auto" aria-label="Tracked employees">
                {rows.map((r) => {
                  const m = metaFor(r.status);
                  return (
                    <li key={r.user_id}>
                      <button
                        type="button"
                        onClick={() => pick(r.user_id)}
                        aria-pressed={r.user_id === selected}
                        className={`w-full text-left px-4 py-3 hover:bg-gray-50 ${
                          r.user_id === selected ? 'bg-indigo-50' : ''
                        }`}
                      >
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-sm font-medium text-gray-900">{r.name}</span>
                          <Badge variant={m.variant}>{m.label}</Badge>
                        </div>
                        <div className="text-xs text-gray-500 mt-0.5">
                          {[r.department, shiftText(r)].filter(Boolean).join(' · ')}
                        </div>
                        <div className="text-xs mt-0.5 text-gray-600">
                          {r.ping
                            ? `Last seen ${lastSeen(r.ping.captured_at)}${
                                r.ping.battery != null ? ` · ${Math.round(r.ping.battery)}% battery` : ''
                              }`
                            : 'No recent location'}
                        </div>
                      </button>
                    </li>
                  );
                })}
              </ul>
            </Card>
          </div>

          {selectedRow && (
            <Card className="p-4 space-y-2">
              <div className="flex items-center gap-3 flex-wrap">
                <h3 className="text-sm font-semibold text-gray-900">Trail: {selectedRow.name}</h3>
                <input
                  type="date"
                  aria-label="Trail date"
                  className={selectCls}
                  value={date}
                  max={todayIso()}
                  onChange={(e) => e.target.value && setDate(e.target.value)}
                />
                <Button variant="outline" size="sm" onClick={() => setSelected(null)}>
                  Clear
                </Button>
              </div>
              <div aria-live="polite">
              {trailLoading && !trailOk ? (
                <p className="text-sm text-gray-500">Loading trail…</p>
              ) : trailErr ? (
                <p role="alert" className="text-sm text-red-700">{trailErr}</p>
              ) : trailOk && trail!.points.length === 0 ? (
                <p className="text-sm text-gray-500">No location points recorded on {trail!.date}.</p>
              ) : trailOk ? (
                <p className="text-sm text-gray-600">
                  {trail!.points.length} point{trail!.points.length === 1 ? '' : 's'} from{' '}
                  {hhmmUtc(trail!.points[0].captured_at)} to{' '}
                  {hhmmUtc(trail!.points[trail!.points.length - 1].captured_at)} UTC
                  {trail!.truncated ? ' (showing the first points only — trail truncated)' : ''}
                </p>
              ) : null}
              </div>
            </Card>
          )}
        </>
      ) : null}
    </div>
  );
};
