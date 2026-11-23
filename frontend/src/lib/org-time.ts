import { useEffect, useState } from 'react';
import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';
import { parseServerDate } from '../components/schedule-delegations-utils';

// Organisation time: the DB stores UTC, but shifts, "today" and HR-entered
// punch times are all read in the org timezone (GET /meta/org-time, public).

export interface OrgTimeInfo {
  timezone: string;
  utc_offset_minutes: number;
  today: string;
}

let info: OrgTimeInfo | null = null;
let pending: Promise<OrgTimeInfo | null> | null = null;
let retryTimer: ReturnType<typeof setTimeout> | null = null;
let retryMs = 2000;
const listeners = new Set<() => void>();

const validZone = (tz: unknown): tz is string => {
  if (typeof tz !== 'string' || !tz) return false;
  try {
    new Intl.DateTimeFormat('en', { timeZone: tz });
    return true;
  } catch {
    return false;
  }
};

/** Fetch once (module-level cache, deduped). Failures retry with backoff. */
export const loadOrgTime = (): Promise<OrgTimeInfo | null> => {
  if (info) return Promise.resolve(info);
  if (!pending) {
    pending = client
      .get<OrgTimeInfo>(ENDPOINTS.META.ORG_TIME)
      .then((res) => {
        if (!validZone(res.data?.timezone)) throw new Error('invalid org timezone');
        info = res.data;
        retryMs = 2000;
        pending = null;
        listeners.forEach((l) => l());
        return info;
      })
      .catch(() => {
        pending = null;
        if (!retryTimer) {
          retryTimer = setTimeout(() => {
            retryTimer = null;
            void loadOrgTime();
          }, retryMs);
          retryMs = Math.min(retryMs * 2, 60_000);
        }
        return null;
      });
  }
  return pending;
};

/** Drop the cache and reload (call after the org timezone is changed). */
export const refreshOrgTime = (): Promise<OrgTimeInfo | null> => {
  info = null;
  pending = null;
  listeners.forEach((l) => l());
  return loadOrgTime();
};

// Warm the cache so synchronous callers (orgToday) have a value by first use.
void loadOrgTime();

/** IANA zone name; falls back to UTC until loaded (and kicks a retry). */
export const orgTimezone = (): string => {
  if (!info) void loadOrgTime();
  return info?.timezone || 'UTC';
};

/** The org's current date as YYYY-MM-DD, computed client-side. */
export const orgToday = (): string =>
  new Intl.DateTimeFormat('en-CA', {
    timeZone: orgTimezone(),
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(new Date());

/** Format a UTC instant in org time. Default: 24-hour HH:MM; '' if invalid. */
export const formatOrgTime = (
  isoUtc: string | Date,
  opts: Intl.DateTimeFormatOptions = { hour: '2-digit', minute: '2-digit' },
): string => {
  const d = typeof isoUtc === 'string' ? parseServerDate(isoUtc) : isoUtc;
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleTimeString('en-GB', { ...opts, hourCycle: 'h23', timeZone: orgTimezone() });
};

/** A UTC instant as org-local "YYYY-MM-DDTHH:MM" (for datetime-local inputs). */
export const toOrgInput = (isoUtc?: string | null): string => {
  if (!isoUtc) return '';
  const d = parseServerDate(isoUtc);
  if (Number.isNaN(d.getTime())) return '';
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: orgTimezone(),
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  }).formatToParts(d);
  const p = (t: string) => parts.find((x) => x.type === t)?.value ?? '';
  return `${p('year')}-${p('month')}-${p('day')}T${p('hour')}:${p('minute')}`;
};

/** Re-renders the component once org time has loaded. */
export const useOrgTime = () => {
  const [, bump] = useState(0);
  useEffect(() => {
    const l = () => bump((n) => n + 1);
    listeners.add(l);
    void loadOrgTime();
    return () => {
      listeners.delete(l);
    };
  }, []);
  return { timezone: orgTimezone(), today: orgToday(), ready: info !== null };
};
