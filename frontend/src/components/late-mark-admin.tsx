import React, { useEffect, useMemo, useState } from 'react';
import { Plus, Edit2, Power, RefreshCw, Clock, PlayCircle, AlarmClock, ListChecks } from 'lucide-react';
import { Card, Button, Badge, cn } from './ui-elements';
import { toast } from 'sonner';
import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';
import { Dialog, DialogContent, DialogTitle, DialogFooter } from './ui/dialog';
import { Input } from './ui/input';

interface Rule {
  id: number;
  name: string;
  scope: string;
  shift_template_id: number | null;
  grace_minutes: number;
  lates_per_deduction: number;
  deduction_days_per_block: number;
  first_leave_type_id: number | null;
  second_leave_type_id: number | null;
  is_active: boolean;
}

interface Deduction {
  id: number;
  user_id: number;
  full_name: string | null;
  year: number;
  month: number;
  late_count: number;
  deducted_days: number;
  cl_days: number;
  pl_days: number;
  lop_days: number;
  payroll_run_id: number | null;
}

const MONTHS = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const selectCls = 'mt-1.5 w-full h-11 px-3 bg-slate-50 border border-slate-200 rounded-xl text-sm font-bold text-[#0F172A] outline-none';
const errMsg = (e: any, f: string) => {
  const d = e?.response?.data?.detail;
  if (typeof d === 'string') return d;
  if (Array.isArray(d)) return d.map((x: any) => x?.msg || JSON.stringify(x)).join('; ');
  return e?.message || f;
};

const emptyRule = {
  name: '', scope: 'org_default', shift_template_id: '' as any,
  grace_minutes: 10, lates_per_deduction: 3, deduction_days_per_block: 1,
  first_leave_type_id: '' as any, second_leave_type_id: '' as any, is_active: true,
};

export const LateMarkAdmin: React.FC = () => {
  const [tab, setTab] = useState<'rules' | 'process'>('rules');
  const [rules, setRules] = useState<Rule[]>([]);
  const [leaveTypes, setLeaveTypes] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<Rule | null>(null);
  const [form, setForm] = useState<any>(emptyRule);
  const [submitting, setSubmitting] = useState(false);

  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [deductions, setDeductions] = useState<Deduction[]>([]);
  const [processing, setProcessing] = useState(false);

  const ltById = useMemo(() => {
    const m: Record<number, string> = {};
    leaveTypes.forEach(l => { m[l.id] = l.name; });
    return m;
  }, [leaveTypes]);

  const fetchRules = async () => {
    setLoading(true);
    try {
      const [r, lt] = await Promise.all([
        client.get(ENDPOINTS.HR.LATE_MARK_RULES),
        client.get(ENDPOINTS.ADMIN.LEAVE_TYPES).catch(() => ({ data: [] })),
      ]);
      setRules(r.data || []);
      setLeaveTypes(lt.data || []);
    } catch (e: any) {
      toast.error(errMsg(e, 'Failed to load rules'));
    } finally { setLoading(false); }
  };
  useEffect(() => { fetchRules(); }, []);

  const openCreate = () => { setEditing(null); setForm(emptyRule); setModalOpen(true); };
  const openEdit = (r: Rule) => {
    setEditing(r);
    setForm({
      name: r.name, scope: r.scope, shift_template_id: r.shift_template_id ?? '',
      grace_minutes: r.grace_minutes, lates_per_deduction: r.lates_per_deduction,
      deduction_days_per_block: r.deduction_days_per_block,
      first_leave_type_id: r.first_leave_type_id ?? '', second_leave_type_id: r.second_leave_type_id ?? '',
      is_active: r.is_active,
    });
    setModalOpen(true);
  };

  const submit = async () => {
    if (!form.name.trim()) { toast.error('Name is required'); return; }
    const payload: any = {
      name: form.name, scope: form.scope,
      shift_template_id: form.scope === 'shift' && form.shift_template_id ? Number(form.shift_template_id) : null,
      grace_minutes: Number(form.grace_minutes), lates_per_deduction: Number(form.lates_per_deduction),
      deduction_days_per_block: Number(form.deduction_days_per_block),
      first_leave_type_id: form.first_leave_type_id ? Number(form.first_leave_type_id) : null,
      second_leave_type_id: form.second_leave_type_id ? Number(form.second_leave_type_id) : null,
      is_active: form.is_active,
    };
    setSubmitting(true);
    try {
      if (editing) await client.patch(ENDPOINTS.HR.LATE_MARK_RULE_DETAIL(editing.id), payload);
      else await client.post(ENDPOINTS.HR.LATE_MARK_RULES, payload);
      toast.success(editing ? 'Rule updated' : 'Rule created');
      setModalOpen(false); fetchRules();
    } catch (e: any) { toast.error(errMsg(e, 'Save failed')); }
    finally { setSubmitting(false); }
  };

  const toggleActive = async (r: Rule) => {
    try { await client.patch(ENDPOINTS.HR.LATE_MARK_RULE_DETAIL(r.id), { is_active: !r.is_active }); fetchRules(); }
    catch (e: any) { toast.error(errMsg(e, 'Toggle failed')); }
  };

  const fetchDeductions = async () => {
    try {
      const res = await client.get(ENDPOINTS.HR.LATE_MARK_DEDUCTIONS, { params: { year, month } });
      setDeductions(res.data || []);
    } catch (e: any) { toast.error(errMsg(e, 'Failed to load deductions')); }
  };
  useEffect(() => { if (tab === 'process') fetchDeductions(); /* eslint-disable-next-line */ }, [tab, year, month]);

  const runProcess = async () => {
    setProcessing(true);
    try {
      const res = await client.post(`${ENDPOINTS.HR.LATE_MARK_PROCESS}?year=${year}&month=${month}`);
      const d = res.data || {};
      if (d.note) toast.warning(d.note);
      else toast.success(`Processed ${d.processed} employee(s), ${d.skipped_locked} locked`);
      fetchDeductions();
    } catch (e: any) { toast.error(errMsg(e, 'Process failed')); }
    finally { setProcessing(false); }
  };

  return (
    <div className="p-8 space-y-6 max-w-[1400px] mx-auto animate-in fade-in duration-300">
      <div>
        <h2 className="text-3xl font-black text-[#0F172A] tracking-tighter uppercase">Late-Mark Rules</h2>
        <p className="text-[#64748B] font-bold uppercase tracking-widest text-[10px] mt-1">
          Grace → N Lates → Deduct Leave (Cascade → LOP) · Directly Affects Payroll
        </p>
      </div>
      <div className="flex items-center gap-2">
        <button type="button" onClick={() => setTab('rules')} className={cn('inline-flex items-center gap-2 px-4 h-10 rounded-xl text-[10px] font-black uppercase tracking-widest', tab === 'rules' ? 'bg-blue-600 text-white' : 'bg-white border border-slate-200 text-slate-600 hover:border-blue-600')}>
          <AlarmClock size={14} /> Rules
        </button>
        <button type="button" onClick={() => setTab('process')} className={cn('inline-flex items-center gap-2 px-4 h-10 rounded-xl text-[10px] font-black uppercase tracking-widest', tab === 'process' ? 'bg-blue-600 text-white' : 'bg-white border border-slate-200 text-slate-600 hover:border-blue-600')}>
          <ListChecks size={14} /> Process & Deductions
        </button>
      </div>

      {tab === 'rules' ? (
        <Card className="p-0 border-slate-200 overflow-hidden bg-white">
          <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between bg-slate-50/40">
            <h4 className="text-sm font-black text-[#0F172A] tracking-tight uppercase">Rules {!loading && <span className="text-slate-400 font-bold text-[10px]">({rules.length})</span>}</h4>
            <div className="flex items-center gap-2">
              <button type="button" onClick={fetchRules} className="p-2 text-slate-400 hover:text-blue-600" title="Refresh" aria-label="Refresh"><RefreshCw size={16} className={cn(loading && 'animate-spin')} /></button>
              <Button onClick={openCreate} className="h-9 bg-blue-600 hover:bg-blue-700 text-white font-black uppercase text-[10px] tracking-widest"><Plus size={14} className="mr-1.5" /> Add Rule</Button>
            </div>
          </div>
          {loading ? <div className="py-16 text-center text-[10px] font-black uppercase tracking-widest text-slate-400 animate-pulse">Loading…</div>
            : rules.length === 0 ? <div className="py-16 text-center text-[10px] font-black uppercase tracking-widest text-slate-400">No rules — add an org-default rule to enable late-mark processing</div>
            : (
            <div className="overflow-x-auto">
              <table className="w-full text-left">
                <thead className="bg-white border-b border-slate-100"><tr>
                  <th className="px-6 py-3 text-[9px] font-black text-slate-400 uppercase tracking-widest">Name</th>
                  <th className="px-6 py-3 text-[9px] font-black text-slate-400 uppercase tracking-widest">Scope</th>
                  <th className="px-6 py-3 text-[9px] font-black text-slate-400 uppercase tracking-widest">Grace</th>
                  <th className="px-6 py-3 text-[9px] font-black text-slate-400 uppercase tracking-widest">Rule</th>
                  <th className="px-6 py-3 text-[9px] font-black text-slate-400 uppercase tracking-widest">Cascade</th>
                  <th className="px-6 py-3 text-[9px] font-black text-slate-400 uppercase tracking-widest">Status</th>
                  <th className="px-6 py-3 text-right text-[9px] font-black text-slate-400 uppercase tracking-widest">Actions</th>
                </tr></thead>
                <tbody className="divide-y divide-slate-50">
                  {rules.map(r => (
                    <tr key={r.id} className="hover:bg-slate-50/60">
                      <td className="px-6 py-3 text-sm font-black text-[#0F172A]">{r.name}</td>
                      <td className="px-6 py-3 text-[11px] font-bold text-slate-500 uppercase">{r.scope}</td>
                      <td className="px-6 py-3 text-[11px] font-bold text-slate-600"><Clock size={11} className="inline mr-1" />{r.grace_minutes}m</td>
                      <td className="px-6 py-3 text-[11px] font-bold text-slate-600">{r.lates_per_deduction} lates → {r.deduction_days_per_block}d</td>
                      <td className="px-6 py-3 text-[11px] font-bold text-slate-600">
                        {(r.first_leave_type_id ? ltById[r.first_leave_type_id] : 'LOP')} → {(r.second_leave_type_id ? ltById[r.second_leave_type_id] : 'LOP')} → LOP
                      </td>
                      <td className="px-6 py-3"><Badge variant={r.is_active ? 'success' : 'neutral'} className="text-[8px] uppercase">{r.is_active ? 'Active' : 'Inactive'}</Badge></td>
                      <td className="px-6 py-3 text-right space-x-1">
                        <button type="button" onClick={() => openEdit(r)} className="inline-flex items-center px-2.5 py-1.5 rounded-lg text-[9px] font-black uppercase tracking-widest text-slate-600 hover:bg-slate-100"><Edit2 size={11} className="mr-1" /> Edit</button>
                        <button type="button" onClick={() => toggleActive(r)} className={cn('inline-flex items-center px-2.5 py-1.5 rounded-lg text-[9px] font-black uppercase tracking-widest', r.is_active ? 'text-amber-700 hover:bg-amber-50' : 'text-emerald-700 hover:bg-emerald-50')}><Power size={11} className="mr-1" /> {r.is_active ? 'Off' : 'On'}</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      ) : (
        <Card className="p-0 border-slate-200 overflow-hidden bg-white">
          <div className="px-6 py-4 border-b border-slate-100 flex items-center gap-3 bg-slate-50/40 flex-wrap">
            <select value={month} onChange={e => setMonth(Number(e.target.value))} className="h-9 px-3 bg-white border border-slate-200 rounded-lg text-xs font-bold outline-none">
              {MONTHS.slice(1).map((m, i) => <option key={i + 1} value={i + 1}>{m}</option>)}
            </select>
            <input type="number" value={year} onChange={e => setYear(Number(e.target.value))} className="h-9 px-3 w-24 bg-white border border-slate-200 rounded-lg text-xs font-bold outline-none" />
            <Button onClick={runProcess} isLoading={processing} className="h-9 bg-emerald-600 hover:bg-emerald-700 text-white font-black uppercase text-[10px] tracking-widest"><PlayCircle size={14} className="mr-1.5" /> Process Month</Button>
            <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Idempotent — recomputes &amp; reverses unpaid prior runs</span>
          </div>
          {deductions.length === 0 ? <div className="py-16 text-center text-[10px] font-black uppercase tracking-widest text-slate-400">No deductions for {MONTHS[month]} {year} — process the month</div> : (
            <div className="overflow-x-auto">
              <table className="w-full text-left">
                <thead className="bg-white border-b border-slate-100"><tr>
                  <th className="px-6 py-3 text-[9px] font-black text-slate-400 uppercase tracking-widest">Employee</th>
                  <th className="px-6 py-3 text-[9px] font-black text-slate-400 uppercase tracking-widest">Late Marks</th>
                  <th className="px-6 py-3 text-[9px] font-black text-slate-400 uppercase tracking-widest">Deducted</th>
                  <th className="px-6 py-3 text-[9px] font-black text-slate-400 uppercase tracking-widest">Tier 1</th>
                  <th className="px-6 py-3 text-[9px] font-black text-slate-400 uppercase tracking-widest">Tier 2</th>
                  <th className="px-6 py-3 text-[9px] font-black text-slate-400 uppercase tracking-widest">LOP</th>
                  <th className="px-6 py-3 text-[9px] font-black text-slate-400 uppercase tracking-widest">Paid?</th>
                </tr></thead>
                <tbody className="divide-y divide-slate-50">
                  {deductions.map(d => (
                    <tr key={d.id} className="hover:bg-slate-50/60">
                      <td className="px-6 py-3 text-sm font-black text-[#0F172A]">{d.full_name || `User #${d.user_id}`}</td>
                      <td className="px-6 py-3 text-sm font-bold tabular-nums">{d.late_count}</td>
                      <td className="px-6 py-3 text-sm font-black tabular-nums">{d.deducted_days}</td>
                      <td className="px-6 py-3 text-sm font-bold text-blue-700 tabular-nums">{d.cl_days}</td>
                      <td className="px-6 py-3 text-sm font-bold text-indigo-700 tabular-nums">{d.pl_days}</td>
                      <td className="px-6 py-3 text-sm font-black text-rose-600 tabular-nums">{d.lop_days}</td>
                      <td className="px-6 py-3"><Badge variant={d.payroll_run_id ? 'success' : 'neutral'} className="text-[8px] uppercase">{d.payroll_run_id ? 'Paid' : 'Pending'}</Badge></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}

      <Dialog open={modalOpen} onOpenChange={setModalOpen}>
        <DialogContent className="max-w-lg p-0 overflow-hidden">
          <div className="bg-blue-600 px-6 py-5 text-white"><DialogTitle className="text-lg font-black uppercase tracking-tight">{editing ? 'Edit Rule' : 'New Late-Mark Rule'}</DialogTitle></div>
          <div className="p-6 space-y-4 max-h-[65vh] overflow-y-auto">
            <div><label className="text-[10px] font-black uppercase tracking-widest text-[#0F172A]">Name</label>
              <Input value={form.name} onChange={(e: any) => setForm({ ...form, name: e.target.value })} placeholder="e.g. Default late policy" className="mt-1.5" /></div>
            <div className="grid grid-cols-3 gap-3">
              <div><label className="text-[10px] font-black uppercase tracking-widest text-[#0F172A]">Grace (min)</label>
                <Input type="number" value={form.grace_minutes} onChange={(e: any) => setForm({ ...form, grace_minutes: e.target.value })} className="mt-1.5" /></div>
              <div><label className="text-[10px] font-black uppercase tracking-widest text-[#0F172A]">Lates / deduction</label>
                <Input type="number" value={form.lates_per_deduction} onChange={(e: any) => setForm({ ...form, lates_per_deduction: e.target.value })} className="mt-1.5" /></div>
              <div><label className="text-[10px] font-black uppercase tracking-widest text-[#0F172A]">Days / block</label>
                <Input type="number" value={form.deduction_days_per_block} onChange={(e: any) => setForm({ ...form, deduction_days_per_block: e.target.value })} className="mt-1.5" /></div>
            </div>
            <p className="text-[9px] font-bold text-slate-400">Every N late marks in a month deducts D days, cascading Tier 1 → Tier 2 → Loss of Pay.</p>
            <div className="grid grid-cols-2 gap-3">
              <div><label className="text-[10px] font-black uppercase tracking-widest text-[#0F172A]">Tier 1 leave type</label>
                <select value={form.first_leave_type_id} onChange={e => setForm({ ...form, first_leave_type_id: e.target.value })} className={selectCls}>
                  <option value="">None → straight to LOP</option>
                  {leaveTypes.filter((l: any) => !l.unpaid_allowed).map((l: any) => <option key={l.id} value={l.id}>{l.name}</option>)}
                </select></div>
              <div><label className="text-[10px] font-black uppercase tracking-widest text-[#0F172A]">Tier 2 leave type</label>
                <select value={form.second_leave_type_id} onChange={e => setForm({ ...form, second_leave_type_id: e.target.value })} className={selectCls}>
                  <option value="">None</option>
                  {leaveTypes.filter((l: any) => !l.unpaid_allowed).map((l: any) => <option key={l.id} value={l.id}>{l.name}</option>)}
                </select></div>
            </div>
            <label className="inline-flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-[#0F172A] cursor-pointer">
              <input type="checkbox" checked={form.is_active} onChange={e => setForm({ ...form, is_active: e.target.checked })} className="w-3.5 h-3.5 accent-blue-600" /> Active
            </label>
          </div>
          <DialogFooter className="px-6 py-4 bg-slate-50 border-t border-slate-100">
            <Button variant="ghost" onClick={() => setModalOpen(false)} className="text-[10px] font-black uppercase tracking-widest">Cancel</Button>
            <Button onClick={submit} isLoading={submitting} className="bg-blue-600 hover:bg-blue-700 text-white text-[10px] font-black uppercase tracking-widest">{editing ? 'Update' : 'Create'}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};
