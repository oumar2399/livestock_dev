import React, { useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator, FlatList, ScrollView, StyleSheet, Text,
  TouchableOpacity, View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { format, subDays } from 'date-fns';

import DrawerScreenBase from './DrawerScreenBase';
import { Colors, Radius, Spacing, Typography } from '../../constants/config';
import { useAnimals } from '../../hooks/useAnimals';
import { useAnimalTimeline } from '../../hooks/useHistory';
import { TimelineEventType, TimelineItem } from '../../types';

type Period = 7 | 30 | 0;

const EVENT_FILTERS: { value: TimelineEventType | null; label: string }[] = [
  { value: null, label: 'All' },
  { value: 'alert', label: 'Alerts' },
  { value: 'daily_summary', label: 'Summaries' },
  { value: 'prediction_feedback', label: 'Predictions' },
  { value: 'alert_feedback', label: 'Feedback' },
];

const eventVisuals: Record<TimelineEventType, { icon: string; color: string }> = {
  alert: { icon: 'warning-outline', color: Colors.severity.warning },
  daily_summary: { icon: 'calendar-outline', color: Colors.severity.info },
  prediction_feedback: { icon: 'analytics-outline', color: Colors.primary },
  alert_feedback: { icon: 'checkmark-done-outline', color: '#9B59B6' },
};

export default function HistoryScreen() {
  const animalsQuery = useAnimals({ page_size: 100 });
  const animals = useMemo(() => animalsQuery.data?.animals ?? [], [animalsQuery.data?.animals]);
  const [animalId, setAnimalId] = useState<number | null>(null);
  const [period, setPeriod] = useState<Period>(30);
  const [eventType, setEventType] = useState<TimelineEventType | null>(null);

  useEffect(() => {
    if (animalId === null && animals.length > 0) setAnimalId(animals[0].id);
    if (animalId !== null && animals.length > 0 && !animals.some((animal) => animal.id === animalId)) {
      setAnimalId(animals[0].id);
    }
  }, [animalId, animals]);

  const filters = useMemo(() => ({
    date_from: period ? format(subDays(new Date(), period), 'yyyy-MM-dd') : undefined,
    date_to: format(new Date(), 'yyyy-MM-dd'),
    event_type: eventType ? [eventType] : undefined,
    limit: 30,
  }), [eventType, period]);

  const timeline = useAnimalTimeline(animalId, filters);
  const events = timeline.data?.pages.flatMap((page) => page.items) ?? [];
  const selectedAnimal = animals.find((animal) => animal.id === animalId);

  const renderEvent = ({ item }: { item: TimelineItem }) => {
    const visual = eventVisuals[item.event_type];
    return (
      <View style={styles.eventRow}>
        <View style={[styles.eventIcon, { backgroundColor: visual.color + '20' }]}>
          <Ionicons name={visual.icon as any} size={18} color={visual.color} />
        </View>
        <View style={styles.eventBody}>
          <View style={styles.eventHeading}>
            <Text style={styles.eventTitle} numberOfLines={2}>{item.title}</Text>
            <Text style={styles.eventTime}>{format(new Date(item.occurred_at), 'MMM d, HH:mm')}</Text>
          </View>
          {item.summary ? <Text style={styles.eventSummary}>{item.summary}</Text> : null}
        </View>
      </View>
    );
  };

  return (
    <DrawerScreenBase title="Animal History" subtitle={selectedAnimal?.name}>
      <View style={styles.screen}>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.animalStrip}>
          {animals.map((animal) => {
            const selected = animal.id === animalId;
            return (
              <TouchableOpacity key={animal.id} style={[styles.animalButton, selected && styles.activeButton]}
                onPress={() => setAnimalId(animal.id)}>
                <Text style={[styles.buttonText, selected && styles.activeText]} numberOfLines={1}>{animal.name}</Text>
              </TouchableOpacity>
            );
          })}
        </ScrollView>

        <View style={styles.filters}>
          <View style={styles.segment}>
            {([7, 30, 0] as Period[]).map((value) => (
              <TouchableOpacity key={value} style={[styles.segmentButton, period === value && styles.segmentActive]}
                onPress={() => setPeriod(value)}>
                <Text style={[styles.segmentText, period === value && styles.activeText]}>{value === 0 ? 'All' : value + 'd'}</Text>
              </TouchableOpacity>
            ))}
          </View>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.eventFilters}>
            {EVENT_FILTERS.map((filter) => {
              const selected = eventType === filter.value;
              return (
                <TouchableOpacity key={filter.label} style={[styles.filterButton, selected && styles.activeButton]}
                  onPress={() => setEventType(filter.value)}>
                  <Text style={[styles.filterText, selected && styles.activeText]}>{filter.label}</Text>
                </TouchableOpacity>
              );
            })}
          </ScrollView>
        </View>

        {animalsQuery.isLoading || timeline.isLoading ? (
          <View style={styles.state}><ActivityIndicator size="large" color={Colors.primary} /></View>
        ) : animals.length === 0 ? (
          <View style={styles.state}><Text style={styles.stateText}>No animals available for this farm.</Text></View>
        ) : timeline.isError ? (
          <View style={styles.state}>
            <Text style={styles.stateText}>Unable to load history.</Text>
            <TouchableOpacity onPress={() => timeline.refetch()}><Text style={styles.retry}>Retry</Text></TouchableOpacity>
          </View>
        ) : (
          <FlatList
            data={events}
            keyExtractor={(item) => item.id}
            renderItem={renderEvent}
            contentContainerStyle={events.length ? styles.list : styles.emptyList}
            ListEmptyComponent={<Text style={styles.stateText}>No events for this period.</Text>}
            onEndReached={() => {
              if (timeline.hasNextPage && !timeline.isFetchingNextPage) timeline.fetchNextPage();
            }}
            onEndReachedThreshold={0.4}
            ListFooterComponent={timeline.isFetchingNextPage ? <ActivityIndicator color={Colors.primary} /> : null}
          />
        )}
      </View>
    </DrawerScreenBase>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  animalStrip: { paddingHorizontal: Spacing.base, paddingVertical: Spacing.sm, gap: Spacing.sm },
  animalButton: { height: 36, maxWidth: 140, justifyContent: 'center', paddingHorizontal: Spacing.md, borderRadius: Radius.sm, borderWidth: 1, borderColor: Colors.border.default, backgroundColor: Colors.bg.card },
  activeButton: { borderColor: Colors.primary, backgroundColor: Colors.primaryMuted },
  buttonText: { color: Colors.text.secondary, fontSize: Typography.sm, fontWeight: '600' },
  activeText: { color: Colors.primary },
  filters: { borderTopWidth: 1, borderBottomWidth: 1, borderColor: Colors.border.default, padding: Spacing.sm, gap: Spacing.sm },
  segment: { alignSelf: 'flex-start', flexDirection: 'row', backgroundColor: Colors.bg.card, borderRadius: Radius.sm, padding: 2 },
  segmentButton: { width: 52, height: 32, alignItems: 'center', justifyContent: 'center', borderRadius: Radius.sm },
  segmentActive: { backgroundColor: Colors.bg.elevated },
  segmentText: { color: Colors.text.muted, fontSize: Typography.xs, fontWeight: '700' },
  eventFilters: { gap: Spacing.xs },
  filterButton: { height: 32, justifyContent: 'center', paddingHorizontal: Spacing.md, borderRadius: Radius.sm, borderWidth: 1, borderColor: Colors.border.default },
  filterText: { color: Colors.text.muted, fontSize: Typography.xs, fontWeight: '600' },
  list: { paddingHorizontal: Spacing.base, paddingBottom: Spacing.xl },
  emptyList: { flexGrow: 1, alignItems: 'center', justifyContent: 'center' },
  eventRow: { flexDirection: 'row', gap: Spacing.md, paddingVertical: Spacing.md, borderBottomWidth: 1, borderColor: Colors.border.default },
  eventIcon: { width: 38, height: 38, borderRadius: Radius.sm, alignItems: 'center', justifyContent: 'center' },
  eventBody: { flex: 1 },
  eventHeading: { flexDirection: 'row', alignItems: 'flex-start', gap: Spacing.sm },
  eventTitle: { flex: 1, color: Colors.text.primary, fontSize: Typography.sm, fontWeight: '700' },
  eventTime: { color: Colors.text.muted, fontSize: Typography.xs },
  eventSummary: { marginTop: Spacing.xs, color: Colors.text.secondary, fontSize: Typography.xs, lineHeight: 18 },
  state: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: Spacing.md, padding: Spacing.xl },
  stateText: { color: Colors.text.muted, fontSize: Typography.sm, textAlign: 'center' },
  retry: { color: Colors.primary, fontWeight: '700' },
});
