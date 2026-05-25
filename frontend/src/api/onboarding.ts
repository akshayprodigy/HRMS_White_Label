import { client } from './client';

export const onboardingApi = {
  getProcesses: () => 
    client.get('/hr/onboarding/'),
  
  completeTask: (processId: number, taskId: number) =>
    client.post(`/hr/onboarding/${processId}/tasks/${taskId}/complete`),

  initiateOnboarding: (applicantId: number) =>
    client.post('/hr/onboarding/', { applicant_id: applicantId }),

  getReadyApplicants: () =>
    client.get('/hr/onboarding/ready'),
};
