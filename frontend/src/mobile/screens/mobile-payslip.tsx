import React, { useEffect, useState } from 'react';
import { FileText, Download, Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { client } from '../../api/client';
import { ENDPOINTS } from '../../api/endpoints';
import {
  cn,
  errMsg,
  fmtInr,
  fmtDate,
  EmptyState,
} from '../../components/ui-elements';

interface PayslipRecord {
  id: number;
  file_url: string;
  published_at: string;
  month: number;
  year: number;
  gross_pay: number;
  net_pay: number;
  advance_deduction: number;
  disbursed_amount: number;
  payable_days: number;
  lop_days: number;
}

const monthName = (m: number) =>
  new Date(2000, m - 1, 1).toLocaleString('en-IN', { month: 'long' });

export const MobilePayslip: React.FC = () => {
  const [slips, setSlips] = useState<PayslipRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [downloading, setDownloading] = useState<number | null>(null);

  useEffect(() => {
    void load();
  }, []);

  const load = async () => {
    setLoading(true);
    try {
      const res = await client.get<PayslipRecord[]>(
        ENDPOINTS.HR.PAYROLL.MY_PAYSLIPS
      );
      setSlips(Array.isArray(res.data) ? res.data : []);
    } catch (e) {
      toast.error(errMsg(e, 'Failed to load payslips'));
    } finally {
      setLoading(false);
    }
  };

  const open = async (slip: PayslipRecord) => {
    setDownloading(slip.id);
    try {
      // Fetch through the authenticated client to a blob, then open.
      // Payslip figures stay in-app: we never surface them in a toast,
      // a URL parameter, or a share intent.
      const res = await client.get(slip.file_url, { responseType: 'blob' });
      const blobUrl = URL.createObjectURL(res.data);
      const w = window.open(blobUrl, '_blank', 'noopener');
      if (!w) {
        // Popups blocked (common on mobile) — force a download instead.
        const a = document.createElement('a');
        a.href = blobUrl;
        a.download = `Payslip_${slip.year}_${String(slip.month).padStart(2, '0')}.pdf`;
        document.body.appendChild(a);
        a.click();
        a.remove();
      }
      setTimeout(() => URL.revokeObjectURL(blobUrl), 60000);
    } catch (e) {
      toast.error(errMsg(e, 'Failed to open payslip'));
    } finally {
      setDownloading(null);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 size={22} className="animate-spin text-slate-400" />
      </div>
    );
  }

  if (slips.length === 0) {
    return (
      <div className="p-4">
        <EmptyState
          title="No payslips yet"
          hint="Once HR publishes a run, payslips will appear here."
        />
      </div>
    );
  }

  return (
    <div className="p-4">
      <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400 mb-2 px-1">
        Published payslips · view only
      </p>
      <ul className="space-y-3">
        {slips.map((s) => (
          <li
            key={s.id}
            className="bg-white border border-slate-200 rounded-2xl p-4"
          >
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="text-[12px] text-slate-400 font-bold uppercase tracking-widest">
                  {monthName(s.month)} {s.year}
                </p>
                <p className="text-lg font-black text-[#0F172A] tabular-nums mt-1">
                  {fmtInr(Math.round((s.net_pay || 0) * 100))}
                </p>
                <p className="text-[11px] text-slate-500 mt-0.5 tabular-nums">
                  Gross {fmtInr(Math.round((s.gross_pay || 0) * 100))}
                  {s.advance_deduction > 0 &&
                    ` · Adv ${fmtInr(Math.round(s.advance_deduction * 100))}`}
                </p>
                <p className="text-[11px] text-slate-500 mt-0.5">
                  {s.payable_days}d worked
                  {s.lop_days > 0 && ` · ${s.lop_days}d LOP`} · Published{' '}
                  {fmtDate(s.published_at)}
                </p>
              </div>
              <button
                type="button"
                onClick={() => open(s)}
                disabled={downloading === s.id}
                className={cn(
                  'w-11 h-11 rounded-xl bg-[#2563EB] text-white active:bg-[#1D4ED8] flex items-center justify-center flex-shrink-0',
                  downloading === s.id && 'opacity-70'
                )}
                aria-label={`Open payslip for ${monthName(s.month)} ${s.year}`}
              >
                {downloading === s.id ? (
                  <Loader2 size={18} className="animate-spin" />
                ) : (
                  <Download size={18} />
                )}
              </button>
            </div>
          </li>
        ))}
      </ul>
      <p className="text-[11px] text-slate-400 mt-4 px-1 flex items-start gap-1">
        <FileText size={12} className="mt-0.5" />
        Payslip figures are shown only in this app — they're never sent
        via notifications or shared previews.
      </p>
    </div>
  );
};
