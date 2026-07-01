import React, { useState, useEffect } from 'react';
import {
  UserPlus,
  Search,
  CheckCircle2,
  Clock,
  ArrowRight,
  Mail,
  FileText,
  ShieldCheck,
  Plus,
  Laptop,
  Building2,
  Calendar,
  Zap,
  CheckCircle,
  AlertCircle,
  Undo2,
  UserCheck,
  Loader2,
  X
} from 'lucide-react';
import { Card, Button, Badge, cn } from './ui-elements';
import { toast } from 'sonner';
import { onboardingApi } from '../api/onboarding';

export const OnboardingHR = () => {
  const [processes, setProcesses] = useState<any[]>([]);
  const [selectedProcess, setSelectedProcess] = useState<any>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [showInitiateDialog, setShowInitiateDialog] = useState(false);
  const [readyApplicants, setReadyApplicants] = useState<any[]>([]);
  const [loadingApplicants, setLoadingApplicants] = useState(false);
  const [initiating, setInitiating] = useState<number | null>(null);

  useEffect(() => {
    fetchOnboarding();
  }, []);

  const fetchOnboarding = async () => {
    try {
      setIsLoading(true);
      const res = await onboardingApi.getProcesses();
      setProcesses(res.data);
      if (res.data.length > 0 && !selectedProcess) {
        setSelectedProcess(res.data[0]);
      }
    } catch (error) {
      toast.error("Failed to load onboarding pipeline");
    } finally {
      setIsLoading(false);
    }
  };

  const openInitiateDialog = async () => {
    setShowInitiateDialog(true);
    setLoadingApplicants(true);
    try {
      const res = await onboardingApi.getReadyApplicants();
      setReadyApplicants(res.data);
    } catch {
      toast.error("Failed to load eligible applicants");
    } finally {
      setLoadingApplicants(false);
    }
  };

  const handleInitiate = async (applicantId: number) => {
    setInitiating(applicantId);
    try {
      await onboardingApi.initiateOnboarding(applicantId);
      toast.success("Onboarding process initiated");
      setShowInitiateDialog(false);
      fetchOnboarding();
    } catch {
      toast.error("Failed to initiate onboarding");
    } finally {
      setInitiating(null);
    }
  };

  const handleTaskComplete = async (processId: number, taskId: number, taskTitle: string) => {
    try {
      await onboardingApi.completeTask(processId, taskId);
      toast.success(`Task Validated`, {
        description: `"${taskTitle}" has been archived and verified.`
      });
      fetchOnboarding();
    } catch (error) {
      toast.error("Process Update Failed");
    }
  };

  const currentSteps = selectedProcess?.tasks || [];

  return (
    <div className="p-8 space-y-8 max-w-[1600px] mx-auto animate-in fade-in duration-500 pb-20">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
        <div>
          <h2 className="text-3xl font-black text-[#0F172A] tracking-tighter uppercase">Enterprise Induction</h2>
          <p className="text-[#64748B] font-bold uppercase tracking-widest text-[10px] mt-1">Strategic Asset Onboarding & Systems Activation Lifecycle</p>
        </div>
        <div className="flex gap-3">
           <Button className="font-black h-12 px-6 uppercase text-[10px] tracking-widest bg-blue-600 shadow-lg shadow-blue-600/20" onClick={openInitiateDialog}>
              <Plus className="w-4 h-4 mr-2" /> Initiate Onboarding
           </Button>
        </div>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-20">
          <div className="flex flex-col items-center gap-4">
            <div className="w-10 h-10 border-4 border-blue-600 border-t-transparent rounded-full animate-spin" />
            <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Loading Onboarding Pipeline...</p>
          </div>
        </div>
      ) : (
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-8">
        {/* Left Sidebar: Active Pipeline */}
        <div className="lg:col-span-1 space-y-4">
           <Card className="p-4 border-slate-200 bg-slate-50 border-dashed border-2">
              <p className="text-[9px] font-black text-slate-400 uppercase tracking-widest">Active Joiners: {processes.length}</p>
           </Card>
           {processes.map((proc) => (
             <Card 
               key={proc.id} 
               onClick={() => setSelectedProcess(proc)}
               className={cn(
                 "p-5 border-slate-200 cursor-pointer hover:shadow-md transition-all group",
                 selectedProcess?.id === proc.id ? "border-blue-600 bg-blue-50/30 ring-1 ring-blue-600/10" : "bg-white"
               )}
             >
                <div className="flex items-center gap-4">
                   <div className={cn(
                     "w-10 h-10 rounded-xl flex items-center justify-center font-black text-xs shadow-sm border transition-colors",
                     selectedProcess?.id === proc.id ? "bg-blue-600 text-white border-blue-600" : "bg-slate-50 text-slate-400 border-slate-100"
                   )}>
                      {proc.applicant_name?.charAt(0)}
                   </div>
                   <div className="flex-1 overflow-hidden">
                      <p className="text-sm font-black text-[#0F172A] truncate group-hover:text-blue-600 transition-colors">{proc.applicant_name}</p>
                      <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest truncate">{proc.id} • {proc.department}</p>
                   </div>
                   <div className="text-right">
                      <p className="text-[9px] font-black text-blue-600 uppercase">Step {proc.current_step}/6</p>
                      <div className="flex items-center gap-1 mt-1">
                        <div className="w-8 h-1 bg-slate-200 rounded-full overflow-hidden">
                           <div className="h-full bg-blue-600" style={{ width: `${(proc.current_step/6)*100}%` }} />
                        </div>
                      </div>
                   </div>
                </div>
             </Card>
           ))}
        </div>

        {/* Central Component: 6-Step Workflow */}
        <div className="lg:col-span-3">
           {selectedProcess ? (
             <div className="space-y-8 animate-in slide-in-from-right duration-500">
                <Card className="p-8 border-slate-200 shadow-sm bg-white overflow-hidden relative">
                   <div className="flex flex-col md:flex-row md:items-center justify-between gap-6 border-b border-slate-100 pb-8 mb-8">
                      <div>
                         <div className="flex items-center gap-3">
                           <h3 className="text-2xl font-black text-[#0F172A] tracking-tight uppercase">{selectedProcess.applicant_name}</h3>
                           <Badge variant="info" className="text-[10px] font-black uppercase tracking-widest px-4">NJ-LIFECYCLE-LOG</Badge>
                         </div>
                         <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mt-1">{selectedProcess.role_title} • {selectedProcess.department}</p>
                      </div>
                      <div className="flex flex-col md:items-end gap-3">
                         <div className="flex items-center gap-2">
                           <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Onboarding Health</p>
                           <Badge variant={selectedProcess.current_step === 6 ? 'success' : 'warning'} className="text-[10px] font-black uppercase px-4">STATUS: {selectedProcess.status}</Badge>
                         </div>
                         <div className="w-full md:w-64 h-2 bg-slate-100 rounded-full overflow-hidden border border-slate-200 p-[1px]">
                            <div className="h-full bg-blue-600 rounded-full shadow-[0_0_10px_rgba(37,99,235,0.3)] transition-all duration-1000" style={{ width: `${(selectedProcess.current_step/6)*100}%` }} />
                         </div>
                      </div>
                   </div>

                   <div className="space-y-4">
                      {selectedProcess.tasks.map((task: any) => {
                         const isCompleted = task.status === 'completed';
                         const isCurrent = task.status === 'pending' && task.step_number === selectedProcess.current_step;
                         const isPending = task.status === 'pending' && task.step_number > selectedProcess.current_step;

                         return (
                           <div key={task.id} className={cn(
                             "p-6 rounded-2xl border transition-all flex flex-col md:flex-row md:items-center gap-6",
                             isCompleted ? "bg-blue-50/30 border-blue-100" : isCurrent ? "bg-white border-blue-600 shadow-xl ring-4 ring-blue-600/5" : "bg-slate-50 border-slate-100 opacity-60"
                           )}>
                              <div className={cn(
                                "w-12 h-12 rounded-xl flex items-center justify-center shadow-sm",
                                isCompleted ? "bg-green-500 text-white" : isCurrent ? "bg-blue-600 text-white" : "bg-white text-slate-300"
                              )}>
                                 {isCompleted ? <CheckCircle2 size={24} /> : <Zap size={24} />}
                              </div>
                              <div className="flex-1">
                                 <div className="flex items-center gap-3">
                                    <h5 className={cn("text-sm font-black uppercase tracking-tight", isCompleted ? "text-green-700" : isCurrent ? "text-blue-700" : "text-slate-400")}>Step {task.step_number}: {task.title}</h5>
                                    <Badge variant="neutral" className="text-[8px] uppercase tracking-widest bg-slate-200">{task.actor_role}</Badge>
                                 </div>
                                 <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mt-1">{task.description}</p>
                              </div>
                              
                              <div className="flex gap-2">
                                 {isCurrent && (
                                   <>
                                     <Button variant="outline" size="sm" className="h-10 px-4 font-black uppercase text-[9px] tracking-widest border-slate-200 hover:bg-slate-50">Reject / Remark</Button>
                                     <Button size="sm" className="h-10 px-6 font-black uppercase text-[9px] tracking-widest bg-blue-600 shadow-lg shadow-blue-600/10" onClick={() => handleTaskComplete(selectedProcess.id, task.id, task.title)}>Verify & Move</Button>
                                   </>
                                 )}
                                 {isCompleted && (
                                   <div className="flex flex-col items-end">
                                      <p className="text-[8px] font-black text-slate-400 uppercase">Validated</p>
                                      <p className="text-[10px] font-black text-green-600 uppercase">Completed</p>
                                   </div>
                                 )}
                              </div>
                           </div>
                         );
                      })}
                   </div>
                </Card>
             </div>
           ) : (
             <Card className="h-[600px] border-2 border-dashed border-slate-200 flex flex-col items-center justify-center text-center p-12 bg-slate-50/50">
                <div className="w-20 h-20 bg-white rounded-3xl shadow-sm border border-slate-100 flex items-center justify-center mb-6 text-slate-300 animate-pulse">
                   <Zap size={40} />
                </div>
                <h4 className="text-xl font-black text-slate-400 tracking-tight uppercase">Select Asset to View Workflow</h4>
                <p className="text-[11px] font-bold text-slate-400 uppercase tracking-widest mt-2 max-w-sm">Organizational onboarding lifecycle tracking. Every step requires verification and creates an audit trail.</p>
             </Card>
           )}
        </div>
      </div>
      )}
      {/* Initiate Onboarding Dialog */}
      {showInitiateDialog && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-6" onClick={() => setShowInitiateDialog(false)}>
          <div className="bg-white rounded-3xl shadow-2xl w-full max-w-lg overflow-hidden" onClick={e => e.stopPropagation()}>
            <div className="p-8 border-b border-slate-100 flex items-center justify-between">
              <div>
                <h3 className="text-lg font-black text-[#0F172A] uppercase tracking-tight">Initiate Onboarding</h3>
                <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mt-1">Select a hired applicant to begin the onboarding lifecycle</p>
              </div>
              <button onClick={() => setShowInitiateDialog(false)} className="w-8 h-8 flex items-center justify-center rounded-xl hover:bg-slate-100 text-slate-400">
                <X size={16} />
              </button>
            </div>
            <div className="p-6 max-h-96 overflow-y-auto">
              {loadingApplicants ? (
                <div className="flex justify-center py-12">
                  <Loader2 size={28} className="text-blue-600 animate-spin" />
                </div>
              ) : readyApplicants.length === 0 ? (
                <div className="text-center py-12">
                  <UserCheck size={32} className="text-slate-200 mx-auto mb-3" />
                  <p className="text-sm font-black text-slate-400 uppercase tracking-widest">No eligible applicants</p>
                  <p className="text-[10px] font-bold text-slate-300 mt-1">All hired applicants already have onboarding processes</p>
                </div>
              ) : (
                <div className="space-y-3">
                  {readyApplicants.map((a: any) => (
                    <div key={a.id} className="flex items-center gap-4 p-5 rounded-2xl border border-slate-100 hover:border-blue-200 hover:bg-blue-50/30 transition-all group">
                      <div className="w-10 h-10 rounded-xl bg-blue-50 text-blue-600 flex items-center justify-center font-black text-sm">
                        {a.full_name?.charAt(0)}
                      </div>
                      <div className="flex-1">
                        <p className="text-sm font-black text-[#0F172A]">{a.full_name}</p>
                        <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">{a.role_title} · {a.department}</p>
                      </div>
                      <Button
                        size="sm"
                        className="h-9 px-5 font-black uppercase text-[9px] tracking-widest bg-blue-600 opacity-0 group-hover:opacity-100 transition-all"
                        onClick={() => handleInitiate(a.id)}
                        disabled={initiating === a.id}
                      >
                        {initiating === a.id ? <Loader2 size={12} className="animate-spin" /> : 'Start'}
                      </Button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export const PolicyCenter = () => null; // Removed as per instructions
