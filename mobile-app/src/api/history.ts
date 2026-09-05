import apiClient from './client';
import { TimelineEventType, TimelinePage } from '../types';

export interface TimelineParams {
  date_from?: string;
  date_to?: string;
  event_type?: TimelineEventType[];
  limit?: number;
  cursor?: string;
}

export const historyApi = {
  getTimeline: async (animalId: number, params: TimelineParams): Promise<TimelinePage> => {
    const { data } = await apiClient.get<TimelinePage>(`/animals/${animalId}/timeline`, {
      params,
      paramsSerializer: { indexes: null },
    });
    return data;
  },
};
