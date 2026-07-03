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
import { PeriodPicker, toIsoDate, type DateRange } from '../period-picker';
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
  { id: 'heatmap', label: 'Calendar', icon: CalendarRange },
  { id: 'ledger', label: 'Leave', icon: ListChecks },
  { id: 'log', label: 'Punches', icon: History },
  { id: 'hours', label: 'Hours', icon: BarChart3 },
  { id: 'corrections', label: 'Requests', icon: Wrench },
];

const STATUS_COLOR: Record<DayStatus, string> = {
  present: 'bg-emerald-500 text-white',
  late: 'bg-amber-500 text-white',
  wfh: 'bg-indigo-400 text-white',
  absent: 'bg-rose-500 text-white',
  leave: 'bg-blue-500 text-white',
  holiday: 'bg-slate-700 text-white',
  holiday_worked: 'bg-slate-700 text-white cell-ring-worked',
  weekend: 'bg-slate-100 text-slate-400',
  weekend_worked: 'bg-slate-200 text-slate-700 cell-ring-worked',
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

/* Shared micro-typography: calmer than the old all-caps-black-
   everywhere look. Section titles small caps; body copy sentence
   case at 13px. */
const SECTION_TITLE = 'sb-group-label font-bold uppercase text-slate-400';

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

  const inherited =
    range.from.getTime() === parentRange.from.getTime() &&
    range.to.getTime() === parentRange.to.getTime();

  return (
    <div className="fixed inset-0 z-50 flex justify-end" role="dialog" aria-modal="true">
      <div
        className="absolute inset-0 bg-slate-900/50 backdrop-blur-[2px] animate-in fade-in duration-200"
        onClick={onClose}
      />
      <aside className="relative w-full max-w-[640px] h-full bg-white shadow-2xl flex flex-col animate-in slide-in-from-right duration-200">
        {/* ---- identity header ---- */}
        <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0">
            <div className="w-12 h-12 rounded-2xl bg-blue-50 text-blue-600 flex items-center justify-center font-black text-lg shrink-0">
              {employee.full_name.charAt(0).toUpperCase()}
            </div>
            <div className="min-w-0">
              <h3 className="text-lg font-black text-[#0F172A] tracking-tight truncate">
                {employee.full_name}
              </h3>
              <div className="flex items-center gap-1 mt-1 flex-wrap">
                {employee.employee_id && <MetaChip>{`#${employee.employee_id}`}</MetaChip>}
                {employee.department && <MetaChip>{employee.department}</MetaChip>}
                {employee.manager_name && <MetaChip>{`Reports to ${employee.manager_name}`}</MetaChip>}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-1 shrink-0">
            <button
              type="button"
              onClick={handleExport}
              className="p-2 text-slate-400 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-colors"
              aria-label="Export PDF"
              title="Export PDF"
            >
              <Download size={16} />
            </button>
            <button
              type="button"
              onClick={onClose}
              className="p-2 text-slate-400 hover:text-slate-600 hover:bg-slate-50 rounded-lg transition-colors"
              aria-label="Close drillover"
            >
              <X size={16} />
            </button>
          </div>
        </div>

        {/* ---- KPI band ---- */}
        <div className="px-6 py-4 border-b border-slate-100 bg-slate-50/60 space-y-3">
          <div className="grid grid-cols-4 gap-2">
            <StatTile label="Present" value={`${summary.presentDays}/${summary.working}`} hint="working days" />
            <StatTile label="Late arrivals" value={summary.late.toString()} tone={summary.late > 0 ? 'amber' : undefined} hint="this period" />
            <StatTile label="Attendance" value={`${(summary.pct * 100).toFixed(0)}%`} tone="emerald" hint="of working days" />
            <StatTile label="Avg hours" value={summary.avgHours > 0 ? `${summary.avgHours.toFixed(1)}h` : '—'} hint="per day worked" />
          </div>
          <div className="flex items-center gap-2">
            <PeriodPicker value={range} onChange={setRange} holidays={holidays} align="start" />
            <span className={cn('sb-group-label font-bold uppercase', inherited ? 'text-slate-400' : 'text-blue-600')}>
              {inherited ? 'Inherited period' : 'Custom period'}
            </span>
          </div>
        </div>

        {/* ---- segmented tabs ---- */}
        <div className="px-6 pt-4">
          <div className="inline-flex p-1 gap-1 bg-slate-100 rounded-xl">
            {TABS.map(t => {
              const Icon = t.icon;
              const active = tab === t.id;
              return (
                <button
                  key={t.id}
                  type="button"
                  onClick={() => setTab(t.id)}
                  className={cn(
                    'inline-flex items-center gap-1.5 px-3 h-8 rounded-lg sb-group-label font-bold uppercase transition-all',
                    active
                      ? 'bg-white text-[#0F172A] shadow-sm'
                      : 'text-slate-500 hover:text-slate-600',
                  )}
                >
                  <Icon size={12} className={active ? 'text-blue-600' : ''} />
                  {t.label}
                  {t.id === 'corrections' && pendingCount > 0 && (
                    <span className="inline-flex items-center justify-center min-w-[1.1rem] h-4 px-1 rounded-full bg-blue-600 text-white text-[8px] font-black">
                      {pendingCount}
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        </div>

        {/* ---- content ---- */}
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

const MetaChip: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <span className="inline-flex items-center px-1.5 py-0.5 rounded-md bg-slate-100 text-slate-500 text-[9px] font-bold uppercase tracking-wider whitespace-nowrap">
    {children}
  </span>
);

const StatTile: React.FC<{
  label: string;
  value: string;
  hint?: string;
  tone?: 'amber' | 'emerald';
}> = ({ label, value, hint, tone }) => (
  <div className="p-3 rounded-xl border border-slate-200 bg-white">
    <p className={SECTION_TITLE}>{label}</p>
    <p
      className={cn(
        'text-lg font-black tabular-nums mt-0.5',
        tone === 'amber' && 'text-amber-600',
        tone === 'emerald' && 'text-emerald-600',
        !tone && 'text-[#0F172A]',
      )}
    >
      {value}
    </p>
    {hint && <p className="text-[9px] font-bold text-slate-400 mt-0.5">{hint}</p>}
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
    return <EmptyState text="No data in this period" />;
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
            <p className="text-sm font-black text-[#0F172A] mb-2">{monthLabel}</p>
            <div className="grid grid-cols-7 gap-1 text-center">
              {['Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su'].map((l, i) => (
                <span key={i} className={cn(SECTION_TITLE, 'pb-1')}>
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
                      isHovered && 'cell-ring-hover',
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

      {/* day detail — reserved height so the layout never jumps */}
      <div className="rounded-xl border border-slate-200 bg-slate-50/60 p-3 min-h-[64px]">
        {hovered ? (
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <span className={cn('w-3 h-3 rounded', STATUS_COLOR[hovered.status])} />
              <p className="text-sm font-black text-[#0F172A] tabular-nums">
                {new Date(hovered.date).toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' })}
                <span className="text-slate-400 font-bold"> · {STATUS_LABEL[hovered.status]}</span>
              </p>
            </div>
            {hovered.punchIn && (
              <p className="sb-item-sm font-medium text-slate-600 tabular-nums">
                In {hovered.punchIn}
                {hovered.punchOut && ` — Out ${hovered.punchOut}`}
                {hovered.hours ? ` · ${hovered.hours}h` : ''}
                {hovered.geoVerified && ' · Geo verified'}
              </p>
            )}
            {hovered.leaveType && <p className="sb-item-sm font-medium text-slate-600">{hovered.leaveType}</p>}
            {hovered.holidayName && <p className="sb-item-sm font-medium text-slate-600">{hovered.holidayName}</p>}
          </div>
        ) : (
          <p className={cn(SECTION_TITLE, 'pt-2')}>Hover a day for details</p>
        )}
      </div>

      <div>
        <p className={cn(SECTION_TITLE, 'mb-2')}>Legend</p>
        <div className="flex flex-wrap gap-1">
          {(['present', 'late', 'wfh', 'absent', 'leave', 'holiday', 'holiday_worked', 'weekend', 'weekend_worked'] as DayStatus[]).map(s => (
            <span
              key={s}
              className="inline-flex items-center gap-1.5 px-2 py-1 rounded-md border border-slate-200 bg-white text-[9px] font-bold text-slate-600"
            >
              <span className={cn('w-2 h-2 rounded', STATUS_COLOR[s])} /> {STATUS_LABEL[s]}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
};

const EmptyState: React.FC<{ text: string; icon?: React.ReactNode }> = ({ text, icon }) => (
  <div className="text-center py-8">
    {icon}
    <p className={SECTION_TITLE}>{text}</p>
  </div>
);

const LedgerView: React.FC<{ balances: any[]; loading: boolean; leaves: LeaveRecord[] }> = ({
  balances,
  loading,
  leaves,
}) => (
  <div className="space-y-5">
    <div>
      <p className={cn(SECTION_TITLE, 'mb-2')}>Leave balances</p>
      {loading ? (
        <p className={SECTION_TITLE}>Loading…</p>
      ) : balances.length === 0 ? (
        <p className={SECTION_TITLE}>No balance records</p>
      ) : (
        <div className="grid grid-cols-2 gap-2">
          {balances.map((b: any, i: number) => {
            const total = b.balance ?? b.total ?? 0;
            const used = b.used ?? 0;
            const remaining = total - used;
            const pct = total > 0 ? Math.min(100, (used / total) * 100) : 0;
            return (
              <div key={i} className="p-3 rounded-xl border border-slate-200 bg-white">
                <p className={cn(SECTION_TITLE, 'truncate')}>
                  {b.leave_type?.name || b.leave_type || 'Leave'}
                </p>
                <div className="flex items-baseline gap-1.5 mt-1 tabular-nums">
                  <span className="text-lg font-black text-[#0F172A]">{remaining.toFixed(1)}</span>
                  <span className="text-[9px] font-bold text-slate-400">of {total.toFixed(1)} left</span>
                </div>
                <div className="mt-2 h-1 bg-slate-100 rounded-full overflow-hidden">
                  <div className="h-full bg-blue-600 rounded-full" style={{ width: `${pct}%` }} />
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
    <div>
      <p className={cn(SECTION_TITLE, 'mb-2')}>Leave in this period</p>
      {leaves.length === 0 ? (
        <p className={SECTION_TITLE}>None in this period</p>
      ) : (
        <div className="space-y-2">
          {leaves.map(lv => (
            <div key={lv.id} className="p-3 rounded-xl border border-slate-200 bg-white">
              <div className="flex items-center justify-between gap-2">
                <p className="sb-item-sm font-black text-[#0F172A]">
                  {lv.leave_type || 'Leave'}
                  <span className="text-slate-400 font-bold"> · {lv.days} day{lv.days === 1 ? '' : 's'}</span>
                </p>
                <Badge
                  variant={lv.status.toLowerCase() === 'approved' ? 'success' : lv.status.toLowerCase() === 'rejected' ? 'error' : 'warning'}
                  className="text-[8px] uppercase"
                >
                  {lv.status}
                </Badge>
              </div>
              <p className="text-[10px] font-bold text-slate-500 mt-1 tabular-nums">
                {lv.start_date} → {lv.end_date}
              </p>
              {lv.reason && <p className="sb-item-sm text-slate-500 italic mt-1 truncate">"{lv.reason}"</p>}
            </div>
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
          className="w-full h-9 sb-group-label font-bold uppercase border-dashed border-slate-300 text-slate-500 hover:text-blue-600 hover:border-blue-300"
        >
          <CalendarPlus size={12} className="mr-2" /> Add missed punch
        </Button>
      )}
      {logs.length === 0 ? (
        <EmptyState text="No punches in this period" />
      ) : logs.map(l => {
        const inDate = new Date(l.captured_at);
        const out = l.punch_out_time ? new Date(l.punch_out_time) : null;
        return (
          <div key={l.id} className="p-3 rounded-xl border border-slate-200 bg-white">
            <div className="flex items-center justify-between gap-2">
              <div className="min-w-0">
                <p className="sb-item-sm font-black text-[#0F172A] tabular-nums">
                  {inDate.toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' })}
                </p>
                <p className="sb-item-sm font-medium text-slate-500 tabular-nums mt-0.5">
                  In {inDate.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                  {out
                    ? ` — Out ${out.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`
                    : ' — still open'}
                </p>
              </div>
              <div className="flex items-center gap-1.5 shrink-0">
                <Badge variant="neutral" className="text-[8px] uppercase">
                  {l.mode}
                </Badge>
                {canEdit && (
                  <button
                    type="button"
                    onClick={() => onEdit(l)}
                    className="p-1.5 text-slate-400 hover:text-blue-600 hover:bg-blue-50 rounded-md transition-colors"
                    aria-label="Edit punch times"
                    title="Edit punch times"
                  >
                    <Pencil size={12} />
                  </button>
                )}
              </div>
            </div>
            {(l.late_minutes || l.early_exit_minutes || l.edited_at || (l.latitude && l.longitude)) ? (
              <div className="flex flex-wrap items-center gap-1 mt-2">
                {l.late_minutes ? (
                  <span className="inline-flex items-center px-1.5 py-0.5 rounded-md bg-amber-50 text-amber-700 text-[8px] font-black uppercase tracking-wider">
                    Late {l.late_minutes}m
                  </span>
                ) : null}
                {l.early_exit_minutes ? (
                  <span className="inline-flex items-center px-1.5 py-0.5 rounded-md bg-rose-50 text-rose-600 text-[8px] font-black uppercase tracking-wider">
                    Early out {l.early_exit_minutes}m
                  </span>
                ) : null}
                {l.edited_at ? (
                  <span
                    className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md bg-slate-100 text-slate-600 text-[8px] font-black uppercase tracking-wider"
                    title={l.edited_by_name ? `Edited by ${l.edited_by_name}` : 'Edited by HR'}
                  >
                    <Pencil size={8} /> Edited{l.edited_by_name ? ` · ${l.edited_by_name}` : ''}
                  </span>
                ) : null}
                {(l.latitude && l.longitude) ? (
                  <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md bg-blue-50 text-blue-600 text-[8px] font-black uppercase tracking-wider">
                    <Navigation size={8} />
                    {l.latitude.toFixed(4)}, {l.longitude.toFixed(4)}
                  </span>
                ) : null}
              </div>
            ) : null}
            {l.remarks && (
              <p className="sb-item-sm text-slate-500 italic mt-1.5">{l.remarks}</p>
            )}
          </div>
        );
      })}
    </div>
  );
};

const HoursView: React.FC<{ days: EmployeeHeatmapDay[] }> = ({ days }) => {
  const workdays = days.filter(d => d.status !== 'weekend' && d.status !== 'holiday' && d.status !== 'future');
  const max = Math.max(10, ...workdays.map(d => d.hours || 0));
  if (workdays.length === 0) {
    return <EmptyState text="No data in this period" />;
  }
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className={SECTION_TITLE}>Hours per day</p>
        <div className="flex items-center gap-2">
          <LegendDot className="bg-emerald-500" label="9h+" />
          <LegendDot className="bg-blue-500" label="7–9h" />
          <LegendDot className="bg-amber-400" label="<7h" />
          <LegendDot className="bg-rose-300" label="none" />
        </div>
      </div>
      <div className="space-y-1">
        {workdays.map(d => {
          const h = d.hours || 0;
          const pct = (h / max) * 100;
          return (
            <div key={d.date} className="flex items-center gap-3">
              <span className="text-[10px] font-bold text-slate-400 w-16 tabular-nums">
                {new Date(d.date).toLocaleDateString(undefined, { day: '2-digit', month: 'short' })}
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
    </div>
  );
};

const LegendDot: React.FC<{ className: string; label: string }> = ({ className, label }) => (
  <span className="inline-flex items-center gap-1 text-[9px] font-bold text-slate-500">
    <span className={cn('w-2 h-2 rounded-full', className)} /> {label}
  </span>
);

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
      <EmptyState
        text="No correction requests"
        icon={<CheckCircle size={28} className="mx-auto text-slate-200 mb-2" />}
      />
    );
  }
  return (
    <div className="space-y-2">
      {corrections.map(c => (
        <div key={c.id} className="p-3 rounded-xl border border-slate-200 bg-white space-y-2">
          <div className="flex items-center justify-between gap-2">
            <p className="sb-item-sm font-black text-[#0F172A] tabular-nums">{c.date}</p>
            <Badge
              variant={c.status === 'submitted' ? 'warning' : c.status === 'approved' ? 'success' : 'error'}
              className="text-[8px] uppercase"
            >
              {c.status}
            </Badge>
          </div>
          <p className="sb-item-sm font-medium text-slate-500">
            Requested mode: <span className="font-black text-slate-600">{c.requested_mode}</span>
          </p>
          {c.reason && <p className="sb-item-sm italic text-slate-500">"{c.reason}"</p>}
          {c.status === 'submitted' && (
            <div className="flex gap-2 pt-1">
              <Button
                onClick={() => handleAction(c.id, 'approved')}
                className="flex-1 h-8 bg-emerald-600 hover:bg-emerald-700 text-white font-black uppercase text-[9px] tracking-wider"
              >
                <CheckCircle size={11} className="mr-1" /> Approve
              </Button>
              <Button
                onClick={() => handleAction(c.id, 'rejected')}
                variant="outline"
                className="flex-1 h-8 border-rose-200 text-rose-600 hover:bg-rose-50 font-black uppercase text-[9px] tracking-wider"
              >
                <XCircle size={11} className="mr-1" /> Reject
              </Button>
            </div>
          )}
        </div>
      ))}
    </div>
  );
};
