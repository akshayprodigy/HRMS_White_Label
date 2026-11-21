import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Activity, AlertTriangle, RefreshCw } from 'lucide-react';
import { Card, Button, Badge, cn } from './ui-elements';
import { Dialog, DialogContent, DialogTitle, DialogDescription, DialogFooter } from './ui/dialog';
import { useVisiblePoll } from '../hooks/use-visible-poll';
import { useReturnFocus } from './my-schedule/use-restore-focus';
import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';
import { errMsg, parseServerDate } from './schedule-delegations-utils';

type Status =
  | 'off'
  | 'on_leave'
  | 'upcoming'
  | 'not_arrived'
  | 'no_show'
  | 'running_late'
  | 'on_shift'
  | 'completed'
  | 'remote';

interface LiveRow {
  user_id: number;
  name: string;
  department: string | null;
  location: string | null;
  work_date: string;
  shift_name: string | null;
  start_hhmm: string | null;
  end_hhmm: string | null;
  status: Status;
  late_minutes: number;
  punch_in: string | null;
  punch_out: string | null;
  alerted: boolean;
  half_day_leave: boolean;
  remote_kind?: "on_duty" | "client_visit" | "wfh" | null;
  remote_portion?: "full" | "first_half" | "second_half" | null;
  late_notice_eta: string | null;
  late_notice_reason: string | null;
  transport_required?: boolean;
  gap_id: number | null;
  gap_status: 'open' | 'filled' | 'dismissed' | null;
};

interface LiveResponse {
  now: string;
  counts: Record<Status, number>;
  rows: LiveRow[];
};

const STATUS_ORDER: Status[] = [
  'no_show',
  'running_late',
  'not_arrived',
  'on_shift',
  'upcoming',
  'completed',
  'remote',
  'on_leave',
  'off',
];

const STATUS_META: Record<
  Status,
  { label: string; variant: 'success' | 'warning' | 'error' | 'info' | 'neutral' }
> = {
  no_show: { label: 'No-show', variant: 'error' },
  running_late: { label: 'Running late', variant: 'info' },
  not_arrived: { label: 'Not arrived', variant: 'warning' },
  on_shift: { label: 'On shift', variant: 'success' },
  upcoming: { label: 'Upcoming', variant: 'info' },
  completed: { label: 'Completed', variant: 'neutral' },
  remote: { label: 'Remote', variant: 'info' },
  on_leave: { label: 'On leave', variant: 'neutral' },
  off: { label: 'Off', variant: 'neutral' },
};

const REFRESH_MS = 60_000;

/** Rows a supervisor can mark present when the punch system is down. */
const MARKABLE: Status[] = ['not_arrived', 'no_show', 'running_late'];

interface BulkResult {
  user_id: number;
  status: 'created' | 'skipped_existing' | 'out_of_scope' | 'locked' | 'error';
  attendance_id?: number | null;
  message?: string | null;
}

const RESULT_LABEL: Record<BulkResult['status'], string> = {
  created: 'Marked present',
  skipped_existing: 'Already has attendance',
  out_of_scope: 'Outside your scope',
  locked: 'Locked by payroll',
  error: 'Failed',
};

/** Client-side mirror of the bulk-mark time rules (attendance_bulk.py):
 * HH:MM punch-out <= punch-in means "next day" (night shift), equal is an
 * error and the span is capped at 24 h. "Punch-in in the future" is checked
 * by the server only (times are org-local, which the browser cannot assume).
 * Returns an error message, or null when valid. */
export const validateMarkTimes = (
  punchIn: string,
  punchOut: string
): string | null => {
  const m = /^(\d{2}):(\d{2})$/.exec(punchIn);
  if (!m) return 'Enter the punch-in time.';
  const inMin = Number(m[1]) * 60 + Number(m[2]);
  if (punchOut) {
    const o = /^(\d{2}):(\d{2})$/.exec(punchOut);
    if (!o) return 'Enter a valid punch-out time.';
    const outMin = Number(o[1]) * 60 + Number(o[2]);
    if (outMin === inMin) return 'Punch-out must be after punch-in.';
    const span = outMin > inMin ? outMin - inMin : outMin + 24 * 60 - inMin;
    if (span > 24 * 60) return 'Punch-out must be within 24 hours of punch-in.';
  }
  return null;
};

/** "Ends next day" hint for an overnight punch-out. */
const overnightHint = (punchIn: string, punchOut: string): string | null =>
  punchIn && punchOut && punchOut < punchIn
    ? `Punch-out ${punchOut} is treated as the next day (night shift).`
    : null;

const hhmm = (iso: string | null) =>
  iso
    ? parseServerDate(iso).toLocaleTimeString([], {
        hour: '2-digit',
        minute: '2-digit',
        hour12: false,
        timeZone: 'UTC',
      })
    : '—';

const hhmmss = (d: Date) =>
  d.toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
    timeZone: 'UTC',
  });

/** Jump to the planner's Requests tab, where open coverage gaps live. */
const openGap = () => {
  try {
    sessionStorage.setItem('roster.openView', 'requests');
  } catch {
    /* storage unavailable: the user lands on the planner */
  }
  window.dispatchEvent(new CustomEvent('erp:navigate', { detail: { tab: 'roster-planner' } }));
};

const unique = (xs: (string | null)[]) =>
  Array.from(new Set(xs.filter((x): x is string => !!x))).sort();

export const LiveBoard: React.FC = () => {
  const [data, setData] = useState<LiveResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [updated, setUpdated] = useState<Date | null>(null);
  const [department, setDepartment] = useState('');
  const [location, setLocation] = useState('');
  const [statusFilter, setStatusFilter] = useState<Status | null>(null);
  // Filter option lists come from the unfiltered response so choosing one
  // does not collapse the other dropdown.
  const [deptOpts, setDeptOpts] = useState<string[]>([]);
  const [locOpts, setLocOpts] = useState<string[]>([]);
  const reqRef = useRef(0);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [markOpen, setMarkOpen] = useState(false);
  const [punchIn, setPunchIn] = useState('');
  const [punchOut, setPunchOut] = useState('');
  const [reason, setReason] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [markError, setMarkError] = useState<string | null>(null);
  const [markResults, setMarkResults] = useState<BulkResult[] | null>(null);
  const markFocus = useReturnFocus();

  const load = useCallback(
    async (background: boolean) => {
      const reqId = ++reqRef.current;
      if (background) setRefreshing(true);
      else setLoading(true);
      try {
        const params = new URLSearchParams();
        if (department) params.set('department', department);
        if (location) params.set('location', location);
        const qs = params.toString();
        const res = await client.get<LiveResponse>(
          ENDPOINTS.ROSTER.LIVE + (qs ? `?${qs}` : '')
        );
        if (reqId !== reqRef.current) return;
        setData(res.data);
        setUpdated(new Date());
        setError(null);
        if (!department && !location) {
          setDeptOpts(unique(res.data.rows.map((r) => r.department)));
          setLocOpts(unique(res.data.rows.map((r) => r.location)));
        }
      } catch (err: any) {
        if (reqId !== reqRef.current) return;
        setError(errMsg(err, 'Failed to load the live board'));
        if (!background) setData(null);
      } finally {
        if (reqId === reqRef.current) {
          setLoading(false);
          setRefreshing(false);
        }
      }
    },
    [department, location]
  );

  // First fetch for a given filter set shows the loader; later ticks (every
  // 60 s while the tab is visible) refresh in the background.
  const loadedFor = useRef<typeof load | null>(null);
  const poll = useCallback(() => {
    const background = loadedFor.current === load;
    loadedFor.current = load;
    return load(background);
  }, [load]);
  useVisiblePoll(poll, REFRESH_MS);

  const rows = useMemo(() => {
    const all = data?.rows ?? [];
    const filtered = statusFilter ? all.filter((r) => r.status === statusFilter) : all;
    const rank = (s: Status) => STATUS_ORDER.indexOf(s);
    return [...filtered].sort(
      (a, b) => rank(a.status) - rank(b.status) || a.name.localeCompare(b.name)
    );
  }, [data, statusFilter]);

  const markable = useMemo(() => rows.filter((r) => MARKABLE.includes(r.status)), [rows]);
  const selectedRows = useMemo(
    () => (data?.rows ?? []).filter((r) => selected.has(r.user_id) && MARKABLE.includes(r.status)),
    [data, selected]
  );
  const allMarked = markable.length > 0 && markable.every((r) => selected.has(r.user_id));
  const nameOf = (id: number) => data?.rows.find((r) => r.user_id === id)?.name ?? `User ${id}`;

  const toggle = (id: number) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const openMark = () => {
    markFocus.capture();
    setPunchIn(selectedRows.find((r) => r.start_hhmm)?.start_hhmm ?? '09:00');
    setPunchOut('');
    setReason('');
    setMarkError(null);
    setMarkResults(null);
    setMarkOpen(true);
  };

  const submitMark = async () => {
    if (reason.trim().length < 5) {
      setMarkError('Enter a reason of at least 5 characters.');
      return;
    }
    const timeErr = validateMarkTimes(punchIn, punchOut);
    if (timeErr) {
      setMarkError(timeErr);
      return;
    }
    setSubmitting(true);
    setMarkError(null);
    try {
      const byDate = new Map<string, number[]>();
      selectedRows.forEach((r) => byDate.set(r.work_date, [...(byDate.get(r.work_date) ?? []), r.user_id]));
      const all: BulkResult[] = [];
      for (const [work_date, user_ids] of byDate) {
        try {
          const res = await client.post<{ results: BulkResult[] }>(ENDPOINTS.ATTENDANCE.BULK_MARK, {
            work_date,
            user_ids,
            punch_in_time: punchIn,
            punch_out_time: punchOut || null,
            reason: reason.trim(),
          });
          all.push(...res.data.results);
        } catch (err: any) {
          const message = errMsg(err, 'Could not mark attendance');
          user_ids.forEach((user_id) => all.push({ user_id, status: 'error', message }));
        }
      }
      setMarkResults(all);
      setSelected(new Set());
      load(true);
    } catch (err: any) {
      setMarkError(errMsg(err, 'Could not mark attendance'));
    } finally {
      setSubmitting(false);
    }
  };

  const selectCls =
    'h-9 px-2 border border-gray-200 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500';

  return (
    <div className="p-8 space-y-5">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2">
          <Activity className="w-5 h-5 text-indigo-600" />
          <div>
            <h2 className="text-lg font-semibold text-gray-900">Live Board</h2>
            <p className="text-sm text-gray-500 mt-0.5">
              Who is on shift, late or missing right now. Times shown in UTC (same as shift schedule).
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs text-gray-500" aria-live="polite">
            {updated ? `Updated ${hhmmss(updated)} UTC` : ''}
          </span>
          <Button
            variant="outline"
            size="sm"
            onClick={() => load(true)}
            disabled={loading || refreshing}
            className="gap-1.5"
          >
            <RefreshCw className={cn('w-4 h-4', refreshing && 'animate-spin')} />
            Refresh
          </Button>
        </div>
      </div>

      <div className="flex items-center gap-3 flex-wrap">
        <label className="flex items-center gap-2 text-sm text-gray-600">
          Department
          <select
            className={selectCls}
            value={department}
            onChange={(e) => setDepartment(e.target.value)}
          >
            <option value="">All</option>
            {deptOpts.map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2 text-sm text-gray-600">
          Location
          <select
            className={selectCls}
            value={location}
            onChange={(e) => setLocation(e.target.value)}
          >
            <option value="">All</option>
            {locOpts.map((l) => (
              <option key={l} value={l}>
                {l}
              </option>
            ))}
          </select>
        </label>
      </div>

      {error && (
        <div
          role="alert"
          className="flex items-center gap-2 px-3 py-2 rounded-lg border border-red-200 bg-red-50 text-sm text-red-700"
        >
          <AlertTriangle className="w-4 h-4 shrink-0" />
          {error}
        </div>
      )}

      {data && (
        <div className="flex flex-wrap gap-2" role="group" aria-label="Filter by status">
          <button
            type="button"
            onClick={() => setStatusFilter(null)}
            aria-pressed={statusFilter === null}
            className={cn(
              'px-3 py-1.5 rounded-full border text-sm',
              statusFilter === null
                ? 'bg-indigo-600 text-white border-indigo-600'
                : 'bg-white text-gray-700 border-gray-200 hover:bg-gray-50'
            )}
          >
            All <span className="font-semibold">{data.rows.length}</span>
          </button>
          {STATUS_ORDER.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => setStatusFilter(statusFilter === s ? null : s)}
              aria-pressed={statusFilter === s}
              className={cn(
                'px-3 py-1.5 rounded-full border text-sm',
                statusFilter === s
                  ? 'bg-indigo-600 text-white border-indigo-600'
                  : 'bg-white text-gray-700 border-gray-200 hover:bg-gray-50'
              )}
            >
              {STATUS_META[s].label}{' '}
              <span className="font-semibold">{data.counts[s] ?? 0}</span>
            </button>
          ))}
        </div>
      )}

      {selectedRows.length > 0 && (
        <div className="flex items-center gap-3 px-3 py-2 rounded-lg border border-indigo-200 bg-indigo-50 text-sm">
          <span className="text-indigo-700">{selectedRows.length} selected</span>
          <Button size="sm" onClick={openMark}>
            Mark present (system outage)
          </Button>
          <button
            type="button"
            onClick={() => setSelected(new Set())}
            className="text-xs text-gray-600 hover:underline"
          >
            Clear
          </button>
        </div>
      )}

      <Card className="overflow-x-auto p-0">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-gray-50 text-left text-gray-600">
              <th className="px-4 py-2 w-8">
                <input
                  type="checkbox"
                  aria-label="Select all not-arrived employees"
                  checked={allMarked}
                  disabled={markable.length === 0}
                  onChange={() =>
                    setSelected(allMarked ? new Set() : new Set(markable.map((r) => r.user_id)))
                  }
                />
              </th>
              <th className="px-4 py-2 font-medium">Employee</th>
              <th className="px-4 py-2 font-medium">Shift</th>
              <th className="px-4 py-2 font-medium">Start – End</th>
              <th className="px-4 py-2 font-medium">Status</th>
              <th className="px-4 py-2 font-medium">Late</th>
              <th className="px-4 py-2 font-medium">Punch in</th>
              <th className="px-4 py-2 font-medium">Punch out</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={8} className="px-4 py-12 text-center text-gray-400">
                  Loading live board…
                </td>
              </tr>
            ) : rows.length === 0 ? (
              <tr>
                <td colSpan={8} className="px-4 py-12 text-center text-gray-400">
                  {error
                    ? 'Could not load the board.'
                    : statusFilter
                      ? 'No employees with this status.'
                      : 'No employees in your scope.'}
                </td>
              </tr>
            ) : (
              rows.map((r) => (
                <tr key={r.user_id} className="border-t border-gray-200">
                  <td className="px-4 py-2">
                    {MARKABLE.includes(r.status) && (
                      <input
                        type="checkbox"
                        aria-label={`Select ${r.name}`}
                        checked={selected.has(r.user_id)}
                        onChange={() => toggle(r.user_id)}
                      />
                    )}
                  </td>
                  <td className="px-4 py-2">
                    <div className="font-medium text-gray-900">{r.name}</div>
                    <div className="text-xs text-gray-500">
                      {[r.department, r.location].filter(Boolean).join(' · ')}
                    </div>
                  </td>
                  <td className="px-4 py-2 text-gray-700">{r.shift_name ?? '—'}</td>
                  <td className="px-4 py-2 text-gray-700 tabular-nums">
                    {r.start_hhmm ? `${r.start_hhmm} – ${r.end_hhmm}` : '—'}
                  </td>
                  <td className="px-4 py-2">
                    <span className="inline-flex items-center gap-1.5">
                      <Badge variant={STATUS_META[r.status].variant}>
                        {STATUS_META[r.status].label}
                      </Badge>
                      {r.late_notice_eta && r.punch_in == null && (
                        <span
                          className="text-xs text-blue-700"
                          title={r.late_notice_reason ?? undefined}
                        >
                          Running late · ETA {hhmm(r.late_notice_eta)} UTC
                          {r.late_notice_reason ? ` · ${r.late_notice_reason}` : ''}
                        </span>
                      )}
                      {r.transport_required && (
                        <span className="text-xs text-indigo-700">Cab/transport arranged</span>
                      )}
                      {r.half_day_leave && (
                        <span className="text-xs text-gray-500">Half-day leave</span>
                      )}
                      {r.gap_id != null && (
                        <button
                          type="button"
                          onClick={() => openGap()}
                          className="text-xs text-indigo-600 hover:underline"
                          aria-label={`Coverage gap ${r.gap_status} for ${r.name}, open in Requests`}
                        >
                          {r.gap_status === 'open'
                            ? 'Coverage gap open'
                            : r.gap_status === 'filled'
                              ? 'Gap filled'
                              : 'Gap dismissed'}
                        </button>
                      )}
                      {r.alerted && (
                        <span
                          className="inline-flex items-center text-red-600"
                          title="No-show alert sent"
                        >
                          <AlertTriangle className="w-4 h-4" aria-hidden="true" />
                          <span className="sr-only">No-show alert sent</span>
                        </span>
                      )}
                    </span>
                  </td>
                  <td className="px-4 py-2 tabular-nums text-gray-700">
                    {r.late_minutes > 0 ? `${r.late_minutes} min` : '—'}
                  </td>
                  <td className="px-4 py-2 tabular-nums text-gray-700">{hhmm(r.punch_in)}</td>
                  <td className="px-4 py-2 tabular-nums text-gray-700">{hhmm(r.punch_out)}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </Card>
      <Dialog open={markOpen} onOpenChange={(o: boolean) => !o && !submitting && setMarkOpen(false)}>
        <DialogContent className="max-w-md" onCloseAutoFocus={markFocus.onCloseAutoFocus}>
          <DialogTitle className="text-base font-semibold text-gray-900">
            Mark present (system outage)
          </DialogTitle>
          <DialogDescription className="sr-only">
            Record the selected employees as present with a punch-in time and reason.
          </DialogDescription>
          {markResults ? (
            <div className="space-y-3" role="status">
              <p className="text-sm text-gray-700">
                {markResults.filter((x) => x.status === 'created').length} of {markResults.length} marked present.
              </p>
              <ul className="text-sm space-y-1 max-h-60 overflow-y-auto">
                {markResults.map((x) => (
                  <li key={x.user_id} className="flex items-start justify-between gap-3">
                    <span className="text-gray-900">{nameOf(x.user_id)}</span>
                    <span
                      className={cn('text-right', x.status === 'created' ? 'text-emerald-700' : 'text-amber-700')}
                      title={x.message ?? undefined}
                    >
                      {RESULT_LABEL[x.status]}
                      {x.message && x.status !== 'created' && (
                        <span className="block text-xs text-gray-600 font-normal">{x.message}</span>
                      )}
                    </span>
                  </li>
                ))}
              </ul>
              <DialogFooter>
                <Button onClick={() => setMarkOpen(false)}>Close</Button>
              </DialogFooter>
            </div>
          ) : (
            <div className="space-y-3">
              <p className="text-sm text-gray-600">
                Records {selectedRows.length} employee{selectedRows.length === 1 ? '' : 's'} as present. Times are UTC,
                same as the board. This is audited.
              </p>
              <div className="grid grid-cols-2 gap-3">
                <label className="text-sm text-gray-700 space-y-1 block">
                  Punch in
                  <input
                    type="time"
                    value={punchIn}
                    onChange={(e) => { setPunchIn(e.target.value); setMarkError(null); }}
                    className={cn(selectCls, 'w-full')}
                  />
                </label>
                <label className="text-sm text-gray-700 space-y-1 block">
                  Punch out (optional)
                  <input
                    type="time"
                    value={punchOut}
                    onChange={(e) => { setPunchOut(e.target.value); setMarkError(null); }}
                    className={cn(selectCls, 'w-full')}
                  />
                </label>
              </div>
              {overnightHint(punchIn, punchOut) && (
                <p className="text-xs text-gray-600">{overnightHint(punchIn, punchOut)}</p>
              )}
              <label className="text-sm text-gray-700 space-y-1 block">
                Reason
                <textarea
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  rows={3}
                  placeholder="e.g. Biometric system down 08:00-10:30"
                  className="w-full px-2 py-1.5 border border-gray-200 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
              </label>
              {markError && (
                <div role="alert" className="text-sm text-red-700">
                  {markError}
                </div>
              )}
              <DialogFooter>
                <Button variant="ghost" onClick={() => setMarkOpen(false)} disabled={submitting}>
                  Cancel
                </Button>
                <Button onClick={submitMark} disabled={submitting}>
                  {submitting ? 'Marking…' : 'Mark present'}
                </Button>
              </DialogFooter>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
};
