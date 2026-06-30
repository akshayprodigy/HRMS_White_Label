/**
 * Compliance due-date dashboard: one card per (payroll_run, stream[,
 * state]) for the last N months — flags overdue + due-within-7-days
 * filings.
 */
import React, { useEffect, useState } from 'react';
import {
  Calendar, AlertTriangle, Clock, CheckCircle2, RefreshCw, ShieldCheck,
} from 'lucide-react';
import { Card, Badge, Button, cn } from './ui-elements';
import { toast } from 'sonner@2.0.3';
import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';

interface ComplianceCard {
  stream: 'epf' | 'esic' | 'pt';
  state: string | null;
  payroll_run_id: number;
  payroll_period: string;
  due_date: string;
  days_to_due: number;
  status: string;
  filing_id: number | null;
  total_amount: number | null;
  employee_count: number | null;
}

interface Dashboard {
  as_of: string;
  cards: ComplianceCard[];
  overdue: number;
  due_within_7_days: number;
}

const errMsg = (e: any, f: string) => {
  const d = e?.response?.data?.detail;
  if (typeof d === 'string') return d;
  return e?.message || f;
};

const streamChip = (s: string) => {
  const cls = s === 'epf' ? 'bg-blue-100 text-blue-700'
    : s === 'esic' ? 'bg-purple-100 text-purple-700'
    : 'bg-amber-100 text-amber-700';
  return <span className={cn('px-2 py-0.5 rounded text-[10px] font-bold uppercase', cls)}>{s}</span>;
};

const statusChip = (s: string) => {
  const v = s === 'paid' || s === 'acknowledged' ? 'success'
    : s === 'rejected' ? 'error'
    : s === 'submitted' ? 'info'
    : 'warning';
  return <Badge variant={v as any}>{s}</Badge>;
};

const cardTone = (c: ComplianceCard) => {
  if (['paid', 'acknowledged'].includes(c.status)) return 'border-green-200 bg-green-50/30';
  if (c.days_to_due < 0) return 'border-red-300 bg-red-50';
  if (c.days_to_due <= 7) return 'border-amber-300 bg-amber-50';
  return 'border-slate-200 bg-white';
};

export const ComplianceDashboardView: React.FC = () => {
  const [dash, setDash] = useState<Dashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [monthsBack, setMonthsBack] = useState(6);

  const fetch = async () => {
    setLoading(true);
    try {
      const r = await client.get(ENDPOINTS.STATUTORY.DASHBOARD, {
        params: { months_back: monthsBack },
      });
      setDash(r.data);
    } catch (e: any) { toast.error(errMsg(e, 'Failed to load')); }
    finally { setLoading(false); }
  };

  useEffect(() => { fetch(); /* eslint-disable-line */ }, [monthsBack]);

  const total = dash?.cards.length || 0;
  const filed = (dash?.cards || []).filter(c =>
    ['paid', 'acknowledged'].includes(c.status)
  ).length;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <ShieldCheck className="w-6 h-6 text-blue-600" /> Compliance Due-Date Dashboard
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            One card per filing obligation across recent payroll months. Overdue + due-soon are flagged.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <select value={monthsBack}
            onChange={e => setMonthsBack(Number(e.target.value))}
            className="border border-slate-200 rounded-md h-9 px-2 text-sm">
            <option value={3}>Last 3 months</option>
            <option value={6}>Last 6 months</option>
            <option value={12}>Last 12 months</option>
          </select>
          <Button variant="outline" onClick={fetch}><RefreshCw className="w-4 h-4" /></Button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
        <Card className="p-4">
          <div className="text-xs uppercase text-slate-500">Filings tracked</div>
          <div className="text-2xl font-bold mt-1">{total}</div>
          <div className="text-[10px] text-slate-500 mt-1">As of {dash?.as_of || '—'}</div>
        </Card>
        <Card className={cn('p-4', (dash?.overdue || 0) > 0 ? 'bg-red-50 border-red-200' : '')}>
          <div className="text-xs uppercase text-red-600 flex items-center gap-1">
            <AlertTriangle className="w-3 h-3" /> Overdue
          </div>
          <div className="text-2xl font-bold mt-1 text-red-700">{dash?.overdue ?? '—'}</div>
        </Card>
        <Card className={cn('p-4', (dash?.due_within_7_days || 0) > 0 ? 'bg-amber-50 border-amber-200' : '')}>
          <div className="text-xs uppercase text-amber-700 flex items-center gap-1">
            <Clock className="w-3 h-3" /> Due ≤7d
          </div>
          <div className="text-2xl font-bold mt-1 text-amber-700">{dash?.due_within_7_days ?? '—'}</div>
        </Card>
        <Card className="p-4 bg-green-50 border-green-200">
          <div className="text-xs uppercase text-green-700 flex items-center gap-1">
            <CheckCircle2 className="w-3 h-3" /> Filed
          </div>
          <div className="text-2xl font-bold mt-1 text-green-700">{filed}</div>
        </Card>
      </div>

      {loading ? <div className="py-8 text-center text-slate-500">Loading…</div>
        : !dash || total === 0 ? (
          <Card className="p-12 text-center text-slate-500">
            No finalized payroll runs in this window — generate a payroll run + close it to populate filings.
          </Card>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {dash.cards.map((c, i) => (
              <div key={i} className={cn('border rounded-lg p-4', cardTone(c))}>
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    {streamChip(c.stream)}
                    {c.state && <span className="text-xs text-slate-600">· {c.state}</span>}
                  </div>
                  {statusChip(c.status)}
                </div>
                <div className="text-xs text-slate-500 flex items-center gap-1">
                  <Calendar className="w-3 h-3" /> Period {c.payroll_period}
                </div>
                <div className="mt-1 text-sm font-semibold">Due {c.due_date}</div>
                <div className={cn('text-xs mt-1',
                  c.days_to_due < 0 ? 'text-red-700 font-bold'
                    : c.days_to_due <= 7 ? 'text-amber-700 font-bold'
                    : 'text-slate-500')}>
                  {c.days_to_due < 0 ? `${Math.abs(c.days_to_due)} days overdue`
                    : c.days_to_due === 0 ? 'Due today'
                    : `${c.days_to_due} days left`}
                </div>
                {c.total_amount != null && (
                  <div className="mt-2 text-sm font-mono">₹{c.total_amount.toLocaleString('en-IN')}</div>
                )}
                {c.employee_count != null && (
                  <div className="text-[10px] text-slate-500">{c.employee_count} employees</div>
                )}
              </div>
            ))}
          </div>
        )}
    </div>
  );
};
