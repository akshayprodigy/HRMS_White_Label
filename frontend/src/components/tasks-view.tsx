import React, { useState, useEffect } from 'react';
import { 
  Plus, 
  Search, 
  Filter, 
  CheckCircle2, 
  Clock, 
  AlertCircle,
  MoreVertical,
  Calendar,
  MessageSquare,
  Paperclip,
  ChevronRight,
  LayoutGrid,
  List,
  Folder
} from 'lucide-react';
import { Card, Button, Badge, cn } from './ui-elements';
import { toast } from 'sonner@2.0.3';
import { TaskDetailModal } from './task-detail-modal';
import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';

export const TasksView = () => {
  const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid');
  const [selectedTaskId, setSelectedTaskId] = useState<number | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [filterPriority, setFilterPriority] = useState<string>('All');
  const [projectsData, setProjectsData] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    fetchTasks();
  }, []);

  const fetchTasks = async () => {
    setIsLoading(true);
    try {
      const response = await client.get(ENDPOINTS.TASKS.MY_TASKS);
      setProjectsData(response.data);
    } catch (error) {
      toast.error("Failed to synchronize deliverables");
    } finally {
      setIsLoading(false);
    }
  };

  const getFilteredTasks = () => {
    // Flatten tasks but keep project context if needed, 
    // or filter within grouped structure. 
    // To support project grouping, we'll filter the structure.
    return projectsData.map(project => ({
      ...project,
      tasks: project.tasks.filter((t: any) => {
        const matchesSearch = t.title.toLowerCase().includes(searchQuery.toLowerCase()) || 
                             t.id.toString().includes(searchQuery.toLowerCase());
        const matchesPriority = filterPriority === 'All' || 
                               t.priority.toLowerCase() === filterPriority.toLowerCase();
        return matchesSearch && matchesPriority;
      })
    })).filter(project => project.tasks.length > 0);
  };

  const filteredProjects = getFilteredTasks();

  const getPriorityColor = (p: string) => {
    const priority = p.toLowerCase();
    switch(priority) {
      case 'urgent':
      case 'critical': return 'text-red-600 bg-red-50 border-red-100';
      case 'high': return 'text-amber-600 bg-amber-50 border-amber-100';
      default: return 'text-blue-600 bg-blue-50 border-blue-100';
    }
  };

  if (isLoading && projectsData.length === 0) {
    return (
      <div className="p-8 text-center py-20">
        <div className="animate-spin w-8 h-8 border-4 border-blue-600 border-t-transparent rounded-full mx-auto mb-4"></div>
        <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Initialising Operational Nodes...</p>
      </div>
    );
  }

  return (
    <div className="p-8 space-y-8 max-w-[1600px] mx-auto animate-in fade-in duration-500">
      <TaskDetailModal 
        isOpen={selectedTaskId !== null}
        taskId={selectedTaskId ? String(selectedTaskId) : null}
        onClose={() => {
          setSelectedTaskId(null);
          fetchTasks();
        }}
      />

      <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
        <div>
          <h2 className="text-3xl font-black text-[#0F172A] tracking-tighter">Operational Deliverables</h2>
          <p className="text-[#64748B] font-bold uppercase tracking-widest text-[10px] mt-1">Manage assigned tasks, track milestone progress, and collaborate on execution</p>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex bg-slate-100 p-1 rounded-xl mr-2">
            <button 
              onClick={() => setViewMode('grid')}
              className={cn("p-2 rounded-lg transition-all", viewMode === 'grid' ? "bg-white shadow-sm text-blue-600" : "text-slate-400")}
            >
              <LayoutGrid size={18} />
            </button>
            <button 
              onClick={() => setViewMode('list')}
              className={cn("p-2 rounded-lg transition-all", viewMode === 'list' ? "bg-white shadow-sm text-blue-600" : "text-slate-400")}
            >
              <List size={18} />
            </button>
          </div>
        </div>
      </div>

      <div className="flex flex-col md:flex-row gap-4 items-center">
        <div className="relative flex-1 w-full">
          <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <input 
            type="text" 
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search operational tasks by ID, title, or project..." 
            className="w-full pl-12 pr-4 py-3 bg-white border border-slate-200 rounded-2xl text-sm font-bold focus:outline-none focus:ring-2 focus:ring-blue-600/10 transition-all shadow-sm"
          />
        </div>
        <div className="flex items-center gap-2 overflow-x-auto pb-2 md:pb-0 w-full md:w-auto">
          {['All', 'Critical', 'High', 'Medium'].map((p) => (
            <button
              key={p}
              onClick={() => setFilterPriority(p)}
              className={cn(
                "px-4 py-2.5 rounded-xl text-[10px] font-black uppercase tracking-widest border transition-all whitespace-nowrap",
                filterPriority === p 
                  ? "bg-blue-600 border-blue-600 text-white shadow-lg shadow-blue-600/20" 
                  : "bg-white border-slate-200 text-[#64748B] hover:border-blue-600"
              )}
            >
              {p}
            </button>
          ))}
        </div>
      </div>

      {filteredProjects.map((project) => (
        <div key={project.id} className="space-y-4">
          <div className="flex items-center gap-3 px-2">
            <div className="w-8 h-8 rounded-lg bg-blue-600/10 flex items-center justify-center text-blue-600">
               <Folder size={16} />
            </div>
            <h3 className="font-black text-[#0F172A] tracking-tight flex items-center gap-3">
              {project.name}
              <Badge variant="neutral" className="text-[9px] h-5">{project.tasks.length} Deliverables</Badge>
            </h3>
          </div>

          {viewMode === 'grid' ? (
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-6">
              {project.tasks.map((task: any) => (
                <Card 
                  key={task.id} 
                  onClick={() => setSelectedTaskId(task.id)}
                  className="p-6 bg-white border-slate-200 hover:border-blue-600 hover:shadow-xl transition-all cursor-pointer group flex flex-col justify-between"
                >
                  <div>
                    <div className="flex items-center justify-between mb-4">
                      <Badge variant="neutral" className="font-black text-[9px] px-2 h-5 uppercase tracking-widest">T-{task.id}</Badge>
                      <button className="text-slate-400 hover:text-blue-600"><MoreVertical size={16} /></button>
                    </div>
                    <h3 className="text-sm font-black text-[#0F172A] mb-2 leading-snug group-hover:text-blue-600 transition-colors">{task.title}</h3>
                    
                    <div className="flex items-center gap-4 mb-6 mt-4">
                      <div className={cn("px-2 py-1 rounded text-[9px] font-black uppercase border", getPriorityColor(task.priority))}>
                        {task.priority}
                      </div>
                      <div className="flex items-center gap-1.5 text-[10px] font-bold text-[#64748B] uppercase tracking-widest">
                          <Clock size={12} className="text-blue-600" /> {task.due_date ? new Date(task.due_date).toLocaleDateString() : 'No Due Date'}
                      </div>
                    </div>
                  </div>

                  <div className="space-y-4 pt-4 border-t border-slate-50">
                    <div className="flex items-center justify-between mb-1">
                        <span className="text-[10px] font-black text-[#64748B] uppercase tracking-widest">Status</span>
                        <Badge variant={task.status === 'completed' ? 'success' : 'neutral'} className="text-[9px] uppercase">{task.status}</Badge>
                    </div>
                    
                    <div className="flex items-center justify-between pt-2">
                        <div className="flex -space-x-2">
                           <div className="w-7 h-7 rounded-full bg-blue-100 border-2 border-white flex items-center justify-center text-[10px] font-black text-blue-600 uppercase">
                            {task.assignee_id ? 'AT' : '?'}
                           </div>
                        </div>
                        <div className="flex items-center gap-4 text-[#94A3B8]">
                           <div className="flex items-center gap-1"><MessageSquare size={14} /> <span className="text-[10px] font-black">{task.subtasks.length}</span></div>
                           {task.actual_hours > 0 && (
                             <div className="flex items-center gap-1 text-blue-500">
                               <Clock size={12} />
                               <span className="text-[10px] font-black">{task.actual_hours}h</span>
                             </div>
                           )}
                        </div>
                    </div>
                  </div>
                </Card>
              ))}
            </div>
          ) : (
            <Card className="bg-white border-slate-200 overflow-hidden shadow-sm">
               <div className="overflow-x-auto">
                  <table className="w-full text-left">
                    <thead>
                        <tr className="bg-slate-50/50 border-b border-slate-100">
                          <th className="px-8 py-4 text-[10px] font-black text-[#64748B] uppercase tracking-widest">Deliverable</th>
                          <th className="px-8 py-4 text-[10px] font-black text-[#64748B] uppercase tracking-widest">Status</th>
                          <th className="px-8 py-4 text-[10px] font-black text-[#64748B] uppercase tracking-widest">Priority</th>
                          <th className="px-8 py-4 text-[10px] font-black text-[#64748B] uppercase tracking-widest">Deadline</th>
                          <th className="px-8 py-4 text-[10px] font-black text-[#64748B] uppercase tracking-widest">Logged</th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-50">
                        {project.tasks.map((task: any) => (
                          <tr 
                            key={task.id} 
                            onClick={() => setSelectedTaskId(task.id)}
                            className="hover:bg-slate-50/50 cursor-pointer transition-colors group"
                          >
                              <td className="px-8 py-6">
                                <p className="text-sm font-black text-[#0F172A] group-hover:text-blue-600">{task.title}</p>
                                <p className="text-[10px] font-black text-[#94A3B8] uppercase mt-1 tracking-widest">T-{task.id}</p>
                              </td>
                              <td className="px-8 py-6">
                                <Badge variant={task.status === 'completed' ? 'success' : 'neutral'} className="font-black text-[9px] uppercase px-3">
                                    {task.status}
                                </Badge>
                              </td>
                              <td className="px-8 py-6">
                                <div className={cn("inline-block px-2 py-1 rounded text-[9px] font-black uppercase border", getPriorityColor(task.priority))}>
                                    {task.priority}
                                </div>
                              </td>
                              <td className="px-8 py-6 text-xs font-black text-[#334155] uppercase tracking-widest">
                                {task.due_date ? new Date(task.due_date).toLocaleDateString() : 'N/A'}
                              </td>
                              <td className="px-8 py-6 text-xs font-black text-blue-600 tabular-nums">
                                {task.actual_hours > 0 ? `${task.actual_hours}h` : '—'}
                              </td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
               </div>
            </Card>
          )}
        </div>
      ))}

      {filteredProjects.length === 0 && (
        <div className="py-20 text-center bg-slate-50/50 rounded-3xl border-2 border-dashed border-slate-200">
           <AlertCircle className="w-8 h-8 text-slate-300 mx-auto mb-3" />
           <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest">No matching deliverables found in operational scope</p>
        </div>
      )}
    </div>
  );
};
