import { client } from '../../api/client';
import { ENDPOINTS } from '../../api/endpoints';
import type { AvailabilityRule, Drop, OpenShift, Swap } from '../my-schedule/my-schedule-api';

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

// ---------------------------------------------------------------------------
// Scheduler-side requests (swaps, drops, open shifts, availability)
// ---------------------------------------------------------------------------
export interface SwapWarning {
  user_id: number;
  employee_name: string | null;
  work_date: string;
  rule: string;
  message: string;
}
export type ApproverSwap = Swap & { warnings: SwapWarning[] };

export type SchedDrop = Drop & {
  user_id: number;
  user_name: string | null;
  shift_template_id: number;
  post_open_shift: boolean;
  open_shift_id: number | null;
  open_shift_skipped_reason: string | null;
};

export interface OpenShiftClaim {
  id: number;
  open_shift_id: number;
  user_id: number;
  user_name: string | null;
  status: string;
  eligibility_reason: string | null;
  /** false for the viewer's own claim unless they are a roster admin */
  can_decide?: boolean;
}
export type SchedOpenShift = OpenShift & {
  shift_template_id: number;
  status: string;
  auto_confirm: boolean;
  can_cancel: boolean;
  created_by_name: string | null;
  claims: OpenShiftClaim[];
};
export interface OpenShiftCreateInput {
  work_date: string;
  shift_template_id: number;
  department: string | null;
  location: string | null;
  slots: number;
  note: string | null;
  auto_confirm: boolean;
}
export type EmployeeAvailabilityRule = AvailabilityRule & {
  user_id: number;
  employee_name: string | null;
};

export interface CoverageGap {
  id: number;
  work_date: string;
  shift_template_id: number;
  shift_name: string | null;
  shift_start: string | null;
  shift_end: string | null;
  department: string | null;
  location: string | null;
  absent_user_id: number | null;
  absent_name: string | null;
  source: 'emergency_leave' | 'no_show' | 'drop' | 'sick_call' | 'manual';
  source_id: number | null;
  status: 'open' | 'filled' | 'dismissed';
  open_shift_id: number | null;
  open_shift_status: string | null;
  filled_by_user_id: number | null;
  filled_by_name: string | null;
  note: string | null;
  warnings?: string[];
}

export interface GapSuggestion {
  user_id: number;
  name: string;
  department: string | null;
  score: number;
  reasons: string[];
  month_hours: number;
  ot_headroom_minutes: number | null;
}

const R = ENDPOINTS.ROSTER;
const data = async <T,>(p: Promise<{ data: T }>): Promise<T> => (await p).data;

export const schedulerApi = {
  swapQueue: () =>
    data<ApproverSwap[]>(client.get(R.SWAPS, { params: { include_warnings: 1 } })),
  swapCheck: (id: number) => data<SwapWarning[]>(client.get(R.SWAP_CHECK(id))),
  decideSwap: (id: number, action: 'approve' | 'reject', note: string | null) =>
    data<ApproverSwap>(client.post(R.SWAP_DECIDE(id), { action, note })),

  dropQueue: () => data<SchedDrop[]>(client.get(R.DROPS)),
  decideDrop: (
    id: number,
    action: 'approve' | 'reject',
    note: string | null,
    post_open_shift: boolean | null
  ) => data<SchedDrop>(client.post(R.DROP_DECIDE(id), { action, note, post_open_shift })),

  openShifts: (start: string, end: string, status?: string) =>
    data<SchedOpenShift[]>(
      client.get(R.OPEN_SHIFTS, { params: { start, end, ...(status ? { status } : {}) } })
    ),
  createOpenShift: (b: OpenShiftCreateInput) =>
    data<SchedOpenShift>(client.post(R.OPEN_SHIFTS, b)),
  decideClaim: (claimId: number, action: 'approve' | 'reject') =>
    data<SchedOpenShift>(client.post(R.OPEN_SHIFT_CLAIM_DECIDE(claimId), { action })),
  cancelOpenShift: (id: number) =>
    data<SchedOpenShift>(client.post(R.OPEN_SHIFT_CANCEL(id), {})),

  gaps: (status = 'open') =>
    data<CoverageGap[]>(client.get(R.GAPS, { params: { status } })),
  gapSuggestions: (id: number) =>
    data<{ gap: CoverageGap; suggestions: GapSuggestion[] }>(client.get(R.GAP_SUGGESTIONS(id))),
  assignGap: (id: number, user_id: number) =>
    data<CoverageGap>(client.post(R.GAP_ASSIGN(id), { user_id })),
  broadcastGap: (id: number, auto_confirm: boolean) =>
    data<CoverageGap>(client.post(R.GAP_BROADCAST(id), { auto_confirm })),
  dismissGap: (id: number, note: string | null) =>
    data<CoverageGap>(client.post(R.GAP_DISMISS(id), { note })),

  availability: (start: string, end: string, department: string) =>
    data<EmployeeAvailabilityRule[]>(
      client.get(R.AVAILABILITY, {
        params: { start, end, ...(department ? { department } : {}) },
      })
    ),
};

export interface AutofillSuggestion {
  employee_id: number;
  employee_name: string | null;
  work_date: string;
  shift_template_id: number;
  shift_name: string | null;
  department: string | null;
  reasons: string[];
}
export interface AutofillUnfilled {
  work_date: string;
  shift_template_id: number;
  shift_name: string | null;
  department: string | null;
  location: string | null;
  missing: number;
}
export interface AutofillPreview {
  suggestions: AutofillSuggestion[];
  unfilled: AutofillUnfilled[];
}
