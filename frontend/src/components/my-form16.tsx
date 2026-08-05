import React, { useEffect, useState } from 'react';
import { FileText, Download, RefreshCw } from 'lucide-react';
import { Card, Button, Badge, cn } from './ui-elements';
import { toast } from 'sonner';
import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';

interface Form16 {
  id: number;
  fy: string;
  reference_number?: string | null;
  status: string;
  part_b_generated_at?: string | null;
  part_a_url?: string | null;
}

const errMsg = (e: any, f: string) => {
  const d = e?.response?.data?.detail;
  return typeof d === 'string' ? d : (e?.message || f);
};

export const MyForm16View: React.FC = () => {
  const [rows, setRows] = useState<Form16[]>([]);
  const [loading, setLoading] = useState(true);
  const [downloading, setDownloading] = useState<number | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      const res = await client.get(ENDPOINTS.TAX.FORM16_MY);
      setRows(res.data || []);
    } catch (e: any) {
      toast.error(errMsg(e, 'Failed to load Form 16'));
    } finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  const download = async (r: Form16) => {
    setDownloading(r.id);
    try {
      const res = await client.get(ENDPOINTS.TAX.FORM16_DOWNLOAD(r.id), { responseType: 'blob' });
      const url = URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }));
      const a = document.createElement('a');
      a.href = url; a.download = `Form16_${r.fy}.pdf`;
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
    } catch (e: any) {
      toast.error(errMsg(e, 'Download not available yet'));
    } finally { setDownloading(null); }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-black text-[#0F172A] uppercase tracking-tight flex items-center gap-2">
            <FileText size={18} className="text-blue-600" /> My Form 16
          </h3>
          <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mt-1">
            Your annual TDS certificate, once HR issues it for the financial year
          </p>
        </div>
        <button type="button" onClick={load} className="p-2 text-slate-400 hover:text-blue-600" title="Refresh" aria-label="Refresh">
          <RefreshCw size={16} className={cn(loading && 'animate-spin')} />
        </button>
      </div>

      <Card className="p-0 border-slate-200 overflow-hidden bg-white">
        {loading ? (
          <div className="py-16 text-center text-[10px] font-black uppercase tracking-widest text-slate-400 animate-pulse">Loading…</div>
        ) : rows.length === 0 ? (
          <div className="py-16 text-center text-[11px] font-bold text-slate-400">
            No Form 16 issued yet. It appears here after HR generates &amp; issues it for the financial year.
          </div>
        ) : (
          <table className="w-full text-left">
            <thead className="bg-white border-b border-slate-100"><tr>
              <th className="px-6 py-3 text-[9px] font-black text-slate-400 uppercase tracking-widest">Financial Year</th>
              <th className="px-6 py-3 text-[9px] font-black text-slate-400 uppercase tracking-widest">Reference</th>
              <th className="px-6 py-3 text-[9px] font-black text-slate-400 uppercase tracking-widest">Status</th>
              <th className="px-6 py-3 text-right text-[9px] font-black text-slate-400 uppercase tracking-widest">Action</th>
            </tr></thead>
            <tbody className="divide-y divide-slate-50">
              {rows.map(r => (
                <tr key={r.id} className="hover:bg-slate-50/60">
                  <td className="px-6 py-3 text-sm font-black text-[#0F172A]">FY {r.fy}</td>
                  <td className="px-6 py-3 text-[11px] font-bold text-slate-500">{r.reference_number || '—'}</td>
                  <td className="px-6 py-3"><Badge variant={/issued|generated/i.test(r.status) ? 'success' : 'neutral'} className="text-[8px] uppercase">{r.status}</Badge></td>
                  <td className="px-6 py-3 text-right">
                    <Button onClick={() => download(r)} isLoading={downloading === r.id} variant="ghost"
                      className="h-9 border border-blue-200 bg-blue-50 text-blue-700 hover:bg-blue-100 font-black uppercase text-[10px] tracking-widest">
                      <Download size={14} className="mr-1.5" /> Download
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
};
