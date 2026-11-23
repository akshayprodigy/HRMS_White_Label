import type { RosterDay, SwapCandidate } from '../../api/types';

/** Backend limits (services/shift_swap: MAX_AHEAD_DAYS / MAX_GAP_DAYS). */
export const MAX_AHEAD_DAYS = 90;
export const MAX_GAP_DAYS = 14;

const ISO = /^\d{4}-\d{2}-\d{2}$/;
const DAY_MS = 86_400_000;
const toMs = (iso: string) => Date.parse(`${iso}T00:00:00Z`);
const fromMs = (ms: number) => new Date(ms).toISOString().slice(0, 10);

// "Today" for rosters is the ORG-local date (backend local_today): use useOrgToday() / orgToday() from lib/org-time, never the UTC date.
export const isIsoDate = (s: string) => ISO.test(s) && !Number.isNaN(toMs(s)) && fromMs(toMs(s)) === s;
export const addDays = (iso: string, n: number) => fromMs(toMs(iso) + n * DAY_MS);
export const daysBetween = (a: string, b: string) => Math.round((toMs(b) - toMs(a)) / DAY_MS);

/** Monday of the ISO week containing `iso` (matches GET /roster/my/week's default week). */
export function weekStartOf(iso: string): string {
  const dow = (new Date(`${iso}T00:00:00Z`).getUTCDay() + 6) % 7; // Mon=0
  return addDays(iso, -dow);
}

/** Monday week starts that together cover every day of `ym` ("YYYY-MM"). */
export function monthWeekStarts(ym: string): string[] {
  const first = `${ym}-01`;
  const [y, m] = ym.split('-').map(Number);
  const last = fromMs(Date.UTC(y, m, 0));
  const out: string[] = [];
  for (let w = weekStartOf(first); w <= last; w = addDays(w, 7)) out.push(w);
  return out;
}
export const shiftMonth = (ym: string, delta: number): string => {
  const [y, m] = ym.split('-').map(Number);
  return new Date(Date.UTC(y, m - 1 + delta, 1)).toISOString().slice(0, 7);
};

export function isWeekOffDay(d: RosterDay): boolean {
  return d.shift.name === 'Week off' || (!!d.is_weekend && d.shift.source !== 'roster');
}

/** A published roster shift (not an assigned/default one) today or later can be swapped or given away. */
export function canActOnDay(d: RosterDay, today: string): boolean {
  return d.shift.source === 'roster' && !!d.shift.start_time && !d.on_leave && d.date >= today;
}

export type MyCell = { shiftTemplateId: number | null; shiftName: string | null; isWeekOff: boolean };

/** A colleague whose cell equals mine that day gains nothing from a swap. */
export function sameShift(c: SwapCandidate, mine: MyCell): boolean {
  if (mine.isWeekOff) return c.is_week_off;
  if (c.is_week_off) return false;
  if (mine.shiftTemplateId != null) return c.shift_template_id === mine.shiftTemplateId;
  return !!mine.shiftName && c.shift_name === mine.shiftName;
}

/** Return-date problem or null; only meaningful when the "different day in return" option is on. */
export function validateReturnDate(date: string, returnDate: string, today: string): string | null {
  const bad = `Pick a return date between today and ${addDays(today, MAX_AHEAD_DAYS)} that differs from ${date}, or untick the option.`;
  if (!isIsoDate(returnDate) || returnDate === date || returnDate < today || returnDate > addDays(today, MAX_AHEAD_DAYS)) return bad;
  if (Math.abs(daysBetween(date, returnDate)) > MAX_GAP_DAYS) return `The two dates must be within ${MAX_GAP_DAYS} days of each other.`;
  return null;
}

export function validateSwap(v: { date: string; today: string; pick: number | null; cands: SwapCandidate[]; mine: MyCell; otherDay: boolean; returnDate: string }): string | null {
  const chosen = v.cands.find((c) => c.user_id === v.pick);
  if (!v.pick || !chosen || sameShift(chosen, v.mine)) return 'Pick a colleague to swap with.';
  if (v.otherDay) return validateReturnDate(v.date, v.returnDate.trim(), v.today);
  return null;
}

export type DayLabel = { title: string; times: string | null; transport: boolean; muted: boolean };
/** What to show for a roster day; times are org-local wall-clock. */
export function dayLabel(d: RosterDay): DayLabel {
  if (d.on_leave) return { title: d.leave_type ? `On leave (${d.leave_type})` : 'On leave', times: null, transport: false, muted: true };
  if (isWeekOffDay(d)) return { title: 'Week off', times: null, transport: false, muted: true };
  const s = d.shift;
  const times = s.start_time && s.end_time ? `${s.start_time}–${s.end_time}${s.is_overnight ? ' (+1 day)' : ''}` : null;
  return { title: s.name, times, transport: !!s.transport_required, muted: false };
}

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
/** "2026-11" -> "November 2026". */
export const monthName = (ym: string) => `${MONTHS[Number(ym.slice(5, 7)) - 1]} ${ym.slice(0, 4)}`;
