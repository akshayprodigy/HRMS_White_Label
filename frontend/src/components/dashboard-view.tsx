import React, { useState, useEffect } from 'react';
import {
  Users,
  Clock,
  Calendar,
  CalendarDays,
  CheckCircle2, 
  AlertCircle, 
  TrendingUp, 
  Briefcase,
  MapPin,
  ChevronRight,
  Target,
  FileText,
  DollarSign,
  ShieldCheck,
  LayoutDashboard,
  Zap,
  Plus,
  ArrowRight,
  MessageSquare,
  History,
  Play,
  Pause,
  Square,
  UserCheck,
  Coffee,
  Umbrella,
  ClipboardCheck,
  MoreVertical,
  Cake,
  Award
} from 'lucide-react';
import { Card, Button, Badge, TimerCard, cn } from './ui-elements';
import { 
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, LineChart, Line, AreaChart, Area
} from 'recharts';
import { toast } from 'sonner';
import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';
import { useTimer } from '../contexts/timer-context';

interface MyWeekDay {
  date: string;
  is_today: boolean;
  is_weekend: boolean;
  holiday_name?: string | null;
  on_leave: boolean;
  leave_type?: string | null;
  shift: {
    name: string;
    start_time: string;
    end_time: string;
    is_overnight: boolean;
    source: 'assigned' | 'default';
  };
}

/** Seven-day shift outlook. Today is highlighted; holidays, approved
 * leave and week-offs replace the shift label where they apply. */
const MyWeekStrip = ({ onNavigate }: { onNavigate: (tab: string) => void }) => {
  const [days, setDays] = useState<MyWeekDay[]>([]);

  useEffect(() => {
    client
      .get(ENDPOINTS.SHIFTS.MY_WEEK)
      .then(r => setDays(Array.isArray(r.data?.days) ? r.data.days : []))
      .catch(() => setDays([]));
  }, []);

  if (days.length === 0) return null;

  // Template names often embed the timing ("Night (22:00-06:30)") —
  // trim it so labels don't show the hours twice.
  const shiftName = (name: string) => name.replace(/\s*\(.*\)\s*$/, '');

  const today = days.find(d => d.is_today);
  const todayLabel = today
    ? today.holiday_name
      ? today.holiday_name
      : today.on_leave
        ? `On leave${today.leave_type ? ` · ${today.leave_type}` : ''}`
        : today.is_weekend
          ? 'Week off'
          : `${shiftName(today.shift.name)} · ${today.shift.start_time}–${today.shift.end_time}${today.shift.is_overnight ? ' (+1d)' : ''}`
    : null;

  return (
    <Card className="p-8 bg-white border-slate-100 shadow-sm">
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-2 mb-4">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-full bg-blue-50 flex items-center justify-center text-[#2563EB] border border-blue-100">
            <CalendarDays size={16} />
          </div>
          <h3 className="text-lg font-black text-[#0F172A] uppercase tracking-tight">My Week</h3>
          {todayLabel && (
            <span className="text-[10px] font-black uppercase tracking-widest text-[#2563EB] bg-blue-50 border border-blue-100 rounded-full px-3 py-1">
              Today · {todayLabel}
            </span>
          )}
        </div>
        <button
          onClick={() => onNavigate('my-shift')}
          className="text-[10px] font-black text-slate-400 uppercase tracking-widest hover:text-[#2563EB] transition-colors text-left"
        >
          My Shift & Requests
        </button>
      </div>

      <div className="grid grid-cols-7 gap-2">
        {days.map(d => {
          const dt = new Date(d.date);
          const dayName = dt.toLocaleDateString(undefined, { weekday: 'short' });
          const dayNum = dt.getDate();
          let body: React.ReactNode;
          if (d.holiday_name) {
            body = <p className="sb-item-sm font-black text-slate-500 mt-1">{d.holiday_name}</p>;
          } else if (d.on_leave) {
            body = <p className="sb-item-sm font-black text-[#2563EB] mt-1">{d.leave_type || 'On leave'}</p>;
          } else if (d.is_weekend) {
            body = <p className="sb-item-sm font-black text-slate-400 mt-1">Week off</p>;
          } else {
            body = (
              <div className="mt-1">
                <p className="sb-item-sm font-black text-[#0F172A] tabular-nums">
                  {d.shift.start_time}–{d.shift.end_time}
                  {d.shift.is_overnight && (
                    <span className="text-amber-600"> +1d</span>
                  )}
                </p>
                <p className="text-[9px] font-bold text-slate-400 uppercase tracking-wider mt-0.5 truncate">
                  {shiftName(d.shift.name)}{d.shift.source === 'default' ? ' · org default' : ''}
                </p>
              </div>
            );
          }
          return (
            <div
              key={d.date}
              className={cn(
                'p-3 rounded-xl border',
                d.is_today
                  ? 'bg-blue-50 border-blue-100'
                  : 'bg-slate-50 border-slate-100',
              )}
            >
              <div className="flex items-center justify-between gap-1">
                <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">
                  {dayName} <span className="text-slate-600">{dayNum}</span>
                </p>
                {d.is_today && (
                  <span className="text-[8px] font-black uppercase tracking-widest bg-[#2563EB] text-white rounded-full px-2 py-0.5">
                    Today
                  </span>
                )}
              </div>
              {body}
            </div>
          );
        })}
      </div>
    </Card>
  );
};

const performanceData = [
  { name: 'Mon', value: 78 },
  { name: 'Tue', value: 85 },
  { name: 'Wed', value: 82 },
  { name: 'Thu', value: 88.5 },
  { name: 'Fri', value: 86 },
];

interface DashboardProps {
  onNavigate: (tab: string) => void;
  onLogout: () => void;
  attendanceMarked: boolean;
  alreadyPunchedOut?: boolean;
  onPunchedOut?: () => void;
  userRole?: string;
}

export const DashboardView = ({ onNavigate, onLogout, attendanceMarked, alreadyPunchedOut = false, onPunchedOut, userRole = "employee" }: DashboardProps) => {
  const [projects, setProjects] = useState<any[]>([]);
  const [tasks, setTasks] = useState<any[]>([]);
  const [timesheetData, setTimesheetData] = useState<any>(null);
  const [me, setMe] = useState<any>(null);
  const [myUtilization, setMyUtilization] = useState<any>(null);
  const [leaveBalances, setLeaveBalances] = useState<any[]>([]);
  const [holidays, setHolidays] = useState<any[]>([]);
  const [celebrations, setCelebrations] = useState<{ birthdays: any[]; anniversaries: any[] }>({ birthdays: [], anniversaries: [] });
  const [isLoading, setIsLoading] = useState(true);

  const { status: unifiedTimerStatus, start, pause, resume, stop } = useTimer();

  useEffect(() => {
    fetchDashboardData();
  }, []);

  const fetchDashboardData = async () => {
    try {
      setIsLoading(true);
      const results = await Promise.allSettled([
        client.get(ENDPOINTS.PROJECTS.LIST),
        client.get(ENDPOINTS.TASKS.MY_TASKS),
        client.get(ENDPOINTS.LEAVE.BALANCES),
        client.get(ENDPOINTS.HR.HOLIDAYS),
        client.get(ENDPOINTS.TIMESHEET.MY),
        client.get(ENDPOINTS.AUTH.ME),
        client.get(ENDPOINTS.TIMESHEET.UTILIZATION_MY, {
          params: { range: 'weekly' },
        }),
        client.get(ENDPOINTS.HR.UPCOMING_CELEBRATIONS, { params: { days: 30 } }),
      ]);

      const [
        projRes,
        taskRes,
        leaveRes,
        holidayRes,
        timesheetRes,
        meRes,
        utilRes,
        celebRes,
      ] = results;

      if (projRes.status === 'fulfilled') {
        setProjects(projRes.value.data);
      }

      if (taskRes.status === 'fulfilled') {
        // Flatten tasks from projects for the dashboard view
        const allTasks = (taskRes.value.data || []).flatMap((p: any) =>
          (p.tasks || []).map((t: any) => ({ ...t, project_name: p.name }))
        );
        setTasks(allTasks);
      } else {
        setTasks([]);
      }

      if (leaveRes.status === 'fulfilled') {
        setLeaveBalances(leaveRes.value.data);
      }

      if (holidayRes.status === 'fulfilled') {
        setHolidays((holidayRes.value.data || []).slice(0, 3));
      }

      if (timesheetRes.status === 'fulfilled') {
        setTimesheetData(timesheetRes.value.data);
      }

      if (meRes.status === 'fulfilled') {
        setMe(meRes.value.data);
      }

      if (utilRes.status === 'fulfilled') {
        setMyUtilization(utilRes.value.data);
      } else {
        setMyUtilization(null);
      }

      if (celebRes.status === 'fulfilled') {
        setCelebrations({
          birthdays: celebRes.value.data?.birthdays || [],
          anniversaries: celebRes.value.data?.anniversaries || [],
        });
      } else {
        setCelebrations({ birthdays: [], anniversaries: [] });
      }
    } catch (error) {
      console.error("Dashboard Sync Failed", error);
    } finally {
      setIsLoading(false);
    }
  };

  const tasksDoneCount = tasks.filter(t => t.status === 'Done').length;
  const totalHoursLogged = timesheetData ? (timesheetData.total_seconds / 3600).toFixed(1) : '0';

  const chartData = timesheetData?.daily_data?.map((d: any) => ({
    name: new Date(d.day).toLocaleDateString(undefined, { weekday: 'short' }),
    value: Math.min(100, (d.total_seconds / (8 * 3600)) * 100)
  })).slice(-7) || performanceData;

  const currentPerformance = chartData.length > 0 ? Math.round(chartData[chartData.length - 1].value) : 88;

  const parseWorkItemSelection = (raw: string) => {
    if (!raw) return { taskId: undefined, subtaskId: undefined };
    if (raw.startsWith('s:')) {
      // format: s:{taskId}:{subtaskId}
      const parts = raw.slice(2).split(':');
      const tId = parseInt(parts[0]);
      const sId = parseInt(parts[1]);
      return {
        taskId: Number.isFinite(tId) ? tId : undefined,
        subtaskId: Number.isFinite(sId) ? sId : undefined,
      };
    }
    if (raw.startsWith('t:')) {
      const id = parseInt(raw.slice(2));
      return { taskId: Number.isFinite(id) ? id : undefined, subtaskId: undefined };
    }
    const id = parseInt(raw);
    return { taskId: Number.isFinite(id) ? id : undefined, subtaskId: undefined };
  };

  const handleStartTimer = async (projectId: string, taskSelection: string) => {
    try {
      const pid = parseInt(projectId);
      if (!Number.isFinite(pid)) {
        toast.error('Select a project to start');
        return;
      }

      const { taskId, subtaskId } = parseWorkItemSelection(taskSelection);

      // Block timer start if this specific work item has a pending completion request
      if (taskId) {
        try {
          const reqs = await client.get(ENDPOINTS.TASKS.COMPLETION_REQUESTS(taskId));
          const hasPending = (reqs.data || []).some((r: any) => {
            if (r.status !== 'pending') return false;
            if (subtaskId != null) return r.subtask_id === subtaskId;
            return r.subtask_id == null;
          });
          if (hasPending) {
            const label = subtaskId ? 'subtask' : 'task';
            toast.error('Timer blocked', {
              description: `This ${label} has a pending approval request. Wait for PM action before logging more time.`,
            });
            return;
          }
        } catch {
          // if check fails, allow timer to proceed
        }
      }

      await start(pid, taskId ?? null, subtaskId ?? null);
      toast.success("Timer Started");
    } catch (error: any) {
      toast.error("Failed to start timer", {
        description: error.response?.data?.error?.message || "Check active timers"
      });
    }
  };

  const handlePauseTimer = async () => {
    try {
      await pause();
      toast.info("Timer Paused");
    } catch (error) {
      toast.error("Failed to pause timer");
    }
  };

  const handleResumeTimer = async () => {
    try {
      await resume();
      toast.info("Timer Resumed");
    } catch (error) {
      toast.error("Failed to resume timer");
    }
  };

  const handleStopTimer = async () => {
    try {
      await stop();
      toast.success("Worklog Saved", { description: "Session synchronized with database." });
    } catch (error) {
      toast.error("Failed to stop timer");
    }
  };

  const [punchOutBusy, setPunchOutBusy] = useState(false);
  const [punchOutPrompt, setPunchOutPrompt] = useState<'idle' | 'timer-running'>('idle');

  // Best-effort geolocation snapshot — mirrors what the punch-in modal does
  // so HR has matching forensics for both ends of the day. Times out fast
  // (3s) so a missing GPS signal can't block the user from punching out.
  const tryGetCoords = (): Promise<
    { latitude: number; longitude: number; accuracy?: number } | null
  > =>
    new Promise((resolve) => {
      if (!('geolocation' in navigator)) {
        resolve(null);
        return;
      }
      let settled = false;
      const safety = window.setTimeout(() => {
        if (!settled) {
          settled = true;
          resolve(null);
        }
      }, 3000);
      navigator.geolocation.getCurrentPosition(
        (position) => {
          if (settled) return;
          settled = true;
          window.clearTimeout(safety);
          resolve({
            latitude: position.coords.latitude,
            longitude: position.coords.longitude,
            accuracy: position.coords.accuracy,
          });
        },
        () => {
          if (settled) return;
          settled = true;
          window.clearTimeout(safety);
          resolve(null);
        },
        { enableHighAccuracy: false, timeout: 2500, maximumAge: 60_000 },
      );
    });

  const submitPunchOut = async (afterStop = false) => {
    setPunchOutBusy(true);
    try {
      const coords = await tryGetCoords();
      await client.post(ENDPOINTS.ATTENDANCE.PUNCH_OUT, coords ?? {});
      toast.success(
        afterStop ? 'Timer stopped & punched out' : 'Punched out',
        {
          description:
            'Your attendance is finalized for today. You can stay logged in.',
        },
      );
      setPunchOutPrompt('idle');
      onPunchedOut?.();
      // No auto-logout — let the user keep browsing their day's summary.
      // The Punch Out button auto-disables via onPunchedOut().
    } catch (err: any) {
      const status = err?.response?.status;
      const detail = err?.response?.data?.detail;
      // STRICT geo rejection -> 422 with structured detail.
      let msg: string;
      if (status === 422 && detail && typeof detail === 'object') {
        msg = detail.message
          || (detail.nearest_fence_name && detail.distance_to_fence_meters != null
            ? `You're ${Math.round(detail.distance_to_fence_meters)}m from ${detail.nearest_fence_name}. Move closer to punch out.`
            : 'Punch-out rejected by geo policy.');
      } else if (typeof detail === 'string') {
        msg = detail;
      } else {
        msg = err?.message || 'Punch-out failed';
      }
      toast.error(msg);
    } finally {
      setPunchOutBusy(false);
    }
  };

  const handleEndWorkday = () => {
    if (unifiedTimerStatus.isActive) {
      setPunchOutPrompt('timer-running');
      return;
    }
    void submitPunchOut(false);
  };

  const handleStopAndPunchOut = async () => {
    setPunchOutBusy(true);
    try {
      await stop();
    } catch {
      toast.error('Failed to stop timer — please stop it manually, then try again.');
      setPunchOutBusy(false);
      return;
    }
    await submitPunchOut(true);
  };

  const handleStartBreak = (type: string) => {
    toast.success(`${type} Started`, {
      description: `Your ${type.toLowerCase()} session has been logged in the system.`,
      style: { background: '#2563EB', color: '#fff' }
    });
  };

  const isManagement = userRole === 'hr';

  const taskOptionsByProjectId = React.useMemo(() => {
    const map: Record<string, { id: number | string; name: string }[]> = {};
    const meId = typeof me?.id === 'number' ? me.id : null;
    for (const t of tasks) {
      if (!t?.project_id || !t?.id) continue;
      const pid = t.project_id.toString();
      if (!map[pid]) map[pid] = [];

      if (!meId || t.assignee_id === meId) {
        map[pid].push({ id: `t:${t.id}`, name: t.title });
      }

      if (meId && Array.isArray(t.subtasks)) {
        for (const st of t.subtasks) {
          if (!st?.id) continue;
          if (st.assignee_id !== meId) continue;
          map[pid].push({
            id: `s:${t.id}:${st.id}`,
            name: `${t.title} / ${st.title}`,
          });
        }
      }
    }
    return map;
  }, [tasks, me]);

  const timerProjectOptions = React.useMemo(() => {
    const byId: Record<string, { id: number; name: string }> = {};
    for (const t of tasks) {
      if (!t?.project_id) continue;
      const pid = t.project_id.toString();
      if (byId[pid]) continue;
      const name = t.project_name || `Project ${pid}`;
      byId[pid] = { id: t.project_id, name };
    }
    return Object.values(byId);
  }, [tasks]);

  const timerSelectionId = unifiedTimerStatus.subtaskId
    ? `s:${unifiedTimerStatus.subtaskId}`
    : unifiedTimerStatus.taskId
    ? `t:${unifiedTimerStatus.taskId}`
    : undefined;

  const timerCardStatus = {
    isActive: unifiedTimerStatus.isActive,
    isPaused: unifiedTimerStatus.isPaused,
    seconds: unifiedTimerStatus.seconds,
    project_id: unifiedTimerStatus.projectId,
    task_id: timerSelectionId,
  };

  const assignmentRows = React.useMemo(() => {
    const items = (myUtilization?.items || []) as any[];
    if (items.length === 0) return [];
    return items.slice(0, 8).map((it: any) => {
      const usedH = Number(it.used_hours || 0);
      const estH = typeof it.estimated_hours === 'number' ? it.estimated_hours : null;
      const ratio = estH && estH > 0 ? usedH / estH : null;
      const dot = ratio !== null && ratio > 1.0 ? 'bg-red-500' : 'bg-blue-500';
      const badge = ratio !== null && ratio > 1.0 ? 'OVER' : 'TRACKING';
      const badgeClass =
        ratio !== null && ratio > 1.0
          ? 'text-amber-500 bg-amber-50'
          : 'text-blue-500 bg-blue-50';
      const title = it.subtask_title
        ? `${it.task_title} / ${it.subtask_title}`
        : it.task_title;
      const estLabel = estH !== null ? `${estH.toFixed(1)}h` : '—';
      return {
        key: `${it.task_id}:${it.subtask_id || ''}`,
        dot,
        title,
        subtitle: `${it.project_name} • USED: ${usedH.toFixed(1)}h • EST: ${estLabel}`,
        badge,
        badgeClass,
      };
    });
  }, [myUtilization]);

  return (
    <div className="p-8 space-y-8 max-w-[1600px] mx-auto animate-in fade-in duration-500 pb-20 bg-[#F8FAFC]">
      
      {/* TOP ROW: TIMER & PERFORMANCE */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Project Deliverable Tracker */}
        <div className="lg:col-span-8 relative">
           <TimerCard
             title="Project Deliverable Tracker"
             projectOptions={timerProjectOptions}
             taskOptions={taskOptionsByProjectId}
             className="min-h-[480px]"
             status={timerCardStatus}
             onStart={handleStartTimer}
             onPause={handlePauseTimer}
             onResume={handleResumeTimer}
             onStop={handleStopTimer}
             headerActions={attendanceMarked ? (
               <Button
                 onClick={handleEndWorkday}
                 isLoading={punchOutBusy}
                 disabled={alreadyPunchedOut || punchOutBusy}
                 className={cn(
                   "h-8 px-4 font-black text-[10px] uppercase tracking-widest rounded-full transition-all",
                   alreadyPunchedOut
                     ? "border border-slate-200 bg-slate-50 text-slate-400 cursor-not-allowed"
                     : "border border-red-100 bg-red-50 text-red-600 hover:bg-red-100 hover:text-red-700",
                 )}
               >
                 {alreadyPunchedOut ? 'Punched Out' : 'Punch Out'}
               </Button>
             ) : undefined}
           />
        </div>

        {/* Performance Index Card */}
        <Card className="lg:col-span-4 p-8 bg-white border-slate-100 shadow-sm flex flex-col justify-between overflow-hidden">
           <div>
              <div className="flex justify-between items-start mb-1">
                 <h3 className="text-xl font-black text-[#0F172A] tracking-tight leading-tight">Performance<br/>Index</h3>
                 <span className="text-4xl font-black text-[#2563EB]">{currentPerformance}%</span>
              </div>
              <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Efficiency Index (Hours Based)</p>
           </div>
           
           <div className="h-48 mt-8 -mx-8 relative">
              <ResponsiveContainer width="100%" height="100%" minHeight={192}>
                 <AreaChart data={chartData}>
                    <defs>
                       <linearGradient id="colorValue" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#2563EB" stopOpacity={0.1}/>
                          <stop offset="95%" stopColor="#2563EB" stopOpacity={0}/>
                       </linearGradient>
                    </defs>
                    <Area type="monotone" dataKey="value" stroke="#2563EB" strokeWidth={3} fillOpacity={1} fill="url(#colorValue)" />
                    <XAxis dataKey="name" hide />
                    <YAxis hide domain={[0, 100]} />
                 </AreaChart>
              </ResponsiveContainer>
              <div className="flex justify-around px-8 mt-2">
                 {chartData.slice(-3).map((d: any, i: number) => (
                   <span key={i} className="text-[10px] font-black text-slate-400">{d.name}</span>
                 ))}
              </div>
           </div>

           <div className="mt-8 p-4 bg-slate-50 rounded-2xl flex items-center justify-between group cursor-pointer hover:bg-blue-50 transition-colors">
              <div className="flex items-center gap-3">
                 <div className="p-2 bg-white rounded-xl shadow-sm">
                    <Clock size={16} className="text-[#2563EB]" />
                 </div>
                 <div>
                    <p className="text-[10px] font-black text-[#2563EB] uppercase tracking-widest">{totalHoursLogged}h Logged This Week</p>
                 </div>
              </div>
              <button 
                onClick={() => onNavigate('timesheet')}
                className="text-[10px] font-black text-slate-400 uppercase tracking-widest group-hover:text-[#2563EB]"
              >
                My Timesheet
              </button>
           </div>
        </Card>
      </div>

      {/* MY WEEK: shift outlook */}
      <MyWeekStrip onNavigate={onNavigate} />

      {/* BOTTOM ROW: ASSIGNMENTS & LEAVE */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
         {/* Operational Assignments */}
         <Card className="p-0 bg-white border-slate-100 shadow-sm overflow-hidden">
            <div className="p-8 flex justify-between items-center border-b border-slate-50">
               <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-full bg-blue-50 flex items-center justify-center text-[#2563EB] border border-blue-100">
                     <ClipboardCheck size={16} />
                  </div>
                  <h3 className="text-lg font-black text-[#0F172A] uppercase tracking-tight">Operational Assignments</h3>
               </div>
               <button className="text-[10px] font-black text-[#2563EB] uppercase tracking-[0.2em] hover:opacity-70 transition-opacity">Task Management Center</button>
            </div>
            
            <div className="divide-y divide-slate-50">
              {assignmentRows.length > 0 ? (
                assignmentRows.map((row: any) => (
                   <div 
                  key={row.key} 
                     onClick={() => onNavigate('tasks')}
                     className="p-8 flex items-center justify-between group hover:bg-slate-50/50 transition-colors cursor-pointer"
                   >
                      <div className="flex items-center gap-6">
                     <div className={cn("w-3 h-3 rounded-full", row.dot)} />
                         <div>
                       <p className="text-md font-black text-[#0F172A] tracking-tight mb-1">{row.title}</p>
                       <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest">{row.subtitle}</p>
                         </div>
                      </div>
                   <Badge className={cn("font-black text-[9px] uppercase tracking-widest px-3 py-1 rounded-md border-none", row.badgeClass)}>
                     {row.badge}
                      </Badge>
                   </div>
                 ))
              ) : tasks.length > 0 ? (
                tasks.map((task: any, i: number) => (
                 <div 
                  key={i} 
                  onClick={() => onNavigate('tasks')}
                  className="p-8 flex items-center justify-between group hover:bg-slate-50/50 transition-colors cursor-pointer"
                 >
                   <div className="flex items-center gap-6">
                     <div className={cn("w-3 h-3 rounded-full", task.priority.toLowerCase() === 'high' ? 'bg-red-500' : 'bg-blue-500')} />
                     <div>
                       <p className="text-md font-black text-[#0F172A] tracking-tight mb-1">{task.title}</p>
                       <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest">{task.project_name} • DEADLINE: {task.due_date ? new Date(task.due_date).toLocaleDateString() : 'NONE'}</p>
                     </div>
                   </div>
                   <Badge className={cn("font-black text-[9px] uppercase tracking-widest px-3 py-1 rounded-md border-none", task.priority.toLowerCase() === 'high' ? 'text-amber-500 bg-amber-50' : 'text-blue-500 bg-blue-50')}>
                     {task.priority}
                   </Badge>
                 </div>
                ))
              ) : (
                 <div className="p-12 text-center text-slate-300 font-bold uppercase text-[10px] italic">No active deliverables detected</div>
               )}
            </div>
            <div className="h-12" /> {/* Spacer */}
         </Card>

         {/* Time-Off & Leave Status */}
         <Card className="p-0 bg-white border-slate-100 shadow-sm overflow-hidden flex flex-col">
            <div className="p-8 flex justify-between items-center border-b border-slate-50">
               <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-full bg-blue-50 flex items-center justify-center text-[#2563EB] border border-blue-100">
                     <Umbrella size={16} />
                  </div>
                  <h3 className="text-lg font-black text-[#0F172A] uppercase tracking-tight">Time-Off & Leave Status</h3>
               </div>
               <button 
                onClick={() => onNavigate('leave')}
                className="text-[10px] font-black text-[#2563EB] uppercase tracking-[0.2em] hover:opacity-70 transition-opacity"
               >
                Request Leave
               </button>
            </div>

            <div className="p-8 grid grid-cols-2 gap-6">
               <div 
                onClick={() => onNavigate('leave')}
                className="p-8 bg-[#EFF6FF] rounded-3xl border border-blue-100 flex flex-col justify-center cursor-pointer hover:bg-blue-100/50 transition-colors"
               >
                  <p className="text-[10px] font-black text-[#2563EB] uppercase tracking-widest mb-4">
                    {leaveBalances[0]?.leave_type_name || 'Earned Leave'}
                  </p>
                  <div className="flex items-baseline gap-2">
                     <span className="text-5xl font-black text-[#0F172A]">
                       {leaveBalances[0]?.remaining_balance || 0}
                     </span>
                     <span className="text-sm font-black text-slate-400">Days Left</span>
                  </div>
               </div>
               <div className="p-8 bg-slate-50 rounded-3xl border border-slate-100 flex flex-col justify-center overflow-hidden">
                  <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-4">Upcoming Holiday</p>
                  <p className="text-xl font-black text-[#0F172A] leading-tight mb-1 truncate">
                    {holidays[0]?.name || 'No Upcoming Holiday'}
                  </p>
                  {holidays[0] && (
                    <p className="text-[10px] font-black text-slate-400 uppercase">
                      {new Date(holidays[0].date).toLocaleDateString(undefined, { month: 'short', day: 'numeric', weekday: 'long' })}
                    </p>
                  )}
               </div>
            </div>

            <div className="px-8 pb-8 space-y-6">
               <h4 className="text-[10px] font-black text-slate-400 uppercase tracking-[0.2em]">Short Break Tracker</h4>
               <div className="space-y-3">
                  {[
                    { label: 'Lunch Session', value: '45/60M', percent: 75, icon: <Coffee size={14}/>, color: 'bg-orange-500' },
                    { label: 'Tea Break', value: '12/15M', percent: 80, icon: <Clock size={14}/>, color: 'bg-blue-500' },
                  ].map((breakItem, i) => (
                    <div 
                      key={i} 
                      onClick={() => handleStartBreak(breakItem.label)}
                      className="p-4 bg-white border border-slate-100 rounded-2xl flex items-center justify-between group hover:border-blue-100 transition-all cursor-pointer hover:bg-slate-50/50"
                    >
                       <div className="flex items-center gap-4">
                          <div className={cn("w-10 h-10 rounded-xl flex items-center justify-center text-white shadow-sm", breakItem.color)}>
                             {breakItem.icon}
                          </div>
                          <p className="text-sm font-black text-[#0F172A] uppercase tracking-tight">{breakItem.label}</p>
                       </div>
                       <div className="text-right">
                          <p className="text-[10px] font-black text-slate-400 tracking-widest">{breakItem.value}</p>
                       </div>
                    </div>
                  ))}
               </div>
            </div>
         </Card>
      </div>

      {(celebrations.birthdays.length > 0 || celebrations.anniversaries.length > 0) && (
        <Card className="p-0 bg-white border-slate-100 shadow-sm overflow-hidden">
          <div className="p-8 flex justify-between items-center border-b border-slate-50">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-full bg-pink-50 flex items-center justify-center text-pink-500 border border-pink-100">
                <Cake size={16} />
              </div>
              <h3 className="text-lg font-black text-[#0F172A] uppercase tracking-tight">Upcoming Celebrations</h3>
            </div>
            <span className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Next 30 days</span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 divide-y md:divide-y-0 md:divide-x divide-slate-100">
            <div className="p-6">
              <div className="flex items-center gap-2 mb-4">
                <Cake size={14} className="text-pink-500" />
                <p className="text-[10px] font-black text-slate-500 uppercase tracking-widest">Birthdays</p>
              </div>
              {celebrations.birthdays.length === 0 ? (
                <p className="text-xs font-medium text-slate-400 italic">No birthdays in the window.</p>
              ) : (
                <ul className="space-y-3">
                  {celebrations.birthdays.slice(0, 5).map((b: any) => (
                    <li key={`b-${b.user_id}`} className="flex items-center justify-between gap-3">
                      <div className="min-w-0">
                        <p className="text-sm font-black text-[#0F172A] truncate">{b.full_name}</p>
                        <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest truncate">{b.designation || 'Employee'}</p>
                      </div>
                      <div className="text-right shrink-0">
                        <p className="text-[11px] font-black text-pink-600">
                          {new Date(b.date).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })}
                        </p>
                        <p className="text-[9px] font-bold text-slate-400 uppercase tracking-widest">
                          {b.days_away === 0 ? 'today' : `in ${b.days_away}d`}
                        </p>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <div className="p-6">
              <div className="flex items-center gap-2 mb-4">
                <Award size={14} className="text-blue-500" />
                <p className="text-[10px] font-black text-slate-500 uppercase tracking-widest">Work anniversaries</p>
              </div>
              {celebrations.anniversaries.length === 0 ? (
                <p className="text-xs font-medium text-slate-400 italic">No anniversaries in the window.</p>
              ) : (
                <ul className="space-y-3">
                  {celebrations.anniversaries.slice(0, 5).map((a: any) => (
                    <li key={`a-${a.user_id}`} className="flex items-center justify-between gap-3">
                      <div className="min-w-0">
                        <p className="text-sm font-black text-[#0F172A] truncate">{a.full_name}</p>
                        <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest truncate">
                          {a.years} year{a.years === 1 ? '' : 's'}{a.designation ? ` · ${a.designation}` : ''}
                        </p>
                      </div>
                      <div className="text-right shrink-0">
                        <p className="text-[11px] font-black text-blue-600">
                          {new Date(a.date).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })}
                        </p>
                        <p className="text-[9px] font-bold text-slate-400 uppercase tracking-widest">
                          {a.days_away === 0 ? 'today' : `in ${a.days_away}d`}
                        </p>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </Card>
      )}

      {punchOutPrompt === 'timer-running' && (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-[80] flex items-center justify-center p-4">
          <Card className="w-full max-w-md p-6 space-y-4 animate-in zoom-in-95 duration-200">
            <div className="flex items-start gap-3">
              <div className="w-10 h-10 rounded-full bg-amber-50 text-amber-600 flex items-center justify-center flex-shrink-0">
                <AlertCircle className="w-5 h-5" />
              </div>
              <div className="flex-1">
                <h3 className="text-lg font-bold text-[#0F172A]">
                  A task timer is still running
                </h3>
                <p className="text-sm text-slate-600 mt-1">
                  Stop your active task timer before punching out. We can do
                  both for you in one step.
                </p>
              </div>
            </div>
            <div className="flex justify-end gap-2 pt-1">
              <Button
                variant="outline"
                onClick={() => setPunchOutPrompt('idle')}
                disabled={punchOutBusy}
              >
                Cancel
              </Button>
              <Button
                className="bg-red-600 hover:bg-red-700 text-white"
                onClick={handleStopAndPunchOut}
                isLoading={punchOutBusy}
              >
                Stop Timer & Punch Out
              </Button>
            </div>
          </Card>
        </div>
      )}

    </div>
  );
};
