/**
 * Service API - Localisation et Historique GPS (Lot B)
 * Endpoints :
 * - GET /farms/{farm_id}/locations/latest
 * - GET /farms/{farm_id}/locations/{animal_id}
 * - GET /farms/{farm_id}/locations/{animal_id}/history
 */
import apiClient from './client';
import {
  LocationPoint,
  LocationHistoryResponse,
} from '../types';

export interface LocationHistoryParams {
  hours?: number;
  start?: string;
  end?: string;
}

export const locationsApi = {
  /**
   * GET /api/v1/farms/{farm_id}/locations/latest
   * Dernières positions fiables et prouvées de tous les animaux de la ferme.
   */
  getLatest: async (farmId: number, signal?: AbortSignal): Promise<LocationPoint[]> => {
    const { data } = await apiClient.get<LocationPoint[]>(
      `/farms/${farmId}/locations/latest`,
      { signal },
    );
    return data;
  },

  /**
   * GET /api/v1/farms/{farm_id}/locations/{animal_id}
   * Position courante prouvée pour un animal spécifique.
   */
  getCurrent: async (
    farmId: number,
    animalId: number,
    signal?: AbortSignal,
  ): Promise<LocationPoint> => {
    const { data } = await apiClient.get<LocationPoint>(
      `/farms/${farmId}/locations/${animalId}`,
      { signal },
    );
    return data;
  },

  /**
   * GET /api/v1/farms/{farm_id}/locations/{animal_id}/history
   * Historique de trajectoire segmentée avec détection des trous.
   */
  getHistory: async (
    farmId: number,
    animalId: number,
    params?: LocationHistoryParams,
    signal?: AbortSignal,
  ): Promise<LocationHistoryResponse> => {
    const query = new URLSearchParams();
    if (params?.hours !== undefined) {
      query.append('hours', String(params.hours));
    }
    if (params?.start) {
      query.append('start', params.start);
    }
    if (params?.end) {
      query.append('end', params.end);
    }
    const qs = query.toString();
    const url = `/farms/${farmId}/locations/${animalId}/history${qs ? `?${qs}` : ''}`;
    const { data } = await apiClient.get<LocationHistoryResponse>(url, { signal });
    return data;
  },
};
