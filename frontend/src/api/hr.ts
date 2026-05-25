import { client } from './client';
import { ENDPOINTS } from './endpoints';

export const hrApi = {
  getDashboardStats: () => 
    client.get(ENDPOINTS.HR.DASHBOARD_STATS),
  
  getEmployees: (params?: any) => 
    client.get(ENDPOINTS.HR.EMPLOYEES, { params }),
  
  getEmployeeDetail: (id: number) => 
    client.get(ENDPOINTS.HR.EMPLOYEE_DETAIL(id)),
  
  deactivateEmployee: (id: number) => 
    client.post(ENDPOINTS.HR.DEACTIVATE(id)),
  
  getAttendanceCorrections: (params?: any) => 
    client.get(ENDPOINTS.HR.ATTENDANCE_CORRECTIONS, { params }),
  
  respondToAttendanceCorrection: (id: number, action: 'approve' | 'reject', comment?: string) => 
    client.post(ENDPOINTS.HR.ATTENDANCE_CORRECTION_ACTION(id), { action, comment }),

  getHolidays: () => 
    client.get(ENDPOINTS.HR.HOLIDAYS),

  getPolicies: () => 
    client.get(ENDPOINTS.HR.POLICIES),
};
