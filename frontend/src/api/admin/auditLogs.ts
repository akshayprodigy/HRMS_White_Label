import { apiFetch } from '../client';

export type AuditLog = {
  id: number;
  entity_type: string;
  entity_id: string;
  action: string;
  before_json: Record<string, unknown> | null;
  after_json: Record<string, unknown> | null;
  actor_user_id: number | null;
  request_id: string | null;
  created_at: string;
};

export type AuditLogFilters = {
  entity_type?: string;
  entity_id?: string;
  action?: string;
  actor_user_id?: number;
  request_id?: string;
  created_from?: string;
  created_to?: string;
  limit?: number;
  offset?: number;
};

function toQueryString(filters: AuditLogFilters): string {
  const params = new URLSearchParams();

  const setIf = (k: string, v: unknown) => {
    if (v === undefined || v === null) return;
    if (typeof v === 'string' && v.trim() === '') return;
    params.set(k, String(v));
  };

  setIf('entity_type', filters.entity_type);
  setIf('entity_id', filters.entity_id);
  setIf('action', filters.action);
  setIf('actor_user_id', filters.actor_user_id);
  setIf('request_id', filters.request_id);
  setIf('created_from', filters.created_from);
  setIf('created_to', filters.created_to);
  setIf('limit', filters.limit ?? 50);
  setIf('offset', filters.offset ?? 0);

  const qs = params.toString();
  return qs ? `?${qs}` : '';
}

export function queryAuditLogs(filters: AuditLogFilters = {}): Promise<AuditLog[]> {
  return apiFetch<AuditLog[]>(`/api/v1/admin/audit-logs${toQueryString(filters)}`);
}
