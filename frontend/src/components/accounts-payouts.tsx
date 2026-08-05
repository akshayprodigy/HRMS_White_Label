import React, { useEffect, useMemo, useState } from 'react';
import { RefreshCw, ShieldCheck, Receipt, Plane, Wallet } from 'lucide-react';
import { Card, Button, Badge, cn } from './ui-elements';
import { toast } from 'sonner';
import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';

type Tab = 'expenses' | 'travel' | 'advances';
const rupees = (paise: number) => '₹' + ((paise || 0) / 100).toLocaleString('en-IN', { maximumFractionDigits: 0 });
const rupeesF = (n: number) => '₹' + (n || 0).toLocaleString('en-IN', { maximumFractionDigits: 0 });
const errMsg = (e: any, f: string) => {
  const d = e?.response?.data?.detail;
  if (typeof d === 'string') return d;
  if (Array.isArray(d)) return d.map((x: any) => x?.msg || JSON.stringify(x)).join('; ');
  return e?.message || f;
};

export const AccountsPayouts: React.FC = () => {
  const [tab, setTab] = useState<Tab>('expenses');
  const [expenses, setExpenses] = useState<any[]>([]);
  const [travel, setTravel] = useState<any[]>([]);
  const [advances, setAdvances] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      const [e, t, a] = await Promise.all([
        client.get(ENDPOINTS.EXPENSES.ACCOUNTS_QUEUE).catch(() => ({ data: [] })),
        client.get(ENDPOINTS.EXPENSES.TRAVEL_ACCOUNTS_QUEUE).catch(() => ({ data: [] })),
        client.get(ENDPOINTS.HR.ADVANCE_PENDING_ACCOUNTS).catch(() => ({ data: [] })),
      ]);
      setExpenses(e.data || []);
      setTravel(t.data || []);
      setAdvances(a.data || []);
    } catch (err: any) {
      toast.error(errMsg(err, 'Failed to load payout queues'));
    } finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  const act = async (key: string, fn: () => Promise<any>, ok: string) => {
    setBusy(key);
    try { await fn(); toast.success(ok); await load(); }
    catch (e: any) { toast.error(errMsg(e, 'Action failed')); }
    finally { setBusy(null); }
  };

  const counts = useMemo(() => ({ expenses: expenses.length, travel: travel.length, advances: advances.length }), [expenses, travel, advances]);

  const TabBtn = ({ id, label, icon: Icon, n }: any) => (
    <button type="button" onClick={() => setTab(id)}
      className={cn('inline-flex items-center gap-2 px-4 h-10 rounded-xl text-[10px] font-black uppercase tracking-widest',
        tab === id ? 'bg-blue-600 text-white' : 'bg-white border border-slate-200 text-slate-600 hover:border-blue-600')}>
      <Icon size={14} /> {label} {n > 0 && <span className={cn('ml-1 px-1.5 rounded-full text-[9px]', tab === id ? 'bg-white/25' : 'bg-blue-100 text-blue-700')}>{n}</span>}
    </button>
  );

  const Empty = ({ what }: { what: string }) => (
    <div className="py-16 text-center text-[10px] font-black uppercase tracking-widest text-slate-400">Nothing awaiting Accounts — {what}</div>
  );

  return (
    <div className="p-8 space-y-6 max-w-[1400px] mx-auto animate-in fade-in duration-300">
      <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-4">
        <div>
          <h2 className="text-3xl font-black text-[#0F172A] tracking-tighter uppercase">Accounts — Payout Verification</h2>
          <p className="text-[#64748B] font-bold uppercase tracking-widest text-[10px] mt-1">
            Verify Every Money-Out Before Payment · Expenses · Travel Advances · Salary Advances
          </p>
        </div>
        <button type="button" onClick={load} className="p-2 text-slate-400 hover:text-blue-600 self-end" title="Refresh" aria-label="Refresh">
          <RefreshCw size={16} className={cn(loading && 'animate-spin')} />
        </button>
      </div>

      <div className="flex items-center gap-2 flex-wrap">
        <TabBtn id="expenses" label="Expenses" icon={Receipt} n={counts.expenses} />
        <TabBtn id="travel" label="Travel Advances" icon={Plane} n={counts.travel} />
        <TabBtn id="advances" label="Salary Advances" icon={Wallet} n={counts.advances} />
      </div>

      <Card className="p-0 border-slate-200 overflow-hidden bg-white">
        {tab === 'expenses' && (
          expenses.length === 0 ? <Empty what="expense claims" /> : (
            <table className="w-full text-left">
              <thead className="bg-white border-b border-slate-100"><tr>
                <th className="px-6 py-3 text-[9px] font-black text-slate-400 uppercase tracking-widest">Claim</th>
                <th className="px-6 py-3 text-[9px] font-black text-slate-400 uppercase tracking-widest">Amount</th>
                <th className="px-6 py-3 text-[9px] font-black text-slate-400 uppercase tracking-widest">Status</th>
                <th className="px-6 py-3 text-right text-[9px] font-black text-slate-400 uppercase tracking-widest">Action</th>
              </tr></thead>
              <tbody className="divide-y divide-slate-50">
                {expenses.map(c => (
                  <tr key={c.id} className="hover:bg-slate-50/60">
                    <td className="px-6 py-3 text-sm font-black text-[#0F172A]">{c.title}</td>
                    <td className="px-6 py-3 text-sm font-bold tabular-nums">{rupees(c.total_amount_paise)}</td>
                    <td className="px-6 py-3"><Badge variant="warning" className="text-[8px] uppercase">{c.status}</Badge></td>
                    <td className="px-6 py-3 text-right">
                      <Button onClick={() => act(`e${c.id}`, () => client.post(ENDPOINTS.EXPENSES.CLAIM_ACCOUNTS_VERIFY(c.id)), 'Verified for payout')} isLoading={busy === `e${c.id}`}
                        className="h-9 bg-emerald-600 hover:bg-emerald-700 text-white font-black uppercase text-[10px] tracking-widest">
                        <ShieldCheck size={14} className="mr-1.5" /> Verify for Payout
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )
        )}
        {tab === 'travel' && (
          travel.length === 0 ? <Empty what="travel advances" /> : (
            <table className="w-full text-left">
              <thead className="bg-white border-b border-slate-100"><tr>
                <th className="px-6 py-3 text-[9px] font-black text-slate-400 uppercase tracking-widest">Purpose</th>
                <th className="px-6 py-3 text-[9px] font-black text-slate-400 uppercase tracking-widest">Advance</th>
                <th className="px-6 py-3 text-right text-[9px] font-black text-slate-400 uppercase tracking-widest">Action</th>
              </tr></thead>
              <tbody className="divide-y divide-slate-50">
                {travel.map(t => (
                  <tr key={t.id} className="hover:bg-slate-50/60">
                    <td className="px-6 py-3 text-sm font-black text-[#0F172A]">{t.purpose} <span className="text-slate-400 font-bold text-xs">({t.from_city}→{t.to_city})</span></td>
                    <td className="px-6 py-3 text-sm font-bold tabular-nums">{rupees(t.advance_requested_paise)}</td>
                    <td className="px-6 py-3 text-right">
                      <Button onClick={() => act(`t${t.id}`, () => client.post(ENDPOINTS.EXPENSES.TRAVEL_ACCOUNTS_VERIFY(t.id)), 'Advance marked paid')} isLoading={busy === `t${t.id}`}
                        className="h-9 bg-emerald-600 hover:bg-emerald-700 text-white font-black uppercase text-[10px] tracking-widest">
                        <ShieldCheck size={14} className="mr-1.5" /> Verify Payout
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )
        )}
        {tab === 'advances' && (
          advances.length === 0 ? <Empty what="salary advances" /> : (
            <table className="w-full text-left">
              <thead className="bg-white border-b border-slate-100"><tr>
                <th className="px-6 py-3 text-[9px] font-black text-slate-400 uppercase tracking-widest">Employee</th>
                <th className="px-6 py-3 text-[9px] font-black text-slate-400 uppercase tracking-widest">Amount</th>
                <th className="px-6 py-3 text-right text-[9px] font-black text-slate-400 uppercase tracking-widest">Action</th>
              </tr></thead>
              <tbody className="divide-y divide-slate-50">
                {advances.map(a => (
                  <tr key={a.id} className="hover:bg-slate-50/60">
                    <td className="px-6 py-3 text-sm font-black text-[#0F172A]">{a.employee_name || `#${a.employee_id}`}</td>
                    <td className="px-6 py-3 text-sm font-bold tabular-nums">{rupeesF(a.amount)}</td>
                    <td className="px-6 py-3 text-right">
                      <Button onClick={() => act(`a${a.id}`, () => client.post(ENDPOINTS.HR.ADVANCE_ACCOUNTS_VERIFY(a.id)), 'Advance disbursement verified')} isLoading={busy === `a${a.id}`}
                        className="h-9 bg-emerald-600 hover:bg-emerald-700 text-white font-black uppercase text-[10px] tracking-widest">
                        <ShieldCheck size={14} className="mr-1.5" /> Verify Disbursement
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )
        )}
      </Card>
      <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">
        Verifying unlocks the next step — expenses go to the Finance reimburse queue; advances become active (recoverable in payroll); travel advances are marked paid.
      </p>
    </div>
  );
};
