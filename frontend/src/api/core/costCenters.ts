import { apiFetch } from '../client';

export type CostCenter = {
  id: number;
  organization_id: number;
  code: string;
  name: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

export type CostCenterCreate = {
  organization_id: number;
  code: string;
  name: string;
  is_active?: boolean;
};

export function listCostCenters(): Promise<CostCenter[]> {
  return apiFetch<CostCenter[]>('/api/v1/core/cost-centers');
}

export function createCostCenter(payload: CostCenterCreate): Promise<CostCenter> {
  return apiFetch<CostCenter>('/api/v1/core/cost-centers', {
    method: 'POST',
    body: JSON.stringify({
      ...payload,
      is_active: payload.is_active ?? true,
    }),
  });
}
