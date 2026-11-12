import { client } from '../../api/client';
import { ENDPOINTS } from '../../api/endpoints';

export interface ShiftOption {
  id: number;
  name: string;
}

export interface AvailabilityRule {
  id: number;
  kind: 'unavailable' | 'preferred';
  weekday: number | null;
  specific_date: string | null;
  shift_template_id: number | null;
  valid_from: string | null;
  valid_to: string | null;
  note: string | null;
}
export interface AvailabilityInput {
  kind: 'unavailable' | 'preferred';
  weekday: number | null;
  specific_date: string | null;
  shift_template_id: number | null;
  valid_from: string | null;
  valid_to: string | null;
  note: string | null;
}

export interface SwapCell {
  shift_template_id: number | null;
  shift_name: string | null;
  is_week_off: boolean;
}
export interface SwapExchangedCell {
  user_id: number;
  work_date: string;
  before: SwapCell;
  after: SwapCell;
}
export interface Swap {
  id: number;
  requester_id: number;
  requester_name: string | null;
  counterparty_id: number;
  counterparty_name: string | null;
  requester_date: string;
  counterparty_date: string;
  reason: string | null;
  status: string;
  requester_cell: SwapCell | null;
  counterparty_cell: SwapCell | null;
  decision_note: string | null;
  created_at: string | null;
  direction: 'incoming' | 'outgoing' | null;
  cells: SwapExchangedCell[];
}
export interface SwapCandidate {
  user_id: number;
  name: string | null;
  shift_template_id: number | null;
  shift_name: string | null;
  is_week_off: boolean;
}

export interface OpenShift {
  id: number;
  work_date: string;
  shift_name: string | null;
  shift_start: string | null;
  shift_end: string | null;
  department: string | null;
  location: string | null;
  note: string | null;
  slots: number;
  filled: number;
  my_claim_id: number | null;
  my_claim_status: string | null;
  warnings: string[];
}

export interface Drop {
  id: number;
  work_date: string;
  shift_name: string | null;
  shift_start: string | null;
  shift_end: string | null;
  reason: string;
  status: string;
  decision_note: string | null;
}

export interface CalendarFeedStatus {
  active: boolean;
  created_at: string | null;
}

const R = ENDPOINTS.ROSTER;
const data = async <T,>(p: Promise<{ data: T }>): Promise<T> => (await p).data;

export const mySchedule = {
  listAvailability: () => data<AvailabilityRule[]>(client.get(R.AVAILABILITY_MY)),
  createAvailability: (b: AvailabilityInput) =>
    data<AvailabilityRule>(client.post(R.AVAILABILITY_MY, b)),
  deleteAvailability: (id: number) => client.delete(R.AVAILABILITY_MY_DETAIL(id)),

  swapCandidates: (date: string) =>
    data<SwapCandidate[]>(client.get(R.SWAP_CANDIDATES, { params: { date } })),
  createSwap: (b: {
    counterparty_id: number;
    requester_date: string;
    counterparty_date?: string | null;
    reason?: string | null;
  }) => data<Swap>(client.post(R.SWAPS, b)),
  mySwaps: () => data<Swap[]>(client.get(R.SWAPS_MY)),
  swapAction: (id: number, action: 'accept' | 'decline' | 'cancel') =>
    data<Swap>(client.post(R.SWAP_ACTION(id, action), {})),

  availableOpenShifts: () => data<OpenShift[]>(client.get(R.OPEN_SHIFTS_AVAILABLE)),
  claim: (id: number) => data<OpenShift>(client.post(R.OPEN_SHIFT_CLAIM(id), {})),
  withdraw: (claimId: number) =>
    data<OpenShift>(client.post(R.OPEN_SHIFT_CLAIM_WITHDRAW(claimId), {})),

  createDrop: (b: { work_date: string; reason: string }) =>
    data<Drop>(client.post(R.DROPS, b)),
  myDrops: () => data<Drop[]>(client.get(R.DROPS_MY)),
  cancelDrop: (id: number) => data<Drop>(client.post(R.DROP_CANCEL(id), {})),

  feedStatus: () => data<CalendarFeedStatus>(client.get(R.CALENDAR_FEED)),
  rotateFeed: () => data<{ url: string }>(client.post(R.CALENDAR_FEED, {})),
  deleteFeed: () => client.delete(R.CALENDAR_FEED),
};

export const WEEKDAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];

export const fmtDate = (iso: string) =>
  new Date(iso + 'T00:00:00').toLocaleDateString('en-IN', {
    weekday: 'short', day: 'numeric', month: 'short',
  });
export const fmtDateShort = (iso: string) =>
  new Date(iso + 'T00:00:00').toLocaleDateString('en-IN', { day: 'numeric', month: 'short' });
export const fmtDateYear = (iso: string) =>
  new Date(iso + 'T00:00:00').toLocaleDateString('en-IN', {
    day: 'numeric', month: 'short', year: 'numeric',
  });

export const STATUS_TONE: Record<string, 'success' | 'error' | 'warning' | 'neutral' | 'info'> = {
  approved: 'success',
  confirmed: 'success',
  accepted: 'info',
  rejected: 'error',
  declined: 'error',
  pending: 'warning',
  pending_peer: 'warning',
  pending_approval: 'warning',
  cancelled: 'neutral',
  withdrawn: 'neutral',
  expired: 'neutral',
};
export const statusLabel = (s: string) => s.replace(/_/g, ' ');

export const inputCls =
  'w-full h-10 px-3 rounded-lg border border-slate-200 text-sm text-[#0F172A] ' +
  'focus:outline-none focus:ring-2 focus:ring-blue-600/30 focus:border-blue-500 bg-white';
export const labelCls = 'text-[9px] font-black uppercase tracking-widest text-slate-400';
