import { api } from '../../api/client';
import type { MyBroadcast } from '../../api/types';

export const BROADCASTS_KEY = ['broadcasts-my'] as const;

export async function fetchMyBroadcasts(): Promise<MyBroadcast[]> {
  const d = (await api.get<MyBroadcast[]>('/broadcasts/my')).data;
  return Array.isArray(d) ? d : [];
}

/** What the backend counts as "responded" (broadcasts._my_row.pending): safety check > ack > read. */
export type RequiredResponse = 'safety' | 'ack' | 'read';
export function requiredResponse(b: Pick<MyBroadcast, 'safety_check' | 'requires_ack'>): RequiredResponse {
  return b.safety_check ? 'safety' : b.requires_ack ? 'ack' : 'read';
}

export const isCritical = (b: Pick<MyBroadcast, 'severity'>) => b.severity === 'critical';

export async function markSafety(id: number, status: 'safe' | 'need_help', note?: string): Promise<MyBroadcast> {
  const n = note?.trim();
  return (await api.post<MyBroadcast>(`/broadcasts/${id}/safety`, { status, note: n ? n : undefined })).data;
}
export async function acknowledge(id: number): Promise<MyBroadcast> {
  return (await api.post<MyBroadcast>(`/broadcasts/${id}/ack`)).data;
}
export async function markRead(id: number): Promise<MyBroadcast> {
  return (await api.post<MyBroadcast>(`/broadcasts/${id}/read`)).data;
}
