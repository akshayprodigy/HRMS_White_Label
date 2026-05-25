export interface Employee {
  id: string;
  firstName: string;
  lastName: string;
  email: string;
  phone: string;
  jobTitle: string;
  department: string;
  employmentStatus: 'active' | 'suspended' | 'on-leave' | 'terminated';
  salary: number;
  attendanceRate: number;
  performanceRating: number;
  leaveBalance: number;
  profileImage: string;
  location: string;
  dateOfBirth: string;
  gender: string;
  maritalStatus: string;
  address: string;
  emergencyContact: {
    name: string;
    relationship: string;
    phone: string;
  };
  hireDate: string;
  manager: string;
  employmentType: string;
  contractTerm: string;
  workLocation: string;
  shift: string;
}

export interface PayrollRecord {
  month: string;
  base: number;
  allowances: number;
  deductions: number;
  net: number;
  status: 'paid' | 'pending' | 'processing';
}

export interface LeaveRequest {
  id: string;
  type: string;
  startDate: string;
  endDate: string;
  days: number;
  status: 'approved' | 'pending' | 'rejected';
}

export interface PerformanceReview {
  quarter: string;
  rating: number;
  feedback: string;
  reviewer: string;
}

export interface Document {
  id: string;
  name: string;
  type: string;
  uploadDate: string;
  size: string;
}
