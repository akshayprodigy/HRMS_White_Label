import React, { useEffect, useMemo, useState } from 'react';
import { Plus, Edit2, Power, RefreshCw, Trash2, Layers, Boxes } from 'lucide-react';
import { Card, Button, Badge, cn } from './ui-elements';
import { toast } from 'sonner';
import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';
import { Dialog, DialogContent, DialogTitle, DialogFooter } from './ui/dialog';
import { Input } from './ui/input';

const SLOTS = ['basic', 'conveyance', 'hra', 'other'] as const;
const CALC_METHODS = ['flat', 'percent_of_basic'] as const;

interface SalaryComponent {
  id: number;
  code: string;
  name: string;
  component_type: string;
  slot: string | null;
  default_calc_method: string;
  default_percent: number | null;
  is_taxable: boolean;
  display_order: number;
  is_active: boolean;
}

interface TemplateLine {
  id?: number;
  component_id: number;
  calc_method: string;
  value: number | null;
  percent: number | null;
  display_order: number;
}

interface SalaryTemplate {
  id: number;
  code: string;
  name: string;
  description: string | null;
  is_active: boolean;
  components: TemplateLine[];
}

const errMsg = (err: any, fallback: string): string => {
  const detail = err?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) return detail.map((d: any) => d?.msg || JSON.stringify(d)).join('; ');
  return err?.message || fallback;
};

const selectCls =
  'mt-1.5 w-full h-10 px-3 bg-white border border-slate-200 rounded-xl text-sm font-bold text-[#0F172A] focus:ring-2 focus:ring-blue-600/10 outline-none';

// ---------------- Components tab ----------------

const emptyComp = {
  code: '', name: '', component_type: 'earning', slot: '' as string,
  default_calc_method: 'flat', default_percent: '' as string, is_taxable: true, is_active: true,
};

const ComponentsTab: React.FC<{ onChanged: () => void }> = ({ onChanged }) => {
  const [items, setItems] = useState<SalaryComponent[]>([]);
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<SalaryComponent | null>(null);
  const [form, setForm] = useState(emptyComp);
  const [submitting, setSubmitting] = useState(false);

  const fetchItems = async () => {
    setLoading(true);
    try {
      const res = await client.get(ENDPOINTS.HR.SALARY_COMPONENTS, { params: { include_inactive: true } });
      setItems(res.data || []);
    } catch (e: any) {
      toast.error(errMsg(e, 'Failed to load components'));
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { fetchItems(); }, []);

  const openCreate = () => { setEditing(null); setForm(emptyComp); setModalOpen(true); };
  const openEdit = (it: SalaryComponent) => {
    setEditing(it);
    setForm({
      code: it.code, name: it.name, component_type: it.component_type,
      slot: it.slot || '', default_calc_method: it.default_calc_method,
      default_percent: it.default_percent == null ? '' : String(it.default_percent),
      is_taxable: it.is_taxable, is_active: it.is_active,
    });
    setModalOpen(true);
  };

  const submit = async () => {
    if (!form.code.trim() || !form.name.trim()) { toast.error('Code and Name are required'); return; }
    const payload: any = {
      name: form.name, component_type: form.component_type,
      slot: form.slot || null, default_calc_method: form.default_calc_method,
      default_percent: form.default_percent.trim() === '' ? null : Number(form.default_percent),
      is_taxable: form.is_taxable, is_active: form.is_active,
    };
    setSubmitting(true);
    try {
      if (editing) {
        await client.patch(ENDPOINTS.HR.SALARY_COMPONENT_DETAIL(editing.id), payload);
        toast.success('Component updated');
      } else {
        await client.post(ENDPOINTS.HR.SALARY_COMPONENTS, { ...payload, code: form.code });
        toast.success('Component created');
      }
      setModalOpen(false); fetchItems(); onChanged();
    } catch (e: any) {
      toast.error(errMsg(e, 'Save failed'));
    } finally { setSubmitting(false); }
  };

  const toggleActive = async (it: SalaryComponent) => {
    try {
      await client.patch(ENDPOINTS.HR.SALARY_COMPONENT_DETAIL(it.id), { is_active: !it.is_active });
      fetchItems(); onChanged();
    } catch (e: any) { toast.error(errMsg(e, 'Toggle failed')); }
  };

  return (
    <Card className="p-0 border-slate-200 overflow-hidden bg-white">
      <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between bg-slate-50/40">
        <h4 className="text-sm font-black text-[#0F172A] tracking-tight uppercase">
          Earning Components {!loading && <span className="ml-2 text-slate-400 font-bold text-[10px]">({items.length})</span>}
        </h4>
        <div className="flex items-center gap-2">
          <button type="button" onClick={fetchItems} className="p-2 text-slate-400 hover:text-blue-600" title="Refresh" aria-label="Refresh">
            <RefreshCw size={16} className={cn(loading && 'animate-spin')} />
          </button>
          <Button onClick={openCreate} className="h-9 bg-blue-600 hover:bg-blue-700 text-white font-black uppercase text-[10px] tracking-widest">
            <Plus size={14} className="mr-1.5" /> Add Component
          </Button>
        </div>
      </div>
      {loading ? (
        <div className="py-16 text-center text-[10px] font-black uppercase tracking-widest text-slate-400 animate-pulse">Loading…</div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left">
            <thead className="bg-white border-b border-slate-100">
              <tr>
                <th className="px-6 py-3 text-[9px] font-black text-slate-400 uppercase tracking-widest">Code</th>
                <th className="px-6 py-3 text-[9px] font-black text-slate-400 uppercase tracking-widest">Name</th>
                <th className="px-6 py-3 text-[9px] font-black text-slate-400 uppercase tracking-widest">Slot</th>
                <th className="px-6 py-3 text-[9px] font-black text-slate-400 uppercase tracking-widest">Default</th>
                <th className="px-6 py-3 text-[9px] font-black text-slate-400 uppercase tracking-widest">Status</th>
                <th className="px-6 py-3 text-right text-[9px] font-black text-slate-400 uppercase tracking-widest">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {items.map(it => (
                <tr key={it.id} className="hover:bg-slate-50/60">
                  <td className="px-6 py-3">
                    <span className="inline-flex items-center px-2.5 py-1 rounded-lg bg-blue-50 text-blue-700 text-[10px] font-black uppercase tracking-widest">{it.code}</span>
                  </td>
                  <td className="px-6 py-3 text-sm font-black text-[#0F172A]">{it.name}</td>
                  <td className="px-6 py-3 text-[11px] font-bold text-slate-500 uppercase">{it.slot || 'other (folded)'}</td>
                  <td className="px-6 py-3 text-[11px] font-bold text-slate-600">
                    {it.default_calc_method === 'percent_of_basic' ? `${it.default_percent ?? '—'}% of basic` : 'flat'}
                  </td>
                  <td className="px-6 py-3">
                    <Badge variant={it.is_active ? 'success' : 'neutral'} className="text-[8px] uppercase">{it.is_active ? 'Active' : 'Inactive'}</Badge>
                  </td>
                  <td className="px-6 py-3 text-right space-x-1">
                    <button type="button" onClick={() => openEdit(it)} className="inline-flex items-center px-2.5 py-1.5 rounded-lg text-[9px] font-black uppercase tracking-widest text-slate-600 hover:bg-slate-100">
                      <Edit2 size={11} className="mr-1" /> Edit
                    </button>
                    <button type="button" onClick={() => toggleActive(it)} className={cn('inline-flex items-center px-2.5 py-1.5 rounded-lg text-[9px] font-black uppercase tracking-widest', it.is_active ? 'text-amber-700 hover:bg-amber-50' : 'text-emerald-700 hover:bg-emerald-50')}>
                      <Power size={11} className="mr-1" /> {it.is_active ? 'Off' : 'On'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Dialog open={modalOpen} onOpenChange={setModalOpen}>
        <DialogContent className="max-w-md p-0 overflow-hidden">
          <div className="bg-blue-600 px-6 py-5 text-white">
            <DialogTitle className="text-lg font-black uppercase tracking-tight">{editing ? 'Edit Component' : 'New Component'}</DialogTitle>
          </div>
          <div className="p-6 space-y-4">
            <div>
              <label className="text-[10px] font-black uppercase tracking-widest text-[#0F172A]">Code</label>
              <Input value={form.code} onChange={(e: any) => setForm({ ...form, code: e.target.value.toLowerCase() })} placeholder="e.g. medical" maxLength={30} disabled={!!editing} className="mt-1.5" />
            </div>
            <div>
              <label className="text-[10px] font-black uppercase tracking-widest text-[#0F172A]">Name</label>
              <Input value={form.name} onChange={(e: any) => setForm({ ...form, name: e.target.value })} placeholder="e.g. Medical Allowance" maxLength={80} className="mt-1.5" />
            </div>
            <div>
              <label className="text-[10px] font-black uppercase tracking-widest text-[#0F172A]">Canonical Slot</label>
              <select value={form.slot} onChange={e => setForm({ ...form, slot: e.target.value })} className={selectCls}>
                <option value="">other (extra earning — folded into Other)</option>
                {SLOTS.map(s => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>
            <label className="inline-flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-[#0F172A] cursor-pointer">
              <input type="checkbox" checked={form.is_active} onChange={e => setForm({ ...form, is_active: e.target.checked })} className="w-3.5 h-3.5 accent-blue-600" />
              Active
            </label>
          </div>
          <DialogFooter className="px-6 py-4 bg-slate-50 border-t border-slate-100">
            <Button variant="ghost" onClick={() => setModalOpen(false)} className="text-[10px] font-black uppercase tracking-widest">Cancel</Button>
            <Button onClick={submit} isLoading={submitting} className="bg-blue-600 hover:bg-blue-700 text-white text-[10px] font-black uppercase tracking-widest">{editing ? 'Update' : 'Create'}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
};

// ---------------- Templates tab ----------------

const TemplatesTab: React.FC<{ components: SalaryComponent[] }> = ({ components }) => {
  const [items, setItems] = useState<SalaryTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<SalaryTemplate | null>(null);
  const [meta, setMeta] = useState({ code: '', name: '', description: '', is_active: true });
  const [lines, setLines] = useState<TemplateLine[]>([]);
  const [submitting, setSubmitting] = useState(false);

  const compById = useMemo(() => {
    const m: Record<number, SalaryComponent> = {};
    components.forEach(c => { m[c.id] = c; });
    return m;
  }, [components]);
  const activeComps = components.filter(c => c.is_active);

  const fetchItems = async () => {
    setLoading(true);
    try {
      const res = await client.get(ENDPOINTS.HR.SALARY_TEMPLATES, { params: { include_inactive: true } });
      setItems(res.data || []);
    } catch (e: any) {
      toast.error(errMsg(e, 'Failed to load templates'));
    } finally { setLoading(false); }
  };
  useEffect(() => { fetchItems(); }, []);

  const openCreate = () => {
    setEditing(null);
    setMeta({ code: '', name: '', description: '', is_active: true });
    setLines([]);
    setModalOpen(true);
  };
  const openEdit = (t: SalaryTemplate) => {
    setEditing(t);
    setMeta({ code: t.code, name: t.name, description: t.description || '', is_active: t.is_active });
    setLines((t.components || []).map(l => ({ ...l })));
    setModalOpen(true);
  };

  const addLine = () => {
    const firstComp = activeComps[0];
    setLines([...lines, {
      component_id: firstComp?.id ?? 0,
      calc_method: firstComp?.default_calc_method || 'percent_of_basic',
      value: null, percent: firstComp?.default_percent ?? 0, display_order: lines.length,
    }]);
  };
  const updateLine = (i: number, patch: Partial<TemplateLine>) => {
    setLines(lines.map((l, idx) => idx === i ? { ...l, ...patch } : l));
  };
  const removeLine = (i: number) => setLines(lines.filter((_, idx) => idx !== i));

  const buildLinesPayload = () => lines.map((l, i) => ({
    component_id: l.component_id,
    calc_method: l.calc_method,
    value: l.calc_method === 'flat' ? Number(l.value ?? 0) : null,
    percent: l.calc_method === 'percent_of_basic' ? Number(l.percent ?? 0) : null,
    display_order: i,
  }));

  const submit = async () => {
    if (!meta.code.trim() || !meta.name.trim()) { toast.error('Code and Name are required'); return; }
    for (const l of lines) {
      if (l.calc_method === 'percent_of_basic' && (l.percent == null || l.percent === ('' as any))) {
        toast.error('Each percent-of-basic line needs a percent'); return;
      }
    }
    setSubmitting(true);
    try {
      if (editing) {
        await client.patch(ENDPOINTS.HR.SALARY_TEMPLATE_DETAIL(editing.id), {
          name: meta.name, description: meta.description || null, is_active: meta.is_active,
        });
        await client.put(ENDPOINTS.HR.SALARY_TEMPLATE_COMPONENTS(editing.id), buildLinesPayload());
        toast.success('Template updated');
      } else {
        await client.post(ENDPOINTS.HR.SALARY_TEMPLATES, {
          code: meta.code, name: meta.name, description: meta.description || null,
          is_active: meta.is_active, components: buildLinesPayload(),
        });
        toast.success('Template created');
      }
      setModalOpen(false); fetchItems();
    } catch (e: any) {
      toast.error(errMsg(e, 'Save failed'));
    } finally { setSubmitting(false); }
  };

  const toggleActive = async (t: SalaryTemplate) => {
    try {
      await client.patch(ENDPOINTS.HR.SALARY_TEMPLATE_DETAIL(t.id), { is_active: !t.is_active });
      fetchItems();
    } catch (e: any) { toast.error(errMsg(e, 'Toggle failed')); }
  };

  return (
    <Card className="p-0 border-slate-200 overflow-hidden bg-white">
      <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between bg-slate-50/40">
        <h4 className="text-sm font-black text-[#0F172A] tracking-tight uppercase">
          Salary Templates {!loading && <span className="ml-2 text-slate-400 font-bold text-[10px]">({items.length})</span>}
        </h4>
        <div className="flex items-center gap-2">
          <button type="button" onClick={fetchItems} className="p-2 text-slate-400 hover:text-blue-600" title="Refresh" aria-label="Refresh">
            <RefreshCw size={16} className={cn(loading && 'animate-spin')} />
          </button>
          <Button onClick={openCreate} className="h-9 bg-blue-600 hover:bg-blue-700 text-white font-black uppercase text-[10px] tracking-widest">
            <Plus size={14} className="mr-1.5" /> Add Template
          </Button>
        </div>
      </div>
      {loading ? (
        <div className="py-16 text-center text-[10px] font-black uppercase tracking-widest text-slate-400 animate-pulse">Loading…</div>
      ) : items.length === 0 ? (
        <div className="py-16 text-center text-[10px] font-black uppercase tracking-widest text-slate-400">No templates yet — create one to assign on an employee</div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left">
            <thead className="bg-white border-b border-slate-100">
              <tr>
                <th className="px-6 py-3 text-[9px] font-black text-slate-400 uppercase tracking-widest">Code</th>
                <th className="px-6 py-3 text-[9px] font-black text-slate-400 uppercase tracking-widest">Name</th>
                <th className="px-6 py-3 text-[9px] font-black text-slate-400 uppercase tracking-widest">Components</th>
                <th className="px-6 py-3 text-[9px] font-black text-slate-400 uppercase tracking-widest">Status</th>
                <th className="px-6 py-3 text-right text-[9px] font-black text-slate-400 uppercase tracking-widest">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {items.map(t => (
                <tr key={t.id} className="hover:bg-slate-50/60">
                  <td className="px-6 py-3">
                    <span className="inline-flex items-center px-2.5 py-1 rounded-lg bg-blue-50 text-blue-700 text-[10px] font-black uppercase tracking-widest">{t.code}</span>
                  </td>
                  <td className="px-6 py-3 text-sm font-black text-[#0F172A]">{t.name}</td>
                  <td className="px-6 py-3 text-[11px] font-bold text-slate-600">
                    {(t.components || []).map(l => {
                      const c = compById[l.component_id];
                      const val = l.calc_method === 'percent_of_basic' ? `${l.percent}%` : `₹${l.value}`;
                      return c ? `${c.name} (${val})` : `#${l.component_id}`;
                    }).join(' · ') || '—'}
                  </td>
                  <td className="px-6 py-3">
                    <Badge variant={t.is_active ? 'success' : 'neutral'} className="text-[8px] uppercase">{t.is_active ? 'Active' : 'Inactive'}</Badge>
                  </td>
                  <td className="px-6 py-3 text-right space-x-1">
                    <button type="button" onClick={() => openEdit(t)} className="inline-flex items-center px-2.5 py-1.5 rounded-lg text-[9px] font-black uppercase tracking-widest text-slate-600 hover:bg-slate-100">
                      <Edit2 size={11} className="mr-1" /> Edit
                    </button>
                    <button type="button" onClick={() => toggleActive(t)} className={cn('inline-flex items-center px-2.5 py-1.5 rounded-lg text-[9px] font-black uppercase tracking-widest', t.is_active ? 'text-amber-700 hover:bg-amber-50' : 'text-emerald-700 hover:bg-emerald-50')}>
                      <Power size={11} className="mr-1" /> {t.is_active ? 'Off' : 'On'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Dialog open={modalOpen} onOpenChange={setModalOpen}>
        <DialogContent className="max-w-2xl p-0 overflow-hidden">
          <div className="bg-blue-600 px-6 py-5 text-white">
            <DialogTitle className="text-lg font-black uppercase tracking-tight">{editing ? 'Edit Template' : 'New Salary Template'}</DialogTitle>
          </div>
          <div className="p-6 space-y-4 max-h-[65vh] overflow-y-auto">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="text-[10px] font-black uppercase tracking-widest text-[#0F172A]">Code</label>
                <Input value={meta.code} onChange={(e: any) => setMeta({ ...meta, code: e.target.value.toLowerCase() })} placeholder="e.g. standard_staff" maxLength={30} disabled={!!editing} className="mt-1.5" />
              </div>
              <div>
                <label className="text-[10px] font-black uppercase tracking-widest text-[#0F172A]">Name</label>
                <Input value={meta.name} onChange={(e: any) => setMeta({ ...meta, name: e.target.value })} placeholder="e.g. Standard Staff" maxLength={80} className="mt-1.5" />
              </div>
            </div>
            <div>
              <label className="text-[10px] font-black uppercase tracking-widest text-[#0F172A]">Description</label>
              <Input value={meta.description} onChange={(e: any) => setMeta({ ...meta, description: e.target.value })} placeholder="Optional" maxLength={255} className="mt-1.5" />
            </div>

            <div className="pt-2">
              <div className="flex items-center justify-between mb-2">
                <label className="text-[10px] font-black uppercase tracking-widest text-[#0F172A]">Component Lines</label>
                <Button onClick={addLine} variant="ghost" className="h-8 border border-blue-200 bg-blue-50 text-blue-700 hover:bg-blue-100 font-black uppercase text-[9px] tracking-widest">
                  <Plus size={12} className="mr-1" /> Add Line
                </Button>
              </div>
              <p className="text-[9px] font-bold text-slate-400 mb-3">
                Basic uses the employee's own salary. Allowances are percent-of-basic or a flat amount. A line mirroring 30/50/20 reproduces the legacy structure.
              </p>
              {lines.length === 0 ? (
                <div className="text-[10px] font-black uppercase tracking-widest text-slate-400 py-4 text-center border border-dashed border-slate-200 rounded-xl">
                  No lines — the employee's basic will be the only earning
                </div>
              ) : (
                <div className="space-y-2">
                  {lines.map((l, i) => (
                    <div key={i} className="flex items-center gap-2 p-2 border border-slate-200 rounded-xl">
                      <select value={l.component_id} onChange={e => updateLine(i, { component_id: Number(e.target.value) })} className="h-9 px-2 bg-white border border-slate-200 rounded-lg text-xs font-bold text-[#0F172A] outline-none flex-1">
                        {activeComps.map(c => <option key={c.id} value={c.id}>{c.name} [{c.slot || 'other'}]</option>)}
                      </select>
                      <select value={l.calc_method} onChange={e => updateLine(i, { calc_method: e.target.value })} className="h-9 px-2 bg-white border border-slate-200 rounded-lg text-xs font-bold text-[#0F172A] outline-none w-40">
                        {CALC_METHODS.map(m => <option key={m} value={m}>{m === 'flat' ? 'Flat ₹' : '% of basic'}</option>)}
                      </select>
                      {l.calc_method === 'percent_of_basic' ? (
                        <input type="number" value={l.percent ?? ''} onChange={e => updateLine(i, { percent: e.target.value === '' ? null : Number(e.target.value) })} placeholder="%" className="h-9 px-2 w-24 bg-white border border-slate-200 rounded-lg text-xs font-bold text-[#0F172A] outline-none" />
                      ) : (
                        <input type="number" value={l.value ?? ''} onChange={e => updateLine(i, { value: e.target.value === '' ? null : Number(e.target.value) })} placeholder="₹" className="h-9 px-2 w-24 bg-white border border-slate-200 rounded-lg text-xs font-bold text-[#0F172A] outline-none" />
                      )}
                      <button type="button" onClick={() => removeLine(i)} className="p-2 text-rose-500 hover:bg-rose-50 rounded-lg" aria-label="Remove line">
                        <Trash2 size={14} />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <label className="inline-flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-[#0F172A] cursor-pointer">
              <input type="checkbox" checked={meta.is_active} onChange={e => setMeta({ ...meta, is_active: e.target.checked })} className="w-3.5 h-3.5 accent-blue-600" />
              Active
            </label>
          </div>
          <DialogFooter className="px-6 py-4 bg-slate-50 border-t border-slate-100">
            <Button variant="ghost" onClick={() => setModalOpen(false)} className="text-[10px] font-black uppercase tracking-widest">Cancel</Button>
            <Button onClick={submit} isLoading={submitting} className="bg-blue-600 hover:bg-blue-700 text-white text-[10px] font-black uppercase tracking-widest">{editing ? 'Update' : 'Create'}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
};

// ---------------- Wrapper ----------------

export const SalaryStructureAdmin: React.FC = () => {
  const [tab, setTab] = useState<'templates' | 'components'>('templates');
  const [components, setComponents] = useState<SalaryComponent[]>([]);

  const loadComponents = async () => {
    try {
      const res = await client.get(ENDPOINTS.HR.SALARY_COMPONENTS, { params: { include_inactive: true } });
      setComponents(res.data || []);
    } catch { /* toast handled in tab */ }
  };
  useEffect(() => { loadComponents(); }, []);

  return (
    <div className="p-8 space-y-6 max-w-[1400px] mx-auto animate-in fade-in duration-300">
      <div>
        <h2 className="text-3xl font-black text-[#0F172A] tracking-tighter uppercase">Salary Structure</h2>
        <p className="text-[#64748B] font-bold uppercase tracking-widest text-[10px] mt-1">
          Component Catalogue &amp; Reusable Templates · Assign On An Employee To Drive Payroll
        </p>
      </div>
      <div className="flex items-center gap-2">
        <button type="button" onClick={() => setTab('templates')} className={cn('inline-flex items-center gap-2 px-4 h-10 rounded-xl text-[10px] font-black uppercase tracking-widest', tab === 'templates' ? 'bg-blue-600 text-white' : 'bg-white border border-slate-200 text-slate-600 hover:border-blue-600')}>
          <Layers size={14} /> Templates
        </button>
        <button type="button" onClick={() => setTab('components')} className={cn('inline-flex items-center gap-2 px-4 h-10 rounded-xl text-[10px] font-black uppercase tracking-widest', tab === 'components' ? 'bg-blue-600 text-white' : 'bg-white border border-slate-200 text-slate-600 hover:border-blue-600')}>
          <Boxes size={14} /> Components
        </button>
      </div>
      {tab === 'templates' ? <TemplatesTab components={components} /> : <ComponentsTab onChanged={loadComponents} />}
    </div>
  );
};
