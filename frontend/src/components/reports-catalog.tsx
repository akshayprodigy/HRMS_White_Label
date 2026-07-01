/**
 * Reports catalog: grouped, searchable list of every available report.
 * Clicking a report navigates to the generic viewer with the descriptor.
 */
import React, { useEffect, useMemo, useState } from 'react';
import {
  Search, RefreshCw, FileText, ClipboardList, CalendarDays,
  Banknote, Shield, Users, ChevronRight, Bookmark, AlertTriangle,
} from 'lucide-react';
import { Card, Button, Badge, cn } from './ui-elements';
import { toast } from 'sonner@2.0.3';
import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';
import { Input } from './ui/input';

interface FilterSchema {
  key: string; label: string; type: string;
  required: boolean; options: any[] | null; hint: string | null;
}
interface ReportDesc {
  key: string; name: string; description: string;
  category: 'attendance' | 'leave' | 'payroll' | 'statutory' | 'headcount';
  permission: string;
  is_sensitive: boolean;
  manager_scoped: boolean;
  filters: FilterSchema[];
}
interface Saved {
  id: number; name: string; report_key: string;
  description: string | null; filters_json: any;
  default_format: string; cadence: string;
  recipients_json: string[];
  last_run_at: string | null;
}

const CATEGORY_META: Record<string, { label: string; icon: any; tone: string }> = {
  attendance: { label: 'Attendance & Time', icon: ClipboardList, tone: 'bg-blue-50 text-blue-700 border-blue-200' },
  leave: { label: 'Leave', icon: CalendarDays, tone: 'bg-amber-50 text-amber-700 border-amber-200' },
  payroll: { label: 'Payroll & Compensation', icon: Banknote, tone: 'bg-purple-50 text-purple-700 border-purple-200' },
  statutory: { label: 'Statutory', icon: Shield, tone: 'bg-green-50 text-green-700 border-green-200' },
  headcount: { label: 'Headcount & Attrition', icon: Users, tone: 'bg-slate-50 text-slate-700 border-slate-200' },
};

const errMsg = (e: any, fb: string) => {
  const d = e?.response?.data?.detail;
  if (typeof d === 'string') return d;
  return e?.message || fb;
};

interface Props {
  onOpenReport: (report: ReportDesc, initial?: any) => void;
}

export const ReportsCatalogView: React.FC<Props> = ({ onOpenReport }) => {
  const [catalog, setCatalog] = useState<ReportDesc[]>([]);
  const [saved, setSaved] = useState<Saved[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [activeCat, setActiveCat] = useState<string>('all');

  const fetchAll = async () => {
    setLoading(true);
    try {
      const [c, s] = await Promise.all([
        client.get(ENDPOINTS.REPORTS_ENGINE.CATALOG),
        client.get(ENDPOINTS.REPORTS_ENGINE.SAVED).catch(() => ({ data: [] })),
      ]);
      setCatalog(c.data.reports || []);
      setSaved((s.data || []).filter((x: Saved) => (x as any).is_active !== false));
    } catch (e: any) { toast.error(errMsg(e, 'Failed to load catalog')); }
    finally { setLoading(false); }
  };
  useEffect(() => { fetchAll(); }, []);

  const grouped = useMemo(() => {
    const q = search.trim().toLowerCase();
    const filtered = catalog.filter(r =>
      (activeCat === 'all' || r.category === activeCat)
      && (!q || r.name.toLowerCase().includes(q)
        || r.description.toLowerCase().includes(q))
    );
    const g: Record<string, ReportDesc[]> = {};
    for (const r of filtered) {
      if (!g[r.category]) g[r.category] = [];
      g[r.category].push(r);
    }
    return g;
  }, [catalog, search, activeCat]);

  const runSaved = async (s: Saved) => {
    const desc = catalog.find(r => r.key === s.report_key);
    if (!desc) { toast.error('Report definition not found'); return; }
    onOpenReport(desc, s.filters_json);
  };

  const catCounts = useMemo(() => {
    const c: Record<string, number> = {};
    for (const r of catalog) c[r.category] = (c[r.category] || 0) + 1;
    return c;
  }, [catalog]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <FileText className="w-6 h-6 text-blue-600" /> Reports Catalog
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Every corporate HR report on one page. Filter → run → export to Excel / CSV / PDF.
          </p>
        </div>
        <Button variant="outline" onClick={fetchAll}><RefreshCw className="w-4 h-4" /></Button>
      </div>

      {saved.length > 0 && (
        <Card className="p-4">
          <h2 className="text-sm font-semibold text-slate-700 uppercase tracking-wide mb-3 flex items-center gap-2">
            <Bookmark className="w-4 h-4" /> Saved reports
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {saved.slice(0, 6).map(s => (
              <button key={s.id}
                onClick={() => runSaved(s)}
                className="text-left border border-slate-200 rounded-lg p-3 hover:border-blue-400 hover:bg-blue-50/40 transition">
                <div className="font-semibold text-sm">{s.name}</div>
                <div className="text-[10px] text-slate-500 mt-1">{s.report_key}</div>
                {s.last_run_at && (
                  <div className="text-[10px] text-slate-400 mt-1">
                    last run {new Date(s.last_run_at).toLocaleDateString()}
                  </div>
                )}
              </button>
            ))}
          </div>
        </Card>
      )}

      <Card className="p-4">
        <div className="flex items-center gap-3 mb-3 flex-wrap">
          <button onClick={() => setActiveCat('all')}
            className={cn('px-3 py-1.5 text-sm rounded-md font-medium',
              activeCat === 'all' ? 'bg-blue-600 text-white' : 'bg-slate-100 text-slate-700')}>
            All ({catalog.length})
          </button>
          {Object.entries(CATEGORY_META).map(([k, meta]) => {
            const Icon = meta.icon;
            return (
              <button key={k} onClick={() => setActiveCat(k)}
                className={cn('px-3 py-1.5 text-sm rounded-md font-medium flex items-center gap-2',
                  activeCat === k ? 'bg-blue-600 text-white' : 'bg-slate-100 text-slate-700')}>
                <Icon className="w-3 h-3" /> {meta.label} ({catCounts[k] || 0})
              </button>
            );
          })}
          <div className="relative flex-1 max-w-sm ml-auto">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <Input placeholder="Search reports…" value={search}
              onChange={e => setSearch(e.target.value)} className="pl-9" />
          </div>
        </div>

        {loading ? <div className="py-8 text-center text-slate-500">Loading…</div>
          : Object.keys(grouped).length === 0 ? (
            <div className="py-12 text-center text-slate-500">
              No reports match your search or you lack permission to view any.
            </div>
          ) : (
            <div className="space-y-6">
              {Object.entries(grouped).map(([cat, reports]) => {
                const meta = CATEGORY_META[cat];
                const Icon = meta?.icon || FileText;
                return (
                  <div key={cat}>
                    <div className={cn('flex items-center gap-2 mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500')}>
                      <Icon className="w-4 h-4" /> {meta?.label || cat}
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                      {reports.map(r => (
                        <button key={r.key} onClick={() => onOpenReport(r)}
                          className="text-left border border-slate-200 rounded-lg p-4 hover:border-blue-400 hover:bg-blue-50/40 transition group">
                          <div className="flex items-start justify-between mb-2">
                            <div className="font-semibold text-sm">{r.name}</div>
                            <ChevronRight className="w-4 h-4 text-slate-300 group-hover:text-blue-600 flex-shrink-0" />
                          </div>
                          <div className="text-xs text-slate-500 line-clamp-3">{r.description}</div>
                          <div className="flex gap-1 mt-2 flex-wrap">
                            {r.is_sensitive && (
                              <Badge variant="warning" className="text-[10px]">
                                <AlertTriangle className="w-2.5 h-2.5 mr-0.5" /> Sensitive
                              </Badge>
                            )}
                            {r.manager_scoped && (
                              <Badge variant="info" className="text-[10px]">Team-scoped</Badge>
                            )}
                          </div>
                        </button>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
      </Card>
    </div>
  );
};
