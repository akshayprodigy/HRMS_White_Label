import { fmtDate, fmtInr } from '../ui-elements';

export type AssetStatus = 'in_stock' | 'allocated' | 'in_repair' | 'retired' | 'lost';

export interface AssetCategory {
  id: number;
  name: string;
  code: string;
  default_useful_life_months: number | null;
  is_active: boolean;
}

export interface Holder { employee_id: number; name: string; emp_code: string | null }

export interface Asset {
  id: number;
  asset_tag: string;
  name: string;
  model: string | null;
  serial_no: string | null;
  status: AssetStatus;
  category: { id: number; name: string; code: string };
  location_id: number | null;
  vendor: string | null;
  invoice_no: string | null;
  purchase_date: string | null;
  purchase_cost_paise: number | null;
  salvage_value_paise: number;
  useful_life_months: number | null;
  warranty_expiry: string | null;
  amc_vendor: string | null;
  amc_expiry: string | null;
  notes: string | null;
  created_at: string | null;
  holder: Holder | null;
  book_value_paise: number | null;
}

export interface Depreciation {
  cost_paise: number;
  salvage_paise: number;
  life_months: number | null;
  months_elapsed: number;
  accumulated_paise: number;
  book_value_paise: number;
  fully_depreciated: boolean;
}

export interface HistoryRow {
  id: number;
  employee_id: number;
  emp_code: string | null;
  employee_name: string;
  issued_date: string | null;
  returned_date: string | null;
  status: string;
  condition: string | null;
  returned_condition: string | null;
  remarks: string | null;
  allocated_by: string | null;
  returned_to: string | null;
}

export type MaintKind = 'repair' | 'service' | 'amc_visit' | 'upgrade';

export interface Maintenance {
  id: number;
  kind: MaintKind;
  description: string;
  vendor: string | null;
  cost_paise: number;
  started_on: string | null;
  completed_on: string | null;
}

export interface AssetDetail extends Asset {
  depreciation: Depreciation | null;
  history: HistoryRow[];
  maintenance: Maintenance[];
  maintenance_cost_total_paise: number;
}

export interface Summary {
  by_status: Record<AssetStatus, number>;
  by_category: { id: number; name: string; count: number }[];
  expiring_30d: number;
  total_cost_paise: number;
  total_book_value_paise: number;
}

export const STATUS_LABEL: Record<AssetStatus, string> = {
  in_stock: 'In stock',
  allocated: 'Allocated',
  in_repair: 'In repair',
  retired: 'Retired',
  lost: 'Lost',
};

export const STATUS_BADGE: Record<AssetStatus, 'success' | 'info' | 'warning' | 'error' | 'neutral'> = {
  in_stock: 'success',
  allocated: 'info',
  in_repair: 'warning',
  retired: 'neutral',
  lost: 'error',
};

export const KIND_LABEL: Record<MaintKind, string> = {
  repair: 'Repair', service: 'Service', amc_visit: 'AMC visit', upgrade: 'Upgrade',
};

export const inputCls =
  'h-9 px-2 border border-gray-200 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500';
export const labelCls = 'block text-xs font-medium text-gray-600 mb-1';

export { fmtDate, fmtInr };

/** Rupee text input -> integer paise. '' -> null; invalid/negative -> NaN. */
export const rupeesToPaise = (s: string): number | null => {
  const t = s.trim();
  if (!t) return null;
  const n = Number(t.replace(/,/g, ''));
  if (!Number.isFinite(n) || n < 0) return NaN;
  return Math.round(n * 100);
};

export const paiseToRupees = (p: number | null | undefined): string =>
  p == null ? '' : (p / 100).toFixed(2);

export const todayIso = (): string => {
  const d = new Date();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${d.getFullYear()}-${m}-${day}`;
};

/** Days from today to an ISO date (negative = past); null when no date. */
export const daysUntil = (iso: string | null | undefined): number | null => {
  if (!iso) return null;
  const t = new Date(iso + 'T00:00:00').getTime();
  if (Number.isNaN(t)) return null;
  const now = new Date();
  const base = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  return Math.round((t - base) / 86_400_000);
};

export const expiringSoon = (iso: string | null | undefined, days = 30): boolean => {
  const d = daysUntil(iso);
  return d != null && d >= 0 && d <= days;
};

export const holderText = (h: Holder | null): string =>
  h ? `${h.name}${h.emp_code ? ` (${h.emp_code})` : ''}` : '—';
