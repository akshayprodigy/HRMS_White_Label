import React, { useEffect, useMemo, useState } from 'react';
import { Plus, Edit2, Power, Search, RefreshCw, Moon } from 'lucide-react';
import { Card, Button, Badge, cn } from './ui-elements';
import { toast } from 'sonner@2.0.3';
import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';
import { Dialog, DialogContent, DialogTitle, DialogFooter } from './ui/dialog';
import { Input } from './ui/input';

interface NightRule {
  id: number;
  name: string;
  scope: 'org_default' | 'shift';
  shift_template_id: number | null;
  shift_template_name?: string | null;
  payout_model: 'flat' | 'hourly';
  flat_amount: number;
  hourly_rate: number;
  night_window_start: string;
  night_window_end: string;
  min_night_minutes: number;
  is_active: boolean;
}

interface ShiftTemplate { id: number; name: string }

const emptyForm = {
  name: '',
  scope: 'org_default' as 'org_default' | 'shift',
  shift_template_id: null as number | null,
  payout_model: 'flat' as 'flat' | 'hourly',
  flat_amount: 200,
  hourly_rate: 80,
  night_window_start: '22:00',
  night_window_end: '06:00',
  min_night_minutes: 60,
  is_active: true,
};

const errMsg = (err: any, fallback: string): string => {
  const detail = err?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail))
    return detail.map((d: any) => d?.msg || JSON.stringify(d)).join('; ');
  return err?.message || fallback;
};

const toHHMMSS = (s: string) => s.length === 5 ? `${s}:00` : s;
const fromHHMMSS = (s: string) => s ? s.slice(0, 5) : '';

export const NightAllowanceRulesAdmin: React.FC = () => {
  const [items, setItems] = useState<NightRule[]>([]);
  const [shifts, setShifts] = useState<ShiftTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [showInactive, setShowInactive] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<NightRule | null>(null);
  const [form, setForm] = useState(emptyForm);
  const [submitting, setSubmitting] = useState(false);

  const fetchAll = async () => {
    setLoading(true);
    try {
      const [r, s] = await Promise.all([
        client.get(ENDPOINTS.OVERTIME.NIGHT_RULES, {
          params: showInactive ? { include_inactive: true } : {},
        }),
        client.get(ENDPOINTS.SHIFTS.TEMPLATES),
      ]);
      setItems(r.data || []); setShifts(s.data || []);
    } catch (e: any) {
      toast.error(errMsg(e, 'Failed to load night rules'));
    } finally { setLoading(false); }
  };

  useEffect(() => { fetchAll(); /* eslint-disable-line */ }, [showInactive]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return items;
    return items.filter(r => r.name.toLowerCase().includes(q));
  }, [items, search]);

  const openCreate = () => { setEditing(null); setForm(emptyForm); setModalOpen(true); };
  const openEdit = (r: NightRule) => {
    setEditing(r);
    setForm({
      name: r.name, scope: r.scope, shift_template_id: r.shift_template_id,
      payout_model: r.payout_model, flat_amount: r.flat_amount,
      hourly_rate: r.hourly_rate,
      night_window_start: fromHHMMSS(r.night_window_start),
      night_window_end: fromHHMMSS(r.night_window_end),
      min_night_minutes: r.min_night_minutes, is_active: r.is_active,
    });
    setModalOpen(true);
  };

  const submit = async () => {
    if (!form.name.trim()) { toast.error('Name required'); return; }
    if (form.scope === 'shift' && !form.shift_template_id) {
      toast.error('Pick a shift template'); return;
    }
    setSubmitting(true);
    try {
      const payload = {
        ...form,
        shift_template_id: form.scope === 'shift' ? form.shift_template_id : null,
        night_window_start: toHHMMSS(form.night_window_start),
        night_window_end: toHHMMSS(form.night_window_end),
      };
      if (editing) {
        await client.patch(ENDPOINTS.OVERTIME.NIGHT_RULE_DETAIL(editing.id), payload);
        toast.success('Updated');
      } else {
        await client.post(ENDPOINTS.OVERTIME.NIGHT_RULES, payload);
        toast.success('Created');
      }
      setModalOpen(false); fetchAll();
    } catch (e: any) {
      toast.error(errMsg(e, 'Save failed'));
    } finally { setSubmitting(false); }
  };

  const toggleActive = async (r: NightRule) => {
    try {
      if (r.is_active) {
        await client.delete(ENDPOINTS.OVERTIME.NIGHT_RULE_DETAIL(r.id));
        toast.success('Deactivated');
      } else {
        await client.patch(ENDPOINTS.OVERTIME.NIGHT_RULE_DETAIL(r.id), {
          is_active: true,
        });
        toast.success('Reactivated');
      }
      fetchAll();
    } catch (e: any) { toast.error(errMsg(e, 'Toggle failed')); }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Moon className="w-6 h-6 text-indigo-600" /> Night-shift Allowance
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Configure flat or hourly payouts for work in the night window.
          </p>
        </div>
        <Button onClick={openCreate}><Plus className="w-4 h-4 mr-2" /> New Rule</Button>
      </div>

      <Card className="p-4">
        <div className="flex items-center gap-3 mb-4">
          <div className="relative flex-1 max-w-sm">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <Input placeholder="Search…" value={search}
              onChange={e => setSearch(e.target.value)} className="pl-9" />
          </div>
          <label className="text-xs text-slate-600 flex items-center gap-2">
            <input type="checkbox" checked={showInactive}
              onChange={e => setShowInactive(e.target.checked)} />
            Show inactive
          </label>
          <Button variant="outline" onClick={fetchAll}><RefreshCw className="w-4 h-4" /></Button>
        </div>

        {loading ? (
          <div className="py-8 text-center text-slate-500">Loading…</div>
        ) : filtered.length === 0 ? (
          <div className="py-12 text-center text-slate-500">No rules.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead className="text-left text-xs uppercase text-slate-500 border-b">
                <tr>
                  <th className="p-3">Name</th>
                  <th className="p-3">Scope</th>
                  <th className="p-3">Payout</th>
                  <th className="p-3">Window</th>
                  <th className="p-3">Min</th>
                  <th className="p-3">Status</th>
                  <th className="p-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map(r => (
                  <tr key={r.id} className="border-b hover:bg-slate-50">
                    <td className="p-3 font-medium">{r.name}</td>
                    <td className="p-3">
                      {r.scope === 'org_default' ? 'Org' : `Shift: ${r.shift_template_name || r.shift_template_id}`}
                    </td>
                    <td className="p-3">
                      {r.payout_model === 'flat'
                        ? <span>Flat ₹{r.flat_amount}</span>
                        : <span>₹{r.hourly_rate}/hr</span>}
                    </td>
                    <td className="p-3 text-xs">
                      {fromHHMMSS(r.night_window_start)} → {fromHHMMSS(r.night_window_end)}
                    </td>
                    <td className="p-3 text-xs">{r.min_night_minutes}m</td>
                    <td className="p-3">
                      <Badge variant={r.is_active ? 'success' : 'error'}>
                        {r.is_active ? 'Active' : 'Inactive'}
                      </Badge>
                    </td>
                    <td className="p-3 text-right space-x-2">
                      <Button size="sm" variant="outline" onClick={() => openEdit(r)}>
                        <Edit2 className="w-3 h-3" />
                      </Button>
                      <Button size="sm" variant="outline" onClick={() => toggleActive(r)}>
                        <Power className={cn('w-3 h-3',
                          r.is_active ? 'text-red-600' : 'text-green-600')} />
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Dialog open={modalOpen} onOpenChange={setModalOpen}>
        <DialogContent className="max-w-xl">
          <DialogTitle>{editing ? 'Edit' : 'New'} Night-shift Allowance Rule</DialogTitle>
          <div className="space-y-3 mt-4 grid grid-cols-2 gap-3 max-h-[60vh] overflow-y-auto pr-1">
            <div className="col-span-2">
              <label className="text-xs font-semibold text-slate-600">Name</label>
              <Input value={form.name}
                onChange={e => setForm({ ...form, name: e.target.value })} />
            </div>
            <div>
              <label className="text-xs font-semibold text-slate-600">Scope</label>
              <select value={form.scope}
                onChange={e => setForm({ ...form, scope: e.target.value as any })}
                className="w-full border border-slate-200 rounded-md h-9 px-2 text-sm">
                <option value="org_default">Org default</option>
                <option value="shift">Per shift</option>
              </select>
            </div>
            <div>
              <label className="text-xs font-semibold text-slate-600">Shift template</label>
              <select value={form.shift_template_id ?? ''}
                disabled={form.scope !== 'shift'}
                onChange={e => setForm({ ...form, shift_template_id: Number(e.target.value) || null })}
                className="w-full border border-slate-200 rounded-md h-9 px-2 text-sm disabled:bg-slate-50">
                <option value="">—</option>
                {shifts.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
            </div>
            <div>
              <label className="text-xs font-semibold text-slate-600">Payout model</label>
              <select value={form.payout_model}
                onChange={e => setForm({ ...form, payout_model: e.target.value as any })}
                className="w-full border border-slate-200 rounded-md h-9 px-2 text-sm">
                <option value="flat">Flat per night</option>
                <option value="hourly">Per hour in window</option>
              </select>
            </div>
            <div>
              <label className="text-xs font-semibold text-slate-600">
                {form.payout_model === 'flat' ? 'Flat amount (₹)' : 'Hourly rate (₹)'}
              </label>
              <Input type="number" min={0} step={1}
                value={form.payout_model === 'flat' ? form.flat_amount : form.hourly_rate}
                onChange={e => setForm({
                  ...form,
                  [form.payout_model === 'flat' ? 'flat_amount' : 'hourly_rate']: Number(e.target.value),
                } as any)} />
            </div>
            <div>
              <label className="text-xs font-semibold text-slate-600">Window start</label>
              <Input type="time" value={form.night_window_start}
                onChange={e => setForm({ ...form, night_window_start: e.target.value })} />
            </div>
            <div>
              <label className="text-xs font-semibold text-slate-600">Window end</label>
              <Input type="time" value={form.night_window_end}
                onChange={e => setForm({ ...form, night_window_end: e.target.value })} />
            </div>
            <div>
              <label className="text-xs font-semibold text-slate-600">Min night minutes</label>
              <Input type="number" min={0} step={5} value={form.min_night_minutes}
                onChange={e => setForm({ ...form, min_night_minutes: Number(e.target.value) })} />
            </div>
            <div className="col-span-2">
              <label className="text-sm flex items-center gap-2">
                <input type="checkbox" checked={form.is_active}
                  onChange={e => setForm({ ...form, is_active: e.target.checked })} />
                Active
              </label>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setModalOpen(false)}>Cancel</Button>
            <Button isLoading={submitting} onClick={submit}>{editing ? 'Save' : 'Create'}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};
