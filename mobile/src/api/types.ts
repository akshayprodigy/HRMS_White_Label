// Shapes read from backend/app/schemas + endpoints (see mobile/README.md "API shapes").

export type AttendanceRow = {
  id: number;
  captured_at: string;
  punch_out_time: string | null;
  work_date?: string | null;
  [k: string]: unknown;
};
/** GET /attendance/today (not gated). */
export type AttendanceToday = { is_marked: boolean; attendance: AttendanceRow | null };

export type ShiftInfo = {
  name: string;
  start_time: string | null; // "HH:MM" UTC
  end_time: string | null;
  is_overnight: boolean;
  source: 'roster' | 'assigned' | 'default';
  transport_required?: boolean;
  /** Set for roster and assigned shifts; absent for the org default. */
  shift_template_id?: number;
};
export type RosterDay = {
  date: string;
  is_today: boolean;
  /** Sundays only (server rule); a published roster shift still wins. */
  is_weekend?: boolean;
  holiday_name: string | null;
  on_leave: boolean;
  leave_type: string | null;
  shift: ShiftInfo;
};
/** GET /roster/my/week (gated). */
export type RosterWeek = { start: string; days: RosterDay[] };

/** GET /broadcasts/my (not gated). */
export type MyBroadcast = {
  id: number;
  title: string;
  message: string;
  severity: string;
  requires_ack: boolean;
  safety_check: boolean;
  created_at: string | null;
  pending: boolean;
};

/** GET /approvals/inbox item. */
export type LegacyInboxItem = {
  id: number;
  resource_type: string;
  resource_id: string;
  status: string;
  current_step_number: number;
  requested_by_id: number | null;
  requested_by_name: string | null;
  created_at: string;
  due_date: string | null;
  due_at: string | null;
  is_overdue: boolean;
  acting_for: { user_id: number; name: string | null } | null;
  steps?: { step_number: number; status: string; [k: string]: unknown }[];
};

/** GET /approval-chains/my-queue item. */
export type ChainQueueItem = {
  step_instance: { id: number; step_order: number; label: string | null; approver_type: string };
  instance: { id: number; entity_type: string; submitter_id: number; amount_paise: number | null; created_at: string };
  entity: {
    kind: string;
    title?: string;
    purpose?: string;
    amount_paise?: number | null;
    description?: string;
    from_city?: string;
    to_city?: string;
    line_count?: number;
    out_of_policy_count?: number;
  } | null;
  due_at: string | null;
  is_overdue: boolean;
  acting_for: { user_id: number; name: string | null } | null;
};

export type BulkResult = {
  results: { kind: string; id: number; ok: boolean; error: string | null }[];
  ok_count: number;
  failed_count: number;
};

/* ---- Schedule self-service (ported from frontend my-schedule-api.ts; verified against backend schemas) ---- */

export type ShiftOption = { id: number; name: string };

export type AvailabilityKind = 'unavailable' | 'preferred';
/** GET/POST /roster/availability/my. Exactly one of weekday (0=Mon..6=Sun) / specific_date. */
export type AvailabilityRule = {
  id: number;
  kind: AvailabilityKind;
  weekday: number | null;
  specific_date: string | null;
  shift_template_id: number | null;
  valid_from: string | null;
  valid_to: string | null;
  note: string | null;
};
export type AvailabilityInput = Omit<AvailabilityRule, 'id'>;

export type SwapCell = { shift_template_id: number | null; shift_name: string | null; is_week_off: boolean };
export type SwapStatus = 'pending_peer' | 'pending_approval' | 'approved' | 'declined' | 'rejected' | 'cancelled' | 'expired' | (string & {});
/** GET /roster/swaps/my (direction is relative to the caller). */
export type Swap = {
  id: number;
  requester_id: number;
  requester_name: string | null;
  counterparty_id: number;
  counterparty_name: string | null;
  requester_date: string;
  counterparty_date: string;
  reason: string | null;
  status: SwapStatus;
  requester_cell: SwapCell | null;
  counterparty_cell: SwapCell | null;
  decision_note: string | null;
  created_at: string | null;
  direction: 'incoming' | 'outgoing' | null;
};
/** GET /roster/swaps/candidates?date= (same-department colleagues and their cell that day). */
export type SwapCandidate = { user_id: number; name: string | null; shift_template_id: number | null; shift_name: string | null; is_week_off: boolean };
export type SwapCreateInput = { counterparty_id: number; requester_date: string; counterparty_date?: string | null; reason?: string | null };

/** GET /roster/open-shifts/available (already filtered for the caller's eligibility). */
export type OpenShift = {
  id: number;
  work_date: string;
  shift_name: string | null;
  shift_start: string | null; // "HH:MM[:SS]" UTC
  shift_end: string | null;
  department: string | null;
  location: string | null;
  note: string | null;
  slots: number;
  filled: number;
  my_claim_id: number | null;
  my_claim_status: string | null;
  warnings: string[];
};

/** GET /roster/drops/my (give-away requests). */
export type Drop = {
  id: number;
  work_date: string;
  shift_name: string | null;
  shift_start: string | null;
  shift_end: string | null;
  reason: string;
  status: string;
  decision_note: string | null;
};

/** GET /roster/my/acks: emergency (lock-window) roster changes still to acknowledge. */
export type ScheduleAck = {
  id: number;
  work_date: string;
  old_shift_name: string | null;
  old_is_week_off: boolean;
  new_shift_name: string | null;
  new_is_week_off: boolean;
  reason: string | null;
};

/** GET /roster/my/on-call (times are "HH:MM" UTC). */
export type OnCallDay = { id: number; work_date: string; start_time: string; end_time: string; is_overnight: boolean; note: string | null };

export type CalendarFeedStatus = { active: boolean; created_at: string | null };
