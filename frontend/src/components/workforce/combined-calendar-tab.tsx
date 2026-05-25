import React, { useMemo, useState } from 'react';
import {
  ChevronLeft,
  ChevronRight,
  X,
  RefreshCw,
  Star,
  Sun,
  CalendarDays,
  type LucideIcon,
} from 'lucide-react';
import { Card, Badge, cn } from '../ui-elements';
import {
  useWorkforceData,
  toIsoDate,
  type DateRange,
  type DailyRollup,
  type EmployeeBasic,
} from './workforce-data';
import { EmployeeDrillover } from './employee-drillover';

const MONTHS = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
];

function monthBounds(year: number, month: number): DateRange {
  const from = new Date(year, month, 1);
  const to = new Date(year, month + 1, 0);
  return { from, to };
}

export const CombinedCalendarTab: React.FC = () => {
  const today = new Date();
  const [year, setYear] = useState(today.getFullYear());
  const [month, setMonth] = useState(today.getMonth());
  const [openDay, setOpenDay] = useState<string | null>(null);
  const [drillId, setDrillId] = useState<number | null>(null);

  const range = useMemo(() => monthBounds(year, month), [year, month]);
  const data = useWorkforceData(range);
  const { isLoading, error, refetch, rollup, employees, holidays, holidayDates, logs, leaves, corrections } = data;

  const cells = useMemo(() => {
    const first = new Date(year, month, 1);
    const padCount = (first.getDay() + 6) % 7;
    const padded: (DailyRollup | null)[] = Array.from({ length: padCount }, () => null);
    return [...padded, ...rollup];
  }, [rollup, year, month]);

  const yearOptions = useMemo(() => {
    const y = today.getFullYear();
    return [y - 2, y - 1, y, y + 1];
  }, [today]);

  const stepMonth = (delta: number) => {
    let m = month + delta;
    let y = year;
    if (m < 0) {
      m = 11;
      y -= 1;
    } else if (m > 11) {
      m = 0;
      y += 1;
    }
    setMonth(m);
    setYear(y);
  };

  const dayDetail = useMemo(() => rollup.find(r => r.date === openDay) || null, [rollup, openDay]);
  const drillEmployee = useMemo(
    () => (drillId !== null ? employees.find(e => e.user_id === drillId) || null : null),
    [drillId, employees],
  );

  return (
    <div className="space-y-6">
      <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-3">
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => stepMonth(-1)}
            className="h-10 w-10 inline-flex items-center justify-center bg-white border border-slate-200 rounded-xl text-slate-500 hover:border-blue-600 hover:text-blue-600 transition-colors"
            aria-label="Previous month"
          >
            <ChevronLeft size={16} />
          </button>
          <div className="flex items-center bg-white border border-slate-200 rounded-xl overflow-hidden">
            <select
              value={month}
              onChange={e => setMonth(parseInt(e.target.value, 10))}
              className="h-10 px-4 bg-transparent text-[10px] font-black uppercase tracking-widest text-[#0F172A] outline-none"
            >
              {MONTHS.map((m, i) => (
                <option key={m} value={i}>
                  {m}
                </option>
              ))}
            </select>
            <select
              value={year}
              onChange={e => setYear(parseInt(e.target.value, 10))}
              className="h-10 px-3 bg-transparent text-[10px] font-black uppercase tracking-widest text-[#0F172A] outline-none border-l border-slate-100 tabular-nums"
            >
              {yearOptions.map(y => (
                <option key={y} value={y}>
                  {y}
                </option>
              ))}
            </select>
          </div>
          <button
            type="button"
            onClick={() => stepMonth(1)}
            className="h-10 w-10 inline-flex items-center justify-center bg-white border border-slate-200 rounded-xl text-slate-500 hover:border-blue-600 hover:text-blue-600 transition-colors"
            aria-label="Next month"
          >
            <ChevronRight size={16} />
          </button>
          <button
            type="button"
            onClick={() => {
              setMonth(today.getMonth());
              setYear(today.getFullYear());
            }}
            className="h-10 px-4 bg-white border border-slate-200 rounded-xl text-[10px] font-black uppercase tracking-widest text-[#0F172A] hover:border-blue-600 transition-colors"
          >
            Today
          </button>
        </div>
        <button
          type="button"
          onClick={refetch}
          className="p-2 text-slate-400 hover:text-blue-600 transition-colors"
          aria-label="Refresh"
          title="Refresh"
        >
          <RefreshCw size={16} className={cn(isLoading && 'animate-spin')} />
        </button>
      </div>

      {error ? (
        <Card className="p-8 border-slate-200 text-center">
          <p className="text-[10px] font-black uppercase tracking-widest text-rose-600">{error}</p>
          <button onClick={refetch} className="mt-2 text-[10px] font-black uppercase tracking-widest text-blue-600 underline">
            Retry
          </button>
        </Card>
      ) : (
        <Card className="p-0 border-slate-200 overflow-hidden bg-white">
          <div className="grid grid-cols-7 border-b border-slate-100 bg-slate-50/40">
            {['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].map(d => (
              <div
                key={d}
                className="px-3 py-2 text-[9px] font-black uppercase tracking-widest text-slate-400"
              >
                {d}
              </div>
            ))}
          </div>
          <div className="grid grid-cols-7">
            {cells.map((c, i) => (
              <CalendarCell
                key={c?.date || `pad-${i}`}
                cell={c}
                onClick={() => c && setOpenDay(c.date)}
                isLoading={isLoading}
              />
            ))}
          </div>
        </Card>
      )}

      <Card className="p-3 border-slate-200 bg-white">
        <p className="text-[9px] font-black uppercase tracking-widest text-slate-400 mb-2">In-Cell Counts</p>
        <div className="flex flex-wrap gap-2 text-[9px] font-black uppercase tracking-widest mb-3">
          <CountChip letter="P" tone="emerald" />
          <span className="text-slate-500">Present</span>
          <CountChip letter="A" tone="rose" />
          <span className="text-slate-500">Absent</span>
          <CountChip letter="L" tone="blue" />
          <span className="text-slate-500">On Leave</span>
          <CountChip letter="W" tone="amber" />
          <span className="text-slate-500">Worked Off-Day</span>
          <CountChip letter="LT" tone="orange" />
          <span className="text-slate-500">Late</span>
        </div>
        <p className="text-[9px] font-black uppercase tracking-widest text-slate-400 mb-2 pt-2 border-t border-slate-100">Cell Types</p>
        <div className="flex flex-wrap gap-x-3 gap-y-1.5 text-[9px] font-black uppercase tracking-widest text-slate-600">
          <Legend icon={Star} label="Holiday (dark)" tone="text-slate-700" />
          <Legend icon={Sun} label="Weekend (light)" tone="text-slate-400" />
          <Legend icon={CalendarDays} label="Today (ringed)" tone="text-blue-600" />
        </div>
      </Card>

      {dayDetail && (
        <DayDetailSlideover
          day={dayDetail}
          employees={employees}
          logs={logs}
          leaves={leaves}
          onClose={() => setOpenDay(null)}
          onEmployeeClick={(uid) => {
            setOpenDay(null);
            setDrillId(uid);
          }}
        />
      )}

      {drillEmployee && (
        <EmployeeDrillover
          employee={drillEmployee}
          parentRange={range}
          holidays={holidayDates}
          allLogs={logs}
          allLeaves={leaves}
          allHolidays={holidays}
          allCorrections={corrections}
          onClose={() => setDrillId(null)}
        />
      )}
    </div>
  );
};

const Legend: React.FC<{
  swatch?: string;
  icon?: LucideIcon;
  label: string;
  tone?: string;
}> = ({ swatch, icon: Icon, label, tone }) => (
  <span className="inline-flex items-center gap-1.5">
    {swatch && <span className={cn('w-3 h-3 rounded', swatch)} />}
    {Icon && <Icon size={12} className={tone || 'text-slate-700'} />}
    {label}
  </span>
);

type ChipTone = 'emerald' | 'rose' | 'blue' | 'amber' | 'orange';
const CHIP_TONES: Record<ChipTone, { bg: string; text: string }> = {
  emerald: { bg: 'bg-emerald-100', text: 'text-emerald-700' },
  rose: { bg: 'bg-rose-100', text: 'text-rose-700' },
  blue: { bg: 'bg-blue-100', text: 'text-blue-700' },
  amber: { bg: 'bg-amber-100', text: 'text-amber-700' },
  orange: { bg: 'bg-orange-100', text: 'text-orange-700' },
};

const CountChip: React.FC<{ letter: string; tone: ChipTone; count?: number; compact?: boolean }> = ({
  letter,
  tone,
  count,
  compact,
}) => {
  const t = CHIP_TONES[tone];
  return (
    <span
      className={cn(
        'inline-flex items-center justify-center rounded font-black tabular-nums',
        t.bg,
        t.text,
        compact ? 'px-1 h-4 text-[9px] gap-0.5' : 'px-1.5 h-5 text-[10px] gap-1',
      )}
    >
      <span className="opacity-70">{letter}</span>
      {typeof count === 'number' && <span>{count}</span>}
    </span>
  );
};

const CalendarCell: React.FC<{
  cell: DailyRollup | null;
  onClick: () => void;
  isLoading: boolean;
}> = ({ cell, onClick, isLoading }) => {
  if (!cell) {
    return <div className="aspect-square min-h-[88px] bg-slate-50/30 border-r border-b border-slate-100" />;
  }
  const day = parseInt(cell.date.slice(8, 10), 10);
  const todayIso = toIsoDate(new Date());
  const isToday = cell.date === todayIso;

  if (cell.isHoliday) {
    return (
      <button
        type="button"
        onClick={onClick}
        className="aspect-square min-h-[96px] bg-slate-900 text-white border-r border-b border-slate-100 p-2 text-left hover:bg-slate-800 transition-colors flex flex-col"
      >
        <div className="flex items-center justify-between">
          <p className="text-sm font-black tabular-nums">{day}</p>
          <Star size={12} className="opacity-70" />
        </div>
        {cell.present > 0 && (
          <div className="mt-1.5">
            <CountChip letter="W" tone="amber" count={cell.present} compact />
          </div>
        )}
        <p className="text-[8px] font-black uppercase tracking-widest mt-auto opacity-80 truncate">
          {cell.holidayName}
        </p>
      </button>
    );
  }
  if (cell.isWeekend) {
    return (
      <button
        type="button"
        onClick={onClick}
        className="aspect-square min-h-[96px] bg-slate-50 border-r border-b border-slate-100 p-2 text-left hover:bg-slate-100 transition-colors flex flex-col"
      >
        <div className="flex items-center justify-between">
          <p className="text-sm font-black text-slate-400 tabular-nums">{day}</p>
          <Sun size={12} className="text-slate-300" />
        </div>
        {cell.present > 0 && (
          <div className="mt-1.5">
            <CountChip letter="W" tone="amber" count={cell.present} compact />
          </div>
        )}
        <p className="text-[8px] font-black uppercase tracking-widest mt-auto text-slate-300">
          Weekend
        </p>
      </button>
    );
  }
  if (cell.isFuture) {
    return (
      <button
        type="button"
        onClick={onClick}
        className={cn(
          'aspect-square min-h-[96px] bg-white border-r border-b border-slate-100 p-2 text-left hover:bg-slate-50/50 transition-colors flex flex-col',
          isToday && 'ring-2 ring-blue-600 ring-inset',
        )}
      >
        <p className={cn('text-sm font-black tabular-nums', isToday ? 'text-blue-600' : 'text-slate-300')}>
          {day}
        </p>
        <p className="text-[8px] font-black uppercase tracking-widest text-slate-300 mt-1">
          Upcoming
        </p>
      </button>
    );
  }
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={isLoading}
      className={cn(
        'aspect-square min-h-[96px] bg-white border-r border-b border-slate-100 p-2 text-left hover:bg-slate-50 transition-colors flex flex-col',
        isToday && 'ring-2 ring-blue-600 ring-inset',
      )}
    >
      <div className="flex items-center justify-between">
        <p className={cn('text-sm font-black tabular-nums', isToday ? 'text-blue-600' : 'text-[#0F172A]')}>
          {day}
        </p>
        {isToday && <span className="w-1.5 h-1.5 rounded-full bg-blue-600" />}
      </div>
      {isLoading ? (
        <div className="mt-2 space-y-1 animate-pulse">
          <div className="h-3 w-14 bg-slate-100 rounded" />
          <div className="h-3 w-10 bg-slate-100 rounded" />
        </div>
      ) : (
        <div className="mt-1.5 flex flex-wrap gap-1">
          <CountChip letter="P" tone="emerald" count={cell.present} compact />
          {cell.absent > 0 && <CountChip letter="A" tone="rose" count={cell.absent} compact />}
          {cell.onLeave > 0 && <CountChip letter="L" tone="blue" count={cell.onLeave} compact />}
          {cell.late > 0 && <CountChip letter="LT" tone="orange" count={cell.late} compact />}
        </div>
      )}
    </button>
  );
};

const DayDetailSlideover: React.FC<{
  day: DailyRollup;
  employees: EmployeeBasic[];
  logs: import('./workforce-data').AttendanceLog[];
  leaves: import('./workforce-data').LeaveRecord[];
  onClose: () => void;
  onEmployeeClick: (userId: number) => void;
}> = ({ day, employees, logs, leaves, onClose, onEmployeeClick }) => {
  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const dateObj = new Date(day.date);
  const dayLabel = dateObj.toLocaleDateString(undefined, {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  });

  const presentSet = useMemo(() => {
    const set = new Set<number>();
    for (const l of logs) {
      const iso = toIsoDate(new Date(l.captured_at));
      if (iso === day.date) set.add(l.user_id);
    }
    return set;
  }, [logs, day.date]);

  const onLeaveByEmp = useMemo(() => {
    const map = new Map<number, string>();
    for (const lv of leaves) {
      if (lv.status.toLowerCase() !== 'approved') continue;
      if (day.date >= lv.start_date && day.date <= lv.end_date) {
        if (lv.employee_id) map.set(lv.employee_id, lv.leave_type || 'Leave');
      }
    }
    return map;
  }, [leaves, day.date]);

  const presentList = employees.filter(e => presentSet.has(e.user_id));
  const onLeaveList = employees.filter(e => e.employee_id && onLeaveByEmp.has(e.employee_id));
  const onLeaveIds = new Set(onLeaveList.map(e => e.user_id));
  const absentList =
    day.isWeekend || day.isHoliday || day.isFuture
      ? []
      : employees.filter(e => !presentSet.has(e.user_id) && !onLeaveIds.has(e.user_id));

  return (
    <div className="fixed inset-0 z-50 flex justify-end" role="dialog" aria-modal="true">
      <div
        className="absolute inset-0 bg-slate-900/40 backdrop-blur-[2px] animate-in fade-in duration-200"
        onClick={onClose}
      />
      <aside className="relative w-full max-w-[520px] h-full bg-white shadow-2xl shadow-slate-900/30 flex flex-col animate-in slide-in-from-right duration-200">
        <div className="px-6 py-5 border-b border-slate-100 flex items-start justify-between gap-3">
          <div>
            <h3 className="text-base font-black text-[#0F172A] tracking-tight">{dayLabel}</h3>
            <p className="text-[9px] font-bold text-slate-400 uppercase tracking-widest mt-0.5 tabular-nums">
              {day.totalEmployees} EMPLOYEES TRACKED
              {day.isHoliday && ` · HOLIDAY: ${day.holidayName}`}
              {day.isWeekend && ' · WEEKEND'}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1.5 text-slate-400 hover:text-slate-700 hover:bg-slate-50 rounded-lg transition-colors shrink-0"
            aria-label="Close day detail"
          >
            <X size={18} />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-6 space-y-5">
          {(day.isHoliday || day.isWeekend) && presentList.length > 0 && (
            <div className="p-3 rounded-xl bg-amber-50 border border-amber-200 text-[10px] font-black uppercase tracking-widest text-amber-700">
              {presentList.length} EMPLOYEE{presentList.length === 1 ? '' : 'S'} WORKED ON THIS{' '}
              {day.isHoliday ? 'HOLIDAY' : 'WEEKEND'}
            </div>
          )}
          <Section
            title={day.isHoliday ? 'Worked Holiday' : day.isWeekend ? 'Worked Weekend' : 'Present'}
            count={presentList.length}
            tone={day.isHoliday || day.isWeekend ? 'amber' : 'emerald'}
            list={presentList}
            extras={() => null}
            onClick={onEmployeeClick}
          />
          {day.late > 0 && (
            <p className="text-[10px] font-black uppercase tracking-widest text-amber-600">
              {day.late} LATE ARRIVALS · {day.wfh} WFH
            </p>
          )}
          {!day.isHoliday && !day.isWeekend && (
            <>
              <Section
                title="On Leave"
                count={onLeaveList.length}
                tone="blue"
                list={onLeaveList}
                extras={(emp) => emp.employee_id ? onLeaveByEmp.get(emp.employee_id) || null : null}
                onClick={onEmployeeClick}
              />
              <Section
                title="Absent"
                count={absentList.length}
                tone="rose"
                list={absentList}
                extras={() => null}
                onClick={onEmployeeClick}
              />
            </>
          )}
        </div>
      </aside>
    </div>
  );
};

const Section: React.FC<{
  title: string;
  count: number;
  tone: 'emerald' | 'rose' | 'blue' | 'amber';
  list: EmployeeBasic[];
  extras: (emp: EmployeeBasic) => string | null;
  onClick: (userId: number) => void;
}> = ({ title, count, tone, list, extras, onClick }) => {
  const dot = {
    emerald: 'bg-emerald-500',
    rose: 'bg-rose-500',
    blue: 'bg-blue-500',
    amber: 'bg-amber-500',
  }[tone];
  return (
    <div>
      <div className="flex items-center gap-2 mb-2">
        <span className={cn('w-2 h-2 rounded-full', dot)} />
        <p className="text-[10px] font-black uppercase tracking-widest text-[#0F172A]">{title}</p>
        <Badge variant="neutral" className="text-[8px]">
          {count}
        </Badge>
      </div>
      {list.length === 0 ? (
        <p className="text-[10px] font-black uppercase tracking-widest text-slate-300">None</p>
      ) : (
        <div className="space-y-1">
          {list.map(emp => {
            const extra = extras(emp);
            return (
              <button
                key={emp.user_id}
                type="button"
                onClick={() => onClick(emp.user_id)}
                className="w-full text-left p-2.5 rounded-lg bg-slate-50/40 hover:bg-blue-50 hover:ring-1 hover:ring-blue-100 transition-all flex items-center justify-between gap-2"
              >
                <div className="flex items-center gap-2 min-w-0">
                  <div className="w-7 h-7 rounded-lg bg-white text-blue-600 flex items-center justify-center font-black text-xs shrink-0">
                    {emp.full_name.charAt(0).toUpperCase()}
                  </div>
                  <div className="min-w-0">
                    <p className="text-[11px] font-black text-[#0F172A] truncate">{emp.full_name}</p>
                    <p className="text-[9px] font-bold text-slate-400 uppercase tracking-widest truncate">
                      {emp.department || '—'}
                    </p>
                  </div>
                </div>
                {extra && (
                  <span className="text-[9px] font-black uppercase tracking-widest text-slate-500 shrink-0">
                    {extra}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
};
