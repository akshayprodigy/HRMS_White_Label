import { apiFetch } from '../client';

export type ProjectConsumptionRow = {
  project_id: number;
  item_id: number;
  qty_issued: number;
};

export type ProjectConsumptionQuery = {
  date_from: string;
  date_to: string;
  project_id?: number;
  item_id?: number;
};

export function getProjectConsumption(
  query: ProjectConsumptionQuery,
): Promise<ProjectConsumptionRow[]> {
  const params = new URLSearchParams({
    date_from: query.date_from,
    date_to: query.date_to,
  });

  if (query.project_id !== undefined) params.set('project_id', String(query.project_id));
  if (query.item_id !== undefined) params.set('item_id', String(query.item_id));

  return apiFetch<ProjectConsumptionRow[]>(
    `/api/v1/inventory/reports/project-consumption?${params.toString()}`,
  );
}
