import React, { useState, useEffect } from 'react';
import { Loader2, Network, Search, ChevronDown, ChevronRight, Mail, Briefcase } from 'lucide-react';
import { Card, Button, cn } from './ui-elements';
import { Input } from './ui/input';
import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';
import { toast } from 'sonner@2.0.3';

type OrgNode = {
  user_id: number;
  employee_id: string;
  full_name: string;
  designation: string | null;
  department: string | null;
  email: string | null;
  manager_id: number | null;
  subordinates: OrgNode[];
};

const initials = (name: string) =>
  (name || '?')
    .split(' ')
    .filter(Boolean)
    .slice(0, 2)
    .map(p => p[0]?.toUpperCase())
    .join('');

const matchesSearch = (node: OrgNode, q: string): boolean => {
  if (!q) return true;
  const haystack = `${node.full_name || ''} ${node.designation || ''} ${node.department || ''} ${node.email || ''}`.toLowerCase();
  if (haystack.includes(q)) return true;
  return node.subordinates.some(child => matchesSearch(child, q));
};

const NodeCard: React.FC<{ node: OrgNode; depth: number; query: string; defaultExpanded: boolean }> = ({ node, depth, query, defaultExpanded }) => {
  const [open, setOpen] = useState(defaultExpanded);
  const hasChildren = node.subordinates.length > 0;
  const isMatch = !query || `${node.full_name} ${node.designation} ${node.department}`.toLowerCase().includes(query);

  return (
    <div className={cn('relative', depth > 0 && 'pl-8 border-l border-dashed border-slate-200')}>
      <div className={cn(
        'flex items-center gap-4 rounded-2xl border bg-white p-4 transition-shadow hover:shadow-md',
        isMatch ? 'border-slate-200' : 'border-slate-100 opacity-60',
      )}>
        <button
          type="button"
          onClick={() => hasChildren && setOpen(o => !o)}
          className={cn(
            'w-7 h-7 rounded-lg border border-slate-200 flex items-center justify-center transition-colors',
            hasChildren ? 'hover:bg-slate-50 cursor-pointer text-slate-600' : 'opacity-30 cursor-default text-slate-300',
          )}
          aria-label={open ? 'Collapse' : 'Expand'}
        >
          {hasChildren ? (open ? <ChevronDown size={14} /> : <ChevronRight size={14} />) : <span className="w-2 h-2 rounded-full bg-slate-200" />}
        </button>

        <div className="w-11 h-11 rounded-full bg-blue-50 text-[#2563EB] flex items-center justify-center font-black tracking-widest text-sm border border-blue-100">
          {initials(node.full_name)}
        </div>

        <div className="flex-1 min-w-0">
          <p className="text-sm font-black text-[#0F172A] truncate">{node.full_name}</p>
          <div className="flex flex-wrap gap-x-4 gap-y-0.5 text-[11px] font-bold text-slate-500 mt-0.5">
            {node.designation && <span className="flex items-center gap-1.5"><Briefcase size={11} /> {node.designation}</span>}
            {node.department && <span className="text-slate-400">{node.department}</span>}
            {node.email && <span className="flex items-center gap-1.5 text-slate-400"><Mail size={11} /> <span className="truncate">{node.email}</span></span>}
          </div>
        </div>

        {hasChildren && (
          <span className="text-[9px] font-black uppercase tracking-widest text-slate-400 bg-slate-50 px-2 py-1 rounded-md">
            {node.subordinates.length} report{node.subordinates.length === 1 ? '' : 's'}
          </span>
        )}
      </div>

      {hasChildren && open && (
        <div className="mt-3 space-y-3">
          {node.subordinates
            .filter(child => matchesSearch(child, query))
            .map(child => (
              <NodeCard key={child.user_id} node={child} depth={depth + 1} query={query} defaultExpanded={defaultExpanded} />
            ))}
        </div>
      )}
    </div>
  );
};

export const OrgChartView = () => {
  const [roots, setRoots] = useState<OrgNode[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [expandAll, setExpandAll] = useState(true);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      try {
        const res = await client.get(ENDPOINTS.HR.ORG_CHART);
        setRoots(res.data?.roots || []);
        setTotal(res.data?.total || 0);
      } catch (err: any) {
        toast.error(err?.response?.data?.detail || 'Failed to load org chart');
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  const q = search.trim().toLowerCase();
  const visibleRoots = roots.filter(r => matchesSearch(r, q));

  return (
    <div className="p-8 space-y-6 max-w-[1400px] mx-auto animate-in fade-in duration-300">
      <Card className="p-8 border-slate-200 shadow-sm bg-white">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            <div className="w-12 h-12 rounded-2xl bg-blue-50 text-[#2563EB] flex items-center justify-center border border-blue-100">
              <Network size={22} />
            </div>
            <div>
              <h2 className="text-xl font-black text-[#0F172A] uppercase tracking-tight">Organisation Chart</h2>
              <p className="text-[11px] font-bold text-slate-400 uppercase tracking-widest mt-0.5">
                {total} active employee{total === 1 ? '' : 's'} • Reporting hierarchy
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <div className="relative">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <Input
                value={search}
                onChange={e => setSearch(e.target.value)}
                placeholder="Search name, role, dept…"
                className="h-10 pl-9 pr-3 w-72 font-bold text-sm"
              />
            </div>
            <Button
              variant="outline"
              size="sm"
              className="h-10 px-4 font-black uppercase text-[10px] tracking-widest"
              onClick={() => setExpandAll(v => !v)}
            >
              {expandAll ? 'Collapse all' : 'Expand all'}
            </Button>
          </div>
        </div>
      </Card>

      <Card className="p-6 border-slate-200 shadow-sm bg-white">
        {loading ? (
          <div className="p-16 flex justify-center">
            <Loader2 className="w-7 h-7 text-blue-600 animate-spin" />
          </div>
        ) : visibleRoots.length === 0 ? (
          <div className="p-16 flex flex-col items-center gap-3 text-center">
            <Network size={36} className="text-slate-300" />
            <p className="text-sm font-black text-slate-500 uppercase tracking-widest">
              {q ? 'No matches' : 'No employees'}
            </p>
            <p className="text-xs font-bold text-slate-400">
              {q ? 'Try a different search term.' : 'Add employees with reporting managers to render the chart.'}
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            {visibleRoots.map(root => (
              <NodeCard key={root.user_id} node={root} depth={0} query={q} defaultExpanded={expandAll} />
            ))}
          </div>
        )}
      </Card>
    </div>
  );
};
