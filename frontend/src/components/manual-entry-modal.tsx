import React, { useState, useEffect } from 'react';
import { X } from 'lucide-react';
import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';
import { Button, Input, Card } from './ui-elements';
import { toast } from 'sonner@2.0.3';

interface ManualEntryModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

export const ManualEntryModal = ({ isOpen, onClose, onSuccess }: ManualEntryModalProps) => {
  const [projects, setProjects] = useState<any[]>([]);
  const [myTasksByProject, setMyTasksByProject] = useState<Record<number, any[]>>({});
  const [projectId, setProjectId] = useState<string>("");
  const [taskId, setTaskId] = useState<string>("");
  const [startAt, setStartAt] = useState("");
  const [endAt, setEndAt] = useState("");
  const [reason, setReason] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    if (isOpen) {
      fetchProjectsAndTasks();
      const now = new Date();
      const oneHourAgo = new Date(now.getTime() - 3600000);
      setStartAt(oneHourAgo.toISOString().slice(0, 16));
      setEndAt(now.toISOString().slice(0, 16));
    }
  }, [isOpen]);

  // Reset task selection when project changes
  useEffect(() => {
    setTaskId("");
  }, [projectId]);

  const fetchProjectsAndTasks = async () => {
    try {
      const [projectsResp, myTasksResp] = await Promise.all([
        client.get(ENDPOINTS.PROJECTS.LIST),
        client.get(ENDPOINTS.TASKS.MY_TASKS),
      ]);
      setProjects(projectsResp.data);
      if (projectsResp.data.length > 0) {
        setProjectId(projectsResp.data[0].id.toString());
      }

      // Build a map of projectId → tasks assigned to me
      const taskMap: Record<number, any[]> = {};
      for (const proj of (myTasksResp.data || [])) {
        taskMap[proj.id] = proj.tasks || [];
      }
      setMyTasksByProject(taskMap);
    } catch (error) {
      console.error("Failed to fetch projects/tasks", error);
    }
  };

  const tasksForProject = projectId ? (myTasksByProject[Number(projectId)] || []) : [];

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!reason) {
      toast.error("Manual reason is required");
      return;
    }
    if (!taskId) {
      toast.error("Please select a task");
      return;
    }

    setIsSubmitting(true);
    try {
      await client.post(ENDPOINTS.TIMESHEET.MANUAL, {
        project_id: parseInt(projectId),
        task_id: parseInt(taskId),
        start_at: new Date(startAt).toISOString(),
        end_at: new Date(endAt).toISOString(),
        manual_reason: reason,
      });
      toast.success("Manual entry recorded");
      onSuccess();
      onClose();
    } catch (error: any) {
      toast.error("Failed to save manual entry", {
        description: error.response?.data?.error?.message || "Invalid dates or missing data"
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-900/60 backdrop-blur-sm p-4">
      <Card
        className="w-full max-w-lg bg-white shadow-2xl rounded-3xl overflow-hidden animate-in zoom-in duration-200"
        style={{
          maxHeight: "70vh",
          overflowY: "auto",
          overscrollBehavior: "contain",
          WebkitOverflowScrolling: "touch",
        }}
      >
        <div className="p-8 border-b border-slate-50 flex justify-between items-center">
          <div>
            <h2 className="text-2xl font-black text-[#0F172A] tracking-tighter">MANUAL WORKLOG ENTRY</h2>
            <p className="text-[10px] font-black text-[#64748B] uppercase tracking-[0.2em] mt-1">Operational integrity verification required</p>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-slate-100 rounded-xl transition-all"><X size={20} /></button>
        </div>

        <form onSubmit={handleSubmit} className="p-8 space-y-6">
          <div className="space-y-4">
            <div className="space-y-1.5">
              <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Select Project</label>
              <select
                value={projectId}
                onChange={(e) => setProjectId(e.target.value)}
                className="w-full h-12 bg-slate-50 border border-slate-100 rounded-xl px-4 text-xs font-black uppercase tracking-widest text-slate-700 outline-none focus:ring-2 focus:ring-blue-500/10"
              >
                {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
            </div>

            <div className="space-y-1.5">
              <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Select Task (Assigned to You)</label>
              {tasksForProject.length === 0 ? (
                <div className="h-12 bg-slate-50 border border-slate-100 rounded-xl px-4 flex items-center text-xs font-bold text-slate-400">
                  {projectId ? "No tasks assigned to you in this project" : "Select a project first"}
                </div>
              ) : (
                <select
                  value={taskId}
                  onChange={(e) => setTaskId(e.target.value)}
                  className="w-full h-12 bg-slate-50 border border-slate-100 rounded-xl px-4 text-xs font-black text-slate-700 outline-none focus:ring-2 focus:ring-blue-500/10"
                >
                  <option value="">— Select a task —</option>
                  {tasksForProject.map((t: any) => (
                    <option key={t.id} value={t.id}>T-{t.id}: {t.title}</option>
                  ))}
                </select>
              )}
            </div>

            <div className="grid grid-cols-2 gap-4">
              <Input
                label="START TIME"
                type="datetime-local"
                value={startAt}
                onChange={(e) => setStartAt(e.target.value)}
                className="font-black text-[10px]"
              />
              <Input
                label="END TIME"
                type="datetime-local"
                value={endAt}
                onChange={(e) => setEndAt(e.target.value)}
                className="font-black text-[10px]"
              />
            </div>

            <div className="space-y-1.5">
              <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest">MANUAL LOG REASON (Required)</label>
              <textarea
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="Explain why this time was not tracked via the live session recorder..."
                className="w-full h-32 bg-slate-50 border border-slate-100 rounded-2xl p-4 text-sm font-medium text-slate-700 outline-none focus:ring-2 focus:ring-blue-500/10 resize-none"
              />
            </div>
          </div>

          <div className="flex gap-4 pt-4">
            <Button
              type="button"
              variant="outline"
              onClick={onClose}
              className="flex-1 h-14 font-black uppercase text-[10px] tracking-widest rounded-2xl"
            >
              Discard
            </Button>
            <Button
              type="submit"
              isLoading={isSubmitting}
              disabled={!taskId || !reason}
              className="flex-1 h-14 bg-[#2563EB] hover:bg-blue-700 font-black uppercase text-[10px] tracking-widest rounded-2xl"
            >
              Save Record
            </Button>
          </div>
        </form>
      </Card>
    </div>
  );
};
