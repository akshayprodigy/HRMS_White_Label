import { api } from '../../api/client';

/** GET /hr/payroll/my-payslips: published payslips only; amounts are rupees (floats), not paise. */
export type Payslip = {
  id: number;
  file_url: string;
  published_at: string | null;
  month: number;
  year: number;
  gross_pay: number;
  net_pay: number;
  advance_deduction: number;
  disbursed_amount: number;
  payable_days: number;
  lop_days: number;
};

export const PAYSLIPS_KEY = ['payslips'] as const;

export async function fetchPayslips(): Promise<Payslip[]> {
  const d = (await api.get<Payslip[]>('/hr/payroll/my-payslips')).data;
  return Array.isArray(d) ? d : [];
}

/** The authenticated PDF render; `file_url` is an internal storage path and is not fetchable. */
export const payslipDownloadPath = (id: number) => `/hr/payroll/payslips/${id}/download`;
export const payslipFileName = (p: Pick<Payslip, 'month' | 'year'>) => `Payslip_${p.year}_${String(p.month).padStart(2, '0')}.pdf`;

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
export const monthLabel = (p: Pick<Payslip, 'month' | 'year'>) => `${MONTHS[p.month - 1] ?? `Month ${p.month}`} ${p.year}`;
export const fmtRupees = (n: number | null | undefined) => `₹${(n ?? 0).toLocaleString('en-IN', { maximumFractionDigits: 2 })}`;
