import { api } from '../../api/client';

/** GET /tax/form16/my (Form16Read). Only Part B is generated in-app; `part_b_url` is an internal path. */
export type Form16 = {
  id: number;
  fy: string;
  reference_number: string | null;
  part_b_url: string | null;
  part_b_generated_at: string | null;
  status: string;
  issued_at: string | null;
};
/** GET /hr/employees/me/documents (EmployeeDocument wire format). */
export type MyDocument = {
  id: number;
  doc_type: string;
  original_filename: string;
  remark: string | null;
  uploaded_at: string | null;
  uploaded_by_name: string | null;
  verification_status: 'verified' | 'rejected' | 'pending';
  rejection_reason: string | null;
};

export const FORM16_KEY = ['form16-my'] as const;
export const DOCUMENTS_KEY = ['my-documents'] as const;

const list = <T>(d: unknown): T[] => (Array.isArray(d) ? (d as T[]) : []);
export async function fetchForm16(): Promise<Form16[]> {
  return list((await api.get('/tax/form16/my')).data);
}
export async function fetchMyDocuments(): Promise<MyDocument[]> {
  return list((await api.get('/hr/employees/me/documents')).data);
}

export const form16DownloadPath = (id: number) => `/tax/form16/${id}/download`;
export const form16FileName = (f: Pick<Form16, 'fy' | 'reference_number'>) => `Form16_${(f.reference_number ?? f.fy).replace(/\//g, '_')}.pdf`;
/** The list endpoint returns an absolute `/api/v1/...` download_url; build the path ourselves against the configured base. */
export const documentDownloadPath = (id: number) => `/hr/employees/me/documents/${id}/download`;
