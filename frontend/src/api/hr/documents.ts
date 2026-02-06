import { apiFetch } from '../client';

export type EmployeeDocument = {
  id: number;
  employee_id: number;

  document_type: string;
  title: string | null;
  file_ref: string;
  mime_type: string | null;
  issued_on: string | null;
  expires_on: string | null;
  notes: string | null;

  created_at: string;
  updated_at: string;
};

export type EmployeeDocumentCreate = {
  document_type: string;
  title?: string | null;
  file_ref: string;
  mime_type?: string | null;
  issued_on?: string | null;
  expires_on?: string | null;
  notes?: string | null;
};

export function listEmployeeDocuments(employeeId: number): Promise<EmployeeDocument[]> {
  return apiFetch<EmployeeDocument[]>(`/api/v1/hr/employees/${employeeId}/documents`);
}

export function createEmployeeDocument(
  employeeId: number,
  payload: EmployeeDocumentCreate,
): Promise<EmployeeDocument> {
  return apiFetch<EmployeeDocument>(`/api/v1/hr/employees/${employeeId}/documents`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function deleteEmployeeDocument(
  employeeId: number,
  documentId: number,
): Promise<{ status: string }> {
  return apiFetch<{ status: string }>(
    `/api/v1/hr/employees/${employeeId}/documents/${documentId}`,
    {
      method: 'DELETE',
    },
  );
}
