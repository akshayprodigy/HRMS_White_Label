import { useQuery } from '@tanstack/react-query';
import { api, ApiError } from '../../api/client';
import type { AttendanceToday } from '../../api/types';
import { useAuth } from '../../auth/AuthProvider';

/** The backend's attendance gate (deps.verify_attendance) answers 403 with error.code ATTENDANCE_REQUIRED. */
export function isGateError(e: unknown): boolean {
  return e instanceof ApiError && e.status === 403 && e.code === 'ATTENDANCE_REQUIRED';
}

export async function fetchAttendanceToday(): Promise<AttendanceToday> {
  return (await api.get<AttendanceToday>('/attendance/today')).data;
}

export const ATTENDANCE_TODAY_KEY = ['attendance-today'] as const;

/**
 * Attendance gate parity with verify_attendance: only superusers are exempt (admin *roles* are not).
 * `gated` is true only once /attendance/today has answered "not marked"; while unknown we do not block.
 * Task 7 (punch) must invalidate ATTENDANCE_TODAY_KEY after a successful punch.
 */
export function useAttendanceGate() {
  const { user } = useAuth();
  const exempt = !!user?.is_superuser;
  const query = useQuery({ queryKey: ATTENDANCE_TODAY_KEY, queryFn: fetchAttendanceToday, enabled: !!user });
  const gated = !exempt && query.data?.is_marked === false;
  // `ready`: the gate answer is known (or the lookup failed), so gated endpoints may be called.
  return { exempt, query, today: query.data, gated, ready: !query.isPending };
}
