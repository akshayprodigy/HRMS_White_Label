import { useCallback, useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';
import { errMsg } from '../schedule-delegations-utils';
import {
  addDays,
  daysBetween,
  schedulerApi,
  type EmployeeAvailabilityRule,
  type ShiftTemplateLite,
} from './roster-api';

export interface AvailabilityMark {
  /** unavailable for the whole day */
  blocked: boolean;
  /** unavailable only for specific shifts (names) */
  shiftBlocked: string[];
  /** preferred shifts (names) */
  prefers: string[];
  /** human lines for tooltip / screen readers */
  lines: string[];
}

interface Loaded {
  start: string;
  end: string;
  department: string;
  rules: EmployeeAvailabilityRule[];
}

/** Mon=0 … Sun=6, same as the backend's date.weekday(). */
const weekdayOf = (iso: string) => (new Date(iso + 'T00:00:00Z').getUTCDay() + 6) % 7;

export const availabilityKey = (userId: number, date: string) => `${userId}-${date}`;

/** Expands raw rules into per (employee, day) marks. Mirrors
 *  services/availability.expand_availability. */
export const expandMarks = (
  rules: EmployeeAvailabilityRule[],
  start: string,
  end: string,
  templates: ShiftTemplateLite[]
): Map<string, AvailabilityMark> => {
  const out = new Map<string, AvailabilityMark>();
  const tname = (id: number | null) =>
    id == null ? '' : templates.find((t) => t.id === id)?.name || `shift #${id}`;
  const n = daysBetween(start, end) + 1;
  for (const r of rules) {
    let days: string[];
    if (r.specific_date) {
      days = r.specific_date >= start && r.specific_date <= end ? [r.specific_date] : [];
    } else {
      days = [];
      for (let i = 0; i < n; i++) {
        const d = addDays(start, i);
        if (
          weekdayOf(d) === r.weekday &&
          (!r.valid_from || d >= r.valid_from) &&
          (!r.valid_to || d <= r.valid_to)
        )
          days.push(d);
      }
    }
    for (const d of days) {
      const k = availabilityKey(r.user_id, d);
      const m = out.get(k) || { blocked: false, shiftBlocked: [], prefers: [], lines: [] };
      if (r.kind === 'unavailable') {
        if (r.shift_template_id == null) {
          m.blocked = true;
          m.lines.push('Unavailable' + (r.note ? ` (${r.note})` : ''));
        } else {
          m.shiftBlocked.push(tname(r.shift_template_id));
          m.lines.push(
            `Unavailable for ${tname(r.shift_template_id)}` + (r.note ? ` (${r.note})` : '')
          );
        }
      } else if (r.kind === 'preferred' && r.shift_template_id != null) {
        m.prefers.push(tname(r.shift_template_id));
        m.lines.push(`Prefers ${tname(r.shift_template_id)}` + (r.note ? ` (${r.note})` : ''));
      } else continue;
      out.set(k, m);
    }
  }
  return out;
};

/** Fetches /roster/availability for the visible window + department. Never
 *  throws; the overlay is advisory so failures only toast once. */
export const useAvailability = () => {
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const req = useRef(0);
  useEffect(
    () => () => {
      req.current++;
    },
    []
  );
  const lastKey = useRef('');
  /** `background` refreshes are skipped when window + department are unchanged. */
  const load = useCallback(async (start: string, end: string, department: string, background = false) => {
    const key = `${start}|${end}|${department}`;
    if (background && key === lastKey.current) return;
    lastKey.current = key;
    const id = ++req.current;
    try {
      const rules = await schedulerApi.availability(start, end, department);
      if (id === req.current) setLoaded({ start, end, department, rules });
    } catch (e: any) {
      if (id === req.current) {
        lastKey.current = ''; // allow a retry on the next refresh
        toast.error(errMsg(e, 'Failed to load availability'), { id: 'roster-availability-error' });
      }
    }
  }, []);
  return { loaded, load };
};
