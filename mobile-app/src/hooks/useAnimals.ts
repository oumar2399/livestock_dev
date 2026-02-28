/**
 * Hooks React Query - Animaux
 *
 * useAnimals()         → liste paginée
 * useAnimal(id)        → détail animal
 * useCreateAnimal()    → mutation création
 * useUpdateAnimal()    → mutation modification
 * useDeleteAnimal()    → mutation suppression
 */
import {
  useQuery,
  useMutation,
  useQueryClient,
  UseQueryOptions,
} from '@tanstack/react-query';
import { animalsApi } from '../api/animals';
import {
  Animal,
  AnimalCreate,
  AnimalList,
  AnimalUpdate,
  AnimalsQueryParams,
} from '../types';
import { Config } from '../constants/config';

// ─── Query Keys ───────────────────────────────────────────────────────────────
// Centralisés ici pour invalidations cohérentes

export const animalKeys = {
  all: ['animals'] as const,
  lists: () => [...animalKeys.all, 'list'] as const,
  list: (params?: AnimalsQueryParams) => [...animalKeys.lists(), params] as const,
  details: () => [...animalKeys.all, 'detail'] as const,
  detail: (id: number) => [...animalKeys.details(), id] as const,
};

// ─── Hooks de lecture ─────────────────────────────────────────────────────────

/**
 * Liste des animaux avec filtres et pagination
 * Se rafraîchit automatiquement toutes les 30s
 */
export function useAnimals(
  params?: AnimalsQueryParams,
  options?: Omit<UseQueryOptions<AnimalList>, 'queryKey' | 'queryFn'>,
) {
  return useQuery({
    queryKey: animalKeys.list(params),
    queryFn: () => animalsApi.list(params),
    staleTime: Config.STALE_TIME_MEDIUM,
    refetchInterval: Config.DASHBOARD_REFRESH_INTERVAL,
    ...options,
  });
}

/**
 * Détail d'un animal par ID
 */
export function useAnimal(
  id: number,
  options?: Omit<UseQueryOptions<Animal>, 'queryKey' | 'queryFn'>,
) {
  return useQuery({
    queryKey: animalKeys.detail(id),
    queryFn: () => animalsApi.getById(id),
    staleTime: Config.STALE_TIME_MEDIUM,
    enabled: id > 0,
    ...options,
  });
}

// ─── Mutations ────────────────────────────────────────────────────────────────

/**
 * Créer un animal
 * Invalide automatiquement le cache de la liste
 */
export function useCreateAnimal() {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: (payload: AnimalCreate) => animalsApi.create(payload),
    onSuccess: (newAnimal) => {
      // Invalider la liste pour forcer re-fetch
      qc.invalidateQueries({ queryKey: animalKeys.lists() });
      // Pré-remplir le cache du détail avec la réponse
      qc.setQueryData(animalKeys.detail(newAnimal.id), newAnimal);
    },
  });
}

/**
 * Modifier un animal
 * Met à jour le cache immédiatement (optimistic update)
 */
export function useUpdateAnimal() {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: AnimalUpdate }) =>
      animalsApi.update(id, payload),
    onSuccess: (updatedAnimal) => {
      // Mettre à jour le cache du détail
      qc.setQueryData(animalKeys.detail(updatedAnimal.id), updatedAnimal);
      // Invalider la liste (le statut/poids a peut-être changé)
      qc.invalidateQueries({ queryKey: animalKeys.lists() });
    },
  });
}

/**
 * Supprimer un animal
 * Retire du cache et invalide la liste
 */
export function useDeleteAnimal() {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: (id: number) => animalsApi.delete(id),
    onSuccess: (_data, deletedId) => {
      qc.removeQueries({ queryKey: animalKeys.detail(deletedId) });
      qc.invalidateQueries({ queryKey: animalKeys.lists() });
    },
  });
}
