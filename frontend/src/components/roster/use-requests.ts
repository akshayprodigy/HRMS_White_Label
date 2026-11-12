import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { errMsg, todayIso } from '../schedule-delegations-utils';
import {
  addDays,
  schedulerApi,
  type ApproverSwap,
  type SchedDrop,
  type SchedOpenShift,
} from './roster-api';

/** Open shifts API windows are capped at 62 days. */
export const OPEN_SHIFT_HORIZON_DAYS = 60;
const POLL_MS = 60_000;

export type QueueKey = 'swaps' | 'drops' | 'shifts';

/** Loads the three approval queues. Reloads when `active` turns on, every
 *  60s while the tab is visible, and on window focus. A failed queue keeps
 *  its last data and reports an error (never silently shown as empty). */
export const useRequests = (enabled: boolean, active: boolean) => {
  const [swaps, setSwaps] = useState<ApproverSwap[]>([]);
  const [drops, setDrops] = useState<SchedDrop[]>([]);
  const [shifts, setShifts] = useState<SchedOpenShift[]>([]);
  const [errors, setErrors] = useState<Partial<Record<QueueKey, string>>>({});
  const [loaded, setLoaded] = useState(false);
  const [loading, setLoading] = useState(false);
  const req = useRef(0);
  useEffect(
    () => () => {
      req.current++;
    },
    []
  );

  const reload = useCallback(async () => {
    const id = ++req.current;
    setLoading(true);
    const start = todayIso();
    const [s, d, o] = await Promise.allSettled([
      schedulerApi.swapQueue(),
      schedulerApi.dropQueue(),
      schedulerApi.openShifts(start, addDays(start, OPEN_SHIFT_HORIZON_DAYS), 'open'),
    ]);
    if (id !== req.current) return;
    if (s.status === 'fulfilled') setSwaps(s.value);
    if (d.status === 'fulfilled') setDrops(d.value);
    if (o.status === 'fulfilled') setShifts(o.value);
    const e: Partial<Record<QueueKey, string>> = {};
    if (s.status === 'rejected') e.swaps = errMsg(s.reason, "Couldn't load swap approvals");
    if (d.status === 'rejected') e.drops = errMsg(d.reason, "Couldn't load give-away approvals");
    if (o.status === 'rejected') e.shifts = errMsg(o.reason, "Couldn't load open shifts");
    setErrors(e);
    setLoaded(true);
    setLoading(false);
  }, []);

  // Initial load, and whenever the Requests tab is opened.
  useEffect(() => {
    if (enabled) reload();
  }, [enabled, active, reload]);

  // Poll while visible (also keeps the badge fresh); refresh on focus.
  useEffect(() => {
    if (!enabled) return;
    const visible = () => document.visibilityState === 'visible';
    const t = window.setInterval(() => visible() && reload(), POLL_MS);
    const onFocus = () => reload();
    const onVis = () => visible() && reload();
    window.addEventListener('focus', onFocus);
    document.addEventListener('visibilitychange', onVis);
    return () => {
      window.clearInterval(t);
      window.removeEventListener('focus', onFocus);
      document.removeEventListener('visibilitychange', onVis);
    };
  }, [enabled, reload]);

  const pendingClaims = useMemo(
    () => shifts.reduce((n, o) => n + o.claims.filter((c) => c.status === 'pending').length, 0),
    [shifts]
  );
  const count = swaps.length + drops.length + pendingClaims;
  return { swaps, drops, shifts, errors, loaded, loading, reload, count, pendingClaims };
};
