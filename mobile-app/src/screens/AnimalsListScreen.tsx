/**
 * AnimalsListScreen - the whole herd
 * Filters: status (active/sick/sold/deceased), one scrolling row
 * Local search by name / official_id, opened from the search icon in the header
 * Navigation to AnimalDetail
 */
import React, { useState, useMemo } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  TouchableOpacity,
  TextInput,
  RefreshControl,
  ScrollView,
} from 'react-native';
import { useNavigation, DrawerActions } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';

import { useAnimals } from '../hooks/useAnimals';
import { useTelemetryLatest } from '../hooks/useTelemetry';
import { useFarmDevices } from '../hooks/useDevices';
import { collarHealthSuffix } from '../utils/deviceStatus';
import { useFarmStore } from '../store/farmStore';
import { Colors, Radius, Spacing, Typography } from '../constants/config';
import { Animal, AnimalStatus, TelemetryLatest } from '../types';
import {
  animalStatusColor,
  animalStatusLabel,
  animalAge,
  animalSexLabel,
  activityStateColor,
  activityStateLabel,
  timeAgo,
  formatWeight,
  batteryColor,
  evaluateFreshness,
  animalCollarStatus,
  CollarStatus,
} from '../utils/helpers';
import {
  ScreenHeader,
  LoadingState,
  ErrorState,
  EmptyState,
} from '../components/ui';

// ─── Status filters ───────────────────────────────────────────────────────────

const STATUS_FILTERS: { label: string; value: AnimalStatus | 'all' }[] = [
  { label: 'All', value: 'all' },
  { label: 'Active', value: 'active' },
  { label: 'Sick', value: 'sick' },
  { label: 'Sold', value: 'sold' },
  { label: 'Deceased', value: 'deceased' },
];

// ─── Animal card ─────────────────────────────────────────────────────────────

interface AnimalCardProps {
  animal: Animal;
  telemetry?: TelemetryLatest;
  collar: CollarStatus;
  healthSuffix: string;
  onPress: () => void;
}

function AnimalCard({ animal, telemetry, collar, healthSuffix, onPress }: AnimalCardProps) {
  const statusColor = animalStatusColor(animal.status);

  const freshness = evaluateFreshness({
    telemetryTime: telemetry?.last_update ?? animal.last_update,
    positionTime: telemetry?.position_time,
    latitude: telemetry?.latitude,
    longitude: telemetry?.longitude,
    deviceStatus: telemetry?.device_status,
    battery: telemetry?.battery,
  });

  // Use the ML-predicted state from the backend (or fallback to threshold)
  const activityState = telemetry && telemetry.behavior_eligible !== false
    ? (telemetry.activity_state ?? (telemetry.activity < 0.5 ? 'Resting' : 'Active'))
    : null;

  const behaviorColor = activityStateColor(activityState as any);

  return (
    <TouchableOpacity style={styles.card} onPress={onPress} activeOpacity={0.8}>
      {/* Avatar */}
      <View style={[styles.avatar, { backgroundColor: statusColor + '20' }]}>
        <Text style={[styles.avatarText, { color: statusColor }]}>
          {animal.name[0].toUpperCase()}
        </Text>
        {/* Data freshness, or collar alert */}
        <View
          style={[
            styles.onlineDot,
            // A collar that is not active (lost, maintenance, retired) wins over data freshness.
            { backgroundColor: collar.state !== 'active' && collar.state !== 'unknown' ? collar.color : freshness.telemetryColor },
          ]}
        />
      </View>

      {/* Main information */}
      <View style={styles.cardBody}>
        <View style={styles.cardTop}>
          <Text style={styles.animalName} numberOfLines={1}>{animal.name}</Text>
          <View style={[styles.statusBadge, { borderColor: statusColor }]}>
            <Text style={[styles.statusText, { color: statusColor }]}>
              Animal: {animalStatusLabel(animal.status)}
            </Text>
          </View>
        </View>

        <Text style={styles.animalMeta}>
          {animal.official_id ? `#${animal.official_id} · ` : ''}
          {animal.breed ?? animal.species} · {animalSexLabel(animal.sex)} · {animalAge(animal.birth_date)}
        </Text>

        <View style={styles.cardBottom}>
          {/* Collar (device) status, distinct from the animal status above */}
          <View style={styles.collarRow}>
            <Ionicons name="hardware-chip-outline" size={12} color={collar.color} />
            <Text style={[styles.collarText, { color: collar.color }]}>
              {collar.label}{animal.assigned_device ? ` · ${animal.assigned_device}` : ''}{healthSuffix}
            </Text>
          </View>

          {freshness.telemetryFreshness === 'recent' && activityState ? (
            <View style={[styles.behaviorTag, { backgroundColor: behaviorColor + '20' }]}>
              <View style={[styles.behaviorDot, { backgroundColor: behaviorColor }]} />
              <Text style={[styles.behaviorText, { color: behaviorColor }]}>
                Behaviour: {activityStateLabel(activityState as any)}
              </Text>
            </View>
          ) : (
            <Text style={styles.offlineText}>
              {freshness.telemetryLabel}
            </Text>
          )}

          {/* GPS indicator */}
          <View style={styles.gpsRow}>
            <Ionicons
              name={freshness.gpsStatus === 'fix' ? 'navigate-circle-outline' : 'navigate-outline'}
              size={12}
              color={freshness.gpsColor}
            />
            <Text style={[styles.gpsText, { color: freshness.gpsColor }]}>
              {freshness.gpsStatus === 'fix' ? 'GPS Fix' : freshness.gpsStatus === 'stale_fix' ? 'Old GPS' : freshness.gpsStatus === 'weak_fix' ? 'Weak GPS' : 'No GPS'}
            </Text>
          </View>

          {/* Battery, "Unknown" when unreadable */}
          {telemetry && (
            <View style={styles.batteryRow}>
              <Ionicons
                name="battery-half-outline"
                size={13}
                color={freshness.batteryColor}
              />
              <Text style={[styles.batteryText, { color: freshness.batteryColor }]}>
                {freshness.batteryLabel}
              </Text>
            </View>
          )}
        </View>
      </View>

      <Ionicons name="chevron-forward" size={18} color={Colors.text.muted} />
    </TouchableOpacity>
  );
}

// ─── Screen ───────────────────────────────────────────────────────────────────

export default function AnimalsListScreen() {
  const navigation = useNavigation<any>();
  const currentFarm = useFarmStore((state) =>
    state.farms.find((farm) => farm.id === state.currentFarmId),
  );
  const canEditAnimals = currentFarm?.permissions.includes('edit_animals') ?? false;

  const [search, setSearch] = useState('');
  const [searchOpen, setSearchOpen] = useState(false);
  const [statusFilter, setStatusFilter] = useState<AnimalStatus | 'all'>('all');

  // Load the list with the status filter
  const { data, isLoading, isError, refetch, isRefetching } = useAnimals({
    status: statusFilter !== 'all' ? statusFilter : undefined,
    page_size: 100,
  });

  const { data: telemetryData } = useTelemetryLatest({ limit: 100 });
  const { data: devices } = useFarmDevices();
  const telemetryMap = useMemo(
    () => new Map((telemetryData ?? []).map((t) => [t.animal_id, t])),
    [telemetryData],
  );

  // Local search (name or official_id)
  const filteredAnimals = useMemo(() => {
    const animals = data?.animals ?? [];
    if (!search.trim()) return animals;
    const q = search.toLowerCase();
    return animals.filter(
      (a) =>
        a.name.toLowerCase().includes(q) ||
        (a.official_id?.toLowerCase().includes(q) ?? false),
    );
  }, [data, search]);

  const handleAnimalPress = (animalId: number) => {
    navigation.navigate('AnimalDetail', { animalId });
  };

  // Closing the search also clears it, so a hidden query never filters the list.
  const toggleSearch = () => {
    if (searchOpen) setSearch('');
    setSearchOpen(!searchOpen);
  };

  if (isLoading && !data) return <LoadingState message="Loading..." />;
  if (isError && !data) return <ErrorState message="Can't load the animals" onRetry={refetch} />;

  return (
    // ScreenHeader already adds the top safe area: no second inset here.
    <View style={styles.screen}>
      <ScreenHeader
        title="Herd"
        subtitle={`${data?.total ?? 0} animals`}
        inlineSubtitle
        onBack={() => navigation.dispatch(DrawerActions.openDrawer())}
        backIcon="menu-outline"
        rightAction={(
          <View style={styles.headerActions}>
            <TouchableOpacity
              style={[styles.headerBtn, searchOpen && styles.headerBtnActive]}
              onPress={toggleSearch}
              accessibilityRole="button"
              accessibilityLabel={searchOpen ? 'Close search' : 'Search animals'}
            >
              <Ionicons name={searchOpen ? 'close' : 'search-outline'} size={20} color={Colors.primary} />
            </TouchableOpacity>
            {canEditAnimals && (
              <TouchableOpacity
                style={styles.headerBtn}
                onPress={() => navigation.navigate('AnimalForm')}
                accessibilityRole="button"
                accessibilityLabel="Add animal"
              >
                <Ionicons name="add" size={22} color={Colors.primary} />
              </TouchableOpacity>
            )}
          </View>
        )}
      />

      {/* Search, opened from the header icon */}
      {searchOpen && (
        <View style={styles.searchContainer}>
          <View style={styles.searchBar}>
            <Ionicons name="search-outline" size={18} color={Colors.text.muted} />
            <TextInput
              style={styles.searchInput}
              placeholder="Search by name or ID"
              placeholderTextColor={Colors.text.muted}
              value={search}
              onChangeText={setSearch}
              returnKeyType="search"
              clearButtonMode="while-editing"
              autoFocus
              accessibilityLabel="Search by name or ID"
            />
          </View>
        </View>
      )}

      {/* Status filters: one scrolling row */}
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        style={styles.filterBar}
        contentContainerStyle={styles.filtersScroll}
      >
        {STATUS_FILTERS.map((f) => {
          const active = statusFilter === f.value;
          const color = f.value !== 'all' ? animalStatusColor(f.value as AnimalStatus) : Colors.primary;
          return (
            <TouchableOpacity
              key={f.value}
              style={[
                styles.filterChip,
                active && { backgroundColor: color + '22', borderColor: color },
              ]}
              onPress={() => setStatusFilter(f.value)}
            >
              <Text style={[styles.filterText, active && { color }]}>{f.label}</Text>
            </TouchableOpacity>
          );
        })}
      </ScrollView>

      {/* List */}
      <FlatList
        data={filteredAnimals}
        keyExtractor={(item) => String(item.id)}
        contentContainerStyle={[
          styles.list,
          filteredAnimals.length === 0 && styles.listEmpty,
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
          <AnimalCard
            animal={item}
            telemetry={telemetryMap.get(item.id)}
            collar={animalCollarStatus(item.assigned_device, devices, telemetryMap.get(item.id)?.device_status)}
            healthSuffix={collarHealthSuffix(devices?.find((device) => device.id === item.assigned_device)?.health)}
            onPress={() => handleAnimalPress(item.id)}
          />
        )}
        ListEmptyComponent={
          <EmptyState
            icon="paw-outline"
            title="No animal found"
            message={
              search
                ? `No results for "${search}"`
                : 'No animals in this status'
            }
          />
        }
        ItemSeparatorComponent={() => <View style={styles.separator} />}
      />
    </View>
  );
}

// ─── Styles ──────────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: Colors.bg.primary },

  headerActions: { flexDirection: 'row', alignItems: 'center', gap: Spacing.sm },
  headerBtn: {
    width: 36, height: 36, borderRadius: Radius.full,
    backgroundColor: Colors.primary + '20',
    alignItems: 'center', justifyContent: 'center',
    borderWidth: 1, borderColor: Colors.primary + '50',
  },
  headerBtnActive: { backgroundColor: Colors.primary + '40' },
  searchContainer: {
    paddingHorizontal: Spacing.base,
    marginBottom: Spacing.sm,
  },
  searchBar: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: Colors.bg.input,
    borderRadius: Radius.lg,
    paddingHorizontal: Spacing.md,
    gap: Spacing.sm,
    height: 44,
    borderWidth: 1,
    borderColor: Colors.border.default,
  },
  searchInput: {
    flex: 1,
    color: Colors.text.primary,
    fontSize: Typography.base,
  },

  // A horizontal ScrollView grows to fill the column unless told not to.
  filterBar: { flexGrow: 0, flexShrink: 0, marginBottom: Spacing.sm },
  filtersScroll: {
    paddingHorizontal: Spacing.base,
    gap: Spacing.sm,
  },
  filterChip: {
    paddingHorizontal: Spacing.md,
    paddingVertical: 5,
    borderRadius: Radius.full,
    borderWidth: 1,
    borderColor: Colors.border.default,
  },
  filterText: {
    fontSize: Typography.sm,
    color: Colors.text.secondary,
    fontWeight: '500',
  },

  list: { paddingHorizontal: Spacing.base, paddingBottom: Spacing['2xl'] },
  listEmpty: { flex: 1 },
  separator: { height: 6 },

  // Card
  card: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: Colors.bg.card,
    borderRadius: Radius.lg,
    paddingVertical: Spacing.sm,
    paddingHorizontal: Spacing.md,
    borderWidth: 1,
    borderColor: Colors.border.default,
    gap: Spacing.md,
  },
  avatar: {
    width: 40,
    height: 40,
    borderRadius: Radius.full,
    alignItems: 'center',
    justifyContent: 'center',
  },
  avatarText: { fontWeight: '700', fontSize: Typography.md },
  onlineDot: {
    position: 'absolute',
    bottom: 0,
    right: 0,
    width: 11,
    height: 11,
    borderRadius: 6,
    borderWidth: 2,
    borderColor: Colors.bg.card,
  },

  cardBody: { flex: 1 },
  cardTop: { flexDirection: 'row', alignItems: 'center', gap: Spacing.sm, marginBottom: 2 },
  animalName: {
    flex: 1,
    fontSize: Typography.base,
    fontWeight: '700',
    color: Colors.text.primary,
  },
  collarRow: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  collarText: { fontSize: Typography.xs, fontWeight: '600' },
  statusBadge: {
    paddingHorizontal: 7,
    paddingVertical: 2,
    borderRadius: Radius.sm,
    borderWidth: 1,
  },
  statusText: { fontSize: 10, fontWeight: '600' },
  animalMeta: {
    fontSize: Typography.xs,
    color: Colors.text.secondary,
    marginBottom: 3,
  },
  cardBottom: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', columnGap: Spacing.sm, rowGap: 2 },
  behaviorTag: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 7,
    paddingVertical: 2,
    borderRadius: Radius.sm,
    gap: 4,
  },
  behaviorDot: { width: 5, height: 5, borderRadius: 3 },
  behaviorText: { fontSize: Typography.xs, fontWeight: '600' },
  offlineText: { fontSize: Typography.xs, color: Colors.text.muted },
  gpsRow: { flexDirection: 'row', alignItems: 'center', gap: 2 },
  gpsText: { fontSize: Typography.xs, fontWeight: '600' },
  batteryRow: { flexDirection: 'row', alignItems: 'center', gap: 2 },
  batteryText: { fontSize: Typography.xs, fontWeight: '600' },
});
