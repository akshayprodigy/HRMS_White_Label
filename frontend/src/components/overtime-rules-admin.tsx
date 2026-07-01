import React, { useEffect, useMemo, useState } from 'react';
import {
  Plus, Edit2, Power, Search, RefreshCw, Clock, Info,
} from 'lucide-react';
import { Card, Button, Badge, cn } from './ui-elements';
import { toast } from 'sonner';
import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';
import { Dialog, DialogContent, DialogTitle, DialogFooter } from './ui/dialog';
import { Input } from './ui/input';

interface OTRule {
  id: number;
  name: string;
  scope: 'org_default' | 'shift';
  shift_template_id: number | null;
  shift_template_name?: string | null;
  ot_basis: 'beyond_shift_hours' | 'beyond_threshold';
  daily_threshold_hours: number | null;
  ot_rate_multiplier: number;
  weekly_off_multiplier: number;
  holiday_multiplier: number;
  min_ot_minutes: number;
  daily_ot_cap_minutes: number;
  monthly_ot_cap_minutes: number | null;
  rounding_minutes: number;
  requires_approval: boolean;
  is_active: boolean;
}

interface ShiftTemplate { id: number; name: string }

const emptyForm = {
  name: '',
  scope: 'org_default' as 'org_default' | 'shift',
  shift_template_id: null as number | null,
  ot_basis: 'beyond_shift_hours' as 'beyond_shift_hours' | 'beyond_threshold',
  daily_threshold_hours: 9 as number | null,
  ot_rate_multiplier: 1.5,
  weekly_off_multiplier: 2.0,
  holiday_multiplier: 2.0,
  min_ot_minutes: 30,
  daily_ot_cap_minutes: 240,
  monthly_ot_cap_minutes: null as number | null,
  rounding_minutes: 30,
  requires_approval: true,
  is_active: true,
};

const errMsg = (err: any, fallback: string): string => {
  const detail = err?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail))
    return detail.map((d: any) => d?.msg || JSON.stringify(d)).join('; ');
  return err?.message || fallback;
};

export const OvertimeRulesAdmin: React.FC = () => {
  const [items, setItems] = useState<OTRule[]>([]);
  const [shifts, setShifts] = useState<ShiftTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [showInactive, setShowInactive] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<OTRule | null>(null);
  const [form, setForm] = useState(emptyForm);
  const [submitting, setSubmitting] = useState(false);
  const [meta, setMeta] = useState<{ hourly_rate_basis?: string } | null>(null);

  const fetchAll = async () => {
    setLoading(true);
    try {
      const [r, s, m] = await Promise.all([
        client.get(ENDPOINTS.OVERTIME.RULES, {
          params: showInactive ? { include_inactive: true } : {},
        }),
        client.get(ENDPOINTS.SHIFTS.TEMPLATES),
        client.get(ENDPOINTS.OVERTIME.META),
      ]);
      setItems(r.data || []);
      setShifts(s.data || []);
      setMeta(m.data);
    } catch (e: any) {
      toast.error(errMsg(e, 'Failed to load OT rules'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchAll(); /* eslint-disable-line */ }, [showInactive]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return items;
    return items.filter(r =>
      r.name.toLowerCase().includes(q)
      || (r.shift_template_name || '').toLowerCase().includes(q)
    );
  }, [items, search]);

  const openCreate = () => {
    setEditing(null); setForm(emptyForm); setModalOpen(true);
  };
  const openEdit = (r: OTRule) => {
    setEditing(r);
    setForm({
      name: r.name, scope: r.scope, shift_template_id: r.shift_template_id,
      ot_basis: r.ot_basis, daily_threshold_hours: r.daily_threshold_hours,
      ot_rate_multiplier: r.ot_rate_multiplier,
      weekly_off_multiplier: r.weekly_off_multiplier,
      holiday_multiplier: r.holiday_multiplier,
      min_ot_minutes: r.min_ot_minutes,
      daily_ot_cap_minutes: r.daily_ot_cap_minutes,
      monthly_ot_cap_minutes: r.monthly_ot_cap_minutes,
      rounding_minutes: r.rounding_minutes,
      requires_approval: r.requires_approval, is_active: r.is_active,
    });
    setModalOpen(true);
  };

  const submit = async () => {
    if (!form.name.trim()) { toast.error('Name required'); return; }
    if (form.scope === 'shift' && !form.shift_template_id) {
      toast.error('Pick a shift template'); return;
    }
    if (form.ot_basis === 'beyond_threshold' && !form.daily_threshold_hours) {
      toast.error('Daily threshold hours required when basis is beyond_threshold');
      return;
    }
    setSubmitting(true);
    try {
      const payload = {
        ...form,
        shift_template_id: form.scope === 'shift' ? form.shift_template_id : null,
        daily_threshold_hours:
          form.ot_basis === 'beyond_threshold' ? form.daily_threshold_hours : null,
      };
      if (editing) {
        await client.patch(ENDPOINTS.OVERTIME.RULE_DETAIL(editing.id), payload);
        toast.success('Updated');
      } else {
        await client.post(ENDPOINTS.OVERTIME.RULES, payload);
        toast.success('Created');
      }
      setModalOpen(false); fetchAll();
    } catch (e: any) {
      toast.error(errMsg(e, 'Save failed'));
    } finally { setSubmitting(false); }
  };

  const toggleActive = async (r: OTRule) => {
    try {
      if (r.is_active) {
        await client.delete(ENDPOINTS.OVERTIME.RULE_DETAIL(r.id));
        toast.success('Deactivated');
      } else {
        await client.patch(ENDPOINTS.OVERTIME.RULE_DETAIL(r.id), {
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
            <Clock className="w-6 h-6 text-blue-600" /> Overtime Rules
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Configure OT multipliers, caps, rounding and approval policy.
          </p>
        </div>
        <Button onClick={openCreate}>
          <Plus className="w-4 h-4 mr-2" /> New Rule
        </Button>
      </div>

      {meta?.hourly_rate_basis && (
        <Card className="p-3 flex items-start gap-2 bg-blue-50/50 border-blue-200">
          <Info className="w-4 h-4 text-blue-600 mt-0.5 flex-shrink-0" />
          <span className="text-xs text-slate-700">
            <span className="font-semibold">Hourly rate basis:</span>{' '}
            {meta.hourly_rate_basis}
          </span>
        </Card>
      )}

      <Card className="p-4">
        <div className="flex items-center gap-3 mb-4">
          <div className="relative flex-1 max-w-sm">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <Input
              placeholder="Search rules…"
              value={search} onChange={e => setSearch(e.target.value)}
              className="pl-9"
            />
          </div>
          <label className="text-xs text-slate-600 flex items-center gap-2">
            <input
              type="checkbox" checked={showInactive}
              onChange={e => setShowInactive(e.target.checked)}
            /> Show inactive
          </label>
          <Button variant="outline" onClick={fetchAll}>
            <RefreshCw className="w-4 h-4" />
          </Button>
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
                  <th className="p-3">Basis</th>
                  <th className="p-3">Multipliers</th>
                  <th className="p-3">Caps</th>
                  <th className="p-3">Approval</th>
                  <th className="p-3">Status</th>
                  <th className="p-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map(r => (
                  <tr key={r.id} className="border-b hover:bg-slate-50">
                    <td className="p-3 font-medium">{r.name}</td>
                    <td className="p-3">
                      {r.scope === 'org_default' ? 'Org default'
                        : <span>Shift: {r.shift_template_name || r.shift_template_id}</span>}
                    </td>
                    <td className="p-3">
                      {r.ot_basis === 'beyond_shift_hours'
                        ? 'Beyond shift hours'
                        : `Beyond ${r.daily_threshold_hours}h/day`}
                    </td>
                    <td className="p-3 text-xs">
                      Wd: {r.ot_rate_multiplier}× · Off: {r.weekly_off_multiplier}× · Hol: {r.holiday_multiplier}×
                    </td>
                    <td className="p-3 text-xs">
                      Daily {r.daily_ot_cap_minutes}m{r.monthly_ot_cap_minutes ? ` · Mo ${r.monthly_ot_cap_minutes}m` : ''} · ≥{r.min_ot_minutes}m · round {r.rounding_minutes}m
                    </td>
                    <td className="p-3">
                      <Badge variant={r.requires_approval ? 'info' : 'success'}>
                        {r.requires_approval ? 'Required' : 'Auto'}
                      </Badge>
                    </td>
                    <td className="p-3">
                      <Badge variant={r.is_active ? 'success' : 'error'}>
                        {r.is_active ? 'Active' : 'Inactive'}
                      </Badge>
                    </td>
                    <td className="p-3 text-right space-x-2">
                      <Button size="sm" variant="outline"
                        onClick={() => openEdit(r)}>
                        <Edit2 className="w-3 h-3" />
                      </Button>
                      <Button size="sm" variant="outline"
                        onClick={() => toggleActive(r)}>
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
        <DialogContent className="max-w-2xl">
          <DialogTitle>{editing ? 'Edit' : 'New'} Overtime Rule</DialogTitle>
          <div className="space-y-4 mt-4 max-h-[60vh] overflow-y-auto pr-1">
            <div className="grid grid-cols-2 gap-3">
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
                <label className="text-xs font-semibold text-slate-600">OT basis</label>
                <select value={form.ot_basis}
                  onChange={e => setForm({ ...form, ot_basis: e.target.value as any })}
                  className="w-full border border-slate-200 rounded-md h-9 px-2 text-sm">
                  <option value="beyond_shift_hours">Beyond shift hours</option>
                  <option value="beyond_threshold">Beyond daily threshold</option>
                </select>
              </div>
              <div>
                <label className="text-xs font-semibold text-slate-600">Daily threshold (hrs)</label>
                <Input type="number" min={0} step={0.5}
                  disabled={form.ot_basis !== 'beyond_threshold'}
                  value={form.daily_threshold_hours ?? ''}
                  onChange={e => setForm({ ...form, daily_threshold_hours: e.target.value ? Number(e.target.value) : null })} />
              </div>
              <div>
                <label className="text-xs font-semibold text-slate-600">Weekday multiplier</label>
                <Input type="number" min={0.1} step={0.1} value={form.ot_rate_multiplier}
                  onChange={e => setForm({ ...form, ot_rate_multiplier: Number(e.target.value) })} />
              </div>
              <div>
                <label className="text-xs font-semibold text-slate-600">Weekly-off multiplier</label>
                <Input type="number" min={0.1} step={0.1} value={form.weekly_off_multiplier}
                  onChange={e => setForm({ ...form, weekly_off_multiplier: Number(e.target.value) })} />
              </div>
              <div>
                <label className="text-xs font-semibold text-slate-600">Holiday multiplier</label>
                <Input type="number" min={0.1} step={0.1} value={form.holiday_multiplier}
                  onChange={e => setForm({ ...form, holiday_multiplier: Number(e.target.value) })} />
              </div>
              <div>
                <label className="text-xs font-semibold text-slate-600">Rounding (min)</label>
                <Input type="number" min={1} step={1} value={form.rounding_minutes}
                  onChange={e => setForm({ ...form, rounding_minutes: Number(e.target.value) })} />
              </div>
              <div>
                <label className="text-xs font-semibold text-slate-600">Min OT (min)</label>
                <Input type="number" min={0} step={1} value={form.min_ot_minutes}
                  onChange={e => setForm({ ...form, min_ot_minutes: Number(e.target.value) })} />
              </div>
              <div>
                <label className="text-xs font-semibold text-slate-600">Daily cap (min)</label>
                <Input type="number" min={0} step={1} value={form.daily_ot_cap_minutes}
                  onChange={e => setForm({ ...form, daily_ot_cap_minutes: Number(e.target.value) })} />
              </div>
              <div>
                <label className="text-xs font-semibold text-slate-600">Monthly cap (min, blank = none)</label>
                <Input type="number" min={0} step={1} value={form.monthly_ot_cap_minutes ?? ''}
                  onChange={e => setForm({ ...form, monthly_ot_cap_minutes: e.target.value ? Number(e.target.value) : null })} />
              </div>
              <div className="col-span-2 flex items-center gap-6 mt-2">
                <label className="text-sm flex items-center gap-2">
                  <input type="checkbox" checked={form.requires_approval}
                    onChange={e => setForm({ ...form, requires_approval: e.target.checked })} />
                  Requires manager approval
                </label>
                <label className="text-sm flex items-center gap-2">
                  <input type="checkbox" checked={form.is_active}
                    onChange={e => setForm({ ...form, is_active: e.target.checked })} />
                  Active
                </label>
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setModalOpen(false)}>Cancel</Button>
            <Button isLoading={submitting} onClick={submit}>
              {editing ? 'Save' : 'Create'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};
