export type WorkLocationKind = 'on_duty' | 'client_visit' | 'wfh';

export interface WorkLocationRequest {
  id: number;
  user_id: number;
  user_name: string | null;
  kind: WorkLocationKind;
  start_date: string;
  end_date: string;
  day_portion: 'full' | 'first_half' | 'second_half';
  place: string | null;
  purpose: string;
  status: 'pending' | 'approved' | 'rejected' | 'cancelled';
  routed_via: 'direct' | 'chain';
  can_decide: boolean;
  summary: string;
  decision_note: string | null;
}

export const KIND_LABEL: Record<WorkLocationKind, string> = {
  on_duty: 'On duty',
  client_visit: 'Client visit',
  wfh: 'Work from home',
};

/** On duty and client visit need a place. */
export const needsPlace = (k: string) => k === 'on_duty' || k === 'client_visit';

export const fmtDay = (iso: string) => {
  const [y, m, d] = iso.split('-').map(Number);
  // Pure calendar date: format in UTC so the browser zone cannot shift it.
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString(undefined, {
    day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC',
  });
};

const PORTION: Record<string, string> = { first_half: ' (first half)', second_half: ' (second half)' };

export const fmtRange = (r: WorkLocationRequest) =>
  (r.start_date === r.end_date ? fmtDay(r.start_date) : `${fmtDay(r.start_date)} – ${fmtDay(r.end_date)}`) +
  (PORTION[r.day_portion] || '');
