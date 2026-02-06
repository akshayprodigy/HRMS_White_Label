import { apiFetch } from '../client';

export type ProjectDirectExpense = {
  id: number;
  project_id: number;
  expense_date: string;
  category: string;
  description: string | null;
  amount: number;
  vendor: string | null;
  reference_no: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
};

export type ProjectDirectExpenseCreate = {
  expense_date: string;
  category: string;
  description?: string | null;
  amount: number;
  vendor?: string | null;
  reference_no?: string | null;
  notes?: string | null;
};

export type ProjectRevenue = {
  id: number;
  project_id: number;
  revenue_date: string;
  category: string;
  description: string | null;
  amount: number;
  client: string | null;
  reference_no: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
};

export type ProjectRevenueCreate = {
  revenue_date: string;
  category: string;
  description?: string | null;
  amount: number;
  client?: string | null;
  reference_no?: string | null;
  notes?: string | null;
};

export type ProjectFinanceListQuery = {
  date_from?: string;
  date_to?: string;
  limit?: number;
  offset?: number;
};

function addCommonParams(params: URLSearchParams, q: ProjectFinanceListQuery) {
  if (q.date_from) params.set('date_from', q.date_from);
  if (q.date_to) params.set('date_to', q.date_to);
  if (q.limit != null) params.set('limit', String(q.limit));
  if (q.offset != null) params.set('offset', String(q.offset));
}

export function createProjectDirectExpense(
  projectId: number,
  payload: ProjectDirectExpenseCreate,
): Promise<ProjectDirectExpense> {
  return apiFetch<ProjectDirectExpense>(`/api/v1/projects/${projectId}/direct-expenses`, {
    method: 'POST',
    body: JSON.stringify({
      ...payload,
      description: payload.description ?? null,
      vendor: payload.vendor ?? null,
      reference_no: payload.reference_no ?? null,
      notes: payload.notes ?? null,
    }),
  });
}

export function listProjectDirectExpenses(
  projectId: number,
  q: ProjectFinanceListQuery,
): Promise<ProjectDirectExpense[]> {
  const params = new URLSearchParams();
  addCommonParams(params, q);
  const qs = params.toString();
  return apiFetch<ProjectDirectExpense[]>(
    `/api/v1/projects/${projectId}/direct-expenses${qs ? `?${qs}` : ''}`,
  );
}

export function createProjectRevenue(
  projectId: number,
  payload: ProjectRevenueCreate,
): Promise<ProjectRevenue> {
  return apiFetch<ProjectRevenue>(`/api/v1/projects/${projectId}/revenues`, {
    method: 'POST',
    body: JSON.stringify({
      ...payload,
      description: payload.description ?? null,
      client: payload.client ?? null,
      reference_no: payload.reference_no ?? null,
      notes: payload.notes ?? null,
    }),
  });
}

export function listProjectRevenues(
  projectId: number,
  q: ProjectFinanceListQuery,
): Promise<ProjectRevenue[]> {
  const params = new URLSearchParams();
  addCommonParams(params, q);
  const qs = params.toString();
  return apiFetch<ProjectRevenue[]>(`/api/v1/projects/${projectId}/revenues${qs ? `?${qs}` : ''}`);
}
