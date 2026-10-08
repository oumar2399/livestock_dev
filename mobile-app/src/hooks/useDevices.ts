/**
 * Collars of the selected farm (GET /devices/?farm_id=…), readable by every member.
 * Source of the collar status shown next to each animal, of the device details
 * screen and of the health indicators (offline, needs attention).
 */
import { useMutation, useQuery } from '@tanstack/react-query';

import apiClient from '../api/client';
import { pollUnlessGone } from '../api/queryPolicy';
import { queryClient } from '../api/queryClient';
import { Config } from '../constants/config';
import { useFarmStore } from '../store/farmStore';

export type DeviceStatus = 'active' | 'maintenance' | 'lost' | 'retired';
export type AttentionReason = 'low_battery' | 'no_gps_fix' | 'battery_unknown';

export interface DeviceHealth {
  offline: boolean;
  offline_since: string | null;
  last_fix_at: string | null;
  needs_attention: AttentionReason[];
}

export interface FarmDevice {
  id: string;
  farm_id: number | null;
  transport_id?: number | null;
  model?: string | null;
  firmware_version?: string | null;
  status: string;
  last_seen: string | null;
  battery_capacity: number | null;
  notes?: string | null;
  created_at?: string;
  ingestion_revoked_at?: string | null;
  assigned_animal?: { id: number; name: string } | null;
  last_position?: { latitude: number; longitude: number; time: string } | null;
  health?: DeviceHealth | null;
}

/** POST /devices answer: the only time the secret is shown. */
export interface ProvisionedDevice extends FarmDevice {
  transport_id: number;
  device_secret: string;
}

export const deviceKeys = {
  all: ['devices'] as const,
  farm: (farmId: number | null) => ['devices', farmId] as const,
  detail: (deviceId: string) => ['devices', 'detail', deviceId] as const,
};

export function useFarmDevices() {
  const currentFarmId = useFarmStore((state) => state.currentFarmId);
  return useQuery({
    queryKey: deviceKeys.farm(currentFarmId),
    queryFn: async ({ signal }) => {
      const { data } = await apiClient.get<FarmDevice[]>('/devices/', {
        params: { farm_id: currentFarmId }, signal,
      });
      return data;
    },
    enabled: currentFarmId !== null,
    staleTime: Config.STALE_TIME_SHORT,
    refetchInterval: pollUnlessGone(Config.DASHBOARD_REFRESH_INTERVAL),
  });
}

export function useDevice(deviceId: string) {
  return useQuery({
    queryKey: deviceKeys.detail(deviceId),
    queryFn: async ({ signal }) => (await apiClient.get<FarmDevice>(`/devices/${encodeURIComponent(deviceId)}`, { signal })).data,
    staleTime: Config.STALE_TIME_SHORT,
    refetchInterval: pollUnlessGone(Config.DASHBOARD_REFRESH_INTERVAL),
  });
}

/** Everything that shows a collar status or a collar position. */
export function refreshDeviceViews() {
  for (const key of ['devices', 'telemetry', 'activity', 'animals', 'alerts', 'locations']) {
    void queryClient.invalidateQueries({ queryKey: [key] });
  }
}

export function useCreateDevice() {
  return useMutation({
    mutationFn: async (payload: { device_id: string; farm_id: number }) =>
      (await apiClient.post<ProvisionedDevice>('/devices/', payload)).data,
    onSuccess: refreshDeviceViews,
  });
}
