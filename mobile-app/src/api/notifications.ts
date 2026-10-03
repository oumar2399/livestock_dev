/**
 * Client API Notifications :
 * - Enregistrement du token push
 * - Désactivation du token push (logout)
 * - Lecture et mise à jour des préférences
 */
import apiClient from './client';

export interface PushDevice {
  id: number;
  user_id: number;
  provider: string;
  push_token: string;
  platform?: string | null;
  active: boolean;
  created_at: string;
  last_seen_at: string;
}

export interface NotificationPreference {
  id: number;
  user_id: number;
  farm_id?: number | null;
  categories: string[];
  min_severity: 'info' | 'warning' | 'critical';
  enabled: boolean;
  updated_at: string;
}

export interface NotificationPreferenceUpdatePayload {
  farm_id?: number | null;
  categories?: string[];
  min_severity?: 'info' | 'warning' | 'critical';
  enabled?: boolean;
}

export const registerPushDevice = async (
  pushToken: string,
  platform?: string,
  provider: string = 'expo',
): Promise<PushDevice> => {
  const response = await apiClient.post<PushDevice>('/notifications/devices', {
    push_token: pushToken,
    platform: platform ?? null,
    provider,
  });
  return response.data;
};

export const deactivatePushDevice = async (pushToken: string): Promise<void> => {
  await apiClient.delete(`/notifications/devices/${encodeURIComponent(pushToken)}`);
};

export const getNotificationPreferences = async (
  farmId?: number,
): Promise<NotificationPreference[]> => {
  const params = farmId !== undefined ? { farm_id: farmId } : undefined;
  const response = await apiClient.get<NotificationPreference[]>('/notifications/preferences', {
    params,
  });
  return response.data;
};

export const updateNotificationPreferences = async (
  payload: NotificationPreferenceUpdatePayload,
): Promise<NotificationPreference> => {
  const response = await apiClient.put<NotificationPreference>(
    '/notifications/preferences',
    payload,
  );
  return response.data;
};
