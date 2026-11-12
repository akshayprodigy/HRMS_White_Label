import { client } from './client';
import { ENDPOINTS } from './endpoints';

export type RegularizationStatus = 'pending' | 'approved' | 'rejected' | 'cancelled';

export interface Regularization {
  id: number;
  user_id: number;
  work_date: string;
  attendance_id?: number | null;
  requested_punch_in: string;
  requested_punch_out?: string | null;
  reason: string;
  status: RegularizationStatus;
  decided_by_id?: number | null;
  decided_at?: string | null;
  decision_note?: string | null;
  created_at: string;
  requester_name?: string | null;
  requester_employee_code?: string | null;
}

export interface RegularizationCreate {
  work_date: string;
  requested_punch_in: string;
  requested_punch_out?: string | null;
  reason: string;
}

/** Backend error body is {"error":{"message"}}; legacy routes use {"detail"}. */
export const regularizationErrMsg = (e: any, fallback: string): string => {
  const data = e?.response?.data;
  if (data?.error?.message) return data.error.message;
  const d = data?.detail;
  if (typeof d === 'string') return d;
  if (Array.isArray(d)) return d.map((x: any) => x?.msg || JSON.stringify(x)).join('; ');
  return e?.message || fallback;
};

export const regularizationApi = {
  create: (body: RegularizationCreate) =>
    client.post<Regularization>(ENDPOINTS.ATTENDANCE.REGULARIZATIONS, body),
  listMine: () => client.get<Regularization[]>(ENDPOINTS.ATTENDANCE.REGULARIZATIONS_MY),
  listQueue: (status: RegularizationStatus | 'all' = 'pending') =>
    client.get<Regularization[]>(ENDPOINTS.ATTENDANCE.REGULARIZATIONS, { params: { status } }),
  decide: (id: number, approve: boolean, note?: string) =>
    client.post<Regularization>(ENDPOINTS.ATTENDANCE.REGULARIZATION_DECIDE(id), {
      approve,
      note: note?.trim() || undefined,
    }),
  cancel: (id: number) =>
    client.post<Regularization>(ENDPOINTS.ATTENDANCE.REGULARIZATION_CANCEL(id)),
};
