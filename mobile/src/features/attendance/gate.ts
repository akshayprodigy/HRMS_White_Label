import { useQuery } from '@tanstack/react-query';
import { api, ApiError } from '../../api/client';
import type { AttendanceToday } from '../../api/types';
import { useAuth } from '../../auth/AuthProvider';

/** The backend's attendance gate (deps.verify_attendance) answers 403 with error.code ATTENDANCE_REQUIRED. */
export function isGateError(e: unknown): boolean {
  return e instanceof ApiError && e.status === 403 && e.code === 'ATTENDANCE_REQUIRED';
}

/** Never retry a gate 403: it only clears after a punch. */
export const retryUnlessGate = (count: number, e: unknown) => !isGateError(e) && count < 1;

export async function fetchAttendanceToday(): Promise<AttendanceToday> {
  return (await api.get<AttendanceToday>('/attendance/today')).data;
}
export async function fetchPendingCount(): Promise<number> {
  const d = (await api.get<{ count?: number }>('/dashboard/pending-count')).data;
  return d?.count ?? 0;
}

export const ATTENDANCE_TODAY_KEY = ['attendance-today'] as const;
export const PENDING_COUNT_KEY = ['pending-count'] as const;

/**
 * Attendance gate parity with verify_attendance (only superusers are exempt; admin roles are not).
 * /attendance/today is only a HINT: its work-date attribution can differ from the server's gate check
 * (night shifts). When the hint says "not marked" we confirm with the first gated call
 * (/dashboard/pending-count, also shown on Home); only an actual ATTENDANCE_REQUIRED 403 sets `gated`.
 * `ready` = the answer is known, so other gated endpoints may be called without 403 spam.
 * Task 7 (punch) must invalidate ATTENDANCE_TODAY_KEY and PENDING_COUNT_KEY after a successful punch.
 */
export function useAttendanceGate() {
  const { user } = useAuth();
  const exempt = !!user?.is_superuser;
  const query = useQuery({ queryKey: ATTENDANCE_TODAY_KEY, queryFn: fetchAttendanceToday, enabled: !!user });
  const hintUnmarked = !exempt && query.data?.is_marked === false;
  const probe = useQuery({
    queryKey: PENDING_COUNT_KEY,
    queryFn: fetchPendingCount,
    enabled: !!user && !query.isPending,
    retry: retryUnlessGate,
  });
  const gated = hintUnmarked && isGateError(probe.error);
  const ready = !query.isPending && (!hintUnmarked || !probe.isPending);
  return { exempt, query, today: query.data, pendingQuery: probe, gated, ready };
}
