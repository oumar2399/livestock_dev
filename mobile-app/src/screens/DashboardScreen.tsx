/**
 * DashboardScreen - Vue d'ensemble troupeau
 * Stats globales + alertes actives + liste rapide animaux
 * Polling : toutes les 30s
 */
import React from 'react';
import {
  View,
  Text,
  ScrollView,
  StyleSheet,
  TouchableOpacity,
  RefreshControl,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Colors, Spacing, Radius, Typography } from '../constants/config';
import { useAnimals } from '../hooks/useAnimals';
import { useActiveAlerts } from '../hooks/useAlerts';
import { useTelemetryLatest } from '../hooks/useTelemetry';
import {
  StatCard,
  SectionTitle,
  EmptyState,
  LoadingState,
  ErrorState,
} from '../components/ui';
import { AnimalStatus, Alert, AlertSeverity, Animal, TelemetryLatest } from '../types';
import {
  alertSeverityColor,
  alertTypeIcon,
  activityStateLabel,
  activityStateColor,
  timeAgo,
  formatWeight,
  animalStatusColor,
  animalStatusLabel,
} from '../utils/helpers';

// ─── Sous-composant : carte alerte récente ────────────────────────────────────

function AlertCard({ alert }: { alert: Alert }) {
  const severityColor = alertSeverityColor(alert.severity);
  return (
    <View style={[styles.alertCard, { borderLeftColor: severityColor }]}>
      <View style={[styles.alertIconBg, { backgroundColor: severityColor + '20' }]}>
        <Ionicons name={alertTypeIcon(alert.type) as any} size={18} color={severityColor} />
      </View>
      <View style={styles.alertContent}>
        <Text style={styles.alertTitle} numberOfLines={1}>{alert.title}</Text>
        <Text style={styles.alertMeta}>
          {alert.animal_name ?? 'Inconnu'} · {timeAgo(alert.triggered_at)}
        </Text>
      </View>
      <View style={[styles.severityDot, { backgroundColor: severityColor }]} />
    </View>
  );
}

// ─── Sous-composant : ligne animal dans la liste rapide ───────────────────────

function AnimalRow({ animal, telemetry }: { animal: Animal; telemetry?: TelemetryLatest }) {
  const navigation = useNavigation<any>();
  const statusColor = animalStatusColor(animal.status);
  const behaviorColor = activityStateColor(telemetry?.activity !== undefined
    ? telemetry.activity < 0.15 ? 'lying'
    : telemetry.activity < 0.5 ? 'standing'
    : telemetry.activity < 1.0 ? 'walking' : 'running'
    : null);

  return (
    <TouchableOpacity
      style={styles.animalRow}
      onPress={() => navigation.navigate('Animals', {
        screen: 'AnimalDetail',
        params: { animalId: animal.id },
      })}
      activeOpacity={0.7}
    >
      {/* Avatar initial */}
      <View style={[styles.animalAvatar, { backgroundColor: statusColor + '20' }]}>
        <Text style={[styles.animalAvatarText, { color: statusColor }]}>
          {animal.name[0].toUpperCase()}
        </Text>
      </View>

      <View style={styles.animalInfo}>
        <Text style={styles.animalName}>{animal.name}</Text>
        <Text style={styles.animalMeta}>
          {animal.official_id ?? '–'} · {animal.breed ?? animal.species}
        </Text>
      </View>

      <View style={styles.animalRight}>
        {telemetry ? (
          <View style={[styles.behaviorTag, { backgroundColor: behaviorColor + '20' }]}>
            <Text style={[styles.behaviorText, { color: behaviorColor }]}>
              {activityStateLabel(
                telemetry.activity < 0.15 ? 'lying'
                : telemetry.activity < 0.5 ? 'standing'
                : telemetry.activity < 1.0 ? 'walking' : 'running'
              )}
            </Text>
          </View>
        ) : (
          <Text style={styles.noSignal}>Hors ligne</Text>
        )}
        <Text style={[styles.statusText, { color: statusColor }]}>
          {animalStatusLabel(animal.status)}
        </Text>
      </View>

      <Ionicons name="chevron-forward" size={16} color={Colors.text.muted} />
    </TouchableOpacity>
  );
}

// ─── Screen principal ─────────────────────────────────────────────────────────

export default function DashboardScreen() {
  const insets = useSafeAreaInsets();
  const navigation = useNavigation<any>();

  const animalsQuery = useAnimals({ page_size: 10 });
  const alertsQuery = useActiveAlerts();
  const telemetryQuery = useTelemetryLatest({ limit: 50 });

  const isRefreshing =
    animalsQuery.isRefetching || alertsQuery.isRefetching || telemetryQuery.isRefetching;

  const onRefresh = () => {
    animalsQuery.refetch();
    alertsQuery.refetch();
    telemetryQuery.refetch();
  };

  const animals = animalsQuery.data?.animals ?? [];
  const alerts = alertsQuery.data?.alerts ?? [];
  const telemetryMap = new Map(
    (telemetryQuery.data ?? []).map((t) => [t.animal_id, t])
  );

  // Stats calculées
  const totalAnimals = animalsQuery.data?.total ?? 0;
  const activeAnimals = animals.filter((a) => a.status === 'active').length;
  const sickAnimals = animals.filter((a) => a.status === 'sick').length;
  const criticalAlerts = alerts.filter((a) => a.severity === 'critical').length;
  const devicesOnline = telemetryQuery.data?.length ?? 0;
  const unresolvedCount = alertsQuery.data?.unresolved_count ?? 0;

  if (animalsQuery.isLoading && !animalsQuery.data) {
    return <LoadingState message="Chargement du troupeau…" />;
  }

  if (animalsQuery.isError) {
    return <ErrorState message="Impossible de charger les données" onRetry={onRefresh} />;
  }

  return (
    <View style={[styles.screen, { backgroundColor: Colors.bg.primary }]}>
      {/* Header */}
      <View style={[styles.header, { paddingTop: insets.top + Spacing.sm }]}>
        <View>
          <Text style={styles.headerGreeting}>Bonjour 👋</Text>
          <Text style={styles.headerTitle}>Tableau de bord</Text>
        </View>
        <TouchableOpacity
          style={styles.alertsBtn}
          onPress={() => navigation.navigate('Alerts')}
        >
          <Ionicons name="notifications-outline" size={22} color={Colors.text.primary} />
          {unresolvedCount > 0 && (
            <View style={styles.notifBadge}>
              <Text style={styles.notifBadgeText}>{unresolvedCount}</Text>
            </View>
          )}
        </TouchableOpacity>
      </View>

      <ScrollView
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}
        refreshControl={
          <RefreshControl
            refreshing={isRefreshing}
            onRefresh={onRefresh}
            tintColor={Colors.primary}
          />
        }
      >
        {/* ── Stats Grid ────────────────────────────── */}
        <View style={styles.statsGrid}>
          <View style={styles.statsRow}>
            <StatCard
              label="Total animaux"
              value={totalAnimals}
              icon="paw-outline"
              color={Colors.primary}
              style={styles.statFlex}
            />
            <View style={styles.statGap} />
            <StatCard
              label="Appareils en ligne"
              value={devicesOnline}
              icon="wifi-outline"
              color={Colors.status.healthy}
              style={styles.statFlex}
            />
          </View>
          <View style={[styles.statsRow, { marginTop: Spacing.sm }]}>
            <StatCard
              label="Malades"
              value={sickAnimals}
              icon="medical-outline"
              color={sickAnimals > 0 ? Colors.severity.warning : Colors.text.muted}
              style={styles.statFlex}
            />
            <View style={styles.statGap} />
            <StatCard
              label="Alertes critiques"
              value={criticalAlerts}
              icon="warning-outline"
              color={criticalAlerts > 0 ? Colors.severity.critical : Colors.text.muted}
              style={styles.statFlex}
            />
          </View>
        </View>

        {/* ── Alertes actives ───────────────────────── */}
        <View style={styles.section}>
          <SectionTitle
            title={`Alertes actives ${unresolvedCount > 0 ? `(${unresolvedCount})` : ''}`}
            action={{ label: 'Voir tout', onPress: () => navigation.navigate('Alerts') }}
          />
          {alerts.length === 0 ? (
            <View style={styles.allGoodCard}>
              <Ionicons name="checkmark-circle" size={24} color={Colors.primary} />
              <Text style={styles.allGoodText}>Aucune alerte active — tout va bien !</Text>
            </View>
          ) : (
            alerts.slice(0, 3).map((alert) => (
              <AlertCard key={alert.id} alert={alert} />
            ))
          )}
        </View>

        {/* ── Troupeau ─────────────────────────────── */}
        <View style={styles.section}>
          <SectionTitle
            title="Troupeau récent"
            action={{ label: 'Voir tout', onPress: () => navigation.navigate('Animals') }}
          />
          {animals.length === 0 ? (
            <EmptyState
              icon="paw-outline"
              title="Aucun animal"
              message="Ajoutez vos premiers animaux"
            />
          ) : (
            <View style={styles.animalsList}>
              {animals.slice(0, 5).map((animal) => (
                <AnimalRow
                  key={animal.id}
                  animal={animal}
                  telemetry={telemetryMap.get(animal.id)}
                />
              ))}
            </View>
          )}
        </View>
      </ScrollView>
    </View>
  );
}

// ─── Styles ──────────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
  screen: { flex: 1 },

  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-end',
    paddingHorizontal: Spacing.base,
    paddingBottom: Spacing.md,
  },
  headerGreeting: { fontSize: Typography.sm, color: Colors.text.secondary },
  headerTitle: {
    fontSize: Typography['2xl'],
    fontWeight: '800',
    color: Colors.text.primary,
    letterSpacing: -0.5,
  },
  alertsBtn: {
    width: 44,
    height: 44,
    borderRadius: Radius.md,
    backgroundColor: Colors.bg.elevated,
    alignItems: 'center',
    justifyContent: 'center',
  },
  notifBadge: {
    position: 'absolute',
    top: 6,
    right: 6,
    width: 16,
    height: 16,
    borderRadius: 8,
    backgroundColor: Colors.severity.critical,
    alignItems: 'center',
    justifyContent: 'center',
  },
  notifBadgeText: { color: '#fff', fontSize: 9, fontWeight: '700' },

  scrollContent: { paddingBottom: Spacing['3xl'] },

  statsGrid: { paddingHorizontal: Spacing.base, marginBottom: Spacing.base },
  statsRow: { flexDirection: 'row' },
  statFlex: { flex: 1 },
  statGap: { width: Spacing.sm },

  section: { paddingHorizontal: Spacing.base, marginTop: Spacing.xl },

  // Alertes
  allGoodCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: Colors.primaryMuted,
    borderRadius: Radius.lg,
    padding: Spacing.base,
    gap: Spacing.sm,
    borderWidth: 1,
    borderColor: Colors.primary + '30',
  },
  allGoodText: { color: Colors.primary, fontWeight: '600', fontSize: Typography.sm },
  alertCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: Colors.bg.card,
    borderRadius: Radius.md,
    padding: Spacing.md,
    marginBottom: Spacing.sm,
    borderLeftWidth: 3,
    gap: Spacing.sm,
    borderWidth: 1,
    borderColor: Colors.border.default,
  },
  alertIconBg: {
    width: 36,
    height: 36,
    borderRadius: Radius.sm,
    alignItems: 'center',
    justifyContent: 'center',
  },
  alertContent: { flex: 1 },
  alertTitle: {
    fontSize: Typography.sm,
    fontWeight: '600',
    color: Colors.text.primary,
  },
  alertMeta: { fontSize: Typography.xs, color: Colors.text.muted, marginTop: 2 },
  severityDot: { width: 8, height: 8, borderRadius: 4 },

  // Animaux
  animalsList: {
    backgroundColor: Colors.bg.card,
    borderRadius: Radius.lg,
    borderWidth: 1,
    borderColor: Colors.border.default,
    overflow: 'hidden',
  },
  animalRow: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: Spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: Colors.border.default,
    gap: Spacing.sm,
  },
  animalAvatar: {
    width: 40,
    height: 40,
    borderRadius: Radius.full,
    alignItems: 'center',
    justifyContent: 'center',
  },
  animalAvatarText: { fontWeight: '700', fontSize: Typography.md },
  animalInfo: { flex: 1 },
  animalName: {
    fontSize: Typography.sm,
    fontWeight: '600',
    color: Colors.text.primary,
  },
  animalMeta: { fontSize: Typography.xs, color: Colors.text.muted, marginTop: 1 },
  animalRight: { alignItems: 'flex-end', gap: 2 },
  behaviorTag: {
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: Radius.sm,
  },
  behaviorText: { fontSize: Typography.xs, fontWeight: '600' },
  noSignal: { fontSize: Typography.xs, color: Colors.text.muted },
  statusText: { fontSize: Typography.xs, fontWeight: '500' },
});
