/**
 * Hooks React Query - Alertes
 *
 * useAlerts()           → liste avec filtres
 * useUnresolvedCount()  → nombre alertes actives (badge onglet)
 * useAcknowledgeAlert() → mutation acquittement
 * useResolveAlert()     → mutation résolution
 */
import {
  useQuery,
  useMutation,
  useQueryClient,
  UseQueryOptions,
} from '@tanstack/react-query';
import { alertsApi } from '../api/alerts';
import {
  Alert,
  AlertList,
  AlertsQueryParams,
  AlertUpdate,
} from '../types';
import { Config } from '../constants/config';

// ─── Query Keys ───────────────────────────────────────────────────────────────

export const alertKeys = {
  all: ['alerts'] as const,
  lists: () => [...alertKeys.all, 'list'] as const,
  list: (params?: AlertsQueryParams) => [...alertKeys.lists(), params] as const,
};

// ─── Hooks de lecture ─────────────────────────────────────────────────────────

/**
 * Liste des alertes avec filtres optionnels
 * Polling toutes les 15s pour détection rapide nouvelles alertes
 */
export function useAlerts(
  params?: AlertsQueryParams,
  options?: Omit<UseQueryOptions<AlertList>, 'queryKey' | 'queryFn'>,
) {
  return useQuery({
    queryKey: alertKeys.list(params),
    queryFn: () => alertsApi.list(params),
    staleTime: Config.STALE_TIME_SHORT,
    refetchInterval: Config.ALERTS_REFRESH_INTERVAL,
    ...options,
  });
}

/**
 * Alertes non résolues uniquement (pour badge onglet)
 */
export function useActiveAlerts() {
  return useAlerts({ resolved: false, limit: 50 });
}

// ─── Mutations ────────────────────────────────────────────────────────────────

/**
 * Acquitter une alerte ("J'ai vu")
 * Met à jour le cache optimistement avant réponse serveur
 */
export function useAcknowledgeAlert() {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: (id: number) => alertsApi.acknowledge(id),
    onSuccess: (updatedAlert) => {
      // Invalider toutes les listes d'alertes
      qc.invalidateQueries({ queryKey: alertKeys.lists() });
    },
  });
}

/**
 * Résoudre une alerte complètement
 */
export function useResolveAlert() {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: (id: number) => alertsApi.resolve(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: alertKeys.lists() });
    },
  });
}

/**
 * Mise à jour générique (pour cas avancés)
 */
export function useUpdateAlert() {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: AlertUpdate }) =>
      alertsApi.update(id, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: alertKeys.lists() });
    },
  });
}
