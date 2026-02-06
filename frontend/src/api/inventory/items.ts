import { apiFetch } from '../client';

export type Item = {
  id: number;
  sku: string;
  name: string;
  description: string | null;
  base_uom_id: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

export type ItemCreate = {
  sku: string;
  name: string;
  description?: string | null;
  base_uom_id: number;
  is_active?: boolean;
};

export function listItems(): Promise<Item[]> {
  return apiFetch<Item[]>('/api/v1/inventory/items');
}

export function createItem(payload: ItemCreate): Promise<Item> {
  return apiFetch<Item>('/api/v1/inventory/items', {
    method: 'POST',
    body: JSON.stringify({
      ...payload,
      description: payload.description ?? null,
      is_active: payload.is_active ?? true,
    }),
  });
}
