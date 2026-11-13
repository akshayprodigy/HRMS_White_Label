import { api } from '../../api/client';

export type RunningLateState = {
  notice: { expected_at: string; eta_hhmm: string; reason: string | null } | null;
  can_post: boolean;
  shift_name?: string | null;
  shift_start?: string;
  shift_end?: string;
};
export const MIN_LATE = 5;
export const MAX_LATE = 240;
export const RUNNING_LATE_KEY = ['running-late'] as const;

export function validateRunningLate(minutes: number, reason: string): string | null {
  if (!Number.isInteger(minutes)) return 'Enter the minutes as a whole number';
  if (minutes < MIN_LATE || minutes > MAX_LATE) return `Minutes late must be between ${MIN_LATE} and ${MAX_LATE}`;
  if (reason.trim().length > 255) return 'Reason must be 255 characters or fewer';
  return null;
}
/** Shown only when the shift has started and the user has not punched in (server also enforces can_post). */
export function canShowRunningLate(s: RunningLateState | undefined, isMarked: boolean | undefined, now = Date.now()): boolean {
  if (!s || !s.can_post || isMarked !== false || !s.shift_start) return false;
  return now >= Date.parse(s.shift_start);
}
export async function fetchRunningLate(): Promise<RunningLateState> {
  return (await api.get<RunningLateState>('/roster/my/running-late')).data;
}
export async function postRunningLate(minutes: number, reason: string) {
  const r = reason.trim();
  return (await api.post('/roster/my/running-late', { minutes_late: minutes, ...(r ? { reason: r } : {}) })).data;
}
export async function clearRunningLate() {
  await api.delete('/roster/my/running-late');
}
