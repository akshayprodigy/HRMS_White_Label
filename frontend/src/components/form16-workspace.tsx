/**
 * Form 16 workspace + Form 24Q. Bulk-generate Part B from finalized
 * payroll, upload TRACES-issued Part A URL, issue and download.
 */
import React, { useEffect, useState } from 'react';
import {
  Play, Download, Upload, FileCheck, AlertCircle, RefreshCw,
} from 'lucide-react';
import { Card, Button, Badge, cn } from './ui-elements';
import { toast } from 'sonner@2.0.3';
import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';
import { Dialog, DialogContent, DialogTitle, DialogFooter } from './ui/dialog';
import { Input } from './ui/input';

interface Form16 {
  id: number; employee_id: number; fy: string;
  reference_number: string | null;
  employee_full_name: string | null; employee_code: string | null;
  pan: string | null;
  part_b_url: string | null; part_b_generated_at: string | null;
  part_a_url: string | null; part_a_uploaded_at: string | null;
  traces_certificate_number: string | null;
  status: 'pending_part_a' | 'ready' | 'issued';
  issued_at: string | null;
  missing_pan_flag: boolean;
}

interface Form24Q {
  id: number; fy: string; quarter: number;
  file_url: string | null; file_name: string | null;
  summary: any;
  status: string;
  challan_number: string | null;
  submitted_at: string | null;
  generated_at: string | null;
}

const errMsg = (e: any, fb: string) => {
  const d = e?.response?.data?.detail;
  if (typeof d === 'string') return d;
  return e?.message || fb;
};

const statusChip = (s: string, missing_pan?: boolean) => {
  if (missing_pan) return <Badge variant="error">PAN missing</Badge>;
  const v = s === 'issued' ? 'success'
    : s === 'ready' ? 'info'
    : 'warning';
  return <Badge variant={v as any}>{s.replace('_', ' ')}</Badge>;
};

export const Form16Workspace: React.FC = () => {
  const [tab, setTab] = useState<'form16' | 'form24q'>('form16');
  const [fy, setFy] = useState('24-25');
  const [rows, setRows] = useState<Form16[]>([]);
  const [q24, setQ24] = useState<Form24Q[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  // Upload Part A modal
  const [uploadOpen, setUploadOpen] = useState<Form16 | null>(null);
  const [uploadForm, setUploadForm] = useState({
    part_a_url: '', traces_certificate_number: '',
  });

  // Generate 24Q modal
  const [gen24Open, setGen24Open] = useState(false);
  const [genQ, setGenQ] = useState(4);

  const fetchAll = async () => {
    setLoading(true);
    try {
      const [f, q] = await Promise.all([
        client.get(ENDPOINTS.TAX.FORM16, { params: { fy } }),
        client.get(ENDPOINTS.TAX.FORM24Q, { params: { fy } }),
      ]);
      setRows(f.data || []); setQ24(q.data || []);
    } catch (e: any) { toast.error(errMsg(e, 'Failed to load')); }
    finally { setLoading(false); }
  };
  useEffect(() => { fetchAll(); /* eslint-disable-line */ }, [fy]);

  const bulkGenerate = async () => {
    setBusy(true);
    try {
      const r = await client.post(ENDPOINTS.TAX.FORM16_GENERATE, { fy });
      const d = r.data;
      toast.success(
        `Generated ${d.generated} · ${d.skipped_no_pan} flagged PAN · ${d.skipped_no_payroll} no payroll`
      );
      fetchAll();
    } catch (e: any) { toast.error(errMsg(e, 'Generate failed')); }
    finally { setBusy(false); }
  };

  const uploadPartA = async () => {
    if (!uploadOpen) return;
    if (!uploadForm.part_a_url.trim()) {
      toast.error('Part A URL required'); return;
    }
    setBusy(true);
    try {
      await client.post(ENDPOINTS.TAX.FORM16_UPLOAD_PART_A(uploadOpen.id), uploadForm);
      toast.success('Part A registered');
      setUploadOpen(null); fetchAll();
    } catch (e: any) { toast.error(errMsg(e, 'Upload failed')); }
    finally { setBusy(false); }
  };

  const issue = async (r: Form16) => {
    try {
      await client.post(ENDPOINTS.TAX.FORM16_ISSUE(r.id));
      toast.success('Issued'); fetchAll();
    } catch (e: any) { toast.error(errMsg(e, 'Issue failed')); }
  };

  const downloadPartB = async (r: Form16) => {
    try {
      const res = await client.get(ENDPOINTS.TAX.FORM16_DOWNLOAD(r.id), { responseType: 'blob' });
      const blob = new Blob([res.data], { type: 'application/pdf' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${r.reference_number?.replace(/\//g, '_') || `form16_${r.id}`}.pdf`;
      a.click(); URL.revokeObjectURL(url);
    } catch (e: any) { toast.error(errMsg(e, 'Download failed')); }
  };

  const generate24Q = async () => {
    setBusy(true);
    try {
      await client.post(ENDPOINTS.TAX.FORM24Q_GENERATE, { fy, quarter: genQ });
      toast.success(`24Q for FY ${fy} Q${genQ} generated`);
      setGen24Open(false); fetchAll();
    } catch (e: any) { toast.error(errMsg(e, '24Q failed')); }
    finally { setBusy(false); }
  };

  const download24Q = async (q: Form24Q) => {
    try {
      const res = await client.get(ENDPOINTS.TAX.FORM24Q_DOWNLOAD(q.id), { responseType: 'blob' });
      const blob = new Blob([res.data], { type: 'text/csv' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = q.file_name || `24Q_${q.id}.csv`;
      a.click(); URL.revokeObjectURL(url);
    } catch (e: any) { toast.error(errMsg(e, 'Download failed')); }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <FileCheck className="w-6 h-6 text-blue-600" /> Form 16 + Form 24Q
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Form 16 Part B is generated from finalized payroll.
            Part A comes from TRACES — upload its URL to pair them.
          </p>
        </div>
        <div className="flex items-end gap-2">
          <div>
            <label className="text-xs font-semibold text-slate-600">FY</label>
            <Input value={fy} onChange={e => setFy(e.target.value)} className="w-28" />
          </div>
          {tab === 'form16' && (
            <Button onClick={bulkGenerate} isLoading={busy}>
              <Play className="w-4 h-4 mr-2" /> Bulk generate Part B
            </Button>
          )}
          {tab === 'form24q' && (
            <Button onClick={() => setGen24Open(true)}>
              <Play className="w-4 h-4 mr-2" /> Generate 24Q
            </Button>
          )}
          <Button variant="outline" onClick={fetchAll}><RefreshCw className="w-4 h-4" /></Button>
        </div>
      </div>

      <Card className="p-4">
        <div className="flex items-center gap-2 mb-3">
          {(['form16', 'form24q'] as const).map(t => (
            <button key={t} onClick={() => setTab(t)}
              className={cn(
                'px-3 py-1.5 text-sm rounded-md font-medium',
                tab === t ? 'bg-blue-600 text-white' : 'bg-slate-100 text-slate-700',
              )}>
              {t === 'form16' ? 'Form 16' : 'Form 24Q'}
            </button>
          ))}
        </div>

        {loading ? <div className="py-8 text-center text-slate-500">Loading…</div>
          : tab === 'form16' ? (
            rows.length === 0 ? <div className="py-12 text-center text-slate-500">No Form 16 records yet.</div>
              : (
                <div className="overflow-x-auto">
                  <table className="min-w-full text-sm">
                    <thead className="text-left text-xs uppercase text-slate-500 border-b">
                      <tr>
                        <th className="p-3">Employee</th>
                        <th className="p-3">PAN</th>
                        <th className="p-3">Ref. number</th>
                        <th className="p-3">Part B</th>
                        <th className="p-3">Part A (TRACES)</th>
                        <th className="p-3">Status</th>
                        <th className="p-3 text-right">Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map(r => (
                        <tr key={r.id} className="border-b hover:bg-slate-50">
                          <td className="p-3">
                            <div className="font-medium">{r.employee_full_name}</div>
                            <div className="text-[10px] text-slate-400">{r.employee_code}</div>
                          </td>
                          <td className="p-3 text-xs font-mono">
                            {r.pan || <span className="text-red-600 flex items-center gap-1"><AlertCircle className="w-3 h-3" /> missing</span>}
                          </td>
                          <td className="p-3 text-xs">{r.reference_number || '—'}</td>
                          <td className="p-3 text-xs">
                            {r.part_b_generated_at
                              ? <span className="text-green-700">✓ {new Date(r.part_b_generated_at).toLocaleDateString()}</span>
                              : '—'}
                          </td>
                          <td className="p-3 text-xs">
                            {r.part_a_url ? <span className="text-green-700">✓ {r.traces_certificate_number || 'linked'}</span>
                              : <span className="text-amber-700">pending</span>}
                          </td>
                          <td className="p-3">{statusChip(r.status, r.missing_pan_flag)}</td>
                          <td className="p-3 text-right space-x-1">
                            {r.part_b_generated_at && (
                              <Button size="sm" variant="outline" onClick={() => downloadPartB(r)}>
                                <Download className="w-3 h-3" />
                              </Button>
                            )}
                            <Button size="sm" variant="outline"
                              onClick={() => { setUploadOpen(r); setUploadForm({ part_a_url: r.part_a_url || '', traces_certificate_number: r.traces_certificate_number || '' }); }}>
                              <Upload className="w-3 h-3" />
                            </Button>
                            {r.status === 'ready' && (
                              <Button size="sm" onClick={() => issue(r)}>Issue</Button>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )
          ) : (
            q24.length === 0 ? <div className="py-12 text-center text-slate-500">No 24Q files yet.</div>
              : (
                <div className="overflow-x-auto">
                  <table className="min-w-full text-sm">
                    <thead className="text-left text-xs uppercase text-slate-500 border-b">
                      <tr>
                        <th className="p-3">Quarter</th>
                        <th className="p-3">Generated</th>
                        <th className="p-3">Status</th>
                        <th className="p-3">Totals</th>
                        <th className="p-3 text-right">Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {q24.map(q => (
                        <tr key={q.id} className="border-b hover:bg-slate-50">
                          <td className="p-3 font-medium">FY {q.fy} · Q{q.quarter}</td>
                          <td className="p-3 text-xs">
                            {q.generated_at ? new Date(q.generated_at).toLocaleDateString() : '—'}
                          </td>
                          <td className="p-3">
                            <Badge variant={q.status === 'accepted' ? 'success' : q.status === 'rejected' ? 'error' : 'info'}>
                              {q.status}
                            </Badge>
                          </td>
                          <td className="p-3 text-xs font-mono">
                            {q.summary?.employee_count != null && `${q.summary.employee_count} emps`}
                            {q.summary?.total_tds_deducted != null && ` · TDS ₹${q.summary.total_tds_deducted.toLocaleString('en-IN')}`}
                          </td>
                          <td className="p-3 text-right">
                            {q.file_name && (
                              <Button size="sm" variant="outline" onClick={() => download24Q(q)}>
                                <Download className="w-3 h-3" />
                              </Button>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )
          )}
      </Card>

      {/* Upload Part A modal */}
      <Dialog open={!!uploadOpen} onOpenChange={(o: boolean) => { if (!o) setUploadOpen(null); }}>
        <DialogContent className="max-w-md">
          <DialogTitle>Upload TRACES Part A</DialogTitle>
          <div className="space-y-3 mt-4">
            <div className="text-xs text-slate-500">
              Part A is generated by TRACES (NSDL) — not by us. Paste its URL / file-share path
              and the certificate number from the downloaded zip.
            </div>
            <div>
              <label className="text-xs font-semibold text-slate-600">Part A URL / path</label>
              <Input value={uploadForm.part_a_url}
                onChange={e => setUploadForm({ ...uploadForm, part_a_url: e.target.value })}
                placeholder="https://… or /shared/traces/…" />
            </div>
            <div>
              <label className="text-xs font-semibold text-slate-600">TRACES certificate number</label>
              <Input value={uploadForm.traces_certificate_number}
                onChange={e => setUploadForm({ ...uploadForm, traces_certificate_number: e.target.value })} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setUploadOpen(null)}>Cancel</Button>
            <Button isLoading={busy} onClick={uploadPartA}>Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Generate 24Q modal */}
      <Dialog open={gen24Open} onOpenChange={setGen24Open}>
        <DialogContent className="max-w-sm">
          <DialogTitle>Generate Form 24Q</DialogTitle>
          <div className="space-y-3 mt-4">
            <div>
              <label className="text-xs font-semibold text-slate-600">Quarter</label>
              <select value={genQ} onChange={e => setGenQ(Number(e.target.value))}
                className="w-full border border-slate-200 rounded-md h-9 px-2 text-sm">
                <option value={1}>Q1 (Apr-Jun)</option>
                <option value={2}>Q2 (Jul-Sep)</option>
                <option value={3}>Q3 (Oct-Dec)</option>
                <option value={4}>Q4 (Jan-Mar)</option>
              </select>
            </div>
            <div className="text-xs text-slate-500">
              Annexure I (per-employee TDS for the quarter). Annexure II
              (full-year breakdown) is required in Q4 — generated as a separate file in a future update.
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setGen24Open(false)}>Cancel</Button>
            <Button isLoading={busy} onClick={generate24Q}>Generate</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};
