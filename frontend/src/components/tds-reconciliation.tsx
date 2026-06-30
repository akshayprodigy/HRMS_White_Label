/**
 * FY-wide TDS reconciliation — the headline Q4 catch-up report.
 * Projected annual tax vs YTD-deducted vs last-month deducted, per
 * employee, with under/over-deduction status.
 */
import React, { useState } from 'react';
import {
  Play, AlertTriangle, CheckCircle2, RefreshCw, Calculator, TrendingUp, TrendingDown,
} from 'lucide-react';
import { Card, Badge, Button, cn } from './ui-elements';
import { toast } from 'sonner@2.0.3';
import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';
import { Input } from './ui/input';

interface Row {
  user_id: number;
  employee_code: string | null;
  name: string | null;
  projected_annual_tax: number;
  ytd_tds: number;
  months_remaining: number;
  required_monthly: number;
  last_month_tds: number;
  catch_up_amount: number;
  status: 'under' | 'over' | 'ok';
}
interface Report {
  fy: string; as_of: string;
  rows: Row[];
  total_under: number; total_over: number; total_ok: number;
}

const errMsg = (e: any, fb: string) => {
  const d = e?.response?.data?.detail;
  if (typeof d === 'string') return d;
  return e?.message || fb;
};

export const TDSReconciliationView: React.FC = () => {
  const [fy, setFy] = useState('24-25');
  const [report, setReport] = useState<Report | null>(null);
  const [loading, setLoading] = useState(false);
  const [statusFilter, setStatusFilter] = useState<string>('all');

  const run = async () => {
    setLoading(true); setReport(null);
    try {
      const r = await client.get(ENDPOINTS.TAX.RECONCILIATION(fy));
      setReport(r.data);
    } catch (e: any) { toast.error(errMsg(e, 'Failed')); }
    finally { setLoading(false); }
  };

  const filtered = report?.rows.filter(r =>
    statusFilter === 'all' ? true : r.status === statusFilter,
  ) || [];

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Calculator className="w-6 h-6 text-blue-600" /> TDS Reconciliation
        </h1>
        <p className="text-sm text-slate-500 mt-1">
          Projected annual tax vs YTD-deducted vs last-month TDS per employee.
          Surfaces the Q4 catch-up gap.
        </p>
      </div>

      <Card className="p-4">
        <div className="flex items-end gap-3">
          <div>
            <label className="text-xs font-semibold text-slate-600">FY</label>
            <Input value={fy} onChange={e => setFy(e.target.value)} className="w-28" />
          </div>
          <Button onClick={run} isLoading={loading}>
            <Play className="w-4 h-4 mr-2" /> Run reconciliation
          </Button>
          {report && (
            <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)}
              className="border border-slate-200 rounded-md h-9 px-2 text-sm ml-auto">
              <option value="all">All ({report.rows.length})</option>
              <option value="under">Under-deducted ({report.total_under})</option>
              <option value="over">Over-deducted ({report.total_over})</option>
              <option value="ok">OK ({report.total_ok})</option>
            </select>
          )}
        </div>

        {report && (
          <>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-3 my-4">
              <div className="p-3 bg-slate-50 rounded-lg">
                <div className="text-[10px] uppercase text-slate-500">FY / As-of</div>
                <div className="text-sm font-semibold mt-1">FY {report.fy} · {report.as_of}</div>
              </div>
              <div className="p-3 bg-red-50 rounded-lg">
                <div className="text-[10px] uppercase text-red-700 flex items-center gap-1">
                  <TrendingUp className="w-3 h-3" /> Under-deducted
                </div>
                <div className="text-xl font-bold mt-1 text-red-700">{report.total_under}</div>
              </div>
              <div className="p-3 bg-blue-50 rounded-lg">
                <div className="text-[10px] uppercase text-blue-700 flex items-center gap-1">
                  <TrendingDown className="w-3 h-3" /> Over-deducted
                </div>
                <div className="text-xl font-bold mt-1 text-blue-700">{report.total_over}</div>
              </div>
              <div className="p-3 bg-green-50 rounded-lg">
                <div className="text-[10px] uppercase text-green-700 flex items-center gap-1">
                  <CheckCircle2 className="w-3 h-3" /> OK
                </div>
                <div className="text-xl font-bold mt-1 text-green-700">{report.total_ok}</div>
              </div>
            </div>

            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead className="text-left text-xs uppercase text-slate-500 border-b">
                  <tr>
                    <th className="p-3">Employee</th>
                    <th className="p-3">Projected annual tax</th>
                    <th className="p-3">YTD TDS</th>
                    <th className="p-3">Months left</th>
                    <th className="p-3">Required / mo</th>
                    <th className="p-3">Last-month TDS</th>
                    <th className="p-3">Catch-up</th>
                    <th className="p-3">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map(r => {
                    const v = r.status === 'ok' ? 'success'
                      : r.status === 'under' ? 'error' : 'info';
                    return (
                      <tr key={r.user_id} className="border-b">
                        <td className="p-3">
                          <div className="font-medium">{r.name || `#${r.user_id}`}</div>
                          <div className="text-[10px] text-slate-400">{r.employee_code}</div>
                        </td>
                        <td className="p-3 font-mono">₹{r.projected_annual_tax.toLocaleString('en-IN')}</td>
                        <td className="p-3 font-mono">₹{r.ytd_tds.toLocaleString('en-IN')}</td>
                        <td className="p-3 text-xs">{r.months_remaining}</td>
                        <td className="p-3 font-mono">₹{r.required_monthly.toLocaleString('en-IN')}</td>
                        <td className="p-3 font-mono">₹{r.last_month_tds.toLocaleString('en-IN')}</td>
                        <td className={cn('p-3 font-mono font-bold',
                          r.catch_up_amount > 0 ? 'text-red-700' : r.catch_up_amount < 0 ? 'text-blue-700' : '')}>
                          {r.catch_up_amount > 0 ? '+' : ''}₹{r.catch_up_amount.toLocaleString('en-IN')}
                        </td>
                        <td className="p-3">
                          <Badge variant={v as any}>{r.status}</Badge>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </>
        )}

        {!report && !loading && (
          <div className="py-12 text-center text-slate-500">
            Pick an FY and click run.
          </div>
        )}
      </Card>
    </div>
  );
};
