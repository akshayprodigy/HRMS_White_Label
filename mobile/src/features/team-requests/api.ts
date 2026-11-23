import { api, ApiError } from '../../api/client';
import { isGateError } from '../attendance/gate';
import type { DayPortion, WorkLocationKind } from '../work-location/api';

/** GET /work-location-requests?status=pending (manager / HR scoped by the server). */
export type TeamWorkLocation = {
  id: number;
  user_name: string | null;
  kind: WorkLocationKind;
  start_date: string;
  end_date: string;
  day_portion: DayPortion;
  place: string | null;
  purpose: string;
  can_decide: boolean;
};
/** GET /holidays/picks?status=pending. */
export type TeamPick = {
  id: number;
  user_name: string | null;
  holiday: { id: number; name: string; date: string; location: string } | null;
  reason: string | null;
  can_decide: boolean;
};

export const TEAM_KEYS = { workLocation: ['team-requests', 'work-location'], picks: ['team-requests', 'picks'] } as const;

/** Only rows this viewer may decide. A plain 403 means "no reports / not an approver": hidden quietly (empty). */
export const decidable = <T extends { can_decide: boolean }>(rows: unknown): T[] => (Array.isArray(rows) ? (rows as T[]).filter((r) => r?.can_decide === true) : []);

async function listPending<T extends { can_decide: boolean }>(url: string): Promise<T[]> {
  try {
    return decidable<T>((await api.get(url, { params: { status: 'pending' } })).data);
  } catch (e) {
    if (e instanceof ApiError && e.status === 403 && !isGateError(e)) return [];
    throw e;
  }
}
export const fetchTeamWorkLocation = () => listPending<TeamWorkLocation>('/work-location-requests');
export const fetchTeamPicks = () => listPending<TeamPick>('/holidays/picks');

export type DecideInput = { id: number; approve: boolean; note: string };
const body = (v: DecideInput) => ({ approve: v.approve, note: v.note.trim() || null });
export const decideWorkLocation = async (v: DecideInput) => (await api.post(`/work-location-requests/${v.id}/decide`, body(v))).data;
export const decidePick = async (v: DecideInput) => (await api.post(`/holidays/picks/${v.id}/decide`, body(v))).data;
