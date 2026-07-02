import React, { useMemo, useState } from 'react';
import {
  Search,
  RefreshCw,
  Download,
  ChevronRight,
  AlertTriangle,
  CircleDot,
  Diamond,
  TrendingUp,
  Clock,
  CalendarDays,
  Inbox,
  type LucideIcon,
} from 'lucide-react';
import { Card, Button, cn } from '../ui-elements';
import { PeriodPicker, presetToRange, type DateRange } from '../period-picker';
import { useWorkforceData, type RosterRow, type EmployeeStatus } from './workforce-data';
import { EmployeeDrillover } from './employee-drillover';
import { exportRosterPdf, exportRosterXlsx } from './workforce-export';

interface AttendanceTabProps {
  initialEmployeeId?: number;
  onEmployeeChange?: (id: number | null) => void;
}

const STATUS_LABEL: Record<EmployeeStatus, string> = {
  on_track: 'On Track',
  review: 'Review',
  flag: 'Flag',
};

const STATUS_STYLE: Record<EmployeeStatus, string> = {
  on_track: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  review: 'bg-amber-50 text-amber-700 border-amber-200',
  flag: 'bg-rose-50 text-rose-700 border-rose-200',
};

const STATUS_ICON: Record<EmployeeStatus, LucideIcon> = {
  on_track: CircleDot,
  review: Diamond,
  flag: AlertTriangle,
};

export const AttendanceTab: React.FC<AttendanceTabProps> = ({ initialEmployeeId, onEmployeeChange }) => {
  const [range, setRange] = useState<DateRange>(() => presetToRange('this_month'));
  const [search, setSearch] = useState('');
  const [deptFilter, setDeptFilter] = useState<string>('all');
  const [anomaliesOnly, setAnomaliesOnly] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
  const [drillId, setDrillId] = useState<number | null>(initialEmployeeId ?? null);

  const data = useWorkforceData(range);
  const { isLoading, error, refetch, roster, holidayDates, workingDaysInRange, employees } = data;

  const departments = useMemo(() => {
    const set = new Set<string>();
    for (const e of employees) if (e.department) set.add(e.department);
    return Array.from(set).sort();
  }, [employees]);

  const filteredRoster = useMemo(() => {
    const q = search.trim().toLowerCase();
    return roster.filter(r => {
      if (deptFilter !== 'all' && r.department !== deptFilter) return false;
      if (anomaliesOnly && r.status === 'on_track') return false;
      if (!q) return true;
      return (
        r.user_name.toLowerCase().includes(q) ||
        r.user_email.toLowerCase().includes(q) ||
        (r.department || '').toLowerCase().includes(q)
      );
    });
  }, [roster, search, deptFilter, anomaliesOnly]);

  const kpis = useMemo(() => {
    const totalLate = roster.reduce((s, r) => s + r.lateCount, 0);
    const totalLeave = roster.reduce((s, r) => s + r.leaveByType.total, 0);
    const leaveSplit = roster.reduce(
      (s, r) => ({
        sick: s.sick + r.leaveByType.sick,
        casual: s.casual + r.leaveByType.casual,
        earned: s.earned + r.leaveByType.earned,
      }),
      { sick: 0, casual: 0, earned: 0 },
    );
    const avgPct =
      roster.length > 0
        ? roster.reduce((s, r) => s + r.presentPct, 0) / roster.length
        : 0;
    const pending = roster.reduce((s, r) => s + r.pendingCorrections, 0);
    return { avgPct, totalLate, totalLeave, leaveSplit, pending };
  }, [roster]);

  const handleOpenEmployee = (id: number) => {
    setDrillId(id);
    onEmployeeChange?.(id);
  };

  const handleCloseEmployee = () => {
    setDrillId(null);
    onEmployeeChange?.(null);
  };

  const drillEmployee = useMemo(
    () => (drillId !== null ? employees.find(e => e.user_id === drillId) || null : null),
    [drillId, employees],
  );

  return (
    <div className="space-y-6">
      <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
        <div className="flex flex-wrap items-center gap-3">
          <PeriodPicker value={range} onChange={setRange} holidays={holidayDates} initialPreset="this_month" />
          <select
            value={deptFilter}
            onChange={e => setDeptFilter(e.target.value)}
            className="h-10 px-4 bg-white border border-slate-200 rounded-xl text-[10px] font-black uppercase tracking-widest text-[#0F172A] outline-none hover:border-blue-600 transition-colors"
          >
            <option value="all">DEPT: ALL</option>
            {departments.map(d => (
              <option key={d} value={d}>
                DEPT: {d.toUpperCase()}
              </option>
            ))}
          </select>
          <label className="inline-flex items-center gap-2 px-4 h-10 bg-white border border-slate-200 rounded-xl text-[10px] font-black uppercase tracking-widest text-[#0F172A] cursor-pointer hover:border-blue-600 transition-colors">
            <input
              type="checkbox"
              checked={anomaliesOnly}
              onChange={e => setAnomaliesOnly(e.target.checked)}
              className="w-3.5 h-3.5 accent-blue-600"
            />
            Anomalies Only
          </label>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={refetch}
            className="p-2 text-slate-400 hover:text-blue-600 transition-colors"
            aria-label="Refresh"
            title="Refresh"
          >
            <RefreshCw size={16} className={cn(isLoading && 'animate-spin')} />
          </button>
          <div className="relative">
            <button
              type="button"
              onClick={() => setExportOpen(o => !o)}
              className="inline-flex items-center gap-2 h-10 px-4 bg-white border border-slate-200 rounded-xl text-[10px] font-black uppercase tracking-widest text-[#0F172A] hover:border-blue-600 transition-colors"
            >
              <Download size={14} /> Export
            </button>
            {exportOpen && (
              <div className="absolute right-0 mt-2 w-44 bg-white border border-slate-200 rounded-xl shadow-2xl shadow-slate-900/10 z-30 overflow-hidden animate-in fade-in zoom-in-95 duration-150">
                <button
                  type="button"
                  onClick={() => {
                    exportRosterPdf(filteredRoster, range);
                    setExportOpen(false);
                  }}
                  className="w-full text-left px-4 py-2.5 text-[10px] font-black uppercase tracking-widest text-slate-700 hover:bg-slate-50"
                >
                  PDF Report
                </button>
                <button
                  type="button"
                  onClick={() => {
                    exportRosterXlsx(filteredRoster, range);
                    setExportOpen(false);
                  }}
                  className="w-full text-left px-4 py-2.5 text-[10px] font-black uppercase tracking-widest text-slate-700 hover:bg-slate-50 border-t border-slate-100"
                >
                  Excel Workbook
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiCard
          icon={TrendingUp}
          label="Avg Attendance"
          value={isLoading ? '—' : `${(kpis.avgPct * 100).toFixed(1)}%`}
          hint={`${roster.length} EMPLOYEES · ${workingDaysInRange} WORKING DAYS`}
        />
        <KpiCard
          icon={Clock}
          label="Late Arrivals"
          value={isLoading ? '—' : kpis.totalLate.toString()}
          hint="THIS PERIOD"
          valueClass="text-amber-600"
        />
        <KpiCard
          icon={CalendarDays}
          label="Leave Days"
          value={isLoading ? '—' : kpis.totalLeave.toString()}
          hint={`S ${kpis.leaveSplit.sick} · C ${kpis.leaveSplit.casual} · E ${kpis.leaveSplit.earned}`}
        />
        <KpiCard
          icon={Inbox}
          label="Pending Approvals"
          value={isLoading ? '—' : kpis.pending.toString()}
          hint="CORRECTIONS"
          dark
        />
      </div>

      <Card className="p-0 border-slate-200 overflow-hidden bg-white">
        <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between bg-slate-50/40 gap-4">
          <h4 className="text-sm font-black text-[#0F172A] tracking-tight uppercase">
            Employee Roster
            {!isLoading && (
              <span className="ml-2 text-slate-400 font-bold text-[10px]">
                ({filteredRoster.length}/{roster.length})
              </span>
            )}
          </h4>
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 pointer-events-none" />
            <input
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Search employee..."
              className="pl-10 pr-4 h-9 bg-white border border-slate-200 rounded-xl text-[10px] font-black uppercase tracking-widest w-64 focus:ring-2 focus:ring-blue-600/10 outline-none"
            />
          </div>
        </div>
        {error ? (
          <div className="py-16 text-center text-[10px] font-black uppercase tracking-widest text-rose-600">
            {error}
            <button
              onClick={refetch}
              className="ml-3 text-blue-600 underline underline-offset-2"
            >
              Retry
            </button>
          </div>
        ) : isLoading ? (
          <RosterSkeleton />
        ) : filteredRoster.length === 0 ? (
          <div className="py-16 text-center">
            <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">
              {anomaliesOnly
                ? 'No anomalies — every employee on track'
                : 'No employees match these filters'}
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead className="bg-white border-b border-slate-100 sticky top-0">
                <tr>
                  <Th>Employee</Th>
                  <Th className="text-right">Present</Th>
                  <Th className="text-right">Late</Th>
                  <Th className="text-right">Avg Hrs</Th>
                  <Th>Leave (S/C/E)</Th>
                  <Th className="text-right">Pend</Th>
                  <Th>Status</Th>
                  <Th className="w-10" />
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {filteredRoster.map(row => (
                  <RosterRowItem key={row.user_id} row={row} onOpen={handleOpenEmployee} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {drillEmployee && (
        <EmployeeDrillover
          employee={drillEmployee}
          parentRange={range}
          holidays={holidayDates}
          allLogs={data.logs}
          allLeaves={data.leaves}
          allHolidays={data.holidays}
          allCorrections={data.corrections}
          onClose={handleCloseEmployee}
          onChanged={refetch}
        />
      )}
    </div>
  );
};

const Th: React.FC<React.ThHTMLAttributes<HTMLTableCellElement>> = ({ className, children, ...props }) => (
  <th
    className={cn(
      'px-6 py-3 text-[9px] font-black text-slate-400 uppercase tracking-widest',
      className,
    )}
    {...props}
  >
    {children}
  </th>
);

const RosterRowItem: React.FC<{ row: RosterRow; onOpen: (id: number) => void }> = ({ row, onOpen }) => {
  const StatusIcon = STATUS_ICON[row.status];
  return (
    <tr
      className="hover:bg-slate-50/60 transition-colors group cursor-pointer"
      onClick={() => onOpen(row.user_id)}
    >
      <td className="px-6 py-3">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-xl bg-blue-50 text-blue-600 flex items-center justify-center font-black text-sm">
            {row.user_name.charAt(0).toUpperCase()}
          </div>
          <div className="min-w-0">
            <p className="text-sm font-black text-[#0F172A] truncate">{row.user_name}</p>
            <p className="text-[9px] font-bold text-slate-400 uppercase tracking-widest truncate">
              {row.department || '—'}{row.manager_name ? ` · MGR ${row.manager_name}` : ''}
            </p>
          </div>
        </div>
      </td>
      <td className="px-6 py-3 text-right">
        <p className="text-sm font-black text-[#0F172A] tabular-nums">
          {row.presentDays}
          <span className="text-slate-300">/</span>
          {row.workingDays}
        </p>
        <p className="text-[9px] font-bold text-slate-400 tabular-nums">
          {(row.presentPct * 100).toFixed(0)}%
        </p>
      </td>
      <td className="px-6 py-3 text-right text-sm font-black text-[#0F172A] tabular-nums">
        {row.lateCount}
      </td>
      <td className="px-6 py-3 text-right text-sm font-black text-[#0F172A] tabular-nums">
        {row.avgHours > 0 ? `${row.avgHours.toFixed(1)}h` : '—'}
      </td>
      <td className="px-6 py-3">
        <div className="flex items-center gap-1.5 text-[10px] font-black uppercase tracking-widest tabular-nums">
          <LeaveChip label="S" count={row.leaveByType.sick} tone="rose" />
          <LeaveChip label="C" count={row.leaveByType.casual} tone="amber" />
          <LeaveChip label="E" count={row.leaveByType.earned} tone="emerald" />
        </div>
      </td>
      <td className="px-6 py-3 text-right">
        {row.pendingCorrections > 0 ? (
          <span className="inline-flex items-center justify-center min-w-[1.5rem] h-5 px-1.5 rounded-full bg-blue-600 text-white text-[9px] font-black tabular-nums">
            {row.pendingCorrections}
          </span>
        ) : (
          <span className="text-slate-300">—</span>
        )}
      </td>
      <td className="px-6 py-3">
        <span
          className={cn(
            'inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg border text-[9px] font-black uppercase tracking-widest',
            STATUS_STYLE[row.status],
          )}
        >
          <StatusIcon size={11} />
          {STATUS_LABEL[row.status]}
        </span>
      </td>
      <td className="px-6 py-3 text-right text-slate-300 group-hover:text-blue-600 transition-colors">
        <ChevronRight size={16} />
      </td>
    </tr>
  );
};

const LeaveChip: React.FC<{ label: string; count: number; tone: 'rose' | 'amber' | 'emerald' }> = ({ label, count, tone }) => {
  const tones = {
    rose: count > 0 ? 'bg-rose-50 text-rose-700' : 'bg-slate-50 text-slate-300',
    amber: count > 0 ? 'bg-amber-50 text-amber-700' : 'bg-slate-50 text-slate-300',
    emerald: count > 0 ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-50 text-slate-300',
  } as const;
  return (
    <span className={cn('inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md', tones[tone])}>
      <span className="opacity-60">{label}</span>
      <span>{count}</span>
    </span>
  );
};

const KpiCard: React.FC<{
  icon: LucideIcon;
  label: string;
  value: string;
  hint: string;
  valueClass?: string;
  dark?: boolean;
}> = ({ icon: Icon, label, value, hint, valueClass, dark }) => (
  <Card
    className={cn(
      'p-5',
      dark
        ? 'bg-slate-900 border-slate-900 text-white'
        : 'bg-white border-slate-200',
    )}
  >
    <div className="flex items-center justify-between mb-2">
      <p
        className={cn(
          'text-[9px] font-black uppercase tracking-widest',
          dark ? 'opacity-60' : 'text-slate-400',
        )}
      >
        {label}
      </p>
      <Icon size={14} className={dark ? 'opacity-50' : 'text-slate-300'} />
    </div>
    <h3 className={cn('text-2xl font-black tabular-nums', valueClass || (dark ? '' : 'text-[#0F172A]'))}>
      {value}
    </h3>
    <p className={cn('text-[9px] font-black uppercase tracking-widest mt-1 tabular-nums', dark ? 'opacity-60' : 'text-slate-400')}>
      {hint}
    </p>
  </Card>
);

const RosterSkeleton: React.FC = () => (
  <div className="divide-y divide-slate-50">
    {Array.from({ length: 6 }).map((_, i) => (
      <div key={i} className="px-6 py-4 flex items-center gap-4 animate-pulse">
        <div className="w-8 h-8 rounded-xl bg-slate-100" />
        <div className="flex-1 space-y-1.5">
          <div className="h-3 w-40 bg-slate-100 rounded" />
          <div className="h-2 w-24 bg-slate-100 rounded" />
        </div>
        <div className="h-3 w-16 bg-slate-100 rounded" />
        <div className="h-3 w-12 bg-slate-100 rounded" />
        <div className="h-3 w-20 bg-slate-100 rounded" />
        <div className="h-5 w-20 bg-slate-100 rounded-lg" />
      </div>
    ))}
  </div>
);
