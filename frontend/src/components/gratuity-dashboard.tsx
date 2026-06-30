/**
 * Gratuity company-liability dashboard + per-employee accrual + exit
 * snapshot trigger.
 */
import React, { useEffect, useMemo, useState } from 'react';
import {
  Award, AlertTriangle, RefreshCw, Search,
} from 'lucide-react';
import { Card, Badge, Button, cn } from './ui-elements';
import { toast } from 'sonner@2.0.3';
import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';
import { Input } from './ui/input';

interface Row {
  employee_id: number;
  employee_full_name: string | null;
  employee_code: string | null;
  last_basic_da: number;
  days_basis: number;
  raw_years: number;
  rounded_years: number;
  is_eligible: boolean;
  computed_amount: number;
  capped_amount: number;
  cap_applied: boolean;
  eligibility_years_used: number;
  note: string;
  as_of: string;
}

interface Report {
  as_of: string;
  total_employees: number;
  eligible_employees: number;
  total_accruing_liability: number;
  payable_if_all_exit_today: number;
  accruing_under_5_years: number;
  rows: Row[];
}

const errMsg = (e: any, fb: string) => {
  const d = e?.response?.data?.detail;
  if (typeof d === 'string') return d;
  return e?.message || fb;
};

export const GratuityDashboardView: React.FC = () => {
  const [report, setReport] = useState<Report | null>(null);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<'all' | 'eligible' | 'accruing'>('all');
  const [search, setSearch] = useState('');

  const fetch = async () => {
    setLoading(true);
    try {
      const r = await client.get(ENDPOINTS.TAX.GRATUITY_LIABILITY);
      setReport(r.data);
    } catch (e: any) { toast.error(errMsg(e, 'Failed')); }
    finally { setLoading(false); }
  };
  useEffect(() => { fetch(); }, []);

  const filtered = useMemo(() => {
    if (!report) return [];
    const q = search.trim().toLowerCase();
    return report.rows.filter(r => {
      if (filter === 'eligible' && !r.is_eligible) return false;
      if (filter === 'accruing' && r.is_eligible) return false;
      if (q) {
        return (r.employee_full_name || '').toLowerCase().includes(q)
          || (r.employee_code || '').toLowerCase().includes(q);
      }
      return true;
    });
  }, [report, search, filter]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Award className="w-6 h-6 text-blue-600" /> Gratuity Liability
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Per-employee accrual + company-wide liability for finance.
            Formula: (Last Basic + DA / days_basis) × 15 × years.
            Eligibility: 5 full years; ≥6 months rounds up for formula.
          </p>
        </div>
        <Button variant="outline" onClick={fetch}><RefreshCw className="w-4 h-4" /></Button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
        <Card className="p-4">
          <div className="text-[10px] uppercase text-slate-500">Total employees</div>
          <div className="text-xl font-bold mt-1">{report?.total_employees ?? '—'}</div>
        </Card>
        <Card className="p-4 bg-green-50 border-green-200">
          <div className="text-[10px] uppercase text-green-700">Eligible (≥5 yrs)</div>
          <div className="text-xl font-bold mt-1 text-green-700">{report?.eligible_employees ?? '—'}</div>
        </Card>
        <Card className="p-4 bg-red-50 border-red-200">
          <div className="text-[10px] uppercase text-red-700 flex items-center gap-1">
            <AlertTriangle className="w-3 h-3" /> Payable if all exit today
          </div>
          <div className="text-xl font-bold mt-1 text-red-700 font-mono">
            ₹{(report?.payable_if_all_exit_today || 0).toLocaleString('en-IN')}
          </div>
        </Card>
        <Card className="p-4">
          <div className="text-[10px] uppercase text-slate-500">Accruing (under 5 yrs)</div>
          <div className="text-xl font-bold mt-1 font-mono text-slate-700">
            ₹{(report?.accruing_under_5_years || 0).toLocaleString('en-IN')}
          </div>
          <div className="text-[10px] text-slate-500 mt-1">
            Total accruing liability: ₹{(report?.total_accruing_liability || 0).toLocaleString('en-IN')}
          </div>
        </Card>
      </div>

      <Card className="p-4">
        <div className="flex items-center gap-3 mb-3">
          <div className="flex gap-2">
            {(['all', 'eligible', 'accruing'] as const).map(f => (
              <button key={f} onClick={() => setFilter(f)}
                className={cn(
                  'px-3 py-1.5 text-sm rounded-md font-medium',
                  filter === f ? 'bg-blue-600 text-white' : 'bg-slate-100 text-slate-700',
                )}>
                {f === 'all' ? 'All' : f === 'eligible' ? 'Eligible' : 'Under 5 yrs'}
              </button>
            ))}
          </div>
          <div className="relative flex-1 max-w-sm ml-auto">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <Input placeholder="Search…" value={search}
              onChange={e => setSearch(e.target.value)} className="pl-9" />
          </div>
        </div>

        {loading ? <div className="py-8 text-center text-slate-500">Loading…</div>
          : (
            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead className="text-left text-xs uppercase text-slate-500 border-b">
                  <tr>
                    <th className="p-3">Employee</th>
                    <th className="p-3">Last Basic+DA</th>
                    <th className="p-3">Tenure</th>
                    <th className="p-3">Formula years</th>
                    <th className="p-3">Computed</th>
                    <th className="p-3">Payable today</th>
                    <th className="p-3">Eligibility</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map(r => (
                    <tr key={r.employee_id} className="border-b hover:bg-slate-50">
                      <td className="p-3">
                        <div className="font-medium">{r.employee_full_name || `#${r.employee_id}`}</div>
                        <div className="text-[10px] text-slate-400">{r.employee_code}</div>
                      </td>
                      <td className="p-3 font-mono">₹{r.last_basic_da.toLocaleString('en-IN')}/mo</td>
                      <td className="p-3 text-xs">{r.raw_years.toFixed(2)} yrs</td>
                      <td className="p-3 text-xs">{r.rounded_years}</td>
                      <td className="p-3 font-mono">
                        ₹{r.computed_amount.toLocaleString('en-IN')}
                        {r.cap_applied && (
                          <Badge variant="warning" className="ml-1">capped</Badge>
                        )}
                      </td>
                      <td className={cn('p-3 font-mono font-bold',
                        r.is_eligible ? 'text-green-700' : 'text-slate-400')}>
                        ₹{r.capped_amount.toLocaleString('en-IN')}
                      </td>
                      <td className="p-3">
                        {r.is_eligible
                          ? <Badge variant="success">Eligible</Badge>
                          : <Badge variant="warning">Accruing</Badge>}
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
