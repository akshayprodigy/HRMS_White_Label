import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  Wand2,
  RefreshCw,
  Info,
  Repeat,
  Copy,
  History,
} from 'lucide-react';
import { Card, Button, Badge, cn } from './ui-elements';
import { toast } from 'sonner';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from './ui/dialog';
import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';
import { ScheduleDelegations } from './schedule-delegations';
import { scopeLabel, errMsg } from './schedule-delegations-utils';
import {
  RosterCell,
  RosterGrid,
  RosterGridRow,
  WEEKOFF,
  addDays,
  daysBetween,
} from './roster/roster-api';
import { ReasonDialog } from './roster/reason-dialog';
import { PublishBar } from './roster/publish-bar';
import { PublishRequestsPanel } from './roster/publish-requests-panel';
import { RotationDialog } from './roster/rotation-dialog';
import { CopyDialog } from './roster/copy-dialog';
import { HistoryDialog } from './roster/history-dialog';

const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

const iso = (d: Date) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(
    d.getDate()
  ).padStart(2, '0')}`;

const mondayOf = (d: Date) => {
  const x = new Date(d);
  const wd = (x.getDay() + 6) % 7; // Mon=0
  x.setDate(x.getDate() - wd);
  return x;
};

const shortDate = (isoStr: string) => {
  const d = new Date(isoStr + 'T00:00:00');
  return {
    dow: WEEKDAYS[(d.getDay() + 6) % 7],
    dm: `${d.getDate()}/${d.getMonth() + 1}`,
    isSun: d.getDay() === 0,
  };
};

export const RosterPlanner = () => {
  const [mode, setMode] = useState<'week' | 'month'>('week');
  const [anchor, setAnchor] = useState<Date>(mondayOf(new Date()));
  const [department, setDepartment] = useState('');
  const [grid, setGrid] = useState<RosterGrid | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [view, setView] = useState<'planner' | 'delegations'>('planner');
  // null until the first response; latched so a later failed fetch doesn't unmount Delegations.
  const [isAdmin, setIsAdmin] = useState<boolean | null>(null);
  const [myGrants, setMyGrants] = useState<any[]>([]);
  const [savingCell, setSavingCell] = useState<string | null>(null);
  const [saveAs, setSaveAs] = useState<'draft' | 'published'>('draft');
  const [pendingEdit, setPendingEdit] = useState<{
    row: RosterGridRow;
    c: RosterCell;
    value: string;
  } | null>(null);
  const [rotOpen, setRotOpen] = useState(false);
  const [copyOpen, setCopyOpen] = useState(false);
  const [historyEmp, setHistoryEmp] = useState<{ id: number; name: string } | null>(null);
  const [prKey, setPrKey] = useState(0);
  const gridReq = useRef(0);

  // Pattern dialog
  const [patternOpen, setPatternOpen] = useState(false);
  const [pattern, setPattern] = useState<Record<number, string>>({});
  const [applying, setApplying] = useState(false);

  const range = useCallback(() => {
    if (mode === 'week') {
      const start = mondayOf(anchor);
      const end = new Date(start);
      end.setDate(end.getDate() + 6);
      return { start: iso(start), end: iso(end) };
    }
    const start = new Date(anchor.getFullYear(), anchor.getMonth(), 1);
    const end = new Date(anchor.getFullYear(), anchor.getMonth() + 1, 0);
    return { start: iso(start), end: iso(end) };
  }, [mode, anchor]);

  const fetchGrid = useCallback(async () => {
    const reqId = ++gridReq.current;
    setLoading(true);
    setLoadError(null);
    try {
      const { start, end } = range();
      const params = new URLSearchParams({ start, end });
      if (department) params.set('department', department);
      const res = await client.get<RosterGrid>(
        ENDPOINTS.ROSTER.PLAN + '?' + params.toString()
      );
      if (reqId !== gridReq.current) return;
      setGrid(res.data);
      setIsAdmin((prev) => prev === true ? true : !!res.data.is_admin);
    } catch (err: any) {
      if (reqId !== gridReq.current) return;
      const msg = errMsg(err, 'Failed to load roster');
      toast.error(msg);
      setLoadError(msg);
      setGrid(null);
      setIsAdmin((prev) => (prev === null ? false : prev));
    } finally {
      if (reqId === gridReq.current) setLoading(false);
    }
  }, [range, department]);

  useEffect(() => {
    if (isAdmin !== false) return; // admins don't need the banner
    client
      .get(ENDPOINTS.ROSTER.DELEGATIONS_MY)
      .then((r) => setMyGrants(r.data || []))
      .catch(() => setMyGrants([]));
  }, [isAdmin]);

  useEffect(() => {
    fetchGrid();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, anchor]);

  const navigate = (dir: number) => {
    const next = new Date(anchor);
    if (mode === 'week') next.setDate(next.getDate() + dir * 7);
    else next.setMonth(next.getMonth() + dir);
    setAnchor(mode === 'week' ? mondayOf(next) : next);
  };

  const cellValue = (c: RosterCell): string => {
    if (c.source !== 'roster') return ''; // fallback/empty is not a saved cell
    if (c.is_week_off) return WEEKOFF;
    return c.shift_template_id ? String(c.shift_template_id) : '';
  };

  const canPublish = !!grid?.can_publish;
  const effStatus = canPublish ? saveAs : 'draft';

  const requestEdit = (row: RosterGridRow, c: RosterCell, value: string) => {
    const isPublished = c.source === 'roster' && c.status === 'published';
    if (isPublished && value !== cellValue(c)) {
      setPendingEdit({ row, c, value });
      return;
    }
    editCell(row, c, value);
  };

  const editCell = async (
    row: RosterGridRow,
    c: RosterCell,
    value: string,
    reason?: string
  ) => {
    const key = `${row.employee_id}-${c.work_date}`;
    setSavingCell(key);
    try {
      if (value === '' && c.entry_id) {
        // Clearing a planned cell removes the entry (reverts to baseline).
        await client.delete(ENDPOINTS.ROSTER.ENTRY_DETAIL(c.entry_id), {
          params: reason ? { reason } : undefined,
        });
      } else if (value !== '') {
        const body: any = {
          employee_id: row.employee_id,
          work_date: c.work_date,
          shift_template_id: null,
          is_week_off: false,
          status: effStatus,
        };
        if (reason) body.reason = reason;
        if (value === WEEKOFF) body.is_week_off = true;
        else body.shift_template_id = Number(value);
        const res = await client.post(ENDPOINTS.ROSTER.ENTRIES, body);
        if (res.data?.notice) toast.info(res.data.notice);
      }
      setPendingEdit(null);
      await fetchGrid();
    } catch (err: any) {
      toast.error(errMsg(err, 'Failed to save cell'));
    } finally {
      setSavingCell(null);
    }
  };

  const previousWindow = () => {
    const { start, end } = range();
    if (mode === 'week') return { start: addDays(start, -7), end: addDays(end, -7) };
    const d = new Date(anchor.getFullYear(), anchor.getMonth() - 1, 1);
    const ps = iso(d);
    const pe = iso(new Date(d.getFullYear(), d.getMonth() + 1, 0));
    const cap = addDays(ps, 30);
    return { start: ps, end: daysBetween(pe, cap) < 0 ? cap : pe };
  };

  const draftCount = (grid?.rows || []).reduce(
    (n, r) => n + r.cells.filter((c) => c.status === 'draft').length,
    0
  );

  const applyPattern = async () => {
    const { start, end } = range();
    const pat: Record<number, number | null> = {};
    Object.entries(pattern).forEach(([wd, val]) => {
      if (val === '') return; // untouched weekday
      pat[Number(wd)] = val === WEEKOFF ? null : Number(val);
    });
    if (Object.keys(pat).length === 0) {
      toast.error('Set at least one weekday in the pattern');
      return;
    }
    setApplying(true);
    try {
      const res = await client.post(ENDPOINTS.ROSTER.BULK, {
        start,
        end,
        department: department || null,
        status: effStatus,
        overwrite: true,
        pattern: pat,
      });
      const r = res.data as any;
      toast.success(
        `Roster applied — ${r.created} created, ${r.updated} updated` +
          (r.out_of_scope.length
            ? `, ${r.out_of_scope.length} out of scope`
            : '')
      );
      if (r.errors?.length) toast.error(r.errors.slice(0, 3).join('; '));
      setPatternOpen(false);
      fetchGrid();
    } catch (err: any) {
      toast.error(errMsg(err, 'Failed to apply pattern'));
    } finally {
      setApplying(false);
    }
  };

  const templates = grid?.shift_templates || [];
  const rangeLabel = grid ? `${grid.start} → ${grid.end}` : '';

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center gap-2">
        <CalendarDays className="w-5 h-5 text-indigo-600" />
        <div>
          <h2 className="text-lg font-semibold text-gray-900">
            Roster Planner
          </h2>
          <p className="text-sm text-gray-500 mt-0.5">
            Plan shifts per employee per day for your team
          </p>
        </div>
      </div>

      {isAdmin && (
        <div role="group" aria-label="Roster view" className="flex rounded-lg border border-gray-200 overflow-hidden w-fit">
          {(['planner', 'delegations'] as const).map((v) => (
            <button
              key={v}
              onClick={() => setView(v)}
              aria-pressed={view === v}
              className={cn(
                'px-3 py-1.5 text-sm font-medium',
                view === v
                  ? 'bg-indigo-600 text-white'
                  : 'bg-white text-gray-600 hover:bg-gray-50'
              )}
            >
              {v === 'planner' ? 'Planner' : 'Delegations'}
            </button>
          ))}
        </div>
      )}

      {isAdmin && view === 'delegations' ? (
        <ScheduleDelegations />
      ) : (
      <>
      {isAdmin === false && myGrants.length > 0 && (
        <div className="flex items-start gap-2 p-3 bg-indigo-50 border border-indigo-200 rounded-lg text-xs text-indigo-800">
          <Info className="w-4 h-4 mt-0.5 shrink-0" />
          <div>
            You can schedule: {myGrants.map((g) => scopeLabel(g)).join('; ')}
            {myGrants.some((g) => !g.can_publish) &&
              ' — publishing requires HR approval'}
          </div>
        </div>
      )}

      {loadError && !grid && (
        <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
          {loadError}
        </div>
      )}

      {/* Precedence note */}
      <div className="flex items-start gap-2 p-3 bg-blue-50 border border-blue-200 rounded-lg text-xs text-blue-800">
        <Info className="w-4 h-4 mt-0.5 shrink-0" />
        <div>
          This is a <b>planning view</b>. Published roster entries are shown to
          employees under "My Shift" but do not change attendance or payroll —
          those still follow shift assignments.
        </div>
      </div>

      {/* Toolbar */}
      <Card className="p-3">
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex rounded-lg border border-gray-200 overflow-hidden">
            {(['week', 'month'] as const).map((m) => (
              <button
                key={m}
                onClick={() => setMode(m)}
                className={cn(
                  'px-3 py-1.5 text-sm font-medium',
                  mode === m
                    ? 'bg-indigo-600 text-white'
                    : 'bg-white text-gray-600 hover:bg-gray-50'
                )}
              >
                {m === 'week' ? 'Week' : 'Month'}
              </button>
            ))}
          </div>

          <div className="flex items-center gap-1">
            <Button variant="outline" size="sm" onClick={() => navigate(-1)}>
              <ChevronLeft className="w-4 h-4" />
            </Button>
            <span className="text-sm text-gray-700 min-w-[180px] text-center font-medium">
              {rangeLabel}
            </span>
            <Button variant="outline" size="sm" onClick={() => navigate(1)}>
              <ChevronRight className="w-4 h-4" />
            </Button>
          </div>

          <input
            type="text"
            placeholder="Filter department"
            value={department}
            onChange={(e) => setDepartment(e.target.value)}
            onBlur={fetchGrid}
            onKeyDown={(e) => e.key === 'Enter' && fetchGrid()}
            className="px-3 py-1.5 border rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
          />

          <div className="flex-1" />

          <Button
            variant="outline"
            size="sm"
            onClick={fetchGrid}
            className="gap-1.5"
          >
            <RefreshCw className={cn('w-4 h-4', loading && 'animate-spin')} />
            Refresh
          </Button>
          <div className="flex items-center gap-1.5 text-sm text-gray-600">
            Save edits as:
            <div role="group" aria-label="Save edits as" className="flex rounded-lg border border-gray-200 overflow-hidden">
              {(['draft', 'published'] as const).map((st) => (
                <button
                  key={st}
                  disabled={st === 'published' && !canPublish}
                  title={st === 'published' && !canPublish ? 'Publishing requires HR approval' : undefined}
                  onClick={() => setSaveAs(st)}
                  aria-pressed={effStatus === st}
                  className={cn(
                    'px-2.5 py-1.5 text-sm font-medium disabled:opacity-40 disabled:cursor-not-allowed',
                    effStatus === st ? 'bg-indigo-600 text-white' : 'bg-white text-gray-600 hover:bg-gray-50'
                  )}
                >
                  {st === 'draft' ? 'Draft' : 'Published'}
                </button>
              ))}
            </div>
          </div>
          <Button variant="outline" size="sm" onClick={() => setCopyOpen(true)} disabled={!grid} className="gap-1.5">
            <Copy className="w-4 h-4" />
            Copy previous
          </Button>
          <Button variant="outline" size="sm" onClick={() => setRotOpen(true)} disabled={!grid} className="gap-1.5">
            <Repeat className="w-4 h-4" />
            Rotations
          </Button>
          <Button
            size="sm"
            onClick={() => {
              setPattern({});
              setPatternOpen(true);
            }}
            className="bg-indigo-600 hover:bg-indigo-700 text-white gap-1.5"
          >
            <Wand2 className="w-4 h-4" />
            Apply Pattern
          </Button>
        </div>
      </Card>

      <PublishRequestsPanel
        isAdmin={!!grid?.is_admin}
        refreshKey={prKey}
        onChanged={fetchGrid}
      />

      {grid && (
        <PublishBar
          draftCount={draftCount}
          canPublish={canPublish}
          start={grid.start}
          end={grid.end}
          department={department}
          onDone={() => {
            fetchGrid();
            setPrKey((k) => k + 1);
          }}
        />
      )}

      {/* Grid */}
      <Card className="overflow-hidden">
        <div className="overflow-x-auto">
          <table className="text-sm border-collapse">
            <thead>
              <tr className="bg-gray-50 border-b">
                <th className="sticky left-0 z-10 bg-gray-50 text-left px-3 py-2 font-medium text-gray-600 min-w-[200px] border-r">
                  Employee
                </th>
                {(grid?.dates || []).map((d) => {
                  const s = shortDate(d);
                  return (
                    <th
                      key={d}
                      className={cn(
                        'px-2 py-2 font-medium text-gray-600 text-center min-w-[110px]',
                        s.isSun && 'bg-rose-50'
                      )}
                    >
                      <div>{s.dow}</div>
                      <div className="text-[11px] text-gray-400">{s.dm}</div>
                    </th>
                  );
                })}
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td
                    colSpan={(grid?.dates?.length || 7) + 1}
                    className="px-4 py-12 text-center text-gray-400"
                  >
                    Loading roster…
                  </td>
                </tr>
              ) : !grid || grid.rows.length === 0 ? (
                <tr>
                  <td
                    colSpan={(grid?.dates?.length || 7) + 1}
                    className="px-4 py-12 text-center text-gray-400"
                  >
                    <CalendarDays className="w-8 h-8 mx-auto mb-2 opacity-40" />
                    No employees in scope for this range.
                  </td>
                </tr>
              ) : (
                grid.rows.map((row) => (
                  <tr key={row.employee_id} className="border-b hover:bg-gray-50">
                    <td className="sticky left-0 z-10 bg-white px-3 py-2 border-r">
                      <div className="flex items-start gap-1.5">
                        <div className="flex-1 min-w-0">
                          <div className="font-medium text-gray-900">
                            {row.full_name || `User #${row.employee_id}`}
                          </div>
                          <div className="text-xs text-gray-500">
                            {row.department} &middot; {row.designation}
                          </div>
                        </div>
                        <button
                          onClick={() =>
                            setHistoryEmp({
                              id: row.employee_id,
                              name: row.full_name || `User #${row.employee_id}`,
                            })
                          }
                          aria-label="View change history"
                          title="Change history"
                          className="text-gray-400 hover:text-indigo-600 p-0.5"
                        >
                          <History className="w-4 h-4" />
                        </button>
                      </div>
                    </td>
                    {row.cells.map((c) => {
                      const key = `${row.employee_id}-${c.work_date}`;
                      const val = cellValue(c);
                      const isFallback = c.source !== 'roster';
                      const isDraft = c.status === 'draft';
                      const lockedPublished =
                        !canPublish && c.source === 'roster' && c.status === 'published';
                      return (
                        <td
                          key={c.work_date}
                          className={cn(
                            'px-1.5 py-1.5 text-center',
                            c.is_week_off && 'bg-amber-50'
                          )}
                        >
                          {isDraft && (
                            <div className="text-[9px] uppercase tracking-wide text-amber-600 leading-none mb-0.5">
                              Draft
                            </div>
                          )}
                          <select
                            value={val}
                            disabled={savingCell === key || lockedPublished}
                            title={lockedPublished ? 'Published — publishing requires HR approval' : undefined}
                            onChange={(e) => requestEdit(row, c, e.target.value)}
                            className={cn(
                              'w-full text-xs px-1.5 py-1 border rounded focus:ring-1 focus:ring-indigo-500',
                              isDraft
                                ? 'border-dashed border-amber-400 text-gray-800'
                                : isFallback
                                ? 'text-gray-400 border-dashed'
                                : c.is_week_off
                                ? 'text-amber-700 border-amber-300'
                                : 'text-gray-800 border-gray-200'
                            )}
                          >
                            <option value="">
                              {isFallback && c.shift_name
                                ? `(${c.shift_name})`
                                : '—'}
                            </option>
                            {templates.map((t) => (
                              <option key={t.id} value={t.id}>
                                {t.name}
                              </option>
                            ))}
                            <option value={WEEKOFF}>Week off</option>
                          </select>
                        </td>
                      );
                    })}
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </Card>

      {grid && (
        <div className="flex items-center gap-4 text-xs text-gray-500">
          <span className="flex items-center gap-1">
            <Badge className="bg-white border-dashed border-gray-300 text-gray-400">
              (dashed)
            </Badge>
            = baseline from shift assignment (not yet planned)
          </span>
          <span className="flex items-center gap-1">
            <Badge className="bg-amber-50 text-amber-700 border-amber-200">
              amber
            </Badge>
            = week off
          </span>
          <span className="flex items-center gap-1">
            <Badge className="bg-white border-dashed border-amber-400 text-amber-600">
              Draft
            </Badge>
            = unpublished (hidden from employees)
          </span>
        </div>
      )}

      <ReasonDialog
        open={!!pendingEdit}
        title="Change a published schedule"
        description={
          pendingEdit
            ? `${pendingEdit.row.full_name || 'Employee'} on ${pendingEdit.c.work_date} is already published. Employees will be notified.`
            : undefined
        }
        label="Reason for change"
        confirmLabel="Save change"
        busy={!!savingCell}
        onConfirm={(reason) =>
          pendingEdit &&
          editCell(pendingEdit.row, pendingEdit.c, pendingEdit.value, reason)
        }
        onClose={() => setPendingEdit(null)}
      />
      <RotationDialog
        open={rotOpen}
        onClose={() => setRotOpen(false)}
        isAdmin={!!grid?.is_admin}
        canPublish={canPublish}
        templates={templates}
        rows={grid?.rows || []}
        start={grid?.start || ''}
        end={grid?.end || ''}
        onApplied={fetchGrid}
      />
      <CopyDialog
        open={copyOpen}
        source={grid ? previousWindow() : null}
        target={{ start: grid?.start || '', end: grid?.end || '' }}
        department={department}
        onClose={() => setCopyOpen(false)}
        onDone={fetchGrid}
      />
      <HistoryDialog employee={historyEmp} onClose={() => setHistoryEmp(null)} />

      {/* Pattern dialog */}
      <Dialog open={patternOpen} onOpenChange={setPatternOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Wand2 className="w-5 h-5 text-indigo-600" />
              Apply weekday pattern
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <p className="text-sm text-gray-500">
              Assign a shift (or week-off) to each weekday across the current{' '}
              {mode}. Leave a weekday blank to keep it unchanged.
            </p>
            {WEEKDAYS.map((label, wd) => (
              <div key={wd} className="flex items-center gap-3">
                <span className="w-12 text-sm font-medium text-gray-700">
                  {label}
                </span>
                <select
                  value={pattern[wd] ?? ''}
                  onChange={(e) =>
                    setPattern((p) => ({ ...p, [wd]: e.target.value }))
                  }
                  className="flex-1 px-3 py-1.5 border rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
                >
                  <option value="">— unchanged —</option>
                  {templates.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.name} ({t.start_time}–{t.end_time})
                    </option>
                  ))}
                  <option value={WEEKOFF}>Week off</option>
                </select>
              </div>
            ))}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setPatternOpen(false)}>
              Cancel
            </Button>
            <Button
              onClick={applyPattern}
              disabled={applying}
              className="bg-indigo-600 hover:bg-indigo-700 text-white gap-2"
            >
              {applying ? (
                <RefreshCw className="w-4 h-4 animate-spin" />
              ) : (
                <Wand2 className="w-4 h-4" />
              )}
              Apply to {mode}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      </>
      )}
    </div>
  );
};
