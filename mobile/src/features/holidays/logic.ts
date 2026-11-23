import type { MyHoliday } from './api';

/** Pending is NOT a granted holiday: it only becomes one once a person approves it. */
export const PICK_LABEL: Record<string, string> = { pending: 'Pending approval', approved: 'Approved', rejected: 'Rejected', cancelled: 'Cancelled' };

export const isActivePick = (h: MyHoliday) => h.pick?.status === 'pending' || h.pick?.status === 'approved';

/** `today` is the ORG-local date (YYYY-MM-DD); both sides are date-only strings, so string compare is exact. */
export const isPast = (h: MyHoliday, today: string) => h.date < today;

/** `ready` = org time has loaded; until then "today" is a UTC guess, so past-checks cannot be trusted and actions stay disabled. */
export function pickAction(h: MyHoliday, today: string, remaining: number, ready = true): { kind: 'cancel' | 'pick' | 'pick_again' | null; disabled: boolean } {
  if (!h.is_optional) return { kind: null, disabled: true };
  const past = !ready || isPast(h, today);
  if (isActivePick(h)) return { kind: 'cancel', disabled: past };
  return { kind: h.pick?.status === 'rejected' ? 'pick_again' : 'pick', disabled: past || remaining <= 0 };
}
