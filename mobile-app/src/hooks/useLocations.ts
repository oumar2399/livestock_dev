/**
 * Hooks React Query - Localisation et Historique GPS (Lot B)
 *
 * useFarmLocations()     → Dernières positions de tous les animaux de la ferme (polling 10s)
 * useAnimalLocation()    → Position courante d'un animal spécifique (polling 10s)
 * useLocationHistory()   → Trajectoire segmentée avec trous d'observation (staleTime 2min)
 */
import { useQuery, UseQueryOptions } from '@tanstack/react-query';
import { locationsApi, LocationHistoryParams } from '../api/locations';
import { LocationPoint, LocationHistoryResponse } from '../types';
import { Config } from '../constants/config';
import { useFarmStore } from '../store/farmStore';

// ─── Query Keys ───────────────────────────────────────────────────────────────

export const locationKeys = {
  all: ['locations'] as const,
  farm: (farmId?: number | null) => [...locationKeys.all, 'farm', farmId] as const,
  animal: (farmId?: number | null, animalId?: number | null) =>
    [...locationKeys.all, 'animal', farmId, animalId] as const,
  history: (
    farmId?: number | null,
    animalId?: number | null,
    params?: LocationHistoryParams,
  ) => [...locationKeys.all, 'history', farmId, animalId, params] as const,
};

// ─── Hooks ────────────────────────────────────────────────────────────────────

/**
 * Dernières positions de tous les animaux de la ferme active.
 * Polling toutes les 10s.
 */
export function useFarmLocations(
  options?: Omit<UseQueryOptions<LocationPoint[]>, 'queryKey' | 'queryFn'>,
) {
  const currentFarmId = useFarmStore((state) => state.currentFarmId);

  return useQuery({
    queryKey: locationKeys.farm(currentFarmId),
    queryFn: ({ signal }) => {
      if (!currentFarmId) throw new Error('No farm selected');
      return locationsApi.getLatest(currentFarmId, signal);
    },
    enabled: !!currentFarmId,
    staleTime: Config.STALE_TIME_SHORT,
    refetchInterval: Config.MAP_REFRESH_INTERVAL, // 10s
    ...options,
  });
}

/**
 * Position courante prouvée pour un animal spécifique.
 * Polling toutes les 10s.
 */
export function useAnimalLocation(
  animalId?: number | null,
  options?: Omit<UseQueryOptions<LocationPoint>, 'queryKey' | 'queryFn'>,
) {
  const currentFarmId = useFarmStore((state) => state.currentFarmId);

  return useQuery({
    queryKey: locationKeys.animal(currentFarmId, animalId),
    queryFn: ({ signal }) => {
      if (!currentFarmId || !animalId) throw new Error('Farm ID and Animal ID required');
      return locationsApi.getCurrent(currentFarmId, animalId, signal);
    },
    enabled: !!currentFarmId && !!animalId,
    staleTime: Config.STALE_TIME_SHORT,
    refetchInterval: Config.MAP_REFRESH_INTERVAL, // 10s
    ...options,
  });
}

/**
 * Historique de trajectoire avec segmentation par trous d'observation.
 * Stale time de 2 minutes pour éviter les requêtes répétitives.
 */
export function useLocationHistory(
  animalId?: number | null,
  params?: LocationHistoryParams,
  options?: Omit<UseQueryOptions<LocationHistoryResponse>, 'queryKey' | 'queryFn'>,
) {
  const currentFarmId = useFarmStore((state) => state.currentFarmId);

  return useQuery({
    queryKey: locationKeys.history(currentFarmId, animalId, params),
    queryFn: ({ signal }) => {
      if (!currentFarmId || !animalId) throw new Error('Farm ID and Animal ID required');
      return locationsApi.getHistory(currentFarmId, animalId, params, signal);
    },
    enabled: !!currentFarmId && !!animalId,
    staleTime: 120_000, // 2 minutes
    ...options,
  });
}
