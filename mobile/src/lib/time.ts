/** Backend timestamps are UTC; some are serialised without a zone suffix, so assume UTC when absent. */
const DATE_ONLY = /^\d{4}-\d{2}-\d{2}$/;
const HAS_ZONE = /([zZ]|[+-]\d{2}:?\d{2})$/;

export function parseUtc(iso: string): Date {
  if (DATE_ONLY.test(iso)) return new Date(`${iso}T00:00:00Z`);
  return new Date(HAS_ZONE.test(iso) ? iso : `${iso}Z`);
}

const pad = (n: number) => String(n).padStart(2, '0');

/** "09:05 UTC" from an ISO timestamp, or an em dash. */
export function fmtUtcTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = parseUtc(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())} UTC`;
}

/** "14 Nov" from an ISO timestamp (UTC calendar date). */
export function fmtUtcDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = parseUtc(iso);
  if (Number.isNaN(d.getTime())) return '—';
  const m = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][d.getUTCMonth()];
  return `${d.getUTCDate()} ${m}`;
}

/** Roster shift times are "HH:MM" org-local wall-clock strings (no zone label). */
export function fmtShiftTime(hhmm: string | null | undefined): string {
  return hhmm ? hhmm.slice(0, 5) : '—';
}

export function fmtInr(paise: number | null | undefined): string {
  if (paise == null) return '';
  return `₹${(paise / 100).toLocaleString('en-IN', { maximumFractionDigits: 2 })}`;
}
