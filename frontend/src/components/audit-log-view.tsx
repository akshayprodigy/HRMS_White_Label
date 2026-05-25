import React, { useState, useEffect, useMemo } from 'react';
import { Loader2, ScrollText, RotateCcw, ChevronLeft, ChevronRight, Search } from 'lucide-react';
import { Card, Button, Badge, cn } from './ui-elements';
import { Input } from './ui/input';
import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';
import { toast } from 'sonner@2.0.3';

type AuditEntry = {
  id: number;
  user_id: number | null;
  user_name: string | null;
  user_email: string | null;
  action: string;
  resource_type: string;
  resource_id: string | null;
  details: any;
  ip_address: string | null;
  created_at: string | null;
};

const PAGE_SIZE = 50;

const ACTION_TONE: Record<string, string> = {
  CREATE: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  ALLOCATE: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  UPDATE: 'bg-blue-50 text-blue-700 border-blue-200',
  PATCH: 'bg-blue-50 text-blue-700 border-blue-200',
  DELETE: 'bg-red-50 text-red-700 border-red-200',
  REJECT: 'bg-red-50 text-red-700 border-red-200',
  VERIFY: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  LOGIN: 'bg-slate-100 text-slate-700 border-slate-200',
  LOGOUT: 'bg-slate-100 text-slate-700 border-slate-200',
  IMPERSONATE: 'bg-amber-50 text-amber-700 border-amber-200',
};

const actionTone = (action: string) => {
  const upper = (action || '').toUpperCase();
  for (const key of Object.keys(ACTION_TONE)) {
    if (upper.includes(key)) return ACTION_TONE[key];
  }
  return 'bg-slate-100 text-slate-700 border-slate-200';
};

const formatDate = (iso: string | null) => {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleString('en-IN', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
};

const summariseDetails = (details: any): string => {
  if (details == null) return '';
  if (typeof details === 'string') return details;
  try {
    const json = JSON.stringify(details);
    return json.length > 140 ? `${json.slice(0, 140)}…` : json;
  } catch {
    return String(details);
  }
};

export const AuditLogView = () => {
  const [items, setItems] = useState<AuditEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [actions, setActions] = useState<string[]>([]);
  const [resourceTypes, setResourceTypes] = useState<string[]>([]);
  const [filterAction, setFilterAction] = useState('');
  const [filterResource, setFilterResource] = useState('');
  const [filterUserId, setFilterUserId] = useState('');
  const [expandedId, setExpandedId] = useState<number | null>(null);

  useEffect(() => {
    const loadDistinct = async () => {
      try {
        const res = await client.get(ENDPOINTS.ADMIN.AUDIT_LOG_DISTINCT);
        setActions(res.data?.actions || []);
        setResourceTypes(res.data?.resource_types || []);
      } catch {
        // distinct values are optional — silent fail
      }
    };
    loadDistinct();
  }, []);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      try {
        const params: Record<string, any> = { page, size: PAGE_SIZE };
        if (filterAction) params.action = filterAction;
        if (filterResource) params.resource_type = filterResource;
        const uid = parseInt(filterUserId);
        if (Number.isFinite(uid)) params.user_id = uid;
        const res = await client.get(ENDPOINTS.ADMIN.AUDIT_LOG, { params });
        setItems(res.data?.items || []);
        setTotal(res.data?.total || 0);
      } catch (err: any) {
        toast.error(err?.response?.data?.detail || 'Failed to load audit log');
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [page, filterAction, filterResource, filterUserId]);

  const totalPages = useMemo(() => Math.max(1, Math.ceil(total / PAGE_SIZE)), [total]);

  const resetFilters = () => {
    setFilterAction('');
    setFilterResource('');
    setFilterUserId('');
    setPage(1);
  };

  return (
    <div className="p-8 space-y-6 max-w-[1500px] mx-auto animate-in fade-in duration-300">
      <Card className="p-8 border-slate-200 shadow-sm bg-white">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            <div className="w-12 h-12 rounded-2xl bg-slate-100 text-slate-700 flex items-center justify-center border border-slate-200">
              <ScrollText size={22} />
            </div>
            <div>
              <h2 className="text-xl font-black text-[#0F172A] uppercase tracking-tight">Audit Log</h2>
              <p className="text-[11px] font-bold text-slate-400 uppercase tracking-widest mt-0.5">
                {total.toLocaleString()} event{total === 1 ? '' : 's'} • Latest first
              </p>
            </div>
          </div>
          <Button
            variant="outline"
            size="sm"
            className="h-10 px-4 font-black uppercase text-[10px] tracking-widest"
            onClick={resetFilters}
            disabled={!filterAction && !filterResource && !filterUserId}
          >
            <RotateCcw size={12} className="mr-2" /> Reset filters
          </Button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-6">
          <div className="space-y-2">
            <label className="text-[9px] font-black text-slate-400 uppercase tracking-widest">Action</label>
            <select
              value={filterAction}
              onChange={e => { setFilterAction(e.target.value); setPage(1); }}
              className="w-full h-10 px-3 rounded-xl border border-slate-200 bg-white text-sm font-bold text-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-500/30"
            >
              <option value="">All actions</option>
              {actions.map(a => <option key={a} value={a}>{a}</option>)}
            </select>
          </div>
          <div className="space-y-2">
            <label className="text-[9px] font-black text-slate-400 uppercase tracking-widest">Resource Type</label>
            <select
              value={filterResource}
              onChange={e => { setFilterResource(e.target.value); setPage(1); }}
              className="w-full h-10 px-3 rounded-xl border border-slate-200 bg-white text-sm font-bold text-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-500/30"
            >
              <option value="">All resources</option>
              {resourceTypes.map(r => <option key={r} value={r}>{r}</option>)}
            </select>
          </div>
          <div className="space-y-2">
            <label className="text-[9px] font-black text-slate-400 uppercase tracking-widest">User ID</label>
            <div className="relative">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <Input
                value={filterUserId}
                onChange={e => { setFilterUserId(e.target.value.replace(/[^0-9]/g, '')); setPage(1); }}
                placeholder="Filter by user ID"
                className="h-10 pl-9 pr-3 font-bold text-sm"
                inputMode="numeric"
              />
            </div>
          </div>
        </div>
      </Card>

      <Card className="p-0 border-slate-200 shadow-sm bg-white overflow-hidden">
        {loading ? (
          <div className="p-16 flex justify-center">
            <Loader2 className="w-7 h-7 text-blue-600 animate-spin" />
          </div>
        ) : items.length === 0 ? (
          <div className="p-16 flex flex-col items-center gap-3 text-center">
            <ScrollText size={36} className="text-slate-300" />
            <p className="text-sm font-black text-slate-500 uppercase tracking-widest">No audit events</p>
            <p className="text-xs font-bold text-slate-400">Try clearing filters or check back later.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead>
                <tr className="bg-slate-50 border-b border-slate-100">
                  <th className="px-6 py-4 text-[9px] font-black text-slate-500 uppercase tracking-widest">Time</th>
                  <th className="px-6 py-4 text-[9px] font-black text-slate-500 uppercase tracking-widest">User</th>
                  <th className="px-6 py-4 text-[9px] font-black text-slate-500 uppercase tracking-widest">Action</th>
                  <th className="px-6 py-4 text-[9px] font-black text-slate-500 uppercase tracking-widest">Resource</th>
                  <th className="px-6 py-4 text-[9px] font-black text-slate-500 uppercase tracking-widest">Details</th>
                  <th className="px-6 py-4 text-[9px] font-black text-slate-500 uppercase tracking-widest">IP</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {items.map(entry => {
                  const open = expandedId === entry.id;
                  return (
                    <React.Fragment key={entry.id}>
                      <tr
                        className="hover:bg-slate-50/60 cursor-pointer transition-colors"
                        onClick={() => setExpandedId(open ? null : entry.id)}
                      >
                        <td className="px-6 py-4 text-[11px] font-bold text-slate-600 tabular-nums whitespace-nowrap">
                          {formatDate(entry.created_at)}
                        </td>
                        <td className="px-6 py-4 text-[11px] font-bold text-slate-700">
                          {entry.user_name || (entry.user_id != null ? `User #${entry.user_id}` : '—')}
                          {entry.user_email && <div className="text-[10px] font-medium text-slate-400">{entry.user_email}</div>}
                        </td>
                        <td className="px-6 py-4">
                          <Badge className={cn('text-[9px] font-black uppercase tracking-widest border', actionTone(entry.action))}>
                            {entry.action || '—'}
                          </Badge>
                        </td>
                        <td className="px-6 py-4 text-[11px] font-bold text-slate-700">
                          <div>{entry.resource_type || '—'}</div>
                          {entry.resource_id && <div className="text-[10px] font-medium text-slate-400">#{entry.resource_id}</div>}
                        </td>
                        <td className="px-6 py-4 text-[11px] font-medium text-slate-500 max-w-[420px] truncate">
                          {summariseDetails(entry.details) || '—'}
                        </td>
                        <td className="px-6 py-4 text-[10px] font-mono text-slate-500">{entry.ip_address || '—'}</td>
                      </tr>
                      {open && (
                        <tr className="bg-slate-50/50">
                          <td colSpan={6} className="px-6 py-4">
                            <pre className="text-[11px] font-mono whitespace-pre-wrap break-words bg-white border border-slate-200 rounded-xl p-4 max-h-80 overflow-auto">
{JSON.stringify(entry.details, null, 2)}
                            </pre>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        <div className="flex items-center justify-between px-6 py-4 border-t border-slate-100">
          <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest">
            Page {page} of {totalPages}
          </p>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              className="h-9 px-3"
              disabled={page <= 1 || loading}
              onClick={() => setPage(p => Math.max(1, p - 1))}
            >
              <ChevronLeft size={14} />
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="h-9 px-3"
              disabled={page >= totalPages || loading}
              onClick={() => setPage(p => Math.min(totalPages, p + 1))}
            >
              <ChevronRight size={14} />
            </Button>
          </div>
        </div>
      </Card>
    </div>
  );
};
