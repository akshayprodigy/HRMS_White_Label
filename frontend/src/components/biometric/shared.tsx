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
  label?: string; // display name for the device (not part of the scope key)
}

interface BackfillState {
  key: string;
  counts: Record<string, number>;
  remaining: number;
  next: number | null;
  scope: BackfillScope;
  stalled?: boolean;
}

const scopeKey = (s: BackfillScope) =>
  [s.state ?? 'pending', s.device_id ?? '', s.pin ?? '', s.import_batch ?? ''].join('|');

/**
 * Tracks chunked back-fills, one notice per scope. Every response carries
 * `remaining` and `next_after_id`; while remaining > 0 the UI offers
 * "Continue", which calls POST /punches/reprocess {state, after_id} and sums
 * the counts. Finished notices auto-dismiss after 10 s.
 */
export const useBackfill = (onProgress?: () => void) => {
  const [list, setList] = useState<BackfillState[]>([]);
  const [busyKey, setBusyKey] = useState<string | null>(null);

  const start = useCallback((resp: BackfillResp, scope: BackfillScope) => {
    const key = scopeKey(scope);
    const n: BackfillState = {
      key, counts: resp.backfill ?? {}, remaining: resp.remaining ?? 0,
      next: resp.next_after_id ?? null, scope,
    };
    setList((l) => [...l.filter((x) => x.key !== key), n]);
  }, []);

  const dismiss = useCallback((key?: string) => {
    setList((l) => (key ? l.filter((x) => x.key !== key) : []));
  }, []);

  // Auto-dismiss finished notices.
  useEffect(() => {
    const done = list.filter((x) => x.remaining === 0);
    if (!done.length) return;
    const t = window.setTimeout(
      () => setList((l) => l.filter((x) => !done.some((d) => d.key === x.key && d.counts === x.counts))),
      10_000
    );
    return () => window.clearTimeout(t);
  }, [list]);

  const cont = useCallback(async (key: string) => {
    const bf = list.find((x) => x.key === key);
    if (!bf) return;
    setBusyKey(key);
    try {
      const body: Record<string, unknown> = { state: bf.scope.state ?? 'pending', after_id: bf.next ?? 0 };
      if (bf.scope.device_id != null) body.device_id = bf.scope.device_id;
      if (bf.scope.pin) body.pin = bf.scope.pin;
      if (bf.scope.import_batch) body.import_batch = bf.scope.import_batch;
      const r = await client.post<BackfillResp>(ENDPOINTS.BIOMETRIC.REPROCESS, body);
      const got = Object.values(r.data.backfill ?? {}).reduce((a, b) => a + b, 0);
      const next = r.data.next_after_id ?? null;
      const upd: BackfillState = {
        ...bf,
        counts: sumCounts(bf.counts, r.data.backfill),
        remaining: r.data.remaining ?? 0,
        next,
        stalled: (r.data.remaining ?? 0) > 0 && got === 0 && next === bf.next,
      };
      setList((l) => l.map((x) => (x.key === key ? upd : x)));
      onProgress?.();
    } catch (err: any) {
      toast.error(errMsg(err, 'Could not continue processing'));
    } finally {
      setBusyKey(null);
    }
  }, [list, onProgress]);

  return { list, busy: busyKey !== null, busyKey, start, cont, dismiss };
};

export const BackfillNotice: React.FC<{ ctl: ReturnType<typeof useBackfill> }> = ({ ctl }) => {
  const { list, busy, busyKey, cont, dismiss } = ctl;
  if (!list.length) return null;
  return (
    <div className="space-y-2">
      {list.map((bf) => {
        const done = bf.remaining === 0;
        const label = [
          bf.scope.import_batch ? `import ${bf.scope.import_batch.slice(0, 8)}` : '',
          bf.scope.device_id != null ? `device ${bf.scope.label || bf.scope.device_id}` : '',
          bf.scope.pin ? `PIN ${bf.scope.pin}` : '',
        ].filter(Boolean).join(', ');
        return (
          <div
            key={bf.key}
            role="status"
            className={`p-3 rounded-lg text-sm flex items-center justify-between gap-3 flex-wrap ${
              done ? 'bg-green-50 text-green-700' : 'bg-amber-50 text-amber-900'
            }`}
          >
            <span>
              {label ? `${label}: ` : ''}
              {done ? 'All taps processed. ' : ''}Applied so far: {countsText(bf.counts)}.
              {!done && <> <strong>{bf.remaining}</strong> taps still to process.</>}
            </span>
            <span className="flex items-center gap-2">
              {!done && bf.stalled && <span className="text-sm">No progress — check the Punch log.</span>}
              {!done && !bf.stalled && (
                <Button size="sm" onClick={() => cont(bf.key)} isLoading={busyKey === bf.key} disabled={busy}>
                  Continue
                </Button>
              )}
              <Button size="sm" variant="outline" onClick={() => dismiss(bf.key)} disabled={busyKey === bf.key}>
                Dismiss
              </Button>
            </span>
          </div>
        );
      })}
    </div>
  );
};

export interface EmpOpt {
  /** Employee primary key (HR employees list `id`). */
  id?: number;
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
              id: x.id,
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

export const Th: React.FC<{ children?: React.ReactNode; className?: string }> = ({ children, className = '' }) => (
  <th className={`${className} px-3 py-2 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide whitespace-nowrap`}>
    {children}
  </th>
);
