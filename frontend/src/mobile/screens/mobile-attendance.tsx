import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  MapPin,
  CheckCircle2,
  AlertCircle,
  Loader2,
  Ban,
  Moon,
  LogIn,
  LogOut,
  RadioTower,
} from 'lucide-react';
import { toast } from 'sonner';
import { client } from '../../api/client';
import { ENDPOINTS } from '../../api/endpoints';
import { cn, errMsg } from '../../components/ui-elements';

// ---- Types ------------------------------------------------------------

interface Fence {
  id: number;
  name: string;
  latitude: number;
  longitude: number;
  radius_meters: number;
  is_active: boolean;
}

interface EffectiveGeo {
  geo_enabled: boolean;
  enforcement_mode: 'strict' | 'allow_with_flag' | null;
  fences: Fence[];
}

interface AttendanceRow {
  id: number;
  captured_at: string;
  punch_out_time: string | null;
  work_date: string | null;
  is_cross_midnight: boolean;
  matched_fence_id: number | null;
  geo_flag: string | null;
  punch_out_geo_flag: string | null;
  mode: string;
}

type PermissionState = 'idle' | 'requesting' | 'granted' | 'denied' | 'unavailable';

interface Position {
  lat: number;
  lng: number;
  accuracy: number;
}

type PunchMode = 'office' | 'wfh' | 'onsite' | 'others';

interface MobileAttendanceProps {
  hasMarkedAttendance: boolean;
  hasPunchedOut: boolean;
  onAttendanceSuccess: () => void;
  onPunchedOut: () => void;
}

// ---- Pure helpers -----------------------------------------------------

// Haversine distance in meters. Exported for possible tests; the same
// formula runs server-side (backend/app/services/geofence.py).
export function haversineMeters(
  a: { lat: number; lng: number },
  b: { lat: number; lng: number }
): number {
  const R = 6371000;
  const toRad = (d: number) => (d * Math.PI) / 180;
  const dLat = toRad(b.lat - a.lat);
  const dLng = toRad(b.lng - a.lng);
  const lat1 = toRad(a.lat);
  const lat2 = toRad(b.lat);
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLng / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
}

interface NearestResult {
  fence: Fence | null;
  distance_m: number;
  inside: boolean;
}

export function nearestFence(pos: Position, fences: Fence[]): NearestResult {
  const active = fences.filter((f) => f.is_active);
  if (active.length === 0) {
    return { fence: null, distance_m: Number.POSITIVE_INFINITY, inside: false };
  }
  let best: Fence = active[0];
  let bestD = haversineMeters(pos, {
    lat: best.latitude,
    lng: best.longitude,
  });
  for (const f of active.slice(1)) {
    const d = haversineMeters(pos, { lat: f.latitude, lng: f.longitude });
    if (d < bestD) {
      best = f;
      bestD = d;
    }
  }
  return { fence: best, distance_m: bestD, inside: bestD <= best.radius_meters };
}

function fmtDistance(m: number): string {
  if (!Number.isFinite(m)) return '—';
  if (m < 1000) return `${Math.round(m)} m`;
  return `${(m / 1000).toFixed(m < 10000 ? 2 : 1)} km`;
}

function fmtTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleTimeString('en-IN', {
      hour: '2-digit',
      minute: '2-digit',
      hour12: true,
    });
  } catch {
    return '—';
  }
}

function fmtElapsed(fromIso: string, toIso: string | null): string {
  const from = new Date(fromIso).getTime();
  const to = (toIso ? new Date(toIso) : new Date()).getTime();
  let ms = Math.max(0, to - from);
  const hrs = Math.floor(ms / 3600000);
  ms -= hrs * 3600000;
  const mins = Math.floor(ms / 60000);
  return `${hrs}h ${mins}m`;
}

// ---- Screen -----------------------------------------------------------

export const MobileAttendance: React.FC<MobileAttendanceProps> = ({
  hasMarkedAttendance,
  hasPunchedOut,
  onAttendanceSuccess,
  onPunchedOut,
}) => {
  const [permission, setPermission] = useState<PermissionState>('idle');
  const [position, setPosition] = useState<Position | null>(null);
  const [effective, setEffective] = useState<EffectiveGeo | null>(null);
  const [today, setToday] = useState<AttendanceRow | null>(null);
  const [mode, setMode] = useState<PunchMode>('office');
  const [remarks, setRemarks] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0); // 1Hz clock for elapsed
  const watchIdRef = useRef<number | null>(null);

  useEffect(() => {
    // Kick off in parallel: effective config + today's row.
    void refreshServerState();
    startWatching();
    const clock = setInterval(() => setTick((t) => t + 1), 1000);
    return () => {
      if (watchIdRef.current !== null && 'geolocation' in navigator) {
        navigator.geolocation.clearWatch(watchIdRef.current);
      }
      clearInterval(clock);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const refreshServerState = async () => {
    try {
      const [eff, td] = await Promise.all([
        client.get<EffectiveGeo>(ENDPOINTS.GEO.MY_EFFECTIVE),
        client.get(ENDPOINTS.ATTENDANCE.TODAY),
      ]);
      setEffective(eff.data);
      setToday(td.data?.attendance ?? null);
    } catch (e: any) {
      // Non-fatal: user can still see permission UI.
      console.warn('attendance refresh failed', e);
    }
  };

  const startWatching = () => {
    if (!('geolocation' in navigator)) {
      setPermission('unavailable');
      return;
    }
    setPermission('requesting');
    const options: PositionOptions = {
      enableHighAccuracy: true,
      timeout: 10000,
      maximumAge: 0,
    };
    watchIdRef.current = navigator.geolocation.watchPosition(
      (p) => {
        setPermission('granted');
        setPosition({
          lat: p.coords.latitude,
          lng: p.coords.longitude,
          accuracy: p.coords.accuracy,
        });
      },
      (err) => {
        console.warn('geolocation error', err);
        if (err.code === err.PERMISSION_DENIED) {
          setPermission('denied');
        } else if (permission === 'requesting') {
          // Retry-friendly state — the watchPosition will keep trying.
          setPermission('requesting');
        }
      },
      options
    );
  };

  const near = useMemo(() => {
    if (!position || !effective) return null;
    if (!effective.geo_enabled || effective.fences.length === 0) return null;
    return nearestFence(position, effective.fences);
  }, [position, effective]);

  // Client-side gate: server is truth. This is UX only. `null` here
  // means "no fences to check against" (geo_enabled=false or no fences
  // assigned) — in that case the button is not gated by geo at all.
  const clientAllowed = useMemo(() => {
    if (!effective) return false; // haven't loaded yet
    if (!effective.geo_enabled) return true; // policy off
    if (effective.fences.length === 0) return true; // no fences → no gate
    if (!position) return false; // waiting on GPS
    if (effective.enforcement_mode === 'allow_with_flag') return true;
    return !!near?.inside;
  }, [effective, position, near]);

  const isPunchedIn = !!today && !today.punch_out_time;
  const isPunchedOut = !!today && !!today.punch_out_time;

  const canPunchIn = !hasMarkedAttendance && !today;
  const canPunchOut = isPunchedIn && !hasPunchedOut;

  const submit = async (kind: 'in' | 'out') => {
    setError(null);
    if (mode === 'others' && !remarks.trim() && kind === 'in') {
      setError('Remarks are required for "Others" mode.');
      return;
    }
    if (!position && effective?.geo_enabled) {
      setError('Waiting for GPS. Make sure Location is on for this site.');
      return;
    }
    setSubmitting(true);
    try {
      const payload: Record<string, any> = {
        latitude: position?.lat,
        longitude: position?.lng,
        accuracy: position?.accuracy,
        // A PWA in the mobile browser cannot detect OS-level mock GPS.
        // We ALWAYS send false and keep the field wired so a future
        // native wrapper (React Native / Capacitor / Cordova) can set
        // it correctly without backend changes.
        is_mock_location: false,
      };
      if (kind === 'in') {
        payload.mode = mode;
        payload.remarks = remarks || (mode === 'others' ? 'Other location' : '');
        payload.captured_at = new Date().toISOString();
        await client.post(ENDPOINTS.ATTENDANCE.MARK, payload);
        toast.success('Punched in.');
        onAttendanceSuccess();
      } else {
        await client.post(ENDPOINTS.ATTENDANCE.PUNCH_OUT, payload);
        toast.success('Punched out.');
        onPunchedOut();
      }
      await refreshServerState();
    } catch (err: any) {
      // STRICT geo rejection: 422 with structured detail.
      const status = err?.response?.status;
      const detail = err?.response?.data?.detail;
      if (status === 422 && detail && typeof detail === 'object') {
        const msg =
          detail.message ||
          (detail.nearest_fence_name && detail.distance_to_fence_meters != null
            ? `You're ${Math.round(detail.distance_to_fence_meters)}m from ${detail.nearest_fence_name}. Move closer to punch.`
            : 'Punch rejected by geo policy.');
        setError(msg);
      } else {
        setError(errMsg(err, 'Punch failed. Please try again.'));
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="p-4 space-y-4">
      <TodayCard today={today} tick={tick} />

      <GpsCard
        permission={permission}
        position={position}
        onRetry={startWatching}
      />

      <FenceCard effective={effective} near={near} position={position} />

      {(canPunchIn || (!isPunchedIn && !isPunchedOut)) && (
        <ModeSelector
          mode={mode}
          setMode={setMode}
          remarks={remarks}
          setRemarks={setRemarks}
          disabled={isPunchedIn || isPunchedOut}
        />
      )}

      {error && <ErrorBanner text={error} />}

      <div className="space-y-3">
        {!isPunchedOut && canPunchIn && (
          <PunchButton
            label="Punch In"
            icon={LogIn}
            disabled={!clientAllowed || submitting || permission === 'denied'}
            loading={submitting}
            onClick={() => submit('in')}
            variant="primary"
          />
        )}
        {!isPunchedOut && canPunchOut && (
          <PunchButton
            label="Punch Out"
            icon={LogOut}
            disabled={!clientAllowed || submitting}
            loading={submitting}
            onClick={() => submit('out')}
            variant="danger"
          />
        )}
        {isPunchedOut && (
          <div className="p-4 rounded-2xl bg-emerald-50 border border-emerald-200 text-emerald-800 text-sm font-semibold text-center">
            You've punched in and out for this shift. See you tomorrow.
          </div>
        )}
      </div>
    </div>
  );
};

// ---- Sub-cards --------------------------------------------------------

const TodayCard: React.FC<{ today: AttendanceRow | null; tick: number }> = ({
  today,
  tick,
}) => {
  // Include tick in the closure so elapsed re-renders every second.
  void tick;
  if (!today) {
    return (
      <div className="rounded-2xl bg-white border border-slate-200 p-5">
        <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400 mb-1">
          Today
        </p>
        <p className="text-lg font-black text-[#0F172A]">Not punched in yet</p>
        <p className="text-sm text-slate-500 mt-1">
          Enable Location, choose a mode, and tap Punch In.
        </p>
      </div>
    );
  }
  const inTime = fmtTime(today.captured_at);
  const outTime = fmtTime(today.punch_out_time);
  const elapsed = fmtElapsed(today.captured_at, today.punch_out_time);
  const workDate = today.work_date
    ? new Date(today.work_date + 'T00:00:00').toLocaleDateString('en-IN', {
        day: '2-digit',
        month: 'short',
        year: 'numeric',
      })
    : null;
  return (
    <div className="rounded-2xl bg-white border border-slate-200 p-5">
      <div className="flex items-center justify-between">
        <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400">
          Today's shift
        </p>
        {today.is_cross_midnight && (
          <span className="inline-flex items-center gap-1 text-[10px] font-bold text-indigo-700 bg-indigo-50 border border-indigo-100 rounded-full px-2 py-0.5">
            <Moon size={11} /> Night shift
          </span>
        )}
      </div>
      {workDate && (
        <p className="text-[11px] text-slate-500 mt-1">
          Work-date <span className="font-semibold">{workDate}</span>
          {today.is_cross_midnight && ' · punch-out lands on next day'}
        </p>
      )}
      <div className="mt-3 grid grid-cols-3 gap-3">
        <Stat label="Punch in" value={inTime} tone="ok" />
        <Stat label="Elapsed" value={elapsed} tone="neutral" />
        <Stat
          label="Punch out"
          value={today.punch_out_time ? outTime : '—'}
          tone={today.punch_out_time ? 'ok' : 'muted'}
        />
      </div>
      <p className="text-[11px] text-slate-500 mt-3">
        Mode: <span className="font-semibold uppercase">{today.mode}</span>
        {today.geo_flag && (
          <span className="ml-2 text-amber-700">· in-flag {today.geo_flag}</span>
        )}
        {today.punch_out_geo_flag && (
          <span className="ml-2 text-amber-700">
            · out-flag {today.punch_out_geo_flag}
          </span>
        )}
      </p>
    </div>
  );
};

const Stat: React.FC<{
  label: string;
  value: string;
  tone: 'ok' | 'muted' | 'neutral';
}> = ({ label, value, tone }) => {
  const toneClass = {
    ok: 'text-emerald-700',
    muted: 'text-slate-400',
    neutral: 'text-[#0F172A]',
  }[tone];
  return (
    <div>
      <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400">
        {label}
      </p>
      <p className={cn('text-base font-black tabular-nums', toneClass)}>{value}</p>
    </div>
  );
};

const GpsCard: React.FC<{
  permission: PermissionState;
  position: Position | null;
  onRetry: () => void;
}> = ({ permission, position, onRetry }) => {
  if (permission === 'unavailable') {
    return (
      <Callout
        tone="error"
        icon={Ban}
        title="This device has no GPS"
        body="Punching requires a device with location services. Use a phone or laptop with GPS."
      />
    );
  }
  if (permission === 'denied') {
    return (
      <Callout
        tone="error"
        icon={Ban}
        title="Location permission denied"
        body="Punch needs your location. Open your browser's Site Settings → Location → Allow, then reload."
        action={
          <button
            type="button"
            onClick={onRetry}
            className="mt-3 text-sm font-bold text-red-700 underline"
          >
            I've enabled it — retry
          </button>
        }
      />
    );
  }
  if (permission === 'requesting' && !position) {
    return (
      <Callout
        tone="info"
        icon={RadioTower}
        title="Getting your location…"
        body="Keep the app open and stay still for a few seconds for a strong GPS signal."
        spin
      />
    );
  }
  return (
    <div className="rounded-2xl bg-white border border-slate-200 p-4 flex items-center gap-3">
      <div className="w-9 h-9 rounded-full bg-emerald-50 flex items-center justify-center text-emerald-700">
        <CheckCircle2 size={18} />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400">
          GPS signal
        </p>
        <p className="text-sm font-black text-[#0F172A] tabular-nums">
          Accuracy ±{position ? Math.round(position.accuracy) : '—'} m
        </p>
      </div>
    </div>
  );
};

const FenceCard: React.FC<{
  effective: EffectiveGeo | null;
  near: NearestResult | null;
  position: Position | null;
}> = ({ effective, near, position }) => {
  if (!effective) {
    return (
      <div className="rounded-2xl bg-white border border-slate-200 p-4 flex items-center gap-3">
        <Loader2 size={16} className="animate-spin text-slate-400" />
        <p className="text-sm text-slate-500">Loading your allowed sites…</p>
      </div>
    );
  }
  if (!effective.geo_enabled || effective.fences.length === 0) {
    return (
      <div className="rounded-2xl bg-white border border-slate-200 p-4">
        <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400 mb-1">
          Geo-fencing
        </p>
        <p className="text-sm font-black text-[#0F172A]">Not required</p>
        <p className="text-[12px] text-slate-500 mt-1">
          No fence assigned to you — punch from anywhere.
        </p>
      </div>
    );
  }
  if (!position || !near) {
    return (
      <div className="rounded-2xl bg-white border border-slate-200 p-4">
        <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400 mb-1">
          Nearest allowed site
        </p>
        <p className="text-sm font-black text-slate-500">Waiting for GPS…</p>
      </div>
    );
  }
  const inside = near.inside;
  const tone = inside ? 'emerald' : 'amber';
  return (
    <div
      className={cn(
        'rounded-2xl border p-4 flex items-center gap-3',
        inside
          ? 'bg-emerald-50 border-emerald-200'
          : 'bg-amber-50 border-amber-200'
      )}
    >
      <div
        className={cn(
          'w-9 h-9 rounded-full flex items-center justify-center',
          inside
            ? 'bg-emerald-600 text-white'
            : 'bg-amber-500 text-white'
        )}
      >
        <MapPin size={18} />
      </div>
      <div className="flex-1 min-w-0">
        <p
          className={cn(
            'text-[10px] font-bold uppercase tracking-widest',
            inside ? 'text-emerald-700' : 'text-amber-700'
          )}
        >
          {inside
            ? `Inside ${near.fence?.name}`
            : `Outside — nearest: ${near.fence?.name}`}
        </p>
        <p
          className={cn(
            'text-sm font-black tabular-nums',
            inside ? 'text-emerald-800' : 'text-amber-800'
          )}
        >
          {inside
            ? `Within ${near.fence?.radius_meters} m radius`
            : `${fmtDistance(near.distance_m)} away`}
        </p>
        {effective.enforcement_mode === 'allow_with_flag' && !inside && (
          <p className="text-[11px] text-amber-800 mt-1">
            Punch allowed — will be flagged for HR review.
          </p>
        )}
      </div>
      {tone === 'emerald' ? (
        <CheckCircle2 size={18} className="text-emerald-700" />
      ) : (
        <AlertCircle size={18} className="text-amber-700" />
      )}
    </div>
  );
};

const ModeSelector: React.FC<{
  mode: PunchMode;
  setMode: (m: PunchMode) => void;
  remarks: string;
  setRemarks: (v: string) => void;
  disabled?: boolean;
}> = ({ mode, setMode, remarks, setRemarks, disabled }) => {
  const OPTIONS: { id: PunchMode; label: string }[] = [
    { id: 'office', label: 'Office' },
    { id: 'wfh', label: 'WFH' },
    { id: 'onsite', label: 'On-site' },
    { id: 'others', label: 'Others' },
  ];
  return (
    <div className="rounded-2xl bg-white border border-slate-200 p-4">
      <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400 mb-2">
        Mode
      </p>
      <div className="grid grid-cols-4 gap-2">
        {OPTIONS.map((o) => {
          const active = mode === o.id;
          return (
            <button
              key={o.id}
              type="button"
              disabled={disabled}
              onClick={() => setMode(o.id)}
              className={cn(
                'h-10 rounded-xl text-[12px] font-bold border transition-colors',
                active
                  ? 'bg-[#2563EB] border-[#2563EB] text-white'
                  : 'bg-white border-slate-200 text-slate-700 active:bg-slate-50',
                disabled && 'opacity-50'
              )}
            >
              {o.label}
            </button>
          );
        })}
      </div>
      {mode === 'others' && (
        <div className="mt-3">
          <label
            htmlFor="mob-remarks"
            className="text-[10px] font-bold uppercase tracking-widest text-slate-400"
          >
            Remarks (required)
          </label>
          <input
            id="mob-remarks"
            type="text"
            value={remarks}
            onChange={(e) => setRemarks(e.target.value)}
            placeholder="e.g. Client site B — Ranchi"
            className="mt-1 w-full h-10 px-3 rounded-xl border border-slate-200 text-sm"
            disabled={disabled}
          />
        </div>
      )}
    </div>
  );
};

const PunchButton: React.FC<{
  label: string;
  icon: React.ComponentType<{ size?: number; className?: string }>;
  disabled: boolean;
  loading: boolean;
  onClick: () => void;
  variant: 'primary' | 'danger';
}> = ({ label, icon: Icon, disabled, loading, onClick, variant }) => {
  const bg =
    variant === 'primary'
      ? 'bg-[#2563EB] active:bg-[#1D4ED8]'
      : 'bg-[#DC2626] active:bg-[#B91C1C]';
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={cn(
        'w-full h-14 rounded-2xl text-white font-black text-base flex items-center justify-center gap-2 shadow-lg',
        bg,
        disabled && 'opacity-50 shadow-none'
      )}
    >
      {loading ? (
        <Loader2 size={20} className="animate-spin" />
      ) : (
        <Icon size={20} />
      )}
      {label}
    </button>
  );
};

const Callout: React.FC<{
  tone: 'info' | 'error';
  icon: React.ComponentType<{ size?: number; className?: string }>;
  title: string;
  body: string;
  action?: React.ReactNode;
  spin?: boolean;
}> = ({ tone, icon: Icon, title, body, action, spin }) => (
  <div
    className={cn(
      'rounded-2xl p-4 border flex items-start gap-3',
      tone === 'error'
        ? 'bg-red-50 border-red-200 text-red-900'
        : 'bg-slate-50 border-slate-200 text-slate-800'
    )}
  >
    <Icon size={18} className={spin ? 'animate-spin' : ''} />
    <div className="flex-1">
      <p className="text-sm font-black">{title}</p>
      <p className="text-[13px] mt-1 leading-snug">{body}</p>
      {action}
    </div>
  </div>
);

const ErrorBanner: React.FC<{ text: string }> = ({ text }) => (
  <div className="rounded-2xl p-4 border bg-red-50 border-red-200 text-red-800 text-sm flex gap-2">
    <AlertCircle size={18} className="flex-shrink-0 mt-0.5" />
    <span className="font-semibold leading-snug">{text}</span>
  </div>
);
