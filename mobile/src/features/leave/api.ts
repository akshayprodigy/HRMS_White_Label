import { api } from '../../api/client';

export type LeaveType = {
  id: number;
  name: string;
  allow_half_day?: boolean;
  requires_medical_cert_after?: number | null;
  unpaid_allowed?: boolean;
};
/** GET /leave/balances (LeaveBalanceRead; `remaining`/`total` are computed server-side). */
export type LeaveBalance = { leave_type: LeaveType; balance: number; used: number; total: number; remaining: number };
export type LeaveStatus = 'draft' | 'submitted' | 'approved' | 'rejected' | 'cancelled';
/** GET /leave/my (LeaveRequestRead). */
export type LeaveRequest = {
  id: number;
  leave_type: LeaveType;
  start_date: string;
  end_date: string;
  is_half_day: boolean;
  half_day_session: 'morning' | 'afternoon' | null;
  reason: string;
  status: LeaveStatus;
  total_days: number;
  is_emergency: boolean;
  attachment_url: string | null;
  proof_due_date: string | null;
  proof_submitted_at: string | null;
  converted_to_lop_at: string | null;
};
export type PickedFile = { uri: string; name: string; mimeType: string; size?: number | null };
export type ApplyPayload = {
  leave_type_id: number;
  start_date: string;
  end_date: string;
  reason: string;
  emergency_contact: string | null;
  is_half_day: boolean;
  half_day_session: 'morning' | 'afternoon' | null;
  attachment_url: string | null;
  is_emergency: boolean;
};

export const LEAVE_KEYS = { balances: ['leave', 'balances'], types: ['leave', 'types'], my: ['leave', 'my'] } as const;

const list = <T>(d: unknown): T[] => (Array.isArray(d) ? (d as T[]) : []);

export async function fetchBalances(): Promise<LeaveBalance[]> {
  return list((await api.get('/leave/balances')).data);
}
export async function fetchLeaveTypes(): Promise<LeaveType[]> {
  return list((await api.get('/leave/types')).data);
}
export async function fetchMyLeaves(): Promise<LeaveRequest[]> {
  return list((await api.get('/leave/my')).data);
}

/** POST /leave/attachments (multipart `file`) -> opaque stored filename to pass as `attachment_url`. */
export async function uploadAttachment(file: PickedFile): Promise<string> {
  const form = new FormData();
  form.append('file', { uri: file.uri, name: file.name, type: file.mimeType } as unknown as Blob);
  const res = await api.post<{ attachment_url: string }>('/leave/attachments', form, { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 60000 });
  return res.data.attachment_url;
}

export async function applyLeave(payload: ApplyPayload, file: PickedFile | null): Promise<LeaveRequest> {
  const attachment_url = file ? await uploadAttachment(file) : payload.attachment_url;
  return (await api.post<LeaveRequest>('/leave/apply', { ...payload, attachment_url })).data;
}

/** Upload then attach to an emergency leave (POST /leave/{id}/proof). */
export async function submitProof(leaveId: number, file: PickedFile): Promise<LeaveRequest> {
  const attachment_url = await uploadAttachment(file);
  return (await api.post<LeaveRequest>(`/leave/${leaveId}/proof`, { attachment_url })).data;
}

export async function cancelLeave(leaveId: number): Promise<LeaveRequest> {
  return (await api.post<LeaveRequest>(`/leave/${leaveId}/cancel`)).data;
}

/** Proof is still owed: emergency leave with a due date, nothing submitted, still live and not converted to LOP. */
export function proofOwed(r: LeaveRequest): boolean {
  return !!r.proof_due_date && !r.proof_submitted_at && !r.converted_to_lop_at && (r.status === 'submitted' || r.status === 'approved');
}
