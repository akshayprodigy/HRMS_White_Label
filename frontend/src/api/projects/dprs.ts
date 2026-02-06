import { apiFetch } from '../client';

export type DprDrillingLineCreate = {
  line_no: number;
  location?: string | null;
  meters_drilled: number;
  recovered_meters?: number | null;
};

export type DprActivityLineCreate = {
  line_no: number;
  activity: string;
  hours?: number | null;
  remarks?: string | null;
};

export type DprConsumptionLineCreate = {
  line_no: number;
  item_id?: number | null;
  uom_id?: number | null;
  qty: number;
  remarks?: string | null;
};

export type DprCreate = {
  project_id: number;
  dpr_date: string; // YYYY-MM-DD
  shift?: string | null;
  remarks?: string | null;
  drilling_lines: DprDrillingLineCreate[];
  activity_lines?: DprActivityLineCreate[];
  consumption_lines?: DprConsumptionLineCreate[];
};

export type DprHeaderPublic = {
  id: number;
  project_id: number;
  dpr_date: string;
  shift: string | null;
  remarks: string | null;
  created_at: string;
  updated_at: string;
};

export type DprMetricsPublic = {
  dpr_id: number;
  meters_drilled_total: number;
  recovered_meters_total: number;
  recovery_percent: number;
};

export function createDpr(payload: DprCreate): Promise<DprHeaderPublic> {
  return apiFetch<DprHeaderPublic>('/api/v1/projects/dprs', {
    method: 'POST',
    body: JSON.stringify({
      ...payload,
      shift: payload.shift ?? null,
      remarks: payload.remarks ?? null,
      activity_lines: payload.activity_lines ?? [],
      consumption_lines: payload.consumption_lines ?? [],
    }),
  });
}

export function getDprMetrics(dprId: number): Promise<DprMetricsPublic> {
  return apiFetch<DprMetricsPublic>(`/api/v1/projects/dprs/${dprId}/metrics`);
}
