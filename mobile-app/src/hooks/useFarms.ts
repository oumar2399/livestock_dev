/**
 * Hooks React Query - Fermes
 *
 * useFarms()        → liste des fermes accessibles
 * useFarm(id)       → détail d'une ferme
 * useCreateFarm()   → mutation création avec auto-sélection et invalidation
 * useUpdateFarm()   → mutation modification de ferme
 */
import {
  useQuery,
  useMutation,
  useQueryClient,
  UseQueryOptions,
} from '@tanstack/react-query';
import { farmsApi } from '../api/farms';
import { FarmAccess, FarmCreateInput, FarmUpdateInput } from '../types';
import { Config } from '../constants/config';
import { useFarmStore } from '../store/farmStore';

export const farmKeys = {
  all: ['farms'] as const,
  lists: () => [...farmKeys.all, 'list'] as const,
  details: () => [...farmKeys.all, 'detail'] as const,
  detail: (id: number) => [...farmKeys.details(), id] as const,
};

/**
 * Liste des fermes accessibles
 */
export function useFarms(
  options?: Omit<UseQueryOptions<FarmAccess[]>, 'queryKey' | 'queryFn'>,
) {
  return useQuery({
    queryKey: farmKeys.lists(),
    queryFn: () => farmsApi.list(),
    staleTime: Config.STALE_TIME_LONG,
    ...options,
  });
}

/**
 * Détail d'une ferme par ID
 */
export function useFarm(
  id: number | null,
  options?: Omit<UseQueryOptions<FarmAccess>, 'queryKey' | 'queryFn'>,
) {
  return useQuery({
    queryKey: farmKeys.detail(id ?? 0),
    queryFn: () => farmsApi.getById(id!),
    staleTime: Config.STALE_TIME_LONG,
    enabled: id !== null && id > 0,
    ...options,
  });
}

/**
 * Créer une ferme
 * Après création, recharge les fermes dans le store et sélectionne la nouvelle ferme
 */
export function useCreateFarm() {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: (payload: FarmCreateInput) => farmsApi.create(payload),
    onSuccess: async (newFarm) => {
      qc.invalidateQueries({ queryKey: farmKeys.lists() });
      qc.setQueryData(farmKeys.detail(newFarm.id), newFarm);
      // Recharger le farmStore et sélectionner la nouvelle ferme
      await useFarmStore.getState().loadFarms();
      await useFarmStore.getState().selectFarm(newFarm.id);
    },
  });
}

/**
 * Modifier une ferme
 */
export function useUpdateFarm() {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: FarmUpdateInput }) =>
      farmsApi.update(id, payload),
    onSuccess: async (updatedFarm) => {
      qc.setQueryData(farmKeys.detail(updatedFarm.id), updatedFarm);
      qc.invalidateQueries({ queryKey: farmKeys.lists() });
      await useFarmStore.getState().loadFarms();
    },
  });
}
