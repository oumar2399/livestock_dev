/**
 * DashboardScreen - Vue d'ensemble troupeau & Centre d'attention opérationnel (Needs Attention)
 * Intègre les règles de rigueur scientifique et de transparence terrain :
 * - Section "Needs Attention" groupant franchissements geofence, anomalies, colliers silencieux (>30m) et batteries critiques (<15%)
 * - Boutons d'action directs : Locate (centrage carte), Acknowledge (acquittement), View Animal
 * - Bannissement du "All Good" aveugle : affiche le ratio de fraîcheur honnête "X/Y reporting recently"
 * - Séparation stricte de la fraîcheur des données
 */
import React, { useMemo, useEffect, useState } from 'react';
import {
  View,
  Text,
  ScrollView,
  StyleSheet,
  TouchableOpacity,
  RefreshControl,
  ActivityIndicator,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Colors, Spacing, Radius, Typography } from '../constants/config';
import { useAnimals } from '../hooks/useAnimals';
import { useActiveAlerts, useAcknowledgeAlert } from '../hooks/useAlerts';
import { useTelemetryLatest } from '../hooks/useTelemetry';
import {
  StatCard,
  SectionTitle,
  EmptyState,
  LoadingState,
  ErrorState,
} from '../components/ui';
import { Alert, Animal, TelemetryLatest } from '../types';
import {
  alertSeverityColor,
  activityStateLabel,
  activityStateColor,
  timeAgo,
  animalStatusColor,
  evaluateFreshness,
  isRecentUpdate,
  formatBattery,
} from '../utils/helpers';

// ─── Modèle unifié pour les éléments "Needs Attention" ────────────────────────

interface AttentionItem {
  id: string;
  category: 'geofence' | 'health' | 'silent' | 'battery';
  severity: 'critical' | 'warning' | 'info';
  title: string;
  description: string;
  animalId?: number;
  animalName: string;
  deviceId?: string;
  alertId?: number;
  hasGpsLocation: boolean;
  timeLabel?: string;
}

// ─── Sous-composant : Carte "Needs Attention" ─────────────────────────────────

function AttentionCard({
  item,
  onLocate,
  onAcknowledge,
  onViewAnimal,
  isAcknowledging,
}: {
  item: AttentionItem;
  onLocate: () => void;
  onAcknowledge?: () => void;
  onViewAnimal: () => void;
  isAcknowledging?: boolean;
}) {
  const sevColor = item.severity === 'critical'
    ? Colors.severity.critical
    : item.severity === 'warning'
      ? Colors.severity.warning
      : Colors.severity.info;

  const iconName = item.category === 'geofence'
    ? 'navigate-circle-outline'
    : item.category === 'silent'
      ? 'cloud-offline-outline'
      : item.category === 'battery'
        ? 'battery-dead-outline'
        : 'fitness-outline';

  return (
    <View style={[styles.attentionCard, { borderLeftColor: sevColor }]}>
      <View style={styles.attentionHeader}>
        <View style={[styles.attentionIconWrap, { backgroundColor: sevColor + '18' }]}>
          <Ionicons name={iconName as any} size={20} color={sevColor} />
        </View>

        <View style={styles.attentionTitleBox}>
          <View style={styles.attentionBadgeRow}>
            <View style={[styles.categoryBadge, { backgroundColor: sevColor + '20' }]}>
              <Text style={[styles.categoryBadgeText, { color: sevColor }]}>
                {item.category.toUpperCase()}
              </Text>
            </View>
            {item.timeLabel ? (
              <Text style={styles.attentionTime}>{item.timeLabel}</Text>
            ) : null}
          </View>
          <Text style={styles.attentionTitle} numberOfLines={1}>{item.title}</Text>
        </View>
      </View>

      <Text style={styles.attentionDesc}>{item.description}</Text>

      {/* Barre d'actions rapides directes */}
      <View style={styles.actionRow}>
        {item.hasGpsLocation && (
          <TouchableOpacity
            style={[styles.actionBtn, styles.locateBtn]}
            onPress={onLocate}
            activeOpacity={0.7}
          >
            <Ionicons name="map-outline" size={14} color="#fff" />
            <Text style={styles.locateBtnText}>Locate</Text>
          </TouchableOpacity>
        )}

        <TouchableOpacity
          style={styles.actionBtnSecondary}
          onPress={onViewAnimal}
          activeOpacity={0.7}
        >
          <Ionicons name="paw-outline" size={14} color={Colors.text.primary} />
          <Text style={styles.actionBtnSecondaryText}>View Animal</Text>
        </TouchableOpacity>

        {item.alertId && onAcknowledge && (
          <TouchableOpacity
            style={styles.actionBtnOutline}
            onPress={onAcknowledge}
            disabled={isAcknowledging}
            activeOpacity={0.7}
          >
            {isAcknowledging ? (
              <ActivityIndicator size="small" color={Colors.primary} />
            ) : (
              <>
                <Ionicons name="checkmark-done-outline" size={14} color={Colors.primary} />
                <Text style={styles.actionBtnOutlineText}>Acknowledge</Text>
              </>
            )}
          </TouchableOpacity>
        )}
      </View>
    </View>
  );
}

// ─── Sous-composant : Ligne animal dans la liste rapide ───────────────────────

function AnimalRow({ animal, telemetry }: { animal: Animal; telemetry?: TelemetryLatest }) {
  const navigation = useNavigation<any>();
  const statusColor = animalStatusColor(animal.status);

  const freshness = evaluateFreshness({
    telemetryTime: telemetry?.last_update,
    positionTime: telemetry?.position_time,
    latitude: telemetry?.latitude,
    longitude: telemetry?.longitude,
    deviceStatus: telemetry?.device_status,
    battery: telemetry?.battery,
  });

  const activityState = telemetry && telemetry.behavior_eligible !== false
    ? (telemetry.activity_state ?? (telemetry.activity < 0.5 ? 'Resting' : 'Active'))
    : null;
  const behaviorColor = activityStateColor(activityState as any);

  return (
    <TouchableOpacity
      style={styles.animalRow}
      onPress={() => navigation.navigate('Animals', {
        screen: 'AnimalDetail',
        params: { animalId: animal.id },
      })}
      activeOpacity={0.7}
    >
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
        <View style={[styles.freshnessTag, { backgroundColor: freshness.telemetryFreshness === 'recent' ? '#27AE6018' : '#7F8C8D18' }]}>
          <Text style={[styles.freshnessText, { color: freshness.telemetryFreshness === 'recent' ? '#27AE60' : Colors.text.muted }]}>
            {freshness.telemetryLabel}
          </Text>
        </View>

        {activityState && (
          <Text style={[styles.behaviorMini, { color: behaviorColor }]}>
            {activityStateLabel(activityState as any)}
          </Text>
        )}
      </View>

      <Ionicons name="chevron-forward" size={16} color={Colors.text.muted} />
    </TouchableOpacity>
  );
}

// ─── Screen principal ─────────────────────────────────────────────────────────

export default function DashboardScreen() {
  const insets = useSafeAreaInsets();
  const navigation = useNavigation<any>();
  const [clockTick, setClockTick] = useState(0);
  useEffect(() => {
    const timer = setInterval(() => setClockTick((value) => value + 1), 30_000);
    return () => clearInterval(timer);
  }, []);

  const animalsQuery = useAnimals({ page_size: 100 }, undefined, true);
  const alertsQuery = useActiveAlerts();
  const telemetryQuery = useTelemetryLatest({ limit: 100 }, undefined, true);
  const acknowledgeMutation = useAcknowledgeAlert();

  const isRefreshing =
    animalsQuery.isRefetching || alertsQuery.isRefetching || telemetryQuery.isRefetching;

  const onRefresh = () => {
    animalsQuery.refetch();
    alertsQuery.refetch();
    telemetryQuery.refetch();
  };

  const animals = animalsQuery.data?.animals ?? [];
  const alerts = alertsQuery.data?.alerts ?? [];
  const telemetryList = telemetryQuery.data ?? [];
  const telemetryMap = useMemo(
    () => new Map(telemetryList.map((t) => [t.animal_id, t])),
    [telemetryList],
  );

  // ── Fraîcheur globale du troupeau ──────────────────────────────────────────
  const totalAnimals = animalsQuery.data?.total ?? animals.length;
  const reportingRecentlyCount = useMemo(() => {
    let count = 0;
    for (const t of telemetryList) {
      if (isRecentUpdate(t.last_update, 5)) {
        count++;
      }
    }
    return count;
  }, [telemetryList, clockTick]);

  // ── Construction du Centre d'Attention ("Needs Attention") ─────────────────
  const attentionItems = useMemo(() => {
    const items: AttentionItem[] = [];

    // 1. Alertes actives serveur (Geofence, Santé, Batterie)
    for (const alert of alerts) {
      const animalTelem = telemetryMap.get(alert.animal_id);
      const hasGps = animalTelem?.latitude != null && animalTelem?.longitude != null;

      let cat: AttentionItem['category'] = 'health';
      if (alert.type === 'geofence') cat = 'geofence';
      else if (alert.type === 'battery') cat = 'battery';

      items.push({
        id: `alert-${alert.id}`,
        category: cat,
        severity: alert.severity,
        title: alert.title ?? 'Alert',
        description: alert.message ?? `${alert.animal_name ?? 'Animal'} requires attention.`,
        animalId: alert.animal_id,
        animalName: alert.animal_name ?? 'Animal',
        alertId: alert.id,
        hasGpsLocation: hasGps,
        timeLabel: timeAgo(alert.triggered_at),
      });
    }

    // 2. Colliers silencieux (> 30 min) pour animaux actifs avec collier assigné
    for (const animal of animals) {
      if (animal.status === 'active' && animal.assigned_device) {
        const telem = telemetryMap.get(animal.id);
        const freshness = evaluateFreshness({
          telemetryTime: telem?.last_update,
          positionTime: telem?.position_time,
          latitude: telem?.latitude,
          longitude: telem?.longitude,
          deviceStatus: telem?.device_status,
          battery: telem?.battery,
        });

        if (freshness.telemetryFreshness === 'silent') {
          const hasExistingSilentAlert = items.some(
            (it) => it.animalId === animal.id && it.category === 'silent'
          );
          if (!hasExistingSilentAlert) {
            const hasGps = telem?.latitude != null && telem?.longitude != null;
            items.push({
              id: `silent-${animal.id}`,
              category: 'silent',
              severity: 'warning',
              title: `Silent Collar (${animal.assigned_device})`,
              description: telem?.last_update
                ? `No telemetry received for ${timeAgo(telem.last_update)}.`
                : 'Collar has not transmitted any telemetry yet.',
              animalId: animal.id,
              animalName: animal.name,
              deviceId: animal.assigned_device,
              hasGpsLocation: hasGps,
              timeLabel: telem?.last_update ? timeAgo(telem.last_update) : 'No signal',
            });
          }
        }
      }
    }

    // 3. Batteries critiques (< 15%) non encore alertées
    for (const animal of animals) {
      const telem = telemetryMap.get(animal.id);
      if (telem && typeof telem.battery === 'number' && telem.battery >= 0 && telem.battery < 15) {
        const alreadyCovered = items.some(
          (it) => it.animalId === animal.id && it.category === 'battery'
        );
        if (!alreadyCovered) {
          const hasGps = telem?.latitude != null && telem?.longitude != null;
          items.push({
            id: `bat-${animal.id}`,
            category: 'battery',
            severity: 'warning',
            title: `Critical Battery (${formatBattery(telem.battery)})`,
            description: `${animal.name}'s collar (${animal.assigned_device ?? 'unknown'}) needs recharging.`,
            animalId: animal.id,
            animalName: animal.name,
            deviceId: animal.assigned_device ?? undefined,
            hasGpsLocation: hasGps,
            timeLabel: formatBattery(telem.battery),
          });
        }
      }
    }

    // Trier : critical en premier, puis warning
    return items.sort((a, b) => {
      const order = { critical: 0, warning: 1, info: 2 };
      return order[a.severity] - order[b.severity];
    });
  }, [alerts, animals, telemetryMap, clockTick]);

  const activeBreachesCount = useMemo(
    () => alerts.filter((a) => a.type === 'geofence').length,
    [alerts],
  );

  const unresolvedCount = alertsQuery.data?.unresolved_count ?? alerts.length;

  if ((animalsQuery.isLoading && !animalsQuery.data) || (telemetryQuery.isLoading && !telemetryQuery.data)) {
    return <LoadingState message="Loading operational dashboard..." />;
  }

  if (animalsQuery.isError || telemetryQuery.isError || alertsQuery.isError) {
    return <ErrorState message="Failed to load dashboard data" onRetry={onRefresh} />;
  }

  return (
    <View style={[styles.screen, { backgroundColor: Colors.bg.primary }]}>
      {/* Header */}
      <View style={[styles.header, { paddingTop: insets.top + Spacing.sm }]}>
        <View>
          <Text style={styles.headerGreeting}>Pastoral Overview 👋</Text>
          <Text style={styles.headerTitle}>Dashboard</Text>
        </View>
        <TouchableOpacity
          style={styles.alertsBtn}
          onPress={() => navigation.navigate('Alerts')}
          activeOpacity={0.7}
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
        {/* ── Bannière de configuration initiale si cheptel vide ───────── */}
        {totalAnimals === 0 && (
          <TouchableOpacity
            style={styles.onboardingCtaCard}
            onPress={() => navigation.navigate('FarmOnboarding')}
            activeOpacity={0.85}
          >
            <View style={styles.onboardingCtaIcon}>
              <Ionicons name="sparkles" size={24} color={Colors.primary} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={styles.onboardingCtaTitle}>Guide de mise en route</Text>
              <Text style={styles.onboardingCtaSub}>
                Configurez votre exploitation : enregistrez vos premiers animaux, associez vos colliers et délimitez vos zones.
              </Text>
            </View>
            <Ionicons name="arrow-forward-circle" size={26} color={Colors.primary} />
          </TouchableOpacity>
        )}

        {/* ── Stats Grid Honnête ────────────────────── */}
        <View style={styles.statsGrid}>
          <View style={styles.statsRow}>
            <StatCard
              label="Total Herd"
              value={totalAnimals}
              icon="paw-outline"
              color={Colors.primary}
              style={styles.statFlex}
            />
            <View style={styles.statGap} />
            <StatCard
              label="Reporting Recently"
              value={`${reportingRecentlyCount}/${totalAnimals}`}
              icon="radio-outline"
              color={reportingRecentlyCount === totalAnimals && totalAnimals > 0 ? '#27AE60' : '#F39C12'}
              style={styles.statFlex}
            />
          </View>
          <View style={[styles.statsRow, { marginTop: Spacing.sm }]}>
            <StatCard
              label="Needs Attention"
              value={attentionItems.length}
              icon="alert-circle-outline"
              color={attentionItems.length > 0 ? Colors.severity.critical : Colors.text.muted}
              style={styles.statFlex}
            />
            <View style={styles.statGap} />
            <StatCard
              label="Geofence Breaches"
              value={activeBreachesCount}
              icon="navigate-outline"
              color={activeBreachesCount > 0 ? Colors.severity.critical : Colors.text.muted}
              style={styles.statFlex}
            />
          </View>
        </View>

        {/* ── Centre d'Attention ("Needs Attention") ───────── */}
        <View style={styles.section}>
          <SectionTitle
            title={`Needs Attention ${attentionItems.length > 0 ? `(${attentionItems.length})` : ''}`}
            action={attentionItems.length > 0 ? { label: 'View Alerts', onPress: () => navigation.navigate('Alerts') } : undefined}
          />

          {attentionItems.length === 0 ? (
            /* État transparent et vérifiable "All Clear" */
            <View style={styles.allClearCard}>
              <View style={styles.allClearIconCircle}>
                <Ionicons name="checkmark-sharp" size={24} color="#27AE60" />
              </View>
              <View style={styles.allClearContent}>
                <Text style={styles.allClearTitle}>No active issues detected</Text>
                <Text style={styles.allClearSubtitle}>
                  {reportingRecentlyCount} of {totalAnimals} animals reporting recently (under 5 min)
                </Text>
                {totalAnimals > reportingRecentlyCount && (
                  <Text style={styles.allClearNotice}>
                    {totalAnimals - reportingRecentlyCount} collar(s) currently silent or unassigned
                  </Text>
                )}
              </View>
            </View>
          ) : (
            attentionItems.map((item) => (
              <AttentionCard
                key={item.id}
                item={item}
                onLocate={() => {
                  if (item.animalId) {
                    navigation.navigate('Map', { focusAnimalId: item.animalId, showTrack: true });
                  }
                }}
                onViewAnimal={() => {
                  if (item.animalId) {
                    navigation.navigate('Animals', {
                      screen: 'AnimalDetail',
                      params: { animalId: item.animalId },
                    });
                  }
                }}
                onAcknowledge={item.alertId ? () => acknowledgeMutation.mutate(item.alertId!) : undefined}
                isAcknowledging={acknowledgeMutation.isPending && acknowledgeMutation.variables === item.alertId}
              />
            ))
          )}
        </View>

        {/* ── Troupeau Récent ──────────────────────── */}
        <View style={styles.section}>
          <SectionTitle
            title="Recent Herd Activity"
            action={{ label: 'View All', onPress: () => navigation.navigate('Animals') }}
          />
          {animals.length === 0 ? (
            <EmptyState
              icon="paw-outline"
              title="No Animals"
              message="Add your first animals to monitor the herd."
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
    height: 90,
  },
  headerGreeting: { fontSize: Typography.sm, color: Colors.text.secondary, fontWeight: '500' },
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
    borderWidth: 1,
    borderColor: Colors.border.default,
  },
  notifBadge: {
    position: 'absolute',
    top: 6,
    right: 6,
    minWidth: 18,
    height: 18,
    borderRadius: 9,
    backgroundColor: Colors.severity.critical,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 4,
  },
  notifBadgeText: { color: '#fff', fontSize: 10, fontWeight: '700' },

  scrollContent: { paddingBottom: Spacing['3xl'] },

  statsGrid: { paddingHorizontal: Spacing.base, marginBottom: Spacing.xs },
  statsRow: { flexDirection: 'row' },
  statFlex: { flex: 1 },
  statGap: { width: Spacing.sm },

  section: { paddingHorizontal: Spacing.base, marginTop: Spacing.lg },

  // ── "All Clear" transparent card ──
  allClearCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: Colors.bg.card,
    borderRadius: Radius.lg,
    padding: Spacing.base,
    gap: Spacing.md,
    borderWidth: 1,
    borderColor: '#27AE6030',
  },
  allClearIconCircle: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: '#27AE6018',
    alignItems: 'center',
    justifyContent: 'center',
  },
  allClearContent: { flex: 1 },
  allClearTitle: {
    color: '#27AE60',
    fontWeight: '700',
    fontSize: Typography.base,
  },
  allClearSubtitle: {
    color: Colors.text.primary,
    fontWeight: '500',
    fontSize: Typography.xs,
    marginTop: 2,
  },
  allClearNotice: {
    color: Colors.text.muted,
    fontSize: Typography.xs,
    marginTop: 2,
  },

  // ── "Needs Attention" card ──
  attentionCard: {
    backgroundColor: Colors.bg.card,
    borderRadius: Radius.lg,
    padding: Spacing.base,
    marginBottom: Spacing.sm,
    borderLeftWidth: 4,
    borderWidth: 1,
    borderColor: Colors.border.default,
  },
  attentionHeader: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: Spacing.sm,
  },
  attentionIconWrap: {
    width: 36,
    height: 36,
    borderRadius: Radius.md,
    alignItems: 'center',
    justifyContent: 'center',
  },
  attentionTitleBox: { flex: 1 },
  attentionBadgeRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 4,
  },
  categoryBadge: {
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: Radius.sm,
  },
  categoryBadgeText: {
    fontSize: 10,
    fontWeight: '800',
    letterSpacing: 0.5,
  },
  attentionTime: {
    fontSize: Typography.xs,
    color: Colors.text.muted,
  },
  attentionTitle: {
    fontSize: Typography.sm,
    fontWeight: '700',
    color: Colors.text.primary,
  },
  attentionDesc: {
    fontSize: Typography.xs,
    color: Colors.text.secondary,
    marginTop: Spacing.xs,
    marginBottom: Spacing.sm,
    lineHeight: 18,
  },

  // Actions
  actionRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.xs,
    flexWrap: 'wrap',
    marginTop: 2,
  },
  actionBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: Spacing.sm,
    paddingVertical: 6,
    borderRadius: Radius.sm,
    gap: 4,
  },
  locateBtn: {
    backgroundColor: Colors.primary,
  },
  locateBtnText: {
    color: '#fff',
    fontSize: Typography.xs,
    fontWeight: '700',
  },
  actionBtnSecondary: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: Spacing.sm,
    paddingVertical: 6,
    borderRadius: Radius.sm,
    backgroundColor: Colors.bg.elevated,
    gap: 4,
    borderWidth: 1,
    borderColor: Colors.border.default,
  },
  actionBtnSecondaryText: {
    color: Colors.text.primary,
    fontSize: Typography.xs,
    fontWeight: '600',
  },
  actionBtnOutline: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: Spacing.sm,
    paddingVertical: 6,
    borderRadius: Radius.sm,
    backgroundColor: Colors.primary + '10',
    gap: 4,
    borderWidth: 1,
    borderColor: Colors.primary + '40',
  },
  actionBtnOutlineText: {
    color: Colors.primary,
    fontSize: Typography.xs,
    fontWeight: '600',
  },

  // Troupeau
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
  freshnessTag: {
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: Radius.sm,
  },
  freshnessText: { fontSize: 10, fontWeight: '600' },
  behaviorMini: { fontSize: 10, fontWeight: '600' },

  onboardingCtaCard: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.md,
    backgroundColor: Colors.primary + '12',
    borderColor: Colors.primary + '40',
    borderWidth: 1.5,
    borderRadius: Radius.lg,
    padding: Spacing.base,
    marginBottom: Spacing.base,
  },
  onboardingCtaIcon: {
    width: 46,
    height: 46,
    borderRadius: 23,
    backgroundColor: Colors.primary + '22',
    alignItems: 'center',
    justifyContent: 'center',
  },
  onboardingCtaTitle: {
    fontSize: Typography.base,
    fontWeight: '700',
    color: Colors.text.primary,
    marginBottom: 3,
  },
  onboardingCtaSub: {
    fontSize: Typography.xs,
    color: Colors.text.secondary,
    lineHeight: 16,
  },
});
