import React, { useEffect, useMemo, useState } from 'react';
import {
  Plus,
  Edit2,
  Trash2,
  Power,
  Search,
  RefreshCw,
  MapPin,
  Crosshair,
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
  created_at: string;
  updated_at: string;
}

const MIN_RADIUS = 100;

const emptyForm = {
  name: '',
  latitude: '' as number | '',
  longitude: '' as number | '',
  radius_meters: 200 as number,
  is_active: true,
};

const errMsg = (err: any, fallback: string): string => {
  const detail = err?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail))
    return detail.map((d: any) => d?.msg || JSON.stringify(d)).join('; ');
  return err?.message || fallback;
};

export const GeoFenceLocationsAdmin: React.FC = () => {
  const [items, setItems] = useState<GeoFence[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [showInactive, setShowInactive] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<GeoFence | null>(null);
  const [form, setForm] = useState(emptyForm);
  const [submitting, setSubmitting] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<GeoFence | null>(null);

  const fetchItems = async () => {
    setLoading(true);
    try {
      const res = await client.get(ENDPOINTS.GEO.FENCES, {
        params: showInactive ? { include_inactive: true } : {},
      });
      setItems(res.data || []);
    } catch (e: any) {
      toast.error(errMsg(e, 'Failed to load fences'));
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
    return items.filter((i) => i.name.toLowerCase().includes(q));
  }, [items, search]);

  const openCreate = () => {
    setEditing(null);
    setForm(emptyForm);
    setModalOpen(true);
  };

  const openEdit = (it: GeoFence) => {
    setEditing(it);
    setForm({
      name: it.name,
      latitude: it.latitude,
      longitude: it.longitude,
      radius_meters: it.radius_meters,
      is_active: it.is_active,
    });
    setModalOpen(true);
  };

  const useMyLocation = () => {
    if (!navigator.geolocation) {
      toast.error('Geolocation not available in this browser');
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setForm((f) => ({
          ...f,
          latitude: Number(pos.coords.latitude.toFixed(6)),
          longitude: Number(pos.coords.longitude.toFixed(6)),
        }));
        toast.success('Coordinates filled from device GPS');
      },
      (err) => toast.error(`GPS failed: ${err.message}`),
      { enableHighAccuracy: true, timeout: 8000 },
    );
  };

  const submit = async () => {
    if (!form.name.trim()) {
      toast.error('Name is required');
      return;
    }
    if (form.latitude === '' || form.longitude === '') {
      toast.error('Latitude and longitude are required');
      return;
    }
    if (form.radius_meters < MIN_RADIUS) {
      toast.error(`Radius must be at least ${MIN_RADIUS}m`);
      return;
    }
    setSubmitting(true);
    try {
      const payload = {
        name: form.name.trim(),
        latitude: Number(form.latitude),
        longitude: Number(form.longitude),
        radius_meters: Number(form.radius_meters),
        is_active: form.is_active,
      };
      if (editing) {
        await client.patch(ENDPOINTS.GEO.FENCE_DETAIL(editing.id), payload);
        toast.success('Fence updated');
      } else {
        await client.post(ENDPOINTS.GEO.FENCES, payload);
        toast.success('Fence created');
      }
      setModalOpen(false);
      fetchItems();
    } catch (e: any) {
      toast.error(errMsg(e, 'Save failed'));
    } finally {
      setSubmitting(false);
    }
  };

  const toggleActive = async (it: GeoFence) => {
    try {
      await client.patch(ENDPOINTS.GEO.FENCE_DETAIL(it.id), {
        is_active: !it.is_active,
      });
      toast.success(it.is_active ? 'Deactivated' : 'Reactivated');
      fetchItems();
    } catch (e: any) {
      toast.error(errMsg(e, 'Toggle failed'));
    }
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    try {
      await client.delete(ENDPOINTS.GEO.FENCE_DETAIL(deleteTarget.id));
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
            Geo-Fence Locations
          </h2>
          <p className="text-[#64748B] font-bold uppercase tracking-widest text-[10px] mt-1">
            Sites Where Employees Are Allowed To Punch From · Min Radius {MIN_RADIUS}m
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
              onChange={(e) => setShowInactive(e.target.checked)}
              className="w-3.5 h-3.5 accent-blue-600"
            />
            Show Inactive
          </label>
          <Button
            onClick={openCreate}
            className="h-10 bg-blue-600 hover:bg-blue-700 text-white font-black uppercase text-[10px] tracking-widest"
          >
            <Plus size={14} className="mr-1.5" />
            New Fence
          </Button>
        </div>
      </div>

      <Card className="p-0 border-slate-200 overflow-hidden bg-white">
        <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between bg-slate-50/40 gap-4">
          <h4 className="text-sm font-black text-[#0F172A] tracking-tight uppercase">
            Fences
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
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search fence name..."
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
            No fences yet — add one to start enforcing punch locations.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead className="bg-white border-b border-slate-100">
                <tr>
                  <th className="px-6 py-3 text-[9px] font-black text-slate-400 uppercase tracking-widest">Name</th>
                  <th className="px-6 py-3 text-[9px] font-black text-slate-400 uppercase tracking-widest">Coordinates</th>
                  <th className="px-6 py-3 text-[9px] font-black text-slate-400 uppercase tracking-widest w-32">Radius</th>
                  <th className="px-6 py-3 text-[9px] font-black text-slate-400 uppercase tracking-widest w-28">Status</th>
                  <th className="px-6 py-3 text-right text-[9px] font-black text-slate-400 uppercase tracking-widest w-40">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {filtered.map((it) => (
                  <tr key={it.id} className="hover:bg-slate-50/60 transition-colors">
                    <td className="px-6 py-3">
                      <div className="flex items-center gap-2">
                        <MapPin size={14} className="text-emerald-500" />
                        <span className="text-sm font-black text-[#0F172A]">{it.name}</span>
                      </div>
                    </td>
                    <td className="px-6 py-3 text-[11px] font-bold text-slate-600 tabular-nums">
                      {it.latitude.toFixed(6)}, {it.longitude.toFixed(6)}
                    </td>
                    <td className="px-6 py-3 text-sm font-black text-[#0F172A] tabular-nums">
                      {it.radius_meters}m
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
        <DialogContent className="max-w-lg p-0 overflow-hidden">
          <div className="bg-blue-600 px-6 py-5 text-white">
            <DialogTitle className="text-lg font-black uppercase tracking-tight flex items-center gap-2">
              <MapPin size={18} />
              {editing ? 'Edit Fence' : 'New Geo-Fence'}
            </DialogTitle>
          </div>
          <div className="p-6 space-y-5 max-h-[70vh] overflow-y-auto">
            <div>
              <label className="text-[10px] font-black uppercase tracking-widest text-[#0F172A]">Name</label>
              <Input
                value={form.name}
                onChange={(e: any) => setForm({ ...form, name: e.target.value })}
                placeholder="e.g. HQ Kolkata, Client Site - SPML"
                maxLength={120}
                className="mt-1.5"
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="text-[10px] font-black uppercase tracking-widest text-[#0F172A]">Latitude</label>
                <Input
                  type="number"
                  step={0.000001}
                  min={-90}
                  max={90}
                  value={form.latitude}
                  onChange={(e: any) =>
                    setForm({
                      ...form,
                      latitude: e.target.value === '' ? '' : Number(e.target.value),
                    })
                  }
                  placeholder="22.5726"
                  className="mt-1.5"
                />
              </div>
              <div>
                <label className="text-[10px] font-black uppercase tracking-widest text-[#0F172A]">Longitude</label>
                <Input
                  type="number"
                  step={0.000001}
                  min={-180}
                  max={180}
                  value={form.longitude}
                  onChange={(e: any) =>
                    setForm({
                      ...form,
                      longitude: e.target.value === '' ? '' : Number(e.target.value),
                    })
                  }
                  placeholder="88.3639"
                  className="mt-1.5"
                />
              </div>
            </div>

            <button
              type="button"
              onClick={useMyLocation}
              className="inline-flex items-center gap-1.5 text-[10px] font-black uppercase tracking-widest text-blue-600 hover:underline"
            >
              <Crosshair size={12} />
              Use my current location
            </button>

            <div>
              <label className="text-[10px] font-black uppercase tracking-widest text-[#0F172A]">
                Radius (metres) ·{' '}
                <span className="text-slate-500 normal-case font-bold">min {MIN_RADIUS}</span>
              </label>
              <Input
                type="number"
                min={MIN_RADIUS}
                max={10000}
                step={10}
                value={form.radius_meters}
                onChange={(e: any) =>
                  setForm({ ...form, radius_meters: Number(e.target.value) || 0 })
                }
                className="mt-1.5"
              />
              {form.radius_meters < MIN_RADIUS && (
                <p className="text-[10px] font-bold text-rose-600 mt-1">
                  Below {MIN_RADIUS}m radius would be too tight for consumer-grade GPS noise.
                </p>
              )}
            </div>

            <label className="inline-flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-[#0F172A] cursor-pointer">
              <input
                type="checkbox"
                checked={form.is_active}
                onChange={(e) => setForm({ ...form, is_active: e.target.checked })}
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
            <DialogTitle className="text-lg font-black uppercase tracking-tight">Delete Fence</DialogTitle>
          </div>
          <div className="p-6">
            <p className="text-sm text-slate-700">
              Delete <strong>{deleteTarget?.name}</strong>? Blocked if any employee still allowlists it — deactivate instead.
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
