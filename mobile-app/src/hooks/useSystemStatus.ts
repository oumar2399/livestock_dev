import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { systemApi } from '../api/system';

export const systemKeys = {
  all: ['system'] as const,
  status: () => [...systemKeys.all, 'status'] as const,
  dailyJobs: () => [...systemKeys.all, 'daily-jobs'] as const,
};

export function useSystemStatus(enabled: boolean) {
  return useQuery({
    queryKey: systemKeys.status(),
    queryFn: systemApi.getStatus,
    enabled,
    refetchInterval: 60_000,
  });
}

export function useDailyJobRuns(enabled: boolean) {
  return useQuery({
    queryKey: systemKeys.dailyJobs(),
    queryFn: () => systemApi.listDailyJobs(),
    enabled,
    refetchInterval: 60_000,
  });
}

export function useRunDailyJobs() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (targetDate?: string) => systemApi.runDailyJobs(targetDate),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: systemKeys.all }),
  });
}
