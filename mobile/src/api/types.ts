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
};
export type RosterDay = {
  date: string;
  is_today: boolean;
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
