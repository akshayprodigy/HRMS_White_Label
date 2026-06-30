/**
 * Statutory reconciliation: compare what payroll actually deducted vs.
 * what the active StatutoryConfig says it should have been. Drift
 * within ₹0.01 is hidden as rounding noise.
 */
import React, { useEffect, useState } from 'react';
import {
  Play, AlertTriangle, CheckCircle2, RefreshCw, GitCompare,
} from 'lucide-react';
import { Card, Button, Badge, cn } from './ui-elements';
import { toast } from 'sonner@2.0.3';
import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';

interface Drift {
  user_id: number;
  employee_code: string | null;
  name: string | null;
  stream: string;
  expected: number;
  actual: number;
  diff: number;
  note: string;
}

interface Report {
  payroll_run_id: number;
  config_id: number | null;
  config_effective_from: string | null;
  employees_checked: number;
  drift_count: number;
  findings: Drift[];
}

interface PayrollRun {
  id: number; month: number; year: number; status: string;
}

const errMsg = (e: any, f: string) => {
  const d = e?.response?.data?.detail;
  if (typeof d === 'string') return d;
  if (Array.isArray(d)) return d.map((x: any) => x?.msg || JSON.stringify(x)).join('; ');
  return e?.message || f;
};

const streamLabel = (s: string) => ({
  epf_employee: 'EPF · Employee',
  epf_employer_total: 'EPF · Employer (total)',
  esic_employee: 'ESIC · Employee',
  esic_employer: 'ESIC · Employer',
  pt: 'PT',
})[s] || s;

const streamCls = (s: string) => {
  if (s.startsWith('epf')) return 'bg-blue-100 text-blue-700';
  if (s.startsWith('esic')) return 'bg-purple-100 text-purple-700';
  return 'bg-amber-100 text-amber-700';
};

export const StatutoryReconciliationView: React.FC = () => {
  const [runs, setRuns] = useState<PayrollRun[]>([]);
  const [selectedRun, setSelectedRun] = useState<number | ''>('');
  const [report, setReport] = useState<Report | null>(null);
  const [loading, setLoading] = useState(false);

  const fetchRuns = async () => {
    try {
      const r = await client.get('/hr/payroll/dashboard');
      const dash = r.data || {};
      const allRuns: PayrollRun[] = [
        ...(dash.active_runs || []),
        ...(dash.last_finalized_run ? [dash.last_finalized_run] : []),
      ];
      setRuns(allRuns.filter((x: any) =>
        ['finalized', 'published'].includes((x.status || '').toLowerCase())
      ));
    } catch (e: any) { toast.error(errMsg(e, 'Failed to load runs')); }
  };

  useEffect(() => { fetchRuns(); }, []);

  const runReconcile = async () => {
    if (!selectedRun) { toast.error('Pick a payroll run'); return; }
    setLoading(true); setReport(null);
    try {
      const r = await client.get(ENDPOINTS.STATUTORY.RECONCILIATION(Number(selectedRun)));
      setReport(r.data);
      if (r.data.drift_count === 0) toast.success('No drift detected');
    } catch (e: any) { toast.error(errMsg(e, 'Reconciliation failed')); }
    finally { setLoading(false); }
  };

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <GitCompare className="w-6 h-6 text-blue-600" /> Statutory Reconciliation
        </h1>
        <p className="text-sm text-slate-500 mt-1">
          Drift report: payroll-deducted vs. config-expected for PF / ESIC / PT. Rounding noise (≤₹0.01) is suppressed.
        </p>
      </div>

      <Card className="p-4">
        <div className="flex items-end gap-3">
          <div className="flex-1 max-w-md">
            <label className="text-xs font-semibold text-slate-600">Payroll run</label>
            <select value={selectedRun}
              onChange={e => setSelectedRun(e.target.value ? Number(e.target.value) : '')}
              className="w-full border border-slate-200 rounded-md h-9 px-2 text-sm">
              <option value="">— Select —</option>
              {runs.map(r =>
                <option key={r.id} value={r.id}>#{r.id} {String(r.month).padStart(2, '0')}/{r.year}</option>
              )}
            </select>
          </div>
          <Button onClick={runReconcile} isLoading={loading}>
            <Play className="w-4 h-4 mr-2" /> Run reconciliation
          </Button>
          <Button variant="outline" onClick={fetchRuns}><RefreshCw className="w-4 h-4" /></Button>
        </div>

        {report && (
          <div className="mt-4">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-4">
              <div className="p-3 bg-slate-50 rounded-lg">
                <div className="text-[10px] uppercase text-slate-500">Run / Config</div>
                <div className="text-sm font-semibold mt-1">
                  Run #{report.payroll_run_id} · Config #{report.config_id || '—'}
                </div>
                <div className="text-[10px] text-slate-500 mt-1">
                  Effective from {report.config_effective_from || '—'}
                </div>
              </div>
              <div className="p-3 bg-blue-50 rounded-lg">
                <div className="text-[10px] uppercase text-blue-600">Employees checked</div>
                <div className="text-xl font-bold mt-1">{report.employees_checked}</div>
              </div>
              <div className={cn(
                'p-3 rounded-lg',
                report.drift_count === 0 ? 'bg-green-50' : 'bg-red-50',
              )}>
                <div className="text-[10px] uppercase">
                  {report.drift_count === 0 ? 'No drift' : 'Drift findings'}
                </div>
                <div className={cn(
                  'text-xl font-bold mt-1 flex items-center gap-2',
                  report.drift_count === 0 ? 'text-green-700' : 'text-red-700',
                )}>
                  {report.drift_count === 0 ? <CheckCircle2 className="w-5 h-5" /> : <AlertTriangle className="w-5 h-5" />}
                  {report.drift_count}
                </div>
              </div>
            </div>

            {report.drift_count > 0 ? (
              <div className="overflow-x-auto">
                <table className="min-w-full text-sm">
                  <thead className="text-left text-xs uppercase text-slate-500 border-b">
                    <tr>
                      <th className="p-3">Employee</th>
                      <th className="p-3">Stream</th>
                      <th className="p-3">Expected</th>
                      <th className="p-3">Actual</th>
                      <th className="p-3">Diff</th>
                      <th className="p-3">Note</th>
                    </tr>
                  </thead>
                  <tbody>
                    {report.findings.map((f, i) => (
                      <tr key={i} className="border-b">
                        <td className="p-3">
                          <div className="font-medium">{f.name || `#${f.user_id}`}</div>
                          <div className="text-[10px] text-slate-400">{f.employee_code || ''}</div>
                        </td>
                        <td className="p-3">
                          <span className={cn('px-2 py-0.5 rounded text-[10px] font-bold uppercase', streamCls(f.stream))}>
                            {streamLabel(f.stream)}
                          </span>
                        </td>
                        <td className="p-3 font-mono">₹{f.expected.toFixed(2)}</td>
                        <td className="p-3 font-mono">₹{f.actual.toFixed(2)}</td>
                        <td className={cn('p-3 font-mono font-bold',
                          f.diff > 0 ? 'text-red-700' : 'text-blue-700')}>
                          {f.diff > 0 ? '+' : ''}₹{f.diff.toFixed(2)}
                        </td>
                        <td className="p-3 text-xs text-slate-600">{f.note || '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="py-8 text-center text-green-700">
                <CheckCircle2 className="w-12 h-12 mx-auto mb-2" />
                <div className="text-sm font-semibold">All deductions match config — no drift.</div>
              </div>
            )}
          </div>
        )}
      </Card>
    </div>
  );
};
