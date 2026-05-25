import React, { useState, useMemo, useEffect } from 'react';
import { 
  Briefcase, 
  Plus, 
  Search, 
  Filter, 
  ChevronRight, 
  Users, 
  Calendar, 
  CheckSquare,
  DollarSign, 
  TrendingUp, 
  AlertTriangle,
  FileText,
  Clock,
  ArrowLeft,
  CheckCircle2,
  MoreVertical,
  X,
  Edit,
  Trash2,
  CheckCircle,
  LayoutGrid,
  List,
  ChevronDown,
  Target,
  ArrowUpRight,
  ShieldAlert,
  HelpCircle,
  Upload,
  Download,
  Paperclip,
  Loader2,
} from 'lucide-react';
import { Card, Button, Badge, Input, cn } from './ui-elements';
import { toast } from 'sonner@2.0.3';
import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';
import { UserRole } from '../types/erp';

// --- Types ---

interface Subtask {
  id: string;
  title: string;
  completed: boolean;
  estimatedHours: number;
  assigned: string;
  parentSubtaskId?: string | null;
}

interface Task {
  id: string;
  projectId: string;
  title: string;
  priority: 'Critical' | 'High' | 'Medium' | 'Low';
  status: 'To Do' | 'In Progress' | 'Review' | 'Done';
  assigned: string;
  estimatedHours: number;
  subtasks: Subtask[];
}

interface Milestone {
  id: number;
  project_id: number;
  title: string;
  description: string;
  due_date: string;
  status: 'pending' | 'in-progress' | 'completed' | 'delayed';
}

interface CostBaseline {
  id: number;
  amount: number;
  description: string;
  is_active: boolean;
  created_at: string;
}

interface Project {
  id: string;
  name: string;
  client: string;
  status: 'active' | 'pipeline' | 'on-hold' | 'completed' | 'approval-pending';
  manager: string;
  budget: number;
  budgetHours?: number | null;
  actualCost: number;
  start: string;
  end: string;
  parentProjectId?: string | null;
}

// --- Main Component ---

export const ProjectsView = ({ userRole = 'employee' }: { userRole?: UserRole }) => {
  const [projects, setProjects] = useState<Project[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [milestones, setMilestones] = useState<Milestone[]>([]);
  const [activeBaseline, setActiveBaseline] = useState<CostBaseline | null>(null);
  const [projectUtilization, setProjectUtilization] = useState<any>(null);
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showBulkUploadModal, setShowBulkUploadModal] = useState(false);
  const [showBulkImportWithTasksModal, setShowBulkImportWithTasksModal] = useState(false);
  const [clientOptions, setClientOptions] = useState<Array<{ id: number; name: string }>>([]);
  const [clientSearchInput, setClientSearchInput] = useState('');
  const [clientSearching, setClientSearching] = useState(false);
  const [clientTotal, setClientTotal] = useState<number>(0);
  const [selectedClientId, setSelectedClientId] = useState<string>('');
  const [selectedClientName, setSelectedClientName] = useState<string>('');
  const [quickAddOpen, setQuickAddOpen] = useState(false);
  const [quickAddSubmitting, setQuickAddSubmitting] = useState(false);
  const [quickAddName, setQuickAddName] = useState('');
  const [quickAddDomain, setQuickAddDomain] = useState('');
  const [quickAddIndustry, setQuickAddIndustry] = useState('');
  const [activeTab, setActiveTab] = useState<'overview' | 'tasks' | 'team' | 'milestones' | 'costing'>('overview');
  const [isLoading, setIsLoading] = useState(false);

  // Modals
  const [showMilestoneModal, setShowMilestoneModal] = useState(false);
  const [showCostChangeModal, setShowCostChangeModal] = useState(false);

  const canCreateProject = userRole === 'pm' || userRole === 'super admin' || userRole === 'coo';
  const canBulkUploadProjects = userRole === 'super admin' || userRole === 'admin';
  const canBulkImportWithTasks = userRole === 'super admin' || userRole === 'admin' || userRole === 'coo';

  useEffect(() => {
    fetchProjects();
  }, []);

  useEffect(() => {
    if (selectedProjectId) {
      fetchProjectDetails(selectedProjectId);
    }
  }, [selectedProjectId]);

  const fetchProjects = async () => {
    try {
      setIsLoading(true);
      const response = await client.get(ENDPOINTS.PROJECTS.LIST);
      // Map API response to Component Type
      const mappedProjects = response.data.map((p: any) => ({
        id: p.id.toString(),
        name: p.name,
        client: p.client_name || 'Internal',
        status: p.status.toLowerCase(),
        manager: p.manager_name || 'Assignee Pending',
        budget: p.budget || 0,
        budgetHours: p.budget_hours ?? null,
        actualCost: p.actual_cost || 0,
        start: p.start_date,
        end: p.end_date,
        parentProjectId: p.parent_project_id ? p.parent_project_id.toString() : null,
      }));
      setProjects(mappedProjects);
    } catch (error) {
      toast.error("Failed to fetch project portfolio");
    } finally {
      setIsLoading(false);
    }
  };

  const fetchProjectDetails = async (id: string) => {
    try {
      setIsLoading(true);
      const results = await Promise.allSettled([
        client.get(ENDPOINTS.PROJECTS.MILESTONES(id)),
        client.get(ENDPOINTS.PROJECTS.COST_BASELINE(id)),
        client.get(ENDPOINTS.TASKS.BY_PROJECT(id)),
        client.get(ENDPOINTS.PROJECTS.MEMBERS(id)),
        userRole === 'pm' || userRole === 'super admin' || userRole === 'coo'
          ? client.get(ENDPOINTS.TIMESHEET.UTILIZATION_PROJECT(id), {
              params: { range: 'monthly' },
            })
          : Promise.resolve({ data: null } as any),
      ]);

      const [milestoneRes, baselineRes, tasksRes, membersRes, utilRes] = results;

      if (milestoneRes.status === 'fulfilled') {
        setMilestones(milestoneRes.value.data);
      }
      if (baselineRes.status === 'fulfilled') {
        setActiveBaseline(baselineRes.value.data);
      }

      if (utilRes.status === 'fulfilled') {
        setProjectUtilization(utilRes.value.data);
      } else {
        setProjectUtilization(null);
      }

      const members: any[] =
        membersRes.status === 'fulfilled' ? membersRes.value.data || [] : [];
      const memberById = new Map<number, any>();
      members.forEach((m: any) => {
        if (typeof m?.user_id === 'number') memberById.set(m.user_id, m);
      });

      const statusMap: Record<string, Task['status']> = {
        todo: 'To Do',
        in_progress: 'In Progress',
        review: 'Review',
        completed: 'Done',
      };
      const priorityMap: Record<string, Task['priority']> = {
        high: 'High',
        medium: 'Medium',
        low: 'Low',
      };

      const rawTasks: any[] =
        tasksRes.status === 'fulfilled' ? tasksRes.value.data || [] : [];

      const mappedTasks: Task[] = rawTasks.map((t: any) => {
        const taskAssignee = typeof t?.assignee_id === 'number' ? memberById.get(t.assignee_id) : null;
        return {
          id: t?.id?.toString() || `T${Date.now()}`,
          projectId: id,
          title: t?.title || '',
          priority: priorityMap[t?.priority] || 'Medium',
          status: statusMap[t?.status] || 'To Do',
          assigned: taskAssignee?.user_email || '',
          estimatedHours: Number(t?.estimated_hours || 0),
          subtasks: (t?.subtasks || []).map((s: any) => {
            const subAssignee = typeof s?.assignee_id === 'number' ? memberById.get(s.assignee_id) : null;
            return {
              id: s?.id?.toString() || `S${Date.now()}`,
              title: s?.title || '',
              completed: Boolean(s?.is_completed),
              estimatedHours: Number(s?.estimated_hours || 0),
              assigned: subAssignee?.user_email || '',
              parentSubtaskId:
                s?.parent_subtask_id != null
                  ? String(s.parent_subtask_id)
                  : null,
            };
          }),
        };
      });

      setTasks(prev => {
        const others = prev.filter(t => t.projectId !== id);
        return [...others, ...mappedTasks];
      });
    } catch (error) {
      console.error("Failed to fetch project details", error);
      toast.error("Error loading project delivery data");
    } finally {
      setIsLoading(false);
    }
  };

  const activeCount = projects.filter(p => p.status === 'active').length;
  const pipelineCount = projects.filter(p => p.status === 'pipeline').length;
  const completedCount = projects.filter(p => p.status === 'completed').length;
  const overBudgetCount = projects.filter(p => (p.actualCost / p.budget) > 0.9).length;

  const filteredProjects = projects.filter(p => 
    p.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    p.client.toLowerCase().includes(searchQuery.toLowerCase()) ||
    p.manager.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const calculateProjectProgress = (projId: string) => {
    const projectTasks = tasks.filter(t => t.projectId === projId);
    const projectMilestones = milestones.filter(m => m.projectId === projId);
    
    if (projectTasks.length === 0 && projectMilestones.length === 0) return 0;

    let totalWeight = 0;
    let completedWeight = 0;

    // Tasks weight (60%)
    if (projectTasks.length > 0) {
      totalWeight += 60;
      const taskWeights = projectTasks.map(t => {
        if (t.status === 'Done') return 1;
        if (t.status === 'Review') return 0.8;
        if (t.status === 'In Progress') return 0.4;
        return 0;
      });
      const avgTaskProgress = taskWeights.reduce((a, b) => a + b, 0) / projectTasks.length;
      completedWeight += avgTaskProgress * 60;
    }

    // Milestones weight (40%)
    if (projectMilestones.length > 0) {
      totalWeight += 40;
      const completedMilestones = projectMilestones.filter(m => m.status === 'Completed').length;
      const avgMilestoneProgress = completedMilestones / projectMilestones.length;
      completedWeight += avgMilestoneProgress * 40;
    }

    return Math.round((completedWeight / totalWeight) * 100);
  };

  const fetchClientOptions = async (query: string) => {
    try {
      setClientSearching(true);
      const res = await client.get(ENDPOINTS.CLIENTS.PAGE, {
        params: { q: query || undefined, limit: 20, offset: 0 },
      });
      const items = (res.data?.items || []).map((c: any) => ({
        id: Number(c.id),
        name: String(c.name || ''),
      }));
      setClientOptions(items);
      setClientTotal(Number(res.data?.total || 0));
    } catch (error) {
      toast.error('Failed to search clients');
    } finally {
      setClientSearching(false);
    }
  };

  // Debounced client search while the create modal is open.
  useEffect(() => {
    if (!showCreateModal) return;
    const t = setTimeout(() => {
      fetchClientOptions(clientSearchInput.trim());
    }, 250);
    return () => clearTimeout(t);
  }, [clientSearchInput, showCreateModal]);

  const openCreateModal = () => {
    setSelectedClientId('');
    setSelectedClientName('');
    setClientSearchInput('');
    setClientOptions([]);
    setClientTotal(0);
    setShowCreateModal(true);
  };

  const openQuickAdd = () => {
    // Pre-fill the name with whatever the user has typed in the search box.
    setQuickAddName(clientSearchInput.trim());
    setQuickAddDomain('');
    setQuickAddIndustry('');
    setQuickAddOpen(true);
  };

  const submitQuickAdd = async () => {
    const name = quickAddName.trim();
    if (!name) {
      toast.error('Client name is required');
      return;
    }
    setQuickAddSubmitting(true);
    try {
      const res = await client.post(ENDPOINTS.CLIENTS.CREATE, {
        name,
        domain: quickAddDomain.trim() || null,
        industry: quickAddIndustry.trim() || null,
      });
      const newId = Number(res.data?.id);
      setSelectedClientId(String(newId));
      setSelectedClientName(name);
      setClientSearchInput('');
      setQuickAddOpen(false);
      toast.success(`Client "${name}" created`);
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      const msg =
        err?.response?.data?.error?.message ||
        (typeof detail === 'string' ? detail : null) ||
        'Failed to create client';
      toast.error(msg);
    } finally {
      setQuickAddSubmitting(false);
    }
  };

  const handleCreateProject = async (e: React.FormEvent) => {
    e.preventDefault();
    const formData = new FormData(e.target as HTMLFormElement);

    const name = (formData.get('name') as string) || '';
    const clientIdNum = selectedClientId ? Number(selectedClientId) : undefined;
    const budget = Number(formData.get('budget') || 0);
    const budgetHours = Number(formData.get('budget_hours') || 0);
    const end = (formData.get('end') as string) || '';

    if (!clientIdNum) {
      toast.error('Please select a client');
      return;
    }

    try {
      const description = [
        budget ? `Budget: ${budget}` : null,
        budgetHours ? `Hours: ${budgetHours}` : null,
        end ? `Target End: ${end}` : null,
      ].filter(Boolean).join(' | ') || undefined;

      const res = await client.post(ENDPOINTS.PROJECTS.CREATE, {
        name,
        description,
        status: 'active',
        budget: budget || undefined,
        budget_hours: budgetHours || undefined,
        end_date: end || undefined,
        client_id: clientIdNum,
      });

      toast.success('Project Created', { description: `${name} is now active.` });
      setShowCreateModal(false);

      const createdId = (res as any).data?.id;
      await fetchProjects();
      if (createdId) setSelectedProjectId(createdId.toString());
    } catch (error: any) {
      const detail = error?.response?.data?.detail;
      const msg = typeof detail === 'string' ? detail
        : error?.response?.data?.error?.message || 'Project creation failed';
      toast.error(msg);
    }
  };

  const selectedProject = projects.find(p => p.id === selectedProjectId);

  if (selectedProjectId && selectedProject) {
    const projectTasks = tasks.filter(t => t.projectId === selectedProjectId);
    const projectMilestones = milestones.filter(m => String(m.project_id) === String(selectedProjectId));
    const progress = calculateProjectProgress(selectedProjectId);

    return (
      <ProjectDetail 
        project={{...selectedProject, progress}} 
        tasks={projectTasks}
        milestones={projectMilestones}
        projectUtilization={projectUtilization}
        userRole={userRole}
        onBack={() => setSelectedProjectId(null)} 
        onUpdateProject={(p) => setProjects(prev => prev.map(proj => proj.id === p.id ? p : proj))}
        onUpdateTasks={(updatedTasks) => {
           // This is tricky because projectTasks is a subset. 
           // We need to merge updatedTasks back into the main tasks array.
           setTasks(prev => {
             const others = prev.filter(t => t.projectId !== selectedProjectId);
             return [...others, ...updatedTasks];
           });
        }}
        onUpdateMilestones={(updatedMilestones) => {
           setMilestones(prev => {
             const others = prev.filter(m => String(m.project_id) !== String(selectedProjectId));
             return [...others, ...updatedMilestones];
           });
        }}
      />
    );
  }

  return (
    <div className="p-8 space-y-6 max-w-[1400px] mx-auto pb-20">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold text-[#0F172A]">Project Portfolio</h2>
          <p className="text-[#64748B]">Manage all active, pipeline, and completed projects.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {canBulkUploadProjects && (
            <Button
              variant="outline"
              className="flex items-center"
              onClick={() => setShowBulkUploadModal(true)}
            >
              <Upload className="w-4 h-4 mr-2" /> Bulk Upload
            </Button>
          )}
          {canBulkImportWithTasks && (
            <Button
              variant="outline"
              className="flex items-center border-blue-200 text-blue-700"
              onClick={() => setShowBulkImportWithTasksModal(true)}
            >
              <Upload className="w-4 h-4 mr-2" /> Bulk Import (with Tasks)
            </Button>
          )}
          {canCreateProject && (
            <Button className="flex items-center" onClick={openCreateModal}>
              <Plus className="w-4 h-4 mr-2" /> Create Project
            </Button>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
        {[
          { label: 'Active Projects', value: activeCount, color: 'text-blue-600', bg: 'bg-blue-50' },
          { label: 'In Pipeline', value: pipelineCount, color: 'text-amber-600', bg: 'bg-amber-50' },
          { label: 'Completed', value: completedCount, color: 'text-green-600', bg: 'bg-green-50' },
          { label: 'Over Budget', value: overBudgetCount, color: 'text-red-600', bg: 'bg-red-50' },
        ].map((stat, i) => (
          <Card key={i} className="p-5 flex items-center gap-4 border-slate-100 shadow-sm">
            <div className={cn("w-12 h-12 rounded-xl flex items-center justify-center", stat.bg)}>
              <Briefcase className={cn("w-6 h-6", stat.color)} />
            </div>
            <div>
              <p className="text-xs font-bold text-[#64748B] uppercase tracking-wider">{stat.label}</p>
              <h4 className="text-2xl font-black text-[#0F172A]">{stat.value.toString().padStart(2, '0')}</h4>
            </div>
          </Card>
        ))}
      </div>

      <Card className="overflow-hidden border-slate-200 shadow-sm">
        <div className="p-4 border-b border-[#E5E7EB] flex flex-wrap items-center gap-4 justify-between bg-white">
          <div className="relative flex-1 min-w-[300px]">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#64748B]" />
            <input 
              type="text" 
              placeholder="Search projects, clients or managers..." 
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-10 pr-4 py-2 border border-[#E5E7EB] rounded-lg text-sm bg-[#F9FAFB] focus:outline-none focus:ring-1 focus:ring-blue-600"
            />
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" className="flex items-center">
              <Filter className="w-4 h-4 mr-2" /> Filter
            </Button>
            <Button variant="outline" size="sm" onClick={() => toast.success("Export started", { description: "Project list exported to CSV" })}>Export CSV</Button>
          </div>
        </div>
        
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-[#F9FAFB] border-b border-[#E5E7EB]">
                <th className="px-6 py-4 text-xs font-bold text-[#374151] uppercase tracking-wider">Project Name</th>
                <th className="px-6 py-4 text-xs font-bold text-[#374151] uppercase tracking-wider">Client</th>
                <th className="px-6 py-4 text-xs font-bold text-[#374151] uppercase tracking-wider">Status</th>
                <th className="px-6 py-4 text-xs font-bold text-[#374151] uppercase tracking-wider">Progress</th>
                <th className="px-6 py-4 text-xs font-bold text-[#374151] uppercase tracking-wider">Manager</th>
                <th className="px-6 py-4 text-xs font-bold text-[#374151] uppercase tracking-wider">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#E5E7EB]">
              {filteredProjects.map((proj) => {
                const progress = calculateProjectProgress(proj.id);
                return (
                  <tr 
                    key={proj.id} 
                    className="hover:bg-blue-50/30 transition-colors cursor-pointer group"
                    onClick={() => setSelectedProjectId(proj.id)}
                  >
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-3">
                        {proj.parentProjectId && (
                          <span className="ml-4 w-0.5 h-8 bg-blue-200 rounded-full flex-shrink-0" />
                        )}
                        <div className={`w-10 h-10 rounded-lg flex items-center justify-center font-bold text-xs border ${proj.parentProjectId ? 'bg-violet-50 text-violet-600 border-violet-100' : 'bg-blue-50 text-blue-600 border-blue-100'}`}>
                          {proj.parentProjectId ? '↳' : proj.id}
                        </div>
                        <div>
                          <div className="flex items-center gap-2">
                            <p className="text-sm font-bold text-[#0F172A] group-hover:text-blue-600 transition-colors">{proj.name}</p>
                            {proj.parentProjectId && (
                              <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-violet-100 text-violet-600">SUB-PROJECT</span>
                            )}
                          </div>
                          <p className="text-xs text-[#64748B]">Due: {proj.end}</p>
                        </div>
                      </div>
                    </td>
                    <td className="px-6 py-4 text-sm text-[#334155]">{proj.client}</td>
                    <td className="px-6 py-4">
                      <Badge variant={proj.status === 'active' ? 'success' : proj.status === 'pipeline' ? 'info' : proj.status === 'approval-pending' ? 'warning' : 'neutral'}>
                        {proj.status.toUpperCase().replace('-', ' ')}
                      </Badge>
                    </td>
                    <td className="px-6 py-4 min-w-[150px]">
                      <div className="flex items-center gap-3">
                        <div className="flex-1 h-2 bg-slate-100 rounded-full overflow-hidden">
                          <div className="h-full bg-blue-600 rounded-full transition-all duration-500" style={{ width: `${progress}%` }} />
                        </div>
                        <span className="text-xs font-bold text-[#0F172A]">{progress}%</span>
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-2">
                        <div className="w-7 h-7 rounded-full bg-blue-100 text-blue-600 flex items-center justify-center text-[10px] font-bold">
                          {proj.manager.split(' ').map(n => n[0]).join('')}
                        </div>
                        <span className="text-sm text-[#334155]">{proj.manager}</span>
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <ChevronRight className="w-4 h-4 text-[#94A3B8] group-hover:text-blue-600 transform group-hover:translate-x-1 transition-all" />
                    </td>
                  </tr>
                );
              })}
              {filteredProjects.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-6 py-20 text-center">
                    <div className="flex flex-col items-center gap-2 opacity-50">
                      <Search size={40} className="text-slate-300" />
                      <p className="text-sm font-bold text-slate-400">No projects found matching your search</p>
                    </div>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Create Project Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <Card
            className="w-full max-w-lg p-8 space-y-6 animate-in zoom-in-95 duration-200"
            style={{
              maxHeight: "70vh",
              overflowY: "auto",
              overscrollBehavior: "contain",
              WebkitOverflowScrolling: "touch",
            }}
          >
            <div className="flex items-center justify-between">
              <h3 className="text-xl font-bold text-[#0F172A]">Create New Project</h3>
              <button onClick={() => setShowCreateModal(false)} className="p-2 hover:bg-slate-100 rounded-full">
                <X size={20} className="text-slate-400" />
              </button>
            </div>
            <form onSubmit={handleCreateProject} className="space-y-4">
              <div className="space-y-2">
                <label className="text-xs font-bold text-slate-500 uppercase">Project Name</label>
                <Input name="name" placeholder="e.g. Website Overhaul" required />
              </div>
              <div className="space-y-2">
                <label className="text-xs font-bold text-slate-500 uppercase">Client</label>
                {selectedClientId ? (
                  <div className="flex items-center justify-between border border-slate-200 rounded-md px-3 h-10 bg-slate-50">
                    <span className="text-sm font-bold text-slate-700">
                      {selectedClientName} <span className="text-xs text-slate-400">#{selectedClientId}</span>
                    </span>
                    <button
                      type="button"
                      onClick={() => {
                        setSelectedClientId('');
                        setSelectedClientName('');
                        setClientSearchInput('');
                      }}
                      className="text-xs text-blue-600 hover:underline"
                    >
                      Change
                    </button>
                  </div>
                ) : (
                  <div className="relative">
                    <div className="flex gap-2">
                      <div className="flex-1">
                        <Input
                          placeholder="Search clients by name, domain, or industry…"
                          value={clientSearchInput}
                          onChange={(e) => setClientSearchInput(e.target.value)}
                          autoComplete="off"
                        />
                      </div>
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={openQuickAdd}
                        className="shrink-0"
                      >
                        <Plus className="w-3.5 h-3.5 mr-1" />
                        Add new
                      </Button>
                    </div>
                    {(clientSearchInput || clientOptions.length > 0) && (
                      <div className="absolute left-0 right-0 mt-1 border border-slate-200 rounded-md bg-white shadow-lg max-h-56 overflow-y-auto z-30">
                        {clientSearching && (
                          <div className="px-3 py-2 text-xs text-slate-400">Searching…</div>
                        )}
                        {!clientSearching && clientOptions.length === 0 && (
                          <div className="px-3 py-2 text-xs text-slate-400">
                            {clientSearchInput ? (
                              <>No clients match. <button type="button" onClick={openQuickAdd} className="text-blue-600 hover:underline">Add "{clientSearchInput}" as a new client</button>?</>
                            ) : 'Start typing to search.'}
                          </div>
                        )}
                        {clientOptions.map((c) => (
                          <button
                            type="button"
                            key={c.id}
                            onClick={() => {
                              setSelectedClientId(String(c.id));
                              setSelectedClientName(c.name);
                            }}
                            className="w-full text-left px-3 py-2 text-sm hover:bg-blue-50 hover:text-blue-700"
                          >
                            <span className="font-medium">{c.name}</span>
                            <span className="text-xs text-slate-400 ml-2">#{c.id}</span>
                          </button>
                        ))}
                        {!clientSearching && clientTotal > clientOptions.length && (
                          <div className="px-3 py-1.5 text-[11px] text-slate-400 border-t border-slate-100">
                            Showing first {clientOptions.length} of {clientTotal} — refine your search.
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )}
                <input type="hidden" name="client_id" value={selectedClientId} />
              </div>
              <div className="grid grid-cols-3 gap-4">
                <div className="space-y-2">
                  <label className="text-xs font-bold text-slate-500 uppercase">Budget (₹)</label>
                  <Input name="budget" type="number" placeholder="50000" required />
                </div>
                <div className="space-y-2">
                  <label className="text-xs font-bold text-slate-500 uppercase">Budget Hours</label>
                  <Input name="budget_hours" type="number" min="0" step="0.5" placeholder="e.g. 200" />
                </div>
                <div className="space-y-2">
                  <label className="text-xs font-bold text-slate-500 uppercase">Deadline</label>
                  <Input name="end" type="date" required />
                </div>
              </div>
              <div className="flex gap-3 pt-4">
                <Button variant="outline" className="flex-1" type="button" onClick={() => setShowCreateModal(false)}>Cancel</Button>
                <Button className="flex-1" type="submit">Create Project</Button>
              </div>
            </form>
          </Card>
        </div>
      )}

      {showBulkUploadModal && (
        <BulkUploadProjectsModal
          onClose={() => setShowBulkUploadModal(false)}
          onUploaded={() => {
            setShowBulkUploadModal(false);
            fetchProjects();
          }}
        />
      )}

      {showBulkImportWithTasksModal && (
        <BulkImportWithTasksModal
          onClose={() => setShowBulkImportWithTasksModal(false)}
          onUploaded={() => {
            setShowBulkImportWithTasksModal(false);
            fetchProjects();
          }}
        />
      )}

      {quickAddOpen && (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-[60] flex items-center justify-center p-4">
          <Card className="w-full max-w-md p-6 space-y-4 animate-in zoom-in-95 duration-200">
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-bold text-[#0F172A]">Quick Add Client</h3>
              <button
                type="button"
                onClick={() => setQuickAddOpen(false)}
                className="p-2 hover:bg-slate-100 rounded-full"
              >
                <X size={18} className="text-slate-400" />
              </button>
            </div>
            <p className="text-xs text-slate-500">
              Adds a minimal client record. You can fill in the rest later from the Clients module.
            </p>
            <div className="space-y-3">
              <div className="space-y-1.5">
                <label className="text-xs font-bold text-slate-500 uppercase">Name *</label>
                <Input
                  value={quickAddName}
                  onChange={(e) => setQuickAddName(e.target.value)}
                  placeholder="Acme Corp"
                  autoFocus
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <label className="text-xs font-bold text-slate-500 uppercase">Domain</label>
                  <Input
                    value={quickAddDomain}
                    onChange={(e) => setQuickAddDomain(e.target.value)}
                    placeholder="acmecorp.com"
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="text-xs font-bold text-slate-500 uppercase">Industry</label>
                  <Input
                    value={quickAddIndustry}
                    onChange={(e) => setQuickAddIndustry(e.target.value)}
                    placeholder="Manufacturing"
                  />
                </div>
              </div>
            </div>
            <div className="flex justify-end gap-2 pt-1">
              <Button
                variant="outline"
                type="button"
                onClick={() => setQuickAddOpen(false)}
                disabled={quickAddSubmitting}
              >
                Cancel
              </Button>
              <Button
                type="button"
                onClick={submitQuickAdd}
                isLoading={quickAddSubmitting}
              >
                <Plus className="w-3.5 h-3.5 mr-1.5" />
                Create & Select
              </Button>
            </div>
          </Card>
        </div>
      )}
    </div>
  );
};

// --- Bulk Upload Projects Modal ---

const BulkUploadProjectsModal = ({
  onClose,
  onUploaded,
}: {
  onClose: () => void;
  onUploaded: () => void;
}) => {
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [createMissingClients, setCreateMissingClients] = useState(false);
  const [result, setResult] = useState<{ created: number; skipped: number; clients_created?: number; errors: string[] } | null>(null);

  const handleDownloadTemplate = async () => {
    try {
      setDownloading(true);
      const res = await client.get(ENDPOINTS.PROJECTS.TEMPLATE, { responseType: 'blob' });
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const a = document.createElement('a');
      a.href = url;
      a.download = 'project_template.xlsx';
      a.click();
      window.URL.revokeObjectURL(url);
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      toast.error(typeof detail === 'string' ? detail : 'Failed to download template');
    } finally {
      setDownloading(false);
    }
  };

  const handleUpload = async () => {
    if (!file) {
      toast.error('Please choose an Excel file');
      return;
    }
    try {
      setUploading(true);
      const fd = new FormData();
      fd.append('file', file);
      const res = await client.post(ENDPOINTS.PROJECTS.BULK_UPLOAD, fd, {
        params: createMissingClients ? { create_missing_clients: true } : undefined,
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setResult(res.data);
      const { created = 0, errors = [], clients_created = 0 } = res.data || {};
      const clientsBlurb = clients_created > 0
        ? ` (and ${clients_created} new client${clients_created === 1 ? '' : 's'})`
        : '';
      if (errors.length === 0) {
        toast.success(`Imported ${created} project${created === 1 ? '' : 's'}${clientsBlurb}`);
      } else {
        toast.warning(`Imported ${created} project${created === 1 ? '' : 's'}${clientsBlurb}, ${errors.length} error${errors.length === 1 ? '' : 's'}`);
      }
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      toast.error(typeof detail === 'string' ? detail : 'Bulk upload failed');
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <Card
        className="w-full max-w-lg p-8 space-y-5 animate-in zoom-in-95 duration-200"
        style={{ maxHeight: '85vh', overflowY: 'auto', overscrollBehavior: 'contain' }}
      >
        <div className="flex items-center justify-between">
          <h3 className="text-xl font-bold text-[#0F172A]">Bulk Upload Projects</h3>
          <button onClick={onClose} className="p-2 hover:bg-slate-100 rounded-full">
            <X size={20} className="text-slate-400" />
          </button>
        </div>

        <div className="text-sm text-slate-600 space-y-2">
          <p>Upload an Excel file (.xlsx) containing your projects.</p>
          <ul className="list-disc list-inside text-xs text-slate-500 space-y-1">
            <li><b>Project Name</b> and <b>Client Name</b> are required.</li>
            <li>Client must already exist in the Clients module — names are matched case-insensitively.</li>
            <li>Project Code is auto-generated if left blank.</li>
            <li>Manager Email (optional) sets the manager; otherwise you (the uploader) become the manager.</li>
          </ul>
        </div>

        <div className="flex gap-2">
          <Button variant="outline" type="button" onClick={handleDownloadTemplate} disabled={downloading}>
            <Download className="w-4 h-4 mr-2" /> {downloading ? 'Downloading…' : 'Download Template'}
          </Button>
        </div>

        <div className="space-y-2">
          <label className="text-xs font-bold text-slate-500 uppercase">Excel File</label>
          <input
            type="file"
            accept=".xlsx,.xls"
            onChange={(e) => setFile(e.target.files?.[0] || null)}
            className="block w-full text-sm text-slate-700 file:mr-4 file:py-2 file:px-3 file:rounded-md file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100"
          />
          {file && <p className="text-xs text-slate-500">Selected: {file.name}</p>}
        </div>

        <label className="flex items-start gap-2 text-xs text-slate-600 cursor-pointer">
          <input
            type="checkbox"
            checked={createMissingClients}
            onChange={(e) => setCreateMissingClients(e.target.checked)}
            className="mt-0.5"
          />
          <span>
            <span className="font-bold text-slate-700">Auto-create missing clients</span>
            <span className="block text-slate-500">
              When checked, client names not found in the directory are added as bare records (name only). Otherwise such rows are reported as errors.
            </span>
          </span>
        </label>

        {result && (
          <div className="border border-slate-200 rounded-lg p-4 space-y-2 bg-slate-50">
            <div className="flex flex-wrap gap-4 text-sm">
              <span className="font-semibold text-green-700">Created: {result.created}</span>
              <span className="text-slate-500">Skipped: {result.skipped}</span>
              {(result.clients_created ?? 0) > 0 && (
                <span className="text-blue-700 font-semibold">+ {result.clients_created} new client{result.clients_created === 1 ? '' : 's'}</span>
              )}
              <span className={result.errors.length ? 'text-red-600' : 'text-slate-500'}>
                Errors: {result.errors.length}
              </span>
            </div>
            {result.errors.length > 0 && (
              <div className="max-h-40 overflow-y-auto text-xs text-red-600 space-y-1">
                {result.errors.map((e, i) => (
                  <div key={i}>• {e}</div>
                ))}
              </div>
            )}
          </div>
        )}

        <div className="flex gap-3 pt-2">
          <Button variant="outline" className="flex-1" type="button" onClick={onClose}>
            {result ? 'Close' : 'Cancel'}
          </Button>
          {result ? (
            <Button className="flex-1" type="button" onClick={onUploaded}>
              Done
            </Button>
          ) : (
            <Button className="flex-1" type="button" onClick={handleUpload} disabled={uploading || !file}>
              {uploading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Upload className="w-4 h-4 mr-2" />}
              {uploading ? 'Uploading…' : 'Upload'}
            </Button>
          )}
        </div>
      </Card>
    </div>
  );
};

// --- Bulk Import Projects WITH Tasks Modal (master + sub pattern) ---

const BulkImportWithTasksModal = ({
  onClose,
  onUploaded,
}: {
  onClose: () => void;
  onUploaded: () => void;
}) => {
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [result, setResult] = useState<{
    projects_created: number;
    subprojects_created: number;
    tasks_created: number;
    errors: string[];
  } | null>(null);

  const handleDownloadTemplate = async () => {
    try {
      setDownloading(true);
      const res = await client.get(ENDPOINTS.PROJECTS.TEMPLATE_WITH_TASKS, {
        responseType: 'blob',
      });
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const a = document.createElement('a');
      a.href = url;
      a.download = 'project_template_with_tasks.xlsx';
      a.click();
      window.URL.revokeObjectURL(url);
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      toast.error(typeof detail === 'string' ? detail : 'Failed to download template');
    } finally {
      setDownloading(false);
    }
  };

  const handleUpload = async () => {
    if (!file) {
      toast.error('Please choose an Excel file');
      return;
    }
    try {
      setUploading(true);
      const fd = new FormData();
      fd.append('file', file);
      const res = await client.post(
        ENDPOINTS.PROJECTS.BULK_IMPORT_WITH_TASKS,
        fd,
        { headers: { 'Content-Type': 'multipart/form-data' } },
      );
      setResult(res.data);
      const {
        projects_created = 0,
        subprojects_created = 0,
        tasks_created = 0,
        errors = [],
      } = res.data || {};
      if (errors.length === 0) {
        toast.success(
          `Imported ${projects_created} master · ${subprojects_created} sub · ${tasks_created} tasks`,
        );
      } else {
        toast.warning(
          `Imported ${projects_created} master / ${subprojects_created} sub / ${tasks_created} tasks · ${errors.length} error${errors.length === 1 ? '' : 's'}`,
        );
      }
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      toast.error(typeof detail === 'string' ? detail : 'Bulk import failed');
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <Card
        className="w-full max-w-lg p-8 space-y-5 animate-in zoom-in-95 duration-200"
        style={{ maxHeight: '85vh', overflowY: 'auto', overscrollBehavior: 'contain' }}
      >
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-xl font-bold text-[#0F172A]">Bulk Import Projects (with Tasks)</h3>
            <p className="text-xs text-slate-500 mt-1">Legacy import · creates master + sub-projects</p>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-slate-100 rounded-full">
            <X size={20} className="text-slate-400" />
          </button>
        </div>

        <div className="text-sm text-slate-600 space-y-2">
          <p>One row per task. Multiple rows share the same Project Code.</p>
          <ul className="list-disc list-inside text-xs text-slate-500 space-y-1">
            <li><b>Client Name</b> must already exist in the Clients module.</li>
            <li><b>Functional Area</b> must match an existing code (e.g. <code>GR</code>) or name.</li>
            <li><b>Project Manager</b> name must match exactly one active user with the <b>PM</b> role.</li>
            <li>Master PM defaults to the first active COO (fallback CEO / Super Admin).</li>
            <li><b>Task Value</b> creates the sub-project's budget; total = master budget.</li>
            <li><b>Sub Task</b> column is ignored — PMs add subtasks in the portal.</li>
          </ul>
        </div>

        <div className="flex gap-2">
          <Button variant="outline" type="button" onClick={handleDownloadTemplate} disabled={downloading}>
            <Download className="w-4 h-4 mr-2" />
            {downloading ? 'Downloading…' : 'Download Template'}
          </Button>
        </div>

        <div className="space-y-2">
          <label className="text-xs font-bold text-slate-500 uppercase">Excel File</label>
          <input
            type="file"
            accept=".xlsx,.xls"
            onChange={e => setFile(e.target.files?.[0] || null)}
            className="block w-full text-sm text-slate-700 file:mr-4 file:py-2 file:px-3 file:rounded-md file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100"
          />
        </div>

        {result && (
          <div className="border border-slate-200 rounded-lg p-4 space-y-2 bg-slate-50">
            <div className="flex flex-wrap gap-4 text-sm">
              <span className="font-semibold text-green-700">Master projects: {result.projects_created}</span>
              <span className="text-blue-700 font-semibold">Sub-projects: {result.subprojects_created}</span>
              <span className="text-slate-700 font-semibold">Tasks: {result.tasks_created}</span>
              <span className={result.errors.length ? 'text-red-600' : 'text-slate-500'}>
                Errors: {result.errors.length}
              </span>
            </div>
            {result.errors.length > 0 && (
              <div className="max-h-40 overflow-y-auto text-xs text-red-600 space-y-1">
                {result.errors.map((e, i) => (
                  <div key={i}>• {e}</div>
                ))}
              </div>
            )}
          </div>
        )}

        <div className="flex gap-3 pt-2">
          <Button variant="outline" className="flex-1" type="button" onClick={onClose}>
            {result ? 'Close' : 'Cancel'}
          </Button>
          {result ? (
            <Button className="flex-1" type="button" onClick={onUploaded}>
              Done
            </Button>
          ) : (
            <Button className="flex-1" type="button" onClick={handleUpload} disabled={uploading || !file}>
              {uploading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Upload className="w-4 h-4 mr-2" />}
              {uploading ? 'Importing…' : 'Import'}
            </Button>
          )}
        </div>
      </Card>
    </div>
  );
};

// --- Project Detail Component ---

const ProjectDetail = ({
  project, 
  tasks, 
  milestones, 
  projectUtilization,
  userRole = 'employee',
  onBack, 
  onUpdateProject, 
  onUpdateTasks, 
  onUpdateMilestones 
}: { 
  project: any, 
  tasks: Task[], 
  milestones: Milestone[], 
  projectUtilization?: any,
  userRole?: UserRole,
  onBack: () => void,
  onUpdateProject: (p: Project) => void,
  onUpdateTasks: (t: Task[]) => void,
  onUpdateMilestones: (m: Milestone[]) => void
}) => {
  const [activeTab, setActiveTab] = useState<'overview' | 'tasks' | 'milestones' | 'costing' | 'team' | 'documents'>('overview');
  const [showTaskModal, setShowTaskModal] = useState(false);
  const [editingTask, setEditingTask] = useState<Task | null>(null);
  const [showSubtaskModal, setShowSubtaskModal] = useState(false);
  const [subtaskParentTask, setSubtaskParentTask] = useState<Task | null>(null);
  const [subtaskParentSubtaskId, setSubtaskParentSubtaskId] = useState<string | null>(null);
  const [editingSubtaskId, setEditingSubtaskId] = useState<string | null>(null);
  const [showMilestoneModal, setShowMilestoneModal] = useState(false);
  const [showCostChangeModal, setShowCostChangeModal] = useState(false);
  const [activeBaseline, setActiveBaseline] = useState<CostBaseline | null>(null);
  const [showDOPModal, setShowDOPModal] = useState(false);
  const [proposedCost, setProposedCost] = useState(project.actualCost);
  const [showCostUpdateModal, setShowCostUpdateModal] = useState(false);
  
  const [projectMembers, setProjectMembers] = useState<any[]>([]);
  const [allUsers, setAllUsers] = useState<any[]>([]);
  const [memberSearchTerm, setMemberSearchTerm] = useState('');
  const [selectedUsersForAllocation, setSelectedUsersForAllocation] = useState<string[]>([]);
  const [showAddMemberModal, setShowAddMemberModal] = useState(false);
  const [isLoadingMembers, setIsLoadingMembers] = useState(false);
  
  const variance = ((project.actualCost / project.budget) * 100);
  const isDOPPending = project.status === 'approval-pending';

  useEffect(() => {
    const projectIdStr = project?.id?.toString();
    if (!projectIdStr) return;

    fetchProjectMembers();
    fetchAllUsers();

    client
      .get(ENDPOINTS.PROJECTS.COST_BASELINE(projectIdStr))
      .then((res) => setActiveBaseline(res.data))
      .catch(() => {
        // Baseline is optional for most flows; avoid crashing the detail view.
      });
  }, [project?.id]);

  const fetchProjectMembers = async () => {
    try {
      setIsLoadingMembers(true);
      const res = await client.get(ENDPOINTS.PROJECTS.MEMBERS(project.id));
      setProjectMembers(res.data);
    } catch (error) {
      console.error("Failed to fetch project members", error);
    } finally {
      setIsLoadingMembers(false);
    }
  };

  const fetchAllUsers = async () => {
    try {
      const res = await client.get(ENDPOINTS.PROJECTS.ALLOCATE_USERS);
      setAllUsers(res.data);
    } catch (error) {
      console.error("Failed to fetch users", error);
    }
  };

  const handleAddMember = async (userId: number, role: string = 'member') => {
    try {
      await client.post(ENDPOINTS.PROJECTS.ADD_MEMBER(project.id), { user_id: userId, role });
      toast.success('Member added to project');
      fetchProjectMembers();
    } catch (error) {
      toast.error('Failed to add member');
    }
  };

  const handleBulkAddMembers = async () => {
    if (selectedUsersForAllocation.length === 0) return;
    
    try {
      setIsLoadingMembers(true);
      // Backend usually expects one at a time unless there's a bulk endpoint
      const promises = selectedUsersForAllocation.map(userId => 
        client.post(ENDPOINTS.PROJECTS.ADD_MEMBER(project.id), { user_id: parseInt(userId), role: 'member' })
      );
      
      await Promise.all(promises);
      toast.success(`${selectedUsersForAllocation.length} members added`);
      setSelectedUsersForAllocation([]);
      setShowAddMemberModal(false);
      fetchProjectMembers();
    } catch (error) {
      toast.error('Failed to add some members');
    } finally {
      setIsLoadingMembers(false);
    }
  };

  const toggleUserSelection = (userId: string) => {
    setSelectedUsersForAllocation(prev => 
      prev.includes(userId) 
        ? prev.filter(id => id !== userId) 
        : [...prev, userId]
    );
  };

  const handleRemoveMember = async (userId: number) => {
    try {
      await client.delete(ENDPOINTS.PROJECTS.REMOVE_MEMBER(project.id, userId));
      toast.success('Member removed');
      fetchProjectMembers();
    } catch (error) {
      toast.error('Failed to remove member');
    }
  };

  const handleTaskSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const formData = new FormData(e.target as HTMLFormElement);

    const title = (formData.get('title') as string) || '';
    const priorityUi = (formData.get('priority') as string) || 'Medium';
    const statusUi = (formData.get('status') as string) || 'To Do';
    const assigned = (formData.get('assigned') as string) || '';
    const hoursRaw = (formData.get('hours') as string) || '';
    const estimatedHours = Number(hoursRaw || 0);

    if (!Number.isFinite(estimatedHours) || estimatedHours < 0) {
      toast.error('Hours must be a valid number (>= 0)');
      return;
    }

    const taskData: Task = {
      id: editingTask?.id || `T${Date.now()}`,
      projectId: project.id,
      title,
      priority: priorityUi as any,
      status: statusUi as any,
      assigned,
      estimatedHours,
      subtasks: editingTask?.subtasks || []
    };

    if (editingTask) {
      // UI-only edit for now (backend update endpoint not implemented).
      onUpdateTasks(tasks.map(t => t.id === taskData.id ? taskData : t));
      toast.success('Task Updated');
      setShowTaskModal(false);
      setEditingTask(null);
      return;
    }

    const projectIdNum = Number.parseInt(project.id, 10);
    if (!Number.isFinite(projectIdNum)) {
      toast.error('Invalid project id');
      return;
    }

    const statusMap: Record<string, string> = {
      'To Do': 'todo',
      'In Progress': 'in_progress',
      'Review': 'review',
      'Done': 'completed',
    };
    const priorityMap: Record<string, string> = {
      'Critical': 'high',
      'High': 'high',
      'Medium': 'medium',
      'Low': 'low',
    };

    try {
      const res = await client.post(ENDPOINTS.TASKS.CREATE, {
        project_id: projectIdNum,
        title,
        description: null,
        status: statusMap[statusUi] || 'todo',
        priority: priorityMap[priorityUi] || 'medium',
        estimated_hours: estimatedHours,
        assignee_email: assigned || null,
      });

      const created = (res as any).data;
      onUpdateTasks([
        ...tasks,
        {
          ...taskData,
          id: created?.id ? created.id.toString() : taskData.id,
        },
      ]);

      toast.success('Task Created');
      setShowTaskModal(false);
      setEditingTask(null);
    } catch (error: any) {
      toast.error(error?.response?.data?.error?.message || 'Task creation failed');
    }
  };

  const handleSubtaskSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!subtaskParentTask) return;

    const formData = new FormData(e.target as HTMLFormElement);
    const title = ((formData.get('subtask_title') as string) || '').trim();
    const assigned = (formData.get('subtask_assigned') as string) || '';
    const hoursRaw = (formData.get('subtask_hours') as string) || '';
    const estimatedHours = Number(hoursRaw || 0);

    if (!title) {
      toast.error('Subtask title is required');
      return;
    }
    if (!Number.isFinite(estimatedHours) || estimatedHours < 0) {
      toast.error('Subtask hours must be a valid number (>= 0)');
      return;
    }

    const isPM = userRole === 'pm' || userRole === 'super admin' || userRole === 'coo';
    const parentSubtask = subtaskParentSubtaskId
      ? subtaskParentTask.subtasks.find(s => s.id === subtaskParentSubtaskId)
      : null;
    const parentCapacity = parentSubtask
      ? parentSubtask.estimatedHours
      : subtaskParentTask.estimatedHours;
    const siblingsUsed = subtaskParentTask.subtasks
      .filter(s => (s.parentSubtaskId || null) === (subtaskParentSubtaskId || null))
      .filter(s => !editingSubtaskId || s.id !== editingSubtaskId)
      .reduce((sum, s) => sum + (s.estimatedHours || 0), 0);

    if (
      Number.isFinite(parentCapacity)
      && siblingsUsed + estimatedHours > parentCapacity + 1e-6
    ) {
      const remaining = Math.max(parentCapacity - siblingsUsed, 0);
      toast.error(
        `Subtask hours exceed parent hours. Remaining: ${remaining.toFixed(2)}h`,
      );
      return;
    }

    const taskIdNum = Number.parseInt(subtaskParentTask.id, 10);
    if (!Number.isFinite(taskIdNum)) {
      toast.error('Invalid task id');
      return;
    }

    const editingSubtask = editingSubtaskId
      ? subtaskParentTask.subtasks.find(s => s.id === editingSubtaskId)
      : null;

    if (editingSubtaskId && !editingSubtask) {
      toast.error('Subtask not found');
      return;
    }

    const childUsed = editingSubtaskId
      ? subtaskParentTask.subtasks
          .filter(s => (s.parentSubtaskId || null) === editingSubtaskId)
          .reduce((sum, s) => sum + (s.estimatedHours || 0), 0)
      : 0;

    if (editingSubtaskId && childUsed > estimatedHours + 1e-6) {
      toast.error(
        `Children hours exceed new hours. Children: ${childUsed.toFixed(2)}h`,
      );
      return;
    }

    try {
      const editingIdNum = editingSubtaskId
        ? Number.parseInt(editingSubtaskId, 10)
        : null;

      const res = editingSubtaskId
        ? (
            Number.isFinite(editingIdNum)
              ? await client.patch(
                  ENDPOINTS.TASKS.SUBTASK(editingIdNum as number),
                  {
                    title,
                    estimated_hours: estimatedHours,
                    assignee_email: assigned || null,
                  },
                )
              : ({ data: { title, estimated_hours: estimatedHours } } as any)
          )
        : await client.post(ENDPOINTS.TASKS.SUBTASKS(taskIdNum), {
            title,
            is_completed: false,
            estimated_hours: estimatedHours,
            assignee_email: assigned || null,
            parent_subtask_id: isPM
              ? (subtaskParentSubtaskId
                  ? Number.parseInt(subtaskParentSubtaskId, 10)
                  : null)
              : null,
          });

      const created = (res as any).data;
      const assigneeEmail = (() => {
        if (assigned) return assigned;
        const id = created?.assignee_id;
        const member = projectMembers.find(m => m.user_id === id);
        return member?.user_email || '';
      })();

      onUpdateTasks(tasks.map(t => {
        if (t.id !== subtaskParentTask.id) return t;

        if (editingSubtaskId) {
          return {
            ...t,
            subtasks: t.subtasks.map(s => {
              if (s.id !== editingSubtaskId) return s;
              return {
                ...s,
                title: created?.title || title,
                estimatedHours: Number(created?.estimated_hours || estimatedHours),
                assigned: assigneeEmail,
              };
            }),
          };
        }

        return {
          ...t,
          subtasks: [
            ...t.subtasks,
            {
              id: created?.id ? created.id.toString() : `S${Date.now()}`,
              title: created?.title || title,
              completed: Boolean(created?.is_completed),
              estimatedHours: Number(created?.estimated_hours || estimatedHours),
              assigned: assigneeEmail,
              parentSubtaskId:
                created?.parent_subtask_id != null
                  ? String(created.parent_subtask_id)
                  : (subtaskParentSubtaskId || null),
            },
          ],
        };
      }));

      toast.success(editingSubtaskId ? 'Subtask Updated' : 'Subtask Created');
      setShowSubtaskModal(false);
      setSubtaskParentTask(null);
      setSubtaskParentSubtaskId(null);
      setEditingSubtaskId(null);
    } catch (error: any) {
      toast.error(error?.response?.data?.error?.message || 'Subtask save failed');
    }
  };

  const handleMilestoneSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const projectIdStr = project?.id?.toString();
    if (!projectIdStr) return;
    const formData = new FormData(e.target as HTMLFormElement);
    try {
      await client.post(ENDPOINTS.PROJECTS.MILESTONES(projectIdStr), {
        title: formData.get('title'),
        description: formData.get('description'),
        due_date: formData.get('due_date'),
        status: formData.get('status') || 'pending'
      });
      toast.success("Strategic milestone registered");
      setShowMilestoneModal(false);
      const refreshed = await client.get(ENDPOINTS.PROJECTS.MILESTONES(projectIdStr));
      onUpdateMilestones(refreshed.data);
    } catch (error) {
       toast.error("Failed to register milestone");
    }
  };

  const handleCostChangeSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const projectIdStr = project?.id?.toString();
    if (!projectIdStr) return;
    const formData = new FormData(e.target as HTMLFormElement);
    try {
      await client.post(ENDPOINTS.PROJECTS.COST_CHANGE(projectIdStr), {
        proposed_amount: Number(formData.get('amount')),
        reason: formData.get('reason'),
        impact: formData.get('impact')
      });
      toast.success("Change request routed for authorization");
      setShowCostChangeModal(false);
    } catch (error: any) {
      toast.error(error.response?.data?.error?.message || "Change request failed");
    }
  };

  const handleCostUpdate = (e: React.FormEvent) => {
    e.preventDefault();
    const newCost = Number(proposedCost);
    const newVariance = (newCost / project.budget) * 100;

    if (newVariance > 90) {
      onUpdateProject({ 
        ...project, 
        status: 'approval-pending', 
        proposedCostUpdate: newCost 
      });
      setShowDOPModal(true);
      toast.warning('DOP Approval Required', { description: 'Cost update exceeds 90% budget threshold.' });
    } else {
      onUpdateProject({ ...project, actualCost: newCost });
      toast.success('Cost Updated Successfully');
    }
    setShowCostUpdateModal(false);
  };

  const handleDOPAction = (approved: boolean) => {
    if (approved) {
      onUpdateProject({ 
        ...project, 
        actualCost: project.proposedCostUpdate || project.actualCost,
        status: 'active',
        proposedCostUpdate: undefined
      });
      toast.success('DOP Approved', { description: 'New project costing has been applied.' });
    } else {
      onUpdateProject({ 
        ...project, 
        status: 'active',
        proposedCostUpdate: undefined
      });
      toast.error('DOP Rejected', { description: 'Costing update was not approved.' });
    }
    setShowDOPModal(false);
  };

  const toggleSubtask = async (taskId: string, subtaskId: string) => {
    const task = tasks.find(t => t.id === taskId);
    const subtask = task?.subtasks.find(s => s.id === subtaskId);
    if (!task || !subtask) return;

    const subtaskIdNum = Number.parseInt(subtaskId, 10);
    const nextCompleted = !subtask.completed;
    if (!Number.isFinite(subtaskIdNum)) {
      onUpdateTasks(tasks.map(t => t.id === taskId ? { ...t, subtasks: t.subtasks.map(s => s.id === subtaskId ? { ...s, completed: nextCompleted } : s) } : t));
      return;
    }

    try {
      const res = await client.patch(ENDPOINTS.TASKS.SUBTASK(subtaskIdNum), { is_completed: nextCompleted });
      const updated = (res as any).data;

      onUpdateTasks(tasks.map(t => {
        if (t.id !== taskId) return t;
        return {
          ...t,
          subtasks: t.subtasks.map(s => {
            if (s.id !== subtaskId) return s;
            return {
              ...s,
              completed: Boolean(updated?.is_completed),
            };
          }),
        };
      }));
    } catch (error: any) {
      toast.error(error?.response?.data?.error?.message || 'Failed to update subtask');
    }
  };

  const isPM = userRole === 'pm' || userRole === 'super admin';

  const renderSubtaskTree = (task: Task) => {
    const byParent = new Map<string | null, Subtask[]>();
    task.subtasks.forEach(s => {
      const parent = (s.parentSubtaskId || null) as string | null;
      byParent.set(parent, [...(byParent.get(parent) || []), s]);
    });

    const visited = new Set<string>();
    const renderLevel = (parentId: string | null, depth: number): React.ReactNode => {
      const nodes = byParent.get(parentId) || [];
      if (nodes.length === 0) return null;
      if (depth > 12) return null;

      return (
        <div className={cn(depth > 0 && 'pl-4 border-l border-slate-100')}>
          <div className={cn(depth > 0 ? 'mt-2 space-y-2' : 'grid grid-cols-1 md:grid-cols-2 gap-3 mt-4')}>
            {nodes.map(sub => {
              if (visited.has(sub.id)) return null;
              visited.add(sub.id);
              return (
                <div key={sub.id} className="space-y-2">
                  <div
                    className={cn(
                      'flex items-center gap-3 p-3 bg-white rounded-xl border border-slate-100 cursor-pointer hover:border-blue-200 transition-colors',
                    )}
                    onClick={() => toggleSubtask(task.id, sub.id)}
                  >
                    <div className={cn(
                      'w-5 h-5 rounded-md flex items-center justify-center border transition-all',
                      sub.completed
                        ? 'bg-green-500 border-green-500 text-white'
                        : 'bg-white border-slate-200 text-transparent',
                    )}>
                      <CheckCircle size={12} strokeWidth={3} />
                    </div>
                    <span className={cn(
                      'text-[11px] font-bold uppercase tracking-tight',
                      sub.completed
                        ? 'text-slate-400 line-through'
                        : 'text-slate-600',
                    )}>
                      {sub.title}{' '}
                      <span className="text-[10px] font-black text-slate-400 uppercase tracking-widest">
                        • {Number(sub.estimatedHours || 0)
                          .toFixed(2)
                          .replace(/\.00$/, '')}h{sub.assigned ? ` • ${sub.assigned}` : ''}
                      </span>
                    </span>

                    {isPM && (
                      <div className="ml-auto flex items-center gap-1">
                        <button
                          type="button"
                          className="p-2 hover:bg-slate-100 text-slate-400 hover:text-slate-700 rounded-lg transition-colors"
                          onClick={(e) => {
                            e.stopPropagation();
                            setSubtaskParentTask(task);
                            setSubtaskParentSubtaskId(sub.parentSubtaskId || null);
                            setEditingSubtaskId(sub.id);
                            setShowSubtaskModal(true);
                          }}
                          aria-label="Edit subtask"
                          title="Edit subtask"
                        >
                          <Edit size={14} />
                        </button>

                        <button
                          type="button"
                          className="p-2 hover:bg-blue-50 text-slate-400 hover:text-blue-600 rounded-lg transition-colors"
                          onClick={(e) => {
                            e.stopPropagation();
                            setSubtaskParentTask(task);
                            setSubtaskParentSubtaskId(sub.id);
                            setEditingSubtaskId(null);
                            setShowSubtaskModal(true);
                          }}
                          aria-label="Add child subtask"
                          title="Add child subtask"
                        >
                          <Plus size={14} />
                        </button>
                      </div>
                    )}
                  </div>

                  {isPM && renderLevel(sub.id, depth + 1)}
                </div>
              );
            })}
          </div>
        </div>
      );
    };

    return isPM ? renderLevel(null, 0) : null;
  };

  const updateMilestoneStatus = (milestoneId: string, status: Milestone['status']) => {
    onUpdateMilestones(milestones.map(m => m.id === milestoneId ? { ...m, status } : m));
    toast.success('Milestone Updated');
  };

  return (
    <div className="p-8 space-y-6 max-w-[1400px] mx-auto pb-20">
      <button onClick={onBack} className="flex items-center text-[#64748B] hover:text-[#0F172A] transition-colors mb-4 group">
        <ArrowLeft className="w-4 h-4 mr-2 group-hover:-translate-x-1 transition-transform" /> Back to Project List
      </button>

      <div className="flex flex-col md:flex-row md:items-end justify-between gap-6 bg-white p-8 rounded-2xl border border-[#E5E7EB] shadow-sm">
        <div className="space-y-4">
          <Badge variant={isDOPPending ? "warning" : "info"}>{project.id} {isDOPPending && "• APPROVAL PENDING"}</Badge>
          <h1 className="text-3xl font-black text-[#0F172A] tracking-tight uppercase">{project.name}</h1>
          <div className="flex flex-wrap gap-6 text-sm text-[#64748B]">
            <div className="flex items-center gap-2">
              <Users size={16} className="text-blue-500" /> <span className="font-bold">{project.client}</span>
            </div>
            <div className="flex items-center gap-2">
              <Calendar size={16} className="text-blue-500" /> {project.start} — {project.end}
            </div>
            <div className="flex items-center gap-2">
              <Briefcase size={16} className="text-blue-500" /> Manager: <span className="font-bold">{project.manager}</span>
            </div>
          </div>
        </div>
        <div className="flex gap-3">
          <Button variant="outline" className="h-12 px-6 font-bold">Edit Detail</Button>
          <Button className="h-12 px-6 font-bold shadow-lg shadow-blue-600/20" onClick={() => toast.success("Report Generated")}>Export Report</Button>
        </div>
      </div>

      <div className="flex border-b border-slate-100 mb-8 overflow-x-auto">
        {[
          { id: 'overview', label: 'Overview', icon: LayoutGrid },
          { id: 'tasks', label: 'Execution Board', icon: CheckSquare },
          { id: 'milestones', label: 'Strategic Milestones', icon: Target },
          { id: 'costing', label: 'Financial Controls', icon: DollarSign },
          { id: 'team', label: 'Resource Matrix', icon: Users },
          { id: 'documents', label: 'Documents', icon: Paperclip },
        ].map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id as any)}
            className={cn(
              "flex items-center gap-2 px-6 py-4 text-[10px] font-black uppercase tracking-[0.2em] transition-all relative whitespace-nowrap",
              activeTab === tab.id ? "text-blue-600" : "text-slate-400 hover:text-slate-600"
            )}
          >
            <tab.icon size={14} />
            {tab.label}
            {activeTab === tab.id && (
              <div className="absolute bottom-0 left-0 right-0 h-1 bg-blue-600 rounded-t-full shadow-[0_-4px_10px_rgba(37,99,235,0.3)]" />
            )}
          </button>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        <div className="lg:col-span-2 space-y-8">
          {activeTab === 'overview' && (
            <Card className="p-8 space-y-8 border-slate-200 shadow-sm">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                <div className="space-y-6">
                  <div>
                    <h3 className="text-xs font-black text-[#94A3B8] uppercase tracking-widest mb-4">Project Summary</h3>
                    <p className="text-[#64748B] leading-relaxed text-sm">
                      This project focuses on modernizing the existing HR infrastructure. The goal is to integrate real-time tracking, 
                      automated payroll calculations, and a comprehensive employee portal. Phase 1 focuses on design and frontend implementation.
                    </p>
                  </div>
                  
                  <div className="p-4 bg-slate-50 rounded-xl border border-slate-100 flex items-center justify-between">
                    <div>
                      <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Total Progress</p>
                      <p className="text-2xl font-black text-blue-600">{project.progress}%</p>
                    </div>
                    <div className="w-32 h-2 bg-slate-200 rounded-full overflow-hidden">
                       <div className="h-full bg-blue-600 rounded-full transition-all duration-1000" style={{ width: `${project.progress}%` }} />
                    </div>
                  </div>
                </div>

                <div className="space-y-6">
                  <h4 className="text-xs font-black text-[#94A3B8] uppercase tracking-widest mb-4">Strategic Milestones</h4>
                  <div className="space-y-4">
                    {milestones.map((m, i) => (
                      <div key={i} className="flex items-center gap-4 group cursor-pointer" onClick={() => {
                        const nextStatus = m.status === 'Pending' ? 'In Progress' : m.status === 'In Progress' ? 'Completed' : 'Pending';
                        updateMilestoneStatus(m.id, nextStatus);
                      }}>
                        <div className={cn(
                          "w-8 h-8 rounded-lg flex items-center justify-center border transition-all",
                          (m.status === 'Completed' || m.status === 'completed') ? "bg-green-100 border-green-200 text-green-600" : 
                          (m.status === 'In Progress' || m.status === 'in-progress') ? "bg-blue-100 border-blue-200 text-blue-600" : 
                          "bg-slate-50 border-slate-200 text-slate-300"
                        )}>
                          {(m.status === 'Completed' || m.status === 'completed') ? <CheckCircle2 size={18} /> : (m.status === 'In Progress' || m.status === 'in-progress') ? <Clock size={18} /> : <div className="w-2 h-2 rounded-full bg-current" />}
                        </div>
                        <div className="flex-1">
                          <p className={cn("text-sm font-bold", (m.status === 'Completed' || m.status === 'completed') ? "text-slate-400 line-through" : "text-[#0F172A]")}>{m.title}</p>
                          <p className="text-[10px] text-[#64748B] uppercase tracking-widest font-black">Due: {m.due_date || m.dueDate} • {m.status}</p>
                        </div>
                        <ChevronRight size={14} className="text-slate-300 opacity-0 group-hover:opacity-100 transition-opacity" />
                      </div>
                    ))}
                    <Button variant="outline" className="w-full border-dashed border-2 text-[10px] font-black uppercase tracking-widest h-10" onClick={() => toast.info("Milestone creation enabled")}>
                       Add Milestone
                    </Button>
                  </div>
                </div>
              </div>

              {projectUtilization?.tasks?.length > 0 && (
                <div className="pt-8 border-t border-slate-100">
                  <div className="flex items-center justify-between">
                    <h4 className="text-xs font-black text-[#94A3B8] uppercase tracking-widest">
                      Work Utilization
                    </h4>
                    <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest">
                      Used: {Number(projectUtilization.total_used_hours || 0).toFixed(1)}h • Est:{' '}
                      {Number(projectUtilization.total_estimated_hours || 0).toFixed(1)}h
                    </p>
                  </div>

                  <div className="mt-6 space-y-4">
                    {(projectUtilization.tasks || []).slice(0, 6).map((t: any) => {
                      const est = typeof t.estimated_hours === 'number' ? t.estimated_hours : 0;
                      const used = Number(t.used_total_hours || 0);
                      const pct = est > 0 ? Math.min(100, (used / est) * 100) : 0;
                      const over = est > 0 && used > est + 1e-6;
                      return (
                        <div
                          key={t.id}
                          className="p-5 bg-slate-50 rounded-2xl border border-slate-100"
                        >
                          <div className="flex items-center justify-between gap-4">
                            <div>
                              <p className="text-sm font-black text-[#0F172A] tracking-tight">
                                {t.title}
                              </p>
                              <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mt-1">
                                Used {used.toFixed(1)}h • Est {est ? est.toFixed(1) : '—'}h
                              </p>
                            </div>
                            <Badge
                              className={cn(
                                'font-black text-[9px] uppercase tracking-widest px-3 py-1 rounded-md border-none',
                                over
                                  ? 'text-amber-600 bg-amber-50'
                                  : 'text-blue-600 bg-blue-50',
                              )}
                            >
                              {over ? 'OVER' : 'TRACK'}
                            </Badge>
                          </div>

                          <div className="mt-4 w-full h-2 bg-slate-200 rounded-full overflow-hidden">
                            <div
                              className={cn(
                                'h-full rounded-full transition-all duration-700',
                                over ? 'bg-amber-500' : 'bg-blue-600',
                              )}
                              style={{ width: `${pct}%` }}
                            />
                          </div>

                          {(t.subtasks || []).length > 0 && (
                            <div className="mt-4 space-y-2">
                              {(t.subtasks || []).slice(0, 3).map((s: any) => {
                                const sEst = typeof s.estimated_hours === 'number' ? s.estimated_hours : 0;
                                const sUsed = Number(s.used_hours || 0);
                                const sPct = sEst > 0 ? Math.min(100, (sUsed / sEst) * 100) : 0;
                                const sOver = sEst > 0 && sUsed > sEst + 1e-6;
                                return (
                                  <div
                                    key={s.id}
                                    className="flex items-center justify-between gap-4"
                                  >
                                    <p className="text-[10px] font-black text-slate-500 uppercase tracking-widest">
                                      {s.title}
                                    </p>
                                    <div className="flex items-center gap-3 min-w-[160px]">
                                      <div className="flex-1 h-1.5 bg-slate-200 rounded-full overflow-hidden">
                                        <div
                                          className={cn(
                                            'h-full rounded-full',
                                            sOver ? 'bg-amber-500' : 'bg-blue-500',
                                          )}
                                          style={{ width: `${sPct}%` }}
                                        />
                                      </div>
                                      <span className="text-[10px] font-black text-slate-400 uppercase tracking-widest tabular-nums">
                                        {sUsed.toFixed(1)}h
                                      </span>
                                    </div>
                                  </div>
                                );
                              })}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
            </Card>
          )}

          {activeTab === 'costing' && (
            <Card className="p-8 space-y-8 border-slate-200 shadow-sm relative overflow-hidden">
              {isDOPPending && (
                <div className="absolute inset-0 bg-white/60 backdrop-blur-[2px] z-10 flex items-center justify-center p-8">
                   <div className="bg-white border-2 border-amber-200 rounded-2xl p-8 shadow-2xl max-w-md text-center space-y-4 animate-in zoom-in-95">
                      <div className="w-16 h-16 bg-amber-50 text-amber-600 rounded-full flex items-center justify-center mx-auto mb-2">
                         <AlertTriangle size={32} />
                      </div>
                      <h4 className="text-xl font-black text-[#0F172A] uppercase tracking-tight">Approval Required</h4>
                       <p className="text-sm text-[#64748B] font-medium">Proposed cost update to <span className="text-amber-600 font-bold">₹{project.proposedCostUpdate?.toLocaleString('en-IN')}</span> is awaiting Executive DOP approval.</p>
                      <div className="flex gap-3 pt-2">
                         <Button variant="outline" className="flex-1" onClick={() => handleDOPAction(false)}>Cancel Request</Button>
                         <Button className="flex-1 bg-blue-600" onClick={() => handleDOPAction(true)}>Approve (CEO/MD)</Button>
                      </div>
                   </div>
                </div>
              )}

              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-lg font-black text-[#0F172A] uppercase tracking-tight">Project Financials</h3>
                  <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Budget vs Actual Spend Tracker</p>
                </div>
                <Button size="sm" className="font-black uppercase text-[10px] tracking-widest h-10 px-6" onClick={() => setShowCostUpdateModal(true)}>Update Actual Cost</Button>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                <div className="p-6 bg-slate-50 rounded-2xl border border-slate-100">
                  <p className="text-[10px] font-black text-[#64748B] uppercase tracking-widest mb-2">Planned Budget</p>
                  <h4 className="text-2xl font-black text-[#0F172A]">₹{project.budget.toLocaleString('en-IN')}</h4>
                  {project.budgetHours ? (
                    <p className="text-xs text-slate-500 mt-1">{project.budgetHours} hours budgeted</p>
                  ) : null}
                </div>
                <div className="p-6 bg-slate-50 rounded-2xl border border-slate-100">
                  <p className="text-[10px] font-black text-[#64748B] uppercase tracking-widest mb-2">Actual Cost</p>
                  <h4 className="text-2xl font-black text-[#0F172A]">₹{project.actualCost.toLocaleString('en-IN')}</h4>
                </div>
                <div className="p-6 bg-slate-50 rounded-2xl border border-slate-100">
                  <p className="text-[10px] font-black text-[#64748B] uppercase tracking-widest mb-2">Cost Variance</p>
                  <div className="flex items-center gap-2">
                    <h4 className={cn("text-2xl font-black", variance > 90 ? "text-red-600" : "text-green-600")}>
                      {variance.toFixed(1)}%
                    </h4>
                    {variance > 90 && <Badge variant="error" className="text-[8px] px-1">OVER</Badge>}
                  </div>
                </div>
              </div>

              <div className="space-y-4">
                <h4 className="text-[10px] font-black text-[#94A3B8] uppercase tracking-widest">Real-time Budget Health</h4>
                <div className="h-4 bg-slate-100 rounded-full overflow-hidden border border-slate-200 p-[2px]">
                   <div 
                    className={cn(
                      "h-full rounded-full transition-all duration-1000",
                      variance > 90 ? "bg-red-500 shadow-[0_0_15px_rgba(239,68,68,0.3)]" : 
                      variance > 70 ? "bg-amber-500 shadow-[0_0_15px_rgba(245,158,11,0.3)]" : 
                      "bg-blue-600 shadow-[0_0_15px_rgba(37,99,235,0.3)]"
                    )} 
                    style={{ width: `${Math.min(100, variance)}%` }} 
                   />
                </div>
              </div>
            </Card>
          )}

          {activeTab === 'tasks' && (
             <div className="space-y-4">
               <div className="flex items-center justify-between mb-2">
                  <div className="flex gap-2">
                     <Button variant="outline" size="sm" className="h-9 px-4 font-black uppercase text-[9px] tracking-widest bg-white">
                        <LayoutGrid size={14} className="mr-2" /> Board View
                     </Button>
                     <Button variant="outline" size="sm" className="h-9 px-4 font-black uppercase text-[9px] tracking-widest bg-slate-50 text-blue-600 border-blue-100">
                        <List size={14} className="mr-2" /> List View
                     </Button>
                  </div>
                  <Button size="sm" className="h-9 px-6 font-black uppercase text-[9px] tracking-widest bg-blue-600" onClick={() => {
                    setEditingTask(null);
                    setShowTaskModal(true);
                  }}>
                     <Plus size={14} className="mr-2" /> Create Task
                  </Button>
               </div>

               {tasks.map((task, i) => (
                 <Card key={task.id} className="group hover:border-blue-300 transition-all border-slate-200 overflow-hidden shadow-sm">
                    <div className="p-5 flex items-center justify-between">
                      <div className="flex items-center gap-4 flex-1">
                        <div className={cn(
                          "w-2 h-10 rounded-full",
                          task.status === 'Done' ? 'bg-green-500' : task.status === 'In Progress' ? 'bg-blue-500' : task.status === 'Review' ? 'bg-amber-500' : 'bg-slate-300'
                        )} />
                        <div>
                          <div className="flex items-center gap-2">
                            <p className="text-sm font-black text-[#0F172A] uppercase tracking-tight">{task.title}</p>
                            <Badge variant={task.status === 'Done' ? 'success' : 'neutral'} className="text-[8px] uppercase tracking-tighter px-2">
                               {task.status}
                            </Badge>
                          </div>
                          <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mt-0.5">
                            Hours: {Number(task.estimatedHours || 0).toFixed(2).replace(/\.00$/, '')}h • Allocated: {task.subtasks.filter(s => !s.parentSubtaskId).reduce((sum, s) => sum + (s.estimatedHours || 0), 0).toFixed(2).replace(/\.00$/, '')}h • Assigned: {task.assigned || 'Unassigned'} • {task.subtasks.length} Subtasks
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center gap-6">
                        <div className="text-right">
                           <p className="text-[9px] font-black text-slate-400 uppercase tracking-widest mb-1">Priority</p>
                           <Badge variant={task.priority === 'Critical' ? 'error' : task.priority === 'High' ? 'warning' : 'neutral'} className="text-[8px] font-black px-3">
                              {task.priority}
                           </Badge>
                        </div>
                        <div className="flex gap-1">
                           <button onClick={() => {
                             setEditingTask(task);
                             setShowTaskModal(true);
                           }} className="p-2 hover:bg-blue-50 text-slate-400 hover:text-blue-600 rounded-lg transition-colors">
                              <Edit size={16} />
                           </button>
                           <button onClick={() => {
                             onUpdateTasks(tasks.filter(t => t.id !== task.id));
                             toast.error("Task Deleted");
                           }} className="p-2 hover:bg-red-50 text-slate-400 hover:text-red-600 rounded-lg transition-colors">
                              <Trash2 size={16} />
                           </button>
                        </div>
                      </div>
                    </div>
                    
                    <div className="px-5 pb-5 pt-0 border-t border-slate-50 bg-slate-50/50">
                      {task.subtasks.length > 0 ? (
                        isPM ? (
                          renderSubtaskTree(task)
                        ) : (
                          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-4">
                            {task.subtasks.filter(s => !s.parentSubtaskId).map(sub => (
                              <div 
                                key={sub.id} 
                                className="flex items-center gap-3 p-3 bg-white rounded-xl border border-slate-100 cursor-pointer hover:border-blue-200 transition-colors"
                                onClick={() => toggleSubtask(task.id, sub.id)}
                              >
                                <div className={cn(
                                  "w-5 h-5 rounded-md flex items-center justify-center border transition-all",
                                  sub.completed ? "bg-green-500 border-green-500 text-white" : "bg-white border-slate-200 text-transparent"
                                )}>
                                  <CheckCircle size={12} strokeWidth={3} />
                                </div>
                                <span className={cn("text-[11px] font-bold uppercase tracking-tight", sub.completed ? "text-slate-400 line-through" : "text-slate-600")}>
                                  {sub.title}{' '}
                                  <span className="text-[10px] font-black text-slate-400 uppercase tracking-widest">
                                    • {Number(sub.estimatedHours || 0).toFixed(2).replace(/\.00$/, '')}h{sub.assigned ? ` • ${sub.assigned}` : ''}
                                  </span>
                                </span>
                              </div>
                            ))}
                          </div>
                        )
                      ) : (
                        <div className="mt-4 text-[10px] font-black text-slate-400 uppercase tracking-widest">
                          No subtasks yet
                        </div>
                      )}

                      <div className="mt-4">
                        <Button
                          variant="outline"
                          size="sm"
                          className="h-9 px-4 font-black uppercase text-[9px] tracking-widest bg-white"
                          onClick={() => {
                            setSubtaskParentTask(task);
                            setSubtaskParentSubtaskId(null);
                            setEditingSubtaskId(null);
                            setShowSubtaskModal(true);
                          }}
                        >
                          <Plus size={14} className="mr-2" /> Add Subtask
                        </Button>
                      </div>
                    </div>
                 </Card>
               ))}
               
               {tasks.length === 0 && (
                 <div className="p-20 text-center border-2 border-dashed border-slate-200 rounded-2xl opacity-50">
                    <p className="text-sm font-black text-slate-400 uppercase tracking-widest">No tasks allocated to this project</p>
                 </div>
               )}
             </div>
          )}
          {activeTab === 'milestones' && (
            <div className="space-y-6">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-xl font-black text-[#0F172A] tracking-tight uppercase">Strategic Milestones</h3>
                  <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mt-1">Key deliverables & phase transitions</p>
                </div>
                <Button size="sm" className="h-9 px-6 font-black uppercase text-[9px] tracking-widest bg-blue-600" onClick={() => setShowMilestoneModal(true)}>
                  <Plus size={14} className="mr-2" /> Add Milestone
                </Button>
              </div>

              <div className="space-y-4">
                {milestones.map((milestone) => (
                  <Card key={milestone.id} className="p-6 border-slate-200 hover:border-blue-300 transition-all group shadow-sm bg-white">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-4">
                        <div className={cn(
                          "w-12 h-12 rounded-2xl flex items-center justify-center font-black text-lg border-2",
                          (milestone.status === 'completed' || milestone.status === 'Completed') ? "bg-green-50 border-green-100 text-green-600" :
                          (milestone.status === 'delayed' || milestone.status === 'Delayed') ? "bg-red-50 border-red-100 text-red-600" :
                          (milestone.status === 'in-progress' || milestone.status === 'In Progress') ? "bg-blue-50 border-blue-100 text-blue-600" :
                          "bg-slate-50 border-slate-100 text-slate-400"
                        )}>
                          <Target size={24} />
                        </div>
                        <div>
                          <h4 className="text-lg font-black text-[#0F172A] tracking-tight uppercase">{milestone.title}</h4>
                          <p className="text-xs text-slate-500 font-medium">{milestone.description}</p>
                        </div>
                      </div>
                      <div className="flex items-center gap-8 text-right">
                        <div>
                           <p className="text-[9px] font-black text-slate-400 uppercase tracking-widest mb-1">Due Date</p>
                           <p className="text-sm font-black text-[#0F172A] uppercase">{new Date(milestone.due_date).toLocaleDateString()}</p>
                        </div>
                        <div>
                           <p className="text-[9px] font-black text-slate-400 uppercase tracking-widest mb-1">Status</p>
                           <Badge variant={
                             (milestone.status === 'completed' || milestone.status === 'Completed') ? 'success' :
                             (milestone.status === 'delayed' || milestone.status === 'Delayed') ? 'error' :
                             (milestone.status === 'in-progress' || milestone.status === 'In Progress') ? 'info' : 'neutral'
                           } className="text-[8px] font-black px-3">
                              {milestone.status}
                           </Badge>
                        </div>
                      </div>
                    </div>
                  </Card>
                ))}

                {milestones.length === 0 && (
                  <div className="p-20 text-center border-2 border-dashed border-slate-200 rounded-2xl opacity-50">
                    <p className="text-sm font-black text-slate-400 uppercase tracking-widest">No strategic milestones defined</p>
                  </div>
                )}
              </div>
            </div>
          )}

          {activeTab === 'costing' && (
            <div className="space-y-8">
               <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-xl font-black text-[#0F172A] tracking-tight uppercase">Financial Controls</h3>
                  <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mt-1">Project baseline and budget modifications</p>
                </div>
                <Button size="sm" className="h-9 px-6 font-black uppercase text-[9px] tracking-widest bg-blue-600" onClick={() => setShowCostChangeModal(true)}>
                  <Plus size={14} className="mr-2" /> Request Budget Change
                </Button>
              </div>

              {activeBaseline ? (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                   <Card className="p-8 border-slate-200 bg-slate-50/30">
                      <div className="flex items-center justify-between mb-8">
                         <div className="p-3 bg-blue-600 text-white rounded-2xl shadow-lg shadow-blue-500/20">
                            <DollarSign size={24} />
                         </div>
                         <Badge variant="success" className="text-[10px] px-4 py-1 font-black">ACTIVE BASELINE</Badge>
                      </div>
                      <p className="text-[10px] font-black text-slate-400 uppercase tracking-[0.2em] mb-1">Total Approved Budget</p>
                      <h4 className="text-4xl font-black text-[#0F172A] tracking-tighter">₹{activeBaseline.amount.toLocaleString('en-IN')}</h4>
                      <div className="mt-8 pt-8 border-t border-slate-200/50">
                         <div className="flex justify-between items-center text-xs">
                            <span className="font-bold text-slate-400 uppercase tracking-widest">Baseline ID</span>
                            <span className="font-black text-slate-700">#BL-{activeBaseline.id}</span>
                         </div>
                         <div className="flex justify-between items-center text-xs mt-3">
                            <span className="font-bold text-slate-400 uppercase tracking-widest">Effective Since</span>
                            <span className="font-black text-slate-700">{new Date(activeBaseline.created_at).toLocaleDateString()}</span>
                         </div>
                      </div>
                   </Card>

                   <Card className="p-8 border-slate-200 bg-white">
                      <div className="flex items-center gap-3 mb-6">
                         <TrendingUp size={20} className="text-blue-600" />
                         <h4 className="text-[11px] font-black text-[#0F172A] uppercase tracking-widest">Health Indicators</h4>
                      </div>
                      <div className="space-y-6">
                        <div>
                          <div className="flex justify-between items-end mb-2">
                             <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Consumption Rate</span>
                             <span className="text-sm font-black text-slate-700">{((project.actualCost / activeBaseline.amount) * 100).toFixed(1)}%</span>
                          </div>
                          <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
                             <div 
                              className={cn(
                                "h-full rounded-full transition-all duration-1000",
                                (project.actualCost / activeBaseline.amount) > 0.9 ? "bg-red-500" : "bg-blue-600"
                              )} 
                              style={{ width: `${Math.min(100, (project.actualCost / activeBaseline.amount) * 100)}%` }} 
                             />
                          </div>
                        </div>
                        <div className="grid grid-cols-2 gap-4">
                           <div className="p-4 bg-slate-50 rounded-xl border border-slate-100">
                             <p className="text-[9px] font-black text-slate-400 uppercase tracking-widest mb-1">Utilized</p>
                             <p className="text-sm font-black text-slate-900">₹{project.actualCost.toLocaleString('en-IN')}</p>
                           </div>
                           <div className="p-4 bg-slate-50 rounded-xl border border-slate-100/50">
                             <p className="text-[9px] font-black text-slate-400 uppercase tracking-widest mb-1">Available</p>
                             <p className="text-sm font-black text-green-600">₹{(activeBaseline.amount - project.actualCost).toLocaleString('en-IN')}</p>
                           </div>
                        </div>
                      </div>
                   </Card>
                </div>
              ) : (
                <div className="p-20 text-center border-2 border-dashed border-slate-200 rounded-2xl">
                  <ShieldAlert size={48} className="mx-auto text-slate-200 mb-4" />
                  <h4 className="text-sm font-black text-slate-400 uppercase tracking-widest">No Active Baseline Found</h4>
                  <p className="text-xs text-slate-400 mt-2">Initialize project costing to enable financial tracking</p>
                </div>
              )}
            </div>
          )}

          {activeTab === 'team' && (
            <div className="space-y-6 animate-in fade-in duration-300">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-xl font-black text-[#0F172A] tracking-tight uppercase">Project Resource Matrix</h3>
                  <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mt-1">Personnel allocated to this deliverable</p>
                </div>
                <Button 
                  size="sm" 
                  className="h-9 px-6 font-black uppercase text-[9px] tracking-widest bg-blue-600"
                  onClick={() => setShowAddMemberModal(true)}
                >
                  <Plus size={14} className="mr-2" /> Add Member
                </Button>
              </div>
              
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {isLoadingMembers ? (
                  <div className="col-span-full py-12 flex justify-center italic text-slate-400">Loading resources...</div>
                ) : projectMembers.length === 0 ? (
                   <div className="col-span-full py-12 flex flex-col items-center justify-center bg-slate-50 rounded-2xl border-2 border-dashed border-slate-200">
                      <Users size={48} className="text-slate-300 mb-4" />
                      <p className="text-sm font-black text-slate-400 uppercase tracking-widest">No members allocated yet</p>
                   </div>
                ) : projectMembers.map((member, i) => (
                  <Card key={member.id} className="p-6 border-slate-200 hover:border-blue-300 transition-all group shadow-sm bg-white">
                    <div className="flex items-start justify-between mb-6">
                      <div className={cn("w-14 h-14 rounded-2xl flex items-center justify-center font-black text-lg border-2 border-white shadow-md bg-blue-100 text-blue-600")}>
                        {member.user_name?.split(' ').map((n: string) => n[0]).join('') || 'U'}
                      </div>
                      <Badge variant="neutral" className="text-[8px] font-black tracking-widest uppercase">{member.role}</Badge>
                    </div>
                    <div className="space-y-1 mb-6">
                      <h4 className="text-lg font-black text-[#0F172A] tracking-tight uppercase">{member.user_name}</h4>
                      <p className="text-[10px] font-bold text-blue-600 uppercase tracking-widest">{member.role}</p>
                      <p className="text-xs text-slate-400 font-medium">{member.user_email}</p>
                    </div>
                    <div className="pt-6 border-t border-slate-50 flex items-center justify-between">
                      <div className="flex flex-col">
                        <span className="text-[9px] font-black text-slate-400 uppercase tracking-widest">Status</span>
                        <span className="text-xs font-bold text-slate-700">Active</span>
                      </div>
                      <div className="flex flex-col text-right">
                        <span className="text-[9px] font-black text-slate-400 uppercase tracking-widest">Member ID</span>
                        <span className="text-xs font-bold text-[#0F172A]">#{member.user_id}</span>
                      </div>
                    </div>
                    <div className="mt-6 flex gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                      <Button variant="outline" size="sm" className="flex-1 h-9 font-black uppercase text-[9px] tracking-widest">Profile</Button>
                      <Button 
                        variant="outline" 
                        size="sm" 
                        className="flex-1 h-9 font-black uppercase text-[9px] tracking-widest text-red-600 border-red-100 hover:bg-red-50"
                        onClick={() => handleRemoveMember(member.user_id)}
                      >
                        Remove
                      </Button>
                    </div>
                  </Card>
                ))}
              </div>
            </div>
          )}

          {activeTab === 'documents' && (
            <ProjectDocumentsTab projectId={project.id} userRole={userRole} />
          )}

          {showAddMemberModal && (
            <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-[60] flex items-center justify-center p-4">
               <Card
                  className="w-full max-w-md p-8 animate-in zoom-in-95 duration-200"
                  style={{
                    maxHeight: "70vh",
                    overflowY: "auto",
                    overscrollBehavior: "contain",
                    WebkitOverflowScrolling: "touch",
                  }}
                >
                  <div className="flex items-center justify-between mb-6">
                    <h3 className="text-xl font-black text-[#0F172A] tracking-tight uppercase">Allocate Member</h3>
                    <button onClick={() => setShowAddMemberModal(false)} className="p-2 hover:bg-slate-100 rounded-full transition-colors">
                       <X size={20} className="text-slate-400" />
                    </button>
                  </div>
                  
                  <div className="mb-6">
                    <div className="relative">
                      <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={16} />
                      <Input 
                        placeholder="SEARCH EMPLOYEES (3+ CHARS)..." 
                        className="pl-10 h-10 text-[10px] font-black uppercase tracking-widest border-slate-200"
                        value={memberSearchTerm}
                        onChange={(e) => setMemberSearchTerm(e.target.value)}
                      />
                    </div>
                  </div>

                  <div className="space-y-3 max-h-[400px] overflow-y-auto pr-2 scrollbar-thin">
                    <p className="text-[9px] font-black text-slate-400 uppercase tracking-widest mb-2">Available Resources</p>
                    {allUsers
                      .filter(u => {
                        const notInProject = !projectMembers.some(m => m.user_id === u.id);
                        if (!notInProject) return false;
                        
                        const term = memberSearchTerm.trim().toLowerCase();
                        if (term.length < 3) return false; // Hide all until 3 chars typed
                        
                        return (
                          u.full_name?.toLowerCase().includes(term) || 
                          u.email?.toLowerCase().includes(term)
                        );
                      })
                      .map(user => (
                        <div 
                          key={user.id} 
                          onClick={() => toggleUserSelection(user.id.toString())}
                          className={`flex items-center justify-between p-4 rounded-xl transition-all border group cursor-pointer ${
                            selectedUsersForAllocation.includes(user.id.toString()) 
                              ? 'bg-blue-50 border-blue-400 ring-2 ring-blue-100 shadow-md' 
                              : 'bg-slate-50 border-transparent hover:bg-slate-100/80 hover:border-slate-200 shadow-sm'
                          }`}
                        >
                          <div className="flex items-center gap-3">
                            <div className="relative">
                              <div className={`w-10 h-10 rounded-xl flex items-center justify-center font-black text-xs shadow-sm transition-all duration-300 ${
                                selectedUsersForAllocation.includes(user.id.toString())
                                  ? 'bg-blue-600 border-blue-600 text-white scale-110 rotate-3'
                                  : 'bg-white border border-slate-200 text-blue-600'
                              }`}>
                                {selectedUsersForAllocation.includes(user.id.toString()) ? (
                                  <div className="animate-in zoom-in-50 duration-200">
                                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="4" className="w-5 h-5">
                                      <polyline points="20 6 9 17 4 12" />
                                    </svg>
                                  </div>
                                ) : (
                                  user.full_name?.split(' ').map((n: string) => n[0]).join('') || 'U'
                                )}
                              </div>
                              {selectedUsersForAllocation.includes(user.id.toString()) && (
                                <div className="absolute -top-1 -right-1 w-4 h-4 bg-green-500 rounded-full border-2 border-white shadow-sm flex items-center justify-center">
                                  <div className="w-1.5 h-1.5 bg-white rounded-full"></div>
                                </div>
                              )}
                            </div>
                            <div>
                              <p className={`font-black text-[11px] uppercase tracking-tight leading-none mb-1 transition-colors ${
                                selectedUsersForAllocation.includes(user.id.toString()) ? 'text-blue-700' : 'text-[#0F172A]'
                              }`}>{user.full_name}</p>
                              <p className={`text-[9px] font-bold uppercase tracking-widest transition-colors ${
                                selectedUsersForAllocation.includes(user.id.toString()) ? 'text-blue-400' : 'text-slate-400'
                              }`}>{user.email}</p>
                            </div>
                          </div>
                          <div 
                            className={`w-6 h-6 rounded-lg border-2 flex items-center justify-center transition-all ${
                              selectedUsersForAllocation.includes(user.id.toString())
                                ? 'bg-blue-600 border-blue-600 scale-110'
                                : 'border-slate-200 group-hover:border-blue-400 bg-white'
                            }`}
                          >
                            {selectedUsersForAllocation.includes(user.id.toString()) && (
                              <div className="w-2.5 h-1.5 border-b-2 border-l-2 border-white -rotate-45 mb-0.5"></div>
                            )}
                          </div>
                        </div>
                      ))
                    }
                    {allUsers.filter(u => {
                       const notInProject = !projectMembers.some(m => m.user_id === u.id);
                       if (!notInProject) return false;
                       const term = memberSearchTerm.trim().toLowerCase();
                       return term.length >= 3 && (u.full_name?.toLowerCase().includes(term) || u.email?.toLowerCase().includes(term));
                    }).length === 0 && memberSearchTerm.length >= 3 && (
                      <div className="py-8 text-center bg-slate-50 rounded-xl border border-dashed border-slate-200">
                        <p className="text-[9px] font-black text-slate-400 uppercase tracking-widest">No matching resources found</p>
                      </div>
                    )}
                    {memberSearchTerm.length < 3 && (
                       <div className="py-12 flex flex-col items-center justify-center bg-slate-50/50 rounded-3xl border border-dashed border-slate-200 transition-all duration-300 group">
                          <div className="w-12 h-12 rounded-2xl bg-white border border-slate-100 flex items-center justify-center mb-4 shadow-sm group-hover:scale-110 transition-transform">
                             <Search className="text-blue-500 animate-pulse" size={20} />
                          </div>
                          <p className="text-[10px] font-black text-[#0F172A] uppercase tracking-widest mb-1">Start Typing to Search</p>
                          <p className="text-[8px] text-slate-400 font-bold uppercase tracking-[0.2em]">Enter 3 or more characters</p>
                       </div>
                    )}
                  </div>

                  {selectedUsersForAllocation.length > 0 && (
                    <div className="mt-8 space-y-4 animate-in slide-in-from-bottom-4 duration-300">
                       <Button 
                          className="w-full bg-blue-600 hover:bg-blue-700 text-white h-12 rounded-2xl font-black uppercase text-[10px] tracking-widest shadow-lg shadow-blue-500/20 active:scale-95 transition-all flex items-center justify-center gap-3"
                          onClick={handleBulkAddMembers}
                          disabled={isLoadingMembers}
                       >
                          {isLoadingMembers ? (
                             <div className="flex items-center gap-2">
                                <div className="w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin"></div>
                                <span>Alloacting...</span>
                             </div>
                          ) : (
                             <>
                                <span>Add {selectedUsersForAllocation.length} Selected Members</span>
                                <div className="w-5 h-5 rounded-lg bg-blue-500/30 flex items-center justify-center text-[8px]">
                                   {selectedUsersForAllocation.length}
                                </div>
                             </>
                          )}
                       </Button>
                       <Button 
                          variant="ghost" 
                          className="w-full text-[9px] font-black uppercase text-slate-400 tracking-widest hover:text-red-500 hover:bg-transparent"
                          onClick={() => setSelectedUsersForAllocation([])}
                       >
                          Clear Selection
                       </Button>
                    </div>
                  )}

                  <div className="mt-8 pt-6 border-t border-slate-100 italic text-[9px] text-slate-400 font-medium text-center uppercase tracking-widest">
                    Authorized personnel will receive a strategic notification upon allocation.
                  </div>
               </Card>
            </div>
          )}

        </div>

        <div className="space-y-8">
          <Card className="p-6 border-slate-200 shadow-sm">
            <h3 className="text-[11px] font-black text-[#0F172A] uppercase tracking-widest mb-6">Execution Timeline</h3>
            <div className="space-y-6">
              <div className="flex items-center gap-4">
                <div className="p-3 bg-blue-50 text-blue-600 rounded-xl border border-blue-100 shadow-sm">
                  <Calendar size={20} />
                </div>
                <div>
                  <p className="text-[9px] font-black text-[#64748B] uppercase tracking-widest">Kickoff Date</p>
                  <p className="text-sm font-black text-[#0F172A] tracking-tight">{project.start}</p>
                </div>
              </div>
              <div className="flex items-center gap-4">
                <div className="p-3 bg-purple-50 text-purple-600 rounded-xl border border-purple-100 shadow-sm">
                  <Clock size={20} />
                </div>
                <div>
                  <p className="text-[9px] font-black text-[#64748B] uppercase tracking-widest">Project Deadline</p>
                  <p className="text-sm font-black text-[#0F172A] tracking-tight">{project.end}</p>
                </div>
              </div>
            </div>
            
            <div className="mt-8 pt-8 border-t border-slate-100">
               <div className="flex items-center justify-between mb-2">
                  <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Days Remaining</p>
                  <Badge variant="info" className="text-[10px] px-3">45 DAYS</Badge>
               </div>
               <div className="w-full h-1.5 bg-slate-100 rounded-full overflow-hidden">
                  <div className="h-full bg-blue-600 rounded-full w-[65%]" />
               </div>
            </div>
          </Card>

          <Card className="p-6 border-slate-200 shadow-sm">
            <h3 className="text-[11px] font-black text-[#0F172A] uppercase tracking-widest mb-6">Core Delivery Team</h3>
            <div className="space-y-4">
              {projectMembers.slice(0, 4).map((member, i) => (
                <div key={member.id} className="flex items-center justify-between group cursor-pointer p-2 hover:bg-slate-50 rounded-xl transition-all">
                  <div className="flex items-center gap-3">
                    <div className={cn("w-9 h-9 rounded-xl flex items-center justify-center font-black text-xs border border-white shadow-sm bg-blue-100 text-blue-600")}>
                      {member.user_name?.split(' ').map((n: string) => n[0]).join('') || 'U'}
                    </div>
                    <div>
                      <p className="text-xs font-black text-[#0F172A] tracking-tight uppercase">{member.user_name}</p>
                      <p className="text-[9px] font-bold text-[#64748B] uppercase tracking-widest">{member.role}</p>
                    </div>
                  </div>
                  <ChevronRight size={14} className="text-slate-300 opacity-0 group-hover:opacity-100 transition-opacity" />
                </div>
              ))}
            </div>
            <Button 
                variant="outline" 
                size="sm" 
                className="w-full mt-6 h-10 font-black uppercase text-[9px] tracking-widest"
                onClick={() => setActiveTab('team')}
            >
                Manage Resources
            </Button>
          </Card>
        </div>
      </div>

      {/* Subtask Creation Modal */}
      {showSubtaskModal && subtaskParentTask && (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <Card
            className="w-full max-w-lg p-8 space-y-6 animate-in zoom-in-95 duration-200"
            style={{
              maxHeight: "70vh",
              overflowY: "auto",
              overscrollBehavior: "contain",
              WebkitOverflowScrolling: "touch",
            }}
          >
            <div className="flex items-center justify-between border-b border-slate-100 pb-4">
              <h3 className="text-xl font-black text-[#0F172A] tracking-tight uppercase">
                {editingSubtaskId ? 'Edit Subtask' : 'New Subtask'}
              </h3>
              <button onClick={() => {
                setShowSubtaskModal(false);
                setSubtaskParentTask(null);
                setSubtaskParentSubtaskId(null);
                setEditingSubtaskId(null);
              }} className="p-2 hover:bg-slate-100 rounded-full transition-colors">
                <X size={20} className="text-slate-400" />
              </button>
            </div>

            <div className="text-[10px] font-black text-slate-400 uppercase tracking-widest">
              {(() => {
                const parentSub = subtaskParentSubtaskId
                  ? subtaskParentTask.subtasks.find(s => s.id === subtaskParentSubtaskId)
                  : null;
                const cap = parentSub
                  ? parentSub.estimatedHours
                  : subtaskParentTask.estimatedHours;
                const used = subtaskParentTask.subtasks
                  .filter(s => (s.parentSubtaskId || null) === (subtaskParentSubtaskId || null))
                  .reduce((sum, s) => sum + (s.estimatedHours || 0), 0);
                const remaining = Math.max(cap - used, 0)
                  .toFixed(2)
                  .replace(/\.00$/, '');
                return (
                  <>
                    Parent Task: {subtaskParentTask.title}
                    {parentSub ? (
                      <> • Parent Subtask: {parentSub.title}</>
                    ) : null}
                    {' '}• Remaining: {remaining}h
                  </>
                );
              })()}
            </div>

            <form onSubmit={handleSubtaskSubmit} className="space-y-5">
              <div className="space-y-2">
                <label className="text-[10px] font-black text-slate-500 uppercase tracking-widest">Subtask Title</label>
                <Input
                  name="subtask_title"
                  defaultValue={
                    editingSubtaskId
                      ? (subtaskParentTask.subtasks.find(s => s.id === editingSubtaskId)?.title || '')
                      : ''
                  }
                  placeholder="e.g. Interview stakeholders"
                  required
                />
              </div>

              <div className="space-y-2">
                <label className="text-[10px] font-black text-slate-500 uppercase tracking-widest">Estimated Hours</label>
                <Input
                  name="subtask_hours"
                  type="number"
                  min={0}
                  step={0.25}
                  defaultValue={
                    editingSubtaskId
                      ? (subtaskParentTask.subtasks.find(s => s.id === editingSubtaskId)?.estimatedHours || 0)
                      : ''
                  }
                  placeholder="e.g. 4"
                  required
                />
              </div>

              <div className="space-y-2">
                <label className="text-[10px] font-black text-slate-500 uppercase tracking-widest">Resource (Optional)</label>
                <select
                  name="subtask_assigned"
                  defaultValue={
                    editingSubtaskId
                      ? (subtaskParentTask.subtasks.find(s => s.id === editingSubtaskId)?.assigned || '')
                      : ''
                  }
                  className="w-full px-4 py-3 bg-slate-50 border border-slate-200 rounded-xl text-xs font-black uppercase tracking-widest focus:outline-none focus:ring-2 focus:ring-blue-600/20 focus:border-blue-600 transition-all cursor-pointer shadow-sm"
                >
                  <option value="">Unassigned</option>
                  {projectMembers.map(member => (
                    <option key={member.user_id} value={member.user_email}>
                      {member.user_name}
                    </option>
                  ))}
                </select>
              </div>

              <div className="flex gap-3 pt-4 border-t border-slate-100 mt-6">
                <Button
                  variant="outline"
                  className="flex-1 font-black uppercase text-[10px] tracking-widest h-11"
                  type="button"
                  onClick={() => {
                    setShowSubtaskModal(false);
                    setSubtaskParentTask(null);
                    setSubtaskParentSubtaskId(null);
                    setEditingSubtaskId(null);
                  }}
                >
                  Cancel
                </Button>
                <Button className="flex-1 bg-blue-600 font-black uppercase text-[10px] tracking-widest h-11" type="submit">
                  {editingSubtaskId ? 'Save Changes' : 'Create Subtask'}
                </Button>
              </div>
            </form>
          </Card>
        </div>
      )}

      {/* Task Creation/Edit Modal */}
      {showTaskModal && (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <Card
            className="w-full max-w-lg p-8 space-y-6 animate-in zoom-in-95 duration-200"
            style={{
              maxHeight: "70vh",
              overflowY: "auto",
              overscrollBehavior: "contain",
              WebkitOverflowScrolling: "touch",
            }}
          >
            <div className="flex items-center justify-between border-b border-slate-100 pb-4">
              <h3 className="text-xl font-black text-[#0F172A] tracking-tight uppercase">{editingTask ? 'Edit Task' : 'New Strategic Task'}</h3>
              <button onClick={() => setShowTaskModal(false)} className="p-2 hover:bg-slate-100 rounded-full transition-colors">
                <X size={20} className="text-slate-400" />
              </button>
            </div>
            <form onSubmit={handleTaskSubmit} className="space-y-5">
              <div className="space-y-2">
                <label className="text-[10px] font-black text-slate-500 uppercase tracking-widest">Task Title</label>
                <Input name="title" defaultValue={editingTask?.title} placeholder="e.g. Database Schema Migration" required />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <label className="text-[10px] font-black text-slate-500 uppercase tracking-widest">Priority</label>
                  <select name="priority" defaultValue={editingTask?.priority || 'Medium'} className="w-full px-4 py-2 bg-slate-50 border border-slate-200 rounded-lg text-sm font-bold focus:outline-none focus:ring-1 focus:ring-blue-600">
                    <option value="Critical">Critical</option>
                    <option value="High">High</option>
                    <option value="Medium">Medium</option>
                    <option value="Low">Low</option>
                  </select>
                </div>
                <div className="space-y-2">
                  <label className="text-[10px] font-black text-slate-500 uppercase tracking-widest">Initial Status</label>
                  <select name="status" defaultValue={editingTask?.status || 'To Do'} className="w-full px-4 py-2 bg-slate-50 border border-slate-200 rounded-lg text-sm font-bold focus:outline-none focus:ring-1 focus:ring-blue-600">
                    <option value="To Do">To Do</option>
                    <option value="In Progress">In Progress</option>
                    <option value="Review">Review</option>
                    <option value="Done">Done</option>
                  </select>
                </div>
              </div>
              <div className="space-y-2">
                <label className="text-[10px] font-black text-slate-500 uppercase tracking-widest">Estimated Hours</label>
                <Input
                  name="hours"
                  type="number"
                  min={0}
                  step={0.25}
                  defaultValue={editingTask?.estimatedHours ?? ''}
                  placeholder="e.g. 10.5"
                  required
                />
              </div>
              <div className="space-y-2">
                <label className="text-[10px] font-black text-slate-500 uppercase tracking-widest">Resource Allocation</label>
                <select 
                  name="assigned" 
                  defaultValue={editingTask?.assigned} 
                  className="w-full px-4 py-3 bg-slate-50 border border-slate-200 rounded-xl text-xs font-black uppercase tracking-widest focus:outline-none focus:ring-2 focus:ring-blue-600/20 focus:border-blue-600 transition-all cursor-pointer shadow-sm"
                >
                  <option value="">Unassigned</option>
                  {projectMembers.map(member => (
                    <option key={member.user_id} value={member.user_email}>
                      {member.user_name}
                    </option>
                  ))}
                </select>
              </div>
              <div className="flex gap-3 pt-4 border-t border-slate-100 mt-6">
                <Button variant="outline" className="flex-1 font-black uppercase text-[10px] tracking-widest h-11" type="button" onClick={() => setShowTaskModal(false)}>Cancel</Button>
                <Button className="flex-1 bg-blue-600 font-black uppercase text-[10px] tracking-widest h-11" type="submit">{editingTask ? 'Save Changes' : 'Allocate Task'}</Button>
              </div>
            </form>
          </Card>
        </div>
      )}

      {/* Milestone Modal */}
      {showMilestoneModal && (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4 text-left">
          <Card
            className="w-full max-w-lg p-8 space-y-6 animate-in zoom-in-95 duration-200"
            style={{
              maxHeight: "70vh",
              overflowY: "auto",
              overscrollBehavior: "contain",
              WebkitOverflowScrolling: "touch",
            }}
          >
            <div className="flex items-center justify-between border-b border-slate-100 pb-4 text-left">
              <h3 className="text-xl font-black text-[#0F172A] tracking-tight uppercase">New Strategic Milestone</h3>
              <button onClick={() => setShowMilestoneModal(false)} className="p-2 hover:bg-slate-100 rounded-full transition-colors">
                <X size={20} className="text-slate-400" />
              </button>
            </div>
            <form onSubmit={handleMilestoneSubmit} className="space-y-5">
              <div className="space-y-2">
                <label className="text-[10px] font-black text-slate-500 uppercase tracking-widest">Milestone Title</label>
                <Input name="title" placeholder="e.g. Phase 1 Design Completion" required />
              </div>
              <div className="space-y-2">
                <label className="text-[10px] font-black text-slate-500 uppercase tracking-widest">Description</label>
                <Input name="description" placeholder="Short description of the deliverable" required />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <label className="text-[10px] font-black text-slate-500 uppercase tracking-widest">Due Date</label>
                  <Input type="date" name="due_date" required />
                </div>
                <div className="space-y-2">
                  <label className="text-[10px] font-black text-slate-500 uppercase tracking-widest">Initial Status</label>
                  <select name="status" className="w-full px-4 py-2 bg-slate-50 border border-slate-200 rounded-lg text-sm font-bold focus:outline-none focus:ring-1 focus:ring-blue-600">
                    <option value="pending">Pending</option>
                    <option value="in-progress">In Progress</option>
                  </select>
                </div>
              </div>
              <div className="flex gap-3 pt-4 border-t border-slate-100 mt-6">
                <Button variant="outline" className="flex-1 font-black uppercase text-[10px] tracking-widest h-11" type="button" onClick={() => setShowMilestoneModal(false)}>Cancel</Button>
                <Button className="flex-1 bg-blue-600 font-black uppercase text-[10px] tracking-widest h-11" type="submit">Establish Milestone</Button>
              </div>
            </form>
          </Card>
        </div>
      )}

      {/* Cost Change Request Modal */}
      {showCostChangeModal && (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4 text-left">
          <Card
            className="w-full max-w-lg p-8 space-y-6 animate-in zoom-in-95 duration-200"
            style={{
              maxHeight: "70vh",
              overflowY: "auto",
              overscrollBehavior: "contain",
              WebkitOverflowScrolling: "touch",
            }}
          >
            <div className="flex items-center justify-between border-b border-slate-100 pb-4 text-left">
              <h3 className="text-xl font-black text-[#0F172A] tracking-tight uppercase">Request Budget Modification</h3>
              <button onClick={() => setShowCostChangeModal(false)} className="p-2 hover:bg-slate-100 rounded-full transition-colors">
                <X size={20} className="text-slate-400" />
              </button>
            </div>
            <div className="p-4 bg-blue-50/50 rounded-xl border border-blue-100 flex justify-between items-center text-left">
               <div>
                  <p className="text-[9px] font-black text-blue-600 uppercase tracking-widest">Active Baseline</p>
                  <p className="text-lg font-black text-[#0F172A]">₹{activeBaseline?.amount.toLocaleString('en-IN')}</p>
               </div>
               <ArrowUpRight className="text-blue-400" size={20} />
            </div>
            <form onSubmit={handleCostChangeSubmit} className="space-y-5">
              <div className="space-y-2">
                <label className="text-[10px] font-black text-slate-500 uppercase tracking-widest">Proposed Total Amount (₹)</label>
                <Input type="number" name="amount" placeholder="e.g. 150000" required />
              </div>
              <div className="space-y-2 text-left">
                <label className="text-[10px] font-black text-slate-500 uppercase tracking-widest">Rational Justification</label>
                <textarea 
                  name="reason" 
                  className="w-full h-24 p-4 bg-slate-50 border border-slate-200 rounded-lg text-sm font-bold focus:outline-none focus:ring-1 focus:ring-blue-600"
                  placeholder="Explain why this change is necessary..."
                  required
                />
              </div>
              <div className="space-y-2 text-left">
                <label className="text-[10px] font-black text-slate-500 uppercase tracking-widest">Project Impact Analysis</label>
                <textarea 
                  name="impact" 
                  className="w-full h-24 p-4 bg-slate-50 border border-slate-200 rounded-lg text-sm font-bold focus:outline-none focus:ring-1 focus:ring-blue-600"
                  placeholder="Detail the impact on timeline and quality..."
                  required
                />
              </div>
              <div className="flex gap-3 pt-4 border-t border-slate-100 mt-6">
                <Button variant="outline" className="flex-1 font-black uppercase text-[10px] tracking-widest h-11" type="button" onClick={() => setShowCostChangeModal(false)}>Cancel</Button>
                <Button className="flex-1 bg-blue-600 font-black uppercase text-[10px] tracking-widest h-11" type="submit">Submit for Authorization</Button>
              </div>
            </form>
          </Card>
        </div>
      )}
    </div>
  );
};

// Roles that can upload/delete project documents from the UI. Backend
// re-checks regardless, so this is purely about hiding the buttons for
// users who'll just get a 403.
const DOC_MANAGE_ROLES: ReadonlyArray<UserRole> = [
  'bd', 'bd manager', 'coo', 'admin', 'super admin', 'ceo',
];

const ProjectDocumentsTab = ({ projectId, userRole }: { projectId: number | string; userRole: UserRole }) => {
  const [docs, setDocs] = React.useState<any[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [showForm, setShowForm] = React.useState(false);
  const [docType, setDocType] = React.useState<string>('Workorder');
  const [remark, setRemark] = React.useState('');
  const [file, setFile] = React.useState<File | null>(null);
  const [uploading, setUploading] = React.useState(false);
  const [deletingId, setDeletingId] = React.useState<number | null>(null);
  const fileInputRef = React.useRef<HTMLInputElement | null>(null);

  const canManage = DOC_MANAGE_ROLES.includes(userRole);

  const fetchDocs = async () => {
    setLoading(true);
    try {
      const res = await client.get(ENDPOINTS.PROJECTS.DOCUMENTS(projectId));
      setDocs(res.data || []);
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Failed to load documents');
      setDocs([]);
    } finally {
      setLoading(false);
    }
  };

  React.useEffect(() => { fetchDocs(); }, [projectId]);

  const handleUpload = async () => {
    if (!file) { toast.error('Pick a file first'); return; }
    setUploading(true);
    try {
      const form = new FormData();
      form.append('file', file);
      const params = new URLSearchParams({ doc_type: docType });
      if (remark.trim()) params.set('remark', remark.trim());
      await client.post(
        `${ENDPOINTS.PROJECTS.DOCUMENT_UPLOAD(projectId)}?${params.toString()}`,
        form,
      );
      toast.success('Document uploaded');
      setShowForm(false);
      setFile(null);
      setRemark('');
      setDocType('Workorder');
      fetchDocs();
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Upload failed');
    } finally {
      setUploading(false);
    }
  };

  const handleDownload = async (doc: any) => {
    try {
      const res = await client.get(ENDPOINTS.PROJECTS.DOCUMENT_DOWNLOAD(projectId, doc.id), { responseType: 'blob' });
      const blobUrl = window.URL.createObjectURL(res.data as Blob);
      const a = document.createElement('a');
      a.href = blobUrl;
      a.download = doc.original_filename || 'document';
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => window.URL.revokeObjectURL(blobUrl), 60000);
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Failed to download');
    }
  };

  const handleDelete = async (doc: any) => {
    if (!confirm(`Delete "${doc.original_filename}"?`)) return;
    setDeletingId(doc.id);
    try {
      await client.delete(ENDPOINTS.PROJECTS.DOCUMENT_DELETE(projectId, doc.id));
      toast.success('Document deleted');
      fetchDocs();
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Failed to delete');
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-xl font-black text-[#0F172A] tracking-tight uppercase">Project Documents</h3>
          <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mt-1">
            Workorders, contracts and supporting paperwork
          </p>
        </div>
        {canManage && (
          <Button
            size="sm"
            className="h-9 px-6 font-black uppercase text-[9px] tracking-widest bg-blue-600"
            onClick={() => setShowForm(s => !s)}
          >
            <Upload size={14} className="mr-2" /> Upload
          </Button>
        )}
      </div>

      {showForm && canManage && (
        <Card className="p-6 border-blue-200 bg-blue-50/30 animate-in slide-in-from-top-2 duration-200">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="space-y-2">
              <label className="text-[9px] font-black text-slate-500 uppercase tracking-widest">Type</label>
              <select
                value={docType}
                onChange={e => setDocType(e.target.value)}
                className="w-full h-11 px-3 rounded-md border border-slate-200 bg-white text-sm font-bold text-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-500/30"
              >
                <option value="Workorder">Workorder</option>
                <option value="Contract">Contract</option>
                <option value="Other">Other</option>
              </select>
            </div>
            <div className="space-y-2">
              <label className="text-[9px] font-black text-slate-500 uppercase tracking-widest">Remark</label>
              <Input value={remark} onChange={e => setRemark(e.target.value)} placeholder="Optional" className="h-11" />
            </div>
            <div className="space-y-2">
              <label className="text-[9px] font-black text-slate-500 uppercase tracking-widest">File</label>
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                className="w-full h-11 flex items-center gap-3 px-4 rounded-md border border-dashed border-slate-300 bg-white hover:border-blue-400 transition-colors text-left"
              >
                {file ? (
                  <span className="text-xs font-bold text-blue-700 truncate">{file.name}</span>
                ) : (
                  <span className="text-xs text-slate-400">Click to select…</span>
                )}
              </button>
              <input
                ref={fileInputRef}
                type="file"
                className="hidden"
                accept="application/pdf,image/jpeg,image/png,image/webp,image/heic,image/gif,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/vnd.ms-excel,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,text/plain"
                onChange={e => setFile(e.target.files?.[0] || null)}
              />
            </div>
          </div>
          <p className="mt-3 text-[10px] text-slate-400">PDF · JPG · PNG · Word · Excel · 25 MB max</p>
          <div className="mt-4 flex justify-end gap-3">
            <Button variant="outline" size="sm" onClick={() => { setShowForm(false); setFile(null); }}>Cancel</Button>
            <Button size="sm" onClick={handleUpload} disabled={!file || uploading} className="bg-blue-600">
              {uploading ? <><Loader2 size={12} className="animate-spin mr-2" />Uploading…</> : 'Upload'}
            </Button>
          </div>
        </Card>
      )}

      {loading ? (
        <div className="p-12 flex justify-center"><Loader2 className="w-6 h-6 text-blue-600 animate-spin" /></div>
      ) : docs.length === 0 ? (
        <Card className="p-12 border-dashed border-2 border-slate-200 bg-slate-50/50 text-center">
          <Paperclip size={36} className="mx-auto text-slate-300 mb-3" />
          <p className="text-sm font-black text-slate-500 uppercase tracking-widest">No documents yet</p>
          <p className="text-xs text-slate-400 mt-1">
            {canManage ? 'Upload the workorder or any related paperwork.' : 'BD, COO, or admin can upload project documents.'}
          </p>
        </Card>
      ) : (
        <Card className="overflow-hidden border-slate-200 shadow-sm">
          <table className="w-full text-left">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-200">
                <th className="px-5 py-3 text-[9px] font-black text-slate-500 uppercase tracking-widest">Filename</th>
                <th className="px-5 py-3 text-[9px] font-black text-slate-500 uppercase tracking-widest">Type</th>
                <th className="px-5 py-3 text-[9px] font-black text-slate-500 uppercase tracking-widest">Uploaded by</th>
                <th className="px-5 py-3 text-[9px] font-black text-slate-500 uppercase tracking-widest">Uploaded on</th>
                <th className="px-5 py-3 text-[9px] font-black text-slate-500 uppercase tracking-widest">Remark</th>
                <th className="px-5 py-3 text-[9px] font-black text-slate-500 uppercase tracking-widest text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {docs.map((d: any) => (
                <tr key={d.id} className="hover:bg-slate-50/60">
                  <td className="px-5 py-4 text-sm font-black text-slate-800">{d.original_filename}</td>
                  <td className="px-5 py-4">
                    <span className="text-[9px] font-black text-slate-600 uppercase tracking-widest px-2 py-1 rounded bg-slate-100">{d.doc_type}</span>
                  </td>
                  <td className="px-5 py-4 text-xs font-bold text-slate-600">{d.uploaded_by_name || '—'}</td>
                  <td className="px-5 py-4 text-xs font-bold text-slate-500 tabular-nums">
                    {d.uploaded_at ? new Date(d.uploaded_at).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' }) : '—'}
                  </td>
                  <td className="px-5 py-4 text-xs italic text-slate-500 max-w-[220px] truncate" title={d.remark || ''}>{d.remark || '—'}</td>
                  <td className="px-5 py-4 text-right">
                    <div className="flex justify-end gap-2">
                      <Button variant="outline" size="sm" className="h-8 w-8 p-0" onClick={() => handleDownload(d)} title="Download">
                        <Download size={12} />
                      </Button>
                      {canManage && (
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-8 w-8 p-0 text-red-500 hover:bg-red-50"
                          onClick={() => handleDelete(d)}
                          disabled={deletingId === d.id}
                          title="Delete"
                        >
                          <Trash2 size={12} />
                        </Button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
};
