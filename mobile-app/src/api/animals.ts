/**
 * Service API - Animaux
 * Endpoints : GET /animals, GET /animals/{id}, POST, PUT, DELETE
 */
import apiClient from './client';
import {
  Animal,
  AnimalCreate,
  AnimalList,
  AnimalUpdate,
  AnimalsQueryParams,
} from '../types';

const BASE = '/animals';

export const animalsApi = {
  /**
   * GET /api/v1/animals/
   * Liste paginée avec filtres optionnels
   */
  list: async (params?: AnimalsQueryParams): Promise<AnimalList> => {
    const { data } = await apiClient.get<AnimalList>(BASE + '/', { params });
    return data;
  },

  /**
   * GET /api/v1/animals/{id}
   * Détail complet d'un animal + dernière position GPS
   */
  getById: async (id: number): Promise<Animal> => {
    const { data } = await apiClient.get<Animal>(`${BASE}/${id}`);
    return data;
  },

  /**
   * POST /api/v1/animals/
   * Créer un nouvel animal
   */
  create: async (payload: AnimalCreate): Promise<Animal> => {
    const { data } = await apiClient.post<Animal>(BASE + '/', payload);
    return data;
  },

  /**
   * PUT /api/v1/animals/{id}
   * Mise à jour complète (tous champs)
   */
  update: async (id: number, payload: AnimalUpdate): Promise<Animal> => {
    const { data } = await apiClient.put<Animal>(`${BASE}/${id}`, payload);
    return data;
  },

  /**
   * DELETE /api/v1/animals/{id}
   * Supprime animal + télémétrie et alertes associées (CASCADE)
   * Retourne 204 No Content
   */
  delete: async (id: number): Promise<void> => {
    await apiClient.delete(`${BASE}/${id}`);
  },
};
