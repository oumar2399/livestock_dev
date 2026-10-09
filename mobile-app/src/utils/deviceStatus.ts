import type { PickerOption } from '../components/SearchablePicker';
import apiClient from '../api/client';
import type { DeviceHealth } from '../hooks/useDevices';
import { showApiError } from './apiErrors';
import { timeAgo } from './helpers';
import { showDialog } from '../components/dialog';

export const DEVICE_STATUS_LABELS: Record<string, string> = {
  active: 'Active',
  maintenance: 'Maintenance',
  lost: 'Lost',
  retired: 'Retired',
};

const ATTENTION_LABELS: Record<string, string> = {
  low_battery: 'Low battery (≤ 25 %)',
  no_gps_fix: 'No GPS fix for over 1 h',
  battery_unknown: 'Battery unreadable for over 1 h',
};

/**
 * Health indicators as display lines. Indicators only: the status "lost" is still
 * set by a person (it changes geofencing and data quality).
 */
export function deviceHealthLines(health?: DeviceHealth | null): { label: string; critical: boolean }[] {
  if (!health) return [];
  const lines: { label: string; critical: boolean }[] = [];
  if (health.offline) {
    lines.push({
      label: health.offline_since ? `Offline since ${timeAgo(health.offline_since)}` : 'Never reported',
      critical: true,
    });
  }
  for (const reason of health.needs_attention) {
    lines.push({ label: ATTENTION_LABELS[reason] ?? reason, critical: false });
  }
  return lines;
}

/** Short suffix for the collar line on the herd card ("offline", "needs attention"). */
export function collarHealthSuffix(health?: DeviceHealth | null): string {
  if (!health) return '';
  if (health.offline) return health.offline_since ? ` · offline ${timeAgo(health.offline_since)}` : ' · never reported';
  return health.needs_attention.length > 0 ? ' · needs attention' : '';
}

/** Status change with the "collar recovered" confirmation when leaving "lost". */
export function changeDeviceStatus(deviceId: string, currentStatus: string, onDone: () => void) {
  const patch = async (body: object, failure: string) => {
    try {
      await apiClient.patch(`/devices/${encodeURIComponent(deviceId)}`, body);
      onDone();
    } catch (error) {
      showApiError(error, 'Could not update', failure);
    }
  };
  showDialog('Change Device Status', `Update status for ${deviceId}:`, [
    ...Object.keys(DEVICE_STATUS_LABELS).filter((s) => s !== currentStatus).map((s) => ({
      text: DEVICE_STATUS_LABELS[s],
      onPress: () => {
        if (currentStatus === 'lost' && s === 'active') {
          showDialog('Collar recovered', 'Is this collar secured on the correct animal again?', [
            { text: 'Cancel', style: 'cancel' },
            { text: 'Confirm remounted', onPress: () => { void patch({ status: s, confirm_remounted: true }, 'Unable to confirm collar recovery.'); } },
          ]);
          return;
        }
        void patch({ status: s }, 'Failed to update device status.');
      },
    })),
    { text: 'Cancel', style: 'cancel' as const },
  ]);
}

/**
 * Devices that may be chosen for an animal: the farm's collars not assigned to another
 * animal (the animal's own collar stays in the list). The server checks it again.
 */
export function assignableDevices<T extends { id: string; assigned_animal?: { id: number } | null }>(
  devices: T[] | undefined, animalId?: number,
): T[] {
  return (devices ?? []).filter((device) => !device.assigned_animal || device.assigned_animal.id === animalId);
}

/** Collar as a picker option: its ID, then status and health ("Active · offline 2 h"). */
export function deviceOption(device: {
  id: string; status: string; transport_id?: number | null; health?: DeviceHealth | null;
}): PickerOption {
  const status = DEVICE_STATUS_LABELS[device.status] ?? device.status;
  return {
    value: device.id,
    label: device.id,
    detail: status + collarHealthSuffix(device.health),
    keywords: device.transport_id != null ? [String(device.transport_id)] : [],
  };
}

/** Lines to copy into m5stack/device_config.py (manual until LoRaWAN pairing). */
export function deviceConfigLines(deviceId: string, transportId: number, secret: string): string {
  return `DEVICE_ID = "${deviceId}"\nTRANSPORT_ID = ${transportId}\nDEVICE_SECRET = "${secret}"`;
}
