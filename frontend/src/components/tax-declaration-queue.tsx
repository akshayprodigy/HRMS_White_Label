/**
 * HR tax-declaration verification queue.
 */
import React, { useEffect, useState } from 'react';
import { Check, X, RefreshCw, Filter } from 'lucide-react';
import { Card, Button, Badge, cn } from './ui-elements';
import { toast } from 'sonner';
import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';
import { Dialog, DialogContent, DialogTitle, DialogFooter } from './ui/dialog';
import { Input } from './ui/input';

interface Decl {
  id: number; employee_id: number;
  employee_full_name: string | null; employee_code: string | null;
  fy: string; regime: string; status: string;
  declarations_json: Record<string, number>;
  monthly_rent_paid: number; rented_in_metro: boolean;
  landlord_pan: string | null;
  other_income_annual: number;
  previous_employer_income: number; previous_employer_tds: number;
  submitted_at: string | null; verified_at: string | null;
  rejection_reason: string | null;
}

const errMsg = (e: any, fb: string) => {
  const d = e?.response?.data?.detail;
  if (typeof d === 'string') return d;
  return e?.message || fb;
};

const statusChip = (s: string) => {
  const v = s === 'verified' ? 'success'
    : s === 'rejected' ? 'error'
    : s === 'submitted' ? 'info'
    : 'warning';
  return <Badge variant={v as any}>{s}</Badge>;
};

export const TaxDeclarationQueue: React.FC = () => {
  const [rows, setRows] = useState<Decl[]>([]);
  const [loading, setLoading] = useState(true);
  const [fy, setFy] = useState('24-25');
  const [status, setStatus] = useState<string>('submitted');
  const [reviewing, setReviewing] = useState<Decl | null>(null);
  const [action, setAction] = useState<'verify' | 'reject'>('verify');
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);

  const fetchAll = async () => {
    setLoading(true);
    try {
      const r = await client.get(ENDPOINTS.TAX.DECLARATIONS, {
        params: {
          fy, ...(status !== 'all' ? { status } : {}),
        },
      });
      setRows(r.data || []);
    } catch (e: any) { toast.error(errMsg(e, 'Failed to load')); }
    finally { setLoading(false); }
  };
  useEffect(() => { fetchAll(); /* eslint-disable-line */ }, [fy, status]);

  const act = async () => {
    if (!reviewing) return;
    setBusy(true);
    try {
      await client.post(ENDPOINTS.TAX.DECLARATION_ACTION(reviewing.id), {
        action, rejection_reason: action === 'reject' ? reason : undefined,
      });
      toast.success(action === 'verify' ? 'Verified' : 'Rejected');
      setReviewing(null); setReason(''); fetchAll();
    } catch (e: any) { toast.error(errMsg(e, 'Action failed')); }
    finally { setBusy(false); }
  };

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold">Tax Declaration Queue</h1>
        <p className="text-sm text-slate-500 mt-1">
          Verify employee tax declarations. Unverified declarations DO NOT block payroll; they get flagged.
        </p>
      </div>

      <Card className="p-4">
        <div className="flex items-end gap-3 mb-4">
          <div>
            <label className="text-xs font-semibold text-slate-600">FY</label>
            <Input value={fy} onChange={e => setFy(e.target.value)} className="w-28" />
          </div>
          <div>
            <label className="text-xs font-semibold text-slate-600 flex items-center gap-1">
              <Filter className="w-3 h-3" /> Status
            </label>
            <select value={status} onChange={e => setStatus(e.target.value)}
              className="border border-slate-200 rounded-md h-9 px-2 text-sm">
              <option value="submitted">Submitted</option>
              <option value="verified">Verified</option>
              <option value="rejected">Rejected</option>
              <option value="all">All</option>
            </select>
          </div>
          <Button variant="outline" onClick={fetchAll} className="ml-auto"><RefreshCw className="w-4 h-4" /></Button>
        </div>

        {loading ? <div className="py-8 text-center text-slate-500">Loading…</div>
          : rows.length === 0 ? <div className="py-12 text-center text-slate-500">No declarations.</div>
          : (
            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead className="text-left text-xs uppercase text-slate-500 border-b">
                  <tr>
                    <th className="p-3">Employee</th>
                    <th className="p-3">FY</th>
                    <th className="p-3">Regime</th>
                    <th className="p-3">Rent / Metro</th>
                    <th className="p-3">Prev. emp. income</th>
                    <th className="p-3">Total declared</th>
                    <th className="p-3">Status</th>
                    <th className="p-3 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map(r => {
                    const totalDeclared = Object.values(r.declarations_json || {})
                      .reduce((s, v) => s + (Number(v) || 0), 0);
                    return (
                      <tr key={r.id} className="border-b hover:bg-slate-50">
                        <td className="p-3">
                          <div className="font-medium">{r.employee_full_name || `#${r.employee_id}`}</div>
                          <div className="text-[10px] text-slate-400">{r.employee_code}</div>
                        </td>
                        <td className="p-3">{r.fy}</td>
                        <td className="p-3 uppercase text-xs">{r.regime}</td>
                        <td className="p-3 text-xs">
                          ₹{r.monthly_rent_paid.toLocaleString('en-IN')}/mo
                          {r.rented_in_metro && <Badge variant="info" className="ml-1">Metro</Badge>}
                        </td>
                        <td className="p-3 text-xs font-mono">
                          ₹{r.previous_employer_income.toLocaleString('en-IN')}
                          <div className="text-[10px] text-slate-400">TDS ₹{r.previous_employer_tds.toLocaleString('en-IN')}</div>
                        </td>
                        <td className="p-3 font-mono">₹{totalDeclared.toLocaleString('en-IN')}</td>
                        <td className="p-3">{statusChip(r.status)}</td>
                        <td className="p-3 text-right space-x-1">
                          {r.status === 'submitted' && (
                            <>
                              <Button size="sm" variant="outline"
                                onClick={() => { setReviewing(r); setAction('verify'); setReason(''); }}>
                                <Check className="w-3 h-3 text-green-600" />
                              </Button>
                              <Button size="sm" variant="outline"
                                onClick={() => { setReviewing(r); setAction('reject'); setReason(''); }}>
                                <X className="w-3 h-3 text-red-600" />
                              </Button>
                            </>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
      </Card>

      <Dialog open={!!reviewing} onOpenChange={(o: boolean) => { if (!o) setReviewing(null); }}>
        <DialogContent className="max-w-lg">
          <DialogTitle>{action === 'verify' ? 'Verify' : 'Reject'} Declaration</DialogTitle>
          {reviewing && (
            <div className="space-y-3 mt-4 text-sm">
              <div><span className="text-slate-500">Employee:</span> {reviewing.employee_full_name}</div>
              <div><span className="text-slate-500">FY:</span> {reviewing.fy} · <span className="uppercase">{reviewing.regime}</span></div>
              <div>
                <span className="text-slate-500">Declarations:</span>
                <ul className="text-xs mt-1 space-y-0.5">
                  {Object.entries(reviewing.declarations_json || {})
                    .filter(([, v]) => Number(v) > 0)
                    .map(([k, v]) => (
                      <li key={k} className="flex justify-between border-b border-slate-100 py-0.5">
                        <span>{k}</span>
                        <span className="font-mono">₹{Number(v).toLocaleString('en-IN')}</span>
                      </li>
                    ))}
                </ul>
              </div>
              <div className="text-xs text-slate-600">
                Rent: ₹{reviewing.monthly_rent_paid.toLocaleString('en-IN')}/mo
                {reviewing.rented_in_metro && ' · Metro'}
                {reviewing.landlord_pan && ` · Landlord PAN ${reviewing.landlord_pan}`}
              </div>
              {action === 'reject' && (
                <div>
                  <label className="text-xs font-semibold text-slate-600">Rejection reason</label>
                  <textarea value={reason} onChange={e => setReason(e.target.value)}
                    className="w-full border border-slate-200 rounded-md p-2 text-sm" rows={3} />
                </div>
              )}
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setReviewing(null)}>Cancel</Button>
            <Button isLoading={busy} onClick={act}>
              {action === 'verify' ? 'Verify' : 'Reject'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};
