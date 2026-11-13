import { parseUtc } from '../../lib/time';
import type { FieldStatus } from './api';

export const STATUS_META: Record<FieldStatus, { label: string; color: string }> = {
  no_show: { label: 'No-show', color: '#DC2626' },
  running_late: { label: 'Running late', color: '#2563EB' },
  not_arrived: { label: 'Not arrived', color: '#D97706' },
  on_shift: { label: 'On shift', color: '#16A34A' },
  upcoming: { label: 'Upcoming', color: '#2563EB' },
  completed: { label: 'Completed', color: '#64748B' },
  on_leave: { label: 'On leave', color: '#64748B' },
  off: { label: 'Off', color: '#64748B' },
};

export function lastSeen(iso: string, now: number = Date.now()): string {
  const mins = Math.max(0, Math.round((now - parseUtc(iso).getTime()) / 60_000));
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins} min ago`;
  return `${Math.floor(mins / 60)} h ${mins % 60} min ago`;
}
export const utcDay = (now: number = Date.now(), offsetDays = 0) => new Date(now - offsetDays * 86_400_000).toISOString().slice(0, 10);
