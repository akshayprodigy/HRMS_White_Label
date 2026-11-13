import type { AvailabilityInput, AvailabilityKind, AvailabilityRule, ShiftOption } from '../../api/types';
import { fmtUtcDate } from '../../lib/time';
import { WEEKDAYS } from './api';
import { isIsoDate } from './dates';

export type AvailabilityForm = {
  kind: AvailabilityKind;
  mode: 'weekday' | 'date';
  weekday: number;
  specificDate: string;
  shiftId: number | null;
  validFrom: string;
  validTo: string;
  note: string;
};
export const EMPTY_AVAILABILITY: AvailabilityForm = { kind: 'unavailable', mode: 'weekday', weekday: 0, specificDate: '', shiftId: null, validFrom: '', validTo: '', note: '' };

/** Mirrors backend roster_availability._validate (+ web form checks). */
export function validateAvailability(f: AvailabilityForm, today: string): string | null {
  if (f.kind === 'preferred' && f.shiftId == null) return 'Pick the shift you prefer.';
  if (f.mode === 'date') {
    if (!isIsoDate(f.specificDate.trim())) return 'Enter the date as YYYY-MM-DD.';
    if (f.specificDate.trim() < today) return 'That date is in the past. Pick today or a later date.';
    return null;
  }
  const from = f.validFrom.trim();
  const to = f.validTo.trim();
  if (from && !isIsoDate(from)) return '"From" must be a date as YYYY-MM-DD.';
  if (to && !isIsoDate(to)) return '"Until" must be a date as YYYY-MM-DD.';
  if (from && to && from > to) return '"From" must be on or before "Until".';
  return null;
}

/** valid_from/valid_to apply to weekday rules only (backend rejects them on a specific date). */
export function toAvailabilityInput(f: AvailabilityForm): AvailabilityInput {
  const wk = f.mode === 'weekday';
  return {
    kind: f.kind,
    weekday: wk ? f.weekday : null,
    specific_date: wk ? null : f.specificDate.trim(),
    shift_template_id: f.shiftId,
    valid_from: wk && f.validFrom.trim() ? f.validFrom.trim() : null,
    valid_to: wk && f.validTo.trim() ? f.validTo.trim() : null,
    note: f.note.trim() || null,
  };
}

export function ruleText(r: AvailabilityRule, shifts: ShiftOption[]): string {
  const shiftName = r.shift_template_id ? shifts.find((s) => s.id === r.shift_template_id)?.name || 'a shift' : null;
  const wk = r.weekday != null ? WEEKDAYS[r.weekday]?.slice(0, 3) : null;
  const bounds = [r.valid_from ? `from ${fmtUtcDate(r.valid_from)}` : '', r.valid_to ? `until ${fmtUtcDate(r.valid_to)}` : ''].filter(Boolean).join(' ');
  const b = bounds ? ` (${bounds})` : '';
  if (r.kind === 'unavailable') {
    const when = wk ? `every ${wk}` : r.specific_date ? `on ${fmtUtcDate(r.specific_date)}` : '';
    return `Unavailable${shiftName ? ` for ${shiftName}` : ''} ${when}${b}`.trim();
  }
  const when = wk ? `on ${wk}` : r.specific_date ? `on ${fmtUtcDate(r.specific_date)}` : '';
  return `Prefers ${shiftName || 'a shift'} ${when}${b}`.trim();
}
