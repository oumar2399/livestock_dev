/**
 * AlertsListScreen - Gestion alerts
 * Filtres : active/résolues, sévérité (info/warning/critical)
 * Actions : Acquitter, Résoudre
 * Polling 15s - GET /alerts
 */
import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  TouchableOpacity,
  RefreshControl,
  Alert as RNAlert,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { format, parseISO } from 'date-fns';
import { fr } from 'date-fns/locale';

import { useAlerts, useAcknowledgeAlert, useResolveAlert } from '../hooks/useAlerts';
import { Colors, Radius, Spacing, Typography } from '../constants/config';
import { Alert, AlertSeverity, AlertType } from '../types';
import {
  alertSeverityColor,
  alertSeverityLabel,
  alertTypeIcon,
  alertTypeLabel,
  isAlertActive,
  isAlertAcknowledged,
  timeAgo,
  formatDateTime,
} from '../utils/helpers';
import {
  ScreenHeader,
  LoadingState,
  ErrorState,
  EmptyState,
} from '../components/ui';

// ─── Filtres ──────────────────────────────────────────────────────────────────

type StatusFilter = 'active' | 'resolved' | 'all';

const STATUS_OPTIONS: { label: string; value: StatusFilter }[] = [
  { label: 'Active', value: 'active' },
  { label: 'All', value: 'all' },
  { label: 'Resolved', value: 'resolved' },
];

const SEVERITY_OPTIONS: { label: string; value: AlertSeverity | 'all' }[] = [
  { label: 'All', value: 'all' },
  { label: 'Critical', value: 'critical' },
  { label: 'Warning', value: 'warning' },
  { label: 'Info', value: 'info' },
];

// ─── Carte alerte ─────────────────────────────────────────────────────────────

interface AlertCardProps {
  alert: Alert;
  onAcknowledge: (id: number) => void;
  onResolve: (id: number) => void;
  isProcessing: boolean;
}

function AlertCard({ alert, onAcknowledge, onResolve, isProcessing }: AlertCardProps) {
  const severityColor = alertSeverityColor(alert.severity);
  const isActive = isAlertActive(alert);
  const isAcked = isAlertAcknowledged(alert);
  const [expanded, setExpanded] = useState(false);

  return (
    <View style={[styles.alertCard, { borderLeftColor: severityColor }, !isActive && styles.alertCardResolved]}>
      {/* Header alerte */}
      <TouchableOpacity
        style={styles.alertHeader}
        onPress={() => setExpanded(!expanded)}
        activeOpacity={0.8}
      >
        {/* Icône type */}
        <View style={[styles.alertIconBg, { backgroundColor: severityColor + '20' }]}>
          <Ionicons name={alertTypeIcon(alert.type) as any} size={20} color={severityColor} />
        </View>

        <View style={styles.alertMeta}>
          <View style={styles.alertTopRow}>
            <Text style={styles.alertTitle} numberOfLines={expanded ? undefined : 1}>
              {alert.title}
            </Text>
            <View style={[styles.severityBadge, { backgroundColor: severityColor + '20', borderColor: severityColor }]}>
              <Text style={[styles.severityText, { color: severityColor }]}>
                {alertSeverityLabel(alert.severity)}
              </Text>
            </View>
          </View>

          <Text style={styles.alertAnimal}>
            {alert.animal_name ?? 'Unknown'} · {alertTypeLabel(alert.type)}
          </Text>
          <Text style={styles.alertTime}>{timeAgo(alert.triggered_at)}</Text>
        </View>

        <Ionicons
          name={expanded ? 'chevron-up' : 'chevron-down'}
          size={16}
          color={Colors.text.muted}
        />
      </TouchableOpacity>

      {/* Détails dépliables */}
      {expanded && (
        <View style={styles.alertBody}>
          {alert.message && (
            <Text style={styles.alertMessage}>{alert.message}</Text>
          )}
          <View style={styles.alertTimes}>
            <View style={styles.alertTimeRow}>
              <Ionicons name="alert-circle-outline" size={13} color={Colors.text.muted} />
              <Text style={styles.alertTimeText}>
                Triggered : {formatDateTime(alert.triggered_at)}
              </Text>
            </View>
            {alert.acknowledged_at && (
              <View style={styles.alertTimeRow}>
                <Ionicons name="eye-outline" size={13} color={Colors.primary} />
                <Text style={[styles.alertTimeText, { color: Colors.primary }]}>
                  Acknowledged : {formatDateTime(alert.acknowledged_at)}
                </Text>
              </View>
            )}
            {alert.resolved_at && (
              <View style={styles.alertTimeRow}>
                <Ionicons name="checkmark-circle-outline" size={13} color={Colors.status.healthy} />
                <Text style={[styles.alertTimeText, { color: Colors.status.healthy }]}>
                  RResolved : {formatDateTime(alert.resolved_at)}
                </Text>
              </View>
            )}
          </View>

          {/* Actions - seulement si alerte active */}
          {isActive && (
            <View style={styles.alertActions}>
              {!isAcked && (
                <TouchableOpacity
                  style={styles.actionBtn}
                  onPress={() => onAcknowledge(alert.id)}
                  disabled={isProcessing}
                >
                  <Ionicons name="eye-outline" size={15} color={Colors.text.secondary} />
                  <Text style={styles.actionBtnText}>J'ai vu</Text>
                </TouchableOpacity>
              )}
              <TouchableOpacity
                style={[styles.actionBtn, styles.actionBtnPrimary]}
                onPress={() => onResolve(alert.id)}
                disabled={isProcessing}
              >
                <Ionicons name="checkmark-outline" size={15} color={Colors.primary} />
                <Text style={[styles.actionBtnText, { color: Colors.primary }]}>Resolved</Text>
              </TouchableOpacity>
            </View>
          )}
        </View>
      )}
    </View>
  );
}

// ─── Screen ───────────────────────────────────────────────────────────────────

export default function AlertsListScreen() {
  const insets = useSafeAreaInsets();

  const [statusFilter, setStatusFilter] = useState<StatusFilter>('active');
  const [severityFilter, setSeverityFilter] = useState<AlertSeverity | 'all'>('all');

  const { mutate: acknowledge, isPending: isAcking } = useAcknowledgeAlert();
  const { mutate: resolve, isPending: isResolving } = useResolveAlert();
  const isProcessing = isAcking || isResolving;

  const queryParams = {
    resolved: statusFilter === 'all' ? undefined : statusFilter === 'resolved',
    severity: severityFilter !== 'all' ? severityFilter : undefined,
    limit: 100,
  };

  const { data, isLoading, isError, refetch, isRefetching } = useAlerts(queryParams);

  const alerts = data?.alerts ?? [];
  const unresolvedCount = data?.unresolved_count ?? 0;

  const handleAcknowledge = (id: number) => {
    acknowledge(id);
  };

  const handleResolve = (id: number) => {
    RNAlert.alert(
      'Résoudre l\'alerte',
      'Confirmer que ce problème est résolu ?',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Resolve',
          style: 'destructive',
          onPress: () => resolve(id),
        },
      ],
    );
  };

  if (isLoading && !data) return <LoadingState message="Loading alerts…" />;
  if (isError && !data) return <ErrorState message="Can't load alerts" onRetry={refetch} />;

  return (
    <View style={[styles.screen, { paddingTop: insets.top }]}>
      <ScreenHeader
        title="Alerts"
        subtitle={unresolvedCount > 0 ? `${unresolvedCount} unresolved${unresolvedCount > 1 ? 's' : ''}` : 'All clear'}
      />

      {/* Filtres statut */}
      <View style={styles.statusTabs}>
        {STATUS_OPTIONS.map((opt) => (
          <TouchableOpacity
            key={opt.value}
            style={[styles.statusTab, statusFilter === opt.value && styles.statusTabActive]}
            onPress={() => setStatusFilter(opt.value)}
          >
            <Text style={[styles.statusTabText, statusFilter === opt.value && styles.statusTabTextActive]}>
              {opt.label}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* Filtres sévérité */}
      <View style={styles.severityRow}>
        {SEVERITY_OPTIONS.map((opt) => {
          const color = opt.value !== 'all' ? alertSeverityColor(opt.value) : Colors.text.secondary;
          const active = severityFilter === opt.value;
          return (
            <TouchableOpacity
              key={opt.value}
              style={[
                styles.severityChip,
                active && { backgroundColor: color + '20', borderColor: color },
              ]}
              onPress={() => setSeverityFilter(opt.value)}
            >
              {opt.value !== 'all' && (
                <View style={[styles.severityDot, { backgroundColor: color }]} />
              )}
              <Text style={[styles.severityChipText, active && { color }]}>
                {opt.label}
              </Text>
            </TouchableOpacity>
          );
        })}
      </View>

      {/* Liste alerts */}
      <FlatList
        data={alerts}
        keyExtractor={(item) => String(item.id)}
        contentContainerStyle={[
          styles.list,
          alerts.length === 0 && styles.listEmpty,
        ]}
        showsVerticalScrollIndicator={false}
        refreshControl={
          <RefreshControl
            refreshing={isRefetching}
            onRefresh={refetch}
            tintColor={Colors.primary}
          />
        }
        renderItem={({ item }) => (
          <AlertCard
            alert={item}
            onAcknowledge={handleAcknowledge}
            onResolve={handleResolve}
            isProcessing={isProcessing}
          />
        )}
        ItemSeparatorComponent={() => <View style={{ height: Spacing.sm }} />}
        ListEmptyComponent={
          <EmptyState
            icon="notifications-outline"
            title="No alerts"
            message={
              statusFilter === 'active'
                ? 'All good, no active alerts!'
                : 'No alerts in this category'
            }
          />
        }
      />
    </View>
  );
}

// ─── Styles ──────────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: Colors.bg.primary },

  statusTabs: {
    flexDirection: 'row',
    marginHorizontal: Spacing.base,
    backgroundColor: Colors.bg.elevated,
    borderRadius: Radius.lg,
    padding: 3,
    marginBottom: Spacing.md,
  },
  statusTab: { flex: 1, paddingVertical: 7, alignItems: 'center', borderRadius: Radius.md },
  statusTabActive: { backgroundColor: Colors.bg.card },
  statusTabText: { fontSize: Typography.sm, color: Colors.text.muted, fontWeight: '600' },
  statusTabTextActive: { color: Colors.text.primary },

  severityRow: {
    flexDirection: 'row',
    paddingHorizontal: Spacing.base,
    gap: Spacing.sm,
    marginBottom: Spacing.md,
  },
  severityChip: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: Spacing.md,
    paddingVertical: 5,
    borderRadius: Radius.full,
    borderWidth: 1,
    borderColor: Colors.border.default,
    gap: 5,
  },
  severityDot: { width: 6, height: 6, borderRadius: 3 },
  severityChipText: { fontSize: Typography.sm, color: Colors.text.secondary, fontWeight: '500' },

  list: { paddingHorizontal: Spacing.base, paddingBottom: Spacing['2xl'] },
  listEmpty: { flex: 1 },

  // Alert card
  alertCard: {
    backgroundColor: Colors.bg.card,
    borderRadius: Radius.lg,
    borderLeftWidth: 3,
    borderWidth: 1,
    borderColor: Colors.border.default,
    overflow: 'hidden',
  },
  alertCardResolved: { opacity: 0.65 },
  alertHeader: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    padding: Spacing.md,
    gap: Spacing.sm,
  },
  alertIconBg: {
    width: 40,
    height: 40,
    borderRadius: Radius.md,
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
  alertMeta: { flex: 1 },
  alertTopRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: Spacing.sm,
    marginBottom: 3,
  },
  alertTitle: {
    flex: 1,
    fontSize: Typography.sm,
    fontWeight: '700',
    color: Colors.text.primary,
    lineHeight: 18,
  },
  severityBadge: {
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: Radius.sm,
    borderWidth: 1,
    flexShrink: 0,
  },
  severityText: { fontSize: 10, fontWeight: '700' },
  alertAnimal: { fontSize: Typography.xs, color: Colors.text.secondary, marginBottom: 2 },
  alertTime: { fontSize: Typography.xs, color: Colors.text.muted },

  alertBody: {
    paddingHorizontal: Spacing.md,
    paddingBottom: Spacing.md,
    borderTopWidth: 1,
    borderTopColor: Colors.border.default,
    paddingTop: Spacing.sm,
  },
  alertMessage: {
    fontSize: Typography.sm,
    color: Colors.text.secondary,
    lineHeight: 20,
    marginBottom: Spacing.sm,
  },
  alertTimes: { gap: 4, marginBottom: Spacing.sm },
  alertTimeRow: { flexDirection: 'row', alignItems: 'center', gap: 5 },
  alertTimeText: { fontSize: Typography.xs, color: Colors.text.muted },

  alertActions: {
    flexDirection: 'row',
    gap: Spacing.sm,
    marginTop: Spacing.sm,
  },
  actionBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    paddingHorizontal: Spacing.md,
    paddingVertical: 7,
    borderRadius: Radius.md,
    backgroundColor: Colors.bg.elevated,
    borderWidth: 1,
    borderColor: Colors.border.default,
  },
  actionBtnPrimary: {
    backgroundColor: Colors.primaryMuted,
    borderColor: Colors.primary + '40',
  },
  actionBtnText: { fontSize: Typography.sm, color: Colors.text.secondary, fontWeight: '600' },
});
