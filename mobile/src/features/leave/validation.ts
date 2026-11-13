import type { ApplyPayload, LeaveType, PickedFile } from './api';

export type LeaveFormValues = {
  typeId: number | null;
  start: string;
  end: string;
  halfDay: boolean;
  session: 'morning' | 'afternoon';
  reason: string;
  emergency: boolean;
  emergencyContact: string;
  attachment: PickedFile | null;
};
export type LeaveFormErrors = Partial<Record<'type' | 'start' | 'end' | 'reason' | 'half' | 'attachment', string>>;

export const ALLOWED_PROOF_TYPES = ['application/pdf', 'image/jpeg', 'image/png', 'image/webp', 'image/heic'];
export const MAX_PROOF_BYTES = 10 * 1024 * 1024;
/** The backend caps leave.emergency_backdate_days at 31; the configured value (default 3) is not readable by employees. */
export const EMERGENCY_MAX_BACKDATE_DAYS = 31;
const DAY_MS = 86_400_000;

/** Parses a strict YYYY-MM-DD calendar date (rejects 2026-02-30) to a UTC day number, else null. */
function dayNumber(s: string): number | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s);
  if (!m) return null;
  const [y, mo, d] = [Number(m[1]), Number(m[2]), Number(m[3])];
  const t = Date.UTC(y, mo - 1, d);
  const back = new Date(t);
  if (back.getUTCFullYear() !== y || back.getUTCMonth() !== mo - 1 || back.getUTCDate() !== d) return null;
  return t / DAY_MS;
}

export function leaveDays(start: string, end: string, halfDay: boolean): number {
  const a = dayNumber(start);
  const b = dayNumber(end);
  if (a == null || b == null || b < a) return 0;
  return halfDay ? 0.5 : b - a + 1;
}

/** Mirrors the backend: the type's certificate rule applies from N days; emergency leave defers it (proof_due_date). */
export function certRequired(type: LeaveType | undefined, days: number, emergency: boolean): boolean {
  const thr = type?.requires_medical_cert_after;
  return !emergency && !!thr && days >= thr;
}

export function validateAttachment(f: PickedFile): string | null {
  if (!ALLOWED_PROOF_TYPES.includes(f.mimeType.toLowerCase())) return 'Only PDF, JPEG, PNG, WebP or HEIC files are allowed.';
  if ((f.size ?? 0) > MAX_PROOF_BYTES) return 'File must be under 10 MB.';
  return null;
}

/** `today` is a YYYY-MM-DD string (injected for tests). */
export function validateLeaveForm(v: LeaveFormValues, type: LeaveType | undefined, today: string): LeaveFormErrors {
  const e: LeaveFormErrors = {};
  if (v.typeId == null || !type) e.type = 'Choose a leave type.';
  const start = dayNumber(v.start);
  const end = dayNumber(v.end);
  if (!v.start.trim()) e.start = 'Enter a start date.';
  else if (start == null) e.start = 'Use the format YYYY-MM-DD.';
  if (!v.end.trim()) e.end = 'Enter an end date.';
  else if (end == null) e.end = 'Use the format YYYY-MM-DD.';
  if (start != null && end != null && end < start) e.end = 'End date cannot be before the start date.';
  if (!v.reason.trim()) e.reason = 'Enter a reason.';

  if (v.halfDay) {
    if (start != null && end != null && start !== end) e.half = 'A half day must be a single day.';
    else if (type && type.allow_half_day === false) e.half = `${type.name} does not allow half-day leave.`;
  }
  if (v.emergency && start != null) {
    const t = dayNumber(today);
    if (t != null && start < t - EMERGENCY_MAX_BACKDATE_DAYS) e.start = `Emergency leave can start at most ${EMERGENCY_MAX_BACKDATE_DAYS} days in the past.`;
  }
  if (v.attachment) {
    const bad = validateAttachment(v.attachment);
    if (bad) e.attachment = bad;
  } else if (type && certRequired(type, leaveDays(v.start, v.end, v.halfDay), v.emergency)) {
    e.attachment = `A medical certificate is required for ${type.requires_medical_cert_after}+ days of ${type.name}.`;
  }
  return e;
}

export function buildApplyPayload(v: LeaveFormValues, attachmentUrl: string | null): ApplyPayload {
  return {
    leave_type_id: v.typeId as number,
    start_date: v.start,
    end_date: v.halfDay ? v.start : v.end,
    reason: v.reason.trim(),
    emergency_contact: v.emergencyContact.trim() || null,
    is_half_day: v.halfDay,
    half_day_session: v.halfDay ? v.session : null,
    attachment_url: attachmentUrl,
    is_emergency: v.emergency,
  };
}

/** Local calendar date as YYYY-MM-DD. */
export function todayIso(now = new Date()): string {
  const p = (n: number) => String(n).padStart(2, '0');
  return `${now.getFullYear()}-${p(now.getMonth() + 1)}-${p(now.getDate())}`;
}
