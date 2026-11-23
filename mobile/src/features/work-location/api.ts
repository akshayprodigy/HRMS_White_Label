import { api } from '../../api/client';

export type WorkLocationKind = 'on_duty' | 'client_visit' | 'wfh';
export type DayPortion = 'full' | 'first_half' | 'second_half';
export type WorkLocationStatus = 'pending' | 'approved' | 'rejected' | 'cancelled';
/** GET /work-location-requests/my. */
export type WorkLocationRequest = {
  id: number;
  kind: WorkLocationKind;
  start_date: string;
  end_date: string;
  day_portion: DayPortion;
  place: string | null;
  purpose: string;
  status: WorkLocationStatus;
  decision_note: string | null;
};
/** The backend body forbids extra fields (extra="forbid"). */
export type RequestPayload = { kind: WorkLocationKind; start_date: string; end_date: string; day_portion: DayPortion; place: string | null; purpose: string };

export const WL_KEYS = { my: ['work-location', 'my'] } as const;

export async function fetchMyRequests(): Promise<WorkLocationRequest[]> {
  const d = (await api.get('/work-location-requests/my')).data;
  return Array.isArray(d) ? (d as WorkLocationRequest[]) : [];
}
export async function createRequest(p: RequestPayload): Promise<unknown> {
  return (await api.post('/work-location-requests', p)).data;
}
export async function cancelRequest(id: number): Promise<unknown> {
  return (await api.post(`/work-location-requests/${id}/cancel`)).data;
}
