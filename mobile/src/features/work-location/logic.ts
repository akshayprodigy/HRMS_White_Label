import { fmtUtcDate } from '../../lib/time';
import type { WorkLocationKind, WorkLocationRequest } from './api';

export const KIND_LABEL: Record<WorkLocationKind, string> = { on_duty: 'On duty', client_visit: 'Client visit', wfh: 'Work from home' };
/** Pending is NOT granted: it only counts once a person approves it. */
export const STATUS_LABEL: Record<string, string> = { pending: 'Pending approval', approved: 'Approved', rejected: 'Rejected', cancelled: 'Cancelled' };
const PORTION: Record<string, string> = { first_half: ' (first half)', second_half: ' (second half)' };

export const needsPlace = (k: string) => k === 'on_duty' || k === 'client_visit';

export const fmtRange = (r: Pick<WorkLocationRequest, 'start_date' | 'end_date' | 'day_portion'>) =>
  (r.start_date === r.end_date ? fmtUtcDate(r.start_date) : `${fmtUtcDate(r.start_date)} – ${fmtUtcDate(r.end_date)}`) + (PORTION[r.day_portion] ?? '');

/** Only pending/approved can be cancelled, and not once started (HR may; the server stays authoritative). `today` is org-local. */
export const canCancel = (r: WorkLocationRequest, today: string) => (r.status === 'pending' || r.status === 'approved') && r.start_date >= today;

/** An APPROVED request covering the org-local `today`; pending/rejected/cancelled never relax anything. */
export function approvedToday(items: WorkLocationRequest[] | undefined, today: string): WorkLocationRequest | null {
  return (items ?? []).find((r) => r.status === 'approved' && r.start_date <= today && today <= r.end_date) ?? null;
}
export const approvedBannerText = (r: WorkLocationRequest) => `Approved ${KIND_LABEL[r.kind] ?? r.kind} today${PORTION[r.day_portion] ?? ''} — location check relaxed`;
