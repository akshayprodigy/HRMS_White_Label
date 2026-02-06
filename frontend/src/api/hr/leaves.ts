import { apiFetch } from '../client';

export type LeaveType = {
  id: number;
  code: string;
  name: string;
  description: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

export type LeavePolicy = {
  id: number;
  leave_type_id: number;
  name: string;
  monthly_credit_days: number;
  max_balance_days: number | null;
  is_active: boolean;
  notes: string | null;
  created_at: string;
  updated_at: string;
};

export type LeaveBalance = {
  id: number;
  employee_id: number;
  leave_type_id: number;
  balance_days: number;
  created_at: string;
  updated_at: string;
};

export type LeaveRequest = {
  id: number;
  employee_id: number;
  leave_type_id: number;
  date_from: string;
  date_to: string;
  days: number;
  reason: string | null;
  status: string;
  applied_at: string;
  decided_at: string | null;
  decided_by_user_id: number | null;
  decision_comment: string | null;
  created_at: string;
  updated_at: string;
};

export type LeaveApplyPayload = {
  employee_id: number;
  leave_type_id: number;
  date_from: string;
  date_to: string;
  reason?: string | null;
};

export type LeaveDecisionPayload = {
  comment?: string | null;
};

export function listLeaveTypes(): Promise<LeaveType[]> {
  return apiFetch<LeaveType[]>('/api/v1/hr/leave-types');
}

export function listLeaveRequests(params?: {
  status?: string | null;
  employee_id?: number | null;
}): Promise<LeaveRequest[]> {
  const usp = new URLSearchParams();
  if (params?.status) usp.set('status', params.status);
  if (params?.employee_id != null) usp.set('employee_id', String(params.employee_id));
  const qs = usp.toString();
  return apiFetch<LeaveRequest[]>(`/api/v1/hr/leave-requests${qs ? `?${qs}` : ''}`);
}

export function applyLeave(payload: LeaveApplyPayload): Promise<LeaveRequest> {
  return apiFetch<LeaveRequest>('/api/v1/hr/leave-requests/apply', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function approveLeave(
  requestId: number,
  payload: LeaveDecisionPayload,
): Promise<LeaveRequest> {
  return apiFetch<LeaveRequest>(`/api/v1/hr/leave-requests/${requestId}/approve`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function rejectLeave(
  requestId: number,
  payload: LeaveDecisionPayload,
): Promise<LeaveRequest> {
  return apiFetch<LeaveRequest>(`/api/v1/hr/leave-requests/${requestId}/reject`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function cancelLeave(requestId: number): Promise<LeaveRequest> {
  return apiFetch<LeaveRequest>(`/api/v1/hr/leave-requests/${requestId}/cancel`, {
    method: 'POST',
    body: JSON.stringify({}),
  });
}

export function listLeaveBalances(employeeId: number): Promise<LeaveBalance[]> {
  return apiFetch<LeaveBalance[]>(`/api/v1/hr/leave-balances/employees/${employeeId}`);
}
