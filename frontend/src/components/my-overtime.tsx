import React, { useEffect, useMemo, useState } from 'react';
import { Calendar, Clock, Moon } from 'lucide-react';
import { Card, Badge } from './ui-elements';
import { toast } from 'sonner';
import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';
import { Input } from './ui/input';

interface MyOTEntry {
  id: number; work_date: string;
  ot_minutes: number; ot_amount: number;
  multiplier_used: number; day_type: string;
  status: 'pending' | 'approved' | 'rejected' | 'auto_approved';
  payroll_run_id: number | null;
  rejection_reason: string | null;
}
interface MyNightEntry {
  id: number; work_date: string;
  night_minutes: number; amount: number;
  payout_model_used: string;
  payroll_run_id: number | null;
}

const fmtMin = (m: number) => {
  const h = Math.floor(m / 60); const r = m % 60;
  return r ? `${h}h ${r}m` : `${h}h`;
};

const errMsg = (err: any, fallback: string): string => {
  const detail = err?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  return err?.message || fallback;
};

const today = () => new Date().toISOString().slice(0, 10);
const monthStart = () => {
  const d = new Date(); d.setDate(1);
  return d.toISOString().slice(0, 10);
};

export const MyOvertimeView: React.FC = () => {
  const [ot, setOt] = useState<MyOTEntry[]>([]);
  const [night, setNight] = useState<MyNightEntry[]>([]);
  const [start, setStart] = useState(monthStart());
  const [end, setEnd] = useState(today());
  const [loading, setLoading] = useState(true);

  const fetchData = async () => {
    setLoading(true);
    try {
      const [o, n] = await Promise.all([
        client.get(ENDPOINTS.OVERTIME.MY_ENTRIES, { params: { start, end } }),
        client.get(ENDPOINTS.OVERTIME.MY_NIGHT_ENTRIES, { params: { start, end } }),
      ]);
      setOt(o.data || []); setNight(n.data || []);
    } catch (e: any) {
      toast.error(errMsg(e, 'Failed to load'));
    } finally { setLoading(false); }
  };

  useEffect(() => { fetchData(); /* eslint-disable-line */ }, [start, end]);

  const totals = useMemo(() => ({
    ot_min: ot.reduce((s, e) => s + e.ot_minutes, 0),
    ot_amt: ot.reduce((s, e) => s + (
      e.status === 'approved' || e.status === 'auto_approved' ? e.ot_amount : 0
    ), 0),
    night_min: night.reduce((s, e) => s + e.night_minutes, 0),
    night_amt: night.reduce((s, e) => s + e.amount, 0),
    pending_ot: ot.filter(e => e.status === 'pending').reduce((s, e) => s + e.ot_amount, 0),
  }), [ot, night]);

  const statusChip = (s: string) => {
    const v = s === 'approved' || s === 'auto_approved' ? 'success'
      : s === 'rejected' ? 'error' : 'info';
    return <Badge variant={v as any}>{s.replace('_', ' ')}</Badge>;
  };

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold">My Overtime &amp; Night Allowance</h1>
        <p className="text-sm text-slate-500 mt-1">
          OT auto-computed from your attendance + assigned shift. Approved OT flows into your next payslip.
        </p>
      </div>

      <div className="flex items-end gap-3">
        <div>
          <label className="text-xs font-semibold text-slate-600 flex items-center gap-1">
            <Calendar className="w-3 h-3" /> Start
          </label>
          <Input type="date" value={start} onChange={e => setStart(e.target.value)} />
        </div>
        <div>
          <label className="text-xs font-semibold text-slate-600">End</label>
          <Input type="date" value={end} onChange={e => setEnd(e.target.value)} />
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
        <Card className="p-4">
          <div className="text-xs uppercase text-slate-500 flex items-center gap-1">
            <Clock className="w-3 h-3" /> Total OT
          </div>
          <div className="text-xl font-bold mt-1">{fmtMin(totals.ot_min)}</div>
        </Card>
        <Card className="p-4">
          <div className="text-xs uppercase text-slate-500">Approved OT amount</div>
          <div className="text-xl font-bold mt-1 text-green-600">₹{totals.ot_amt.toFixed(2)}</div>
        </Card>
        <Card className="p-4">
          <div className="text-xs uppercase text-slate-500">Pending OT amount</div>
          <div className="text-xl font-bold mt-1 text-amber-600">₹{totals.pending_ot.toFixed(2)}</div>
        </Card>
        <Card className="p-4">
          <div className="text-xs uppercase text-slate-500 flex items-center gap-1">
            <Moon className="w-3 h-3" /> Night allowance
          </div>
          <div className="text-xl font-bold mt-1 text-indigo-600">
            {fmtMin(totals.night_min)} · ₹{totals.night_amt.toFixed(2)}
          </div>
        </Card>
      </div>

      <Card className="p-4">
        <h2 className="text-sm font-semibold mb-3">Overtime entries</h2>
        {loading ? <div className="py-6 text-center text-slate-500">Loading…</div>
          : ot.length === 0 ? <div className="py-8 text-center text-slate-500">No OT in this window.</div>
            : (
              <div className="overflow-x-auto">
                <table className="min-w-full text-sm">
                  <thead className="text-left text-xs uppercase text-slate-500 border-b">
                    <tr>
                      <th className="p-2">Date</th>
                      <th className="p-2">Day</th>
                      <th className="p-2">OT</th>
                      <th className="p-2">Mult</th>
                      <th className="p-2">Amount</th>
                      <th className="p-2">Status</th>
                      <th className="p-2">In payroll</th>
                    </tr>
                  </thead>
                  <tbody>
                    {ot.map(e => (
                      <tr key={e.id} className="border-b">
                        <td className="p-2">{e.work_date}</td>
                        <td className="p-2 text-xs">{e.day_type}</td>
                        <td className="p-2 font-mono">{fmtMin(e.ot_minutes)}</td>
                        <td className="p-2">{e.multiplier_used}×</td>
                        <td className="p-2 font-mono">₹{e.ot_amount.toFixed(2)}</td>
                        <td className="p-2">{statusChip(e.status)}
                          {e.rejection_reason && (
                            <div className="text-[10px] text-red-600 mt-0.5">
                              {e.rejection_reason}
                            </div>
                          )}
                        </td>
                        <td className="p-2 text-xs">
                          {e.payroll_run_id
                            ? <Badge variant="info">#{e.payroll_run_id}</Badge>
                            : '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
      </Card>

      <Card className="p-4">
        <h2 className="text-sm font-semibold mb-3">Night-shift allowance</h2>
        {night.length === 0 ? (
          <div className="py-8 text-center text-slate-500">No night allowance entries.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead className="text-left text-xs uppercase text-slate-500 border-b">
                <tr>
                  <th className="p-2">Date</th>
                  <th className="p-2">Night minutes</th>
                  <th className="p-2">Model</th>
                  <th className="p-2">Amount</th>
                  <th className="p-2">In payroll</th>
                </tr>
              </thead>
              <tbody>
                {night.map(e => (
                  <tr key={e.id} className="border-b">
                    <td className="p-2">{e.work_date}</td>
                    <td className="p-2 font-mono">{fmtMin(e.night_minutes)}</td>
                    <td className="p-2 text-xs">{e.payout_model_used}</td>
                    <td className="p-2 font-mono">₹{e.amount.toFixed(2)}</td>
                    <td className="p-2 text-xs">
                      {e.payroll_run_id ? <Badge variant="info">#{e.payroll_run_id}</Badge> : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
};
