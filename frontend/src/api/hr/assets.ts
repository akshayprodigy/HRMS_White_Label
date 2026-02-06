import { apiFetch } from '../client';

export type EmployeeAsset = {
  id: number;
  employee_id: number;

  asset_category: string;
  asset_name: string;
  asset_tag: string | null;

  issued_on: string;
  returned_on: string | null;
  notes: string | null;

  created_at: string;
  updated_at: string;
};

export type EmployeeAssetCreate = {
  asset_category: string;
  asset_name: string;
  asset_tag?: string | null;
  issued_on: string;
  returned_on?: string | null;
  notes?: string | null;
};

export type EmployeeAssetUpdate = Partial<EmployeeAssetCreate>;

export function listEmployeeAssets(employeeId: number): Promise<EmployeeAsset[]> {
  return apiFetch<EmployeeAsset[]>(`/api/v1/hr/employees/${employeeId}/assets`);
}

export function assignEmployeeAsset(
  employeeId: number,
  payload: EmployeeAssetCreate,
): Promise<EmployeeAsset> {
  return apiFetch<EmployeeAsset>(`/api/v1/hr/employees/${employeeId}/assets`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function updateEmployeeAsset(
  employeeId: number,
  assetId: number,
  payload: EmployeeAssetUpdate,
): Promise<EmployeeAsset> {
  return apiFetch<EmployeeAsset>(`/api/v1/hr/employees/${employeeId}/assets/${assetId}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  });
}

export function deleteEmployeeAsset(
  employeeId: number,
  assetId: number,
): Promise<{ status: string }> {
  return apiFetch<{ status: string }>(`/api/v1/hr/employees/${employeeId}/assets/${assetId}`, {
    method: 'DELETE',
  });
}
