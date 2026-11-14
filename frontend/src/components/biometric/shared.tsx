import React, { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Button } from '../ui-elements';
import { client } from '../../api/client';
import { ENDPOINTS } from '../../api/endpoints';
import { errMsg } from '../schedule-delegations-utils';
import { BackfillResp, countsText, sumCounts } from './biometric-utils';

export const inputCls =
  'h-9 px-2 border border-gray-200 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500';
export const labelCls = 'block text-xs font-medium text-gray-600 mb-1';

export interface BackfillScope {
  state?: string;
  device_id?: number | null;
  pin?: string;
  import_batch?: string;
}

interface BackfillState {
  counts: Record<string, number>;
  remaining: number;
  next: number | null;
  scope: BackfillScope;
  stalled?: boolean;
}

/**
 * Tracks a chunked back-fill. Every response carries `remaining` and
 * `next_after_id`; while remaining > 0 the UI offers "Continue", which calls
 * POST /punches/reprocess {state:'pending', after_id} and sums the counts.
 */
export const useBackfill = (onProgress?: () => void) => {
  const [bf, setBf] = useState<BackfillState | null>(null);
  const [busy, setBusy] = useState(false);

  const start = useCallback((resp: BackfillResp, scope: BackfillScope) => {
    setBf({
      counts: resp.backfill ?? {},
      remaining: resp.remaining ?? 0,
      next: resp.next_after_id ?? null,
      scope,
    });
  }, []);

  const cont = useCallback(async () => {
    if (!bf) return;
    setBusy(true);
    try {
      const body: Record<string, unknown> = { state: bf.scope.state ?? 'pending', after_id: bf.next ?? 0 };
      if (bf.scope.device_id != null) body.device_id = bf.scope.device_id;
      if (bf.scope.pin) body.pin = bf.scope.pin;
      if (bf.scope.import_batch) body.import_batch = bf.scope.import_batch;
      const r = await client.post<BackfillResp>(ENDPOINTS.BIOMETRIC.REPROCESS, body);
      const got = Object.values(r.data.backfill ?? {}).reduce((a, b) => a + b, 0);
      const next = r.data.next_after_id ?? null;
      setBf({
        counts: sumCounts(bf.counts, r.data.backfill),
        remaining: r.data.remaining ?? 0,
        next,
        scope: bf.scope,
        stalled: (r.data.remaining ?? 0) > 0 && got === 0 && next === bf.next,
      });
      onProgress?.();
    } catch (err: any) {
      toast.error(errMsg(err, 'Could not continue processing'));
    } finally {
      setBusy(false);
    }
  }, [bf, onProgress]);

  const dismiss = useCallback(() => setBf(null), []);
  return { bf, busy, start, cont, dismiss };
};

export const BackfillNotice: React.FC<{ ctl: ReturnType<typeof useBackfill> }> = ({ ctl }) => {
  const { bf, busy, cont, dismiss } = ctl;
  if (!bf) return null;
  const done = bf.remaining === 0;
  return (
    <div
      role="status"
      className={`p-3 rounded-lg text-sm flex items-center justify-between gap-3 flex-wrap ${
        done ? 'bg-green-50 text-green-700' : 'bg-amber-50 text-amber-900'
      }`}
    >
      <span>
        {done ? 'All taps processed. ' : ''}Applied so far: {countsText(bf.counts)}.
        {!done && <> <strong>{bf.remaining}</strong> taps still to process.</>}
      </span>
      <span className="flex items-center gap-2">
        {!done && bf.stalled && <span className="text-sm">No progress — check the Punch log.</span>}
        {!done && !bf.stalled && (
          <Button size="sm" onClick={cont} isLoading={busy} disabled={busy}>Continue</Button>
        )}
        <Button size="sm" variant="outline" onClick={dismiss} disabled={busy}>Dismiss</Button>
      </span>
    </div>
  );
};

export interface EmpOpt {
  user_id: number;
  name: string;
  code: string;
}

/** Debounced server-side employee search; calls onPick when a result is chosen. */
export const EmployeePicker: React.FC<{
  onPick: (e: EmpOpt) => void;
  placeholder?: string;
  label?: string;
  disabled?: boolean;
}> = ({ onPick, placeholder = 'Search employee…', label = 'Search employee', disabled }) => {
  const [q, setQ] = useState('');
  const [matches, setMatches] = useState<EmpOpt[]>([]);
  useEffect(() => {
    const s = q.trim();
    if (s.length < 2) { setMatches([]); return; }
    let live = true;
    const t = window.setTimeout(async () => {
      try {
        const r = await client.get(ENDPOINTS.HR.EMPLOYEES, { params: { search: s, size: 8 } });
        if (!live) return;
        setMatches(
          (r.data?.items ?? [])
            .map((x: any) => ({
              user_id: x.user_id ?? x.user?.id,
              name: x.user?.full_name || x.user?.email || '',
              code: x.employee_id || '',
            }))
            .filter((x: EmpOpt) => x.user_id && x.name)
        );
      } catch {
        if (live) setMatches([]);
      }
    }, 250);
    return () => { live = false; window.clearTimeout(t); };
  }, [q]);
  return (
    <div className="relative">
      <input
        type="text"
        aria-label={label}
        className={`${inputCls} w-full`}
        placeholder={placeholder}
        value={q}
        disabled={disabled}
        onChange={(e) => setQ(e.target.value)}
      />
      {matches.length > 0 && (
        <ul className="absolute z-20 mt-1 w-full max-h-56 overflow-y-auto bg-white border border-gray-200 rounded-lg shadow-lg divide-y divide-gray-100">
          {matches.map((m) => (
            <li key={m.user_id}>
              <button
                type="button"
                className="w-full text-left px-3 py-2 text-sm hover:bg-gray-50"
                onClick={() => { onPick(m); setQ(''); setMatches([]); }}
              >
                {m.name} <span className="text-xs text-gray-500">{m.code}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};

export const Th: React.FC<{ children?: React.ReactNode }> = ({ children }) => (
  <th className="px-3 py-2 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide whitespace-nowrap">
    {children}
  </th>
);
