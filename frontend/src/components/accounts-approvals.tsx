import React, { useEffect, useMemo, useState } from 'react';
import { RefreshCw, ShieldCheck, CheckCircle2, Clock, IndianRupee } from 'lucide-react';
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

const MONTHS = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const money = (n: number) => '₹' + (n || 0).toLocaleString('en-IN', { maximumFractionDigits: 0 });

const errMsg = (err: any, fallback: string): string => {
  const detail = err?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) return detail.map((d: any) => d?.msg || JSON.stringify(d)).join('; ');
  return err?.message || fallback;
};

export const AccountsApprovals: React.FC = () => {
  const [runs, setRuns] = useState<Run[]>([]);
  const [loading, setLoading] = useState(true);
  const [confirm, setConfirm] = useState<Run | null>(null);
  const [submitting, setSubmitting] = useState(false);

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

  const RunRow = ({ r, canApprove }: { r: Run; canApprove: boolean }) => (
    <tr className="hover:bg-slate-50/60 transition-colors">
      <td className="px-6 py-4 text-sm font-black text-[#0F172A]">{MONTHS[r.month]} {r.year}</td>
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
  );

  return (
    <div className="p-8 space-y-6 max-w-[1400px] mx-auto animate-in fade-in duration-300">
      <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-4">
        <div>
          <h2 className="text-3xl font-black text-[#0F172A] tracking-tighter uppercase">Accounts — Payroll Approval</h2>
          <p className="text-[#64748B] font-bold uppercase tracking-widest text-[10px] mt-1">
            Verify Finalized Payroll Before Payment · HR Finalizes → Accounts Approves → Payment
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
                {awaiting.map(r => <RunRow key={r.id} r={r} canApprove />)}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {approved.length > 0 && (
        <Card className="p-0 border-slate-200 overflow-hidden bg-white">
          <div className="px-6 py-4 border-b border-slate-100 bg-emerald-50/40">
            <h4 className="text-sm font-black text-[#0F172A] tracking-tight uppercase flex items-center gap-2">
              <CheckCircle2 size={16} /> Approved — Ready for HR to Publish ({approved.length})
            </h4>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead className="bg-white border-b border-slate-100">
                <tr>
                  <th className="px-6 py-3 text-[9px] font-black text-slate-400 uppercase tracking-widest">Period</th>
                  <th className="px-6 py-3 text-[9px] font-black text-slate-400 uppercase tracking-widest">Gross</th>
                  <th className="px-6 py-3 text-[9px] font-black text-slate-400 uppercase tracking-widest">Deductions</th>
                  <th className="px-6 py-3 text-[9px] font-black text-slate-400 uppercase tracking-widest">Net Payable</th>
                  <th className="px-6 py-3 text-[9px] font-black text-slate-400 uppercase tracking-widest">Status</th>
                  <th className="px-6 py-3"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {approved.map(r => <RunRow key={r.id} r={r} canApprove={false} />)}
              </tbody>
            </table>
          </div>
        </Card>
      )}

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
