import React, { useEffect, useMemo, useState } from 'react';
import { Plus, Edit2, Power, Search, RefreshCw } from 'lucide-react';
import { Card, Button, Badge, cn } from './ui-elements';
import { toast } from 'sonner';
import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';
import { Dialog, DialogContent, DialogTitle, DialogFooter } from './ui/dialog';
import { Input } from './ui/input';

interface EmploymentType {
  id: number;
  code: string;
  name: string;
  is_on_payroll: boolean;
  statutory_enabled: boolean;
  flat_tds_rate: number | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

const emptyForm = {
  code: '',
  name: '',
  is_on_payroll: true,
  statutory_enabled: true,
  flat_tds_rate: '' as string,
  is_active: true,
};

const errMsg = (err: any, fallback: string): string => {
  const detail = err?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) return detail.map((d: any) => d?.msg || JSON.stringify(d)).join('; ');
  return err?.message || fallback;
};

export const EmploymentTypesAdmin: React.FC = () => {
  const [items, setItems] = useState<EmploymentType[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [showInactive, setShowInactive] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<EmploymentType | null>(null);
  const [form, setForm] = useState(emptyForm);
  const [submitting, setSubmitting] = useState(false);

  const fetchItems = async () => {
    setLoading(true);
    try {
      const res = await client.get(ENDPOINTS.HR.EMPLOYMENT_TYPES, {
        params: showInactive ? { include_inactive: true } : {},
      });
      setItems(res.data || []);
    } catch (e: any) {
      toast.error(errMsg(e, 'Failed to load employment types'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchItems();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showInactive]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return items;
    return items.filter(
      i => i.name.toLowerCase().includes(q) || i.code.toLowerCase().includes(q),
    );
  }, [items, search]);

  const openCreate = () => {
    setEditing(null);
    setForm(emptyForm);
    setModalOpen(true);
  };

  const openEdit = (it: EmploymentType) => {
    setEditing(it);
    setForm({
      code: it.code,
      name: it.name,
      is_on_payroll: it.is_on_payroll,
      statutory_enabled: it.statutory_enabled,
      flat_tds_rate: it.flat_tds_rate == null ? '' : String(it.flat_tds_rate),
      is_active: it.is_active,
    });
    setModalOpen(true);
  };

  const submit = async () => {
    if (!form.code.trim() || !form.name.trim()) {
      toast.error('Code and Name are required');
      return;
    }
    const rate = form.flat_tds_rate.trim() === '' ? null : Number(form.flat_tds_rate);
    if (rate != null && (isNaN(rate) || rate < 0 || rate > 1)) {
      toast.error('Flat TDS rate must be a fraction between 0 and 1 (e.g. 0.10)');
      return;
    }
    setSubmitting(true);
    try {
      if (editing) {
        // code is immutable on the backend — omit it from the patch.
        await client.patch(ENDPOINTS.HR.EMPLOYMENT_TYPE_DETAIL(editing.id), {
          name: form.name,
          is_on_payroll: form.is_on_payroll,
          statutory_enabled: form.statutory_enabled,
          flat_tds_rate: rate,
          is_active: form.is_active,
        });
        toast.success('Employment type updated');
      } else {
        await client.post(ENDPOINTS.HR.EMPLOYMENT_TYPES, {
          code: form.code,
          name: form.name,
          is_on_payroll: form.is_on_payroll,
          statutory_enabled: form.statutory_enabled,
          flat_tds_rate: rate,
          is_active: form.is_active,
        });
        toast.success('Employment type created');
      }
      setModalOpen(false);
      fetchItems();
    } catch (e: any) {
      toast.error(errMsg(e, 'Save failed'));
    } finally {
      setSubmitting(false);
    }
  };

  const toggleActive = async (it: EmploymentType) => {
    try {
      await client.patch(ENDPOINTS.HR.EMPLOYMENT_TYPE_DETAIL(it.id), {
        is_active: !it.is_active,
      });
      toast.success(it.is_active ? 'Deactivated' : 'Reactivated');
      fetchItems();
    } catch (e: any) {
      toast.error(errMsg(e, 'Toggle failed'));
    }
  };

  return (
    <div className="p-8 space-y-6 max-w-[1400px] mx-auto animate-in fade-in duration-300">
      <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-4">
        <div>
          <h2 className="text-3xl font-black text-[#0F172A] tracking-tighter uppercase">
            Employment Types
          </h2>
          <p className="text-[#64748B] font-bold uppercase tracking-widest text-[10px] mt-1">
            Payroll Profile Master · Drives Statutory vs Flat-TDS Calculation
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={fetchItems}
            className="p-2 text-slate-400 hover:text-blue-600 transition-colors"
            title="Refresh"
            aria-label="Refresh"
          >
            <RefreshCw size={16} className={cn(loading && 'animate-spin')} />
          </button>
          <label className="inline-flex items-center gap-2 px-4 h-10 bg-white border border-slate-200 rounded-xl text-[10px] font-black uppercase tracking-widest text-[#0F172A] cursor-pointer hover:border-blue-600 transition-colors">
            <input
              type="checkbox"
              checked={showInactive}
              onChange={e => setShowInactive(e.target.checked)}
              className="w-3.5 h-3.5 accent-blue-600"
            />
            Show Inactive
          </label>
          <Button
            onClick={openCreate}
            className="h-10 bg-blue-600 hover:bg-blue-700 text-white font-black uppercase text-[10px] tracking-widest"
          >
            <Plus size={14} className="mr-1.5" />
            Add Type
          </Button>
        </div>
      </div>

      <Card className="p-0 border-slate-200 overflow-hidden bg-white">
        <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between bg-slate-50/40 gap-4">
          <h4 className="text-sm font-black text-[#0F172A] tracking-tight uppercase">
            Types
            {!loading && (
              <span className="ml-2 text-slate-400 font-bold text-[10px]">
                ({filtered.length}/{items.length})
              </span>
            )}
          </h4>
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 pointer-events-none" />
            <input
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Search code or name..."
              className="pl-10 pr-4 h-9 bg-white border border-slate-200 rounded-xl text-[10px] font-black uppercase tracking-widest w-64 focus:ring-2 focus:ring-blue-600/10 outline-none"
            />
          </div>
        </div>
        {loading ? (
          <div className="py-16 text-center text-[10px] font-black uppercase tracking-widest text-slate-400 animate-pulse">
            Loading…
          </div>
        ) : filtered.length === 0 ? (
          <div className="py-16 text-center text-[10px] font-black uppercase tracking-widest text-slate-400">
            No employment types
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead className="bg-white border-b border-slate-100">
                <tr>
                  <th className="px-6 py-3 text-[9px] font-black text-slate-400 uppercase tracking-widest w-32">Code</th>
                  <th className="px-6 py-3 text-[9px] font-black text-slate-400 uppercase tracking-widest">Name</th>
                  <th className="px-6 py-3 text-[9px] font-black text-slate-400 uppercase tracking-widest w-32">On Payroll</th>
                  <th className="px-6 py-3 text-[9px] font-black text-slate-400 uppercase tracking-widest w-32">Statutory</th>
                  <th className="px-6 py-3 text-[9px] font-black text-slate-400 uppercase tracking-widest w-28">Flat TDS</th>
                  <th className="px-6 py-3 text-[9px] font-black text-slate-400 uppercase tracking-widest w-24">Status</th>
                  <th className="px-6 py-3 text-right text-[9px] font-black text-slate-400 uppercase tracking-widest w-32">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {filtered.map(it => (
                  <tr key={it.id} className="hover:bg-slate-50/60 transition-colors">
                    <td className="px-6 py-3">
                      <span className="inline-flex items-center px-2.5 py-1 rounded-lg bg-blue-50 text-blue-700 text-[10px] font-black uppercase tracking-widest tabular-nums">
                        {it.code}
                      </span>
                    </td>
                    <td className="px-6 py-3 text-sm font-black text-[#0F172A]">{it.name}</td>
                    <td className="px-6 py-3">
                      <Badge variant={it.is_on_payroll ? 'success' : 'neutral'} className="text-[8px] uppercase">
                        {it.is_on_payroll ? 'Yes' : 'No'}
                      </Badge>
                    </td>
                    <td className="px-6 py-3">
                      <Badge variant={it.statutory_enabled ? 'success' : 'warning'} className="text-[8px] uppercase">
                        {it.statutory_enabled ? 'PF/ESI/PT' : 'Flat TDS'}
                      </Badge>
                    </td>
                    <td className="px-6 py-3 text-sm font-bold text-[#0F172A] tabular-nums">
                      {it.statutory_enabled ? '—' : it.flat_tds_rate == null ? '10%' : `${(it.flat_tds_rate * 100).toFixed(0)}%`}
                    </td>
                    <td className="px-6 py-3">
                      <Badge variant={it.is_active ? 'success' : 'neutral'} className="text-[8px] uppercase">
                        {it.is_active ? 'Active' : 'Inactive'}
                      </Badge>
                    </td>
                    <td className="px-6 py-3 text-right space-x-1">
                      <button
                        type="button"
                        onClick={() => openEdit(it)}
                        className="inline-flex items-center px-2.5 py-1.5 rounded-lg text-[9px] font-black uppercase tracking-widest text-slate-600 hover:bg-slate-100"
                      >
                        <Edit2 size={11} className="mr-1" /> Edit
                      </button>
                      <button
                        type="button"
                        onClick={() => toggleActive(it)}
                        className={cn(
                          'inline-flex items-center px-2.5 py-1.5 rounded-lg text-[9px] font-black uppercase tracking-widest',
                          it.is_active
                            ? 'text-amber-700 hover:bg-amber-50'
                            : 'text-emerald-700 hover:bg-emerald-50',
                        )}
                      >
                        <Power size={11} className="mr-1" />
                        {it.is_active ? 'Off' : 'On'}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Dialog open={modalOpen} onOpenChange={setModalOpen}>
        <DialogContent className="max-w-md p-0 overflow-hidden">
          <div className="bg-blue-600 px-6 py-5 text-white">
            <DialogTitle className="text-lg font-black uppercase tracking-tight">
              {editing ? 'Edit Employment Type' : 'New Employment Type'}
            </DialogTitle>
          </div>
          <div className="p-6 space-y-4">
            <div>
              <label className="text-[10px] font-black uppercase tracking-widest text-[#0F172A]">
                Code
              </label>
              <Input
                value={form.code}
                onChange={(e: any) => setForm({ ...form, code: e.target.value.toLowerCase() })}
                placeholder="e.g. consultant"
                maxLength={20}
                disabled={!!editing}
                className="mt-1.5"
              />
              <p className="text-[9px] font-bold text-slate-400 mt-1">
                Matches Employee.employment_type. Lowercase. {editing && 'Immutable once created.'}
              </p>
            </div>
            <div>
              <label className="text-[10px] font-black uppercase tracking-widest text-[#0F172A]">
                Name
              </label>
              <Input
                value={form.name}
                onChange={(e: any) => setForm({ ...form, name: e.target.value })}
                placeholder="e.g. Consultant (off-payroll)"
                maxLength={60}
                className="mt-1.5"
              />
            </div>
            <label className="inline-flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-[#0F172A] cursor-pointer">
              <input
                type="checkbox"
                checked={form.is_on_payroll}
                onChange={e => setForm({ ...form, is_on_payroll: e.target.checked })}
                className="w-3.5 h-3.5 accent-blue-600"
              />
              On Payroll
            </label>
            <div>
              <label className="inline-flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-[#0F172A] cursor-pointer">
                <input
                  type="checkbox"
                  checked={form.statutory_enabled}
                  onChange={e => setForm({ ...form, statutory_enabled: e.target.checked })}
                  className="w-3.5 h-3.5 accent-blue-600"
                />
                Statutory (PF / ESI / PT / regular TDS)
              </label>
              <p className="text-[9px] font-bold text-slate-400 mt-1">
                Uncheck for contractual/advisor profiles that use a flat TDS rate instead.
              </p>
            </div>
            {!form.statutory_enabled && (
              <div>
                <label className="text-[10px] font-black uppercase tracking-widest text-[#0F172A]">
                  Flat TDS Rate (fraction)
                </label>
                <Input
                  value={form.flat_tds_rate}
                  onChange={(e: any) => setForm({ ...form, flat_tds_rate: e.target.value })}
                  placeholder="e.g. 0.10 for 10%"
                  className="mt-1.5"
                />
                <p className="text-[9px] font-bold text-slate-400 mt-1">
                  Leave blank to use the default 10%.
                </p>
              </div>
            )}
            <label className="inline-flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-[#0F172A] cursor-pointer">
              <input
                type="checkbox"
                checked={form.is_active}
                onChange={e => setForm({ ...form, is_active: e.target.checked })}
                className="w-3.5 h-3.5 accent-blue-600"
              />
              Active
            </label>
          </div>
          <DialogFooter className="px-6 py-4 bg-slate-50 border-t border-slate-100">
            <Button
              variant="ghost"
              onClick={() => setModalOpen(false)}
              className="text-[10px] font-black uppercase tracking-widest"
            >
              Cancel
            </Button>
            <Button
              onClick={submit}
              isLoading={submitting}
              className="bg-blue-600 hover:bg-blue-700 text-white text-[10px] font-black uppercase tracking-widest"
            >
              {editing ? 'Update' : 'Create'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};
