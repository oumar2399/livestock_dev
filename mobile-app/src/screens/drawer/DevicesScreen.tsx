/**
 * DevicesScreen - M5Stack device management
 * Data comes from /devices table (auto-registered on first telemetry)
 * No more duplicate keys — device_id is primary key in devices table
 */
import React, { useEffect, useState } from 'react';
import {
  View, Text, StyleSheet, FlatList,
  ActivityIndicator, RefreshControl, TouchableOpacity, Alert,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import DrawerScreenBase from './DrawerScreenBase';
import { Colors, Spacing, Typography, Radius } from '../../constants/config';
import { timeAgo } from '../../utils/helpers';
import apiClient from '../../api/client';

// ─── Types ────────────────────────────────────────────────────────────────────
interface Device {
  id:               string;
  farm_id:          number | null;
  model:            string | null;
  firmware_version: string | null;
  last_seen:        string | null;
  battery_capacity: number | null;
  status:           'active' | 'maintenance' | 'lost' | 'retired';
  notes:            string | null;
  created_at:       string;
}

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

const STATUS_LABELS: Record<string, string> = {
  active:      'Active',
  maintenance: 'Maintenance',
  lost:        'Lost',
  retired:     'Retired',
};

// ─── Battery helper ───────────────────────────────────────────────────────────

function batteryColor(level: number | null): string {
  if (level === null) return Colors.text.muted;
  if (level > 50) return Colors.primary;
  if (level > 20) return Colors.severity.warning;
  return Colors.severity.critical;
}

function batteryIcon(level: number | null): string {
  if (level === null) return 'battery-dead-outline';
  if (level > 80) return 'battery-full-outline';
  if (level > 50) return 'battery-half-outline';
  if (level > 20) return 'battery-low-outline';
  return 'battery-dead-outline';
}

// ─── Device card ──────────────────────────────────────────────────────────────

function DeviceCard({
  device,
  onChangeStatus,
}: {
  device: Device;
  onChangeStatus: (id: string, status: string) => void;
}) {
  const statusColor = STATUS_COLORS[device.status] ?? Colors.text.muted;
  const batColor    = batteryColor(device.battery_capacity);

  return (
    <View style={styles.card}>
      {/* Icon + ID */}
      <View style={styles.cardHeader}>
        <View style={[styles.deviceIcon, { backgroundColor: statusColor + '20' }]}>
          <Ionicons
            name={STATUS_ICONS[device.status] as any}
            size={22}
            color={statusColor}
          />
        </View>
        <View style={styles.cardInfo}>
          <Text style={styles.deviceId}>{device.id}</Text>
          <Text style={styles.deviceModel}>{device.model ?? 'M5Stack M5GO'}</Text>
        </View>
        {/* Status badge — tap to change */}
        <TouchableOpacity
          style={[styles.statusBadge, { backgroundColor: statusColor + '20', borderColor: statusColor + '50' }]}
          onPress={() => onChangeStatus(device.id, device.status)}
        >
          <Text style={[styles.statusText, { color: statusColor }]}>
            {STATUS_LABELS[device.status]}
          </Text>
        </TouchableOpacity>
      </View>

      {/* Details row */}
      <View style={styles.cardDetails}>
        {/* Battery */}
        <View style={styles.detailItem}>
          <Ionicons name={batteryIcon(device.battery_capacity) as any} size={14} color={batColor} />
          <Text style={[styles.detailText, { color: batColor }]}>
            {device.battery_capacity !== null ? `${device.battery_capacity}%` : 'Unknown'}
          </Text>
        </View>

        {/* Last seen */}
        <View style={styles.detailItem}>
          <Ionicons name="time-outline" size={14} color={Colors.text.muted} />
          <Text style={styles.detailText}>
            {device.last_seen ? timeAgo(device.last_seen) : 'Never'}
          </Text>
        </View>

        {/* Registered */}
        <View style={styles.detailItem}>
          <Ionicons name="calendar-outline" size={14} color={Colors.text.muted} />
          <Text style={styles.detailText}>
            {new Date(device.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
          </Text>
        </View>
      </View>

      {/* Notes if any */}
      {device.notes && (
        <Text style={styles.notes}>{device.notes}</Text>
      )}
    </View>
  );
}

// ─── Screen ───────────────────────────────────────────────────────────────────

export default function DevicesScreen() {
  const [devices,    setDevices]    = useState<Device[]>([]);
  const [loading,    setLoading]    = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = async () => {
    try {
      const { data } = await apiClient.get('/devices/');
      setDevices(data);
    } catch {
      // Silently fail — devices table might be empty on first launch
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => { load(); }, []);

  // Change device status via PATCH /devices/{id}
  const handleChangeStatus = (deviceId: string, currentStatus: string) => {
    const statuses = ['active', 'maintenance', 'lost', 'retired'];
    Alert.alert(
      'Change Device Status',
      `Update status for ${deviceId}:`,
      [
        ...statuses
          .filter(s => s !== currentStatus)
          .map(s => ({
            text: STATUS_LABELS[s],
            onPress: async () => {
              try {
                await apiClient.patch(`/devices/${deviceId}`, { status: s });
                load();
              } catch {
                Alert.alert('Error', 'Failed to update device status.');
              }
            },
          })),
        { text: 'Cancel', style: 'cancel' as const },
      ]
    );
  };

  const activeCount = devices.filter(d => d.status === 'active').length;

  return (
    <DrawerScreenBase
      title="M5Stack Devices"
      subtitle={`${devices.length} registered · ${activeCount} active`}
    >
      {loading ? (
        <View style={styles.center}>
          <ActivityIndicator color={Colors.primary} size="large" />
        </View>
      ) : (
        <FlatList
          data={devices}
          keyExtractor={d => d.id}           // device_id is unique PK — no duplicates
          contentContainerStyle={styles.list}
          refreshControl={
            <RefreshControl
              refreshing={refreshing}
              onRefresh={() => { setRefreshing(true); load(); }}
              tintColor={Colors.primary}
            />
          }
          renderItem={({ item }) => (
            <DeviceCard
              device={item}
              onChangeStatus={handleChangeStatus}
            />
          )}
          ListEmptyComponent={
            <View style={styles.empty}>
              <Ionicons name="hardware-chip-outline" size={48} color={Colors.text.muted} />
              <Text style={styles.emptyTitle}>No devices registered</Text>
              <Text style={styles.emptyText}>
                Devices are automatically registered when they send their first telemetry data.
              </Text>
            </View>
          }
        />
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