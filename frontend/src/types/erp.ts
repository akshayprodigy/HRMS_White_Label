export type UserRole =
  | 'employee'
  | 'hr'
  | 'recruiter'
  | 'pm'
  | 'admin'
  | 'super admin'
  | 'dop'
  | 'coo'
  | 'bd'
  | 'bd manager'
  | 'dept head'
  | 'ceo'
  | 'client manager'
  | 'finance';

export interface Project {
  id: string;
  name: string;
  client: string;
  status: 'active' | 'on-hold' | 'completed' | 'pipeline';
  progress: number;
  manager: string;
  budget: number;
  actualCost: number;
  startDate: string;
  endDate: string;
}

export interface Lead {
  id: string;
  name: string;
  source: string;
  status: 'new' | 'contacted' | 'proposal' | 'negotiation' | 'converted' | 'lost';
  owner: string;
  value: number;
  createdAt: string;
}

export interface AttendanceRecord {
  id: string;
  employeeId: string;
  date: string;
  type: 'office' | 'wfh' | 'onsite' | 'others';
  remarks?: string;
  location: { lat: number; lng: number };
  timestamp: string;
}

export interface LeaveType {
  id: number;
  name: string;
  description?: string;
  is_paid: boolean;
}

export interface LeaveBalance {
  id: number;
  leave_type: LeaveType;
  total: number;
  used: number;
  remaining: number;
}

export interface LeaveRequest {
  id: number;
  user_id: string;
  leave_type_id: number;
  leave_type: LeaveType;
  start_date: string;
  end_date: string;
  is_half_day: boolean;
  half_day_session?: 'morning' | 'afternoon';
  reason: string;
  emergency_contact?: string;
  status: 'submitted' | 'approved' | 'rejected' | 'cancelled';
  total_days: number;
  created_at: string;
}

// Backend enum values are lowercase strings (see backend PayrollRunStatus).
export type PayrollRunStatus =
  | 'draft'
  | 'attendance_locked'
  | 'leaves_locked'
  | 'draft_generated'
  | 'finalized'
  | 'published';

export interface PayrollRun {
  id: number;
  month: number;
  year: number;
  status: PayrollRunStatus;
  total_gross: number;
  total_net: number;
  total_deductions: number;
  attendance_locked_at?: string;
  leaves_locked_at?: string;
  finalized_at?: string;
  finalized_by_id?: number;
  published_at?: string;
  created_at: string;
}

export interface PayrollLine {
  id: number;
  user_id: number;
  user_full_name?: string;
  base_salary: number;
  payable_days: number;
  lop_days: number;
  gross_pay: number;
  net_pay: number;
  advance_deduction: number;
  disbursed_amount: number;
  held_amount: number;
  held_reason?: string;
  held_released: boolean;
  payable_amount?: number;
  pending_amount?: number;
  disbursement_count?: number;
}

export interface SalaryDisbursementRecord {
  id: number;
  payroll_line_id: number;
  amount: number;
  payment_mode: string;
  reference?: string;
  remarks?: string;
  disbursed_by_id: number;
  disbursed_by_name?: string;
  disbursed_at: string;
}

export interface SalaryAdvance {
  id: number;
  employee_id: number;
  amount: number;
  reason?: string;
  disbursed_date: string;
  recovery_mode: 'one_time' | 'installment';
  installment_months: number;
  recovered_amount: number;
  status: 'active' | 'fully_recovered' | 'written_off' | 'cancelled';
  approved_by_id: number;
  remarks?: string;
  created_at: string;
  updated_at?: string;
  employee_name?: string;
  employee_code?: string;
  department?: string;
  approved_by_name?: string;
  outstanding?: number;
  monthly_emi?: number;
}

export interface AdvanceRecovery {
  id: number;
  advance_id: number;
  payroll_run_id?: number;
  amount: number;
  recovered_at: string;
  remarks?: string;
}

export interface ApprovalStep {
  id: number;
  step_number: number;
  approver_id?: number;
  role_id?: number;
  status: 'pending' | 'approved' | 'rejected' | 'changes_requested';
  comment?: string;
  actioned_at?: string;
}

export interface ApprovalItem {
  id: number;
  resource_type: string;
  resource_id: string;
  status: 'pending' | 'approved' | 'rejected' | 'changes_requested';
  current_step_number: number;
  requested_by_id?: number;
  requested_by_name?: string;
  created_at: string;
  due_date?: string;
  steps: ApprovalStep[];
}

export interface Notification {
  id: number;
  user_id: number;
  title: string;
  message: string;
  type: 'info' | 'warning' | 'success' | 'error';
  resource_type?: string;
  resource_id?: string;
  is_read: boolean;
  created_at: string;
}

export interface AttendanceCompliance {
  date: string;
  total_employees: number;
  present_count: number;
  compliance_percentage: number;
}

export interface ProjectUtilization {
  project_id: number;
  project_name: string;
  total_hours: number;
  billable_hours: number;
  utilization_percentage: number;
}

export interface LeaveBalanceSummary {
  employee_id: number;
  employee_name: string;
  leave_type: string;
  total_allotted: number;
  taken: number;
  remaining: number;
}

export interface CostVariance {
  category: string;
  budgeted_cost: number;
  actual_cost: number;
  variance: number;
  variance_percentage: number;
}

export interface ReportsSummary {
  attendance_compliance: AttendanceCompliance[];
  project_utilization: ProjectUtilization[];
  leave_balances: LeaveBalanceSummary[];
  cost_variance: CostVariance[];
}
