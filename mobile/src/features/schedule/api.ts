import { api } from '../../api/client';
import type {
  AvailabilityInput, AvailabilityRule, CalendarFeedStatus, Drop, OnCallDay, OpenShift, RosterWeek, ScheduleAck,
  ShiftOption, Swap, SwapCandidate, SwapCreateInput,
} from '../../api/types';

export const SCHEDULE_KEYS = {
  week: ['schedule', 'week'],
  onCall: ['schedule', 'on-call'],
  acks: ['schedule', 'acks'],
  swaps: ['schedule', 'swaps'],
  drops: ['schedule', 'drops'],
  openShifts: ['schedule', 'open-shifts'],
  availability: ['schedule', 'availability'],
  templates: ['schedule', 'templates'],
  feed: ['schedule', 'feed'],
  candidates: ['schedule', 'candidates'],
} as const;

const list = <T>(d: unknown): T[] => (Array.isArray(d) ? (d as T[]) : []);

/** GET /roster/my/week?start= (gated). Omit `start` for the current week. */
export async function fetchWeek(start?: string): Promise<RosterWeek> {
  return (await api.get<RosterWeek>('/roster/my/week', { params: start ? { start } : undefined })).data;
}
/** GET /roster/my/on-call: today .. +30 days. */
export async function fetchOnCall(): Promise<OnCallDay[]> {
  return list((await api.get('/roster/my/on-call')).data);
}
export async function fetchAcks(): Promise<ScheduleAck[]> {
  return list((await api.get('/roster/my/acks')).data);
}
export async function ackChange(id: number): Promise<void> {
  await api.post(`/roster/my/acks/${id}`);
}

export async function fetchSwaps(): Promise<Swap[]> {
  return list((await api.get('/roster/swaps/my')).data);
}
export async function fetchSwapCandidates(date: string): Promise<SwapCandidate[]> {
  return list((await api.get('/roster/swaps/candidates', { params: { date } })).data);
}
export async function createSwap(b: SwapCreateInput): Promise<Swap> {
  const body = { counterparty_id: b.counterparty_id, requester_date: b.requester_date, counterparty_date: b.counterparty_date ?? null, reason: b.reason?.trim() || null };
  return (await api.post<Swap>('/roster/swaps', body)).data;
}
export type SwapAction = 'accept' | 'decline' | 'cancel';
export async function swapAction(id: number, action: SwapAction): Promise<Swap> {
  return (await api.post<Swap>(`/roster/swaps/${id}/${action}`, {})).data;
}

export async function fetchOpenShifts(): Promise<OpenShift[]> {
  return list((await api.get('/roster/open-shifts/available')).data);
}
export async function claimOpenShift(id: number): Promise<OpenShift> {
  return (await api.post<OpenShift>(`/roster/open-shifts/${id}/claim`, {})).data;
}
export async function withdrawClaim(claimId: number): Promise<OpenShift> {
  return (await api.post<OpenShift>(`/roster/open-shifts/claims/${claimId}/withdraw`, {})).data;
}

export async function fetchDrops(): Promise<Drop[]> {
  return list((await api.get('/roster/drops/my')).data);
}
export async function createDrop(b: { work_date: string; reason: string }): Promise<Drop> {
  return (await api.post<Drop>('/roster/drops', { work_date: b.work_date, reason: b.reason.trim() })).data;
}
export async function cancelDrop(id: number): Promise<Drop> {
  return (await api.post<Drop>(`/roster/drops/${id}/cancel`, {})).data;
}

export async function fetchAvailability(): Promise<AvailabilityRule[]> {
  return list((await api.get('/roster/availability/my')).data);
}
export async function createAvailability(b: AvailabilityInput): Promise<AvailabilityRule> {
  return (await api.post<AvailabilityRule>('/roster/availability/my', b)).data;
}
export async function deleteAvailability(id: number): Promise<void> {
  await api.delete(`/roster/availability/my/${id}`);
}
/** GET /shifts/templates: readable by any authenticated user (used for pickers). */
export async function fetchShiftOptions(): Promise<ShiftOption[]> {
  return list<{ id: number; name: string }>((await api.get('/shifts/templates')).data).map((t) => ({ id: t.id, name: t.name }));
}

export async function fetchFeedStatus(): Promise<CalendarFeedStatus> {
  return (await api.get<CalendarFeedStatus>('/roster/my/calendar-feed')).data;
}
/** Creates (or rotates, invalidating the old link) the feed. The URL is returned once only. */
export async function rotateFeed(): Promise<string> {
  return (await api.post<{ url: string }>('/roster/my/calendar-feed', {})).data.url;
}
export async function deleteFeed(): Promise<void> {
  await api.delete('/roster/my/calendar-feed');
}

export const STATUS_LABEL = (s: string) => s.replace(/_/g, ' ');
export const cellText = (c: { shift_name: string | null; is_week_off: boolean } | null) => (!c ? '—' : c.is_week_off ? 'Week off' : c.shift_name || 'Shift');
/** "09:00" from "09:00:00" / "09:00"; always labelled UTC. */
export const fmtHm = (t: string | null | undefined) => (t ? `${t.slice(0, 5)} UTC` : '—');
export const fmtRange = (a: string | null | undefined, b: string | null | undefined) => (a ? `${a.slice(0, 5)}–${(b ?? '').slice(0, 5)} UTC` : '');
export const WEEKDAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
