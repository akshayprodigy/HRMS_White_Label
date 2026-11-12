export interface Delegation {
  id: number;
  grantee_id: number;
  grantee_name: string | null;
  scope_type: 'employees' | 'department' | 'location' | 'team';
  scope_value: string | null;
  employee_ids: number[];
  can_publish: boolean;
  can_approve_changes: boolean;
  can_emergency_override?: boolean;
  valid_from: string;
  valid_to: string | null;
  revoked_at: string | null;
  granted_by_name: string | null;
  note: string | null;
  covered_count: number;
}
export interface UserLite {
  id: number;
  email: string;
  full_name: string | null;
}

// Backend evaluates validity in UTC, so use the UTC date everywhere.
export const todayIso = () => new Date().toISOString().slice(0, 10);

export const errMsg = (err: any, fallback: string): string => {
  const data = err?.response?.data;
  if (typeof data?.detail === 'string') return data.detail;
  if (Array.isArray(data?.detail)) {
    const msgs = data.detail
      .map((d: any) => (typeof d?.msg === 'string' ? d.msg : null))
      .filter(Boolean);
    if (msgs.length) return msgs.join('; ');
  }
  if (typeof data?.error?.message === 'string') return data.error.message;
  return fallback;
};

export const scopeLabel = (d: {
  scope_type: string;
  scope_value: string | null;
  employee_ids: number[];
}) => {
  switch (d.scope_type) {
    case 'department':
      return `Department: ${d.scope_value}`;
    case 'location':
      return `Location: ${d.scope_value}`;
    case 'team':
      return 'Their reporting team';
    default:
      return `${d.employee_ids.length} selected employee${
        d.employee_ids.length === 1 ? '' : 's'
      }`;
  }
};

// Server datetimes may be naive (UTC, no offset) or carry Z / an offset.
export const parseServerDate = (iso: string) =>
  new Date(/(Z|[+-]\d{2}:?\d{2})$/.test(iso) ? iso : `${iso}Z`);
