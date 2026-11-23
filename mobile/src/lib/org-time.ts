import { useEffect, useState } from 'react';
import { api } from '../api/client';
import { fmtUtcDate, parseUtc } from './time';

// Organisation time: the DB stores UTC, but shifts, "today" and HR-entered punch times are read in the
// org timezone (GET /meta/org-time, public). Same API as frontend/src/lib/org-time.ts.

export type OrgTimeInfo = { timezone: string; utc_offset_minutes: number; today: string };

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
    pending = api
      .get<OrgTimeInfo>('/meta/org-time')
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
          (retryTimer as { unref?: () => void }).unref?.();
        }
        return null;
      });
  }
  return pending;
};

/** Drop the cache and reload (e.g. after sign-in as another tenant user). */
export const refreshOrgTime = (): Promise<OrgTimeInfo | null> => {
  info = null;
  pending = null;
  listeners.forEach((l) => l());
  return loadOrgTime();
};

/** Test hook: forget everything, including a scheduled retry. */
export const resetOrgTimeForTests = () => {
  info = null;
  pending = null;
  if (retryTimer) clearTimeout(retryTimer);
  retryTimer = null;
  retryMs = 2000;
  listeners.clear();
};

/** IANA zone name; falls back to UTC until loaded (and kicks a load). */
export const orgTimezone = (): string => {
  if (!info) void loadOrgTime();
  return info?.timezone || 'UTC';
};

export const orgTimeReady = (): boolean => info !== null;

/** The org's current date as YYYY-MM-DD, computed client-side (never the device zone). */
/** The org-local calendar date (YYYY-MM-DD) of a UTC instant. */
export const orgDateOf = (now: Date): string => {
  // formatToParts, not the en-CA string shape (Hermes ICU may format it differently).
  const parts = new Intl.DateTimeFormat('en-US', { timeZone: orgTimezone(), year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(now);
  const p = (t: string) => parts.find((x) => x.type === t)?.value ?? '';
  return `${p('year')}-${p('month')}-${p('day')}`;
};
export const orgToday = (now: Date = new Date(Date.now())): string => orgDateOf(now);

/** Format a UTC instant in org time. Default: 24-hour HH:MM; '' if invalid. */
export const formatOrgTime = (
  isoUtc: string | Date,
  opts: Intl.DateTimeFormatOptions = { hour: '2-digit', minute: '2-digit' },
): string => {
  const d = typeof isoUtc === 'string' ? parseUtc(isoUtc) : isoUtc;
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleTimeString('en-GB', { ...opts, hourCycle: 'h23', timeZone: orgTimezone() });
};

/** Instant -> "HH:MM" in org time (no suffix), or an em dash. Call useOrgTime() in the component so it refreshes on load. */
export const fmtOrgTime = (iso: string | null | undefined): string => (iso ? formatOrgTime(iso) || '—' : '—');
/** Instant -> "14 Nov" for its org-local date, or an em dash. */
export const fmtOrgDate = (iso: string | null | undefined): string => {
  if (!iso) return '—';
  if (/^\d{4}-\d{2}-\d{2}$/.test(iso)) return fmtUtcDate(iso); // a calendar date, not an instant: never shift it
  const d = parseUtc(iso);
  return Number.isNaN(d.getTime()) ? '—' : fmtUtcDate(orgDateOf(d));
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
