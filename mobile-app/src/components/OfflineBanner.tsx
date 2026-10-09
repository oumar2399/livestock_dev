import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { Colors, Spacing, Typography, Radius } from '../constants/config';

interface OfflineBannerProps {
  isOffline: boolean;
  lastSyncedAt?: string | null;
  resourceName?: string;
}

export function formatTimeAgo(isoString?: string | null): string {
  if (!isoString) return 'unknown';
  try {
    const diffMs = Date.now() - new Date(isoString).getTime();
    if (diffMs < 0) return 'just now';
    const mins = Math.floor(diffMs / 60000);
    if (mins < 1) return 'just now';
    if (mins < 60) return `${mins} min ago`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `${hours} h ago`;
    const days = Math.floor(hours / 24);
    return `${days} d ago`;
  } catch {
    return 'unknown';
  }
}

export default function OfflineBanner({
  isOffline,
  lastSyncedAt,
  resourceName,
}: OfflineBannerProps) {
  if (!isOffline) return null;

  const timeAgo = formatTimeAgo(lastSyncedAt);

  return (
    <View style={styles.banner}>
      <View style={styles.iconContainer}>
        <Ionicons name="cloud-offline-outline" size={20} color={Colors.severity.warning} />
      </View>
      <View style={styles.textContainer}>
        <Text style={styles.title}>
          Offline mode {resourceName ? `(${resourceName})` : ''}
        </Text>
        <Text style={styles.subText}>
          Last sync: {timeAgo} • Cached data
        </Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  banner: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(243, 156, 18, 0.15)',
    borderColor: 'rgba(243, 156, 18, 0.4)',
    borderWidth: 1,
    borderRadius: Radius.md,
    paddingHorizontal: Spacing.md,
    paddingVertical: Spacing.sm,
    marginHorizontal: Spacing.base,
    marginVertical: Spacing.xs,
    gap: Spacing.sm,
  },
  iconContainer: {
    justifyContent: 'center',
    alignItems: 'center',
  },
  textContainer: {
    flex: 1,
  },
  title: {
    fontSize: Typography.xs,
    fontWeight: '700',
    color: Colors.severity.warning,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  subText: {
    fontSize: Typography.xs,
    color: Colors.text.secondary,
    marginTop: 2,
  },
});
