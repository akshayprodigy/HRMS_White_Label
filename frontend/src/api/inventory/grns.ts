import { apiFetch } from '../client';

export type Grn = {
  id: number;
  grn_number: string;
  grn_date: string;
  purchase_order_id: number | null;
  vendor_name: string | null;
  warehouse_id: number;
  item_id: number;
  uom_id: number;
  qty_received: number;
  unit_cost: number | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
};

export type GrnCreate = {
  grn_number: string;
  grn_date: string;
  purchase_order_id?: number | null;
  vendor_name?: string | null;
  warehouse_id: number;
  item_id: number;
  uom_id: number;
  qty_received: number;
  unit_cost?: number | null;
  notes?: string | null;
};

export function listGrns(): Promise<Grn[]> {
  return apiFetch<Grn[]>('/api/v1/inventory/grns');
}

export function createGrn(payload: GrnCreate): Promise<Grn> {
  return apiFetch<Grn>('/api/v1/inventory/grns', {
    method: 'POST',
    body: JSON.stringify({
      ...payload,
      purchase_order_id: payload.purchase_order_id ?? null,
      vendor_name: payload.vendor_name ?? null,
      unit_cost: payload.unit_cost ?? null,
      notes: payload.notes ?? null,
    }),
  });
}
