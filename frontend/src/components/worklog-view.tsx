import React, { useState, useEffect } from 'react';
import {
  Search,
  Clock,
  AlertCircle,
  MoreVertical,
  Plus,
} from 'lucide-react';
import { Card, Button, Badge, TimerCard, cn } from './ui-elements';
import { toast } from 'sonner';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from './ui/dialog';
import { Input } from './ui/input';
import { Textarea } from './ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';
import { useTimer } from '../contexts/timer-context';

interface WorklogEntry {
  id: string;
  date: string;
  project: string;
  task: string;
  duration: string;
  status: string;
  description: string;
  remarks?: string;
  source?: string;
}

const formatDuration = (seconds: number): string => {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return `${h}h ${m.toString().padStart(2, '0')}m`;
};

export const WorklogView = () => {
  const { status: unifiedTimerStatus, start, pause, resume, stop } = useTimer();

  const [searchQuery, setSearchQuery] = useState('');
  const [filterStatus, setFilterStatus] = useState<'All' | 'Approved' | 'Pending' | 'Timer' | 'Manual'>('All');
  const [isAddingLog, setIsAddingLog] = useState(false);
  const [loadingLogs, setLoadingLogs] = useState(true);

  const [manualProject, setManualProject] = useState('');
  const [manualTask, setManualTask] = useState('');
  const [manualDate, setManualDate] = useState(new Date().toISOString().slice(0, 10));
  const [manualStartTime, setManualStartTime] = useState('09:00');
  const [manualEndTime, setManualEndTime] = useState('13:00');
  const [manualReason, setManualReason] = useState('');
  const [submittingManual, setSubmittingManual] = useState(false);

  const [logs, setLogs] = useState<WorklogEntry[]>([]);

  const [timerProjects, setTimerProjects] = useState<Array<{ id: number; name: string }>>([]);
  const [timerTaskOptions, setTimerTaskOptions] = useState<
    Record<string, Array<{ id: number | string; name: string }>>
  >({});

  const fetchWorklogs = async () => {
    try {
      const res = await client.get(ENDPOINTS.TIMESHEET.MY);
      const data = res.data;
      const entries: WorklogEntry[] = [];

      for (const day of data.daily_data || []) {
        for (const entry of day.entries || []) {
          const dateStr = new Date(entry.start_at).toLocaleDateString(undefined, {
            month: 'short', day: 'numeric', year: 'numeric',
          });

          // Resolve task name from timerTaskOptions if possible
          let taskLabel = 'General Activity';
          if (entry.subtask_id && entry.task_id) {
            const key = `s:${entry.task_id}:${entry.subtask_id}`;
            const opts = timerTaskOptions[String(entry.project_id)] || [];
            const match = opts.find(o => o.id.toString() === key);
            taskLabel = match?.name || `Subtask #${entry.subtask_id}`;
          } else if (entry.task_id) {
            const key = `t:${entry.task_id}`;
            const opts = timerTaskOptions[String(entry.project_id)] || [];
            const match = opts.find(o => o.id.toString() === key);
            taskLabel = match?.name || `Task #${entry.task_id}`;
          }

          entries.push({
            id: `TE-${entry.id}`,
            date: dateStr,
            project: entry.project_name || `Project #${entry.project_id}`,
            task: taskLabel,
            duration: formatDuration(entry.duration_seconds || 0),
            status: entry.source === 'timer' ? 'Timer' : 'Manual',
            description: entry.manual_reason || `Logged via ${entry.source || 'timer'}`,
            source: entry.source,
          });
        }
      }

      setLogs(entries);
    } catch {
      // Keep existing logs if fetch fails
    } finally {
      setLoadingLogs(false);
    }
  };

  useEffect(() => {
    const fetchAssignedTasks = async () => {
      try {
        const [meRes, tasksRes] = await Promise.allSettled([
          client.get(ENDPOINTS.AUTH.ME),
          client.get(ENDPOINTS.TASKS.MY_TASKS),
        ]);
        const meId =
          meRes.status === 'fulfilled' && typeof meRes.value.data?.id === 'number'
            ? meRes.value.data.id
            : null;

        const projects =
          tasksRes.status === 'fulfilled' ? ((tasksRes.value.data || []) as any[]) : [];

        if (projects.length > 0) {
          setTimerProjects(projects.map(p => ({ id: p.id, name: p.name })));

          const byProject: Record<string, Array<{ id: number; name: string }>> = {};
          for (const p of projects) {
            const pid = p.id?.toString();
            if (!pid) continue;

            const opts: Array<{ id: number | string; name: string }> = [];
            for (const t of p.tasks || []) {
              if (!t?.id) continue;
              if (!meId || t.assignee_id === meId) {
                opts.push({ id: `t:${t.id}`, name: t.title });
              }
              if (meId && Array.isArray(t.subtasks)) {
                for (const st of t.subtasks) {
                  if (!st?.id) continue;
                  if (st.assignee_id !== meId) continue;
                  opts.push({ id: `s:${t.id}:${st.id}`, name: `${t.title} / ${st.title}` });
                }
              }
            }
            byProject[pid] = opts;
          }
          setTimerTaskOptions(byProject);
          return;
        }

        // No assigned tasks: still allow selecting a project to start a general session.
        const projRes = await client.get(ENDPOINTS.PROJECTS.LIST);
        const allProjects = (projRes.data || []) as any[];
        setTimerProjects(allProjects.map((p) => ({ id: p.id, name: p.name })));
        setTimerTaskOptions({});
      } catch (e) {
        // Keep UI functional even if task list fails.
        try {
          const projRes = await client.get(ENDPOINTS.PROJECTS.LIST);
          const allProjects = (projRes.data || []) as any[];
          setTimerProjects(allProjects.map((p) => ({ id: p.id, name: p.name })));
          setTimerTaskOptions({});
        } catch {
          // Swallow; timer will still render but without selectors.
        }
      }
    };

    fetchAssignedTasks();
    fetchWorklogs();
  }, []);

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
            // Match the exact work item: subtask selection or main-task selection
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
      toast.success('Timer Started');
    } catch (error: any) {
      toast.error('Failed to start timer', {
        description: error.response?.data?.error?.message || 'Check active timers / attendance gate',
      });
    }
  };

  const handlePauseTimer = async () => {
    try {
      await pause();
      toast.info('Timer Paused');
    } catch {
      toast.error('Failed to pause timer');
    }
  };

  const handleResumeTimer = async () => {
    try {
      await resume();
      toast.info('Timer Resumed');
    } catch {
      toast.error('Failed to resume timer');
    }
  };

  const handleStopTimer = async (durationSeconds: number, projectId: string, taskId: string) => {
    try {
      await stop();
      toast.success('Timer stopped — entry saved');
      // Refresh worklogs to show the newly created time entry
      fetchWorklogs();
    } catch {
      toast.error('Failed to stop timer');
    }
  };

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

  const handleManualSubmit = async () => {
    if (!manualProject) { toast.error('Select a project'); return; }
    if (!manualReason.trim()) { toast.error('Provide a reason for manual entry'); return; }

    const startAt = new Date(`${manualDate}T${manualStartTime}:00`);
    const endAt = new Date(`${manualDate}T${manualEndTime}:00`);
    if (endAt <= startAt) { toast.error('End time must be after start time'); return; }

    const { taskId, subtaskId } = parseWorkItemSelection(manualTask);

    setSubmittingManual(true);
    try {
      await client.post(ENDPOINTS.TIMESHEET.MANUAL, {
        project_id: parseInt(manualProject),
        task_id: taskId ?? null,
        subtask_id: subtaskId ?? null,
        start_at: startAt.toISOString(),
        end_at: endAt.toISOString(),
        manual_reason: manualReason.trim(),
      });
      toast.success('Manual entry submitted');
      setIsAddingLog(false);
      setManualProject('');
      setManualTask('');
      setManualReason('');
      fetchWorklogs();
    } catch (error: any) {
      toast.error('Failed to submit', {
        description: error.response?.data?.detail || error.response?.data?.error?.message || 'Check your inputs',
      });
    } finally {
      setSubmittingManual(false);
    }
  };

  const filteredLogs = logs.filter(log => {
    const matchesSearch = log.task.toLowerCase().includes(searchQuery.toLowerCase()) ||
                         log.project.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesStatus = filterStatus === 'All' || log.status === filterStatus;
    return matchesSearch && matchesStatus;
  });

  return (
    <div className="p-8 space-y-8 max-w-[1600px] mx-auto animate-in fade-in duration-500 pb-20 bg-[#F8FAFC]">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
        <div>
          <h2 className="text-3xl font-black text-[#0F172A] tracking-tighter uppercase">Operational Worklogs</h2>
          <p className="text-[#64748B] font-bold uppercase tracking-widest text-[10px] mt-1">Audit trail of daily activities, time allocation, and approval statuses</p>
        </div>
        <div className="flex gap-3">
           <Button className="font-black h-12 px-8 uppercase text-[10px] tracking-widest bg-white border-slate-200 text-[#0F172A] hover:bg-slate-50 shadow-sm" onClick={() => setIsAddingLog(true)}>
              <Plus className="w-4 h-4 mr-2" /> Manual Log Entry
           </Button>
        </div>
      </div>

      {/* Unified Timer Design (Matches Dashboard) */}
      <TimerCard 
        title="Deliverable Session Tracker"
        projectOptions={timerProjects}
        taskOptions={timerTaskOptions}
        status={timerCardStatus}
        onStart={handleStartTimer}
        onPause={handlePauseTimer}
        onResume={handleResumeTimer}
        onStop={handleStopTimer}
      />

      <div className="flex flex-col md:flex-row gap-4 items-center">
        <div className="relative flex-1 w-full">
          <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <input 
            type="text" 
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search activity by task name or project identifier..." 
            className="w-full pl-12 pr-4 py-3 bg-white border border-slate-200 rounded-2xl text-sm font-bold focus:outline-none focus:ring-2 focus:ring-blue-600/10 transition-all shadow-sm"
          />
        </div>
        <div className="flex items-center gap-2 overflow-x-auto pb-2 md:pb-0 w-full md:w-auto scrollbar-none">
          {['All', 'Timer', 'Manual', 'Pending'].map((status) => (
            <button
              key={status}
              onClick={() => setFilterStatus(status as any)}
              className={cn(
                "px-4 py-2.5 rounded-xl text-[10px] font-black uppercase tracking-widest border transition-all whitespace-nowrap",
                filterStatus === status 
                  ? "bg-[#2563EB] border-[#2563EB] text-white shadow-lg shadow-blue-600/20" 
                  : "bg-white border-slate-200 text-[#64748B] hover:border-[#2563EB]"
              )}
            >
              {status}
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6">
        {loadingLogs && (
          <div className="text-center py-12 text-slate-400 font-bold text-sm">Loading worklogs...</div>
        )}
        {!loadingLogs && filteredLogs.length === 0 && (
          <div className="text-center py-12">
            <Clock className="w-12 h-12 text-slate-200 mx-auto mb-4" />
            <p className="text-slate-400 font-bold text-sm">No worklog entries found</p>
            <p className="text-slate-300 text-xs mt-1">Start a timer or add a manual entry to see your worklogs here</p>
          </div>
        )}
        {filteredLogs.map((log) => (
          <Card key={log.id} className="p-0 bg-white border-slate-200 overflow-hidden hover:shadow-xl transition-all group">
            <div className="flex flex-col md:flex-row">
              <div className={cn(
                "w-full md:w-2 border-r-0 md:border-r border-b md:border-b-0",
                log.status === 'Timer' ? 'bg-blue-500' : log.status === 'Manual' ? 'bg-amber-500' : 'bg-green-500'
              )} />
              <div className="flex-1 p-6 md:p-8">
                <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-6">
                  <div className="flex items-center gap-4">
                    <div className="p-3 bg-slate-50 rounded-xl">
                      <Clock size={20} className="text-blue-600" />
                    </div>
                    <div>
                      <h3 className="text-lg font-black text-[#0F172A] tracking-tight">{log.task}</h3>
                      <p className="text-[10px] font-black text-[#94A3B8] uppercase tracking-[0.2em]">{log.project} • {log.date}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-4">
                     <div className="text-right">
                        <p className="text-[10px] font-black text-[#94A3B8] uppercase tracking-widest">Duration</p>
                        <p className="text-lg font-black text-[#0F172A] tabular-nums">{log.duration}</p>
                     </div>
                     <Badge
                        variant={log.status === 'Timer' ? 'info' : log.status === 'Manual' ? 'warning' : 'neutral'}
                        className="h-8 px-4 font-black text-[10px] uppercase tracking-[0.2em]"
                     >
                        {log.status}
                     </Badge>
                     <button className="p-2 text-slate-300 hover:text-[#0F172A] transition-colors"><MoreVertical size={18} /></button>
                  </div>
                </div>
                
                <div className="bg-slate-50/50 p-5 rounded-2xl border border-slate-100 mb-4">
                   <p className="text-[10px] font-black text-[#94A3B8] uppercase tracking-widest mb-2">Activity Description</p>
                   <p className="text-xs font-medium text-slate-600 leading-relaxed">{log.description}</p>
                </div>

                {log.remarks && (
                  <div className="flex items-center gap-3 px-5 py-3 bg-red-50 rounded-xl border border-red-100">
                     <AlertCircle size={14} className="text-red-600" />
                     <p className="text-[10px] font-black text-red-600 uppercase tracking-widest">Supervisor Remarks: {log.remarks}</p>
                  </div>
                )}
              </div>
            </div>
          </Card>
        ))}
      </div>

      {/* Manual Entry Modal */}
      <Dialog open={isAddingLog} onOpenChange={setIsAddingLog}>
        <DialogContent className="max-w-xl p-0 overflow-hidden rounded-3xl border-none max-h-[90vh] min-h-[240px] flex flex-col">
           <DialogHeader className="p-8 bg-[#0F172A] text-white">
              <DialogTitle className="text-2xl font-black tracking-tighter">Manual Log Entry</DialogTitle>
              <p className="text-slate-400 text-[10px] font-bold uppercase tracking-widest mt-1">Record historical activity for project auditing</p>
           </DialogHeader>
          <div className="p-8 space-y-6 flex-1 overflow-y-auto min-h-0">
              <div className="grid grid-cols-2 gap-4">
                 <div className="space-y-2">
                    <label className="text-[10px] font-black text-[#64748B] uppercase tracking-widest">Project</label>
                    <Select value={manualProject} onValueChange={(val) => {
                      setManualProject(val);
                      setManualTask('');
                    }}>
                       <SelectTrigger className="h-12 font-bold rounded-xl bg-slate-50 border-slate-200">
                          <SelectValue placeholder="Select Project" />
                       </SelectTrigger>
                       <SelectContent>
                          {timerProjects.map(proj => (
                            <SelectItem key={proj.id} value={proj.id.toString()}>{proj.name}</SelectItem>
                          ))}
                       </SelectContent>
                    </Select>
                 </div>
                 <div className="space-y-2">
                    <label className="text-[10px] font-black text-[#64748B] uppercase tracking-widest">Date</label>
                    <Input type="date" className="h-12 font-bold rounded-xl bg-slate-50 border-slate-200" value={manualDate} onChange={(e) => setManualDate(e.target.value)} />
                 </div>
              </div>
              <div className="space-y-2">
                 <label className="text-[10px] font-black text-[#64748B] uppercase tracking-widest">Task Activity</label>
                 <Select value={manualTask} onValueChange={setManualTask}>
                    <SelectTrigger className="h-12 font-bold rounded-xl bg-slate-50 border-slate-200">
                       <SelectValue placeholder="Choose task from list" />
                    </SelectTrigger>
                    <SelectContent>
                       {(timerTaskOptions[manualProject] || []).map(task => (
                         <SelectItem key={task.id.toString()} value={task.id.toString()}>{task.name}</SelectItem>
                       ))}
                       {!(timerTaskOptions[manualProject] || []).length && manualProject && (
                         <SelectItem value="__none" disabled>No tasks assigned in this project</SelectItem>
                       )}
                    </SelectContent>
                 </Select>
              </div>
              <div className="grid grid-cols-2 gap-4">
                 <div className="space-y-2">
                    <label className="text-[10px] font-black text-[#64748B] uppercase tracking-widest">Start Time</label>
                    <Input type="time" className="h-12 font-bold rounded-xl bg-slate-50 border-slate-200" value={manualStartTime} onChange={(e) => setManualStartTime(e.target.value)} />
                 </div>
                 <div className="space-y-2">
                    <label className="text-[10px] font-black text-[#64748B] uppercase tracking-widest">End Time</label>
                    <Input type="time" className="h-12 font-bold rounded-xl bg-slate-50 border-slate-200" value={manualEndTime} onChange={(e) => setManualEndTime(e.target.value)} />
                 </div>
              </div>
              <div className="space-y-2">
                 <label className="text-[10px] font-black text-[#64748B] uppercase tracking-widest">Reason for Manual Entry</label>
                 <Textarea placeholder="Explain why this entry is being logged manually..." value={manualReason} onChange={(e) => setManualReason(e.target.value)} className="min-h-[120px] font-bold rounded-2xl bg-slate-50 border-slate-200 resize-none" />
              </div>
           </div>
           <DialogFooter className="p-8 bg-slate-50 border-t border-slate-100 flex gap-3">
              <Button variant="outline" className="flex-1 h-12 font-black uppercase text-[10px] tracking-widest" onClick={() => setIsAddingLog(false)}>Cancel</Button>
              <Button disabled={submittingManual} className="flex-1 h-12 font-black uppercase text-[10px] tracking-widest bg-blue-600 hover:bg-blue-700 shadow-lg shadow-blue-600/20" onClick={handleManualSubmit}>
                {submittingManual ? 'Submitting...' : 'Submit Log'}
              </Button>
           </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};
