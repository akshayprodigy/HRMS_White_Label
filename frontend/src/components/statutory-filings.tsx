/**
 * Statutory Filings page: generate PF / ESIC / PT files from a
 * finalized payroll run; track filing status (generated → submitted →
 * paid); download the generated file.
 */
import React, { useEffect, useMemo, useState } from 'react';
import {
  Play, Download, RefreshCw, Filter, FileText, ExternalLink,
} from 'lucide-react';
import { Card, Button, Badge, cn } from './ui-elements';
import { toast } from 'sonner@2.0.3';
import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';
import { Dialog, DialogContent, DialogTitle, DialogFooter } from './ui/dialog';
import { Input } from './ui/input';

interface Filing {
  id: number; payroll_run_id: number;
  stream: 'epf' | 'esic' | 'pt'; state: string | null;
  status: string;
  file_url: string | null; file_name: string | null;
  challan_number: string | null;
  paid_amount: number | null;
  paid_at: string | null;
  submitted_at: string | null;
  generated_at: string;
  payroll_period: string | null;
  due_date: string | null;
  days_to_due: number | null;
  summary: any;
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

export const StatutoryFilingsView: React.FC = () => {
  const [filings, setFilings] = useState<Filing[]>([]);
  const [runs, setRuns] = useState<PayrollRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [stream, setStream] = useState<string>('');
  const [status, setStatus] = useState<string>('');
  const [genOpen, setGenOpen] = useState(false);
  const [genForm, setGenForm] = useState({
    payroll_run_id: 0, state: '',
  });
  const [statusEditing, setStatusEditing] = useState<Filing | null>(null);
  const [statusForm, setStatusForm] = useState({
    status: 'submitted', challan_number: '', paid_amount: '' as number | '',
  });
  const [busy, setBusy] = useState(false);

  const fetchAll = async () => {
    setLoading(true);
    try {
      const [f, r] = await Promise.all([
        client.get(ENDPOINTS.STATUTORY.FILINGS, {
          params: {
            ...(stream ? { stream } : {}),
            ...(status ? { status } : {}),
          },
        }),
        client.get('/hr/payroll/dashboard').catch(() => ({ data: { active_runs: [] } })),
      ]);
      setFilings(f.data || []);
      const dash = r.data || {};
      const allRuns: PayrollRun[] = [
        ...(dash.active_runs || []),
        ...(dash.last_finalized_run ? [dash.last_finalized_run] : []),
      ];
      // Filter to finalized / published only (statutory needs frozen payroll)
      setRuns(allRuns.filter((x: any) =>
        ['finalized', 'published'].includes((x.status || '').toLowerCase())
      ));
    } catch (e: any) { toast.error(errMsg(e, 'Failed to load')); }
    finally { setLoading(false); }
  };

  useEffect(() => { fetchAll(); /* eslint-disable-line */ }, [stream, status]);

  const submitGenerate = async () => {
    if (!genForm.payroll_run_id) { toast.error('Pick a payroll run'); return; }
    setBusy(true);
    try {
      const r = await client.post(ENDPOINTS.STATUTORY.GENERATE, {
        payroll_run_id: genForm.payroll_run_id,
        state: genForm.state || undefined,
      });
      const n = (r.data?.filings || []).length;
      const skipped = (r.data?.skipped_states || []).length;
      toast.success(`Generated ${n} filing${n === 1 ? '' : 's'}${skipped ? `, skipped ${skipped} empty state(s)` : ''}`);
      setGenOpen(false); fetchAll();
    } catch (e: any) { toast.error(errMsg(e, 'Generation failed')); }
    finally { setBusy(false); }
  };

  const downloadFiling = async (f: Filing) => {
    try {
      const res = await client.get(ENDPOINTS.STATUTORY.DOWNLOAD(f.id), { responseType: 'blob' });
      const blob = new Blob([res.data], { type: 'application/octet-stream' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = f.file_name || `filing_${f.id}`;
      a.click(); URL.revokeObjectURL(url);
    } catch (e: any) { toast.error(errMsg(e, 'Download failed')); }
  };

  const openStatusEdit = (f: Filing) => {
    setStatusEditing(f);
    setStatusForm({
      status: f.status === 'generated' ? 'submitted' : f.status,
      challan_number: f.challan_number || '',
      paid_amount: f.paid_amount ?? '',
    });
  };
  const submitStatus = async () => {
    if (!statusEditing) return;
    setBusy(true);
    try {
      await client.patch(ENDPOINTS.STATUTORY.STATUS(statusEditing.id), {
        status: statusForm.status,
        challan_number: statusForm.challan_number || undefined,
        paid_amount: statusForm.paid_amount === '' ? undefined : Number(statusForm.paid_amount),
      });
      toast.success('Status updated'); setStatusEditing(null); fetchAll();
    } catch (e: any) { toast.error(errMsg(e, 'Status update failed')); }
    finally { setBusy(false); }
  };

  const groupedByRun = useMemo(() => {
    const m = new Map<number, Filing[]>();
    for (const f of filings) {
      if (!m.has(f.payroll_run_id)) m.set(f.payroll_run_id, []);
      m.get(f.payroll_run_id)!.push(f);
    }
    return Array.from(m.entries()).sort((a, b) => b[0] - a[0]);
  }, [filings]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <FileText className="w-6 h-6 text-blue-600" /> Statutory Filings
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            EPFO ECR, ESIC contribution CSV and per-state PT summary — generated from finalized payroll only.
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={fetchAll}><RefreshCw className="w-4 h-4" /></Button>
          <Button onClick={() => setGenOpen(true)}><Play className="w-4 h-4 mr-2" /> Generate</Button>
        </div>
      </div>

      <Card className="p-4">
        <div className="flex items-center gap-3 mb-4">
          <Filter className="w-4 h-4 text-slate-500" />
          <select value={stream} onChange={e => setStream(e.target.value)}
            className="border border-slate-200 rounded-md h-9 px-2 text-sm">
            <option value="">All streams</option>
            <option value="epf">EPF</option>
            <option value="esic">ESIC</option>
            <option value="pt">PT</option>
          </select>
          <select value={status} onChange={e => setStatus(e.target.value)}
            className="border border-slate-200 rounded-md h-9 px-2 text-sm">
            <option value="">All statuses</option>
            <option value="generated">Generated</option>
            <option value="submitted">Submitted</option>
            <option value="acknowledged">Acknowledged</option>
            <option value="paid">Paid</option>
            <option value="rejected">Rejected</option>
          </select>
        </div>

        {loading ? <div className="py-8 text-center text-slate-500">Loading…</div>
          : filings.length === 0 ? <div className="py-12 text-center text-slate-500">No statutory filings yet.</div>
          : (
            <div className="space-y-4">
              {groupedByRun.map(([runId, runFilings]) => (
                <div key={runId} className="border border-slate-200 rounded-lg overflow-hidden">
                  <div className="bg-slate-50 px-4 py-2 border-b border-slate-200 flex items-center justify-between">
                    <div className="font-semibold text-sm">
                      Payroll Run #{runId}
                      {runFilings[0].payroll_period && (
                        <span className="ml-2 text-slate-500 font-normal">· {runFilings[0].payroll_period}</span>
                      )}
                    </div>
                    <span className="text-xs text-slate-500">{runFilings.length} file{runFilings.length === 1 ? '' : 's'}</span>
                  </div>
                  <table className="min-w-full text-sm">
                    <thead className="text-left text-xs uppercase text-slate-500">
                      <tr>
                        <th className="p-3">Stream</th>
                        <th className="p-3">State</th>
                        <th className="p-3">Generated</th>
                        <th className="p-3">Due</th>
                        <th className="p-3">Status</th>
                        <th className="p-3">Totals</th>
                        <th className="p-3 text-right">Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {runFilings.map(f => {
                        const overdue = f.days_to_due != null && f.days_to_due < 0;
                        const due7 = f.days_to_due != null && f.days_to_due >= 0 && f.days_to_due <= 7;
                        const totals = (() => {
                          const s = f.summary || {};
                          if (f.stream === 'epf') return s.total_employee_epf != null ? `EE ₹${s.total_employee_epf}` : null;
                          if (f.stream === 'esic') return s.total_employee_contribution != null ? `EE ₹${s.total_employee_contribution}` : null;
                          if (f.stream === 'pt') return s.total_pt_amount != null ? `PT ₹${s.total_pt_amount}` : null;
                          return null;
                        })();
                        return (
                          <tr key={f.id} className="border-t border-slate-100">
                            <td className="p-3">{streamChip(f.stream)}</td>
                            <td className="p-3 text-xs">{f.state || '—'}</td>
                            <td className="p-3 text-xs">{new Date(f.generated_at).toLocaleDateString()}</td>
                            <td className="p-3 text-xs">
                              <span className={cn(overdue && 'text-red-600 font-bold', due7 && 'text-amber-600 font-bold')}>
                                {f.due_date || '—'}
                                {f.days_to_due != null && (
                                  <span className="ml-1">
                                    ({overdue ? `${Math.abs(f.days_to_due)}d overdue` : `${f.days_to_due}d left`})
                                  </span>
                                )}
                              </span>
                            </td>
                            <td className="p-3">{statusChip(f.status)}
                              {f.challan_number && <div className="text-[10px] text-slate-400">{f.challan_number}</div>}
                            </td>
                            <td className="p-3 text-xs font-mono">
                              {totals || '—'}
                              {f.summary?.employee_count != null && (
                                <div className="text-[10px] text-slate-400">{f.summary.employee_count} employees</div>
                              )}
                            </td>
                            <td className="p-3 text-right space-x-1">
                              <Button size="sm" variant="outline" onClick={() => downloadFiling(f)}>
                                <Download className="w-3 h-3" />
                              </Button>
                              <Button size="sm" variant="outline" onClick={() => openStatusEdit(f)}>
                                <ExternalLink className="w-3 h-3" />
                              </Button>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              ))}
            </div>
          )}
      </Card>

      {/* Generate modal */}
      <Dialog open={genOpen} onOpenChange={setGenOpen}>
        <DialogContent className="max-w-md">
          <DialogTitle>Generate statutory files</DialogTitle>
          <div className="space-y-3 mt-4">
            <div>
              <label className="text-xs font-semibold text-slate-600">Payroll run (finalized only)</label>
              <select value={genForm.payroll_run_id || ''}
                onChange={e => setGenForm({ ...genForm, payroll_run_id: Number(e.target.value) })}
                className="w-full border border-slate-200 rounded-md h-9 px-2 text-sm">
                <option value="">— Select —</option>
                {runs.map(r =>
                  <option key={r.id} value={r.id}>#{r.id} {String(r.month).padStart(2, '0')}/{r.year} ({r.status})</option>
                )}
              </select>
            </div>
            <div>
              <label className="text-xs font-semibold text-slate-600">PT state filter (optional)</label>
              <Input value={genForm.state}
                onChange={e => setGenForm({ ...genForm, state: e.target.value })}
                placeholder="e.g. WB — leave blank to generate all states" />
              <div className="text-[10px] text-slate-400 mt-1">
                PF + ESIC are always generated. PT generates one file per distinct employee state.
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setGenOpen(false)}>Cancel</Button>
            <Button isLoading={busy} onClick={submitGenerate}>Generate</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Status modal */}
      <Dialog open={!!statusEditing} onOpenChange={(o: boolean) => { if (!o) setStatusEditing(null); }}>
        <DialogContent className="max-w-md">
          <DialogTitle>Update filing status</DialogTitle>
          {statusEditing && (
            <div className="space-y-3 mt-4">
              <div className="text-xs text-slate-500">
                {streamChip(statusEditing.stream)}
                {statusEditing.state && <span className="ml-2">· {statusEditing.state}</span>}
                <span className="ml-2">· Run #{statusEditing.payroll_run_id} {statusEditing.payroll_period && `(${statusEditing.payroll_period})`}</span>
              </div>
              <div>
                <label className="text-xs font-semibold text-slate-600">Status</label>
                <select value={statusForm.status}
                  onChange={e => setStatusForm({ ...statusForm, status: e.target.value })}
                  className="w-full border border-slate-200 rounded-md h-9 px-2 text-sm">
                  <option value="generated">Generated</option>
                  <option value="submitted">Submitted</option>
                  <option value="acknowledged">Acknowledged</option>
                  <option value="paid">Paid</option>
                  <option value="rejected">Rejected</option>
                </select>
              </div>
              <div>
                <label className="text-xs font-semibold text-slate-600">Challan number</label>
                <Input value={statusForm.challan_number}
                  onChange={e => setStatusForm({ ...statusForm, challan_number: e.target.value })} />
              </div>
              <div>
                <label className="text-xs font-semibold text-slate-600">Paid amount ₹</label>
                <Input type="number" min={0} value={statusForm.paid_amount}
                  onChange={e => setStatusForm({ ...statusForm, paid_amount: e.target.value === '' ? '' : Number(e.target.value) })} />
              </div>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setStatusEditing(null)}>Cancel</Button>
            <Button isLoading={busy} onClick={submitStatus}>Update</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};
