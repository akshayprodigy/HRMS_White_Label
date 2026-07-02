import React, { useEffect, useMemo, useState } from 'react';
import {
  X,
  Download,
  CalendarRange,
  ListChecks,
  History,
  BarChart3,
  Wrench,
  CheckCircle,
  XCircle,
  Navigation,
  Pencil,
  CalendarPlus,
  type LucideIcon,
} from 'lucide-react';
import { Card, Button, Badge, cn } from '../ui-elements';
import { client } from '../../api/client';
import { ENDPOINTS } from '../../api/endpoints';
import { toast } from 'sonner';
import { PeriodPicker, formatRangeLabel, toIsoDate, type DateRange } from '../period-picker';
import {
  buildEmployeeHeatmap,
  type AttendanceLog,
  type LeaveRecord,
  type CorrectionRecord,
  type HolidayRecord,
  type EmployeeBasic,
  type EmployeeHeatmapDay,
  type DayStatus,
} from './workforce-data';
import { exportEmployeePdf } from './workforce-export';
import { EditPunchModal, AddMissedPunchModal } from './edit-punch-modal';

// Section Q: HR/admin can hand-edit punches. Backend enforces the
// 'attendance edit' permission; this only controls button visibility.
const canEditPunches = (): boolean => {
  const role = (localStorage.getItem('hr_role') || '').toLowerCase();
  return role === 'hr' || role === 'admin' || role === 'super admin';
};

interface EmployeeDrilloverProps {
  employee: EmployeeBasic;
  parentRange: DateRange;
  holidays: Set<string>;
  allLogs: AttendanceLog[];
  allLeaves: LeaveRecord[];
  allHolidays: Map<string, HolidayRecord>;
  allCorrections: CorrectionRecord[];
  onClose: () => void;
  onChanged?: () => void;
}

type InnerTab = 'heatmap' | 'ledger' | 'log' | 'hours' | 'corrections';

const TABS: { id: InnerTab; label: string; icon: LucideIcon }[] = [
  { id: 'heatmap', label: 'Heatmap', icon: CalendarRange },
  { id: 'ledger', label: 'Ledger', icon: ListChecks },
  { id: 'log', label: 'Punch Log', icon: History },
  { id: 'hours', label: 'Hours', icon: BarChart3 },
  { id: 'corrections', label: 'Corrections', icon: Wrench },
];

const STATUS_COLOR: Record<DayStatus, string> = {
  present: 'bg-emerald-500 text-white',
  late: 'bg-amber-500 text-white',
  wfh: 'bg-indigo-400 text-white',
  absent: 'bg-rose-500 text-white',
  leave: 'bg-blue-500 text-white',
  holiday: 'bg-slate-700 text-white',
  holiday_worked: 'bg-slate-700 text-white ring-2 ring-amber-400 ring-inset',
  weekend: 'bg-slate-100 text-slate-400',
  weekend_worked: 'bg-slate-200 text-slate-700 ring-2 ring-amber-400 ring-inset',
  future: 'bg-white text-slate-300 border border-slate-100',
};

const STATUS_LABEL: Record<DayStatus, string> = {
  present: 'Present',
  late: 'Late',
  wfh: 'Work From Home',
  absent: 'Absent',
  leave: 'On Leave',
  holiday: 'Holiday',
  holiday_worked: 'Worked Holiday',
  weekend: 'Weekend',
  weekend_worked: 'Worked Weekend',
  future: 'Upcoming',
};

export const EmployeeDrillover: React.FC<EmployeeDrilloverProps> = ({
  employee,
  parentRange,
  holidays,
  allLogs,
  allLeaves,
  allHolidays,
  allCorrections,
  onClose,
  onChanged,
}) => {
  const [range, setRange] = useState<DateRange>(parentRange);
  const [tab, setTab] = useState<InnerTab>('heatmap');
  const [balances, setBalances] = useState<any[]>([]);
  const [balLoading, setBalLoading] = useState(true);
  const [editLog, setEditLog] = useState<AttendanceLog | null>(null);
  const [addPunchOpen, setAddPunchOpen] = useState(false);
  const allowEdit = canEditPunches();

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setBalLoading(true);
      try {
        const res = await client.get(ENDPOINTS.LEAVE.BALANCES_BY_USER(employee.user_id));
        if (!cancelled) setBalances(res.data || []);
      } catch {
        if (!cancelled) setBalances([]);
      } finally {
        if (!cancelled) setBalLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [employee.user_id]);

  const heatmap = useMemo(
    () => buildEmployeeHeatmap(range, employee, allLogs, allLeaves, allHolidays),
    [range, employee, allLogs, allLeaves, allHolidays],
  );

  const summary = useMemo(() => {
    let presentDays = 0, late = 0, hoursSum = 0, hoursCount = 0, leaveDays = 0, working = 0;
    for (const d of heatmap) {
      if (d.status === 'weekend' || d.status === 'holiday' || d.status === 'future') continue;
      working++;
      if (d.status === 'present' || d.status === 'wfh' || d.status === 'late') {
        presentDays++;
        if (d.status === 'late') late++;
        if (d.hours && d.hours > 0) {
          hoursSum += d.hours;
          hoursCount++;
        }
      }
      if (d.status === 'leave') leaveDays++;
    }
    return {
      presentDays,
      late,
      working,
      leaveDays,
      pct: working > 0 ? presentDays / working : 0,
      avgHours: hoursCount > 0 ? hoursSum / hoursCount : 0,
    };
  }, [heatmap]);

  const empCorrections = useMemo(
    () => allCorrections.filter(c => c.user_id === employee.user_id),
    [allCorrections, employee.user_id],
  );
  const pendingCount = empCorrections.filter(c => c.status === 'submitted').length;

  const empLogs = useMemo(() => {
    const fromIso = toIsoDate(range.from);
    const toIso = toIsoDate(range.to);
    return allLogs
      .filter(l => l.user_id === employee.user_id)
      .filter(l => {
        const iso = toIsoDate(new Date(l.captured_at));
        return iso >= fromIso && iso <= toIso;
      })
      .sort((a, b) => b.captured_at.localeCompare(a.captured_at));
  }, [allLogs, employee.user_id, range]);

  const empLeaves = useMemo(
    () =>
      allLeaves
        .filter(lv => lv.employee_id === employee.employee_id)
        .filter(lv => lv.end_date >= toIsoDate(range.from) && lv.start_date <= toIsoDate(range.to))
        .sort((a, b) => b.start_date.localeCompare(a.start_date)),
    [allLeaves, employee.employee_id, range],
  );

  const handleExport = () => exportEmployeePdf(employee, range, heatmap, summary);

  return (
    <div className="fixed inset-0 z-50 flex justify-end" role="dialog" aria-modal="true">
      <div
        className="absolute inset-0 bg-slate-900/40 backdrop-blur-[2px] animate-in fade-in duration-200"
        onClick={onClose}
      />
      <aside className="relative w-full max-w-[560px] h-full bg-white shadow-2xl shadow-slate-900/30 flex flex-col animate-in slide-in-from-right duration-200">
        <div className="px-6 py-5 border-b border-slate-100 flex items-start justify-between">
          <div className="flex items-center gap-3 min-w-0">
            <div className="w-12 h-12 rounded-2xl bg-blue-50 text-blue-600 flex items-center justify-center font-black text-lg shrink-0">
              {employee.full_name.charAt(0).toUpperCase()}
            </div>
            <div className="min-w-0">
              <h3 className="text-lg font-black text-[#0F172A] tracking-tight truncate">
                {employee.full_name}
              </h3>
              <p className="text-[9px] font-bold text-slate-400 uppercase tracking-widest truncate">
                {employee.department || '—'}
                {employee.manager_name ? ` · MGR ${employee.manager_name}` : ''}
                {employee.employee_id ? ` · ID #${employee.employee_id}` : ''}
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1.5 text-slate-400 hover:text-slate-700 hover:bg-slate-50 rounded-lg transition-colors shrink-0"
            aria-label="Close drillover"
          >
            <X size={18} />
          </button>
        </div>

        <div className="px-6 py-3 border-b border-slate-100 bg-slate-50/40 space-y-3">
          <div className="flex items-center gap-2">
            <PeriodPicker value={range} onChange={setRange} holidays={holidays} align="start" />
            <span className="text-[9px] font-black uppercase tracking-widest text-slate-400">
              {range.from.getTime() === parentRange.from.getTime() &&
              range.to.getTime() === parentRange.to.getTime()
                ? '· INHERITED'
                : '· OVERRIDE'}
            </span>
          </div>
          <div className="grid grid-cols-4 gap-2 text-center tabular-nums">
            <Stat label="Present" value={`${summary.presentDays}/${summary.working}`} />
            <Stat label="Late" value={summary.late.toString()} tone="amber" />
            <Stat label="Attn %" value={`${(summary.pct * 100).toFixed(0)}%`} tone="emerald" />
            <Stat label="Avg Hrs" value={summary.avgHours > 0 ? `${summary.avgHours.toFixed(1)}h` : '—'} />
          </div>
        </div>

        <nav className="flex border-b border-slate-100 bg-white">
          {TABS.map(t => {
            const Icon = t.icon;
            const active = tab === t.id;
            return (
              <button
                key={t.id}
                type="button"
                onClick={() => setTab(t.id)}
                className={cn(
                  'flex-1 inline-flex items-center justify-center gap-1.5 py-3 text-[9px] font-black uppercase tracking-widest transition-colors border-b-2',
                  active
                    ? 'text-blue-600 border-blue-600'
                    : 'text-slate-400 border-transparent hover:text-slate-700',
                )}
              >
                <Icon size={12} />
                {t.label}
                {t.id === 'corrections' && pendingCount > 0 && (
                  <span className="ml-1 inline-flex items-center justify-center min-w-[1.1rem] h-4 px-1 rounded-full bg-blue-600 text-white text-[8px]">
                    {pendingCount}
                  </span>
                )}
              </button>
            );
          })}
        </nav>

        <div className="flex-1 overflow-y-auto p-6 space-y-5">
          {tab === 'heatmap' && <HeatmapView days={heatmap} />}
          {tab === 'ledger' && <LedgerView balances={balances} loading={balLoading} leaves={empLeaves} />}
          {tab === 'log' && (
            <LogView
              logs={empLogs}
              canEdit={allowEdit}
              onEdit={setEditLog}
              onAddMissed={() => setAddPunchOpen(true)}
            />
          )}
          {tab === 'hours' && <HoursView days={heatmap} />}
          {tab === 'corrections' && <CorrectionsView corrections={empCorrections} />}
        </div>

        <div className="px-6 py-4 border-t border-slate-100 bg-slate-50/40 flex gap-2">
          <Button
            variant="outline"
            onClick={handleExport}
            className="flex-1 h-10 text-[10px] font-black uppercase tracking-widest border-slate-200"
          >
            <Download size={13} className="mr-2" /> Export PDF
          </Button>
          <Button
            onClick={onClose}
            className="flex-1 h-10 bg-slate-900 hover:bg-black text-white text-[10px] font-black uppercase tracking-widest"
          >
            Close
          </Button>
        </div>
      </aside>

      {editLog && (
        <EditPunchModal
          log={editLog}
          onClose={() => setEditLog(null)}
          onSaved={() => onChanged?.()}
        />
      )}
      {addPunchOpen && (
        <AddMissedPunchModal
          userId={employee.user_id}
          userName={employee.full_name}
          onClose={() => setAddPunchOpen(false)}
          onSaved={() => onChanged?.()}
        />
      )}
    </div>
  );
};

const Stat: React.FC<{ label: string; value: string; tone?: 'amber' | 'emerald' }> = ({ label, value, tone }) => (
  <div>
    <p
      className={cn(
        'text-base font-black',
        tone === 'amber' && 'text-amber-600',
        tone === 'emerald' && 'text-emerald-600',
        !tone && 'text-[#0F172A]',
      )}
    >
      {value}
    </p>
    <p className="text-[8px] font-black uppercase tracking-widest text-slate-400 mt-0.5">{label}</p>
  </div>
);

const HeatmapView: React.FC<{ days: EmployeeHeatmapDay[] }> = ({ days }) => {
  const [hovered, setHovered] = useState<EmployeeHeatmapDay | null>(null);

  const months = useMemo(() => {
    const groups = new Map<string, EmployeeHeatmapDay[]>();
    for (const d of days) {
      const key = d.date.slice(0, 7);
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key)!.push(d);
    }
    return Array.from(groups.entries()).sort(([a], [b]) => a.localeCompare(b));
  }, [days]);

  if (days.length === 0) {
    return <p className="text-[10px] font-black uppercase tracking-widest text-slate-400 text-center py-8">No data in this period</p>;
  }

  return (
    <div className="space-y-5">
      {months.map(([key, monthDays]) => {
        const [y, m] = key.split('-').map(Number);
        const monthLabel = new Date(y, m - 1, 1).toLocaleDateString(undefined, { month: 'long', year: 'numeric' });
        const firstDayDow = new Date(y, m - 1, 1).getDay();
        const padCount = (firstDayDow + 6) % 7;
        return (
          <div key={key}>
            <p className="text-[10px] font-black uppercase tracking-widest text-[#0F172A] mb-2">{monthLabel}</p>
            <div className="grid grid-cols-7 gap-1 text-center">
              {['M', 'T', 'W', 'T', 'F', 'S', 'S'].map((l, i) => (
                <span
                  key={i}
                  className="text-[9px] font-black uppercase tracking-widest text-slate-400"
                >
                  {l}
                </span>
              ))}
              {Array.from({ length: padCount }).map((_, i) => (
                <span key={`pad-${i}`} className="h-9" />
              ))}
              {monthDays.map(d => {
                const day = parseInt(d.date.slice(8, 10), 10);
                const isHovered = hovered?.date === d.date;
                return (
                  <button
                    key={d.date}
                    type="button"
                    onMouseEnter={() => setHovered(d)}
                    onFocus={() => setHovered(d)}
                    onMouseLeave={() => setHovered(null)}
                    className={cn(
                      'h-9 rounded-md text-[10px] font-black tabular-nums transition-all',
                      STATUS_COLOR[d.status],
                      isHovered && 'ring-2 ring-blue-600/40 scale-105',
                    )}
                    title={`${d.date} — ${STATUS_LABEL[d.status]}`}
                    aria-label={`${d.date} ${STATUS_LABEL[d.status]}`}
                  >
                    {day}
                  </button>
                );
              })}
            </div>
          </div>
        );
      })}

      <div className="border-t border-slate-100 pt-4">
        <p className="text-[9px] font-black uppercase tracking-widest text-slate-400 mb-2">Legend</p>
        <div className="flex flex-wrap gap-x-3 gap-y-1.5">
          {(['present', 'late', 'wfh', 'absent', 'leave', 'holiday', 'holiday_worked', 'weekend', 'weekend_worked'] as DayStatus[]).map(s => (
            <span key={s} className="inline-flex items-center gap-1.5 text-[9px] font-black uppercase tracking-widest text-slate-600">
              <span className={cn('w-3 h-3 rounded', STATUS_COLOR[s])} /> {STATUS_LABEL[s]}
            </span>
          ))}
        </div>
      </div>

      <div className="border-t border-slate-100 pt-4 min-h-[60px]">
        {hovered ? (
          <div className="text-[10px] font-black uppercase tracking-widest text-slate-600 space-y-0.5 tabular-nums">
            <p className="text-[#0F172A]">{hovered.date} — {STATUS_LABEL[hovered.status]}</p>
            {hovered.punchIn && (
              <p>
                {hovered.punchIn} IN
                {hovered.punchOut && ` · ${hovered.punchOut} OUT`}
                {hovered.hours ? ` · ${hovered.hours}H` : ''}
                {hovered.geoVerified && ' · GEO VERIFIED'}
              </p>
            )}
            {hovered.leaveType && <p>{hovered.leaveType}</p>}
            {hovered.holidayName && <p>{hovered.holidayName}</p>}
          </div>
        ) : (
          <p className="text-[9px] font-black uppercase tracking-widest text-slate-300">Hover a cell for detail</p>
        )}
      </div>
    </div>
  );
};

const LedgerView: React.FC<{ balances: any[]; loading: boolean; leaves: LeaveRecord[] }> = ({
  balances,
  loading,
  leaves,
}) => (
  <div className="space-y-5">
    <div>
      <p className="text-[10px] font-black uppercase tracking-widest text-[#0F172A] mb-2">Balances</p>
      {loading ? (
        <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">Loading…</p>
      ) : balances.length === 0 ? (
        <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">No balance records</p>
      ) : (
        <div className="grid grid-cols-2 gap-2">
          {balances.map((b: any, i: number) => {
            const total = b.balance ?? b.total ?? 0;
            const used = b.used ?? 0;
            const remaining = total - used;
            const pct = total > 0 ? Math.min(100, (used / total) * 100) : 0;
            return (
              <Card key={i} className="p-3 border-slate-200 bg-white">
                <p className="text-[9px] font-black uppercase tracking-widest text-slate-400 truncate">
                  {b.leave_type?.name || b.leave_type || 'Leave'}
                </p>
                <div className="flex items-baseline gap-1.5 mt-1 tabular-nums">
                  <span className="text-base font-black text-[#0F172A]">{remaining.toFixed(1)}</span>
                  <span className="text-[9px] font-black text-slate-400">/ {total.toFixed(1)} REMAINING</span>
                </div>
                <div className="mt-2 h-1 bg-slate-100 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-blue-600 rounded-full"
                    style={{ width: `${pct}%` }}
                  />
                </div>
              </Card>
            );
          })}
        </div>
      )}
    </div>
    <div>
      <p className="text-[10px] font-black uppercase tracking-widest text-[#0F172A] mb-2">Recent Leaves</p>
      {leaves.length === 0 ? (
        <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">None in this period</p>
      ) : (
        <div className="space-y-2">
          {leaves.map(lv => (
            <Card key={lv.id} className="p-3 border-slate-200 bg-white">
              <div className="flex items-center justify-between gap-2">
                <p className="text-[10px] font-black uppercase tracking-widest text-[#0F172A]">
                  {lv.leave_type || 'Leave'} · {lv.days}D
                </p>
                <Badge
                  variant={lv.status.toLowerCase() === 'approved' ? 'success' : lv.status.toLowerCase() === 'rejected' ? 'error' : 'warning'}
                  className="text-[8px] uppercase"
                >
                  {lv.status}
                </Badge>
              </div>
              <p className="text-[9px] font-bold text-slate-500 mt-1 tabular-nums">
                {lv.start_date} → {lv.end_date}
              </p>
              {lv.reason && <p className="text-[10px] text-slate-600 italic mt-1.5 truncate">"{lv.reason}"</p>}
            </Card>
          ))}
        </div>
      )}
    </div>
  </div>
);

const LogView: React.FC<{
  logs: AttendanceLog[];
  canEdit: boolean;
  onEdit: (log: AttendanceLog) => void;
  onAddMissed: () => void;
}> = ({ logs, canEdit, onEdit, onAddMissed }) => {
  return (
    <div className="space-y-2">
      {canEdit && (
        <Button
          variant="outline"
          onClick={onAddMissed}
          className="w-full h-9 text-[9px] font-black uppercase tracking-widest border-dashed border-slate-300 text-slate-500 hover:text-blue-600 hover:border-blue-300"
        >
          <CalendarPlus size={12} className="mr-2" /> Add Missed Punch
        </Button>
      )}
      {logs.length === 0 ? (
        <p className="text-[10px] font-black uppercase tracking-widest text-slate-400 text-center py-8">No punches in this period</p>
      ) : logs.map(l => {
        const inDate = new Date(l.captured_at);
        const out = l.punch_out_time ? new Date(l.punch_out_time) : null;
        return (
          <Card key={l.id} className="p-3 border-slate-200 bg-white">
            <div className="flex items-center justify-between gap-2">
              <p className="text-[10px] font-black uppercase tracking-widest text-[#0F172A] tabular-nums">
                {inDate.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })}
              </p>
              <div className="flex items-center gap-1.5">
                <Badge variant="neutral" className="text-[8px] uppercase">
                  {l.mode}
                </Badge>
                {canEdit && (
                  <button
                    type="button"
                    onClick={() => onEdit(l)}
                    className="p-1 text-slate-400 hover:text-blue-600 hover:bg-blue-50 rounded-md transition-colors"
                    aria-label="Edit punch times"
                    title="Edit punch times"
                  >
                    <Pencil size={12} />
                  </button>
                )}
              </div>
            </div>
            <p className="text-[10px] font-bold text-slate-600 mt-1 tabular-nums">
              {inDate.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} IN
              {out ? ` · ${out.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} OUT` : ' · OPEN'}
            </p>
            {(l.late_minutes || l.early_exit_minutes || l.edited_at) ? (
              <div className="flex flex-wrap gap-1 mt-1.5">
                {l.late_minutes ? (
                  <span className="inline-flex items-center px-1.5 py-0.5 rounded-md bg-amber-50 text-amber-700 text-[8px] font-black uppercase tracking-widest">
                    Late {l.late_minutes}m
                  </span>
                ) : null}
                {l.early_exit_minutes ? (
                  <span className="inline-flex items-center px-1.5 py-0.5 rounded-md bg-rose-50 text-rose-600 text-[8px] font-black uppercase tracking-widest">
                    Early out {l.early_exit_minutes}m
                  </span>
                ) : null}
                {l.edited_at ? (
                  <span
                    className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md bg-slate-100 text-slate-600 text-[8px] font-black uppercase tracking-widest"
                    title={l.edited_by_name ? `Edited by ${l.edited_by_name}` : 'Edited by HR'}
                  >
                    <Pencil size={8} /> Edited{l.edited_by_name ? ` · ${l.edited_by_name}` : ''}
                  </span>
                ) : null}
              </div>
            ) : null}
            {(l.latitude && l.longitude) ? (
              <p className="text-[9px] font-bold text-slate-400 uppercase tracking-widest mt-1 inline-flex items-center gap-1">
                <Navigation size={10} className="text-blue-600" />
                {l.latitude.toFixed(4)}, {l.longitude.toFixed(4)}
              </p>
            ) : null}
            {l.remarks && (
              <p className="text-[9px] font-bold text-slate-500 italic mt-1">{l.remarks}</p>
            )}
          </Card>
        );
      })}
    </div>
  );
};

const HoursView: React.FC<{ days: EmployeeHeatmapDay[] }> = ({ days }) => {
  const workdays = days.filter(d => d.status !== 'weekend' && d.status !== 'holiday' && d.status !== 'future');
  const max = Math.max(10, ...workdays.map(d => d.hours || 0));
  if (workdays.length === 0) {
    return <p className="text-[10px] font-black uppercase tracking-widest text-slate-400 text-center py-8">No data in this period</p>;
  }
  return (
    <div className="space-y-3">
      <p className="text-[10px] font-black uppercase tracking-widest text-[#0F172A]">Hours per Day</p>
      <div className="space-y-1">
        {workdays.map(d => {
          const h = d.hours || 0;
          const pct = (h / max) * 100;
          return (
            <div key={d.date} className="flex items-center gap-3">
              <span className="text-[9px] font-black uppercase tracking-widest text-slate-400 w-16 tabular-nums">
                {d.date.slice(5)}
              </span>
              <div className="flex-1 h-4 bg-slate-50 rounded-md overflow-hidden">
                <div
                  className={cn(
                    'h-full rounded-md transition-all',
                    h >= 9 ? 'bg-emerald-500' : h >= 7 ? 'bg-blue-500' : h > 0 ? 'bg-amber-400' : 'bg-rose-300',
                  )}
                  style={{ width: `${pct}%` }}
                />
              </div>
              <span className="text-[10px] font-black text-[#0F172A] w-12 text-right tabular-nums">
                {h > 0 ? `${h.toFixed(1)}h` : '—'}
              </span>
            </div>
          );
        })}
      </div>
      <p className="text-[9px] font-black uppercase tracking-widest text-slate-400 pt-2 border-t border-slate-100">
        Green ≥9h · Blue ≥7h · Amber &lt;7h · Rose 0h
      </p>
    </div>
  );
};

const CorrectionsView: React.FC<{ corrections: CorrectionRecord[] }> = ({ corrections }) => {
  const handleAction = async (id: number, status: 'approved' | 'rejected') => {
    try {
      await client.post(ENDPOINTS.HR.ATTENDANCE_CORRECTION_ACTION(id), { status });
      toast.success(`Correction ${status}`);
    } catch {
      toast.error(`Failed to ${status} correction`);
    }
  };

  if (corrections.length === 0) {
    return (
      <div className="text-center py-8">
        <CheckCircle size={28} className="mx-auto text-slate-200 mb-2" />
        <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">No corrections</p>
      </div>
    );
  }
  return (
    <div className="space-y-2">
      {corrections.map(c => (
        <Card key={c.id} className="p-3 border-slate-200 bg-white space-y-2">
          <div className="flex items-center justify-between gap-2">
            <p className="text-[10px] font-black uppercase tracking-widest text-[#0F172A] tabular-nums">{c.date}</p>
            <Badge
              variant={c.status === 'submitted' ? 'warning' : c.status === 'approved' ? 'success' : 'error'}
              className="text-[8px] uppercase"
            >
              {c.status}
            </Badge>
          </div>
          <p className="text-[9px] font-black uppercase tracking-widest text-slate-500">
            Mode: {c.requested_mode}
          </p>
          {c.reason && <p className="text-[10px] italic text-slate-600">"{c.reason}"</p>}
          {c.status === 'submitted' && (
            <div className="flex gap-2 pt-1">
              <Button
                onClick={() => handleAction(c.id, 'approved')}
                className="flex-1 h-7 bg-emerald-600 hover:bg-emerald-700 text-white font-black uppercase text-[9px] tracking-widest"
              >
                <CheckCircle size={11} className="mr-1" /> Approve
              </Button>
              <Button
                onClick={() => handleAction(c.id, 'rejected')}
                variant="outline"
                className="flex-1 h-7 border-rose-200 text-rose-600 hover:bg-rose-50 font-black uppercase text-[9px] tracking-widest"
              >
                <XCircle size={11} className="mr-1" /> Reject
              </Button>
            </div>
          )}
        </Card>
      ))}
    </div>
  );
};
