import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { geofencesApi } from '../api/geofences';
import { GeofenceCreate, GeofenceUpdate } from '../types';

const geofenceKeys = {
  farm: (farmId: number | null) => ['geofences', farmId] as const,
};

export function useGeofences(farmId: number | null) {
  return useQuery({
    queryKey: geofenceKeys.farm(farmId),
    queryFn: () => geofencesApi.list(farmId as number),
    enabled: farmId !== null,
  });
}

export function useCreateGeofence(farmId: number | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: GeofenceCreate) => geofencesApi.create(payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: geofenceKeys.farm(farmId) }),
  });
}

export function useUpdateGeofence(farmId: number | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: GeofenceUpdate }) =>
      geofencesApi.update(id, payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: geofenceKeys.farm(farmId) }),
  });
}

export function useDeleteGeofence(farmId: number | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: geofencesApi.remove,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: geofenceKeys.farm(farmId) }),
  });
}
