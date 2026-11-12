export interface ShiftTemplateLite {
  id: number;
  name: string;
  start_time: string;
  end_time: string;
  is_overnight: boolean;
}
export interface RosterCell {
  work_date: string;
  shift_template_id: number | null;
  is_week_off: boolean;
  status: string | null;
  entry_id: number | null;
  source: string;
  shift_name: string | null;
}
export interface RosterGridRow {
  employee_id: number;
  full_name: string | null;
  department: string | null;
  designation: string | null;
  in_scope: boolean;
  cells: RosterCell[];
}
export interface RosterGrid {
  start: string;
  end: string;
  dates: string[];
  shift_templates: ShiftTemplateLite[];
  rows: RosterGridRow[];
  is_admin: boolean;
  can_publish: boolean;
}
export interface BulkResult {
  created: number;
  updated: number;
  skipped: number;
  out_of_scope: number[];
  errors: string[];
}
export interface PublishResult {
  published: number;
  employees: number;
  not_permitted: number[];
}
export interface PublishRequest {
  id: number;
  requested_by_id: number;
  requester_name: string | null;
  start: string;
  end: string;
  department: string | null;
  employee_ids: number[];
  note: string | null;
  status: string;
  decision_note: string | null;
  draft_count: number | null;
  message: string | null;
}
export interface RotationPattern {
  id: number;
  name: string;
  description: string | null;
  cycle: (number | null)[];
  is_active: boolean;
}
export interface HistoryRow {
  id: number;
  employee_id: number;
  employee_name: string | null;
  work_date: string;
  old_shift_name: string | null;
  old_is_week_off: boolean;
  new_shift_name: string | null;
  new_is_week_off: boolean;
  action: string;
  reason: string | null;
  changed_by_name: string | null;
  changed_at: string;
}

export interface Violation {
  user_id: number;
  work_date: string;
  rule: string;
  message: string;
  employee_name?: string | null;
}
export interface CoverageCell {
  date: string;
  shift_template_id: number;
  shift_name?: string | null;
  department: string | null;
  location: string | null;
  required_min: number;
  required_max: number | null;
  scheduled: number;
  status: 'under' | 'ok' | 'over';
}
export interface Insights {
  violations: Violation[];
  coverage: CoverageCell[];
}
export interface CoverageRequirement {
  id: number;
  department: string | null;
  location: string | null;
  shift_template_id: number;
  weekday: number | null;
  min_headcount: number;
  max_headcount: number | null;
  is_active: boolean;
}

export const WEEKOFF = '__weekoff__';

/** Human label of a history side: shift name, "Week off" or "—". */
export const sideLabel = (name: string | null, weekOff: boolean) =>
  weekOff ? 'Week off' : name || '—';

/** ISO date helpers working on pure YYYY-MM-DD strings (UTC, no TZ drift). */
export const addDays = (isoStr: string, n: number) => {
  const d = new Date(isoStr + 'T00:00:00Z');
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
};
export const daysBetween = (a: string, b: string) =>
  Math.round(
    (Date.parse(b + 'T00:00:00Z') - Date.parse(a + 'T00:00:00Z')) / 86400000
  );
