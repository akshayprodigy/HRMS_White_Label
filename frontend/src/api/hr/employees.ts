import { apiFetch } from '../client';

export type Employee = {
  id: number;
  employee_code: string | null;

  first_name: string;
  last_name: string | null;

  email: string | null;
  phone: string | null;

  date_of_birth: string | null;
  gender: string | null;

  address_line1: string | null;
  address_line2: string | null;
  city: string | null;
  state: string | null;
  postal_code: string | null;
  country: string | null;

  bank_name: string | null;
  bank_account_number: string | null;
  bank_ifsc: string | null;
  bank_branch: string | null;

  emergency_contact_name: string | null;
  emergency_contact_relation: string | null;
  emergency_contact_phone: string | null;

  employment_type: string;
  employment_status: string;

  joining_date: string;
  exit_date: string | null;

  created_at: string;
  updated_at: string;
};

export type EmployeeCreate = {
  employee_code?: string | null;

  first_name: string;
  last_name?: string | null;

  email?: string | null;
  phone?: string | null;

  date_of_birth?: string | null;
  gender?: string | null;

  address_line1?: string | null;
  address_line2?: string | null;
  city?: string | null;
  state?: string | null;
  postal_code?: string | null;
  country?: string | null;

  bank_name?: string | null;
  bank_account_number?: string | null;
  bank_ifsc?: string | null;
  bank_branch?: string | null;

  emergency_contact_name?: string | null;
  emergency_contact_relation?: string | null;
  emergency_contact_phone?: string | null;

  employment_type: string;
  employment_status: string;

  joining_date: string;
  exit_date?: string | null;
};

export type EmployeeUpdate = Partial<EmployeeCreate>;

export function listEmployees(): Promise<Employee[]> {
  return apiFetch<Employee[]>('/api/v1/hr/employees');
}

export function createEmployee(payload: EmployeeCreate): Promise<Employee> {
  return apiFetch<Employee>('/api/v1/hr/employees', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function getEmployee(employeeId: number): Promise<Employee> {
  return apiFetch<Employee>(`/api/v1/hr/employees/${employeeId}`);
}

export function updateEmployee(employeeId: number, payload: EmployeeUpdate): Promise<Employee> {
  return apiFetch<Employee>(`/api/v1/hr/employees/${employeeId}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  });
}

export function deleteEmployee(employeeId: number): Promise<{ status: string }> {
  return apiFetch<{ status: string }>(`/api/v1/hr/employees/${employeeId}`, {
    method: 'DELETE',
  });
}
