import React, { useEffect, useState } from 'react';
import { Download, TrendingUp, Calendar } from 'lucide-react';
import { Card, Badge, cn } from './ui-elements';
import { toast } from 'sonner';
import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';

interface Revision {
  id: number;
  revision_type: string; effective_from: string; status: string;
  old_ctc: number; new_ctc: number; hike_amount: number; hike_percent: number;
  old_designation_title: string | null; new_designation_title: string | null;
  letter_id: number | null;
  arrears_run_id: number | null; arrears_amount: number; arrears_months: number;
  rejected_reason: string | null;
  applied_at: string | null;
}

const errMsg = (e: any, f: string) =>
  e?.response?.data?.detail || e?.message || f;

const chip = (s: string) => {
  const v = s === 'applied' || s === 'approved' ? 'success'
    : s === 'rejected' || s === 'cancelled' ? 'error' : 'info';
  return <Badge variant={v as any}>{s}</Badge>;
};

export const MyRevisionsView: React.FC = () => {
  const [rows, setRows] = useState<Revision[]>([]);
  const [loading, setLoading] = useState(true);

  const fetch = async () => {
    setLoading(true);
    try {
      const r = await client.get(ENDPOINTS.REVISIONS.MY);
      setRows(r.data || []);
    } catch (e: any) { toast.error(errMsg(e, 'Failed to load')); }
    finally { setLoading(false); }
  };
  useEffect(() => { fetch(); }, []);

  const downloadLetter = async (r: Revision) => {
    if (!r.letter_id) return;
    try {
      const res = await client.get(ENDPOINTS.REVISIONS.LETTER(r.id), { responseType: 'blob' });
      const blob = new Blob([res.data], { type: 'application/pdf' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = `revision_${r.id}.pdf`; a.click();
      URL.revokeObjectURL(url);
    } catch (e: any) { toast.error(errMsg(e, 'Download failed')); }
  };

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <TrendingUp className="w-6 h-6 text-blue-600" /> My Revisions
        </h1>
        <p className="text-sm text-slate-500 mt-1">
          Your compensation timeline — promotions, increments, applied changes and arrears.
        </p>
      </div>

      <Card className="p-4">
        {loading ? <div className="py-8 text-center text-slate-500">Loading…</div>
          : rows.length === 0 ? <div className="py-12 text-center text-slate-500">No revisions yet.</div>
            : (
              <div className="space-y-3">
                {rows.map(r => (
                  <div key={r.id} className="border-l-4 border-blue-500 pl-4 py-2 hover:bg-slate-50 rounded-r-md">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <span className="font-bold capitalize">{r.revision_type}</span>
                        {chip(r.status)}
                        <span className="text-xs text-slate-500 flex items-center gap-1">
                          <Calendar className="w-3 h-3" /> {r.effective_from}
                        </span>
                      </div>
                      {r.letter_id && (
                        <button onClick={() => downloadLetter(r)}
                          className="text-xs text-blue-600 hover:underline flex items-center gap-1">
                          <Download className="w-3 h-3" /> Letter
                        </button>
                      )}
                    </div>
                    <div className="mt-2 text-sm flex items-center gap-4">
                      {r.old_designation_title !== r.new_designation_title && (
                        <span className="text-slate-600">
                          {r.old_designation_title || '—'} → <span className="font-semibold">{r.new_designation_title}</span>
                        </span>
                      )}
                      <span className="font-mono text-slate-700">
                        ₹{r.old_ctc.toLocaleString('en-IN')} → ₹{r.new_ctc.toLocaleString('en-IN')}
                      </span>
                      <span className={cn('font-bold',
                        r.hike_amount > 0 ? 'text-green-700' : 'text-red-700')}>
                        {r.hike_amount > 0 ? '+' : ''}{r.hike_percent.toFixed(2)}%
                      </span>
                    </div>
                    {r.arrears_run_id && (
                      <div className="text-xs text-slate-500 mt-1">
                        Arrears: ₹{r.arrears_amount.toLocaleString('en-IN')} ({r.arrears_months} mo) — paid in payroll run #{r.arrears_run_id}
                      </div>
                    )}
                    {r.rejected_reason && (
                      <div className="text-xs text-red-600 mt-1">Rejected: {r.rejected_reason}</div>
                    )}
                    {r.applied_at && (
                      <div className="text-[10px] text-slate-400 mt-1">
                        Applied on {new Date(r.applied_at).toLocaleString()}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
      </Card>
    </div>
  );
};
