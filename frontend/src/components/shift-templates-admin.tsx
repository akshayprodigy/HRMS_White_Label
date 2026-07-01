import React, { useEffect, useMemo, useState } from 'react';
import {
  Plus,
  Edit2,
  Trash2,
  Power,
  Search,
  RefreshCw,
  Moon,
  Sun,
  Clock,
} from 'lucide-react';
import { Card, Button, Badge, cn } from './ui-elements';
import { toast } from 'sonner';
import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';
import { Dialog, DialogContent, DialogTitle, DialogFooter } from './ui/dialog';
import { Input } from './ui/input';

interface ShiftTemplate {
  id: number;
  name: string;
  start_time: string; // "HH:MM:SS"
  end_time: string;
  is_overnight: boolean;
  break_minutes: number;
  grace_in_minutes: number;
  grace_out_minutes: number;
  full_day_hours: number;
  half_day_hours: number;
  weekly_offs: number[];
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

const WEEKDAY_LABELS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

const errMsg = (err: any, fallback: string): string => {
  const detail = err?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail))
    return detail.map((d: any) => d?.msg || JSON.stringify(d)).join('; ');
  return err?.message || fallback;
};

const emptyForm = {
  name: '',
  start_time: '09:00',
  end_time: '18:00',
  break_minutes: 60,
  grace_in_minutes: 10,
  grace_out_minutes: 10,
  full_day_hours: 9.0,
  half_day_hours: 4.5,
  weekly_offs: [6] as number[], // Sunday off by default
  is_active: true,
};

// Normalize "HH:MM:SS" or "HH:MM" -> "HH:MM" for <input type=time>.
const toHHMM = (t: string | undefined): string => {
  if (!t) return '';
  const parts = t.split(':');
  return parts.length >= 2 ? `${parts[0]}:${parts[1]}` : t;
};

// Add ":00" seconds for the backend Time column.
const toHHMMSS = (t: string): string =>
  t.length === 5 ? `${t}:00` : t;

const fmtTime = (t: string): string => toHHMM(t);

export const ShiftTemplatesAdmin: React.FC = () => {
  const [items, setItems] = useState<ShiftTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [showInactive, setShowInactive] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<ShiftTemplate | null>(null);
  const [form, setForm] = useState(emptyForm);
  const [submitting, setSubmitting] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<ShiftTemplate | null>(null);

  const fetchItems = async () => {
    setLoading(true);
    try {
      const res = await client.get(ENDPOINTS.SHIFTS.TEMPLATES, {
        params: showInactive ? { include_inactive: true } : {},
      });
      setItems(res.data || []);
    } catch (e: any) {
      toast.error(errMsg(e, 'Failed to load shift templates'));
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

  const openEdit = (it: ShiftTemplate) => {
    setEditing(it);
    setForm({
      name: it.name,
      start_time: toHHMM(it.start_time),
      end_time: toHHMM(it.end_time),
      break_minutes: it.break_minutes,
      grace_in_minutes: it.grace_in_minutes,
      grace_out_minutes: it.grace_out_minutes,
      full_day_hours: it.full_day_hours,
      half_day_hours: it.half_day_hours,
      weekly_offs: it.weekly_offs ?? [],
      is_active: it.is_active,
    });
    setModalOpen(true);
  };

  const toggleWeeklyOff = (day: number) => {
    setForm((f) => ({
      ...f,
      weekly_offs: f.weekly_offs.includes(day)
        ? f.weekly_offs.filter((d) => d !== day)
        : [...f.weekly_offs, day].sort((a, b) => a - b),
    }));
  };

  const submit = async () => {
    if (!form.name.trim()) {
      toast.error('Name is required');
      return;
    }
    if (!form.start_time || !form.end_time) {
      toast.error('Start and end time are required');
      return;
    }
    if (form.start_time === form.end_time) {
      toast.error('Start and end time cannot be equal');
      return;
    }
    if (form.half_day_hours > form.full_day_hours) {
      toast.error('Half-day hours cannot exceed full-day hours');
      return;
    }

    const payload = {
      ...form,
      start_time: toHHMMSS(form.start_time),
      end_time: toHHMMSS(form.end_time),
    };

    setSubmitting(true);
    try {
      if (editing) {
        await client.patch(
          ENDPOINTS.SHIFTS.TEMPLATE_DETAIL(editing.id),
          payload,
        );
        toast.success('Shift template updated');
      } else {
        await client.post(ENDPOINTS.SHIFTS.TEMPLATES, payload);
        toast.success('Shift template created');
      }
      setModalOpen(false);
      fetchItems();
    } catch (e: any) {
      toast.error(errMsg(e, 'Save failed'));
    } finally {
      setSubmitting(false);
    }
  };

  const toggleActive = async (it: ShiftTemplate) => {
    try {
      await client.patch(ENDPOINTS.SHIFTS.TEMPLATE_DETAIL(it.id), {
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
      await client.delete(
        ENDPOINTS.SHIFTS.TEMPLATE_DETAIL(deleteTarget.id),
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
            Shift Templates
          </h2>
          <p className="text-[#64748B] font-bold uppercase tracking-widest text-[10px] mt-1">
            Reusable Shift Patterns · Assigned To Employees &amp; Teams
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
            New Shift
          </Button>
        </div>
      </div>

      <Card className="p-0 border-slate-200 overflow-hidden bg-white">
        <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between bg-slate-50/40 gap-4">
          <h4 className="text-sm font-black text-[#0F172A] tracking-tight uppercase">
            Templates
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
              placeholder="Search shift name..."
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
            No shift templates yet — create your first one.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead className="bg-white border-b border-slate-100">
                <tr>
                  <th className="px-6 py-3 text-[9px] font-black text-slate-400 uppercase tracking-widest">
                    Name
                  </th>
                  <th className="px-6 py-3 text-[9px] font-black text-slate-400 uppercase tracking-widest">
                    Timing
                  </th>
                  <th className="px-6 py-3 text-[9px] font-black text-slate-400 uppercase tracking-widest">
                    Hours
                  </th>
                  <th className="px-6 py-3 text-[9px] font-black text-slate-400 uppercase tracking-widest">
                    Weekly Off
                  </th>
                  <th className="px-6 py-3 text-[9px] font-black text-slate-400 uppercase tracking-widest w-28">
                    Status
                  </th>
                  <th className="px-6 py-3 text-right text-[9px] font-black text-slate-400 uppercase tracking-widest w-40">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {filtered.map((it) => (
                  <tr
                    key={it.id}
                    className="hover:bg-slate-50/60 transition-colors"
                  >
                    <td className="px-6 py-3">
                      <div className="flex items-center gap-2">
                        {it.is_overnight ? (
                          <Moon
                            size={14}
                            className="text-indigo-500"
                            aria-label="Overnight shift"
                          />
                        ) : (
                          <Sun
                            size={14}
                            className="text-amber-500"
                            aria-label="Day shift"
                          />
                        )}
                        <span className="text-sm font-black text-[#0F172A]">
                          {it.name}
                        </span>
                      </div>
                    </td>
                    <td className="px-6 py-3 text-xs font-bold text-slate-700 tabular-nums">
                      {fmtTime(it.start_time)} → {fmtTime(it.end_time)}
                      {it.is_overnight && (
                        <span className="ml-1 text-[9px] uppercase tracking-widest font-black text-indigo-600">
                          (+1d)
                        </span>
                      )}
                    </td>
                    <td className="px-6 py-3 text-[11px] text-slate-600">
                      <span className="font-black text-slate-900">
                        {it.full_day_hours}h
                      </span>{' '}
                      full ·{' '}
                      <span className="font-black text-slate-700">
                        {it.half_day_hours}h
                      </span>{' '}
                      half · {it.break_minutes}m break
                    </td>
                    <td className="px-6 py-3">
                      {it.weekly_offs.length === 0 ? (
                        <span className="text-[10px] text-slate-400 font-bold">
                          —
                        </span>
                      ) : (
                        <div className="flex flex-wrap gap-1">
                          {it.weekly_offs.map((d) => (
                            <span
                              key={d}
                              className="inline-flex items-center px-1.5 py-0.5 rounded-md bg-slate-100 text-slate-700 text-[9px] font-black uppercase tracking-widest"
                            >
                              {WEEKDAY_LABELS[d]}
                            </span>
                          ))}
                        </div>
                      )}
                    </td>
                    <td className="px-6 py-3">
                      <Badge
                        variant={it.is_active ? 'success' : 'neutral'}
                        className="text-[8px] uppercase"
                      >
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
        <DialogContent className="max-w-xl p-0 overflow-hidden">
          <div className="bg-blue-600 px-6 py-5 text-white">
            <DialogTitle className="text-lg font-black uppercase tracking-tight flex items-center gap-2">
              <Clock size={18} />
              {editing ? 'Edit Shift Template' : 'New Shift Template'}
            </DialogTitle>
          </div>
          <div className="p-6 space-y-5 max-h-[70vh] overflow-y-auto">
            <div>
              <label className="text-[10px] font-black uppercase tracking-widest text-[#0F172A]">
                Name
              </label>
              <Input
                value={form.name}
                onChange={(e: any) =>
                  setForm({ ...form, name: e.target.value })
                }
                placeholder="e.g. Night A, General, Rotational-1"
                maxLength={80}
                className="mt-1.5"
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="text-[10px] font-black uppercase tracking-widest text-[#0F172A]">
                  Start Time
                </label>
                <Input
                  type="time"
                  value={form.start_time}
                  onChange={(e: any) =>
                    setForm({ ...form, start_time: e.target.value })
                  }
                  className="mt-1.5"
                />
              </div>
              <div>
                <label className="text-[10px] font-black uppercase tracking-widest text-[#0F172A]">
                  End Time
                </label>
                <Input
                  type="time"
                  value={form.end_time}
                  onChange={(e: any) =>
                    setForm({ ...form, end_time: e.target.value })
                  }
                  className="mt-1.5"
                />
                {form.end_time !== '' &&
                  form.start_time !== '' &&
                  form.end_time <= form.start_time && (
                    <p className="text-[9px] font-bold text-indigo-600 mt-1 flex items-center gap-1">
                      <Moon size={10} />
                      Overnight shift (ends next day)
                    </p>
                  )}
              </div>
            </div>

            <div className="grid grid-cols-3 gap-3">
              <div>
                <label className="text-[10px] font-black uppercase tracking-widest text-[#0F172A]">
                  Break (min)
                </label>
                <Input
                  type="number"
                  min={0}
                  max={480}
                  value={form.break_minutes}
                  onChange={(e: any) =>
                    setForm({
                      ...form,
                      break_minutes: Number(e.target.value) || 0,
                    })
                  }
                  className="mt-1.5"
                />
              </div>
              <div>
                <label className="text-[10px] font-black uppercase tracking-widest text-[#0F172A]">
                  Grace In (min)
                </label>
                <Input
                  type="number"
                  min={0}
                  max={120}
                  value={form.grace_in_minutes}
                  onChange={(e: any) =>
                    setForm({
                      ...form,
                      grace_in_minutes: Number(e.target.value) || 0,
                    })
                  }
                  className="mt-1.5"
                />
              </div>
              <div>
                <label className="text-[10px] font-black uppercase tracking-widest text-[#0F172A]">
                  Grace Out (min)
                </label>
                <Input
                  type="number"
                  min={0}
                  max={120}
                  value={form.grace_out_minutes}
                  onChange={(e: any) =>
                    setForm({
                      ...form,
                      grace_out_minutes: Number(e.target.value) || 0,
                    })
                  }
                  className="mt-1.5"
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="text-[10px] font-black uppercase tracking-widest text-[#0F172A]">
                  Full Day Hours
                </label>
                <Input
                  type="number"
                  step={0.5}
                  min={0.5}
                  max={24}
                  value={form.full_day_hours}
                  onChange={(e: any) =>
                    setForm({
                      ...form,
                      full_day_hours: Number(e.target.value) || 0,
                    })
                  }
                  className="mt-1.5"
                />
              </div>
              <div>
                <label className="text-[10px] font-black uppercase tracking-widest text-[#0F172A]">
                  Half Day Hours
                </label>
                <Input
                  type="number"
                  step={0.5}
                  min={0.5}
                  max={24}
                  value={form.half_day_hours}
                  onChange={(e: any) =>
                    setForm({
                      ...form,
                      half_day_hours: Number(e.target.value) || 0,
                    })
                  }
                  className="mt-1.5"
                />
              </div>
            </div>

            <div>
              <label className="text-[10px] font-black uppercase tracking-widest text-[#0F172A]">
                Weekly Offs
              </label>
              <div className="flex gap-1.5 mt-2 flex-wrap">
                {WEEKDAY_LABELS.map((lbl, idx) => {
                  const on = form.weekly_offs.includes(idx);
                  return (
                    <button
                      key={lbl}
                      type="button"
                      onClick={() => toggleWeeklyOff(idx)}
                      className={cn(
                        'px-3 py-1.5 rounded-lg text-[10px] font-black uppercase tracking-widest border transition-colors',
                        on
                          ? 'bg-blue-600 text-white border-blue-600'
                          : 'bg-white text-slate-600 border-slate-200 hover:border-blue-300',
                      )}
                    >
                      {lbl}
                    </button>
                  );
                })}
              </div>
            </div>

            <label className="inline-flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-[#0F172A] cursor-pointer">
              <input
                type="checkbox"
                checked={form.is_active}
                onChange={(e) =>
                  setForm({ ...form, is_active: e.target.checked })
                }
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

      <Dialog
        open={!!deleteTarget}
        onOpenChange={() => setDeleteTarget(null)}
      >
        <DialogContent className="max-w-md p-0 overflow-hidden">
          <div className="bg-rose-600 px-6 py-5 text-white">
            <DialogTitle className="text-lg font-black uppercase tracking-tight">
              Delete Shift Template
            </DialogTitle>
          </div>
          <div className="p-6">
            <p className="text-sm text-slate-700">
              Delete <strong>{deleteTarget?.name}</strong>? Blocked if any
              assignment still references it — deactivate instead.
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
