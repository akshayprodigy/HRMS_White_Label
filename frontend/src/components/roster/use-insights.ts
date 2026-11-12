import { useCallback, useRef, useState } from 'react';
import { toast } from 'sonner';
import { client } from '../../api/client';
import { ENDPOINTS } from '../../api/endpoints';
import { errMsg } from '../schedule-delegations-utils';
import type { Insights } from './roster-api';

export interface InsightsState {
  start: string;
  end: string;
  data: Insights;
}

/** Fetches /roster/insights with a request-id stale guard. Failures never
 *  throw: they set `error` and toast once (deduped by id). */
export const useInsights = () => {
  const [state, setState] = useState<InsightsState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const req = useRef(0);

  const load = useCallback(
    async (start: string, end: string, department: string, background = false) => {
      const id = ++req.current;
      if (!background) setState(null);
      try {
        const params = new URLSearchParams({ start, end });
        if (department) params.set('department', department);
        const res = await client.get<Insights>(
          ENDPOINTS.ROSTER.INSIGHTS + '?' + params.toString()
        );
        if (id !== req.current) return;
        setState({ start, end, data: res.data });
        setError(null);
      } catch (err: any) {
        if (id !== req.current) return;
        const msg = errMsg(err, 'Failed to load coverage and rule checks');
        setError(msg);
        toast.error(msg, { id: 'roster-insights-error' });
      }
    },
    []
  );
  return { state, error, load };
};
