import { client } from './client';
import { ENDPOINTS } from './endpoints';

export const recruitmentApi = {
  getRequisitions: (params?: any) => 
    client.get(ENDPOINTS.RECRUITMENT.REQUISITIONS, { params }),
  
  createRequisition: (data: any) => 
    client.post(ENDPOINTS.RECRUITMENT.REQUISITIONS, data),
  
  submitRequisition: (id: number) => 
    client.post(ENDPOINTS.RECRUITMENT.SUBMIT(id)),
  
  getRequisition: (id: number) => 
    client.get(ENDPOINTS.RECRUITMENT.DETAIL(id)),
  
  getApplicants: (params?: any) => 
    client.get(ENDPOINTS.RECRUITMENT.APPLICANTS, { params }),
  
  createApplicant: (data: any) => 
    client.post(ENDPOINTS.RECRUITMENT.APPLICANTS, data),
  
  updateApplicantStatus: (id: number, status: string) => 
    client.patch(ENDPOINTS.RECRUITMENT.APPLICANT_STATUS(id), null, { params: { status } }),
  
  scheduleInterview: (data: any) =>
    client.post(ENDPOINTS.RECRUITMENT.INTERVIEWS, data),
};
