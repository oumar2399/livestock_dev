/**
 * Hooks React Query - Télémétrie
 *
 * useTelemetryLatest()     → positions actuelles (polling 10s pour carte)
 * useTelemetryHistory()    → historique animal (graphiques)
 */
import { useQuery, UseQueryOptions } from '@tanstack/react-query';
import { telemetryApi } from '../api/telemetry';
import {
  TelemetryLatest,
  TelemetryLatestParams,
  TelemetryRecord,
} from '../types';
import { Config } from '../constants/config';

// ─── Query Keys ───────────────────────────────────────────────────────────────

export const telemetryKeys = {
  all: ['telemetry'] as const,
  latest: (params?: TelemetryLatestParams) => [...telemetryKeys.all, 'latest', params] as const,
  history: (animalId: number, hours: number) =>
    [...telemetryKeys.all, 'history', animalId, hours] as const,
};

// ─── Hooks ────────────────────────────────────────────────────────────────────

/**
 * Dernières positions de tous les animaux
 * Polling toutes les 10s = synchronisé avec refresh M5Stack
 *
 * Utilisé par MapScreen pour les marqueurs temps réel
 */
export function useTelemetryLatest(
  params?: TelemetryLatestParams,
  options?: Omit<UseQueryOptions<TelemetryLatest[]>, 'queryKey' | 'queryFn'>,
) {
  return useQuery({
    queryKey: telemetryKeys.latest(params),
    queryFn: () => telemetryApi.getLatest(params),
    staleTime: Config.STALE_TIME_SHORT,
    refetchInterval: Config.MAP_REFRESH_INTERVAL,    // 10s
    refetchIntervalInBackground: false,               // Stop si app en arrière-plan
    ...options,
  });
}

/**
 * Historique télémétrie d'un animal pour graphiques
 * Cache 5 minutes (données historiques stables)
 *
 * @param animalId - ID de l'animal
 * @param hours    - Fenêtre temporelle (1-168, défaut 24h)
 */
export function useTelemetryHistory(
  animalId: number,
  hours: number = 24,
  options?: Omit<UseQueryOptions<TelemetryRecord[]>, 'queryKey' | 'queryFn'>,
) {
  return useQuery({
    queryKey: telemetryKeys.history(animalId, hours),
    queryFn: () => telemetryApi.getHistory(animalId, hours),
    staleTime: 0,
    enabled: animalId > 0,
    ...options,
  });
}
