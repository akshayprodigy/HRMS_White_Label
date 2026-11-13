import Constants from 'expo-constants';
import { api } from '../../api/client';

export const MY_STATUS_KEY = ['tracking', 'my-status'] as const;
export const FIELD_NOW_KEY = ['tracking', 'field-now'] as const;

export type TrackingWindow = {
  work_date: string;
  /** Window = shift start - 30 min ... shift end + 30 min (UTC). */
  start: string;
  end: string;
  shift_start: string;
  shift_end: string;
  in_window: boolean;
};
/** GET /tracking/my-status. `active` = required (HR policy) AND consented. */
export type MyStatus = {
  required: boolean;
  consented: boolean;
  consented_at: string | null;
  active: boolean;
  window: TrackingWindow | null;
  interval_seconds: number;
  distance_filter_m: number;
};

/** One point as POSTed to /tracking/pings. accuracy/speed/battery are optional server-side but must be in range. */
export type WirePing = { captured_at: string; lat: number; lng: number; accuracy: number | null; speed: number | null; battery: number | null };
export type PingResult = { accepted: number; dropped: Record<string, number> };

export type FieldStatus = 'off' | 'on_leave' | 'upcoming' | 'not_arrived' | 'no_show' | 'running_late' | 'on_shift' | 'completed';
export type FieldPing = { captured_at: string; lat: number; lng: number; accuracy: number | null; speed: number | null; battery: number | null };
export type FieldRow = {
  user_id: number;
  name: string;
  department: string | null;
  status: FieldStatus;
  late_minutes: number;
  shift_name: string | null;
  start_hhmm: string | null;
  end_hhmm: string | null;
  ping: FieldPing | null;
};
export type FieldNow = { now: string; tracked: number; with_location: number; rows: FieldRow[] };
export type Trail = { user_id: number; date: string; truncated: boolean; points: FieldPing[] };

export async function fetchMyStatus(): Promise<MyStatus> {
  return (await api.get<MyStatus>('/tracking/my-status')).data;
}
export async function giveConsent(): Promise<{ consented: boolean; consented_at: string | null }> {
  const appVersion = Constants.expoConfig?.version ?? undefined;
  return (await api.post('/tracking/consent', appVersion ? { app_version: appVersion } : {})).data;
}
export async function revokeConsent(): Promise<{ consented: boolean; revoked: boolean }> {
  return (await api.delete('/tracking/consent')).data;
}
export async function deleteMyData(): Promise<{ deleted: { pings: number; alerts: number } }> {
  return (await api.delete('/tracking/my-data')).data;
}
export async function postPings(pings: WirePing[]): Promise<PingResult> {
  const d = (await api.post<Partial<PingResult>>('/tracking/pings', { pings })).data;
  return { accepted: d.accepted ?? 0, dropped: d.dropped ?? {} };
}
export async function fetchFieldNow(department?: string): Promise<FieldNow> {
  return (await api.get<FieldNow>('/tracking/field-now', { params: department ? { department } : undefined })).data;
}
export async function fetchTrail(userId: number, date: string): Promise<Trail> {
  return (await api.get<Trail>('/tracking/trail', { params: { user_id: userId, date } })).data;
}
/** GET /tracking/my-trail?date= : the caller's own points for a UTC work date (no consent/policy gate). */
export async function fetchMyTrail(date: string): Promise<Trail> {
  return (await api.get<Trail>('/tracking/my-trail', { params: { date } })).data;
}
