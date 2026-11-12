import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Activity, AlertTriangle, RefreshCw } from 'lucide-react';
import { Card, Button, Badge, cn } from './ui-elements';
import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';
import { errMsg, parseServerDate } from './schedule-delegations-utils';

type Status =
  | 'off'
  | 'on_leave'
  | 'upcoming'
  | 'not_arrived'
  | 'no_show'
  | 'on_shift'
  | 'completed';

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
  'not_arrived',
  'on_shift',
  'upcoming',
  'completed',
  'on_leave',
  'off',
];

const STATUS_META: Record<
  Status,
  { label: string; variant: 'success' | 'warning' | 'error' | 'info' | 'neutral' }
> = {
  no_show: { label: 'No-show', variant: 'error' },
  not_arrived: { label: 'Not arrived', variant: 'warning' },
  on_shift: { label: 'On shift', variant: 'success' },
  upcoming: { label: 'Upcoming', variant: 'info' },
  completed: { label: 'Completed', variant: 'neutral' },
  on_leave: { label: 'On leave', variant: 'neutral' },
  off: { label: 'Off', variant: 'neutral' },
};

const REFRESH_MS = 60_000;

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

  useEffect(() => {
    load(false);
  }, [load]);

  // Auto-refresh every 60 s, only while the tab is visible.
  useEffect(() => {
    const tick = () => {
      if (document.visibilityState === 'visible') load(true);
    };
    const id = window.setInterval(tick, REFRESH_MS);
    const onVis = () => {
      if (document.visibilityState === 'visible') load(true);
    };
    document.addEventListener('visibilitychange', onVis);
    return () => {
      window.clearInterval(id);
      document.removeEventListener('visibilitychange', onVis);
    };
  }, [load]);

  const rows = useMemo(() => {
    const all = data?.rows ?? [];
    const filtered = statusFilter ? all.filter((r) => r.status === statusFilter) : all;
    const rank = (s: Status) => STATUS_ORDER.indexOf(s);
    return [...filtered].sort(
      (a, b) => rank(a.status) - rank(b.status) || a.name.localeCompare(b.name)
    );
  }, [data, statusFilter]);

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

      <Card className="overflow-x-auto p-0">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-gray-50 text-left text-gray-600">
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
                <td colSpan={7} className="px-4 py-12 text-center text-gray-400">
                  Loading live board…
                </td>
              </tr>
            ) : rows.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-4 py-12 text-center text-gray-400">
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
    </div>
  );
};
