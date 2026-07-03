import React, { useState, useEffect } from 'react';
import { FileCheck, Download, Loader2, Calendar } from 'lucide-react';
import { Card, Button, Badge, cn } from './ui-elements';
import { toast } from 'sonner';
import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';

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

export const MyPayslips = () => {
  const [payslips, setPayslips] = useState<PayslipRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [downloadingId, setDownloadingId] = useState<number | null>(null);

  const downloadPayslip = async (slip: PayslipRecord) => {
    setDownloadingId(slip.id);
    try {
      const res = await client.get(
        ENDPOINTS.HR.PAYROLL.PAYSLIP_DOWNLOAD(slip.id),
        { responseType: 'blob' }
      );
      const url = URL.createObjectURL(
        new Blob([res.data], { type: 'application/pdf' })
      );
      const a = document.createElement('a');
      a.href = url;
      a.download = `Payslip_${slip.year}_${String(slip.month).padStart(2, '0')}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (error: any) {
      toast.error('Failed to download payslip');
    } finally {
      setDownloadingId(null);
    }
  };

  useEffect(() => {
    fetchPayslips();
  }, []);

  const fetchPayslips = async () => {
    setLoading(true);
    try {
      const res = await client.get(ENDPOINTS.HR.PAYROLL.MY_PAYSLIPS);
      setPayslips(Array.isArray(res.data) ? res.data : []);
    } catch (error: any) {
      toast.error(
        error?.response?.data?.detail ||
        error?.response?.data?.error?.message ||
        'Failed to fetch payslips'
      );
    } finally {
      setLoading(false);
    }
  };

  const monthName = (m: number) =>
    new Date(0, m - 1).toLocaleString('default', { month: 'long' });

  if (loading) {
    return (
      <div className="flex h-96 items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-blue-600" />
      </div>
    );
  }

  return (
    <div className="p-8 max-w-[1000px] mx-auto animate-in fade-in duration-700">
      <div className="mb-10">
        <h1 className="text-4xl font-black text-[#0F172A] tracking-tighter">My Payslips</h1>
        <p className="text-[#64748B] font-bold uppercase tracking-widest text-[10px] mt-1">
          Published Salary Statements
        </p>
      </div>

      {payslips.length === 0 ? (
        <div className="p-16 border-2 border-dashed border-slate-200 rounded-3xl text-center">
          <FileCheck size={48} className="mx-auto text-slate-300 mb-4" />
          <p className="font-bold text-slate-400 text-lg">No payslips available yet</p>
          <p className="text-slate-400 text-sm mt-1">Payslips will appear here once published by HR</p>
        </div>
      ) : (
        <div className="space-y-4">
          {payslips.map((slip) => (
              <Card
                key={slip.id}
                className="p-6 border-slate-200 flex items-center justify-between hover:shadow-lg transition-shadow"
              >
                <div className="flex items-center gap-5">
                  <div className="w-14 h-14 bg-blue-50 rounded-2xl flex items-center justify-center text-blue-600">
                    <Calendar size={28} />
                  </div>
                  <div>
                    <h3 className="text-lg font-black text-slate-900">
                      {monthName(slip.month)} {slip.year}
                    </h3>
                    <div className="flex gap-4 mt-1 text-xs">
                      <span className="font-bold text-slate-500">
                        Gross: <span className="text-slate-900">₹{slip.gross_pay?.toLocaleString('en-IN')}</span>
                      </span>
                      <span className="font-bold text-slate-500">
                        Net: <span className="text-green-600 font-black">₹{slip.net_pay?.toLocaleString('en-IN')}</span>
                      </span>
                      {slip.advance_deduction > 0 && (
                        <span className="font-bold text-amber-600">
                          Adv: ₹{slip.advance_deduction.toLocaleString('en-IN')}
                        </span>
                      )}
                      <span className="text-slate-400 font-bold">
                        {slip.payable_days}d worked{slip.lop_days > 0 ? ` (${slip.lop_days} LOP)` : ''}
                      </span>
                      <span className="text-slate-400 font-bold">
                        Published {new Date(slip.published_at).toLocaleDateString()}
                      </span>
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <Badge className="bg-green-100 text-green-700 text-[9px] font-black px-3 py-1">
                    Published
                  </Badge>
                  <Button
                    variant="outline"
                    onClick={() => downloadPayslip(slip)}
                    disabled={downloadingId === slip.id}
                    className="h-10 px-4 rounded-xl font-black text-xs"
                  >
                    {downloadingId === slip.id ? (
                      <Loader2 size={14} className="animate-spin mr-1.5" />
                    ) : (
                      <Download size={14} className="mr-1.5" />
                    )}
                    PDF
                  </Button>
                </div>
              </Card>
          ))}
        </div>
      )}
    </div>
  );
};
