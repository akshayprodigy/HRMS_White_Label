import { Employee, PayrollRecord, LeaveRequest, PerformanceReview, Document } from '../types/employee';

export const mockEmployee: Employee = {
  id: 'EMP-2024-0847',
  firstName: 'Sarah',
  lastName: 'Chen',
  email: 'sarah.chen@company.com',
  phone: '+1 (555) 123-4567',
  jobTitle: 'Senior Product Designer',
  department: 'Design & UX',
  employmentStatus: 'active',
  salary: 8500,
  attendanceRate: 96,
  performanceRating: 4.6,
  leaveBalance: 8,
  profileImage: 'https://images.unsplash.com/photo-1573496359142-b8d87734a5a2?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&ixid=M3w3Nzg4Nzd8MHwxfHNlYXJjaHwxfHxwcm9mZXNzaW9uYWwlMjB3b21hbnxlbnwxfHx8fDE3NjE3NDkwNDB8MA&ixlib=rb-4.1.0&q=80&w=1080&utm_source=figma&utm_medium=referral',
  location: 'San Francisco, CA',
  dateOfBirth: '1990-06-15',
  gender: 'Female',
  maritalStatus: 'Married',
  address: '1234 Market Street, Apt 5B, San Francisco, CA 94103',
  emergencyContact: {
    name: 'Michael Chen',
    relationship: 'Spouse',
    phone: '+1 (555) 987-6543'
  },
  hireDate: '2021-03-15',
  manager: 'Jennifer Martinez',
  employmentType: 'Full-time',
  contractTerm: 'Permanent',
  workLocation: 'Hybrid',
  shift: 'Day Shift (9 AM - 6 PM)'
};

export const payrollHistory: PayrollRecord[] = [
  { month: 'Oct 2024', base: 8500, allowances: 1200, deductions: 1850, net: 7850, status: 'paid' },
  { month: 'Sep 2024', base: 8500, allowances: 1200, deductions: 1850, net: 7850, status: 'paid' },
  { month: 'Aug 2024', base: 8500, allowances: 1400, deductions: 1850, net: 8050, status: 'paid' },
  { month: 'Jul 2024', base: 8500, allowances: 1200, deductions: 1850, net: 7850, status: 'paid' },
  { month: 'Jun 2024', base: 8000, allowances: 1200, deductions: 1750, net: 7450, status: 'paid' },
];

export const leaveRequests: LeaveRequest[] = [
  { id: '1', type: 'Annual Leave', startDate: '2024-12-20', endDate: '2024-12-27', days: 5, status: 'approved' },
  { id: '2', type: 'Sick Leave', startDate: '2024-11-05', endDate: '2024-11-06', days: 2, status: 'approved' },
  { id: '3', type: 'Personal Leave', startDate: '2024-11-18', endDate: '2024-11-18', days: 1, status: 'pending' },
];

export const performanceReviews: PerformanceReview[] = [
  { quarter: 'Q3 2024', rating: 4.6, feedback: 'Excellent leadership and project delivery', reviewer: 'Jennifer Martinez' },
  { quarter: 'Q2 2024', rating: 4.5, feedback: 'Strong collaboration with engineering team', reviewer: 'Jennifer Martinez' },
  { quarter: 'Q1 2024', rating: 4.7, feedback: 'Outstanding design system contribution', reviewer: 'Jennifer Martinez' },
  { quarter: 'Q4 2023', rating: 4.4, feedback: 'Good progress on user research initiatives', reviewer: 'Jennifer Martinez' },
];

export const documents: Document[] = [
  { id: '1', name: 'Employment_Contract.pdf', type: 'pdf', uploadDate: '2021-03-15', size: '2.4 MB' },
  { id: '2', name: 'NDA_Agreement.pdf', type: 'pdf', uploadDate: '2021-03-15', size: '1.2 MB' },
  { id: '3', name: 'Performance_Review_Q3_2024.pdf', type: 'pdf', uploadDate: '2024-10-01', size: '856 KB' },
  { id: '4', name: 'Tax_Form_W2_2023.pdf', type: 'pdf', uploadDate: '2024-01-31', size: '324 KB' },
  { id: '5', name: 'Certificate_UX_Design.pdf', type: 'pdf', uploadDate: '2024-08-15', size: '1.8 MB' },
];

export const attendanceData = [
  { date: '2024-10-01', status: 'present' },
  { date: '2024-10-02', status: 'present' },
  { date: '2024-10-03', status: 'present' },
  { date: '2024-10-04', status: 'present' },
  { date: '2024-10-05', status: 'absent' },
  { date: '2024-10-07', status: 'present' },
  { date: '2024-10-08', status: 'present' },
  { date: '2024-10-09', status: 'present' },
  { date: '2024-10-10', status: 'present' },
  { date: '2024-10-11', status: 'present' },
  { date: '2024-10-14', status: 'present' },
  { date: '2024-10-15', status: 'present' },
  { date: '2024-10-16', status: 'late' },
  { date: '2024-10-17', status: 'present' },
  { date: '2024-10-18', status: 'present' },
  { date: '2024-10-21', status: 'present' },
  { date: '2024-10-22', status: 'present' },
  { date: '2024-10-23', status: 'present' },
  { date: '2024-10-24', status: 'present' },
  { date: '2024-10-25', status: 'present' },
  { date: '2024-10-28', status: 'present' },
];

export const salaryGrowthData = [
  { year: '2021', salary: 6500 },
  { year: '2022', salary: 7200 },
  { year: '2023', salary: 7800 },
  { year: '2024', salary: 8500 },
];

export const performanceTrendData = [
  { quarter: 'Q1 23', rating: 4.3 },
  { quarter: 'Q2 23', rating: 4.4 },
  { quarter: 'Q3 23', rating: 4.5 },
  { quarter: 'Q4 23', rating: 4.4 },
  { quarter: 'Q1 24', rating: 4.7 },
  { quarter: 'Q2 24', rating: 4.5 },
  { quarter: 'Q3 24', rating: 4.6 },
];

export const skillsData = [
  { skill: 'UI Design', proficiency: 95 },
  { skill: 'User Research', proficiency: 88 },
  { skill: 'Prototyping', proficiency: 92 },
  { skill: 'Design Systems', proficiency: 90 },
  { skill: 'Leadership', proficiency: 85 },
];

export const trainingCourses = [
  { name: 'Advanced Figma Techniques', status: 'completed', completedDate: '2024-08-15', progress: 100 },
  { name: 'Leadership Fundamentals', status: 'completed', completedDate: '2024-06-20', progress: 100 },
  { name: 'Data-Driven Design', status: 'in-progress', completedDate: null, progress: 65 },
  { name: 'Accessibility Standards', status: 'assigned', completedDate: null, progress: 0 },
];
