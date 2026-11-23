import type { DayPortion, RequestPayload, WorkLocationKind } from './api';
import { needsPlace } from './logic';

export type RequestFormValues = { kind: WorkLocationKind; start: string; end: string; portion: DayPortion; place: string; purpose: string };
export type RequestFormErrors = Partial<Record<'start' | 'end' | 'place' | 'purpose' | 'portion', string>>;

/** Strict YYYY-MM-DD calendar date (rejects 2026-02-30). */
export function isIsoDate(s: string): boolean {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s);
  if (!m) return false;
  const [y, mo, d] = [Number(m[1]), Number(m[2]), Number(m[3])];
  const t = new Date(Date.UTC(y, mo - 1, d));
  return t.getUTCFullYear() === y && t.getUTCMonth() === mo - 1 && t.getUTCDate() === d;
}

export function validateRequest(v: RequestFormValues): RequestFormErrors {
  const e: RequestFormErrors = {};
  if (!v.start.trim()) e.start = 'Enter a start date.';
  else if (!isIsoDate(v.start)) e.start = 'Use the format YYYY-MM-DD.';
  if (!v.end.trim()) e.end = 'Enter an end date.';
  else if (!isIsoDate(v.end)) e.end = 'Use the format YYYY-MM-DD.';
  if (!e.start && !e.end && v.end < v.start) e.end = 'End date cannot be before the start date.';
  if (v.portion !== 'full' && v.start !== v.end) e.portion = 'Half days are for a single date.';
  if (needsPlace(v.kind) && !v.place.trim()) e.place = 'Place is required.';
  if (!v.purpose.trim()) e.purpose = 'Please give a purpose.';
  return e;
}

export function buildRequestPayload(v: RequestFormValues): RequestPayload {
  const single = v.start === v.end;
  return {
    kind: v.kind,
    start_date: v.start,
    end_date: v.end,
    day_portion: single ? v.portion : 'full',
    place: needsPlace(v.kind) ? v.place.trim() : v.place.trim() || null,
    purpose: v.purpose.trim(),
  };
}
