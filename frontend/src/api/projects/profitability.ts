import { apiFetch } from '../client';

export type MoneyByCategory = {
  category: string;
  amount: number;
};

export type LaborByEmployee = {
  employee_id: number;
  hours: number;
  cost: number;
  avg_rate: number;
};

export type MaterialByItem = {
  item_id: number;
  qty_issued: number;
  cost: number;
  avg_unit_cost: number;
};

export type ProjectProfitability = {
  project_id: number;
  date_from: string;
  date_to: string;

  revenue_total: number;
  revenue_by_category: MoneyByCategory[];

  labor_hours_total: number;
  labor_cost_total: number;
  labor_avg_rate: number;
  labor_by_employee: LaborByEmployee[];

  materials_qty_total: number;
  materials_cost_total: number;
  materials_avg_unit_cost: number;
  materials_by_item: MaterialByItem[];

  direct_expenses_total: number;
  direct_expenses_by_category: MoneyByCategory[];

  total_cost: number;
  gross_profit: number;
  gross_margin_percent: number;
};

export type ProfitabilityQuery = {
  date_from?: string;
  date_to?: string;
};

export function getProjectProfitability(
  projectId: number,
  q: ProfitabilityQuery,
): Promise<ProjectProfitability> {
  const params = new URLSearchParams();
  if (q.date_from) params.set('date_from', q.date_from);
  if (q.date_to) params.set('date_to', q.date_to);
  const qs = params.toString();
  return apiFetch<ProjectProfitability>(
    `/api/v1/projects/${projectId}/profitability${qs ? `?${qs}` : ''}`,
  );
}
