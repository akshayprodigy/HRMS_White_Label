import React, { useState, useEffect } from 'react';
import {
  Activity,
  ChevronDown,
  ChevronRight,
  Users,
  CheckCircle2,
  Clock,
  AlertTriangle,
  Briefcase,
  TrendingUp,
  Search,
} from 'lucide-react';
import { Card, Badge, cn } from './ui-elements';
import { toast } from 'sonner';
import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';

interface ManagerInfo {
  user_id: number;
  user_name: string;
  user_email: string;
  role: string;
}

interface ProjectOverview {
  id: number;
  name: string;
  code: string;
  status: string;
  created_at: string | null;
  parent_project_id: number | null;
  parent_project_name: string | null;
  child_project_ids: number[];
  managers: ManagerInfo[];
  total_tasks: number;
  completed_tasks: number;
  completion_pct: number;
  task_status_breakdown: Record<string, number>;
}

const StatusBadge = ({ pct }: { pct: number }) => {
  if (pct >= 80) return <Badge variant="success">{pct}%</Badge>;
  if (pct >= 40) return <Badge variant="warning">{pct}%</Badge>;
  return <Badge variant="neutral">{pct}%</Badge>;
};

const ProgressBar = ({ pct }: { pct: number }) => (
  <div className="flex items-center gap-2 min-w-[120px]">
    <div className="flex-1 h-2 bg-slate-100 rounded-full overflow-hidden">
      <div
        className={cn(
          'h-full rounded-full transition-all duration-500',
          pct >= 80 ? 'bg-green-500' : pct >= 40 ? 'bg-amber-400' : 'bg-blue-500',
        )}
        style={{ width: `${pct}%` }}
      />
    </div>
    <span className="text-xs font-bold text-[#0F172A] w-8 text-right">{pct}%</span>
  </div>
);

export const COODashboardView = () => {
  const [projects, setProjects] = useState<ProjectOverview[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [expandedIds, setExpandedIds] = useState<Set<number>>(new Set());

  useEffect(() => {
    fetchOverview();
  }, []);

  const fetchOverview = async () => {
    try {
      setIsLoading(true);
      const res = await client.get(ENDPOINTS.PROJECTS.COO_OVERVIEW);
      setProjects(res.data);
      // Auto-expand master projects (those with children)
      const withChildren = res.data
        .filter((p: ProjectOverview) => p.child_project_ids.length > 0)
        .map((p: ProjectOverview) => p.id);
      setExpandedIds(new Set(withChildren));
    } catch {
      toast.error('Failed to load COO overview');
    } finally {
      setIsLoading(false);
    }
  };

  const toggleExpand = (id: number, e: React.MouseEvent) => {
    e.stopPropagation();
    setExpandedIds(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  // Split into master (no parent) and child projects
  const masterProjects = projects.filter(p => !p.parent_project_id);
  const childMap = new Map<number, ProjectOverview[]>();
  projects.forEach(p => {
    if (p.parent_project_id) {
      const arr = childMap.get(p.parent_project_id) || [];
      arr.push(p);
      childMap.set(p.parent_project_id, arr);
    }
  });

  const filtered = masterProjects.filter(p =>
    !searchQuery ||
    p.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    p.code.toLowerCase().includes(searchQuery.toLowerCase()) ||
    p.managers.some(m => m.user_name.toLowerCase().includes(searchQuery.toLowerCase())),
  );

  // Summary stats
  const totalProjects = projects.length;
  const activeProjects = projects.filter(p => p.status === 'active').length;
  const totalTasks = projects.reduce((a, p) => a + p.total_tasks, 0);
  const completedTasks = projects.reduce((a, p) => a + p.completed_tasks, 0);
  const overallPct = totalTasks > 0 ? Math.round((completedTasks / totalTasks) * 100) : 0;
  const atRiskCount = projects.filter(p => p.total_tasks > 0 && p.completion_pct < 30).length;

  const renderProjectRow = (proj: ProjectOverview, isChild = false) => {
    const children = childMap.get(proj.id) || [];
    const hasChildren = children.length > 0;
    const isExpanded = expandedIds.has(proj.id);

    return (
      <React.Fragment key={proj.id}>
        <tr className={cn(
          'border-b border-[#E5E7EB] transition-colors',
          isChild ? 'bg-slate-50/60 hover:bg-violet-50/30' : 'hover:bg-blue-50/20',
        )}>
          <td className="px-4 py-3">
            <div className={cn('flex items-center gap-2', isChild && 'pl-8')}>
              {hasChildren && (
                <button
                  onClick={e => toggleExpand(proj.id, e)}
                  className="p-0.5 rounded hover:bg-slate-200 transition-colors"
                >
                  {isExpanded
                    ? <ChevronDown className="w-4 h-4 text-slate-500" />
                    : <ChevronRight className="w-4 h-4 text-slate-500" />}
                </button>
              )}
              {!hasChildren && <span className="w-5" />}
              <div className={cn(
                'w-8 h-8 rounded-lg flex items-center justify-center text-[10px] font-bold flex-shrink-0',
                isChild ? 'bg-violet-100 text-violet-700' : 'bg-blue-100 text-blue-700',
              )}>
                {isChild ? '↳' : <Briefcase className="w-4 h-4" />}
              </div>
              <div>
                <p className={cn('text-sm font-semibold text-[#0F172A]', isChild && 'text-slate-700')}>
                  {proj.name}
                </p>
                <p className="text-[10px] text-[#64748B] font-mono">{proj.code}</p>
              </div>
              {isChild && (
                <span className="text-[9px] font-bold px-1.5 py-0.5 rounded bg-violet-100 text-violet-600 uppercase">sub</span>
              )}
            </div>
          </td>

          <td className="px-4 py-3">
            {proj.managers.length > 0 ? (
              <div className="flex flex-col gap-1">
                {proj.managers.map(m => (
                  <div key={m.user_id} className="flex items-center gap-1.5">
                    <div className="w-6 h-6 rounded-full bg-blue-100 text-blue-700 flex items-center justify-center text-[9px] font-bold flex-shrink-0">
                      {m.user_name.split(' ').map(n => n[0]).join('').slice(0, 2)}
                    </div>
                    <span className="text-xs text-[#334155]">{m.user_name}</span>
                  </div>
                ))}
              </div>
            ) : (
              <span className="text-xs text-slate-400 italic">Unassigned</span>
            )}
          </td>

          <td className="px-4 py-3">
            <Badge variant={proj.status === 'active' ? 'success' : 'neutral'}>
              {proj.status.toUpperCase()}
            </Badge>
          </td>

          <td className="px-4 py-3">
            <ProgressBar pct={proj.completion_pct} />
          </td>

          <td className="px-4 py-3 text-center">
            <span className="text-sm font-bold text-[#0F172A]">{proj.completed_tasks}</span>
            <span className="text-xs text-slate-400"> / {proj.total_tasks}</span>
          </td>

          <td className="px-4 py-3">
            <div className="flex flex-wrap gap-1">
              {Object.entries(proj.task_status_breakdown).map(([status, count]) => (
                <span key={status} className={cn(
                  'text-[9px] font-semibold px-1.5 py-0.5 rounded-full',
                  status === 'completed' ? 'bg-green-100 text-green-700'
                    : status === 'in_progress' ? 'bg-blue-100 text-blue-700'
                    : status === 'review' ? 'bg-amber-100 text-amber-700'
                    : 'bg-slate-100 text-slate-600',
                )}>
                  {status.replace('_', ' ')}: {count}
                </span>
              ))}
            </div>
          </td>

          <td className="px-4 py-3">
            {proj.total_tasks > 0 && proj.completion_pct < 30 && (
              <AlertTriangle className="w-4 h-4 text-amber-500" />
            )}
          </td>
        </tr>

        {/* Render children if expanded */}
        {hasChildren && isExpanded && children.map(child => renderProjectRow(child, true))}
      </React.Fragment>
    );
  };

  if (isLoading) {
    return (
      <div className="p-8 flex items-center justify-center min-h-[60vh]">
        <div className="w-10 h-10 border-4 border-blue-600 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="p-8 space-y-6 max-w-[1400px] mx-auto pb-20">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold text-[#0F172A]">COO Operations Hub</h2>
          <p className="text-[#64748B]">Cross-project visibility — all PMs, tasks, and delivery progress.</p>
        </div>
        <button
          onClick={fetchOverview}
          className="flex items-center gap-2 px-4 py-2 rounded-lg border border-slate-200 text-sm font-medium text-slate-600 hover:bg-slate-50 transition-colors"
        >
          <Activity className="w-4 h-4" />
          Refresh
        </button>
      </div>

      {/* Summary Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: 'Total Projects', value: totalProjects, icon: Briefcase, color: 'text-blue-600', bg: 'bg-blue-50' },
          { label: 'Active Projects', value: activeProjects, icon: Activity, color: 'text-green-600', bg: 'bg-green-50' },
          { label: 'Overall Completion', value: `${overallPct}%`, icon: TrendingUp, color: 'text-violet-600', bg: 'bg-violet-50' },
          { label: 'At Risk', value: atRiskCount, icon: AlertTriangle, color: 'text-amber-600', bg: 'bg-amber-50' },
        ].map((s, i) => (
          <Card key={i} className="p-4 flex items-center gap-3 border-slate-100 shadow-sm">
            <div className={cn('w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0', s.bg)}>
              <s.icon className={cn('w-5 h-5', s.color)} />
            </div>
            <div>
              <p className="text-[10px] font-bold text-[#64748B] uppercase tracking-wider">{s.label}</p>
              <p className="text-xl font-black text-[#0F172A]">{s.value}</p>
            </div>
          </Card>
        ))}
      </div>

      {/* Overall progress bar */}
      <Card className="p-4 border-slate-100">
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm font-semibold text-slate-600">Portfolio-wide task completion</span>
          <span className="text-sm font-bold text-[#0F172A]">{completedTasks} / {totalTasks} tasks</span>
        </div>
        <div className="h-3 bg-slate-100 rounded-full overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-blue-500 to-violet-500 rounded-full transition-all duration-700"
            style={{ width: `${overallPct}%` }}
          />
        </div>
      </Card>

      {/* Project Table */}
      <Card className="overflow-hidden border-slate-200 shadow-sm">
        <div className="p-4 border-b border-[#E5E7EB] flex items-center gap-4 bg-white">
          <div className="relative flex-1 max-w-sm">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#64748B]" />
            <input
              type="text"
              placeholder="Search projects or PMs…"
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              className="w-full pl-9 pr-4 py-2 border border-[#E5E7EB] rounded-lg text-sm bg-[#F9FAFB] focus:outline-none focus:ring-1 focus:ring-blue-600"
            />
          </div>
          <span className="text-xs text-slate-400">{filtered.length} master project(s)</span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-[#F9FAFB] border-b border-[#E5E7EB]">
                <th className="px-4 py-3 text-xs font-bold text-[#374151] uppercase tracking-wider">Project</th>
                <th className="px-4 py-3 text-xs font-bold text-[#374151] uppercase tracking-wider">PM(s)</th>
                <th className="px-4 py-3 text-xs font-bold text-[#374151] uppercase tracking-wider">Status</th>
                <th className="px-4 py-3 text-xs font-bold text-[#374151] uppercase tracking-wider">Progress</th>
                <th className="px-4 py-3 text-xs font-bold text-[#374151] uppercase tracking-wider">Tasks</th>
                <th className="px-4 py-3 text-xs font-bold text-[#374151] uppercase tracking-wider">Breakdown</th>
                <th className="px-4 py-3 text-xs font-bold text-[#374151] uppercase tracking-wider">Risk</th>
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-6 py-20 text-center">
                    <div className="flex flex-col items-center gap-2 opacity-40">
                      <Briefcase size={36} className="text-slate-300" />
                      <p className="text-sm text-slate-400">No projects found</p>
                    </div>
                  </td>
                </tr>
              ) : (
                filtered.map(proj => renderProjectRow(proj))
              )}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
};
