/**
 * Hooks React Query pour les notifications et préférences
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  getNotificationPreferences,
  updateNotificationPreferences,
  registerPushDevice,
  deactivatePushDevice,
  NotificationPreference,
  NotificationPreferenceUpdatePayload,
} from '../api/notifications';
import { Config } from '../constants/config';
import { useFarmStore } from '../store/farmStore';

export const notificationKeys = {
  all: ['notifications'] as const,
  preferences: (farmId?: number | null) => [...notificationKeys.all, 'preferences', farmId] as const,
};

export function useNotificationPreferences(farmIdOverride?: number) {
  const currentFarmId = useFarmStore((state) => state.currentFarmId);
  const targetFarmId = farmIdOverride !== undefined ? farmIdOverride : (currentFarmId ?? undefined);

  return useQuery({
    queryKey: notificationKeys.preferences(targetFarmId),
    queryFn: () => getNotificationPreferences(targetFarmId),
    staleTime: Config.STALE_TIME_MEDIUM,
  });
}

export function useUpdateNotificationPreferences() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: NotificationPreferenceUpdatePayload) =>
      updateNotificationPreferences(payload),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({
        queryKey: notificationKeys.preferences(variables.farm_id),
      });
      queryClient.invalidateQueries({
        queryKey: notificationKeys.preferences(undefined),
      });
    },
  });
}

export function useRegisterPushDevice() {
  return useMutation({
    mutationFn: ({
      pushToken,
      platform,
      provider,
    }: {
      pushToken: string;
      platform?: string;
      provider?: string;
    }) => registerPushDevice(pushToken, platform, provider),
  });
}

export function useDeactivatePushDevice() {
  return useMutation({
    mutationFn: (pushToken: string) => deactivatePushDevice(pushToken),
  });
}
