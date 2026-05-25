import { client } from './client';
import { ENDPOINTS } from './endpoints';

export const timesheetApi = {
  getTimerStatus: () => 
    client.get(ENDPOINTS.TIMESHEET.TIMER_STATUS),
  
  startTimer: (
    projectId: number,
    taskId?: number,
    subtaskId?: number,
    notes?: string,
  ) => 
    client.post(ENDPOINTS.TIMESHEET.TIMER_START, {
      project_id: projectId,
      task_id: taskId ?? null,
      subtask_id: subtaskId ?? null,
      notes,
    }),
  
  pauseTimer: () => 
    client.post(ENDPOINTS.TIMESHEET.TIMER_PAUSE),
  
  resumeTimer: () => 
    client.post(ENDPOINTS.TIMESHEET.TIMER_RESUME),
  
  stopTimer: () => 
    client.post(ENDPOINTS.TIMESHEET.TIMER_STOP),
  
  getMyTimeEntries: (params?: any) => 
    client.get(ENDPOINTS.TIMESHEET.MY, { params }),
  
  createManualEntry: (data: any) => 
    client.post(ENDPOINTS.TIMESHEET.MANUAL, data),

  getMyUtilization: (params?: any) =>
    client.get(ENDPOINTS.TIMESHEET.UTILIZATION_MY, { params }),

  getProjectUtilization: (projectId: number | string, params?: any) =>
    client.get(ENDPOINTS.TIMESHEET.UTILIZATION_PROJECT(projectId), { params }),
};
