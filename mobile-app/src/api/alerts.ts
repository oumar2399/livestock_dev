/**
 * Service API - Alertes
 * Endpoints : GET /alerts, PATCH /alerts/{id}
 */
import apiClient from './client';
import {
  Alert,
  AlertList,
  AlertsQueryParams,
  AlertUpdate,
} from '../types';

const BASE = '/alerts';

export const alertsApi = {
  /**
   * GET /api/v1/alerts/
   * Liste alertes avec filtres : resolved, severity, animal_id
   * Inclut unresolved_count pour le badge de l'onglet
   */
  list: async (params?: AlertsQueryParams): Promise<AlertList> => {
    const { data } = await apiClient.get<AlertList>(BASE + '/', { params });
    return data;
  },

  /**
   * PATCH /api/v1/alerts/{id}
   * Acquitter une alerte (acknowledged_at + acknowledged_by)
   * ou la résoudre (resolved_at)
   *
   * Exemple acquittement :
   *   { acknowledged_at: new Date().toISOString() }
   * Exemple résolution :
   *   { resolved_at: new Date().toISOString() }
   */
  update: async (id: number, payload: AlertUpdate): Promise<Alert> => {
    const { data } = await apiClient.patch<Alert>(`${BASE}/${id}`, payload);
    return data;
  },

  // ─── Helpers métier ──────────────────────────────────────────────────────

  /**
   * Acquitter une alerte en un appel
   */
  acknowledge: async (id: number): Promise<Alert> => {
    return alertsApi.update(id, {
      acknowledged_at: new Date().toISOString(),
    });
  },

  /**
   * Résoudre une alerte en un appel
   */
  resolve: async (id: number): Promise<Alert> => {
    return alertsApi.update(id, {
      resolved_at: new Date().toISOString(),
    });
  },
};
