import { apiFetch } from '../client';

export type MaterialIssue = {
  id: number;
  issue_number: string;
  issue_date: string;
  project_id: number;
  cost_center_id: number;
  warehouse_id: number;
  item_id: number;
  uom_id: number;
  qty_issued: number;
  unit_cost: number | null;
  remarks: string | null;
  created_at: string;
  updated_at: string;
};

export type MaterialIssueCreate = {
  issue_number: string;
  issue_date: string;
  project_id: number;
  cost_center_id: number;
  warehouse_id: number;
  item_id: number;
  uom_id: number;
  qty_issued: number;
  unit_cost?: number | null;
  remarks?: string | null;
};

export function listIssues(): Promise<MaterialIssue[]> {
  return apiFetch<MaterialIssue[]>('/api/v1/inventory/issues');
}

export function createIssue(payload: MaterialIssueCreate): Promise<MaterialIssue> {
  return apiFetch<MaterialIssue>('/api/v1/inventory/issues', {
    method: 'POST',
    body: JSON.stringify({
      ...payload,
      unit_cost: payload.unit_cost ?? null,
      remarks: payload.remarks ?? null,
    }),
  });
}
