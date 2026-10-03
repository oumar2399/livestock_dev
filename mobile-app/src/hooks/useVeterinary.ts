/**
 * Hooks React Query pour le workflow vétérinaire (Lot E)
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  veterinaryApi,
  VeterinaryCaseCreatePayload,
  VeterinaryCaseUpdatePayload,
  VeterinaryEntryCreatePayload,
} from '../api/veterinary';
import { Config } from '../constants/config';
import { useFarmStore } from '../store/farmStore';

export const veterinaryKeys = {
  all: ['veterinary'] as const,
  farmCases: (farmId?: number | null, params?: object) =>
    [...veterinaryKeys.all, 'farmCases', farmId, params] as const,
  caseDetail: (farmId?: number | null, caseId?: number) =>
    [...veterinaryKeys.all, 'caseDetail', farmId, caseId] as const,
  animalCases: (animalId?: number) =>
    [...veterinaryKeys.all, 'animalCases', animalId] as const,
};

export function useFarmVeterinaryCases(params?: {
  animal_id?: number;
  status?: string;
  linked_alert_id?: number;
}) {
  const currentFarmId = useFarmStore((state) => state.currentFarmId);

  return useQuery({
    queryKey: veterinaryKeys.farmCases(currentFarmId, params),
    queryFn: () => {
      if (!currentFarmId) throw new Error('No farm selected');
      return veterinaryApi.listFarmCases(currentFarmId, params);
    },
    enabled: currentFarmId !== null,
    staleTime: Config.STALE_TIME_MEDIUM,
  });
}

export function useVeterinaryCaseDetail(caseId?: number) {
  const currentFarmId = useFarmStore((state) => state.currentFarmId);

  return useQuery({
    queryKey: veterinaryKeys.caseDetail(currentFarmId, caseId),
    queryFn: () => {
      if (!currentFarmId || !caseId) throw new Error('Farm or case id missing');
      return veterinaryApi.getCaseDetail(currentFarmId, caseId);
    },
    enabled: currentFarmId !== null && caseId !== undefined,
    staleTime: Config.STALE_TIME_MEDIUM,
  });
}

export function useAnimalVeterinaryCases(animalId?: number) {
  return useQuery({
    queryKey: veterinaryKeys.animalCases(animalId),
    queryFn: () => {
      if (!animalId) throw new Error('Animal id missing');
      return veterinaryApi.listAnimalCases(animalId);
    },
    enabled: animalId !== undefined,
    staleTime: Config.STALE_TIME_MEDIUM,
  });
}

export function useCreateVeterinaryCase() {
  const queryClient = useQueryClient();
  const currentFarmId = useFarmStore((state) => state.currentFarmId);

  return useMutation({
    mutationFn: (payload: VeterinaryCaseCreatePayload) => {
      if (!currentFarmId) throw new Error('No farm selected');
      return veterinaryApi.createCase(currentFarmId, payload);
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: veterinaryKeys.all });
    },
  });
}

export function useUpdateVeterinaryCase() {
  const queryClient = useQueryClient();
  const currentFarmId = useFarmStore((state) => state.currentFarmId);

  return useMutation({
    mutationFn: ({
      caseId,
      payload,
    }: {
      caseId: number;
      payload: VeterinaryCaseUpdatePayload;
    }) => {
      if (!currentFarmId) throw new Error('No farm selected');
      return veterinaryApi.updateCase(currentFarmId, caseId, payload);
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: veterinaryKeys.all });
    },
  });
}

export function useAddCaseEntry() {
  const queryClient = useQueryClient();
  const currentFarmId = useFarmStore((state) => state.currentFarmId);

  return useMutation({
    mutationFn: ({
      caseId,
      payload,
    }: {
      caseId: number;
      payload: VeterinaryEntryCreatePayload;
    }) => {
      if (!currentFarmId) throw new Error('No farm selected');
      return veterinaryApi.addEntry(currentFarmId, caseId, payload);
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({
        queryKey: veterinaryKeys.caseDetail(currentFarmId, variables.caseId),
      });
      queryClient.invalidateQueries({ queryKey: veterinaryKeys.all });
    },
  });
}
