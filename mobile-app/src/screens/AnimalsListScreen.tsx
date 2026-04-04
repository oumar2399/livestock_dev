/**
 * AnimalsListScreen - Liste complète du troupeau
 * Filtres : statut (active/sick/sold/deceased)
 * Recherche locale par nom / official_id
 * Navigation vers AnimalDetail
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
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { DrawerActions } from '@react-navigation/native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';

import { useAnimals } from '../hooks/useAnimals';
import { useTelemetryLatest } from '../hooks/useTelemetry';
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
} from '../utils/helpers';
import {
  ScreenHeader,
  LoadingState,
  ErrorState,
  EmptyState,
} from '../components/ui';

// ─── Filtres statut ───────────────────────────────────────────────────────────

const STATUS_FILTERS: { label: string; value: AnimalStatus | 'all' }[] = [
  { label: 'All', value: 'all' },
  { label: 'Active', value: 'active' },
  { label: 'Sick', value: 'sick' },
  { label: 'Sold', value: 'sold' },
  { label: 'Deceased', value: 'deceased' },
];

// ─── Carte animal ─────────────────────────────────────────────────────────────

interface AnimalCardProps {
  animal: Animal;
  telemetry?: TelemetryLatest;
  onPress: () => void;
}

function AnimalCard({ animal, telemetry, onPress }: AnimalCardProps) {
  const statusColor = animalStatusColor(animal.status);
  const isOnline = !!telemetry;

  const activityState = telemetry
    ? telemetry.activity < 0.15 ? 'lying'
    : telemetry.activity < 0.5 ? 'standing'
    : telemetry.activity < 1.0 ? 'walking' : 'running'
    : null;


  const behaviorColor = activityStateColor(activityState as any);

  return (
    <TouchableOpacity style={styles.card} onPress={onPress} activeOpacity={0.8}>
      {/* Avatar */}
      <View style={[styles.avatar, { backgroundColor: statusColor + '20' }]}>
        <Text style={[styles.avatarText, { color: statusColor }]}>
          {animal.name[0].toUpperCase()}
        </Text>
        {/* Indicateur online/offline */}
        <View
          style={[
            styles.onlineDot,
            { backgroundColor: isOnline ? Colors.status.healthy : Colors.status.offline },
          ]}
        />
      </View>

      {/* Infos principales */}
      <View style={styles.cardBody}>
        <View style={styles.cardTop}>
          <Text style={styles.animalName} numberOfLines={1}>{animal.name}</Text>
          <View style={[styles.statusBadge, { borderColor: statusColor }]}>
            <Text style={[styles.statusText, { color: statusColor }]}>
              {animalStatusLabel(animal.status)}
            </Text>
          </View>
        </View>

        <Text style={styles.animalMeta}>
          {animal.official_id ? `#${animal.official_id} · ` : ''}
          {animal.breed ?? animal.species} · {animalSexLabel(animal.sex)} · {animalAge(animal.birth_date)}
        </Text>

        <View style={styles.cardBottom}>
          {isOnline && activityState ? (
            <View style={[styles.behaviorTag, { backgroundColor: behaviorColor + '20' }]}>
              <View style={[styles.behaviorDot, { backgroundColor: behaviorColor }]} />
              <Text style={[styles.behaviorText, { color: behaviorColor }]}>
                {activityStateLabel(activityState as any)}
              </Text>
            </View>
          ) : (
            <Text style={styles.offlineText}>
              {animal.last_update ? `Seen ${timeAgo(animal.last_update)}` : 'Never seen'}
            </Text>
          )}

          {isOnline && telemetry && (
            <View style={styles.batteryRow}>
              <Ionicons
                name="battery-half-outline"
                size={13}
                color={batteryColor(telemetry.battery)}
              />
              <Text style={[styles.batteryText, { color: batteryColor(telemetry.battery) }]}>
                {telemetry.battery}%
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
  const insets = useSafeAreaInsets();
  const navigation = useNavigation<any>();

  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<AnimalStatus | 'all'>('all');

  // Charger liste avec filtre statut
  const { data, isLoading, isError, refetch, isRefetching } = useAnimals({
    status: statusFilter !== 'all' ? statusFilter : undefined,
    page_size: 100,
  });

  const { data: telemetryData } = useTelemetryLatest({ limit: 100 });
  const telemetryMap = useMemo(
    () => new Map((telemetryData ?? []).map((t) => [t.animal_id, t])),
    [telemetryData],
  );

  // Recherche locale (nom ou official_id)
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

  if (isLoading && !data) return <LoadingState message="Loading..." />;
  if (isError && !data) return <ErrorState message="Can't load the animals" onRetry={refetch} />;

  return (
    <View style={[styles.screen, { paddingTop: insets.top }]}>
      <ScreenHeader
        title="Herd"
        subtitle={`${data?.total ?? 0} animals`}
        onBack={() => navigation.dispatch(DrawerActions.openDrawer())}
        backIcon="menu-outline"
        rightAction={
          <TouchableOpacity
            style={styles.addBtn}
            onPress={() => navigation.navigate('AnimalForm')}
          >
            <Ionicons name="add" size={22} color={Colors.primary} />
          </TouchableOpacity>
        }
      />

      {/* Recherche */}
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
          />
        </View>
      </View>

      {/* Filtres statut */}
      <View style={styles.filtersScroll}>
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
      </View>

      {/* Liste */}
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

  filtersScroll: {
    flexDirection: 'row',
    paddingHorizontal: Spacing.base,
    gap: Spacing.sm,
    marginBottom: Spacing.md,
    flexWrap: 'wrap',
  },
  filterChip: {
    paddingHorizontal: Spacing.md,
    paddingVertical: 6,
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
  separator: { height: Spacing.sm },

  // Card
  card: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: Colors.bg.card,
    borderRadius: Radius.lg,
    padding: Spacing.md,
    borderWidth: 1,
    borderColor: Colors.border.default,
    gap: Spacing.md,
  },
  avatar: {
    width: 52,
    height: 52,
    borderRadius: Radius.full,
    alignItems: 'center',
    justifyContent: 'center',
  },
  avatarText: { fontWeight: '700', fontSize: Typography.lg },
  onlineDot: {
    position: 'absolute',
    bottom: 1,
    right: 1,
    width: 12,
    height: 12,
    borderRadius: 6,
    borderWidth: 2,
    borderColor: Colors.bg.card,
  },

  cardBody: { flex: 1 },
  cardTop: { flexDirection: 'row', alignItems: 'center', gap: Spacing.sm, marginBottom: 3 },
  animalName: {
    flex: 1,
    fontSize: Typography.base,
    fontWeight: '700',
    color: Colors.text.primary,
  },
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
    marginBottom: Spacing.xs,
  },
  cardBottom: { flexDirection: 'row', alignItems: 'center', gap: Spacing.sm },
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
  batteryRow: { flexDirection: 'row', alignItems: 'center', gap: 2 },
  batteryText: { fontSize: Typography.xs, fontWeight: '600' },
  addBtn: {
    width: 36, height: 36, borderRadius: Radius.full,
    backgroundColor: Colors.primary + '20',
    alignItems: 'center', justifyContent: 'center',
    borderWidth: 1, borderColor: Colors.primary + '50',
  },
});