/**
 * Service API - Fermes
 * Endpoints : GET /farms, POST /farms, GET /farms/{id}, PUT /farms/{id}
 */
import apiClient from './client';
import { FarmAccess, FarmCreateInput, FarmUpdateInput } from '../types';

const BASE = '/farms';

export const farmsApi = {
  /**
   * GET /api/v1/farms/
   * Liste des fermes accessibles à l'utilisateur courant (via membership actif)
   */
  list: async (): Promise<FarmAccess[]> => {
    const { data } = await apiClient.get<FarmAccess[]>(BASE + '/');
    return data;
  },

  /**
   * GET /api/v1/farms/{id}
   * Détail d'une ferme
   */
  getById: async (id: number): Promise<FarmAccess> => {
    const { data } = await apiClient.get<FarmAccess>(`${BASE}/${id}`);
    return data;
  },

  /**
   * POST /api/v1/farms/
   * Créer une ferme avec auto-membership 'owner'
   * Supporte client_request_id pour idempotence anti-double-clic
   */
  create: async (payload: FarmCreateInput): Promise<FarmAccess> => {
    const { data } = await apiClient.post<FarmAccess>(BASE + '/', payload);
    return data;
  },

  /**
   * PUT /api/v1/farms/{id}
   * Mettre à jour une ferme (nécessite permission manage_farm)
   */
  update: async (id: number, payload: FarmUpdateInput): Promise<FarmAccess> => {
    const { data } = await apiClient.put<FarmAccess>(`${BASE}/${id}`, payload);
    return data;
  },
};
