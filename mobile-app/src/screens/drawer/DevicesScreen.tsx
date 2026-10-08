/**
 * DevicesScreen - collars of the selected farm.
 * Owners and farmers add collars here (the server returns the secret once) and open a
 * collar for its details, status and health indicators.
 */
import React, { useState } from 'react';
import {
  View, Text, StyleSheet, FlatList,
  ActivityIndicator, RefreshControl, TouchableOpacity,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useNavigation } from '@react-navigation/native';
import DrawerScreenBase from './DrawerScreenBase';
import AddDeviceModal from '../../components/AddDeviceModal';
import { Colors, Spacing, Typography, Radius } from '../../constants/config';
import { timeAgo } from '../../utils/helpers';
import { useFarmStore } from '../../store/farmStore';
import { FarmDevice, useFarmDevices } from '../../hooks/useDevices';
import { DEVICE_STATUS_LABELS, deviceHealthLines } from '../../utils/deviceStatus';

// ─── Status config ────────────────────────────────────────────────────────────

const STATUS_COLORS: Record<string, string> = {
  active:      Colors.primary,
  maintenance: Colors.severity.warning,
  lost:        Colors.severity.critical,
  retired:     Colors.text.muted,
};

const STATUS_ICONS: Record<string, string> = {
  active:      'hardware-chip-outline',
  maintenance: 'construct-outline',
  lost:        'warning-outline',
  retired:     'archive-outline',
};

// ─── Battery helper ───────────────────────────────────────────────────────────

function batteryColor(level: number | null): string {
  if (level === null) return Colors.text.muted;
  if (level > 50) return Colors.primary;
  if (level > 25) return Colors.severity.warning;
  return Colors.severity.critical;
}

function batteryIcon(level: number | null): string {
  if (level === null) return 'battery-dead-outline';
  if (level > 80) return 'battery-full-outline';
  if (level > 50) return 'battery-half-outline';
  if (level > 25) return 'battery-low-outline';
  return 'battery-dead-outline';
}

// ─── Device card ──────────────────────────────────────────────────────────────

function DeviceCard({ device, onPress }: { device: FarmDevice; onPress: () => void }) {
  const statusColor = STATUS_COLORS[device.status] ?? Colors.text.muted;
  const batColor    = batteryColor(device.battery_capacity);
  const health      = deviceHealthLines(device.health);

  return (
    <TouchableOpacity style={styles.card} onPress={onPress} activeOpacity={0.8}>
      <View style={styles.cardHeader}>
        <View style={[styles.deviceIcon, { backgroundColor: statusColor + '20' }]}>
          <Ionicons name={STATUS_ICONS[device.status] as any} size={22} color={statusColor} />
        </View>
        <View style={styles.cardInfo}>
          <Text style={styles.deviceId}>{device.id}</Text>
          <Text style={styles.deviceModel}>
            {device.assigned_animal ? `On ${device.assigned_animal.name}` : 'Not assigned'}
          </Text>
        </View>
        <View style={[styles.statusBadge, { backgroundColor: statusColor + '20', borderColor: statusColor + '50' }]}>
          <Text style={[styles.statusText, { color: statusColor }]}>{DEVICE_STATUS_LABELS[device.status] ?? device.status}</Text>
        </View>
        <Ionicons name="chevron-forward" size={16} color={Colors.text.muted} />
      </View>

      <View style={styles.cardDetails}>
        <View style={styles.detailItem}>
          <Ionicons name={batteryIcon(device.battery_capacity) as any} size={14} color={batColor} />
          <Text style={[styles.detailText, { color: batColor }]}>
            {device.battery_capacity !== null ? `${device.battery_capacity}%` : 'Unknown'}
          </Text>
        </View>
        <View style={styles.detailItem}>
          <Ionicons name="time-outline" size={14} color={Colors.text.muted} />
          <Text style={styles.detailText}>{device.last_seen ? timeAgo(device.last_seen) : 'Never'}</Text>
        </View>
      </View>

      {/* Health indicators (offline, needs attention) — never change the status by themselves */}
      {health.map((line) => (
        <Text key={line.label} style={[styles.healthText, { color: line.critical ? Colors.severity.critical : Colors.severity.warning }]}>
          {line.label}
        </Text>
      ))}
      {device.ingestion_revoked_at && <Text style={styles.notes}>Reception revoked</Text>}
      {device.notes && <Text style={styles.notes}>{device.notes}</Text>}
    </TouchableOpacity>
  );
}

// ─── Screen ───────────────────────────────────────────────────────────────────

export default function DevicesScreen() {
  const navigation = useNavigation<any>();
  const currentFarm = useFarmStore((state) =>
    state.farms.find((farm) => farm.id === state.currentFarmId),
  );
  const canManageDevices = currentFarm?.permissions.includes('manage_devices') ?? false;
  const { data, isLoading, refetch, isRefetching } = useFarmDevices();
  const devices = data ?? [];
  const [showAdd, setShowAdd] = useState(false);
  const activeCount = devices.filter(d => d.status === 'active').length;

  return (
    <DrawerScreenBase
      title="M5Stack Devices"
      subtitle={`${devices.length} registered · ${activeCount} active`}
      rightAction={canManageDevices && currentFarm ? (
        <TouchableOpacity onPress={() => setShowAdd(true)} hitSlop={8} accessibilityLabel="Add a device">
          <Ionicons name="add-circle-outline" size={24} color={Colors.primary} />
        </TouchableOpacity>
      ) : undefined}
    >
      {isLoading ? (
        <View style={styles.center}>
          <ActivityIndicator color={Colors.primary} size="large" />
        </View>
      ) : (
        <FlatList
          data={devices}
          keyExtractor={d => d.id}
          contentContainerStyle={styles.list}
          refreshControl={<RefreshControl refreshing={isRefetching} onRefresh={() => { void refetch(); }} tintColor={Colors.primary} />}
          renderItem={({ item }) => (
            <DeviceCard device={item} onPress={() => navigation.navigate('DeviceDetail', { deviceId: item.id })} />
          )}
          ListEmptyComponent={
            <View style={styles.empty}>
              <Ionicons name="hardware-chip-outline" size={48} color={Colors.text.muted} />
              <Text style={styles.emptyTitle}>No devices registered</Text>
              <Text style={styles.emptyText}>
                {canManageDevices ? 'Add a collar with the + button.' : 'Ask the farm owner or farmer to add collars.'}
              </Text>
            </View>
          }
        />
      )}
      {currentFarm && (
        <AddDeviceModal visible={showAdd} farmId={currentFarm.id} farmName={currentFarm.name} onClose={() => setShowAdd(false)} />
      )}
    </DrawerScreenBase>
  );
}

// ─── Styles ──────────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  list:   { padding: Spacing.base, gap: Spacing.sm },

  card: {
    backgroundColor: Colors.bg.card,
    borderRadius: Radius.lg,
    padding: Spacing.md,
    borderWidth: 1,
    borderColor: Colors.border.default,
    gap: Spacing.sm,
  },
  cardHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.md,
  },
  deviceIcon: {
    width: 46, height: 46, borderRadius: 23,
    alignItems: 'center', justifyContent: 'center',
  },
  cardInfo:    { flex: 1 },
  deviceId:    { fontSize: Typography.base, fontWeight: '700', color: Colors.text.primary },
  deviceModel: { fontSize: Typography.xs, color: Colors.text.muted, marginTop: 2 },

  statusBadge: {
    paddingHorizontal: Spacing.sm,
    paddingVertical: 4,
    borderRadius: Radius.full,
    borderWidth: 1,
  },
  statusText: { fontSize: Typography.xs, fontWeight: '700' },

  cardDetails: {
    flexDirection: 'row',
    gap: Spacing.base,
    paddingTop: Spacing.xs,
    borderTopWidth: 1,
    borderTopColor: Colors.border.default,
  },
  detailItem:  { flexDirection: 'row', alignItems: 'center', gap: 4 },
  detailText:  { fontSize: Typography.xs, color: Colors.text.muted },

  healthText: { fontSize: Typography.xs, fontWeight: '600' },

  notes: {
    fontSize: Typography.xs,
    color: Colors.text.secondary,
    fontStyle: 'italic',
    paddingTop: Spacing.xs,
  },

  empty: {
    alignItems: 'center',
    padding: Spacing['2xl'],
    gap: Spacing.md,
  },
  emptyTitle: {
    fontSize: Typography.base, fontWeight: '700',
    color: Colors.text.primary,
  },
  emptyText: {
    fontSize: Typography.sm, color: Colors.text.muted,
    textAlign: 'center', lineHeight: 20,
  },
});
