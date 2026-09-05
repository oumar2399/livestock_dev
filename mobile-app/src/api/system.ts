import apiClient from './client';
import { DailyJobRunList, SystemStatus } from '../types';

export const systemApi = {
  getStatus: async (): Promise<SystemStatus> => {
    const { data } = await apiClient.get<SystemStatus>('/admin/system-status');
    return data;
  },

  listDailyJobs: async (limit = 20): Promise<DailyJobRunList> => {
    const { data } = await apiClient.get<DailyJobRunList>('/admin/daily-job-runs', {
      params: { limit },
    });
    return data;
  },

  runDailyJobs: async (targetDate?: string): Promise<unknown> => {
    const { data } = await apiClient.post('/admin/run-daily-jobs', null, {
      params: targetDate ? { target_date: targetDate } : undefined,
    });
    return data;
  },
};
