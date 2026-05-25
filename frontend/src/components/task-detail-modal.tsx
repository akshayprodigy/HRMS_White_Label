import { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import {
  X,
  Paperclip,
  CheckCircle2,
  ChevronRight,
  Plus,
  Loader2,
  Send,
  ClipboardCheck,
  ThumbsUp,
  ThumbsDown,
  PauseCircle,
  Upload,
  History,
  Clock,
  Lock,
  AlertCircle,
} from 'lucide-react';
import { Badge, Button, cn } from './ui-elements';
import { toast } from 'sonner';
import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';
import { normalizeRoleName } from '../utils/roles';

interface TaskDetailModalProps {
  taskId: string | null;
  isOpen: boolean;
  onClose: () => void;
}

const statusColors: Record<string, string> = {
  approved: 'bg-green-100 text-green-700 border-green-200',
  rejected: 'bg-red-100 text-red-700 border-red-200',
  on_hold: 'bg-amber-100 text-amber-700 border-amber-200',
  pending: 'bg-blue-100 text-blue-700 border-blue-200',
};
const borderColors: Record<string, string> = {
  approved: 'border-green-400',
  rejected: 'border-red-400',
  on_hold: 'border-amber-400',
  pending: 'border-blue-400',
};

export const TaskDetailModal = ({ taskId, isOpen, onClose }: TaskDetailModalProps) => {
  const [task, setTask] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [activeSubtaskId, setActiveSubtaskId] = useState<number | null>(null);
  const [commentText, setCommentText] = useState('');
  const [postingComment, setPostingComment] = useState(false);
  const [newMilestoneTitle, setNewMilestoneTitle] = useState('');
  const [creatingMilestone, setCreatingMilestone] = useState(false);
  const [showMilestoneCreate, setShowMilestoneCreate] = useState(false);
  const [me, setMe] = useState<any>(null);
  const [completionRequests, setCompletionRequests] = useState<any[]>([]);
  const [timeSummary, setTimeSummary] = useState<any>(null);
  const [subtaskTimeSummary, setSubtaskTimeSummary] = useState<any>(null);
  const [submitNotes, setSubmitNotes] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [reviewNotes, setReviewNotes] = useState('');
  const [reviewing, setReviewing] = useState(false);
  const [showSubmitModal, setShowSubmitModal] = useState(false);
  const [pendingFiles, setPendingFiles] = useState<File[]>([]);
  const [timerStatus, setTimerStatus] = useState<any>(null);
  const submitFileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (isOpen && taskId) {
      fetchTask();
      fetchMe();
      loadCompletionData();
      setShowSubmitModal(false);
      setPendingFiles([]);
      setActiveSubtaskId(null);
    }
  }, [isOpen, taskId]);

  useEffect(() => {
    if (activeSubtaskId && taskId) {
      client.get(ENDPOINTS.TASKS.TIME_SUMMARY(Number(taskId)), {
        params: { subtask_id: activeSubtaskId },
      }).then(r => setSubtaskTimeSummary(r.data)).catch(() => setSubtaskTimeSummary(null));
    } else {
      setSubtaskTimeSummary(null);
    }
  }, [activeSubtaskId, taskId]);

  const fetchMe = async () => {
    try {
      const resp = await client.get(ENDPOINTS.AUTH.ME);
      setMe(resp.data);
    } catch {
      setMe(null);
    }
  };

  const loadCompletionData = async () => {
    if (!taskId) return;
    try {
      const [reqResp, summaryResp] = await Promise.all([
        client.get(ENDPOINTS.TASKS.COMPLETION_REQUESTS(Number(taskId))),
        client.get(ENDPOINTS.TASKS.TIME_SUMMARY(Number(taskId))),
      ]);
      setCompletionRequests(reqResp.data || []);
      setTimeSummary(summaryResp.data);
    } catch (error) {
      console.error('Error loading completion data:', error);
    }
  };

  const checkAndOpenSubmitModal = async (prefillNotes?: string) => {
    try {
      const r = await client.get(ENDPOINTS.TIMESHEET.TIMER_STATUS);
      setTimerStatus(r.data);
    } catch {
      setTimerStatus(null);
    }
    if (prefillNotes) setSubmitNotes(prefillNotes);
    setShowSubmitModal(true);
  };

  const handleSubmitCompletion = async () => {
    if (!submitNotes.trim() || !taskId) return;
    setSubmitting(true);
    try {
      const reqResp = await client.post(ENDPOINTS.TASKS.COMPLETION_REQUESTS(Number(taskId)), {
        notes: submitNotes.trim(),
        subtask_id: activeSubtaskId ?? undefined,
      });
      const requestId = reqResp.data.id;
      for (const file of pendingFiles) {
        const fd = new FormData();
        fd.append('file', file);
        await client.post(ENDPOINTS.TASKS.COMPLETION_DOCUMENT(Number(taskId), requestId), fd, {
          headers: { 'Content-Type': 'multipart/form-data' },
        });
      }
      setSubmitNotes('');
      setPendingFiles([]);
      setShowSubmitModal(false);
      await loadCompletionData();
      toast.success('Submitted for PM approval', {
        description: 'Your PM will review and get back to you.',
      });
    } catch (error: any) {
      console.error('Error submitting completion request:', error);
      toast.error('Submission failed', {
        description: error?.response?.data?.error?.message || 'Something went wrong. Please try again.',
      });
    } finally {
      setSubmitting(false);
    }
  };

  const handleReview = async (requestId: number, action: 'approve' | 'reject' | 'on_hold') => {
    if (!reviewNotes.trim() || !taskId) return;
    setReviewing(true);
    try {
      await client.post(ENDPOINTS.TASKS.COMPLETION_REVIEW(Number(taskId), requestId), {
        action,
        reviewer_notes: reviewNotes.trim(),
      });
      setReviewNotes('');
      await loadCompletionData();
      if (action === 'approve') fetchTask();
    } catch (error) {
      console.error('Error reviewing completion request:', error);
    } finally {
      setReviewing(false);
    }
  };


  const isPM = () => {
    if (!me) return false;
    if (me.is_superuser) return true;
    const roleNames = Array.isArray(me?.roles)
      ? me.roles.map((r: any) => normalizeRoleName(String(r?.name || ''))).filter(Boolean)
      : [];
    return roleNames.includes('super admin') || roleNames.includes('pm') || roleNames.includes('coo');
  };
  const isEmployeeView = () => !isPM();

  // Filter completion requests to the active work item:
  // null activeSubtaskId → main task requests (subtask_id == null)
  // non-null → only that subtask's requests
  const itemCompletionRequests = completionRequests.filter((r: any) =>
    activeSubtaskId === null ? r.subtask_id == null : r.subtask_id === activeSubtaskId
  );
  const pendingRequest = itemCompletionRequests.find((r: any) => r.status === 'pending');

  const fetchTask = async () => {
    setLoading(true);
    try {
      const response = await client.get(ENDPOINTS.TASKS.DETAIL(Number(taskId)));
      setTask(response.data);
      if (response.data.subtasks && response.data.subtasks.length > 0) {
        setActiveSubtaskId(response.data.subtasks[0].id);
      }
    } catch (error) {
      console.error('Error fetching task details:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleAddComment = async () => {
    if (!commentText.trim()) return;
    setPostingComment(true);
    try {
      await client.post(ENDPOINTS.TASKS.COMMENTS(Number(taskId)), {
        content: commentText,
        subtask_id: activeSubtaskId ?? undefined,
      });
      setCommentText('');
      fetchTask();
    } catch (error) {
      console.error('Error posting comment:', error);
    } finally {
      setPostingComment(false);
    }
  };

  const toggleSubtask = async (subtaskId: number, currentlyCompleted: boolean) => {
    const newStatus = !currentlyCompleted;
    try {
      await client.patch(ENDPOINTS.TASKS.SUBTASK(subtaskId), { is_completed: newStatus });
      setTask((prev: any) => ({
        ...prev,
        subtasks: prev.subtasks.map((st: any) =>
          st.id === subtaskId ? { ...st, is_completed: newStatus } : st
        )
      }));
    } catch (error) {
      console.error('Error updating subtask:', error);
    }
  };

  const canManageMilestones = () => {
    if (!task) return false;
    if (me?.is_superuser) return true;
    const roleNames = Array.isArray(me?.roles)
      ? me.roles.map((r: any) => normalizeRoleName(String(r?.name || ''))).filter(Boolean)
      : [];
    if (roleNames.includes('super admin') || roleNames.includes('pm')) return true;
    return Number(task?.assignee_id) === Number(me?.id) || Number(task?.creator_id) === Number(me?.id);
  };

  const handleCreateMilestone = async () => {
    if (!taskId) return;
    const title = newMilestoneTitle.trim();
    if (!title) return;
    setCreatingMilestone(true);
    try {
      const resp = await client.post(ENDPOINTS.TASKS.SUBTASKS(Number(taskId)), {
        title,
        is_completed: false,
      });
      const created = resp.data;
      setTask((prev: any) => ({
        ...prev,
        subtasks: Array.isArray(prev?.subtasks) ? [...prev.subtasks, created] : [created],
      }));
      if (created?.id) setActiveSubtaskId(created.id);
      setNewMilestoneTitle('');
      setShowMilestoneCreate(false);
    } catch (error) {
      console.error('Error creating milestone:', error);
    } finally {
      setCreatingMilestone(false);
    }
  };

  if (!isOpen) return null;

  // ── Shared sub-components ──────────────────────────────────────────────────

  const CompletionHistory = () => (
    itemCompletionRequests.length > 0 ? (
      <div className="space-y-3">
        {itemCompletionRequests.map((req: any) => (
          <div key={req.id} className={cn("p-4 rounded-2xl border-l-4 bg-slate-50", borderColors[req.status] ?? 'border-slate-300')}>
            <div className="flex items-center justify-between mb-2">
              <span className={cn("text-[9px] font-black uppercase tracking-widest px-2 py-0.5 rounded-full border", statusColors[req.status])}>
                {req.status.replace('_', ' ')}
              </span>
              <span className="text-[10px] font-bold text-slate-400">
                {new Date(req.created_at).toLocaleDateString()}
              </span>
            </div>
            {req.subtask_title && (
              <p className="text-[9px] font-black text-blue-500 uppercase tracking-widest mb-1">
                Subtask: {req.subtask_title}
              </p>
            )}
            <p className="text-xs font-medium text-slate-600 mb-1">{req.notes}</p>
            {req.reviewer_notes && (
              <p className="text-[10px] font-bold text-slate-500 italic border-t border-slate-200 pt-2 mt-2">
                PM feedback: {req.reviewer_notes}
              </p>
            )}
            {req.documents?.length > 0 && (
              <div className="flex flex-wrap gap-2 mt-2">
                {req.documents.map((d: any) => (
                  <span key={d.id} className="flex items-center gap-1 text-[9px] font-black text-slate-500 bg-white border border-slate-200 rounded-lg px-2 py-1">
                    <Paperclip size={9} /> {d.file_name}
                  </span>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    ) : null
  );

  // ── Employee view ──────────────────────────────────────────────────────────
  const renderEmployeeView = () => {
    const mySubtasks = (task?.subtasks || []).filter(
      (st: any) => Number(st.assignee_id) === Number(me?.id)
    );
    const activeSt = mySubtasks.find((st: any) => st.id === activeSubtaskId) ?? null;
    const displaySummary = activeSubtaskId ? subtaskTimeSummary : timeSummary;
    const isTimerRunningForTask =
      timerStatus?.is_active && Number(timerStatus?.session?.task_id) === Number(taskId);
    // Last PM-reviewed request for this work item that needs resubmission
    const lastActedRequest = !pendingRequest && task?.status !== 'completed'
      ? [...itemCompletionRequests].reverse().find((r: any) => r.status === 'rejected' || r.status === 'on_hold')
      : null;

    return (
      <div
        style={{ maxHeight: '85vh' }}
        className="relative w-full max-w-4xl bg-white rounded-3xl shadow-2xl flex flex-col overflow-hidden"
      >
        {/* Header */}
        <div className="bg-[#0F172A] px-6 py-4 text-white rounded-t-3xl flex items-center justify-between flex-shrink-0">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 mb-1">
              <span className="text-[10px] font-black text-slate-400 uppercase tracking-widest">T-{taskId}</span>
              {task && (
                <Badge variant={task.status === 'completed' ? 'success' : 'neutral'} className="uppercase text-[9px] font-black px-2 h-5">
                  {task.status.replace('_', ' ')}
                </Badge>
              )}
            </div>
            <h2 className="text-base font-black leading-snug truncate">{task?.title || 'Loading...'}</h2>
            <p className="text-[10px] font-bold text-slate-400 mt-0.5">{task?.project?.name}</p>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-white/10 rounded-xl transition-colors ml-4 flex-shrink-0">
            <X size={18} />
          </button>
        </div>

        {/* Body: two columns */}
        <div className="flex flex-1 overflow-hidden min-h-0">

          {/* Left panel — work items */}
          <div className="w-56 border-r border-slate-100 bg-slate-50/40 overflow-y-auto flex-shrink-0 p-4 space-y-1.5">
            <p className="text-[9px] font-black text-slate-400 uppercase tracking-widest mb-3">Your Work Items</p>

            {/* Main task */}
            <div
              onClick={() => setActiveSubtaskId(null)}
              className={cn(
                "p-3 rounded-xl cursor-pointer transition-all border-2",
                activeSubtaskId === null
                  ? "bg-white border-blue-600 shadow-sm"
                  : "bg-transparent border-transparent hover:bg-white hover:border-slate-200"
              )}
            >
              <p className={cn("text-xs font-black truncate", activeSubtaskId === null ? "text-blue-600" : "text-[#0F172A]")}>
                {task?.title || '...'}
              </p>
              <p className="text-[9px] font-bold text-slate-400 mt-0.5">Main Task</p>
              {timeSummary?.actual_hours > 0 && (
                <p className="text-[9px] font-black text-blue-500 mt-1">{timeSummary.actual_hours.toFixed(1)}h logged</p>
              )}
            </div>

            {/* Subtasks */}
            {mySubtasks.length > 0 && (
              <>
                <p className="text-[9px] font-black text-slate-300 uppercase tracking-widest px-1 pt-2">Subtasks</p>
                {mySubtasks.map((st: any) => (
                  <div
                    key={st.id}
                    onClick={() => setActiveSubtaskId(st.id)}
                    className={cn(
                      "p-3 rounded-xl cursor-pointer transition-all border-2",
                      activeSubtaskId === st.id
                        ? "bg-white border-blue-600 shadow-sm"
                        : "bg-transparent border-transparent hover:bg-white hover:border-slate-200"
                    )}
                  >
                    <div className="flex items-center gap-2">
                      <div
                        onClick={(e) => { e.stopPropagation(); toggleSubtask(st.id, st.is_completed); }}
                        className={cn(
                          "w-4 h-4 rounded flex items-center justify-center cursor-pointer flex-shrink-0 transition-transform hover:scale-110",
                          st.is_completed ? "bg-green-100 text-green-600" : "bg-slate-200 text-slate-400"
                        )}
                      >
                        {st.is_completed ? <CheckCircle2 size={10} /> : <div className="w-1.5 h-1.5 rounded-full bg-slate-400" />}
                      </div>
                      <p className={cn(
                        "text-xs font-black truncate",
                        activeSubtaskId === st.id ? "text-blue-600" : st.is_completed ? "text-slate-400 line-through" : "text-[#0F172A]"
                      )}>
                        {st.title}
                      </p>
                    </div>
                    {st.estimated_hours != null && (
                      <p className="text-[9px] text-slate-400 font-bold mt-1 ml-6">{st.estimated_hours}h est.</p>
                    )}
                  </div>
                ))}
              </>
            )}
          </div>

          {/* Right panel — detail + comments */}
          <div className="flex-1 flex flex-col overflow-hidden">
            <div className="flex-1 overflow-y-auto p-6 space-y-5">

              {/* Status banners */}
              {task?.status === 'completed' && (
                <div className="flex items-center gap-3 p-4 bg-green-50 border border-green-200 rounded-2xl">
                  <CheckCircle2 size={18} className="text-green-500 flex-shrink-0" />
                  <div>
                    <p className="text-sm font-black text-green-700">Task approved and completed</p>
                    <p className="text-xs text-green-600">Your PM has approved this task.</p>
                  </div>
                </div>
              )}
              {pendingRequest && task?.status !== 'completed' && (
                <div className="flex items-start gap-3 p-4 bg-amber-50 border-2 border-amber-200 rounded-2xl">
                  <div className="w-2 h-2 rounded-full bg-amber-400 animate-pulse flex-shrink-0 mt-1.5" />
                  <div>
                    <p className="text-sm font-black text-amber-700">Waiting for PM review</p>
                    <p className="text-xs text-amber-600 mt-0.5 italic">"{pendingRequest.notes}"</p>
                    {pendingRequest.documents?.length > 0 && (
                      <div className="flex flex-wrap gap-1.5 mt-2">
                        {pendingRequest.documents.map((d: any) => (
                          <span key={d.id} className="flex items-center gap-1 text-[9px] font-black text-amber-700 bg-amber-100 rounded-lg px-2 py-1">
                            <Paperclip size={9} /> {d.file_name}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* Re-submit banner (rejected or on_hold, no pending) */}
              {lastActedRequest && (
                <div className={cn(
                  "p-4 rounded-2xl border-2 space-y-3",
                  lastActedRequest.status === 'rejected'
                    ? "bg-red-50 border-red-200"
                    : "bg-amber-50 border-amber-200"
                )}>
                  <div className="flex items-center gap-2">
                    <AlertCircle size={15} className={lastActedRequest.status === 'rejected' ? "text-red-500" : "text-amber-500"} />
                    <p className={cn("text-sm font-black", lastActedRequest.status === 'rejected' ? "text-red-700" : "text-amber-700")}>
                      {lastActedRequest.status === 'rejected' ? 'PM rejected your submission' : 'PM put your submission on hold'}
                    </p>
                  </div>
                  {lastActedRequest.reviewer_notes && (
                    <p className={cn("text-xs italic", lastActedRequest.status === 'rejected' ? "text-red-600" : "text-amber-600")}>
                      PM feedback: "{lastActedRequest.reviewer_notes}"
                    </p>
                  )}
                  <button
                    onClick={() => checkAndOpenSubmitModal(`Re-submission: [describe what changed]\n\nPrevious submission: ${lastActedRequest.notes}`)}
                    className={cn(
                      "w-full h-10 rounded-xl font-black text-xs uppercase tracking-widest flex items-center justify-center gap-2 text-white transition-colors",
                      lastActedRequest.status === 'rejected' ? "bg-red-600 hover:bg-red-700" : "bg-amber-500 hover:bg-amber-600"
                    )}
                  >
                    <ClipboardCheck size={13} /> Re-submit for Approval
                  </button>
                </div>
              )}

              {/* Time summary */}
              {displaySummary && (
                <div className={cn("bg-slate-50 rounded-2xl p-4 border flex items-center gap-5", pendingRequest ? "border-slate-200" : "border-slate-100")}>
                  {pendingRequest && <Lock size={12} className="text-slate-400 flex-shrink-0" />}
                  <div className="flex items-center gap-2">
                    <Clock size={13} className="text-blue-500" />
                    <div>
                      <p className="text-[9px] font-black text-slate-400 uppercase tracking-widest">
                        {activeSt ? `${activeSt.title} — ` : ''}Logged
                      </p>
                      <p className="text-base font-black text-blue-600">{(displaySummary.actual_hours ?? 0).toFixed(1)}h</p>
                    </div>
                  </div>
                  {displaySummary.estimated_hours != null && (
                    <>
                      <div className="h-7 w-px bg-slate-200" />
                      <div>
                        <p className="text-[9px] font-black text-slate-400 uppercase tracking-widest">Estimated</p>
                        <p className="text-base font-black text-slate-700">{displaySummary.estimated_hours}h</p>
                      </div>
                      <div className="flex-1">
                        <div className="w-full h-1.5 bg-slate-200 rounded-full overflow-hidden">
                          <div
                            className={cn("h-full rounded-full", (displaySummary.actual_hours / displaySummary.estimated_hours) > 1 ? "bg-red-400" : "bg-blue-500")}
                            style={{ width: `${Math.min((displaySummary.actual_hours / displaySummary.estimated_hours) * 100, 100)}%` }}
                          />
                        </div>
                        <p className="text-[9px] font-bold text-slate-400 text-right mt-0.5">
                          {Math.round((displaySummary.actual_hours / displaySummary.estimated_hours) * 100)}% of estimate
                        </p>
                      </div>
                    </>
                  )}
                </div>
              )}

              {/* Description (main task only) */}
              {!activeSubtaskId && task?.description && (
                <p className="text-sm text-slate-600 leading-relaxed bg-slate-50 p-4 rounded-2xl border border-slate-100">
                  {task.description}
                </p>
              )}

              {/* Approval history */}
              {itemCompletionRequests.length > 0 && (
                <div className="space-y-2">
                  <h3 className="text-[9px] font-black text-slate-400 uppercase tracking-widest flex items-center gap-1.5">
                    <History size={10} /> Approval History
                  </h3>
                  <CompletionHistory />
                </div>
              )}

              {/* Comments */}
              {(() => {
                const visibleComments = (task?.comments || []).filter((c: any) =>
                  activeSubtaskId === null ? c.subtask_id == null : c.subtask_id === activeSubtaskId
                );
                return (
                  <div className="space-y-3">
                    <h3 className="text-[9px] font-black text-slate-400 uppercase tracking-widest">Comments</h3>
                    {visibleComments.length > 0 ? (
                      <div className="space-y-3">
                        {visibleComments.map((c: any, i: number) => (
                          <div key={i} className="flex gap-3">
                            <div className="w-8 h-8 rounded-lg bg-blue-100 text-blue-600 flex items-center justify-center text-[10px] font-black flex-shrink-0">
                              {c.user?.full_name?.substring(0, 2) || '??'}
                            </div>
                            <div className="flex-1 bg-slate-50 p-3 rounded-xl">
                              <div className="flex items-center justify-between mb-1">
                                <span className="text-xs font-black text-[#0F172A]">{c.user?.full_name}</span>
                                <span className="text-[10px] text-slate-400">
                                  {new Date(c.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                                </span>
                              </div>
                              <p className="text-xs text-slate-600">{c.content}</p>
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="text-xs text-slate-400 text-center py-3">No comments yet.</p>
                    )}
                  </div>
                );
              })()}
            </div>

            {/* Footer: comment input + submit button */}
            <div className="flex-shrink-0 border-t border-slate-100">
              <div className="p-4 flex items-center gap-3 bg-slate-50/50">
                <input
                  type="text"
                  value={commentText}
                  onChange={(e) => setCommentText(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleAddComment()}
                  placeholder="Add a comment..."
                  className="flex-1 h-10 bg-white border border-slate-200 rounded-xl px-4 text-sm focus:outline-none focus:ring-2 focus:ring-blue-600/10"
                />
                <button
                  disabled={postingComment || !commentText.trim()}
                  onClick={handleAddComment}
                  className="h-10 px-4 bg-blue-600 text-white rounded-xl disabled:opacity-40 hover:bg-blue-700 transition-colors"
                >
                  {postingComment ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
                </button>
              </div>
              {task?.status !== 'completed' && !pendingRequest && (
                <div className="px-4 pb-4">
                  <button
                    onClick={() => checkAndOpenSubmitModal()}
                    className="w-full h-12 bg-[#0F172A] hover:bg-blue-700 text-white rounded-2xl font-black text-xs uppercase tracking-widest flex items-center justify-center gap-2 transition-colors"
                  >
                    <ClipboardCheck size={15} /> Submit for PM Approval
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Submission overlay modal */}
        {showSubmitModal && (
          <div className="absolute inset-0 z-20 flex items-center justify-center p-6 bg-[#0F172A]/70 backdrop-blur-sm rounded-3xl">
            <div className="w-full max-w-md bg-white rounded-2xl shadow-2xl p-6 space-y-5">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-base font-black text-[#0F172A]">Submit for PM Approval</h3>
                  <p className="text-[10px] font-bold text-slate-400 mt-0.5">
                    {activeSt ? `${task?.title} › ${activeSt.title}` : task?.title}
                  </p>
                </div>
                <button
                  onClick={() => { setShowSubmitModal(false); setPendingFiles([]); setSubmitNotes(''); }}
                  className="p-1.5 hover:bg-slate-100 rounded-lg transition-colors"
                >
                  <X size={16} />
                </button>
              </div>

              {/* Timer warning */}
              {isTimerRunningForTask && (
                <div className="flex items-start gap-3 p-4 bg-orange-50 border-2 border-orange-200 rounded-xl">
                  <AlertCircle size={16} className="text-orange-500 flex-shrink-0 mt-0.5" />
                  <div>
                    <p className="text-xs font-black text-orange-700">Timer is still running!</p>
                    <p className="text-xs text-orange-600 mt-0.5">
                      Stop your timer and sync your time before submitting — otherwise your logged hours won't be counted.
                    </p>
                  </div>
                </div>
              )}

              {/* Notes */}
              <div className="space-y-1.5">
                <label className="text-[9px] font-black text-slate-400 uppercase tracking-widest">Completion Notes *</label>
                <textarea
                  value={submitNotes}
                  onChange={(e) => setSubmitNotes(e.target.value)}
                  placeholder="What did you complete? Any blockers or notes for your PM..."
                  rows={4}
                  className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 resize-none"
                />
              </div>

              {/* File attachments */}
              <div className="space-y-2">
                <label className="text-[9px] font-black text-slate-400 uppercase tracking-widest">Supporting Documents</label>
                <input
                  ref={submitFileInputRef}
                  type="file"
                  multiple
                  className="hidden"
                  onChange={(e) => {
                    const files = Array.from(e.target.files || []);
                    setPendingFiles((prev) => [...prev, ...files]);
                    e.target.value = '';
                  }}
                />
                {pendingFiles.length > 0 && (
                  <div className="space-y-1.5">
                    {pendingFiles.map((f, i) => (
                      <div key={i} className="flex items-center justify-between text-xs font-bold text-slate-600 bg-slate-50 rounded-lg px-3 py-2">
                        <span className="flex items-center gap-2 truncate min-w-0">
                          <Paperclip size={11} className="text-blue-400 flex-shrink-0" />
                          <span className="truncate">{f.name}</span>
                        </span>
                        <button
                          onClick={() => setPendingFiles((prev) => prev.filter((_, j) => j !== i))}
                          className="text-slate-400 hover:text-red-500 ml-2 flex-shrink-0"
                        >
                          <X size={12} />
                        </button>
                      </div>
                    ))}
                  </div>
                )}
                <button
                  onClick={() => submitFileInputRef.current?.click()}
                  className="flex items-center gap-2 text-xs font-black text-blue-600 hover:text-blue-800 transition-colors"
                >
                  <Upload size={13} /> Attach file
                </button>
              </div>

              {/* Actions */}
              <div className="flex gap-3 pt-1">
                <button
                  onClick={() => { setShowSubmitModal(false); setPendingFiles([]); setSubmitNotes(''); }}
                  className="flex-1 h-11 border-2 border-slate-200 rounded-xl font-black text-xs uppercase tracking-widest text-slate-600 hover:bg-slate-50 transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={handleSubmitCompletion}
                  disabled={submitting || !submitNotes.trim() || isTimerRunningForTask}
                  className="flex-1 h-11 bg-blue-600 hover:bg-blue-700 text-white rounded-xl font-black text-xs uppercase tracking-widest flex items-center justify-center gap-2 disabled:opacity-40 transition-colors"
                >
                  {submitting ? <Loader2 size={13} className="animate-spin" /> : <ClipboardCheck size={13} />}
                  Submit
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    );
  };

  // ── PM / full view ─────────────────────────────────────────────────────────
  const renderPMView = () => {
    const allSubtasks: any[] = task?.subtasks || [];

    // Index pending requests by work item key
    const pendingByItem: Record<string, any> = {};
    for (const r of completionRequests) {
      if (r.status !== 'pending') continue;
      const key = r.subtask_id == null ? 'main' : `st:${r.subtask_id}`;
      pendingByItem[key] = r;
    }
    const pendingItems = Object.values(pendingByItem);
    const totalPending = pendingItems.length;

    // Pending request for the currently selected work item
    const activePending = activeSubtaskId === null
      ? pendingByItem['main']
      : pendingByItem[`st:${activeSubtaskId}`];

    // Active item's scoped data
    const visibleComments = (task?.comments || []).filter((c: any) =>
      activeSubtaskId === null ? c.subtask_id == null : c.subtask_id === activeSubtaskId
    );
    const activeHistory = completionRequests.filter((r: any) =>
      activeSubtaskId === null ? r.subtask_id == null : r.subtask_id === activeSubtaskId
    );
    const activeTs = activeSubtaskId ? subtaskTimeSummary : timeSummary;

    // Active subtask metadata
    const activeSt = allSubtasks.find((s: any) => s.id === activeSubtaskId) ?? null;
    const isOwnedByMe = activeSt
      ? Number(activeSt.assignee_id) === Number(me?.id)
      : Number(task?.assignee_id) === Number(me?.id);

    // Avatar color palette (cycles by subtask index)
    const avatarColors = ['bg-violet-100 text-violet-700', 'bg-teal-100 text-teal-700', 'bg-rose-100 text-rose-700', 'bg-sky-100 text-sky-700', 'bg-orange-100 text-orange-700'];

    return (
      <div style={{ maxHeight: '88vh' }} className="relative w-full max-w-5xl bg-white rounded-3xl shadow-2xl overflow-hidden flex flex-col">

        {/* ── Header ── */}
        <div className="bg-[#0F172A] px-7 py-4 text-white flex items-center justify-between flex-shrink-0">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 mb-0.5">
              <span className="text-[10px] font-black text-slate-400 uppercase tracking-widest">T-{taskId}</span>
              <span className="text-slate-600">·</span>
              <span className="text-[10px] font-bold text-slate-400">{task?.project?.name}</span>
            </div>
            <h2 className="text-base font-black tracking-tight truncate">{task?.title || 'Loading...'}</h2>
          </div>
          <div className="flex items-center gap-2.5 flex-shrink-0 ml-4">
            {totalPending > 0 && (
              <span className="flex items-center gap-1.5 bg-amber-500 text-white text-[10px] font-black px-2.5 py-1 rounded-full whitespace-nowrap">
                <AlertCircle size={10} /> {totalPending} awaiting review
              </span>
            )}
            {task && (
              <Badge variant={task.status === 'completed' ? 'success' : 'neutral'} className="uppercase text-[9px] font-black px-2.5 h-6">
                {task.status.replace('_', ' ')}
              </Badge>
            )}
            <button onClick={onClose} className="p-2 hover:bg-white/10 rounded-xl transition-colors">
              <X size={18} />
            </button>
          </div>
        </div>

        {loading ? (
          <div className="flex-1 flex items-center justify-center py-20">
            <Loader2 className="w-8 h-8 text-blue-600 animate-spin" />
          </div>
        ) : (
          <div className="flex flex-1 overflow-hidden min-h-0">

            {/* ── Left panel: Review Inbox + Work Items ── */}
            <div className="w-64 border-r border-slate-100 overflow-y-auto flex-shrink-0 flex flex-col">

              {/* Review Inbox section */}
              {totalPending > 0 && (
                <div className="bg-amber-50 border-b border-amber-100 p-3 space-y-1.5">
                  <p className="text-[9px] font-black text-amber-600 uppercase tracking-widest flex items-center gap-1.5 mb-2">
                    <AlertCircle size={9} /> Needs Your Review
                  </p>
                  {pendingItems.map((req: any) => {
                    const reqSubtask = req.subtask_id != null
                      ? allSubtasks.find((s: any) => s.id === req.subtask_id)
                      : null;
                    const itemLabel = reqSubtask ? reqSubtask.title : task?.title;
                    const isActive = req.subtask_id == null
                      ? activeSubtaskId === null
                      : activeSubtaskId === req.subtask_id;
                    return (
                      <button
                        key={req.id}
                        onClick={() => setActiveSubtaskId(req.subtask_id ?? null)}
                        className={cn(
                          "w-full text-left p-2.5 rounded-xl border-2 transition-all",
                          isActive
                            ? "bg-white border-amber-400 shadow-sm"
                            : "bg-amber-50 border-amber-200 hover:bg-white hover:border-amber-300"
                        )}
                      >
                        <div className="flex items-start gap-2">
                          <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse flex-shrink-0 mt-1.5" />
                          <div className="min-w-0">
                            <p className="text-[10px] font-black text-amber-800 truncate">{itemLabel}</p>
                            <p className="text-[9px] text-amber-600 font-bold mt-0.5">
                              from {req.submitted_by_name || 'Employee'} · {new Date(req.created_at).toLocaleDateString()}
                            </p>
                          </div>
                        </div>
                      </button>
                    );
                  })}
                </div>
              )}

              {/* Work items list */}
              <div className="flex-1 p-3 space-y-1">
                <div className="flex items-center justify-between mb-2 px-1">
                  <p className="text-[9px] font-black text-slate-400 uppercase tracking-widest">All Work Items</p>
                  {canManageMilestones() && (
                    <button
                      onClick={() => setShowMilestoneCreate((v) => !v)}
                      className="p-1 rounded-lg hover:bg-slate-100 transition-colors text-slate-400 hover:text-blue-600"
                    >
                      <Plus size={13} />
                    </button>
                  )}
                </div>

                {showMilestoneCreate && canManageMilestones() && (
                  <div className="p-2.5 bg-white rounded-xl border border-slate-200 space-y-2 mb-2">
                    <input
                      type="text"
                      value={newMilestoneTitle}
                      onChange={(e) => setNewMilestoneTitle(e.target.value)}
                      placeholder="Subtask title"
                      className="w-full h-8 bg-slate-50 border border-slate-200 rounded-lg px-3 text-xs font-bold focus:outline-none"
                    />
                    <Button onClick={handleCreateMilestone} disabled={creatingMilestone || !newMilestoneTitle.trim()} className="w-full h-7 rounded-lg font-black text-[10px] uppercase tracking-widest">
                      {creatingMilestone ? <Loader2 size={11} className="animate-spin" /> : 'Add Subtask'}
                    </Button>
                  </div>
                )}

                {/* Main task row */}
                {(() => {
                  const isActive = activeSubtaskId === null;
                  const hasPending = !!pendingByItem['main'];
                  const isMe = Number(task?.assignee_id) === Number(me?.id);
                  return (
                    <div
                      onClick={() => setActiveSubtaskId(null)}
                      className={cn(
                        "p-2.5 rounded-xl cursor-pointer transition-all border-2",
                        isActive ? "bg-white border-blue-500 shadow-sm" : "border-transparent hover:bg-slate-50 hover:border-slate-200"
                      )}
                    >
                      <div className="flex items-center gap-2">
                        <div className="w-6 h-6 rounded-lg bg-slate-200 text-slate-600 flex items-center justify-center text-[9px] font-black flex-shrink-0">
                          T
                        </div>
                        <div className="min-w-0 flex-1">
                          <p className={cn("text-[11px] font-black truncate", isActive ? "text-blue-600" : "text-slate-700")}>{task?.title || '...'}</p>
                          <p className="text-[9px] font-bold text-slate-400">
                            {isMe ? '(You)' : task?.assignee_id ? 'Assigned to other' : 'Unassigned'} · Main
                          </p>
                        </div>
                        {hasPending && <span className="w-2 h-2 rounded-full bg-amber-400 animate-pulse flex-shrink-0" />}
                      </div>
                    </div>
                  );
                })()}

                {/* Subtask rows */}
                {allSubtasks.length > 0 && (
                  <>
                    <div className="h-px bg-slate-100 my-1" />
                    {allSubtasks.map((st: any, idx: number) => {
                      const isActive = activeSubtaskId === st.id;
                      const hasPending = !!pendingByItem[`st:${st.id}`];
                      const isMe = Number(st.assignee_id) === Number(me?.id);
                      const avatarClass = avatarColors[idx % avatarColors.length];
                      const initials = (st.title || '?').substring(0, 1).toUpperCase();
                      return (
                        <div
                          key={st.id}
                          onClick={() => setActiveSubtaskId(st.id)}
                          className={cn(
                            "p-2.5 rounded-xl cursor-pointer transition-all border-2",
                            isActive ? "bg-white border-blue-500 shadow-sm" : "border-transparent hover:bg-slate-50 hover:border-slate-200"
                          )}
                        >
                          <div className="flex items-center gap-2">
                            <div
                              onClick={(e) => { e.stopPropagation(); toggleSubtask(st.id, st.is_completed); }}
                              className={cn("w-6 h-6 rounded-lg flex items-center justify-center cursor-pointer hover:scale-110 transition-transform flex-shrink-0 text-[9px] font-black", st.is_completed ? "bg-green-100 text-green-600" : avatarClass)}
                            >
                              {st.is_completed ? <CheckCircle2 size={11} /> : initials}
                            </div>
                            <div className="min-w-0 flex-1">
                              <p className={cn("text-[11px] font-black truncate", isActive ? "text-blue-600" : st.is_completed ? "text-slate-400 line-through" : "text-slate-700")}>{st.title}</p>
                              <p className={cn("text-[9px] font-bold", isMe ? "text-blue-500" : "text-slate-400")}>
                                {isMe ? '(You)' : st.assignee_id ? 'Employee' : 'Unassigned'}
                                {st.estimated_hours != null ? ` · ${st.estimated_hours}h` : ''}
                              </p>
                            </div>
                            {hasPending && <span className="w-2 h-2 rounded-full bg-amber-400 animate-pulse flex-shrink-0" />}
                          </div>
                        </div>
                      );
                    })}
                  </>
                )}
              </div>
            </div>

            {/* ── Right panel ── */}
            <div className="flex-1 flex flex-col overflow-hidden">
              <div className="flex-1 overflow-y-auto">

                {/* Zone A: Review (amber tinted when pending, clean when not) */}
                <div className={cn("p-5 border-b-2", activePending ? "bg-amber-50 border-amber-100" : "bg-slate-50/40 border-slate-100")}>
                  {activePending ? (
                    <div className="space-y-4">
                      {/* Who submitted + what item */}
                      <div className="flex items-start gap-3">
                        <div className="w-9 h-9 rounded-xl bg-amber-100 text-amber-700 flex items-center justify-center text-[10px] font-black flex-shrink-0">
                          {(activePending.submitted_by_name || 'E').substring(0, 2).toUpperCase()}
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 flex-wrap">
                            <p className="text-sm font-black text-amber-900">{activePending.submitted_by_name || 'Employee'}</p>
                            <span className="text-[9px] font-black bg-amber-200 text-amber-800 px-2 py-0.5 rounded-full uppercase tracking-widest">Awaiting Review</span>
                          </div>
                          <p className="text-[10px] font-bold text-amber-600 mt-0.5">
                            submitted {new Date(activePending.created_at).toLocaleDateString()} for{' '}
                            <span className="font-black">{activeSt ? activeSt.title : task?.title}</span>
                          </p>
                        </div>
                      </div>

                      {/* Employee's notes */}
                      <div className="bg-white rounded-xl border border-amber-200 p-4">
                        <p className="text-[9px] font-black uppercase tracking-widest text-amber-500 mb-2">Employee Notes</p>
                        <p className="text-sm text-slate-700 leading-relaxed">{activePending.notes}</p>
                      </div>

                      {/* Attached docs */}
                      {activePending.documents?.length > 0 && (
                        <div className="flex flex-wrap gap-2">
                          {activePending.documents.map((d: any) => (
                            <span key={d.id} className="flex items-center gap-1.5 text-[10px] font-black text-slate-600 bg-white border border-amber-200 rounded-lg px-3 py-1.5">
                              <Paperclip size={10} className="text-amber-500" /> {d.file_name}
                            </span>
                          ))}
                        </div>
                      )}

                      {/* PM feedback + actions */}
                      <div className="space-y-2">
                        <p className="text-[9px] font-black uppercase tracking-widest text-slate-500">Your Decision & Feedback</p>
                        <textarea
                          value={reviewNotes}
                          onChange={(e) => setReviewNotes(e.target.value)}
                          placeholder="Write feedback for the employee — they'll see this..."
                          rows={3}
                          className="w-full bg-white border border-slate-200 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 resize-none"
                        />
                        <div className="flex gap-2 pt-1">
                          <button
                            onClick={() => handleReview(activePending.id, 'approve')}
                            disabled={reviewing || !reviewNotes.trim()}
                            className="flex-1 flex items-center justify-center gap-2 h-10 bg-green-600 hover:bg-green-700 text-white rounded-xl font-black text-[10px] uppercase tracking-widest disabled:opacity-40 transition-colors"
                          >
                            {reviewing ? <Loader2 size={12} className="animate-spin" /> : <ThumbsUp size={12} />} Approve
                          </button>
                          <button
                            onClick={() => handleReview(activePending.id, 'on_hold')}
                            disabled={reviewing || !reviewNotes.trim()}
                            className="flex-1 flex items-center justify-center gap-2 h-10 bg-amber-500 hover:bg-amber-600 text-white rounded-xl font-black text-[10px] uppercase tracking-widest disabled:opacity-40 transition-colors"
                          >
                            {reviewing ? <Loader2 size={12} className="animate-spin" /> : <PauseCircle size={12} />} On Hold
                          </button>
                          <button
                            onClick={() => handleReview(activePending.id, 'reject')}
                            disabled={reviewing || !reviewNotes.trim()}
                            className="flex-1 flex items-center justify-center gap-2 h-10 bg-red-500 hover:bg-red-600 text-white rounded-xl font-black text-[10px] uppercase tracking-widest disabled:opacity-40 transition-colors"
                          >
                            {reviewing ? <Loader2 size={12} className="animate-spin" /> : <ThumbsDown size={12} />} Reject
                          </button>
                        </div>
                      </div>
                    </div>
                  ) : (
                    <div className="flex items-center gap-3 py-2">
                      <CheckCircle2 size={16} className="text-slate-300 flex-shrink-0" />
                      <div>
                        <p className="text-xs font-black text-slate-400">No pending submission</p>
                        <p className="text-[10px] text-slate-300 font-bold">
                          {isOwnedByMe ? 'This is your own work item.' : 'Employee has not submitted this item yet.'}
                        </p>
                      </div>
                    </div>
                  )}
                </div>

                {/* Zone B: Task details */}
                <div className="p-5 space-y-5">

                  {/* Context: who this item belongs to */}
                  <div className="flex items-center gap-2 text-[10px] font-bold text-slate-400">
                    {activeSt ? (
                      <>
                        <span className="font-black text-slate-600">{activeSt.title}</span>
                        <span>·</span>
                        <span className={Number(activeSt.assignee_id) === Number(me?.id) ? "text-blue-500 font-black" : ""}>
                          {Number(activeSt.assignee_id) === Number(me?.id) ? 'Assigned to you' : 'Employee subtask'}
                        </span>
                        {activeSt.estimated_hours != null && <><span>·</span><span>{activeSt.estimated_hours}h estimated</span></>}
                      </>
                    ) : (
                      <>
                        <span className="font-black text-slate-600">Main Task</span>
                        <span>·</span>
                        <span className={Number(task?.assignee_id) === Number(me?.id) ? "text-blue-500 font-black" : ""}>
                          {Number(task?.assignee_id) === Number(me?.id) ? 'Assigned to you' : task?.assignee_id ? 'Employee task' : 'Unassigned'}
                        </span>
                        {task?.estimated_hours != null && <><span>·</span><span>{task.estimated_hours}h estimated</span></>}
                      </>
                    )}
                  </div>

                  {/* Description — main task only */}
                  {!activeSubtaskId && task?.description && (
                    <p className="text-sm text-slate-600 leading-relaxed bg-slate-50 p-4 rounded-xl border border-slate-100">
                      {task.description}
                    </p>
                  )}

                  {/* Time logged */}
                  {activeTs && (
                    <div className="flex items-center gap-5 bg-slate-50 rounded-xl p-4 border border-slate-100">
                      <div className="flex items-center gap-2">
                        <Clock size={13} className="text-blue-500" />
                        <div>
                          <p className="text-[9px] font-black text-slate-400 uppercase tracking-widest">Logged</p>
                          <p className="text-base font-black text-blue-600">{(activeTs.actual_hours ?? 0).toFixed(1)}h</p>
                        </div>
                      </div>
                      {activeTs.estimated_hours != null && (
                        <>
                          <div className="h-7 w-px bg-slate-200" />
                          <div>
                            <p className="text-[9px] font-black text-slate-400 uppercase tracking-widest">Estimated</p>
                            <p className="text-base font-black text-slate-700">{activeTs.estimated_hours}h</p>
                          </div>
                          <div className="flex-1">
                            <div className="w-full h-1.5 bg-slate-200 rounded-full overflow-hidden">
                              <div
                                className={cn("h-full rounded-full", (activeTs.actual_hours / activeTs.estimated_hours) > 1 ? "bg-red-400" : "bg-blue-500")}
                                style={{ width: `${Math.min((activeTs.actual_hours / activeTs.estimated_hours) * 100, 100)}%` }}
                              />
                            </div>
                            <p className="text-[9px] font-bold text-slate-400 text-right mt-0.5">
                              {Math.round((activeTs.actual_hours / activeTs.estimated_hours) * 100)}%
                            </p>
                          </div>
                        </>
                      )}
                    </div>
                  )}

                  {/* Approval history */}
                  {activeHistory.length > 0 && (
                    <div className="space-y-2">
                      <p className="text-[9px] font-black text-slate-400 uppercase tracking-widest flex items-center gap-1.5">
                        <History size={9} /> Approval History
                      </p>
                      {activeHistory.map((req: any) => (
                        <div key={req.id} className={cn("p-3 rounded-xl border-l-4 bg-slate-50 text-xs", borderColors[req.status] ?? 'border-slate-300')}>
                          <div className="flex items-center justify-between mb-1.5">
                            <span className={cn("text-[9px] font-black uppercase tracking-widest px-2 py-0.5 rounded-full border", statusColors[req.status])}>
                              {req.status.replace('_', ' ')}
                            </span>
                            <span className="text-[10px] font-bold text-slate-400">{new Date(req.created_at).toLocaleDateString()}</span>
                          </div>
                          <p className="font-medium text-slate-600 mb-1">{req.notes}</p>
                          {req.reviewer_notes && (
                            <p className="text-[10px] font-bold text-slate-500 italic border-t border-slate-200 pt-1.5 mt-1.5">
                              Your feedback: {req.reviewer_notes}
                            </p>
                          )}
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Comments */}
                  <div className="space-y-3">
                    <p className="text-[9px] font-black text-slate-400 uppercase tracking-widest">Comments</p>
                    {visibleComments.length > 0 ? visibleComments.map((c: any, i: number) => (
                      <div key={i} className="flex gap-3">
                        <div className="w-8 h-8 rounded-xl bg-blue-100 text-blue-600 flex items-center justify-center text-[10px] font-black flex-shrink-0">
                          {c.user?.full_name?.substring(0, 2) || '??'}
                        </div>
                        <div className="flex-1 bg-slate-50 p-3 rounded-xl">
                          <div className="flex items-center justify-between mb-1">
                            <span className="text-xs font-black text-slate-800">{c.user?.full_name}</span>
                            <span className="text-[10px] font-bold text-slate-400">
                              {new Date(c.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                            </span>
                          </div>
                          <p className="text-xs text-slate-600">{c.content}</p>
                        </div>
                      </div>
                    )) : (
                      <p className="text-xs text-slate-400 text-center py-3">No comments for this work item.</p>
                    )}
                  </div>
                </div>
              </div>

              {/* Comment input */}
              <div className="p-4 border-t border-slate-100 bg-white flex items-center gap-3 flex-shrink-0">
                <input
                  type="text"
                  value={commentText}
                  onChange={(e) => setCommentText(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleAddComment()}
                  placeholder="Add a comment..."
                  className="flex-1 h-10 bg-slate-50 border border-slate-200 rounded-xl px-4 text-sm focus:outline-none focus:ring-2 focus:ring-blue-600/10"
                />
                <Button disabled={postingComment || !commentText.trim()} onClick={handleAddComment} className="h-10 px-5 font-black text-[10px] uppercase tracking-widest flex items-center gap-2">
                  {postingComment ? <Loader2 size={13} className="animate-spin" /> : <Send size={13} />} Post
                </Button>
              </div>
            </div>

          </div>
        )}
      </div>
    );
  };

  return (
    <AnimatePresence>
      {isOpen && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
            className="absolute inset-0 bg-[#0F172A]/60 backdrop-blur-sm"
          />
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 20 }}
            className="relative z-10 w-full flex justify-center"
          >
            {loading && !task ? (
              <div className="bg-white rounded-3xl shadow-2xl p-16 flex items-center justify-center">
                <Loader2 className="w-8 h-8 text-blue-600 animate-spin" />
              </div>
            ) : isEmployeeView() ? renderEmployeeView() : renderPMView()}
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
};
