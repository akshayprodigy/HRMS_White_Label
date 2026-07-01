import React, { useEffect, useMemo, useState } from 'react';
import {
  Plus,
  Trash2,
  Search,
  RefreshCw,
  Shield,
  ShieldAlert,
  Building2,
  Users,
  ToggleLeft,
  ToggleRight,
  MapPin,
} from 'lucide-react';
import { Card, Button, Badge, cn } from './ui-elements';
import { toast } from 'sonner';
import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';
import { Dialog, DialogContent, DialogTitle, DialogFooter } from './ui/dialog';
import { Input } from './ui/input';

interface GeoFence {
  id: number;
  name: string;
  latitude: number;
  longitude: number;
  radius_meters: number;
  is_active: boolean;
}

interface EmployeeGeoConfig {
  user_id: number;
  enforcement_mode: 'strict' | 'allow_with_flag';
  geo_enabled: boolean;
  fence_ids: number[];
  updated_at: string;
  employee_name?: string | null;
  employee_email?: string | null;
  employee_department?: string | null;
  fences: GeoFence[];
}

const errMsg = (err: any, fallback: string): string => {
  const detail = err?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail))
    return detail.map((d: any) => d?.msg || JSON.stringify(d)).join('; ');
  return err?.message || fallback;
};

const MODE_LABELS: Record<string, { label: string; tone: string; icon: any }> = {
  strict: { label: 'Strict', tone: 'bg-rose-100 text-rose-800', icon: Shield },
  allow_with_flag: {
    label: 'Allow + Flag',
    tone: 'bg-amber-100 text-amber-800',
    icon: ShieldAlert,
  },
};

export const EmployeeGeoAssignments: React.FC = () => {
  const [items, setItems] = useState<EmployeeGeoConfig[]>([]);
  const [fences, setFences] = useState<GeoFence[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [deptFilter, setDeptFilter] = useState('');

  const [singleOpen, setSingleOpen] = useState(false);
  const [editing, setEditing] = useState<EmployeeGeoConfig | null>(null);
  const [singleForm, setSingleForm] = useState({
    user_id: '' as number | '',
    enforcement_mode: 'strict' as 'strict' | 'allow_with_flag',
    geo_enabled: true,
    fence_ids: [] as number[],
  });
  const [submitting, setSubmitting] = useState(false);

  const [bulkOpen, setBulkOpen] = useState(false);
  const [bulkSubmitting, setBulkSubmitting] = useState(false);
  const [bulkResult, setBulkResult] = useState<{
    upserted: number;
    failed: number;
    errors: string[];
  } | null>(null);
  const [bulkForm, setBulkForm] = useState({
    mode: 'department' as 'department' | 'employee_ids',
    department: '',
    employee_ids: '',
    enforcement_mode: 'strict' as 'strict' | 'allow_with_flag',
    geo_enabled: true,
    fence_ids: [] as number[],
  });

  const [deleteTarget, setDeleteTarget] = useState<EmployeeGeoConfig | null>(null);

  const fetchItems = async () => {
    setLoading(true);
    try {
      const params: any = {};
      if (deptFilter) params.department = deptFilter;
      const res = await client.get(ENDPOINTS.GEO.EMPLOYEES, { params });
      setItems(res.data || []);
    } catch (e: any) {
      toast.error(errMsg(e, 'Failed to load employee geo configs'));
    } finally {
      setLoading(false);
    }
  };

  const fetchFences = async () => {
    try {
      const res = await client.get(ENDPOINTS.GEO.FENCES);
      setFences(res.data || []);
    } catch {
      /* non-fatal */
    }
  };

  useEffect(() => {
    fetchFences();
  }, []);

  useEffect(() => {
    fetchItems();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [deptFilter]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return items;
    return items.filter(
      (i) =>
        (i.employee_name || '').toLowerCase().includes(q) ||
        (i.employee_email || '').toLowerCase().includes(q) ||
        (i.employee_department || '').toLowerCase().includes(q),
    );
  }, [items, search]);

  const openCreate = () => {
    setEditing(null);
    setSingleForm({
      user_id: '',
      enforcement_mode: 'strict',
      geo_enabled: true,
      fence_ids: [],
    });
    setSingleOpen(true);
  };

  const openEdit = (cfg: EmployeeGeoConfig) => {
    setEditing(cfg);
    setSingleForm({
      user_id: cfg.user_id,
      enforcement_mode: cfg.enforcement_mode,
      geo_enabled: cfg.geo_enabled,
      fence_ids: cfg.fence_ids ?? [],
    });
    setSingleOpen(true);
  };

  const toggleFenceInSet = (
    arr: number[],
    id: number,
  ): number[] =>
    arr.includes(id) ? arr.filter((x) => x !== id) : [...arr, id];

  const submitSingle = async () => {
    if (singleForm.user_id === '' || !Number(singleForm.user_id)) {
      toast.error('Employee user ID is required');
      return;
    }
    if (singleForm.fence_ids.length === 0) {
      toast.error('Pick at least one allowed fence');
      return;
    }
    setSubmitting(true);
    try {
      await client.put(ENDPOINTS.GEO.EMPLOYEES, {
        user_id: Number(singleForm.user_id),
        enforcement_mode: singleForm.enforcement_mode,
        geo_enabled: singleForm.geo_enabled,
        fence_ids: singleForm.fence_ids,
      });
      toast.success(editing ? 'Config updated' : 'Config saved');
      setSingleOpen(false);
      fetchItems();
    } catch (e: any) {
      toast.error(errMsg(e, 'Save failed'));
    } finally {
      setSubmitting(false);
    }
  };

  const toggleGeo = async (cfg: EmployeeGeoConfig) => {
    try {
      await client.patch(ENDPOINTS.GEO.EMPLOYEE_TOGGLE(cfg.user_id), {
        geo_enabled: !cfg.geo_enabled,
      });
      toast.success(cfg.geo_enabled ? 'Geo disabled' : 'Geo enabled');
      fetchItems();
    } catch (e: any) {
      toast.error(errMsg(e, 'Toggle failed'));
    }
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    try {
      await client.delete(ENDPOINTS.GEO.EMPLOYEE_DETAIL(deleteTarget.user_id));
      toast.success('Removed from geo fencing');
      setDeleteTarget(null);
      fetchItems();
    } catch (e: any) {
      toast.error(errMsg(e, 'Delete failed'));
    }
  };

  const openBulk = () => {
    setBulkResult(null);
    setBulkForm({
      mode: 'department',
      department: '',
      employee_ids: '',
      enforcement_mode: 'strict',
      geo_enabled: true,
      fence_ids: [],
    });
    setBulkOpen(true);
  };

  const submitBulk = async () => {
    if (bulkForm.fence_ids.length === 0) {
      toast.error('Pick at least one fence');
      return;
    }
    const payload: any = {
      enforcement_mode: bulkForm.enforcement_mode,
      geo_enabled: bulkForm.geo_enabled,
      fence_ids: bulkForm.fence_ids,
    };
    if (bulkForm.mode === 'department') {
      if (!bulkForm.department.trim()) {
        toast.error('Department is required');
        return;
      }
      payload.department = bulkForm.department.trim();
    } else {
      const ids = bulkForm.employee_ids
        .split(/[,\s]+/)
        .map((s) => s.trim())
        .filter(Boolean)
        .map((s) => Number(s))
        .filter((n) => Number.isFinite(n) && n > 0);
      if (ids.length === 0) {
        toast.error('Provide at least one employee user ID');
        return;
      }
      payload.employee_ids = ids;
    }

    setBulkSubmitting(true);
    try {
      const res = await client.post(ENDPOINTS.GEO.EMPLOYEES_BULK, payload);
      setBulkResult(res.data);
      const { upserted, failed } = res.data || {};
      if (failed > 0) {
        toast.error(`Bulk done: ${upserted} upserted, ${failed} failed`);
      } else {
        toast.success(`Bulk done: ${upserted} upserted`);
      }
      fetchItems();
    } catch (e: any) {
      toast.error(errMsg(e, 'Bulk assignment failed'));
    } finally {
      setBulkSubmitting(false);
    }
  };

  return (
    <div className="p-8 space-y-6 max-w-[1600px] mx-auto animate-in fade-in duration-300">
      <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-4">
        <div>
          <h2 className="text-3xl font-black text-[#0F172A] tracking-tighter uppercase">
            Employee Geo-Fences
          </h2>
          <p className="text-[#64748B] font-bold uppercase tracking-widest text-[10px] mt-1">
            Who Must Punch From Where · Enforcement Mode &amp; Real-Time Toggle
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <button
            type="button"
            onClick={fetchItems}
            className="p-2 text-slate-400 hover:text-blue-600 transition-colors"
            title="Refresh"
            aria-label="Refresh"
          >
            <RefreshCw size={16} className={cn(loading && 'animate-spin')} />
          </button>
          <Button
            onClick={openBulk}
            variant="ghost"
            className="h-10 border border-blue-200 bg-blue-50 text-blue-700 hover:bg-blue-100 font-black uppercase text-[10px] tracking-widest"
          >
            <Users size={14} className="mr-1.5" />
            Bulk Assign
          </Button>
          <Button
            onClick={openCreate}
            className="h-10 bg-blue-600 hover:bg-blue-700 text-white font-black uppercase text-[10px] tracking-widest"
          >
            <Plus size={14} className="mr-1.5" />
            Assign
          </Button>
        </div>
      </div>

      <Card className="p-0 border-slate-200 overflow-hidden bg-white">
        <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between bg-slate-50/40 gap-4 flex-wrap">
          <div className="flex items-center gap-3 flex-wrap">
            <h4 className="text-sm font-black text-[#0F172A] tracking-tight uppercase">
              Configurations
              {!loading && (
                <span className="ml-2 text-slate-400 font-bold text-[10px]">
                  ({filtered.length}/{items.length})
                </span>
              )}
            </h4>
            <input
              value={deptFilter}
              onChange={(e) => setDeptFilter(e.target.value)}
              placeholder="Filter dept…"
              className="h-9 px-3 bg-white border border-slate-200 rounded-xl text-[10px] font-black uppercase tracking-widest w-40 outline-none"
            />
          </div>
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 pointer-events-none" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search name, email, dept..."
              className="pl-10 pr-4 h-9 bg-white border border-slate-200 rounded-xl text-[10px] font-black uppercase tracking-widest w-72 focus:ring-2 focus:ring-blue-600/10 outline-none"
            />
          </div>
        </div>

        {loading ? (
          <div className="py-16 text-center text-[10px] font-black uppercase tracking-widest text-slate-400 animate-pulse">
            Loading…
          </div>
        ) : filtered.length === 0 ? (
          <div className="py-16 text-center text-[10px] font-black uppercase tracking-widest text-slate-400">
            No employees configured yet. Bulk-assign by department to get started.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead className="bg-white border-b border-slate-100">
                <tr>
                  <th className="px-6 py-3 text-[9px] font-black text-slate-400 uppercase tracking-widest">Employee</th>
                  <th className="px-6 py-3 text-[9px] font-black text-slate-400 uppercase tracking-widest">Department</th>
                  <th className="px-6 py-3 text-[9px] font-black text-slate-400 uppercase tracking-widest">Mode</th>
                  <th className="px-6 py-3 text-[9px] font-black text-slate-400 uppercase tracking-widest">Allowed Fences</th>
                  <th className="px-6 py-3 text-[9px] font-black text-slate-400 uppercase tracking-widest w-28">Geo Toggle</th>
                  <th className="px-6 py-3 text-right text-[9px] font-black text-slate-400 uppercase tracking-widest w-44">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {filtered.map((cfg) => {
                  const meta = MODE_LABELS[cfg.enforcement_mode];
                  const Icon = meta?.icon ?? Shield;
                  return (
                    <tr key={cfg.user_id} className="hover:bg-slate-50/60 transition-colors">
                      <td className="px-6 py-3">
                        <div className="text-sm font-black text-[#0F172A]">
                          {cfg.employee_name || `User #${cfg.user_id}`}
                        </div>
                        {cfg.employee_email && (
                          <div className="text-[10px] font-bold text-slate-400">
                            {cfg.employee_email}
                          </div>
                        )}
                      </td>
                      <td className="px-6 py-3 text-[11px] font-bold text-slate-600">
                        {cfg.employee_department || '—'}
                      </td>
                      <td className="px-6 py-3">
                        <span
                          className={cn(
                            'inline-flex items-center gap-1 px-2 py-1 rounded-md text-[9px] font-black uppercase tracking-widest',
                            meta?.tone ?? 'bg-slate-100 text-slate-700',
                          )}
                        >
                          <Icon size={9} /> {meta?.label ?? cfg.enforcement_mode}
                        </span>
                      </td>
                      <td className="px-6 py-3">
                        {cfg.fences.length === 0 ? (
                          <span className="text-[10px] text-slate-400 font-bold italic">none</span>
                        ) : (
                          <div className="flex flex-wrap gap-1">
                            {cfg.fences.map((f) => (
                              <span
                                key={f.id}
                                className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md bg-emerald-50 text-emerald-700 text-[9px] font-black uppercase tracking-widest"
                              >
                                <MapPin size={9} /> {f.name}
                              </span>
                            ))}
                          </div>
                        )}
                      </td>
                      <td className="px-6 py-3">
                        <button
                          type="button"
                          onClick={() => toggleGeo(cfg)}
                          className={cn(
                            'inline-flex items-center gap-1.5 text-[10px] font-black uppercase tracking-widest',
                            cfg.geo_enabled ? 'text-emerald-600' : 'text-slate-400',
                          )}
                          title="Toggle geo enforcement"
                        >
                          {cfg.geo_enabled ? <ToggleRight size={20} /> : <ToggleLeft size={20} />}
                          {cfg.geo_enabled ? 'On' : 'Off'}
                        </button>
                      </td>
                      <td className="px-6 py-3 text-right space-x-1">
                        <button
                          type="button"
                          onClick={() => openEdit(cfg)}
                          className="inline-flex items-center px-2.5 py-1.5 rounded-lg text-[9px] font-black uppercase tracking-widest text-slate-600 hover:bg-slate-100"
                        >
                          Edit
                        </button>
                        <button
                          type="button"
                          onClick={() => setDeleteTarget(cfg)}
                          className="inline-flex items-center px-2.5 py-1.5 rounded-lg text-[9px] font-black uppercase tracking-widest text-rose-600 hover:bg-rose-50"
                        >
                          <Trash2 size={11} className="mr-1" /> Remove
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* Single dialog */}
      <Dialog open={singleOpen} onOpenChange={setSingleOpen}>
        <DialogContent className="max-w-lg p-0 overflow-hidden">
          <div className="bg-blue-600 px-6 py-5 text-white">
            <DialogTitle className="text-lg font-black uppercase tracking-tight flex items-center gap-2">
              <Shield size={18} />
              {editing ? `Edit · ${editing.employee_name || `User #${editing.user_id}`}` : 'Assign Employee'}
            </DialogTitle>
          </div>
          <div className="p-6 space-y-5 max-h-[70vh] overflow-y-auto">
            <div>
              <label className="text-[10px] font-black uppercase tracking-widest text-[#0F172A]">
                Employee User ID
              </label>
              <Input
                type="number"
                disabled={!!editing}
                value={singleForm.user_id}
                onChange={(e: any) =>
                  setSingleForm({
                    ...singleForm,
                    user_id: e.target.value === '' ? '' : Number(e.target.value),
                  })
                }
                className="mt-1.5"
                placeholder="e.g. 32"
              />
            </div>

            <div>
              <label className="text-[10px] font-black uppercase tracking-widest text-[#0F172A]">
                Enforcement Mode
              </label>
              <div className="flex gap-2 mt-1.5">
                {(['strict', 'allow_with_flag'] as const).map((m) => (
                  <button
                    key={m}
                    type="button"
                    onClick={() => setSingleForm({ ...singleForm, enforcement_mode: m })}
                    className={cn(
                      'flex-1 px-3 py-2 rounded-xl border text-[10px] font-black uppercase tracking-widest transition-colors',
                      singleForm.enforcement_mode === m
                        ? 'bg-blue-600 text-white border-blue-600'
                        : 'bg-white text-slate-600 border-slate-200 hover:border-blue-300',
                    )}
                  >
                    {MODE_LABELS[m].label}
                  </button>
                ))}
              </div>
              <p className="text-[10px] font-bold text-slate-400 mt-1.5">
                Strict rejects punches outside all fences. Allow + Flag accepts them but raises a flag for HR review.
              </p>
            </div>

            <label className="inline-flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-[#0F172A] cursor-pointer">
              <input
                type="checkbox"
                checked={singleForm.geo_enabled}
                onChange={(e) => setSingleForm({ ...singleForm, geo_enabled: e.target.checked })}
                className="w-3.5 h-3.5 accent-blue-600"
              />
              Geo enforcement enabled
            </label>

            <div>
              <label className="text-[10px] font-black uppercase tracking-widest text-[#0F172A]">
                Allowed Fences
              </label>
              <div className="flex flex-wrap gap-1.5 mt-1.5">
                {fences.filter((f) => f.is_active).map((f) => {
                  const on = singleForm.fence_ids.includes(f.id);
                  return (
                    <button
                      key={f.id}
                      type="button"
                      onClick={() =>
                        setSingleForm({
                          ...singleForm,
                          fence_ids: toggleFenceInSet(singleForm.fence_ids, f.id),
                        })
                      }
                      className={cn(
                        'inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-[10px] font-black uppercase tracking-widest border transition-colors',
                        on
                          ? 'bg-emerald-600 text-white border-emerald-600'
                          : 'bg-white text-slate-600 border-slate-200 hover:border-emerald-300',
                      )}
                    >
                      <MapPin size={10} /> {f.name} · {f.radius_meters}m
                    </button>
                  );
                })}
              </div>
            </div>
          </div>
          <DialogFooter className="px-6 py-4 bg-slate-50 border-t border-slate-100">
            <Button variant="ghost" onClick={() => setSingleOpen(false)} className="text-[10px] font-black uppercase tracking-widest">
              Cancel
            </Button>
            <Button
              onClick={submitSingle}
              isLoading={submitting}
              className="bg-blue-600 hover:bg-blue-700 text-white text-[10px] font-black uppercase tracking-widest"
            >
              {editing ? 'Update' : 'Save'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Bulk dialog */}
      <Dialog open={bulkOpen} onOpenChange={setBulkOpen}>
        <DialogContent className="max-w-xl p-0 overflow-hidden">
          <div className="bg-blue-600 px-6 py-5 text-white">
            <DialogTitle className="text-lg font-black uppercase tracking-tight flex items-center gap-2">
              <Users size={18} />
              Bulk Assign Geo-Fences
            </DialogTitle>
          </div>
          <div className="p-6 space-y-5 max-h-[70vh] overflow-y-auto">
            <div>
              <label className="text-[10px] font-black uppercase tracking-widest text-[#0F172A]">Target</label>
              <div className="flex gap-2 mt-1.5">
                <button
                  type="button"
                  onClick={() => setBulkForm({ ...bulkForm, mode: 'department' })}
                  className={cn(
                    'flex-1 px-3 py-2 rounded-xl border text-[10px] font-black uppercase tracking-widest transition-colors',
                    bulkForm.mode === 'department'
                      ? 'bg-blue-600 text-white border-blue-600'
                      : 'bg-white text-slate-600 border-slate-200 hover:border-blue-300',
                  )}
                >
                  <Building2 size={12} className="inline mr-1" /> By Department
                </button>
                <button
                  type="button"
                  onClick={() => setBulkForm({ ...bulkForm, mode: 'employee_ids' })}
                  className={cn(
                    'flex-1 px-3 py-2 rounded-xl border text-[10px] font-black uppercase tracking-widest transition-colors',
                    bulkForm.mode === 'employee_ids'
                      ? 'bg-blue-600 text-white border-blue-600'
                      : 'bg-white text-slate-600 border-slate-200 hover:border-blue-300',
                  )}
                >
                  <Users size={12} className="inline mr-1" /> By Employee IDs
                </button>
              </div>
            </div>

            {bulkForm.mode === 'department' ? (
              <div>
                <label className="text-[10px] font-black uppercase tracking-widest text-[#0F172A]">
                  Department Name
                </label>
                <Input
                  value={bulkForm.department}
                  onChange={(e: any) => setBulkForm({ ...bulkForm, department: e.target.value })}
                  placeholder="e.g. Field Operations"
                  className="mt-1.5"
                />
              </div>
            ) : (
              <div>
                <label className="text-[10px] font-black uppercase tracking-widest text-[#0F172A]">
                  Employee User IDs
                </label>
                <Input
                  value={bulkForm.employee_ids}
                  onChange={(e: any) => setBulkForm({ ...bulkForm, employee_ids: e.target.value })}
                  placeholder="32, 43, 47"
                  className="mt-1.5"
                />
              </div>
            )}

            <div>
              <label className="text-[10px] font-black uppercase tracking-widest text-[#0F172A]">
                Enforcement Mode
              </label>
              <div className="flex gap-2 mt-1.5">
                {(['strict', 'allow_with_flag'] as const).map((m) => (
                  <button
                    key={m}
                    type="button"
                    onClick={() => setBulkForm({ ...bulkForm, enforcement_mode: m })}
                    className={cn(
                      'flex-1 px-3 py-2 rounded-xl border text-[10px] font-black uppercase tracking-widest transition-colors',
                      bulkForm.enforcement_mode === m
                        ? 'bg-blue-600 text-white border-blue-600'
                        : 'bg-white text-slate-600 border-slate-200 hover:border-blue-300',
                    )}
                  >
                    {MODE_LABELS[m].label}
                  </button>
                ))}
              </div>
            </div>

            <label className="inline-flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-[#0F172A] cursor-pointer">
              <input
                type="checkbox"
                checked={bulkForm.geo_enabled}
                onChange={(e) => setBulkForm({ ...bulkForm, geo_enabled: e.target.checked })}
                className="w-3.5 h-3.5 accent-blue-600"
              />
              Geo enforcement enabled
            </label>

            <div>
              <label className="text-[10px] font-black uppercase tracking-widest text-[#0F172A]">
                Allowed Fences
              </label>
              <div className="flex flex-wrap gap-1.5 mt-1.5">
                {fences.filter((f) => f.is_active).map((f) => {
                  const on = bulkForm.fence_ids.includes(f.id);
                  return (
                    <button
                      key={f.id}
                      type="button"
                      onClick={() =>
                        setBulkForm({
                          ...bulkForm,
                          fence_ids: toggleFenceInSet(bulkForm.fence_ids, f.id),
                        })
                      }
                      className={cn(
                        'inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-[10px] font-black uppercase tracking-widest border transition-colors',
                        on
                          ? 'bg-emerald-600 text-white border-emerald-600'
                          : 'bg-white text-slate-600 border-slate-200 hover:border-emerald-300',
                      )}
                    >
                      <MapPin size={10} /> {f.name}
                    </button>
                  );
                })}
              </div>
            </div>

            {bulkResult && (
              <div className="grid grid-cols-2 gap-2">
                <div className="rounded-xl border border-emerald-100 bg-emerald-50 px-3 py-3 text-center">
                  <div className="text-[9px] font-black uppercase tracking-widest text-emerald-700">Upserted</div>
                  <div className="text-2xl font-black text-emerald-700 tabular-nums">{bulkResult.upserted}</div>
                </div>
                <div className="rounded-xl border border-rose-100 bg-rose-50 px-3 py-3 text-center">
                  <div className="text-[9px] font-black uppercase tracking-widest text-rose-700">Failed</div>
                  <div className="text-2xl font-black text-rose-700 tabular-nums">{bulkResult.failed}</div>
                </div>
                {bulkResult.errors.length > 0 && (
                  <div className="col-span-2 rounded-xl border border-rose-100 bg-rose-50/40 p-3 max-h-32 overflow-y-auto">
                    <ul className="space-y-1">
                      {bulkResult.errors.map((err, i) => (
                        <li key={i} className="text-[11px] text-rose-800 break-all">
                          • {err}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}
          </div>
          <DialogFooter className="px-6 py-4 bg-slate-50 border-t border-slate-100">
            <Button variant="ghost" onClick={() => setBulkOpen(false)} className="text-[10px] font-black uppercase tracking-widest">
              {bulkResult ? 'Done' : 'Cancel'}
            </Button>
            {!bulkResult && (
              <Button
                onClick={submitBulk}
                isLoading={bulkSubmitting}
                className="bg-blue-600 hover:bg-blue-700 text-white text-[10px] font-black uppercase tracking-widest"
              >
                <Plus size={12} className="mr-1.5" /> Apply
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!deleteTarget} onOpenChange={() => setDeleteTarget(null)}>
        <DialogContent className="max-w-md p-0 overflow-hidden">
          <div className="bg-rose-600 px-6 py-5 text-white">
            <DialogTitle className="text-lg font-black uppercase tracking-tight">Remove from Geo Fencing</DialogTitle>
          </div>
          <div className="p-6">
            <p className="text-sm text-slate-700">
              Remove geo enforcement from <strong>{deleteTarget?.employee_name || `user #${deleteTarget?.user_id}`}</strong>?
              Their punches will behave exactly like pre-geo (no checks).
            </p>
          </div>
          <DialogFooter className="px-6 py-4 bg-slate-50 border-t border-slate-100">
            <Button variant="ghost" onClick={() => setDeleteTarget(null)} className="text-[10px] font-black uppercase tracking-widest">
              Cancel
            </Button>
            <Button onClick={confirmDelete} className="bg-rose-600 hover:bg-rose-700 text-white text-[10px] font-black uppercase tracking-widest">
              Remove
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};
