import apiClient from './client';
import { Geofence, GeofenceCreate, GeofenceUpdate } from '../types';

export const geofencesApi = {
  list: async (farmId: number): Promise<Geofence[]> => {
    const { data } = await apiClient.get<Geofence[]>('/geofences/', {
      params: { farm_id: farmId },
    });
    return data;
  },

  create: async (payload: GeofenceCreate): Promise<Geofence> => {
    const { data } = await apiClient.post<Geofence>('/geofences/', payload);
    return data;
  },

  update: async (id: number, payload: GeofenceUpdate): Promise<Geofence> => {
    const { data } = await apiClient.patch<Geofence>(`/geofences/${id}`, payload);
    return data;
  },

  remove: async (id: number): Promise<void> => {
    await apiClient.delete(`/geofences/${id}`);
  },
};
