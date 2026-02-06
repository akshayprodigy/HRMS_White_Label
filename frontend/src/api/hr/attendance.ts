import { apiFetch } from '../client';

export type AttendanceEntry = {
  id: number;
  employee_id: number;
  project_id: number;
  work_date: string;
  hours: number;
  hourly_rate: number;
  notes: string | null;
  created_at: string;
  updated_at: string;
};

export type AttendanceEntryCreate = {
  employee_id: number;
  project_id: number;
  work_date: string;
  hours: number;
  hourly_rate: number;
  notes?: string | null;
};

export type AttendanceEntryListQuery = {
  project_id?: number;
  employee_id?: number;
  date_from?: string;
  date_to?: string;
  limit?: number;
  offset?: number;
};

export function createAttendanceEntry(payload: AttendanceEntryCreate): Promise<AttendanceEntry> {
  return apiFetch<AttendanceEntry>('/api/v1/hr/attendance', {
    method: 'POST',
    body: JSON.stringify({
      ...payload,
      notes: payload.notes ?? null,
    }),
  });
}

export function listAttendanceEntries(q: AttendanceEntryListQuery): Promise<AttendanceEntry[]> {
  const params = new URLSearchParams();
  if (q.project_id != null) params.set('project_id', String(q.project_id));
  if (q.employee_id != null) params.set('employee_id', String(q.employee_id));
  if (q.date_from) params.set('date_from', q.date_from);
  if (q.date_to) params.set('date_to', q.date_to);
  if (q.limit != null) params.set('limit', String(q.limit));
  if (q.offset != null) params.set('offset', String(q.offset));
  const qs = params.toString();
  return apiFetch<AttendanceEntry[]>(`/api/v1/hr/attendance${qs ? `?${qs}` : ''}`);
}
