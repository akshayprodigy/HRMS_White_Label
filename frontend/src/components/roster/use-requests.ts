import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { toast } from 'sonner';
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

export const useRequests = (enabled: boolean) => {
  const [swaps, setSwaps] = useState<ApproverSwap[]>([]);
  const [drops, setDrops] = useState<SchedDrop[]>([]);
  const [shifts, setShifts] = useState<SchedOpenShift[]>([]);
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
    // A failed queue keeps its previous contents; tell the user once.
    if (s.status === 'fulfilled') setSwaps(s.value);
    if (d.status === 'fulfilled') setDrops(d.value);
    if (o.status === 'fulfilled') setShifts(o.value);
    const failed = [s, d, o].find((r) => r.status === 'rejected') as
      | PromiseRejectedResult
      | undefined;
    if (failed) toast.error(errMsg(failed.reason, 'Failed to load requests'), { id: 'roster-requests-error' });
    setLoaded(true);
    setLoading(false);
  }, []);

  useEffect(() => {
    if (enabled) reload();
  }, [enabled, reload]);

  const pendingClaims = useMemo(
    () => shifts.reduce((n, o) => n + o.claims.filter((c) => c.status === 'pending').length, 0),
    [shifts]
  );
  const count = swaps.length + drops.length + pendingClaims;
  return { swaps, drops, shifts, loaded, loading, reload, count, pendingClaims };
};
