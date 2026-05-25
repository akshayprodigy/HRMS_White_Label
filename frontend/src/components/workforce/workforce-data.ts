import { useEffect, useMemo, useState, useCallback } from 'react';
import { client } from '../../api/client';
import { ENDPOINTS } from '../../api/endpoints';
import { toIsoDate, fromIsoDate, type DateRange } from '../period-picker';

const LATE_HOUR = 9;
const LATE_MINUTE = 30;

// Sunday only — Saturdays are working days.
const WEEKEND_DAYS = new Set<number>([0]);

export function isWeekendDay(d: Date): boolean {
  return WEEKEND_DAYS.has(d.getDay());
}

export type EmployeeStatus = 'on_track' | 'review' | 'flag';

export type DayStatus =
  | 'present'
  | 'late'
  | 'wfh'
  | 'absent'
  | 'leave'
  | 'holiday'
  | 'holiday_worked'
  | 'weekend'
  | 'weekend_worked'
  | 'future';

export interface EmployeeBasic {
  user_id: number;
  employee_id?: number;
  full_name: string;
  email?: string;
  department?: string;
  designation?: string;
  manager_name?: string;
}

export interface AttendanceLog {
  id: number;
  user_id: number;
  user_name?: string;
  user_email?: string;
  captured_at: string;
  punch_out_time?: string | null;
  mode: string;
  latitude?: number | null;
  longitude?: number | null;
  remarks?: string | null;
}

export interface LeaveRecord {
  id: number;
  employee_id: number;
  employee_name?: string;
  employee_email?: string;
  leave_type: string | null;
  leave_type_code?: string | null;
  start_date: string;
  end_date: string;
  is_half_day: boolean;
  half_day_session?: string | null;
  days: number;
  reason: string;
  status: string;
}

export interface CorrectionRecord {
  id: number;
  user_id: number;
  date: string;
  requested_mode: string;
  reason: string;
  status: string;
  created_at: string;
}

export interface HolidayRecord {
  id: number;
  name: string;
  date: string;
  is_optional: boolean;
}

export interface LeaveByType {
  sick: number;
  casual: number;
  earned: number;
  other: number;
  total: number;
}

export interface RosterRow {
  user_id: number;
  employee_id?: number;
  user_name: string;
  user_email: string;
  department?: string;
  designation?: string;
  manager_name?: string;
  presentDays: number;
  workingDays: number;
  presentPct: number;
  lateCount: number;
  avgHours: number;
  leaveByType: LeaveByType;
  pendingCorrections: number;
  status: EmployeeStatus;
}

export interface DailyRollup {
  date: string;
  isWeekend: boolean;
  isHoliday: boolean;
  isFuture: boolean;
  holidayName?: string;
  totalEmployees: number;
  present: number;
  absent: number;
  onLeave: number;
  late: number;
  wfh: number;
}

export interface EmployeeHeatmapDay {
  date: string;
  status: DayStatus;
  punchIn?: string;
  punchOut?: string;
  hours?: number;
  mode?: string;
  leaveType?: string;
  holidayName?: string;
  geoVerified?: boolean;
}

const STATUS_THRESHOLD_OK = 0.9;
const STATUS_THRESHOLD_REVIEW = 0.75;

function bucketLeave(code: string | null | undefined, name: string | null): keyof Omit<LeaveByType, 'total'> {
  const k = (code || name || '').toLowerCase();
  if (!k) return 'other';
  if (k.includes('sick') || k === 'sl') return 'sick';
  if (k.includes('casual') || k === 'cl') return 'casual';
  if (k.includes('earned') || k.includes('annual') || k.includes('privilege') || k === 'el' || k === 'pl') return 'earned';
  return 'other';
}

function isLatePunch(captured_at: string): boolean {
  const d = new Date(captured_at);
  const h = d.getHours();
  const m = d.getMinutes();
  return h > LATE_HOUR || (h === LATE_HOUR && m > LATE_MINUTE);
}

function isWfhMode(mode: string | undefined): boolean {
  if (!mode) return false;
  const m = mode.toLowerCase();
  return m.includes('wfh') || m.includes('remote') || m.includes('home');
}

function hoursBetween(inIso: string, outIso?: string | null): number {
  if (!outIso) return 0;
  const ms = new Date(outIso).getTime() - new Date(inIso).getTime();
  return Math.max(0, ms / 3_600_000);
}

function* eachDay(range: DateRange): Generator<Date> {
  const cursor = new Date(range.from);
  cursor.setHours(0, 0, 0, 0);
  const end = new Date(range.to);
  end.setHours(0, 0, 0, 0);
  while (cursor <= end) {
    yield new Date(cursor);
    cursor.setDate(cursor.getDate() + 1);
  }
}

function leaveCoversDate(lv: LeaveRecord, iso: string): boolean {
  return iso >= lv.start_date && iso <= lv.end_date;
}

function logFields(log: AttendanceLog): Pick<EmployeeHeatmapDay, 'punchIn' | 'punchOut' | 'hours' | 'mode' | 'geoVerified'> {
  const punchIn = log.captured_at;
  const punchOut = log.punch_out_time || undefined;
  const hours = hoursBetween(punchIn, punchOut);
  return {
    punchIn: new Date(punchIn).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    punchOut: punchOut ? new Date(punchOut).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : undefined,
    hours: Math.round(hours * 10) / 10,
    mode: log.mode,
    geoVerified: !!(log.latitude && log.longitude),
  };
}

function classifyDay(args: {
  iso: string;
  isWeekend: boolean;
  holidayName?: string;
  isFuture: boolean;
  log?: AttendanceLog;
  approvedLeave?: LeaveRecord;
}): EmployeeHeatmapDay {
  const { iso, isWeekend, holidayName, isFuture, log, approvedLeave } = args;
  // Holidays / weekends still surface punch detail when the employee worked.
  if (holidayName) {
    return log
      ? { date: iso, status: 'holiday_worked', holidayName, ...logFields(log) }
      : { date: iso, status: 'holiday', holidayName };
  }
  if (isWeekend) {
    return log
      ? { date: iso, status: 'weekend_worked', ...logFields(log) }
      : { date: iso, status: 'weekend' };
  }
  if (log) {
    const wfh = isWfhMode(log.mode);
    const late = !wfh && isLatePunch(log.captured_at);
    return {
      date: iso,
      status: wfh ? 'wfh' : late ? 'late' : 'present',
      ...logFields(log),
    };
  }
  if (approvedLeave) {
    return { date: iso, status: 'leave', leaveType: approvedLeave.leave_type || 'Leave' };
  }
  if (isFuture) return { date: iso, status: 'future' };
  return { date: iso, status: 'absent' };
}

function deriveStatus(presentPct: number, pendingCorrections: number): EmployeeStatus {
  if (presentPct >= STATUS_THRESHOLD_OK && pendingCorrections === 0) return 'on_track';
  if (presentPct < STATUS_THRESHOLD_REVIEW) return 'flag';
  return 'review';
}

export function buildEmployeeHeatmap(
  range: DateRange,
  employee: EmployeeBasic,
  logs: AttendanceLog[],
  leaves: LeaveRecord[],
  holidays: Map<string, HolidayRecord>,
  today: Date = new Date(),
): EmployeeHeatmapDay[] {
  const todayIso = toIsoDate(today);
  const empLogs = logs.filter(l => l.user_id === employee.user_id);
  const logByDay = new Map<string, AttendanceLog>();
  for (const l of empLogs) {
    const iso = toIsoDate(new Date(l.captured_at));
    if (!logByDay.has(iso)) logByDay.set(iso, l);
  }
  const empLeaves = leaves.filter(
    lv => lv.employee_id === employee.employee_id && lv.status.toLowerCase() === 'approved',
  );
  const days: EmployeeHeatmapDay[] = [];
  for (const d of eachDay(range)) {
    const iso = toIsoDate(d);
    const isWeekend = isWeekendDay(d);
    const holiday = holidays.get(iso);
    const log = logByDay.get(iso);
    const leave = empLeaves.find(lv => leaveCoversDate(lv, iso));
    days.push(
      classifyDay({
        iso,
        isWeekend,
        holidayName: holiday?.name,
        isFuture: iso > todayIso,
        log,
        approvedLeave: leave,
      }),
    );
  }
  return days;
}

function aggregateRoster(args: {
  range: DateRange;
  employees: EmployeeBasic[];
  logs: AttendanceLog[];
  leaves: LeaveRecord[];
  holidays: Map<string, HolidayRecord>;
  corrections: CorrectionRecord[];
  today?: Date;
}): RosterRow[] {
  const { range, employees, logs, leaves, holidays, corrections, today = new Date() } = args;
  const todayIso = toIsoDate(today);
  let workingDaysInRange = 0;
  for (const d of eachDay(range)) {
    const iso = toIsoDate(d);
    const isWeekend = isWeekendDay(d);
    if (isWeekend || holidays.has(iso) || iso > todayIso) continue;
    workingDaysInRange++;
  }
  const pendingByUser = new Map<number, number>();
  for (const c of corrections) {
    if (c.status === 'submitted') {
      pendingByUser.set(c.user_id, (pendingByUser.get(c.user_id) || 0) + 1);
    }
  }
  return employees.map(emp => {
    const days = buildEmployeeHeatmap(range, emp, logs, leaves, holidays, today);
    let presentDays = 0,
      lateCount = 0,
      hoursSum = 0,
      hoursCount = 0;
    const leaveByType: LeaveByType = { sick: 0, casual: 0, earned: 0, other: 0, total: 0 };
    for (const d of days) {
      if (d.status === 'present' || d.status === 'wfh' || d.status === 'late') {
        presentDays++;
        if (d.status === 'late') lateCount++;
        if (d.hours && d.hours > 0) {
          hoursSum += d.hours;
          hoursCount++;
        }
      }
      if (d.status === 'leave') {
        const bucket = bucketLeave(null, d.leaveType || null);
        leaveByType[bucket]++;
        leaveByType.total++;
      }
    }
    const pendingCorrections = pendingByUser.get(emp.user_id) || 0;
    const presentPct = workingDaysInRange > 0 ? presentDays / workingDaysInRange : 0;
    const avgHours = hoursCount > 0 ? hoursSum / hoursCount : 0;
    return {
      user_id: emp.user_id,
      employee_id: emp.employee_id,
      user_name: emp.full_name,
      user_email: emp.email || '',
      department: emp.department,
      designation: emp.designation,
      manager_name: emp.manager_name,
      presentDays,
      workingDays: workingDaysInRange,
      presentPct,
      lateCount,
      avgHours: Math.round(avgHours * 10) / 10,
      leaveByType,
      pendingCorrections,
      status: deriveStatus(presentPct, pendingCorrections),
    };
  });
}

function buildDailyRollup(args: {
  range: DateRange;
  employees: EmployeeBasic[];
  logs: AttendanceLog[];
  leaves: LeaveRecord[];
  holidays: Map<string, HolidayRecord>;
  today?: Date;
}): DailyRollup[] {
  const { range, employees, logs, leaves, holidays, today = new Date() } = args;
  const todayIso = toIsoDate(today);
  const totalEmployees = employees.length;
  const empByUser = new Map<number, EmployeeBasic>();
  for (const e of employees) empByUser.set(e.user_id, e);
  const logsByDayUser = new Map<string, Set<number>>();
  const lateByDay = new Map<string, number>();
  const wfhByDay = new Map<string, number>();
  for (const l of logs) {
    const iso = toIsoDate(new Date(l.captured_at));
    if (!logsByDayUser.has(iso)) logsByDayUser.set(iso, new Set());
    logsByDayUser.get(iso)!.add(l.user_id);
    const wfh = isWfhMode(l.mode);
    if (wfh) wfhByDay.set(iso, (wfhByDay.get(iso) || 0) + 1);
    else if (isLatePunch(l.captured_at)) lateByDay.set(iso, (lateByDay.get(iso) || 0) + 1);
  }
  const out: DailyRollup[] = [];
  for (const d of eachDay(range)) {
    const iso = toIsoDate(d);
    const isWeekend = isWeekendDay(d);
    const holiday = holidays.get(iso);
    const isFuture = iso > todayIso;
    let onLeave = 0;
    if (!isWeekend && !holiday) {
      for (const lv of leaves) {
        if (lv.status.toLowerCase() !== 'approved') continue;
        if (leaveCoversDate(lv, iso)) onLeave++;
      }
    }
    const presentSet = logsByDayUser.get(iso) || new Set();
    const present = presentSet.size;
    const absent =
      isWeekend || holiday || isFuture
        ? 0
        : Math.max(0, totalEmployees - present - onLeave);
    out.push({
      date: iso,
      isWeekend,
      isHoliday: !!holiday,
      isFuture,
      holidayName: holiday?.name,
      totalEmployees,
      present,
      absent,
      onLeave,
      late: lateByDay.get(iso) || 0,
      wfh: wfhByDay.get(iso) || 0,
    });
  }
  return out;
}

export interface WorkforceData {
  isLoading: boolean;
  error: string | null;
  refetch: () => void;
  employees: EmployeeBasic[];
  logs: AttendanceLog[];
  leaves: LeaveRecord[];
  holidays: Map<string, HolidayRecord>;
  holidayDates: Set<string>;
  corrections: CorrectionRecord[];
  roster: RosterRow[];
  rollup: DailyRollup[];
  workingDaysInRange: number;
}

function normalizeEmployee(raw: any): EmployeeBasic {
  const user = raw.user || {};
  return {
    user_id: raw.user_id ?? user.id,
    employee_id: raw.id,
    full_name: user.full_name || raw.full_name || 'Unknown',
    email: user.email || raw.email,
    department: raw.department,
    designation: raw.designation,
    manager_name: raw.manager_name,
  };
}

export function useWorkforceData(range: DateRange): WorkforceData {
  const [employees, setEmployees] = useState<EmployeeBasic[]>([]);
  const [logs, setLogs] = useState<AttendanceLog[]>([]);
  const [leaves, setLeaves] = useState<LeaveRecord[]>([]);
  const [holidays, setHolidays] = useState<Map<string, HolidayRecord>>(new Map());
  const [corrections, setCorrections] = useState<CorrectionRecord[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refetchKey, setRefetchKey] = useState(0);

  const dateFrom = toIsoDate(range.from);
  const dateTo = toIsoDate(range.to);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setIsLoading(true);
      setError(null);
      try {
        const [empRes, logRes, leaveRes, holRes, corrRes] = await Promise.all([
          client.get(ENDPOINTS.HR.EMPLOYEES),
          client.get(ENDPOINTS.ATTENDANCE.ALL, { params: { date_from: dateFrom, date_to: dateTo } }),
          client.get(ENDPOINTS.LEAVE.HISTORY, { params: { limit: 1000 } }),
          client.get(ENDPOINTS.HR.HOLIDAYS),
          client.get(ENDPOINTS.HR.ATTENDANCE_CORRECTIONS),
        ]);
        if (cancelled) return;
        const empList = Array.isArray(empRes.data)
          ? empRes.data
          : empRes.data?.items || [];
        const employeesNorm: EmployeeBasic[] = empList
          .map(normalizeEmployee)
          .filter((e: EmployeeBasic) => Number.isFinite(e.user_id));
        setEmployees(employeesNorm);
        setLogs(logRes.data || []);
        const leaveData: LeaveRecord[] = (leaveRes.data || []).filter((lv: LeaveRecord) => {
          // Pre-filter to those that might overlap with the range
          return lv.end_date >= dateFrom && lv.start_date <= dateTo;
        });
        setLeaves(leaveData);
        const holMap = new Map<string, HolidayRecord>();
        for (const h of holRes.data || []) {
          holMap.set(typeof h.date === 'string' ? h.date : toIsoDate(new Date(h.date)), h);
        }
        setHolidays(holMap);
        setCorrections(corrRes.data || []);
      } catch (e: any) {
        if (!cancelled) {
          setError(e?.message || 'Failed to load workforce data');
        }
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    };
    load();
    return () => {
      cancelled = true;
    };
  }, [dateFrom, dateTo, refetchKey]);

  const roster = useMemo(
    () => aggregateRoster({ range, employees, logs, leaves, holidays, corrections }),
    [range, employees, logs, leaves, holidays, corrections],
  );

  const rollup = useMemo(
    () => buildDailyRollup({ range, employees, logs, leaves, holidays }),
    [range, employees, logs, leaves, holidays],
  );

  const holidayDates = useMemo(() => new Set(holidays.keys()), [holidays]);

  const workingDaysInRange = useMemo(() => {
    const todayIso = toIsoDate(new Date());
    let n = 0;
    for (const d of eachDay(range)) {
      const iso = toIsoDate(d);
      const isWeekend = isWeekendDay(d);
      if (isWeekend || holidays.has(iso) || iso > todayIso) continue;
      n++;
    }
    return n;
  }, [range, holidays]);

  const refetch = useCallback(() => setRefetchKey(k => k + 1), []);

  return {
    isLoading,
    error,
    refetch,
    employees,
    logs,
    leaves,
    holidays,
    holidayDates,
    corrections,
    roster,
    rollup,
    workingDaysInRange,
  };
}

// Re-export utilities for consumers that need to format dates consistently
export { toIsoDate, fromIsoDate };
export type { DateRange };
