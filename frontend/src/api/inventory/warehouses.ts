import { apiFetch } from '../client';

export type Warehouse = {
  id: number;
  code: string;
  name: string;
  location: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

export type WarehouseCreate = {
  code: string;
  name: string;
  location?: string | null;
  is_active?: boolean;
};

export function listWarehouses(): Promise<Warehouse[]> {
  return apiFetch<Warehouse[]>('/api/v1/inventory/warehouses');
}

export function createWarehouse(payload: WarehouseCreate): Promise<Warehouse> {
  return apiFetch<Warehouse>('/api/v1/inventory/warehouses', {
    method: 'POST',
    body: JSON.stringify({
      ...payload,
      location: payload.location ?? null,
      is_active: payload.is_active ?? true,
    }),
  });
}
