import React, { useState, useEffect, useCallback } from 'react';
import {
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  Wand2,
  RefreshCw,
  Info,
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

interface ShiftTemplateLite {
  id: number;
  name: string;
  start_time: string;
  end_time: string;
  is_overnight: boolean;
}
interface RosterCell {
  work_date: string;
  shift_template_id: number | null;
  is_week_off: boolean;
  status: string | null;
  entry_id: number | null;
  source: string;
  shift_name: string | null;
}
interface RosterGridRow {
  employee_id: number;
  full_name: string | null;
  department: string | null;
  designation: string | null;
  in_scope: boolean;
  cells: RosterCell[];
}
interface RosterGrid {
  start: string;
  end: string;
  dates: string[];
  shift_templates: ShiftTemplateLite[];
  rows: RosterGridRow[];
  is_admin: boolean;
}

const WEEKOFF = '__weekoff__';
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
  const [savingCell, setSavingCell] = useState<string | null>(null);

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
    setLoading(true);
    try {
      const { start, end } = range();
      const params = new URLSearchParams({ start, end });
      if (department) params.set('department', department);
      const res = await client.get<RosterGrid>(
        ENDPOINTS.ROSTER.PLAN + '?' + params.toString()
      );
      setGrid(res.data);
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      toast.error(
        typeof detail === 'string' ? detail : 'Failed to load roster'
      );
      setGrid(null);
    } finally {
      setLoading(false);
    }
  }, [range, department]);

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

  const editCell = async (
    row: RosterGridRow,
    c: RosterCell,
    value: string
  ) => {
    const key = `${row.employee_id}-${c.work_date}`;
    setSavingCell(key);
    try {
      const body: any = {
        employee_id: row.employee_id,
        work_date: c.work_date,
        shift_template_id: null,
        is_week_off: false,
      };
      if (value === WEEKOFF) body.is_week_off = true;
      else if (value) body.shift_template_id = Number(value);
      await client.post(ENDPOINTS.ROSTER.ENTRIES, body);
      await fetchGrid();
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Failed to save cell');
    } finally {
      setSavingCell(null);
    }
  };

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
        status: 'published',
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
      setPatternOpen(false);
      fetchGrid();
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Failed to apply pattern');
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
                      <div className="font-medium text-gray-900">
                        {row.full_name || `User #${row.employee_id}`}
                      </div>
                      <div className="text-xs text-gray-500">
                        {row.department} &middot; {row.designation}
                      </div>
                    </td>
                    {row.cells.map((c) => {
                      const key = `${row.employee_id}-${c.work_date}`;
                      const val = cellValue(c);
                      const isFallback = c.source !== 'roster';
                      return (
                        <td
                          key={c.work_date}
                          className={cn(
                            'px-1.5 py-1.5 text-center',
                            c.is_week_off && 'bg-amber-50'
                          )}
                        >
                          <select
                            value={val}
                            disabled={savingCell === key}
                            onChange={(e) => editCell(row, c, e.target.value)}
                            className={cn(
                              'w-full text-xs px-1.5 py-1 border rounded focus:ring-1 focus:ring-indigo-500',
                              isFallback
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
        </div>
      )}

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
    </div>
  );
};
