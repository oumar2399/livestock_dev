/**
 * AnimalDetailScreen - Fiche complète d'un animal
 * Infos générales + position actuelle + graphique activité 24h
 * GET /animals/{id} + GET /telemetry/history/{id}
 */
import React, { useState } from 'react';
import {
  View,
  Text,
  ScrollView,
  StyleSheet,
  TouchableOpacity,
  RefreshControl,
} from 'react-native';
import { useRoute, useNavigation, RouteProp } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { VictoryChart, VictoryArea, VictoryAxis, VictoryTheme, VictoryBar } from 'victory-native';
import { format, parseISO } from 'date-fns';
import { fr } from 'date-fns/locale';

import { AnimalsStackParamList, ActivityState, TelemetryRecord } from '../types';
import { useAnimal } from '../hooks/useAnimals';
import { useTelemetryHistory } from '../hooks/useTelemetry';
import { Colors, Radius, Spacing, Typography } from '../constants/config';
import {
  animalStatusColor,
  animalStatusLabel,
  animalAge,
  animalSexLabel,
  formatWeight,
  formatDate,
  formatTemperature,
  activityStateColor,
  activityStateLabel,
  batteryColor,
  batteryIcon,
  timeAgo,
  formatCoords,
  isRecentUpdate,
} from '../utils/helpers';
import {
  ScreenHeader,
  LoadingState,
  ErrorState,
  InfoRow,
  StatusBadge,
} from '../components/ui';

// ─── Sélecteur période ────────────────────────────────────────────────────────

const PERIOD_OPTIONS = [
  { label: '6h', hours: 6 },
  { label: '24h', hours: 24 },
  { label: '7j', hours: 168 },
];

// ─── Graphique activité ────────────────────────────────────────────────────────

function ActivityChart({ records }: { records: TelemetryRecord[] }) {
  if (!records.length) {
    return (
      <View style={styles.noDataChart}>
        <Ionicons name="bar-chart-outline" size={32} color={Colors.text.muted} />
        <Text style={styles.noDataText}>Pas de données disponibles</Text>
      </View>
    );
  }

  const chartData = records.map((r) => ({
    x: new Date(r.time),
    y: r.activity,
  }));

  return (
    <VictoryChart
      theme={VictoryTheme.material}
      height={160}
      padding={{ top: 10, bottom: 30, left: 40, right: 20 }}
      style={{ parent: { backgroundColor: 'transparent' } }}
    >
      <VictoryAxis
        tickFormat={(t: Date) => format(t, 'HH:mm')}
        tickCount={5}
        style={{
          axis: { stroke: Colors.border.default },
          tickLabels: { fill: Colors.text.muted, fontSize: 9 },
          grid: { stroke: 'transparent' },
        }}
      />
      <VictoryAxis
        dependentAxis
        tickFormat={(t: number) => `${t.toFixed(1)}g`}
        style={{
          axis: { stroke: Colors.border.default },
          tickLabels: { fill: Colors.text.muted, fontSize: 9 },
          grid: { stroke: Colors.border.default, strokeDasharray: '4,4' },
        }}
      />
      <VictoryArea
        data={chartData}
        interpolation="monotoneX"
        style={{
          data: {
            fill: Colors.primary + '30',
            stroke: Colors.primary,
            strokeWidth: 2,
          },
        }}
        animate={{ duration: 500 }}
      />
    </VictoryChart>
  );
}

// ─── Distribution comportements ────────────────────────────────────────────────

function BehaviorDistribution({ records }: { records: TelemetryRecord[] }) {
  if (!records.length) return null;

  const counts: Record<ActivityState, number> = {
    lying: 0, standing: 0, walking: 0, running: 0,
  };
  records.forEach((r) => {
    if (r.activity_state) counts[r.activity_state as ActivityState]++;
  });
  const total = records.length;

  return (
    <View style={styles.behaviorDist}>
      {(Object.entries(counts) as [ActivityState, number][]).map(([state, count]) => {
        const pct = total > 0 ? (count / total) * 100 : 0;
        const color = activityStateColor(state);
        return (
          <View key={state} style={styles.behaviorRow}>
            <View style={styles.behaviorRowLeft}>
              <View style={[styles.behaviorDot, { backgroundColor: color }]} />
              <Text style={styles.behaviorLabel}>{activityStateLabel(state)}</Text>
            </View>
            <View style={styles.behaviorBarBg}>
              <View style={[styles.behaviorBarFill, { width: `${pct}%` as any, backgroundColor: color }]} />
            </View>
            <Text style={[styles.behaviorPct, { color }]}>{pct.toFixed(0)}%</Text>
          </View>
        );
      })}
    </View>
  );
}

// ─── Screen ───────────────────────────────────────────────────────────────────

type RouteProps = RouteProp<AnimalsStackParamList, 'AnimalDetail'>;

export default function AnimalDetailScreen() {
  const route = useRoute<RouteProps>();
  const navigation = useNavigation();
  const insets = useSafeAreaInsets();
  const { animalId } = route.params;

  const [historyHours, setHistoryHours] = useState(24);

  const animalQuery = useAnimal(animalId);
  const historyQuery = useTelemetryHistory(animalId, historyHours);

  const animal = animalQuery.data;
  const records = historyQuery.data ?? [];
  const latestRecord = records[records.length - 1];

  const onRefresh = () => {
    animalQuery.refetch();
    historyQuery.refetch();
  };

  if (animalQuery.isLoading) return <LoadingState message="Chargement de la fiche…" />;
  if (animalQuery.isError || !animal) {
    return <ErrorState message="Animal introuvable" onRetry={() => animalQuery.refetch()} />;
  }

  const statusColor = animalStatusColor(animal.status);
  const isLive = isRecentUpdate(animal.last_update);
  const currentState = latestRecord?.activity_state as ActivityState | null;

  return (
    <View style={[styles.screen, { paddingTop: insets.top }]}>
      <ScreenHeader
        title={animal.name}
        subtitle={`${animal.official_id ? `#${animal.official_id} · ` : ''}${animal.breed ?? animal.species}`}
        onBack={() => navigation.goBack()}
      />

      <ScrollView
        contentContainerStyle={styles.content}
        showsVerticalScrollIndicator={false}
        refreshControl={
          <RefreshControl refreshing={animalQuery.isRefetching} onRefresh={onRefresh} tintColor={Colors.primary} />
        }
      >
        {/* ── Hero card ──────────────────────────── */}
        <View style={styles.heroCard}>
          {/* Grand avatar */}
          <View style={[styles.heroAvatar, { backgroundColor: statusColor + '20' }]}>
            <Text style={[styles.heroAvatarText, { color: statusColor }]}>
              {animal.name[0].toUpperCase()}
            </Text>
          </View>

          <View style={styles.heroInfo}>
            <Text style={styles.heroName}>{animal.name}</Text>
            <View style={styles.heroBadges}>
              <StatusBadge label={animalStatusLabel(animal.status)} color={statusColor} />
              {isLive && currentState && (
                <StatusBadge
                  label={activityStateLabel(currentState)}
                  color={activityStateColor(currentState)}
                />
              )}
            </View>
          </View>

          {/* Batterie live */}
          {latestRecord && (
            <View style={styles.heroBattery}>
              <Ionicons
                name={batteryIcon(latestRecord.battery) as any}
                size={20}
                color={batteryColor(latestRecord.battery)}
              />
              <Text style={[styles.heroBatteryText, { color: batteryColor(latestRecord.battery) }]}>
                {latestRecord.battery}%
              </Text>
            </View>
          )}
        </View>

        {/* ── Position GPS ───────────────────────── */}
        <View style={styles.card}>
          <View style={styles.cardHeader}>
            <Ionicons name="location-outline" size={18} color={Colors.primary} />
            <Text style={styles.cardTitle}>Position GPS</Text>
            {isLive && <View style={styles.liveDot} />}
          </View>
          <Text style={styles.coordText}>
            {formatCoords(animal.last_latitude, animal.last_longitude)}
          </Text>
          <Text style={styles.coordMeta}>
            {animal.last_update
              ? `Dernière mise à jour : ${timeAgo(animal.last_update)}`
              : 'Aucune position enregistrée'}
          </Text>
        </View>

        {/* ── Informations ───────────────────────── */}
        <View style={styles.card}>
          <View style={styles.cardHeader}>
            <Ionicons name="information-circle-outline" size={18} color={Colors.primary} />
            <Text style={styles.cardTitle}>Informations</Text>
          </View>
          <InfoRow label="Identifiant" value={animal.official_id ?? '–'} icon="barcode-outline" />
          <InfoRow label="Espèce" value={animal.species} icon="paw-outline" />
          <InfoRow label="Race" value={animal.breed ?? '–'} icon="leaf-outline" />
          <InfoRow label="Sexe" value={animalSexLabel(animal.sex)} icon="male-female-outline" />
          <InfoRow label="Âge" value={animalAge(animal.birth_date)} icon="calendar-outline" />
          <InfoRow label="Poids" value={formatWeight(animal.weight)} icon="scale-outline" />
          <InfoRow label="Appareil" value={animal.assigned_device ?? 'Non assigné'} icon="hardware-chip-outline" />
          <InfoRow label="Enregistré le" value={formatDate(animal.created_at)} icon="time-outline" last />
        </View>

        {/* ── Activité ─────────────────────────────── */}
        <View style={styles.card}>
          <View style={styles.cardHeader}>
            <Ionicons name="pulse-outline" size={18} color={Colors.primary} />
            <Text style={styles.cardTitle}>Activité</Text>
            {/* Sélecteur période */}
            <View style={styles.periodSelector}>
              {PERIOD_OPTIONS.map((opt) => (
                <TouchableOpacity
                  key={opt.hours}
                  style={[
                    styles.periodBtn,
                    historyHours === opt.hours && styles.periodBtnActive,
                  ]}
                  onPress={() => setHistoryHours(opt.hours)}
                >
                  <Text
                    style={[
                      styles.periodText,
                      historyHours === opt.hours && styles.periodTextActive,
                    ]}
                  >
                    {opt.label}
                  </Text>
                </TouchableOpacity>
              ))}
            </View>
          </View>

          {historyQuery.isLoading ? (
            <View style={styles.chartLoading}>
              <Text style={styles.chartLoadingText}>Chargement des données…</Text>
            </View>
          ) : (
            <ActivityChart records={records} />
          )}
        </View>

        {/* ── Distribution comportements ──────────── */}
        {records.length > 0 && (
          <View style={styles.card}>
            <View style={styles.cardHeader}>
              <Ionicons name="bar-chart-outline" size={18} color={Colors.primary} />
              <Text style={styles.cardTitle}>Répartition comportements</Text>
            </View>
            <BehaviorDistribution records={records} />
          </View>
        )}

        {/* ── Télémétrie dernière mesure ───────────── */}
        {latestRecord && (
          <View style={styles.card}>
            <View style={styles.cardHeader}>
              <Ionicons name="hardware-chip-outline" size={18} color={Colors.primary} />
              <Text style={styles.cardTitle}>Dernière mesure capteur</Text>
            </View>
            <InfoRow label="Activité brute" value={`${latestRecord.activity.toFixed(3)} g`} icon="pulse-outline" />
            {latestRecord.temperature && (
              <InfoRow label="Température" value={formatTemperature(latestRecord.temperature)} icon="thermometer-outline" />
            )}
            {latestRecord.speed !== null && (
              <InfoRow label="Vitesse GPS" value={latestRecord.speed != null ? `${latestRecord.speed.toFixed(1)} km/h` : '–'} icon="speedometer-outline" />
            )}
            {latestRecord.satellites !== null && (
              <InfoRow label="Satellites" value={String(latestRecord.satellites ?? '–')} icon="planet-outline" />
            )}
            <InfoRow label="Batterie" value={`${latestRecord.battery}%`} icon="battery-half-outline" last />
          </View>
        )}
      </ScrollView>
    </View>
  );
}

// ─── Styles ──────────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: Colors.bg.primary },
  content: { padding: Spacing.base, paddingBottom: Spacing['3xl'], gap: Spacing.md },

  // Hero
  heroCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: Colors.bg.card,
    borderRadius: Radius.xl,
    padding: Spacing.base,
    gap: Spacing.md,
    borderWidth: 1,
    borderColor: Colors.border.default,
  },
  heroAvatar: {
    width: 64,
    height: 64,
    borderRadius: Radius.full,
    alignItems: 'center',
    justifyContent: 'center',
  },
  heroAvatarText: { fontWeight: '800', fontSize: Typography['2xl'] },
  heroInfo: { flex: 1 },
  heroName: { fontSize: Typography.xl, fontWeight: '700', color: Colors.text.primary, marginBottom: Spacing.xs },
  heroBadges: { flexDirection: 'row', gap: Spacing.xs, flexWrap: 'wrap' },
  heroBattery: { alignItems: 'center', gap: 2 },
  heroBatteryText: { fontSize: Typography.xs, fontWeight: '700' },
  liveDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: Colors.primary,
    marginLeft: 'auto',
  },

  // Card
  card: {
    backgroundColor: Colors.bg.card,
    borderRadius: Radius.xl,
    padding: Spacing.base,
    borderWidth: 1,
    borderColor: Colors.border.default,
  },
  cardHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.sm,
    marginBottom: Spacing.md,
  },
  cardTitle: { fontSize: Typography.md, fontWeight: '700', color: Colors.text.primary, flex: 1 },

  // Position
  coordText: { fontSize: Typography.base, color: Colors.text.secondary, fontFamily: 'monospace', marginBottom: 4 },
  coordMeta: { fontSize: Typography.xs, color: Colors.text.muted },

  // Chart
  noDataChart: {
    height: 120,
    alignItems: 'center',
    justifyContent: 'center',
    gap: Spacing.sm,
  },
  noDataText: { fontSize: Typography.sm, color: Colors.text.muted },
  chartLoading: { height: 120, alignItems: 'center', justifyContent: 'center' },
  chartLoadingText: { color: Colors.text.muted, fontSize: Typography.sm },

  // Période
  periodSelector: {
    flexDirection: 'row',
    backgroundColor: Colors.bg.elevated,
    borderRadius: Radius.sm,
    padding: 2,
  },
  periodBtn: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: Radius.sm - 2 },
  periodBtnActive: { backgroundColor: Colors.primary },
  periodText: { fontSize: Typography.xs, color: Colors.text.secondary, fontWeight: '600' },
  periodTextActive: { color: '#fff' },

  // Behavior distribution
  behaviorDist: { gap: Spacing.sm },
  behaviorRow: { flexDirection: 'row', alignItems: 'center', gap: Spacing.sm },
  behaviorRowLeft: { flexDirection: 'row', alignItems: 'center', gap: 6, width: 90 },
  behaviorDot: { width: 8, height: 8, borderRadius: 4 },
  behaviorLabel: { fontSize: Typography.sm, color: Colors.text.secondary },
  behaviorBarBg: {
    flex: 1,
    height: 8,
    backgroundColor: Colors.bg.elevated,
    borderRadius: Radius.full,
    overflow: 'hidden',
  },
  behaviorBarFill: { height: '100%', borderRadius: Radius.full },
  behaviorPct: { width: 36, fontSize: Typography.sm, fontWeight: '700', textAlign: 'right' },
});
