/**
 * AnimalDetailScreen - Full animal profile
 * General info + GPS position + activity chart + daily time budget
 */
import React, { useState } from 'react';
import {
  View,
  Text,
  ScrollView,
  StyleSheet,
  TouchableOpacity,
  RefreshControl,
  Alert,
} from 'react-native';
import { useRoute, useNavigation, RouteProp } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { LineChart, PieChart } from 'react-native-gifted-charts';
import { format } from 'date-fns';
import { useQueryClient } from '@tanstack/react-query';

import { AnimalsStackParamList, ActivityState, TelemetryRecord } from '../types';
import { useAnimal } from '../hooks/useAnimals';
import { useTelemetryHistory } from '../hooks/useTelemetry';
import { useActivitySummary, ActivityBudgetItem } from '../hooks/useActivity';
import { Colors, Radius, Spacing, Typography } from '../constants/config';
import apiClient from '../api/client';
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

// ─── Constants ────────────────────────────────────────────────────────────────

const PERIOD_OPTIONS = [
  { label: '6h',  hours: 6   },
  { label: '24h', hours: 24  },
  { label: '7d',  hours: 168 },
];

const BUDGET_COLORS = {
  lying:    '#6C8EBF',
  standing: '#82B366',
  walking:  '#F0A500',
  running:  '#D64045',
};

const BUDGET_LABELS = {
  lying:    'Lying',
  standing: 'Standing',
  walking:  'Walking',
  running:  'Running',
};

// ─── Activity Chart ───────────────────────────────────────────────────────────

// ─── Activity Chart ───────────────────────────────────────────────────────────

function ActivityChart({ records }: { records: TelemetryRecord[] }) {
  if (!records.length) {
    return (
      <View style={styles.noDataChart}>
        <Ionicons name="bar-chart-outline" size={32} color={Colors.text.muted} />
        <Text style={styles.noDataText}>No data available</Text>
      </View>
    );
  }

  const step = Math.ceil(records.length / 5);

  const chartData = records.map((r, i) => ({
    value: parseFloat(r.activity.toFixed(3)),
    label: i % step === 0 ? format(new Date(r.time), 'HH:mm') : '',
    labelTextStyle: { color: Colors.text.muted, fontSize: 9 },
  }));

  return (
    <LineChart
      data={chartData}
      height={130}
      curved
      areaChart
      color={Colors.primary}
      startFillColor={Colors.primary + '50'}
      endFillColor={Colors.primary + '05'}
      thickness={2}
      hideDataPoints
      xAxisColor={Colors.border.default}
      yAxisColor={Colors.border.default}
      yAxisTextStyle={{ color: Colors.text.muted, fontSize: 9 }}
      rulesColor={Colors.border.default}
      rulesType="dashed"
      noOfSections={4}
      yAxisSuffix="g"
      initialSpacing={0}
      endSpacing={8}
      adjustToWidth
    />
  );
}

// ─── Daily Time Budget (Pie Chart) ────────────────────────────────────────────

function ActivityBudgetChart({ animalId }: { animalId: number }) {
  const { data, isLoading, isError, error } = useActivitySummary(animalId);

  if (isLoading) {
    return (
      <View style={styles.chartLoading}>
        <Text style={styles.chartLoadingText}>Loading budget…</Text>
      </View>
    );
  }

  if (isError || !data) {
    return (
      <View style={styles.noDataChart}>
        <Ionicons name="pie-chart-outline" size={32} color={Colors.text.muted} />
        <Text style={styles.noDataText}>No data for today</Text>
      </View>
    );
  }

  const pieData = (
    Object.entries(data.budget) as [keyof typeof BUDGET_COLORS, ActivityBudgetItem][]
  )
    .filter(([, item]) => item.percentage > 0)
    .map(([state, item]) => ({
      value: item.percentage,
      color: BUDGET_COLORS[state],
      text: '',
    }));

  return (
    <View>
      {/* Pie */}
      <View style={{ alignItems: 'center' }}>
        <PieChart
          data={pieData}
          donut
          radius={90}
          innerRadius={55}
          innerCircleColor={Colors.bg.card}
        />
      </View>

      {/* Legend */}
      <View style={styles.budgetLegend}>
        {(
          Object.entries(data.budget) as [keyof typeof BUDGET_COLORS, ActivityBudgetItem][]
        ).map(([state, item]) => (
          <View key={state} style={styles.budgetLegendRow}>
            <View style={styles.budgetLegendLeft}>
              <View style={[styles.dot, { backgroundColor: BUDGET_COLORS[state] }]} />
              <Text style={styles.budgetLabel}>{BUDGET_LABELS[state]}</Text>
            </View>
            <Text style={styles.budgetMinutes}>{item.minutes} min</Text>
            <Text style={[styles.budgetPct, { color: BUDGET_COLORS[state] }]}>
              {item.percentage}%
            </Text>
          </View>
        ))}
      </View>

      {/* Meta */}
      <Text style={styles.budgetMeta}>
        {data.total_records} records · {data.duration_hours}h coverage
      </Text>
    </View>
  );
}

// ─── Screen ───────────────────────────────────────────────────────────────────

type RouteProps = RouteProp<AnimalsStackParamList, 'AnimalDetail'>;

export default function AnimalDetailScreen() {
  const route      = useRoute<RouteProps>();
  const navigation = useNavigation<any>();
  const insets     = useSafeAreaInsets();
  const queryClient = useQueryClient();
  const { animalId } = route.params;

  const [historyHours, setHistoryHours] = useState(24);

  const handleDelete = (animalName: string) => {
    Alert.alert(
      'Delete Animal',
      `Delete ${animalName}? All its data (telemetry, alerts) will be permanently deleted.`,
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Delete',
          style: 'destructive',
          onPress: async () => {
            try {
              await apiClient.delete(`/animals/${animalId}`);
              queryClient.invalidateQueries({ queryKey: ['animals'] });
              navigation.navigate('AnimalsList');
            } catch {
              Alert.alert('Error', 'Failed to delete the animal');
            }
          },
        },
      ]
    );
  };

  const animalQuery  = useAnimal(animalId);
  const historyQuery = useTelemetryHistory(animalId, historyHours);

  const animal      = animalQuery.data;
  const records     = historyQuery.data ?? [];
  const latestRecord = records[records.length - 1];

  console.log('=== DEBUG ===');
  console.log('records count:', records.length);
  console.log('latestRecord:', latestRecord);
  console.log('historyQuery status:', historyQuery.status);
  console.log('historyQuery error:', historyQuery.error);

  const onRefresh = () => {
    animalQuery.refetch();
    historyQuery.refetch();
  };

  if (animalQuery.isLoading) return <LoadingState message="Loading animal profile…" />;
  if (animalQuery.isError || !animal) {
    return <ErrorState message="Animal not found" onRetry={() => animalQuery.refetch()} />;
  }

  const statusColor  = animalStatusColor(animal.status);
  const isLive       = isRecentUpdate(animal.last_update);
  const currentState = latestRecord?.activity_state as ActivityState | null;

  return (
    <View style={[styles.screen, { paddingTop: insets.top }]}>
      <ScreenHeader
        title={animal.name}
        subtitle={`${animal.official_id ? `#${animal.official_id} · ` : ''}${animal.breed ?? animal.species}`}
        onBack={() => navigation.goBack()}
        rightAction={
          <TouchableOpacity
            style={styles.editBtn}
            onPress={() => navigation.navigate('AnimalForm', { animalId: animal.id })}
          >
            <Ionicons name="create-outline" size={20} color={Colors.primary} />
          </TouchableOpacity>
        }
      />

      <ScrollView
        contentContainerStyle={styles.content}
        showsVerticalScrollIndicator={false}
        refreshControl={
          <RefreshControl
            refreshing={animalQuery.isRefetching}
            onRefresh={onRefresh}
            tintColor={Colors.primary}
          />
        }
      >
        {/* ── Hero ─────────────────────────────────── */}
        <View style={styles.heroCard}>
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

        {/* ── GPS Position ─────────────────────────── */}
        <View style={styles.card}>
          <View style={styles.cardHeader}>
            <Ionicons name="location-outline" size={18} color={Colors.primary} />
            <Text style={styles.cardTitle}>GPS Position</Text>
            {isLive && <View style={styles.liveDot} />}
          </View>
          <Text style={styles.coordText}>
            {formatCoords(animal.last_latitude, animal.last_longitude)}
          </Text>
          <Text style={styles.coordMeta}>
            {animal.last_update
              ? `Last updated: ${timeAgo(animal.last_update)}`
              : 'No position recorded'}
          </Text>
        </View>

        {/* ── Informations ─────────────────────────── */}
        <View style={styles.card}>
          <View style={styles.cardHeader}>
            <Ionicons name="information-circle-outline" size={18} color={Colors.primary} />
            <Text style={styles.cardTitle}>Informations</Text>
          </View>
          <InfoRow label="Identifier"    value={animal.official_id ?? '–'}               icon="barcode-outline"       />
          <InfoRow label="Species"       value={animal.species}                           icon="paw-outline"           />
          <InfoRow label="Breed"         value={animal.breed ?? '–'}                     icon="leaf-outline"          />
          <InfoRow label="Gender"        value={animalSexLabel(animal.sex)}               icon="male-female-outline"   />
          <InfoRow label="Age"           value={animalAge(animal.birth_date)}             icon="calendar-outline"      />
          <InfoRow label="Weight"        value={formatWeight(animal.weight)}              icon="scale-outline"         />
          <InfoRow label="Device"        value={animal.assigned_device ?? 'Not assigned'} icon="hardware-chip-outline" />
          <InfoRow label="Registered on" value={formatDate(animal.created_at)}            icon="time-outline"          last />
        </View>

        {/* ── Activity Chart ───────────────────────── */}
        <View style={styles.card}>
          <View style={styles.cardHeader}>
            <Ionicons name="pulse-outline" size={18} color={Colors.primary} />
            <Text style={styles.cardTitle}>Activity</Text>
            <View style={styles.periodSelector}>
              {PERIOD_OPTIONS.map((opt) => (
                <TouchableOpacity
                  key={opt.hours}
                  style={[styles.periodBtn, historyHours === opt.hours && styles.periodBtnActive]}
                  onPress={() => setHistoryHours(opt.hours)}
                >
                  <Text style={[styles.periodText, historyHours === opt.hours && styles.periodTextActive]}>
                    {opt.label}
                  </Text>
                </TouchableOpacity>
              ))}
            </View>
          </View>
          {historyQuery.isLoading ? (
            <View style={styles.chartLoading}>
              <Text style={styles.chartLoadingText}>Loading data…</Text>
            </View>
          ) : (
            <ActivityChart records={records} />
          )}
        </View>

        {/* ── Daily Time Budget ────────────────────── */}
        <View style={styles.card}>
          <View style={styles.cardHeader}>
            <Ionicons name="pie-chart-outline" size={18} color={Colors.primary} />
            <Text style={styles.cardTitle}>Daily Time Budget</Text>
          </View>
          <ActivityBudgetChart animalId={animalId} />
        </View>

        {/* ── Latest Sensor Reading ────────────────── */}
        {latestRecord && (
          <View style={styles.card}>
            <View style={styles.cardHeader}>
              <Ionicons name="hardware-chip-outline" size={18} color={Colors.primary} />
              <Text style={styles.cardTitle}>Latest Sensor Reading</Text>
            </View>
            <InfoRow label="Raw Activity" value={`${latestRecord.activity.toFixed(3)} g`}  icon="pulse-outline"       />
            {latestRecord.temperature && (
              <InfoRow label="Temperature" value={formatTemperature(latestRecord.temperature)} icon="thermometer-outline" />
            )}
            {latestRecord.speed != null && (
              <InfoRow label="GPS Speed"  value={`${latestRecord.speed.toFixed(1)} km/h`}  icon="speedometer-outline" />
            )}
            {latestRecord.satellites != null && (
              <InfoRow label="Satellites" value={String(latestRecord.satellites)}           icon="planet-outline"      />
            )}
            <InfoRow label="Battery"      value={`${latestRecord.battery}%`}               icon="battery-half-outline" last />
          </View>
        )}

        {/* ── Delete ───────────────────────────────── */}
        <TouchableOpacity
          style={styles.deleteBtn}
          onPress={() => handleDelete(animal.name)}
        >
          <Ionicons name="trash-outline" size={18} color={Colors.severity.critical} />
          <Text style={styles.deleteBtnText}>Delete this animal</Text>
        </TouchableOpacity>
      </ScrollView>
    </View>
  );
}

// ─── Styles ──────────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
  screen:  { flex: 1, backgroundColor: Colors.bg.primary },
  content: { padding: Spacing.base, paddingBottom: Spacing['3xl'], gap: Spacing.md },

  // Hero
  heroCard: {
    flexDirection: 'row', alignItems: 'center',
    backgroundColor: Colors.bg.card, borderRadius: Radius.xl,
    padding: Spacing.base, gap: Spacing.md,
    borderWidth: 1, borderColor: Colors.border.default,
  },
  heroAvatar:     { width: 64, height: 64, borderRadius: Radius.full, alignItems: 'center', justifyContent: 'center' },
  heroAvatarText: { fontWeight: '800', fontSize: Typography['2xl'] },
  heroInfo:       { flex: 1 },
  heroName:       { fontSize: Typography.xl, fontWeight: '700', color: Colors.text.primary, marginBottom: Spacing.xs },
  heroBadges:     { flexDirection: 'row', gap: Spacing.xs, flexWrap: 'wrap' },
  heroBattery:    { alignItems: 'center', gap: 2 },
  heroBatteryText: { fontSize: Typography.xs, fontWeight: '700' },
  liveDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: Colors.primary, marginLeft: 'auto' },

  // Card
  card: {
    backgroundColor: Colors.bg.card, borderRadius: Radius.xl,
    padding: Spacing.base, borderWidth: 1, borderColor: Colors.border.default,
  },
  cardHeader: { flexDirection: 'row', alignItems: 'center', gap: Spacing.sm, marginBottom: Spacing.md },
  cardTitle:  { fontSize: Typography.md, fontWeight: '700', color: Colors.text.primary, flex: 1 },

  // GPS
  coordText: { fontSize: Typography.base, color: Colors.text.secondary, fontFamily: 'monospace', marginBottom: 4 },
  coordMeta: { fontSize: Typography.xs, color: Colors.text.muted },

  // Chart shared
  noDataChart:      { height: 120, alignItems: 'center', justifyContent: 'center', gap: Spacing.sm },
  noDataText:       { fontSize: Typography.sm, color: Colors.text.muted },
  chartLoading:     { height: 120, alignItems: 'center', justifyContent: 'center' },
  chartLoadingText: { color: Colors.text.muted, fontSize: Typography.sm },

  // Period selector
  periodSelector:  { flexDirection: 'row', backgroundColor: Colors.bg.elevated, borderRadius: Radius.sm, padding: 2 },
  periodBtn:       { paddingHorizontal: 8, paddingVertical: 3, borderRadius: Radius.sm - 2 },
  periodBtnActive: { backgroundColor: Colors.primary },
  periodText:      { fontSize: Typography.xs, color: Colors.text.secondary, fontWeight: '600' },
  periodTextActive: { color: '#fff' },

  // Budget Temps
  budgetLegend:    { gap: Spacing.sm, marginTop: Spacing.sm },
  budgetLegendRow: { flexDirection: 'row', alignItems: 'center', gap: Spacing.sm },
  budgetLegendLeft: { flexDirection: 'row', alignItems: 'center', gap: 6, flex: 1 },
  dot:             { width: 8, height: 8, borderRadius: 4 },
  budgetLabel:     { fontSize: Typography.sm, color: Colors.text.secondary },
  budgetMinutes:   { fontSize: Typography.sm, color: Colors.text.muted, width: 55, textAlign: 'right' },
  budgetPct:       { width: 40, fontSize: Typography.sm, fontWeight: '700', textAlign: 'right' },
  budgetMeta:      { fontSize: Typography.xs, color: Colors.text.muted, textAlign: 'center', marginTop: Spacing.sm },

  // Edit / Delete
  editBtn: {
    width: 36, height: 36, borderRadius: Radius.full,
    backgroundColor: Colors.primary + '20', alignItems: 'center', justifyContent: 'center',
    borderWidth: 1, borderColor: Colors.primary + '50',
  },
  deleteBtn: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    gap: Spacing.sm, marginTop: Spacing.md, padding: Spacing.md,
    borderRadius: Radius.md, borderWidth: 1,
    borderColor: Colors.severity.critical + '50',
    backgroundColor: Colors.severity.critical + '10',
  },
  deleteBtnText: { color: Colors.severity.critical, fontSize: Typography.sm, fontWeight: '600' },
});