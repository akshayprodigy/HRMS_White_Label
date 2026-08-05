import React, { useEffect, useMemo, useState } from 'react';
import { RefreshCw, UserPlus, Edit3, CheckCircle2, Clock } from 'lucide-react';
import { Card, Button, Badge, cn } from './ui-elements';
import { toast } from 'sonner';
import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';
import { Dialog, DialogContent, DialogTitle, DialogFooter } from './ui/dialog';
import { Input } from './ui/input';

const money = (n: number) => '₹' + (n || 0).toLocaleString('en-IN', { maximumFractionDigits: 0 });
const errMsg = (e: any, f: string) => {
  const d = e?.response?.data?.detail;
  if (typeof d === 'string') return d;
  if (Array.isArray(d)) return d.map((x: any) => x?.msg || JSON.stringify(x)).join('; ');
  return e?.message || f;
};
const selectCls = 'mt-1.5 w-full h-11 px-3 bg-slate-50 border border-slate-200 rounded-xl text-sm font-bold text-[#0F172A] outline-none';

const STATUS: Record<string, { label: string; variant: any }> = {
  awaiting_value: { label: 'Awaiting value (Head)', variant: 'warning' },
  pending: { label: 'In CEO/MD approval', variant: 'info' },
  approved: { label: 'Approved — HR to commit', variant: 'success' },
  applied: { label: 'Applied', variant: 'neutral' },
  rejected: { label: 'Rejected', variant: 'error' },
};

export const MultiStageRevisionsView: React.FC = () => {
  const [rows, setRows] = useState<any[]>([]);
  const [employees, setEmployees] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<number | null>(null);

  const [selOpen, setSelOpen] = useState(false);
  const [selForm, setSelForm] = useState({ employee_id: '', effective_from: '', revision_type: 'increment', reason: '' });
  const [valOpen, setValOpen] = useState<any | null>(null);
  const [valForm, setValForm] = useState({ new_basic: '', new_conveyance: '', new_hra: '', new_other_allowance: '' });
  const [submitting, setSubmitting] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const [r, e] = await Promise.all([
        client.get(ENDPOINTS.REVISIONS.REVISIONS),
        client.get(ENDPOINTS.HR.EMPLOYEES, { params: { limit: 500 } }).catch(() => ({ data: { items: [] } })),
      ]);
      const all = Array.isArray(r.data) ? r.data : (r.data?.items || []);
      setRows(all.filter((x: any) => x.is_multistage));
      setEmployees(e.data?.items ?? (Array.isArray(e.data) ? e.data : []));
    } catch (err: any) {
      toast.error(errMsg(err, 'Failed to load revisions'));
    } finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  const empName = useMemo(() => {
    const m: Record<number, string> = {};
    employees.forEach(e => { if (e?.id) m[e.id] = e.user?.full_name || e.employee_id; });
    return m;
  }, [employees]);

  const submitSelect = async () => {
    if (!selForm.employee_id || !selForm.effective_from) { toast.error('Employee and effective date are required'); return; }
    setSubmitting(true);
    try {
      await client.post(ENDPOINTS.REVISIONS.SELECT, {
        employee_id: Number(selForm.employee_id), effective_from: selForm.effective_from,
        revision_type: selForm.revision_type, reason: selForm.reason || null,
      });
      toast.success('Employee selected — functional head can now enter the value');
      setSelOpen(false); setSelForm({ employee_id: '', effective_from: '', revision_type: 'increment', reason: '' });
      load();
    } catch (e: any) { toast.error(errMsg(e, 'Select failed')); }
    finally { setSubmitting(false); }
  };

  const submitValue = async () => {
    const b = Number(valForm.new_basic), c = Number(valForm.new_conveyance), h = Number(valForm.new_hra), o = Number(valForm.new_other_allowance);
    if (!(b >= 0 && c >= 0 && h >= 0 && o >= 0) || !valForm.new_basic) { toast.error('Enter all component values'); return; }
    setSubmitting(true);
    try {
      await client.post(ENDPOINTS.REVISIONS.ENTER_VALUE(valOpen.id), { new_basic: b, new_conveyance: c, new_hra: h, new_other_allowance: o });
      toast.success('Value submitted → sent for CEO/MD approval');
      setValOpen(null); setValForm({ new_basic: '', new_conveyance: '', new_hra: '', new_other_allowance: '' });
      load();
    } catch (e: any) { toast.error(errMsg(e, 'Enter-value failed')); }
    finally { setSubmitting(false); }
  };

  const apply = async (r: any) => {
    setBusy(r.id);
    try { await client.post(ENDPOINTS.REVISIONS.APPLY(r.id), {}); toast.success('Applied — employee master updated'); load(); }
    catch (e: any) { toast.error(errMsg(e, 'Apply failed')); }
    finally { setBusy(null); }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-black text-[#0F172A] uppercase tracking-tight">Multi-stage Revision</h3>
          <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mt-1">
            HR selects → Functional head enters value → CEO/MD approve → HR commits
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button type="button" onClick={load} className="p-2 text-slate-400 hover:text-blue-600" title="Refresh" aria-label="Refresh"><RefreshCw size={16} className={cn(loading && 'animate-spin')} /></button>
          <Button onClick={() => setSelOpen(true)} className="h-9 bg-blue-600 hover:bg-blue-700 text-white font-black uppercase text-[10px] tracking-widest"><UserPlus size={14} className="mr-1.5" /> Select Employee</Button>
        </div>
      </div>

      <Card className="p-0 border-slate-200 overflow-hidden bg-white">
        {loading ? <div className="py-16 text-center text-[10px] font-black uppercase tracking-widest text-slate-400 animate-pulse">Loading…</div>
          : rows.length === 0 ? <div className="py-16 text-center text-[11px] font-bold text-slate-400">No multi-stage revisions yet — click "Select Employee" to start one.</div>
          : (
          <table className="w-full text-left">
            <thead className="bg-white border-b border-slate-100"><tr>
              <th className="px-6 py-3 text-[9px] font-black text-slate-400 uppercase tracking-widest">Employee</th>
              <th className="px-6 py-3 text-[9px] font-black text-slate-400 uppercase tracking-widest">Old → New CTC</th>
              <th className="px-6 py-3 text-[9px] font-black text-slate-400 uppercase tracking-widest">Effective</th>
              <th className="px-6 py-3 text-[9px] font-black text-slate-400 uppercase tracking-widest">Status</th>
              <th className="px-6 py-3 text-right text-[9px] font-black text-slate-400 uppercase tracking-widest">Action</th>
            </tr></thead>
            <tbody className="divide-y divide-slate-50">
              {rows.map(r => {
                const st = STATUS[r.status] || { label: r.status, variant: 'neutral' };
                return (
                  <tr key={r.id} className="hover:bg-slate-50/60">
                    <td className="px-6 py-3 text-sm font-black text-[#0F172A]">{r.employee_full_name || empName[r.employee_id] || `#${r.employee_id}`}</td>
                    <td className="px-6 py-3 text-sm font-bold tabular-nums">
                      {money(r.old_ctc)} → {r.status === 'awaiting_value' ? '—' : money(r.new_ctc)}
                      {r.status !== 'awaiting_value' && r.hike_percent != null && <span className={cn('ml-2 text-[10px] font-black', r.hike_percent >= 0 ? 'text-emerald-600' : 'text-rose-600')}>{r.hike_percent >= 0 ? '+' : ''}{r.hike_percent.toFixed(1)}%</span>}
                    </td>
                    <td className="px-6 py-3 text-[11px] font-bold text-slate-500">{r.effective_from}</td>
                    <td className="px-6 py-3"><Badge variant={st.variant} className="text-[8px] uppercase">{st.label}</Badge></td>
                    <td className="px-6 py-3 text-right">
                      {r.status === 'awaiting_value' && (
                        <Button onClick={() => { setValOpen(r); setValForm({ new_basic: String(r.old_basic || ''), new_conveyance: String(r.old_conveyance || ''), new_hra: String(r.old_hra || ''), new_other_allowance: String(r.old_other_allowance || '') }); }}
                          className="h-9 bg-amber-600 hover:bg-amber-700 text-white font-black uppercase text-[10px] tracking-widest"><Edit3 size={14} className="mr-1.5" /> Enter Value</Button>
                      )}
                      {r.status === 'pending' && <span className="text-[10px] font-black uppercase tracking-widest text-slate-400"><Clock size={11} className="inline mr-1" />awaiting CEO/MD</span>}
                      {r.status === 'approved' && (
                        <Button onClick={() => apply(r)} isLoading={busy === r.id} className="h-9 bg-emerald-600 hover:bg-emerald-700 text-white font-black uppercase text-[10px] tracking-widest"><CheckCircle2 size={14} className="mr-1.5" /> Commit</Button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </Card>

      {/* Select modal */}
      <Dialog open={selOpen} onOpenChange={setSelOpen}>
        <DialogContent className="max-w-md p-0 overflow-hidden">
          <div className="bg-blue-600 px-6 py-5 text-white"><DialogTitle className="text-lg font-black uppercase tracking-tight">Select Employee for Revision</DialogTitle></div>
          <div className="p-6 space-y-4">
            <div><label className="text-[10px] font-black uppercase tracking-widest text-[#0F172A]">Employee</label>
              <select value={selForm.employee_id} onChange={e => setSelForm({ ...selForm, employee_id: e.target.value })} className={selectCls}>
                <option value="">Select…</option>
                {employees.filter(e => e?.id).map(e => <option key={e.id} value={e.id}>{e.user?.full_name || e.employee_id}</option>)}
              </select></div>
            <div className="grid grid-cols-2 gap-3">
              <div><label className="text-[10px] font-black uppercase tracking-widest text-[#0F172A]">Effective From</label>
                <Input type="date" value={selForm.effective_from} onChange={(e: any) => setSelForm({ ...selForm, effective_from: e.target.value })} className="mt-1.5" /></div>
              <div><label className="text-[10px] font-black uppercase tracking-widest text-[#0F172A]">Type</label>
                <select value={selForm.revision_type} onChange={e => setSelForm({ ...selForm, revision_type: e.target.value })} className={selectCls}>
                  <option value="increment">Increment</option><option value="promotion">Promotion</option><option value="correction">Correction</option>
                </select></div>
            </div>
            <div><label className="text-[10px] font-black uppercase tracking-widest text-[#0F172A]">Reason</label>
              <Input value={selForm.reason} onChange={(e: any) => setSelForm({ ...selForm, reason: e.target.value })} placeholder="Optional" className="mt-1.5" /></div>
          </div>
          <DialogFooter className="px-6 py-4 bg-slate-50 border-t border-slate-100">
            <Button variant="ghost" onClick={() => setSelOpen(false)} className="text-[10px] font-black uppercase tracking-widest">Cancel</Button>
            <Button onClick={submitSelect} isLoading={submitting} className="bg-blue-600 hover:bg-blue-700 text-white text-[10px] font-black uppercase tracking-widest">Select</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Enter-value modal */}
      <Dialog open={!!valOpen} onOpenChange={(o) => !o && setValOpen(null)}>
        <DialogContent className="max-w-md p-0 overflow-hidden">
          <div className="bg-amber-600 px-6 py-5 text-white"><DialogTitle className="text-lg font-black uppercase tracking-tight">Enter New Value (Functional Head)</DialogTitle></div>
          <div className="p-6 space-y-4">
            <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Current CTC: {valOpen && money(valOpen.old_ctc)}. On submit this goes to CEO/MD for approval.</p>
            <div className="grid grid-cols-2 gap-3">
              {(['new_basic', 'new_conveyance', 'new_hra', 'new_other_allowance'] as const).map(k => (
                <div key={k}><label className="text-[10px] font-black uppercase tracking-widest text-[#0F172A]">{k.replace('new_', '').replace('_', ' ')}</label>
                  <Input type="number" value={(valForm as any)[k]} onChange={(e: any) => setValForm({ ...valForm, [k]: e.target.value })} className="mt-1.5" /></div>
              ))}
            </div>
            <div className="text-sm font-black text-[#0F172A]">New CTC: {money(Number(valForm.new_basic || 0) + Number(valForm.new_conveyance || 0) + Number(valForm.new_hra || 0) + Number(valForm.new_other_allowance || 0))}</div>
          </div>
          <DialogFooter className="px-6 py-4 bg-slate-50 border-t border-slate-100">
            <Button variant="ghost" onClick={() => setValOpen(null)} className="text-[10px] font-black uppercase tracking-widest">Cancel</Button>
            <Button onClick={submitValue} isLoading={submitting} className="bg-amber-600 hover:bg-amber-700 text-white text-[10px] font-black uppercase tracking-widest">Submit for Approval</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};
