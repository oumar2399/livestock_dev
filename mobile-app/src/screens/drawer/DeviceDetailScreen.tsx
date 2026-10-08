/**
 * Device details: status, last seen, battery, last known position, assigned animal,
 * health indicators. "Offline" and "needs attention" are indicators only; the status
 * "lost" is still set by a person here.
 */
import React from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useNavigation, useRoute } from '@react-navigation/native';

import DrawerScreenBase from './DrawerScreenBase';
import { Colors, Radius, Spacing, Typography } from '../../constants/config';
import { refreshDeviceViews, useDevice } from '../../hooks/useDevices';
import { useFarmStore } from '../../store/farmStore';
import { collarStatus, formatBattery, formatDateTime, timeAgo } from '../../utils/helpers';
import { changeDeviceStatus, deviceHealthLines, DEVICE_STATUS_LABELS } from '../../utils/deviceStatus';
import { ErrorState, InfoRow, LoadingState } from '../../components/ui';

export default function DeviceDetailScreen() {
  const navigation = useNavigation<any>();
  const route = useRoute<any>();
  const deviceId: string = route.params?.deviceId;
  const { data: device, isLoading, isError, refetch } = useDevice(deviceId);
  const canManage = useFarmStore((state) =>
    state.farms.find((farm) => farm.id === state.currentFarmId)?.permissions.includes('manage_devices') ?? false);

  if (isLoading) return <LoadingState message="Loading device…" />;
  if (isError || !device) return <ErrorState message="Device not found" onRetry={() => refetch()} />;

  const collar = collarStatus(device.status);
  const health = deviceHealthLines(device.health);
  const position = device.last_position;

  return (
    <DrawerScreenBase title={device.id} subtitle={collar.label}>
      <ScrollView contentContainerStyle={styles.content}>
        {health.length > 0 && (
          <View style={styles.healthBox}>
            {health.map((line) => (
              <View key={line.label} style={styles.healthRow}>
                <Ionicons name={line.critical ? 'cloud-offline-outline' : 'alert-circle-outline'} size={16}
                  color={line.critical ? Colors.severity.critical : Colors.severity.warning} />
                <Text style={[styles.healthText, { color: line.critical ? Colors.severity.critical : Colors.severity.warning }]}>
                  {line.label}
                </Text>
              </View>
            ))}
            <Text style={styles.hint}>Indicators only — set the status to Lost yourself if the collar is lost.</Text>
          </View>
        )}

        <View style={styles.card}>
          <InfoRow label="Status" value={DEVICE_STATUS_LABELS[device.status] ?? device.status} icon="pulse-outline" />
          <InfoRow label="Last seen" value={device.last_seen ? timeAgo(device.last_seen) : 'Never'} icon="time-outline" />
          <InfoRow label="Battery" value={formatBattery(device.battery_capacity)} icon="battery-half-outline" />
          <InfoRow label="Transport ID" value={device.transport_id != null ? String(device.transport_id) : '–'} icon="key-outline" />
          <InfoRow label="Assigned animal" value={device.assigned_animal?.name ?? 'None'} icon="paw-outline" />
          <InfoRow
            label="Last position"
            value={position ? `${position.latitude.toFixed(5)}, ${position.longitude.toFixed(5)} · ${formatDateTime(position.time)}` : 'No position yet'}
            icon="location-outline"
            last
          />
        </View>

        {position && (
          <TouchableOpacity
            style={styles.button}
            onPress={() => navigation.navigate('HomeTabs', {
              screen: 'Map',
              params: { focusPosition: { latitude: position.latitude, longitude: position.longitude, label: `Collar ${device.id} — last known position` } },
            })}
          >
            <Ionicons name="map-outline" size={18} color={Colors.primary} />
            <Text style={styles.buttonText}>Show on map</Text>
          </TouchableOpacity>
        )}
        {device.assigned_animal && (
          <TouchableOpacity
            style={styles.button}
            onPress={() => navigation.navigate('HomeTabs', {
              screen: 'Animals', params: { screen: 'AnimalDetail', params: { animalId: device.assigned_animal!.id } },
            })}
          >
            <Ionicons name="paw-outline" size={18} color={Colors.primary} />
            <Text style={styles.buttonText}>Open {device.assigned_animal.name}</Text>
          </TouchableOpacity>
        )}
        {canManage && (
          <TouchableOpacity
            style={styles.button}
            onPress={() => changeDeviceStatus(device.id, device.status, () => { refreshDeviceViews(); void refetch(); })}
          >
            <Ionicons name="swap-horizontal-outline" size={18} color={Colors.primary} />
            <Text style={styles.buttonText}>Change status</Text>
          </TouchableOpacity>
        )}
      </ScrollView>
    </DrawerScreenBase>
  );
}

const styles = StyleSheet.create({
  content: { padding: Spacing.base, gap: Spacing.md },
  card: { backgroundColor: Colors.bg.card, borderRadius: Radius.lg, borderWidth: 1, borderColor: Colors.border.default, paddingHorizontal: Spacing.md },
  healthBox: { backgroundColor: Colors.bg.card, borderRadius: Radius.lg, borderWidth: 1, borderColor: Colors.severity.warning, padding: Spacing.md, gap: Spacing.xs },
  healthRow: { flexDirection: 'row', alignItems: 'center', gap: Spacing.xs },
  healthText: { fontSize: Typography.sm, fontWeight: '600' },
  hint: { fontSize: Typography.xs, color: Colors.text.muted, marginTop: Spacing.xs },
  button: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: Spacing.xs,
    paddingVertical: Spacing.md, borderRadius: Radius.md, borderWidth: 1, borderColor: Colors.primary,
  },
  buttonText: { color: Colors.primary, fontWeight: '700', fontSize: Typography.sm },
});
