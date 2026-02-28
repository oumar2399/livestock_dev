/**
 * Service API - Télémétrie
 * Endpoints : POST /telemetry, GET /telemetry/latest, GET /telemetry/history/{id}
 */
import apiClient from './client';
import {
  TelemetryCreate,
  TelemetryLatest,
  TelemetryLatestParams,
  TelemetryRecord,
} from '../types';

const BASE = '/telemetry';

export const telemetryApi = {
  /**
   * POST /api/v1/telemetry/
   * Envoyer données depuis M5Stack (utilisé par firmware ESP32)
   * Retourne la télémétrie enregistrée avec ID
   */
  send: async (payload: TelemetryCreate): Promise<TelemetryRecord> => {
    const { data } = await apiClient.post<TelemetryRecord>(BASE + '/', payload);
    return data;
  },

  /**
   * GET /api/v1/telemetry/latest
   * Dernières positions de tous les animaux (ou d'un seul)
   * Utilisé pour la carte temps réel (polling toutes les 10s)
   */
  getLatest: async (params?: TelemetryLatestParams): Promise<TelemetryLatest[]> => {
    const { data } = await apiClient.get<TelemetryLatest[]>(BASE + '/latest', { params });
    return data;
  },

  /**
   * GET /api/v1/telemetry/history/{animal_id}?hours=24
   * Historique complet d'un animal pour graphiques et traces GPS
   * hours: 1-168 (max 7 jours)
   */
  getHistory: async (
    animalId: number,
    hours: number = 24,
  ): Promise<TelemetryRecord[]> => {
    const { data } = await apiClient.get<TelemetryRecord[]>(
      `${BASE}/history/${animalId}`,
      { params: { hours } },
    );
    return data;
  },
};
