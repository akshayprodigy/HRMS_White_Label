import React, { useEffect, useMemo, useState } from 'react';
import { Plus, Edit2, Trash2, Power, Search, RefreshCw } from 'lucide-react';
import { Card, Button, Badge, cn } from './ui-elements';
import { toast } from 'sonner@2.0.3';
import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';
import { Dialog, DialogContent, DialogTitle, DialogFooter } from './ui/dialog';
import { Input } from './ui/input';

interface FunctionalArea {
  id: number;
  name: string;
  code: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

const emptyForm = { name: '', code: '', is_active: true };

const errMsg = (err: any, fallback: string): string => {
  const detail = err?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) return detail.map((d: any) => d?.msg || JSON.stringify(d)).join('; ');
  return err?.message || fallback;
};

export const FunctionalAreasAdmin: React.FC = () => {
  const [items, setItems] = useState<FunctionalArea[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [showInactive, setShowInactive] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<FunctionalArea | null>(null);
  const [form, setForm] = useState(emptyForm);
  const [submitting, setSubmitting] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<FunctionalArea | null>(null);

  const fetchItems = async () => {
    setLoading(true);
    try {
      const res = await client.get(ENDPOINTS.ADMIN.FUNCTIONAL_AREAS, {
        params: showInactive ? { include_inactive: true } : {},
      });
      setItems(res.data || []);
    } catch (e: any) {
      toast.error(errMsg(e, 'Failed to load functional areas'));
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
      i =>
        i.name.toLowerCase().includes(q) || i.code.toLowerCase().includes(q),
    );
  }, [items, search]);

  const openCreate = () => {
    setEditing(null);
    setForm(emptyForm);
    setModalOpen(true);
  };

  const openEdit = (it: FunctionalArea) => {
    setEditing(it);
    setForm({ name: it.name, code: it.code, is_active: it.is_active });
    setModalOpen(true);
  };

  const submit = async () => {
    if (!form.name.trim() || !form.code.trim()) {
      toast.error('Code and Name are required');
      return;
    }
    setSubmitting(true);
    try {
      if (editing) {
        await client.patch(
          ENDPOINTS.ADMIN.FUNCTIONAL_AREA_DETAIL(editing.id),
          form,
        );
        toast.success('Functional area updated');
      } else {
        await client.post(ENDPOINTS.ADMIN.FUNCTIONAL_AREAS, form);
        toast.success('Functional area created');
      }
      setModalOpen(false);
      fetchItems();
    } catch (e: any) {
      toast.error(errMsg(e, 'Save failed'));
    } finally {
      setSubmitting(false);
    }
  };

  const toggleActive = async (it: FunctionalArea) => {
    try {
      await client.patch(
        ENDPOINTS.ADMIN.FUNCTIONAL_AREA_DETAIL(it.id),
        { is_active: !it.is_active },
      );
      toast.success(it.is_active ? 'Deactivated' : 'Reactivated');
      fetchItems();
    } catch (e: any) {
      toast.error(errMsg(e, 'Toggle failed'));
    }
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    try {
      await client.delete(
        ENDPOINTS.ADMIN.FUNCTIONAL_AREA_DETAIL(deleteTarget.id),
      );
      toast.success(`"${deleteTarget.name}" deleted`);
      setDeleteTarget(null);
      fetchItems();
    } catch (e: any) {
      toast.error(errMsg(e, 'Delete failed'));
    }
  };

  return (
    <div className="p-8 space-y-6 max-w-[1400px] mx-auto animate-in fade-in duration-300">
      <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-4">
        <div>
          <h2 className="text-3xl font-black text-[#0F172A] tracking-tighter uppercase">
            Functional Areas
          </h2>
          <p className="text-[#64748B] font-bold uppercase tracking-widest text-[10px] mt-1">
            Project Classification Taxonomy · Used By Bulk Import &amp; Project Master
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
            Add Area
          </Button>
        </div>
      </div>

      <Card className="p-0 border-slate-200 overflow-hidden bg-white">
        <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between bg-slate-50/40 gap-4">
          <h4 className="text-sm font-black text-[#0F172A] tracking-tight uppercase">
            Functional Areas
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
            No functional areas
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead className="bg-white border-b border-slate-100">
                <tr>
                  <th className="px-6 py-3 text-[9px] font-black text-slate-400 uppercase tracking-widest w-32">Code</th>
                  <th className="px-6 py-3 text-[9px] font-black text-slate-400 uppercase tracking-widest">Name</th>
                  <th className="px-6 py-3 text-[9px] font-black text-slate-400 uppercase tracking-widest w-28">Status</th>
                  <th className="px-6 py-3 text-right text-[9px] font-black text-slate-400 uppercase tracking-widest w-40">Actions</th>
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
                      <button
                        type="button"
                        onClick={() => setDeleteTarget(it)}
                        className="inline-flex items-center px-2.5 py-1.5 rounded-lg text-[9px] font-black uppercase tracking-widest text-rose-600 hover:bg-rose-50"
                      >
                        <Trash2 size={11} className="mr-1" /> Delete
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
              {editing ? 'Edit Functional Area' : 'New Functional Area'}
            </DialogTitle>
          </div>
          <div className="p-6 space-y-4">
            <div>
              <label className="text-[10px] font-black uppercase tracking-widest text-[#0F172A]">
                Code
              </label>
              <Input
                value={form.code}
                onChange={(e: any) => setForm({ ...form, code: e.target.value.toUpperCase() })}
                placeholder="e.g. GR"
                maxLength={20}
                className="mt-1.5"
              />
              <p className="text-[9px] font-bold text-slate-400 mt-1">
                Short identifier used in bulk-import sheets. Uppercase.
              </p>
            </div>
            <div>
              <label className="text-[10px] font-black uppercase tracking-widest text-[#0F172A]">
                Name
              </label>
              <Input
                value={form.name}
                onChange={(e: any) => setForm({ ...form, name: e.target.value })}
                placeholder="e.g. Geological Report - Coal"
                maxLength={200}
                className="mt-1.5"
              />
            </div>
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

      <Dialog open={!!deleteTarget} onOpenChange={() => setDeleteTarget(null)}>
        <DialogContent className="max-w-md p-0 overflow-hidden">
          <div className="bg-rose-600 px-6 py-5 text-white">
            <DialogTitle className="text-lg font-black uppercase tracking-tight">
              Delete Functional Area
            </DialogTitle>
          </div>
          <div className="p-6">
            <p className="text-sm text-slate-700">
              Delete <strong>{deleteTarget?.name}</strong>? Blocked if any project still references it — deactivate instead.
            </p>
          </div>
          <DialogFooter className="px-6 py-4 bg-slate-50 border-t border-slate-100">
            <Button
              variant="ghost"
              onClick={() => setDeleteTarget(null)}
              className="text-[10px] font-black uppercase tracking-widest"
            >
              Cancel
            </Button>
            <Button
              onClick={confirmDelete}
              className="bg-rose-600 hover:bg-rose-700 text-white text-[10px] font-black uppercase tracking-widest"
            >
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};
