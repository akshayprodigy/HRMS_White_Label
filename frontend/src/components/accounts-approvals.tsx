import React, { useEffect, useMemo, useState } from 'react';
import {
  RefreshCw, ShieldCheck, CheckCircle2, Clock, IndianRupee,
  ChevronDown, ChevronRight, Download, Users, Pencil,
} from 'lucide-react';
import { Card, Button, Badge, cn } from './ui-elements';
import { toast } from 'sonner';
import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';
import { Dialog, DialogContent, DialogTitle, DialogFooter } from './ui/dialog';

interface Run {
  id: number;
  month: number;
  year: number;
  status: string;
  total_gross: number;
  total_net: number;
  total_deductions: number;
  finalized_at: string | null;
  accounts_approved_at: string | null;
}

interface Line {
  id: number;
  user_id: number;
  user_full_name: string | null;
  base_salary: number;
  payable_days: number;
  lop_days: number;
  gross_pay: number;
  net_pay: number;
  advance_deduction: number;
  allowances: Record<string, any> | null;
  deductions: Record<string, any> | null;
}

const MONTHS = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const money = (n: number) => '₹' + (n || 0).toLocaleString('en-IN', { maximumFractionDigits: 0 });
const num = (n: any) => (Number(n) || 0).toLocaleString('en-IN', { maximumFractionDigits: 0 });

const errMsg = (err: any, fallback: string): string => {
  const detail = err?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) return detail.map((d: any) => d?.msg || JSON.stringify(d)).join('; ');
  return err?.message || fallback;
};

const alw = (l: Line, k: string) => Number(l.allowances?.[k]) || 0;
const ded = (l: Line, k: string) => Number(l.deductions?.[k]) || 0;

export const AccountsApprovals: React.FC = () => {
  const [runs, setRuns] = useState<Run[]>([]);
  const [loading, setLoading] = useState(true);
  const [confirm, setConfirm] = useState<Run | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // Per-employee drill-down
  const [expanded, setExpanded] = useState<number | null>(null);
  const [linesByRun, setLinesByRun] = useState<Record<number, Line[]>>({});
  const [loadingLines, setLoadingLines] = useState<number | null>(null);

  // Line edit
  const [edit, setEdit] = useState<{ runId: number; line: Line } | null>(null);
  const [editForm, setEditForm] = useState({ arrear: '', incentive: '', guest_house: '', tds: '', reason: '' });
  const [savingEdit, setSavingEdit] = useState(false);

  const fetchRuns = async () => {
    setLoading(true);
    try {
      const res = await client.get(ENDPOINTS.HR.PAYROLL.DASHBOARD);
      setRuns(res.data?.active_runs || []);
    } catch (e: any) {
      toast.error(errMsg(e, 'Failed to load payroll runs (are you punched in?)'));
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { fetchRuns(); }, []);

  const awaiting = useMemo(() => runs.filter(r => r.status === 'finalized'), [runs]);
  const approved = useMemo(() => runs.filter(r => r.status === 'accounts_approved'), [runs]);

  const toggleExpand = async (run: Run) => {
    if (expanded === run.id) { setExpanded(null); return; }
    setExpanded(run.id);
    if (!linesByRun[run.id]) {
      setLoadingLines(run.id);
      try {
        const res = await client.get<Line[]>(ENDPOINTS.HR.PAYROLL.LINES(run.id));
        setLinesByRun(prev => ({ ...prev, [run.id]: res.data || [] }));
      } catch (e: any) {
        toast.error(errMsg(e, 'Failed to load employee breakdown'));
        setExpanded(null);
      } finally {
        setLoadingLines(null);
      }
    }
  };

  const reloadLines = async (runId: number) => {
    try {
      const res = await client.get<Line[]>(ENDPOINTS.HR.PAYROLL.LINES(runId));
      setLinesByRun(prev => ({ ...prev, [runId]: res.data || [] }));
    } catch { /* keep old */ }
  };

  const openEdit = (runId: number, line: Line) => {
    setEditForm({
      arrear: String(alw(line, 'arrear') || ''),
      incentive: String(alw(line, 'incentive') || ''),
      guest_house: String(ded(line, 'guest_house') || ''),
      tds: String(ded(line, 'tds') || ''),
      reason: '',
    });
    setEdit({ runId, line });
  };

  const saveEdit = async () => {
    if (!edit) return;
    if (editForm.reason.trim().length < 1) {
      toast.error('A reason is required for a payroll line edit');
      return;
    }
    setSavingEdit(true);
    try {
      const payload: any = { reason: editForm.reason.trim() };
      (['arrear', 'incentive', 'guest_house', 'tds'] as const).forEach(k => {
        if (editForm[k] !== '') payload[k] = Number(editForm[k]);
      });
      await client.patch(ENDPOINTS.HR.PAYROLL.LINE_UPDATE(edit.runId, edit.line.id), payload);
      toast.success('Payroll line updated');
      const runId = edit.runId;
      setEdit(null);
      await reloadLines(runId);
      await fetchRuns(); // refresh the run summary (gross/net/deductions)
    } catch (e: any) {
      toast.error(errMsg(e, 'Failed to update line'));
    } finally {
      setSavingEdit(false);
    }
  };

  const approve = async () => {
    if (!confirm) return;
    setSubmitting(true);
    try {
      await client.post(ENDPOINTS.HR.PAYROLL.ACCOUNTS_APPROVE(confirm.id));
      toast.success(`Approved ${MONTHS[confirm.month]} ${confirm.year} for payment`);
      setConfirm(null);
      fetchRuns();
    } catch (e: any) {
      toast.error(errMsg(e, 'Approval failed'));
    } finally {
      setSubmitting(false);
    }
  };

  const exportCsv = (run: Run, lines: Line[]) => {
    const headers = [
      'Employee', 'Payable Days', 'LOP Days', 'Basic', 'HRA', 'Conveyance',
      'Other Allow.', 'Arrear', 'Incentive', 'Gross', 'PF', 'ESI', 'Prof. Tax',
      'TDS', 'Advance Recovery', 'Total Deductions', 'Net Pay',
    ];
    const rows = lines.map(l => [
      l.user_full_name || `#${l.user_id}`, l.payable_days, l.lop_days,
      alw(l, 'basic_salary_actual') || l.base_salary, alw(l, 'hra_fixed'),
      alw(l, 'conveyance_fixed'), alw(l, 'other_allowance_fixed'),
      alw(l, 'arrear'), alw(l, 'incentive'), l.gross_pay,
      ded(l, 'employee_pf'), ded(l, 'employee_esi'), ded(l, 'professional_tax'),
      ded(l, 'tds'), l.advance_deduction || ded(l, 'advance_recovery'),
      ded(l, 'total_deductions'), l.net_pay,
    ]);
    const csv = [headers, ...rows].map(r => r.join(',')).join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `payroll_${MONTHS[run.month]}_${run.year}_employee_sheet.csv`;
    a.click();
    window.URL.revokeObjectURL(url);
  };

  const EmployeeSheet = ({ run, editable }: { run: Run; editable: boolean }) => {
    const lines = linesByRun[run.id];
    if (loadingLines === run.id) {
      return <div className="py-8 text-center text-[10px] font-black uppercase tracking-widest text-slate-400 animate-pulse">Loading employee breakdown…</div>;
    }
    if (!lines) return null;
    const tot = lines.reduce((a, l) => ({
      gross: a.gross + l.gross_pay,
      ded: a.ded + ded(l, 'total_deductions'),
      adv: a.adv + (l.advance_deduction || ded(l, 'advance_recovery')),
      net: a.net + l.net_pay,
    }), { gross: 0, ded: 0, adv: 0, net: 0 });

    return (
      <div className="bg-slate-50/70 border-t border-slate-200 p-4">
        <div className="flex items-center justify-between mb-3">
          <p className="text-[10px] font-black uppercase tracking-widest text-slate-500 flex items-center gap-1.5">
            <Users size={13} /> Employee-wise breakdown ({lines.length}) — verify calculations before approving
          </p>
          <button type="button" onClick={() => exportCsv(run, lines)}
            className="inline-flex items-center gap-1.5 text-[10px] font-black uppercase tracking-widest text-blue-600 hover:text-blue-800">
            <Download size={13} /> Download sheet (CSV)
          </button>
        </div>
        <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
          <table className="w-full text-right text-xs whitespace-nowrap">
            <thead className="bg-slate-100/70 border-b border-slate-200">
              <tr className="text-[9px] font-black text-slate-500 uppercase tracking-wider">
                <th className="px-3 py-2 text-left sticky left-0 bg-slate-100/70">Employee</th>
                <th className="px-3 py-2">Days</th>
                <th className="px-3 py-2">LOP</th>
                <th className="px-3 py-2">Basic</th>
                <th className="px-3 py-2">HRA</th>
                <th className="px-3 py-2">Conv.</th>
                <th className="px-3 py-2">Other</th>
                <th className="px-3 py-2">Gross</th>
                <th className="px-3 py-2">PF</th>
                <th className="px-3 py-2">PT</th>
                <th className="px-3 py-2">TDS</th>
                <th className="px-3 py-2">Adv. Rec.</th>
                <th className="px-3 py-2">Deductions</th>
                <th className="px-3 py-2 text-emerald-700">Net Pay</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {lines.map(l => (
                <tr key={l.id} className="hover:bg-slate-50/60 tabular-nums">
                  <td className="px-3 py-2 text-left font-bold text-[#0F172A] sticky left-0 bg-white">
                    <span className="inline-flex items-center gap-1.5">
                      {editable && (
                        <button type="button" onClick={() => openEdit(run.id, l)}
                          className="text-slate-400 hover:text-blue-600" title="Edit this line">
                          <Pencil size={12} />
                        </button>
                      )}
                      {l.user_full_name || `#${l.user_id}`}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-slate-600">{l.payable_days}</td>
                  <td className={cn('px-3 py-2', l.lop_days > 0 ? 'text-rose-600 font-bold' : 'text-slate-400')}>{l.lop_days}</td>
                  <td className="px-3 py-2 text-slate-600">{num(alw(l, 'basic_salary_actual') || l.base_salary)}</td>
                  <td className="px-3 py-2 text-slate-600">{num(alw(l, 'hra_fixed'))}</td>
                  <td className="px-3 py-2 text-slate-600">{num(alw(l, 'conveyance_fixed'))}</td>
                  <td className="px-3 py-2 text-slate-600">{num(alw(l, 'other_allowance_fixed'))}</td>
                  <td className="px-3 py-2 font-bold text-[#0F172A]">{num(l.gross_pay)}</td>
                  <td className="px-3 py-2 text-slate-600">{num(ded(l, 'employee_pf'))}</td>
                  <td className="px-3 py-2 text-slate-600">{num(ded(l, 'professional_tax'))}</td>
                  <td className="px-3 py-2 text-slate-600">{num(ded(l, 'tds'))}</td>
                  <td className={cn('px-3 py-2', (l.advance_deduction || ded(l, 'advance_recovery')) > 0 ? 'text-amber-700 font-bold' : 'text-slate-400')}>{num(l.advance_deduction || ded(l, 'advance_recovery'))}</td>
                  <td className="px-3 py-2 text-slate-500">{num(ded(l, 'total_deductions'))}</td>
                  <td className="px-3 py-2 font-black text-emerald-700">{num(l.net_pay)}</td>
                </tr>
              ))}
            </tbody>
            <tfoot className="bg-slate-100/80 border-t-2 border-slate-300">
              <tr className="tabular-nums font-black text-[#0F172A]">
                <td className="px-3 py-2 text-left uppercase text-[9px] tracking-widest sticky left-0 bg-slate-100/80">Total ({lines.length})</td>
                <td colSpan={6}></td>
                <td className="px-3 py-2">{num(tot.gross)}</td>
                <td colSpan={3}></td>
                <td className="px-3 py-2 text-amber-700">{num(tot.adv)}</td>
                <td className="px-3 py-2">{num(tot.ded)}</td>
                <td className="px-3 py-2 text-emerald-700">{num(tot.net)}</td>
              </tr>
            </tfoot>
          </table>
        </div>
        <p className="text-[9px] font-bold text-slate-400 uppercase tracking-widest mt-2">
          Sheet total net {money(tot.net)} — reconcile against run Net Payable {money(run.total_net)}
        </p>
      </div>
    );
  };

  const RunBlock = ({ r, canApprove }: { r: Run; canApprove: boolean }) => {
    const isOpen = expanded === r.id;
    return (
      <>
        <tr className="hover:bg-slate-50/60 transition-colors">
          <td className="px-6 py-4">
            <button type="button" onClick={() => toggleExpand(r)}
              className="inline-flex items-center gap-2 text-sm font-black text-[#0F172A] hover:text-blue-600">
              {isOpen ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
              {MONTHS[r.month]} {r.year}
            </button>
          </td>
          <td className="px-6 py-4 text-sm font-bold text-[#0F172A] tabular-nums">{money(r.total_gross)}</td>
          <td className="px-6 py-4 text-sm font-bold text-slate-500 tabular-nums">{money(r.total_deductions)}</td>
          <td className="px-6 py-4 text-sm font-black text-emerald-700 tabular-nums">{money(r.total_net)}</td>
          <td className="px-6 py-4">
            {canApprove ? (
              <Badge variant="warning" className="text-[8px] uppercase"><Clock size={9} className="mr-1 inline" />Awaiting Accounts</Badge>
            ) : (
              <Badge variant="success" className="text-[8px] uppercase"><CheckCircle2 size={9} className="mr-1 inline" />Approved</Badge>
            )}
          </td>
          <td className="px-6 py-4 text-right">
            {canApprove && (
              <Button onClick={() => setConfirm(r)} className="h-9 bg-emerald-600 hover:bg-emerald-700 text-white font-black uppercase text-[10px] tracking-widest">
                <ShieldCheck size={14} className="mr-1.5" /> Approve for Payment
              </Button>
            )}
          </td>
        </tr>
        {isOpen && (
          <tr>
            <td colSpan={6} className="p-0"><EmployeeSheet run={r} editable={canApprove} /></td>
          </tr>
        )}
      </>
    );
  };

  const RunTable = ({ list, canApprove }: { list: Run[]; canApprove: boolean }) => (
    <div className="overflow-x-auto">
      <table className="w-full text-left">
        <thead className="bg-white border-b border-slate-100">
          <tr>
            <th className="px-6 py-3 text-[9px] font-black text-slate-400 uppercase tracking-widest">Period</th>
            <th className="px-6 py-3 text-[9px] font-black text-slate-400 uppercase tracking-widest">Gross</th>
            <th className="px-6 py-3 text-[9px] font-black text-slate-400 uppercase tracking-widest">Deductions</th>
            <th className="px-6 py-3 text-[9px] font-black text-slate-400 uppercase tracking-widest">Net Payable</th>
            <th className="px-6 py-3 text-[9px] font-black text-slate-400 uppercase tracking-widest">Status</th>
            <th className="px-6 py-3 text-right text-[9px] font-black text-slate-400 uppercase tracking-widest">Action</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-50">
          {list.map(r => <RunBlock key={r.id} r={r} canApprove={canApprove} />)}
        </tbody>
      </table>
    </div>
  );

  return (
    <div className="p-8 space-y-6 max-w-[1400px] mx-auto animate-in fade-in duration-300">
      <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-4">
        <div>
          <h2 className="text-3xl font-black text-[#0F172A] tracking-tighter uppercase">Accounts — Payroll Approval</h2>
          <p className="text-[#64748B] font-bold uppercase tracking-widest text-[10px] mt-1">
            Verify Finalized Payroll Before Payment · Expand a run to check every employee's calculation
          </p>
        </div>
        <button type="button" onClick={fetchRuns} className="p-2 text-slate-400 hover:text-blue-600 self-end" title="Refresh" aria-label="Refresh">
          <RefreshCw size={16} className={cn(loading && 'animate-spin')} />
        </button>
      </div>

      <Card className="p-0 border-slate-200 overflow-hidden bg-white">
        <div className="px-6 py-4 border-b border-slate-100 bg-amber-50/40">
          <h4 className="text-sm font-black text-[#0F172A] tracking-tight uppercase flex items-center gap-2">
            <Clock size={16} /> Awaiting Approval {!loading && <span className="text-slate-400 font-bold text-[10px]">({awaiting.length})</span>}
          </h4>
        </div>
        {loading ? (
          <div className="py-16 text-center text-[10px] font-black uppercase tracking-widest text-slate-400 animate-pulse">Loading…</div>
        ) : awaiting.length === 0 ? (
          <div className="py-16 text-center text-[10px] font-black uppercase tracking-widest text-slate-400">Nothing awaiting Accounts approval</div>
        ) : (
          <RunTable list={awaiting} canApprove />
        )}
      </Card>

      {approved.length > 0 && (
        <Card className="p-0 border-slate-200 overflow-hidden bg-white">
          <div className="px-6 py-4 border-b border-slate-100 bg-emerald-50/40">
            <h4 className="text-sm font-black text-[#0F172A] tracking-tight uppercase flex items-center gap-2">
              <CheckCircle2 size={16} /> Approved — Ready for HR to Publish ({approved.length})
            </h4>
          </div>
          <RunTable list={approved} canApprove={false} />
        </Card>
      )}

      {/* Line edit dialog */}
      <Dialog open={!!edit} onOpenChange={(o) => !o && setEdit(null)}>
        <DialogContent className="max-w-md">
          <DialogTitle className="flex items-center gap-2 text-base font-black uppercase tracking-tight text-[#0F172A]">
            <Pencil size={15} className="text-blue-600" /> Edit payroll line
          </DialogTitle>
          {edit && (
            <p className="text-[10px] font-bold text-slate-500 -mt-1">
              {edit.line.user_full_name} · gross recalculates on save
            </p>
          )}
          <div className="space-y-3 pt-1">
            <div className="grid grid-cols-2 gap-3">
              {(['arrear', 'incentive', 'guest_house', 'tds'] as const).map(k => (
                <div key={k} className="space-y-1">
                  <label className="text-[9px] font-black uppercase tracking-widest text-slate-400">
                    {k === 'guest_house' ? 'Guest House (−)' : k === 'tds' ? 'TDS (−)' : k}
                  </label>
                  <input type="number" value={(editForm as any)[k]}
                    onChange={(e) => setEditForm({ ...editForm, [k]: e.target.value })}
                    placeholder="0"
                    className="w-full h-10 px-3 rounded-lg border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-blue-600/30 focus:border-blue-500 bg-white" />
                </div>
              ))}
            </div>
            <div className="space-y-1">
              <label className="text-[9px] font-black uppercase tracking-widest text-slate-400">Reason (required · audited)</label>
              <textarea value={editForm.reason} onChange={(e) => setEditForm({ ...editForm, reason: e.target.value })}
                placeholder="e.g. Approved arrear for prior-month correction"
                className="w-full h-16 px-3 py-2 rounded-lg border border-slate-200 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-blue-600/30 focus:border-blue-500 bg-white" />
            </div>
            <p className="text-[9px] font-bold text-slate-400 uppercase tracking-widest">
              Arrear / incentive add to gross; guest house / TDS are deductions. Statutory PF / ESI / PT recompute automatically.
            </p>
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setEdit(null)} className="text-[10px] font-black uppercase tracking-widest">Cancel</Button>
            <Button onClick={saveEdit} isLoading={savingEdit} className="bg-blue-600 hover:bg-blue-700 text-white text-[10px] font-black uppercase tracking-widest">Save &amp; Recalculate</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!confirm} onOpenChange={(o) => !o && setConfirm(null)}>
        <DialogContent className="max-w-md p-0 overflow-hidden">
          <div className="bg-emerald-600 px-6 py-5 text-white">
            <DialogTitle className="text-lg font-black uppercase tracking-tight flex items-center gap-2">
              <IndianRupee size={18} /> Approve for Payment
            </DialogTitle>
          </div>
          <div className="p-6 space-y-3">
            <p className="text-sm text-slate-700">
              Approve <strong>{confirm && `${MONTHS[confirm.month]} ${confirm.year}`}</strong> payroll for payment?
            </p>
            {confirm && (
              <div className="rounded-xl bg-slate-50 border border-slate-200 p-4 space-y-1">
                <div className="flex justify-between text-sm"><span className="text-slate-500 font-bold">Net payable</span><span className="font-black text-emerald-700 tabular-nums">{money(confirm.total_net)}</span></div>
                <div className="flex justify-between text-sm"><span className="text-slate-500 font-bold">Gross</span><span className="font-bold tabular-nums">{money(confirm.total_gross)}</span></div>
              </div>
            )}
            <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">
              This unlocks HR to publish payslips. It cannot be published without this approval.
            </p>
          </div>
          <DialogFooter className="px-6 py-4 bg-slate-50 border-t border-slate-100">
            <Button variant="ghost" onClick={() => setConfirm(null)} className="text-[10px] font-black uppercase tracking-widest">Cancel</Button>
            <Button onClick={approve} isLoading={submitting} className="bg-emerald-600 hover:bg-emerald-700 text-white text-[10px] font-black uppercase tracking-widest">Approve</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};
