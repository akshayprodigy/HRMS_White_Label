import { apiFetch } from '../client';

export type Uom = {
  id: number;
  code: string;
  name: string;
  symbol: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

export type UomCreate = {
  code: string;
  name: string;
  symbol?: string | null;
  is_active?: boolean;
};

export function listUoms(): Promise<Uom[]> {
  return apiFetch<Uom[]>('/api/v1/inventory/uoms');
}

export function createUom(payload: UomCreate): Promise<Uom> {
  return apiFetch<Uom>('/api/v1/inventory/uoms', {
    method: 'POST',
    body: JSON.stringify({
      ...payload,
      symbol: payload.symbol ?? null,
      is_active: payload.is_active ?? true,
    }),
  });
}
