import { useQuery } from '@tanstack/react-query';
import apiClient from '../api/client';

export interface ActivityBudgetItem {
  minutes: number;
  percentage: number;
}

export interface ActivitySummary {
  animal_id: number;
  animal_name: string;
  date: string;
  total_records: number;
  duration_hours: number;
  budget: {
    lying: ActivityBudgetItem;
    standing: ActivityBudgetItem;
    walking: ActivityBudgetItem;
    running: ActivityBudgetItem;
  };
  averages: {
    activity: number;
    temperature: number | null;
    battery: number | null;
  };
  hourly_breakdown: {
    hour: number;
    dominant_state: string | null;
    avg_activity: number;
    record_count: number;
  }[];
}

export function useActivitySummary(animalId: number, date?: string) {
  return useQuery<ActivitySummary>({
    queryKey: ['activity-summary', animalId, date],
    queryFn: async () => {
      const params = date ? `?target_date=${date}` : '';
      const res = await apiClient.get(`/activity/summary/${animalId}${params}`);
      return res.data;
    },
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}