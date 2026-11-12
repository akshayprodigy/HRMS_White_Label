import { useCallback, useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';
import { client } from '../../api/client';
import { ENDPOINTS } from '../../api/endpoints';
import { errMsg } from '../schedule-delegations-utils';
import type { Insights } from './roster-api';

export interface InsightsState {
  start: string;
  end: string;
  department: string;
  data: Insights;
  /** true when the latest refresh failed, so counts may be out of date */
  stale: boolean;
}

/** Fetches /roster/insights with a request-id stale guard. Failures never
 *  throw: they set `error`, mark kept data stale and toast once. */
export const useInsights = () => {
  const [state, setState] = useState<InsightsState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const req = useRef(0);
  const last = useRef<[string, string, string] | null>(null);

  useEffect(
    () => () => {
      req.current++; // invalidate in-flight responses after unmount
    },
    []
  );

  const load = useCallback(
    async (start: string, end: string, department: string, background = false) => {
      const id = ++req.current;
      last.current = [start, end, department];
      if (!background) {
        setState(null);
        setError(null);
      }
      try {
        const params = new URLSearchParams({ start, end });
        if (department) params.set('department', department);
        const res = await client.get<Insights>(
          ENDPOINTS.ROSTER.INSIGHTS + '?' + params.toString()
        );
        if (id !== req.current) return;
        setState({ start, end, department, data: res.data, stale: false });
        setError(null);
      } catch (err: any) {
        if (id !== req.current) return;
        const msg = errMsg(err, 'Failed to load coverage and rule checks');
        setError(msg);
        setState((s) => (s ? { ...s, stale: true } : s));
        toast.error(msg, { id: 'roster-insights-error' });
      }
    },
    []
  );
  const retry = useCallback(() => {
    if (last.current) load(last.current[0], last.current[1], last.current[2], true);
  }, [load]);
  return { state, error, load, retry };
};
