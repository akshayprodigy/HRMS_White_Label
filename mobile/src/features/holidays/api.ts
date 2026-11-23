import { api } from '../../api/client';

export type HolidayPick = { id: number; status: string; decision_note?: string | null };
export type MyHoliday = { id: number; name: string; date: string; location: string; is_optional: boolean; pick: HolidayPick | null };
/** GET /holidays/my: the latest pick per holiday in ANY status; quota counts pending + approved. */
export type MyHolidays = { quota: number; used: number; remaining: number; year: number; holidays: MyHoliday[] };

export const HOLIDAY_KEYS = { my: ['holidays', 'my'] } as const;

/** Omit `year` so the backend uses the org-local year. */
export async function fetchMyHolidays(year?: number | null): Promise<MyHolidays> {
  return (await api.get<MyHolidays>('/holidays/my', { params: year ? { year } : {} })).data;
}
export async function pickHoliday(v: { holidayId: number; reason: string }): Promise<unknown> {
  return (await api.post('/holidays/picks', { holiday_id: v.holidayId, reason: v.reason.trim() || null })).data;
}
export async function cancelPick(pickId: number): Promise<unknown> {
  return (await api.post(`/holidays/picks/${pickId}/cancel`)).data;
}
