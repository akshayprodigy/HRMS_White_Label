import { useEffect, useState } from 'react';
import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';

// Organisation time: the DB stores UTC, but shifts, "today" and HR-entered
// punch times are all read in the org timezone (GET /meta/org-time, public).

export interface OrgTimeInfo {
  timezone: string;
  utc_offset_minutes: number;
  today: string;
}

let info: OrgTimeInfo | null = null;
let pending: Promise<OrgTimeInfo | null> | null = null;
const listeners = new Set<() => void>();

/** Fetch once (module-level cache). A failed fetch is retried on the next call. */
export const loadOrgTime = (): Promise<OrgTimeInfo | null> => {
  if (info) return Promise.resolve(info);
  if (!pending) {
    pending = client
      .get<OrgTimeInfo>(ENDPOINTS.META.ORG_TIME)
      .then((res) => {
        info = res.data;
        listeners.forEach((l) => l());
        return info;
      })
      .catch(() => {
        pending = null;
        return null;
      });
  }
  return pending;
};

// Warm the cache so synchronous callers (orgToday) have a value by first use.
void loadOrgTime();

/** IANA zone name; falls back to UTC until the fetch resolves. */
export const orgTimezone = (): string => info?.timezone || 'UTC';

/** The org's current date as YYYY-MM-DD, computed client-side. */
export const orgToday = (): string =>
  new Intl.DateTimeFormat('en-CA', {
    timeZone: orgTimezone(),
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(new Date());

// Server datetimes may be naive (UTC, no offset) or carry Z / an offset.
const parseUtc = (iso: string): Date =>
  new Date(/(Z|[+-]\d{2}:?\d{2})$/.test(iso) ? iso : `${iso}Z`);

/** Format a UTC instant in org time. Default: 24-hour HH:MM. */
export const formatOrgTime = (
  isoUtc: string | Date,
  opts: Intl.DateTimeFormatOptions = { hour: '2-digit', minute: '2-digit', hour12: false },
): string => {
  const d = typeof isoUtc === 'string' ? parseUtc(isoUtc) : isoUtc;
  return d.toLocaleTimeString([], { ...opts, timeZone: orgTimezone() });
};

/** A UTC instant as org-local "YYYY-MM-DDTHH:MM" (for datetime-local inputs). */
export const toOrgInput = (isoUtc?: string | null): string => {
  if (!isoUtc) return '';
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: orgTimezone(),
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  }).formatToParts(parseUtc(isoUtc));
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
