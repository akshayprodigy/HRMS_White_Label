import { parseServerDate } from '../schedule-delegations-utils';

export type DeviceStatus = 'pending' | 'active' | 'disabled';
export type Health = 'online' | 'offline' | 'never' | 'disabled';

export interface Device {
  id: number;
  serial: string;
  name: string | null;
  status: DeviceStatus;
  utc_offset_minutes: number;
  ip_allowlist: string | null;
  location_note: string | null;
  last_seen_at: string | null;
  last_ip: string | null;
  firmware: string | null;
  approved_at: string | null;
  health: Health;
  pending_punches: number;
  unmapped_pins: number;
  enrolled_users: number;
}

export interface MappingInfo {
  id: number;
  device_id: number | null;
  pin: string;
  user_id: number;
  user_name: string | null;
  employee_code: string | null;
  created_at: string;
  scope?: 'device' | 'global';
}

export interface DeviceUser {
  pin: string;
  name: string | null;
  mapping: MappingInfo | null;
  suggested_user_id: number | null;
  suggested_user_name: string | null;
  suggested_employee_code: string | null;
}

export interface Punch {
  id: number;
  source: string;
  device_id: number | null;
  device_serial: string | null;
  import_batch: string | null;
  pin: string;
  punch_time: string;
  device_status: string | null;
  verify_type: number | string | null;
  state: string;
  user_id: number | null;
  user_name: string | null;
  employee_code: string | null;
  attendance_id: number | null;
  error: string | null;
  created_at: string;
  applied_at: string | null;
}

/** Shape of every back-fill carrying response. */
export interface BackfillResp {
  backfill?: Record<string, number>;
  remaining?: number;
  next_after_id?: number | null;
}

export const HEALTH_META: Record<Health, { label: string; variant: 'success' | 'error' | 'neutral' }> = {
  online: { label: 'Online', variant: 'success' },
  offline: { label: 'Offline', variant: 'error' },
  never: { label: 'Never seen', variant: 'neutral' },
  disabled: { label: 'Disabled', variant: 'neutral' },
};

export const STATUS_VARIANT: Record<DeviceStatus, 'success' | 'warning' | 'neutral'> = {
  active: 'success',
  pending: 'warning',
  disabled: 'neutral',
};

export const PUNCH_STATES = [
  'pending_device', 'unmapped', 'received', 'applied', 'duplicate', 'locked', 'edited', 'error', 'ignored',
] as const;

export const PUNCH_STATE_VARIANT: Record<string, 'success' | 'warning' | 'error' | 'info' | 'neutral'> = {
  applied: 'success',
  received: 'info',
  edited: 'info',
  pending_device: 'warning',
  unmapped: 'warning',
  locked: 'warning',
  error: 'error',
  duplicate: 'neutral',
  ignored: 'neutral',
};

export const REPROCESS_STATES = ['error', 'unmapped', 'locked', 'pending'] as const;

/** Common UTC offsets, in minutes. */
export const COMMON_OFFSETS: { minutes: number; label: string }[] = [
  { minutes: 330, label: 'UTC+05:30 (India)' },
  { minutes: 0, label: 'UTC+00:00' },
  { minutes: 60, label: 'UTC+01:00' },
  { minutes: 120, label: 'UTC+02:00' },
  { minutes: 180, label: 'UTC+03:00' },
  { minutes: 240, label: 'UTC+04:00 (Gulf)' },
  { minutes: 300, label: 'UTC+05:00' },
  { minutes: 345, label: 'UTC+05:45 (Nepal)' },
  { minutes: 360, label: 'UTC+06:00' },
  { minutes: 480, label: 'UTC+08:00' },
  { minutes: 540, label: 'UTC+09:00' },
  { minutes: -300, label: 'UTC-05:00' },
  { minutes: -480, label: 'UTC-08:00' },
];

export const offsetLabel = (m: number): string => {
  const sign = m < 0 ? '-' : '+';
  const a = Math.abs(m);
  return `UTC${sign}${String(Math.floor(a / 60)).padStart(2, '0')}:${String(a % 60).padStart(2, '0')}`;
};

export const relTime = (iso: string | null, now: Date = new Date()): string => {
  if (!iso) return 'never';
  const secs = Math.max(0, Math.round((now.getTime() - parseServerDate(iso).getTime()) / 1000));
  if (secs < 60) return 'just now';
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `${mins} min ago`;
  const h = Math.floor(mins / 60);
  if (h < 48) return `${h} h ago`;
  return `${Math.floor(h / 24)} d ago`;
};

/** Convention (same as Field Team): exact instants are labelled UTC. */
export const utcText = (iso: string | null): string =>
  iso ? `${parseServerDate(iso).toISOString().slice(0, 19).replace('T', ' ')} UTC` : '';

/** Viewer-local display, e.g. "06 Jan 2031, 09:00:12". */
export const localText = (iso: string | null): string => {
  if (!iso) return '';
  const d = parseServerDate(iso);
  return d.toLocaleString([], {
    day: '2-digit', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
  });
};

export const sumCounts = (a: Record<string, number>, b?: Record<string, number>) => {
  const out = { ...a };
  Object.entries(b ?? {}).forEach(([k, v]) => { out[k] = (out[k] ?? 0) + v; });
  return out;
};

export const countsText = (c: Record<string, number>): string => {
  const parts = Object.entries(c).filter(([, v]) => v > 0).map(([k, v]) => `${v} ${k.replace(/_/g, ' ')}`);
  return parts.length ? parts.join(', ') : 'nothing to apply';
};

export const downloadTextFile = (text: string, filename: string, mime = 'text/csv') => {
  const url = URL.createObjectURL(new Blob([text], { type: mime }));
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
};

/** Attendance `mode` label; biometric rows read "Biometric". */
export const attendanceModeLabel = (mode: string | null | undefined): string =>
  mode === 'biometric' ? 'Biometric' : (mode ?? '');

/** Local-midnight date input value -> ISO instant. */
export const dayStartIso = (d: string, plusDays = 0): string => {
  const dt = new Date(`${d}T00:00:00`);
  dt.setDate(dt.getDate() + plusDays);
  return dt.toISOString();
};
