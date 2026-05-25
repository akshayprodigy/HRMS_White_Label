import React, { useState, useEffect, useRef } from 'react';
import { 
  Users, 
  Clock, 
  Calendar, 
  CheckCircle2, 
  AlertCircle, 
  TrendingUp, 
  Briefcase,
  Plus,
  ArrowRight,
  FileBadge,
  LayoutDashboard,
  ShieldCheck,
  Zap,
  Timer,
  Play,
  CircleCheck,
  Megaphone,
  Pause,
  Square
} from 'lucide-react';
import { Card, Button, Badge, cn } from './ui-elements';
import { 
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, LineChart, Line, AreaChart, Area 
} from 'recharts';
import { toast } from 'sonner@2.0.3';
import { hrApi } from '../api/hr';
import { timesheetApi } from '../api/timesheet';

interface HRDashboardProps {
    onNavigate?: (tab: string) => void;
}

interface DashboardStats {
  total_employees: number;
  active_requisitions: number;
  pending_actions: number;
  avg_working_hours: string;
  attendance_rate: number;
  requisition_trend: string;
  onboarding_count: number;
  attendance_trends: any[];
  leave_trends: any[];
}

export const HRDashboard = ({ onNavigate = () => {} }: HRDashboardProps) => {
  const [statsData, setStatsData] = useState<DashboardStats | null>(null);
  const [timerStatus, setTimerStatus] = useState<any>(null);
  const [seconds, setSeconds] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const timerIntervalRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    fetchDashboardData();
    return () => {
      if (timerIntervalRef.current) clearInterval(timerIntervalRef.current);
    };
  }, []);

  const fetchDashboardData = async () => {
    try {
      setIsLoading(true);
         const [statsRes, timerRes] = await Promise.allSettled([
            hrApi.getDashboardStats(),
            timesheetApi.getTimerStatus(),
         ]);

         if (statsRes.status === 'fulfilled') {
            setStatsData(statsRes.value.data);
         } else {
            console.error('Failed to fetch HR dashboard stats', statsRes.reason);
            toast.error('Cloud Sync Failed', {
               description: 'Unable to retrieve real-time operational metrics.',
            });
         }

         if (timerRes.status === 'fulfilled') {
            const timerData = timerRes.value.data;
            if (timerData.auto_stopped) {
               toast.warning('Timer Auto-Stopped', {
                  description: timerData.auto_stop_reason || 'Daily 9-hour limit reached. Your time has been logged.',
                  duration: 8000,
               });
               setTimerStatus({ is_active: false });
               setSeconds(0);
               stopLocalTimer();
            } else {
               setTimerStatus(timerData);
               if (
                  timerData.is_active &&
                  timerData.session?.status === 'running'
               ) {
                  setSeconds(timerData.current_duration_seconds);
                  startLocalTimer();
               } else if (timerData.is_active) {
                  setSeconds(timerData.current_duration_seconds);
               }
            }
         } else {
            // Timer status is not critical for HR intelligence charts.
            console.error('Failed to fetch timer status', timerRes.reason);
            setTimerStatus({ is_active: false });
         }
    } catch (error) {
      console.error("Failed to fetch dashboard data", error);
      toast.error("Cloud Sync Failed", {
        description: "Unable to retrieve real-time operational metrics."
      });
    } finally {
      setIsLoading(false);
    }
  };

  const startLocalTimer = () => {
    if (timerIntervalRef.current) clearInterval(timerIntervalRef.current);
    timerIntervalRef.current = setInterval(() => {
      setSeconds(prev => prev + 1);
    }, 1000);
  };

  const stopLocalTimer = () => {
    if (timerIntervalRef.current) {
      clearInterval(timerIntervalRef.current);
      timerIntervalRef.current = null;
    }
  };

  const handleStartTimer = async () => {
    try {
      // Use project 3 (HR System Migration) as default for dashboard quick-start
             const res = await timesheetApi.startTimer(
                3,
                undefined,
                undefined,
                "HR Dashboard Quick Start",
             );
      setTimerStatus({
        is_active: true,
        session: res.data,
        current_duration_seconds: 0
      });
      setSeconds(0);
      startLocalTimer();
      toast.success("Timer Started", { description: "Session: HR System Migration" });
    } catch (error) {
      toast.error("Action Failed", { description: "System could not initialize timer session." });
    }
  };

  const handlePauseResume = async () => {
    try {
      if (timerStatus.session.status === 'running') {
        await timesheetApi.pauseTimer();
        stopLocalTimer();
        setTimerStatus({
          ...timerStatus,
          session: { ...timerStatus.session, status: 'paused' }
        });
        toast.info("Timer Paused");
      } else {
        await timesheetApi.resumeTimer();
        startLocalTimer();
        setTimerStatus({
          ...timerStatus,
          session: { ...timerStatus.session, status: 'running' }
        });
        toast.success("Timer Resumed");
      }
    } catch (error) {
      toast.error("Action Failed");
    }
  };

  const handleStopTimer = async () => {
    try {
      await timesheetApi.stopTimer();
      stopLocalTimer();
      setTimerStatus({ is_active: false });
      setSeconds(0);
      toast.success("Timer Stopped", { description: "Work session recorded successfully." });
    } catch (error) {
      toast.error("Action Failed");
    }
  };

  const formatTime = (totalSeconds: number) => {
    const h = Math.floor(totalSeconds / 3600);
    const m = Math.floor((totalSeconds % 3600) / 60);
    const s = totalSeconds % 60;
    return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  };

  const stats = [
    { 
      label: 'Total Enterprise Assets', 
      value: statsData?.total_employees.toString() || '...', 
      trend: '+12 this month', 
      icon: Users, 
      color: 'text-blue-600', 
      bg: 'bg-blue-50', 
      tab: 'hr-directory' 
    },
    { 
      label: 'Avg. Working Hours', 
      value: statsData?.avg_working_hours || '...', 
      trend: `Productivity: ${statsData?.attendance_rate || 0}%`, 
      icon: Clock, 
      color: 'text-purple-600', 
      bg: 'bg-purple-50', 
      tab: 'hr-reports' 
    },
    { 
      label: 'Active Requisitions', 
      value: statsData?.active_requisitions.toString() || '...', 
      trend: statsData?.requisition_trend || 'No trend', 
      icon: Briefcase, 
      color: 'text-amber-600', 
      bg: 'bg-amber-50', 
      tab: 'hr-recruitment' 
    },
    { 
      label: 'Pending HR Actions', 
      value: statsData?.pending_actions.toString().padStart(2, '0') || '...', 
      trend: `${statsData?.onboarding_count || 0} Onboarding`, 
      icon: AlertCircle, 
      color: 'text-red-600', 
      bg: 'bg-red-50', 
      tab: 'dashboard' 
    },
  ];

  const handleQuickAction = (action: string) => {
      toast.success(`${action} initialized`, {
          description: "System preparing necessary enterprise modules."
      });
  };

  return (
    <div className="p-8 space-y-8 max-w-[1600px] mx-auto animate-in fade-in duration-500 pb-20">
      {/* Header with Persistent Core Widgets */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        <Card className="lg:col-span-3 p-8 border-slate-200 bg-white shadow-xl shadow-slate-200/50 flex flex-col md:flex-row items-center justify-between gap-8 relative overflow-hidden">
           <div className="relative z-10">
              <div className="flex items-center gap-3 mb-2">
                 <Badge variant="success" className="font-black text-[9px] uppercase tracking-widest px-3 py-1">
                    Attendance Verified ({new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })})
                 </Badge>
                 <span className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Logged: Office Mode</span>
              </div>
              <h2 className="text-3xl font-black text-[#0F172A] tracking-tighter uppercase">HR Operational Command</h2>
              <p className="text-slate-500 font-bold uppercase tracking-widest text-[10px] mt-2">Enterprise Resource Oversight & Strategic Asset Planning</p>
           </div>
           
           <div className="relative z-10 flex flex-col items-center gap-2 bg-slate-50 p-5 rounded-3xl border border-slate-100 min-w-[220px]">
              <div className="flex items-center gap-2 text-slate-400 uppercase font-black text-[9px] tracking-[0.2em] mb-1">
                 <div className={cn("w-1.5 h-1.5 rounded-full animate-pulse", timerStatus?.session?.status === 'running' ? "bg-red-500" : "bg-slate-400")} /> 
                 Live Task Timer
              </div>
              <div className="text-3xl font-black text-[#0F172A] font-mono tracking-tighter">{formatTime(seconds)}</div>
              <div className="flex gap-2 w-full mt-3">
                 {!timerStatus?.is_active ? (
                    <Button 
                      className="w-full h-9 bg-blue-600 font-black uppercase text-[9px] tracking-widest"
                      onClick={handleStartTimer}
                    >
                      <Play size={12} className="mr-2" /> Start Timer
                    </Button>
                 ) : (
                    <>
                      <Button variant="outline" className="flex-1 h-9 border-slate-200 text-[9px] font-black uppercase tracking-widest" onClick={handlePauseResume}>
                          {timerStatus.session.status === 'running' ? <><Pause size={12} className="mr-2"/> Pause</> : <><Play size={12} className="mr-2"/> Resume</>}
                      </Button>
                      <Button 
                        className="flex-1 h-9 bg-slate-900 text-white font-black uppercase text-[9px] tracking-widest"
                        onClick={handleStopTimer}
                      >
                        <Square size={12} className="mr-2" /> Stop
                      </Button>
                    </>
                 )}
              </div>
           </div>
           <Zap size={180} className="absolute -left-10 -bottom-10 opacity-[0.03] text-blue-600 rotate-12" />
        </Card>

        <Card className="p-8 bg-slate-900 border-none shadow-2xl flex flex-col justify-between overflow-hidden relative">
           <div className="relative z-10">
              <h3 className="text-white font-black uppercase tracking-widest text-[9px] opacity-60 mb-2 flex items-center gap-2"><Megaphone size={12}/> Global Announcement</h3>
              <p className="text-white text-lg font-black tracking-tight leading-snug">FY 2026-27 Appraisal Policy Update is now live.</p>
           </div>
           <Button variant="outline" className="relative z-10 mt-6 w-full h-10 border-white/10 text-white hover:bg-white/10 font-black uppercase text-[9px] tracking-widest">Acknowledge</Button>
           <ShieldCheck size={140} className="absolute -right-8 -top-8 opacity-10 transform rotate-12" />
        </Card>
      </div>

      {/* Stats Summary Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        {stats.map((stat, i) => (
          <Card key={i} className="p-6 border-slate-200 shadow-sm bg-white group hover:border-blue-600 transition-all cursor-pointer" onClick={() => onNavigate(stat.tab)}>
             <div className="flex items-start justify-between">
                <div>
                   <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1">{stat.label}</p>
                   <h4 className="text-3xl font-black text-[#0F172A] tracking-tighter">{stat.value}</h4>
                </div>
                <div className={cn("p-2.5 rounded-2xl", stat.bg, stat.color)}>
                   <stat.icon size={20} />
                </div>
             </div>
             <div className="mt-4 flex items-center gap-2">
                <Badge variant="ghost" className="text-[9px] font-black uppercase text-blue-600 bg-blue-50 px-2 py-0.5">
                   <TrendingUp size={10} className="mr-1" /> {stat.trend}
                </Badge>
             </div>
          </Card>
        ))}
      </div>

      {/* Simplified Analytics Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
         {/* Attendance Precision Chart */}
         <Card className="p-8 border-slate-200 shadow-sm space-y-8 bg-white">
            <div className="flex items-center justify-between">
               <h4 className="text-xl font-black text-[#0F172A] tracking-tight uppercase flex items-center gap-2">
                  <CircleCheck size={18} className="text-blue-600"/> Attendance Trends (Weekly)
               </h4>
               <Badge variant="info" className="text-[9px] font-black uppercase">Live Delta</Badge>
            </div>
            <div className="h-[280px] w-full min-h-[280px]">
               <ResponsiveContainer width="99%" height="100%">
                  <AreaChart data={statsData?.attendance_trends || []}>
                     <defs>
                        <linearGradient id="colorOnTime" x1="0" y1="0" x2="0" y2="1">
                           <stop offset="5%" stopColor="#2563EB" stopOpacity={0.1}/>
                           <stop offset="95%" stopColor="#2563EB" stopOpacity={0}/>
                        </linearGradient>
                     </defs>
                     <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#F1F5F9" />
                     <XAxis dataKey="day" axisLine={false} tickLine={false} tick={{ fontSize: 10, fontWeight: 900, fill: '#94A3B8' }} />
                     <YAxis axisLine={false} tickLine={false} tick={{ fontSize: 10, fontWeight: 900, fill: '#94A3B8' }} />
                     <Tooltip 
                        contentStyle={{ borderRadius: '16px', border: 'none', boxShadow: '0 20px 25px -5px rgb(0 0 0 / 0.1)', fontWeight: 900 }}
                     />
                     <Area type="monotone" dataKey="onTime" stroke="#2563EB" strokeWidth={3} fillOpacity={1} fill="url(#colorOnTime)" />
                  </AreaChart>
               </ResponsiveContainer>
            </div>
         </Card>

         {/* Leave Inflow Chart */}
         <Card className="p-8 border-slate-200 shadow-sm space-y-8 bg-white">
            <div className="flex items-center justify-between">
               <h4 className="text-xl font-black text-[#0F172A] tracking-tight uppercase flex items-center gap-2">
                  <Calendar size={18} className="text-purple-600"/> Leave Requisitions (Monthly)
               </h4>
               <Badge variant="warning" className="text-[9px] font-black uppercase">Seasonal View</Badge>
            </div>
            <div className="h-[280px] w-full min-h-[280px]">
               <ResponsiveContainer width="99%" height="100%">
                  <BarChart data={statsData?.leave_trends || []}>
                     <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#F1F5F9" />
                     <XAxis dataKey="month" axisLine={false} tickLine={false} tick={{ fontSize: 10, fontWeight: 900, fill: '#94A3B8' }} />
                     <YAxis axisLine={false} tickLine={false} tick={{ fontSize: 10, fontWeight: 900, fill: '#94A3B8' }} />
                     <Tooltip 
                        contentStyle={{ borderRadius: '16px', border: 'none', boxShadow: '0 20px 25px -5px rgb(0 0 0 / 0.1)', fontWeight: 900 }}
                     />
                     <Bar dataKey="count" fill="#8B5CF6" radius={[6, 6, 0, 0]} barSize={35} />
                  </BarChart>
               </ResponsiveContainer>
            </div>
         </Card>
      </div>

      {/* Actions Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
         <div className="lg:col-span-2 space-y-6">
            <Card className="p-8 border-slate-200 shadow-sm bg-white">
               <div className="flex items-center justify-between mb-8">
                  <h4 className="text-xl font-black text-[#0F172A] tracking-tight uppercase">Strategic Activity Queue</h4>
                  <Badge variant="error" className="text-[9px] font-black uppercase px-3 py-1">08 Flagged Events</Badge>
               </div>
               <div className="space-y-4">
                  {(statsData?.activities || []).map((item, i) => (
                     <div key={i} className="flex items-center justify-between p-4 bg-slate-50 border border-slate-100 rounded-2xl group hover:border-blue-600 hover:bg-white transition-all shadow-sm">
                        <div className="flex items-center gap-4">
                           <div className="w-10 h-10 rounded-xl bg-white border border-slate-200 flex items-center justify-center font-black text-xs text-blue-600 group-hover:bg-blue-600 group-hover:text-white transition-all">
                              {item.name.charAt(0)}
                           </div>
                           <div>
                              <p className="text-sm font-black text-[#0F172A]">{item.action}</p>
                              <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">{item.name} • {item.identifier} • {item.type}</p>
                           </div>
                        </div>
                        <Button size="sm" className="h-9 px-6 bg-slate-900 font-black uppercase text-[9px] tracking-widest shadow-lg shadow-slate-900/10">Execute</Button>
                     </div>
                  ))}
               </div>
               <Button variant="ghost" className="w-full mt-6 font-black text-[10px] uppercase tracking-widest text-slate-400 hover:text-blue-600">View Comprehensive Action Log <ArrowRight size={14} className="ml-2" /></Button>
            </Card>
         </div>

         <div className="space-y-6">
            <Card className="p-8 border-slate-200 shadow-sm bg-white">
               <h4 className="text-lg font-black text-[#0F172A] tracking-tight mb-6 uppercase flex items-center gap-2"><Timer size={18} className="text-blue-600"/> Today's Log Summary</h4>
               <div className="space-y-6">
                  <div className="p-5 rounded-2xl bg-blue-50 border border-blue-100">
                     <p className="text-[10px] font-black text-blue-600 uppercase tracking-widest mb-1">Total Productivity</p>
                     <p className="text-2xl font-black text-[#0F172A]">07h 42m</p>
                  </div>
                  <div className="space-y-4">
                     <div className="flex justify-between items-center text-[10px] font-black uppercase">
                        <span className="text-slate-400">HR Tasks</span>
                        <span className="text-[#0F172A]">04h 15m</span>
                     </div>
                     <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden">
                        <div className="h-full bg-blue-600 w-3/4" />
                     </div>
                     <div className="flex justify-between items-center text-[10px] font-black uppercase pt-2">
                        <span className="text-slate-400">Recruitment</span>
                        <span className="text-[#0F172A]">02h 30m</span>
                     </div>
                     <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden">
                        <div className="h-full bg-purple-600 w-1/3" />
                     </div>
                  </div>
               </div>
            </Card>
            
            <Card className="p-8 border-slate-200 shadow-sm bg-slate-50 border-dashed border-2 flex flex-col items-center justify-center text-center">
               <div className="w-12 h-12 bg-white rounded-2xl flex items-center justify-center shadow-sm mb-4 text-blue-600">
                  <Plus size={24} />
               </div>
               <h5 className="text-[10px] font-black text-[#0F172A] uppercase tracking-widest">Post Custom Announcement</h5>
               <p className="text-[9px] font-bold text-slate-400 uppercase tracking-widest mt-1">Broadcast to all Enterprise Assets</p>
            </Card>
         </div>
      </div>
    </div>
  );
};
