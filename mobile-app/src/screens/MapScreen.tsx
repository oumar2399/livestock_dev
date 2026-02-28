/**
 * MapScreen - Carte temps réel du troupeau
 * Polling GET /telemetry/latest toutes les 10s
 * Marqueurs colorés par état d'activité
 */
import React, { useRef, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  Modal,
  ScrollView,
} from 'react-native';
import MapView, { Marker, Callout, PROVIDER_DEFAULT } from 'react-native-maps';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useNavigation } from '@react-navigation/native';

import { useTelemetryLatest } from '../hooks/useTelemetry';
import { Colors, Radius, Spacing, Typography } from '../constants/config';
import { TelemetryLatest, ActivityState } from '../types';
import {
  activityStateColor,
  activityStateLabel,
  timeAgo,
  batteryColor,
  batteryIcon,
} from '../utils/helpers';
import { LoadingState, ErrorState } from '../components/ui';

// ─── Calcul état depuis valeur activity (miroir de calculate_activity_state backend) ──

function getActivityState(activity: number): ActivityState {
  if (activity < 0.15) return 'lying';
  if (activity < 0.5) return 'standing';
  if (activity < 1.0) return 'walking';
  return 'running';
}

// ─── Marqueur animal ──────────────────────────────────────────────────────────

function AnimalMarker({ point, onPress }: { point: TelemetryLatest; onPress: () => void }) {
  const state = getActivityState(point.activity);
  const color = activityStateColor(state);

  return (
    <Marker
      coordinate={{ latitude: point.latitude, longitude: point.longitude }}
      onPress={onPress}
      tracksViewChanges={false}
    >
      <View style={styles.markerContainer}>
        <View style={[styles.markerOuter, { borderColor: color }]}>
          <View style={[styles.markerInner, { backgroundColor: color }]}>
            <Text style={styles.markerInitial}>{point.animal_name[0].toUpperCase()}</Text>
          </View>
        </View>
        <View style={[styles.markerTail, { backgroundColor: color }]} />
      </View>
    </Marker>
  );
}

// ─── Bottom sheet info animal ─────────────────────────────────────────────────

function AnimalInfoSheet({
  point,
  onClose,
  onNavigate,
}: {
  point: TelemetryLatest | null;
  onClose: () => void;
  onNavigate: (id: number) => void;
}) {
  if (!point) return null;
  const state = getActivityState(point.activity);
  const stateColor = activityStateColor(state);
  const batColor = batteryColor(point.battery);

  return (
    <View style={styles.infoSheet}>
      <View style={styles.infoSheetHandle} />

      <View style={styles.infoSheetHeader}>
        <View style={[styles.infoAnimalAvatar, { backgroundColor: stateColor + '20' }]}>
          <Text style={[styles.infoAvatarText, { color: stateColor }]}>
            {point.animal_name[0].toUpperCase()}
          </Text>
        </View>
        <View style={styles.infoSheetTitle}>
          <Text style={styles.infoAnimalName}>{point.animal_name}</Text>
          <Text style={styles.infoDeviceId}>Appareil: {point.device_id}</Text>
        </View>
        <TouchableOpacity onPress={onClose} hitSlop={12}>
          <Ionicons name="close" size={22} color={Colors.text.secondary} />
        </TouchableOpacity>
      </View>

      <View style={styles.infoStats}>
        {/* Comportement */}
        <View style={styles.infoStat}>
          <View style={[styles.infoStatIcon, { backgroundColor: stateColor + '20' }]}>
            <Ionicons name="walk-outline" size={18} color={stateColor} />
          </View>
          <Text style={styles.infoStatLabel}>Comportement</Text>
          <Text style={[styles.infoStatValue, { color: stateColor }]}>
            {activityStateLabel(state)}
          </Text>
        </View>

        {/* Activité */}
        <View style={styles.infoStat}>
          <View style={[styles.infoStatIcon, { backgroundColor: Colors.primary + '20' }]}>
            <Ionicons name="pulse-outline" size={18} color={Colors.primary} />
          </View>
          <Text style={styles.infoStatLabel}>Activité</Text>
          <Text style={styles.infoStatValue}>{point.activity.toFixed(2)} g</Text>
        </View>

        {/* Batterie */}
        <View style={styles.infoStat}>
          <View style={[styles.infoStatIcon, { backgroundColor: batColor + '20' }]}>
            <Ionicons name={batteryIcon(point.battery) as any} size={18} color={batColor} />
          </View>
          <Text style={styles.infoStatLabel}>Batterie</Text>
          <Text style={[styles.infoStatValue, { color: batColor }]}>{point.battery}%</Text>
        </View>
      </View>

      <View style={styles.infoFooter}>
        <Text style={styles.infoUpdated}>Mis à jour {timeAgo(point.last_update)}</Text>
        <TouchableOpacity
          style={styles.infoDetailBtn}
          onPress={() => onNavigate(point.animal_id)}
        >
          <Text style={styles.infoDetailBtnText}>Voir fiche complète</Text>
          <Ionicons name="arrow-forward" size={16} color={Colors.primary} />
        </TouchableOpacity>
      </View>
    </View>
  );
}

// ─── Screen ───────────────────────────────────────────────────────────────────

export default function MapScreen() {
  const insets = useSafeAreaInsets();
  const navigation = useNavigation<any>();
  const mapRef = useRef<MapView>(null);
  const [selectedAnimal, setSelectedAnimal] = useState<TelemetryLatest | null>(null);

  const { data, isLoading, isError, refetch, dataUpdatedAt } = useTelemetryLatest({ limit: 100 });

  const points = data ?? [];

  // Centrer la carte sur le troupeau
  const fitToAnimals = () => {
    if (!points.length || !mapRef.current) return;
    mapRef.current.fitToCoordinates(
      points.map((p) => ({ latitude: p.latitude, longitude: p.longitude })),
      { edgePadding: { top: 80, right: 40, bottom: 200, left: 40 }, animated: true },
    );
  };

  const handleMarkerPress = (point: TelemetryLatest) => {
    setSelectedAnimal(point);
  };

  const handleNavigateToAnimal = (animalId: number) => {
    setSelectedAnimal(null);
    navigation.navigate('Animals', {
      screen: 'AnimalDetail',
      params: { animalId },
    });
  };

  if (isLoading && !data) {
    return <LoadingState message="Chargement de la carte…" />;
  }

  if (isError && !data) {
    return <ErrorState message="Impossible de charger les positions" onRetry={refetch} />;
  }

  return (
    <View style={styles.screen}>
      {/* Map */}
      <MapView
        ref={mapRef}
        style={StyleSheet.absoluteFillObject}
        provider={PROVIDER_DEFAULT}
        initialRegion={{
          latitude: points[0]?.latitude ?? 35.6762,
          longitude: points[0]?.longitude ?? 139.6503,
          latitudeDelta: 0.05,
          longitudeDelta: 0.05,
        }}
        mapType="satellite"
        showsUserLocation
        showsCompass
        onMapReady={fitToAnimals}
      >
        {points.map((point) => (
          <AnimalMarker
            key={point.animal_id}
            point={point}
            onPress={() => handleMarkerPress(point)}
          />
        ))}
      </MapView>

      {/* Header overlay */}
      <View style={[styles.headerOverlay, { paddingTop: insets.top + Spacing.sm }]}>
        <View style={styles.headerCard}>
          <Ionicons name="map" size={16} color={Colors.primary} />
          <Text style={styles.headerText}>
            {points.length} animal{points.length > 1 ? 'x' : ''} localisé{points.length > 1 ? 's' : ''}
          </Text>
          <View style={styles.liveIndicator}>
            <View style={styles.liveDot} />
            <Text style={styles.liveText}>Live</Text>
          </View>
        </View>
      </View>

      {/* Bouton fit bounds */}
      <View style={[styles.fabContainer, { bottom: insets.bottom + (selectedAnimal ? 220 : 80) }]}>
        <TouchableOpacity style={styles.fab} onPress={fitToAnimals}>
          <Ionicons name="locate-outline" size={22} color={Colors.text.primary} />
        </TouchableOpacity>
        <TouchableOpacity style={styles.fab} onPress={() => refetch()}>
          <Ionicons name="refresh-outline" size={22} color={Colors.text.primary} />
        </TouchableOpacity>
      </View>

      {/* Légende comportements */}
      {!selectedAnimal && (
        <View style={[styles.legend, { bottom: insets.bottom + 80 }]}>
          {(['lying', 'standing', 'walking', 'running'] as ActivityState[]).map((s) => (
            <View key={s} style={styles.legendItem}>
              <View style={[styles.legendDot, { backgroundColor: activityStateColor(s) }]} />
              <Text style={styles.legendText}>{activityStateLabel(s)}</Text>
            </View>
          ))}
        </View>
      )}

      {/* Bottom sheet animal sélectionné */}
      {selectedAnimal && (
        <AnimalInfoSheet
          point={selectedAnimal}
          onClose={() => setSelectedAnimal(null)}
          onNavigate={handleNavigateToAnimal}
        />
      )}
    </View>
  );
}

// ─── Styles ──────────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: Colors.bg.primary },

  headerOverlay: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    alignItems: 'center',
    paddingHorizontal: Spacing.base,
  },
  headerCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(13,27,42,0.92)',
    borderRadius: Radius.full,
    paddingHorizontal: Spacing.base,
    paddingVertical: Spacing.sm,
    gap: Spacing.sm,
    borderWidth: 1,
    borderColor: Colors.border.default,
  },
  headerText: { fontSize: Typography.sm, color: Colors.text.primary, fontWeight: '600' },
  liveIndicator: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  liveDot: { width: 7, height: 7, borderRadius: 4, backgroundColor: Colors.primary },
  liveText: { fontSize: Typography.xs, color: Colors.primary, fontWeight: '700' },

  fabContainer: {
    position: 'absolute',
    right: Spacing.base,
    gap: Spacing.sm,
  },
  fab: {
    width: 44,
    height: 44,
    borderRadius: Radius.full,
    backgroundColor: 'rgba(13,27,42,0.92)',
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: Colors.border.default,
  },

  legend: {
    position: 'absolute',
    left: Spacing.base,
    backgroundColor: 'rgba(13,27,42,0.92)',
    borderRadius: Radius.md,
    padding: Spacing.sm,
    gap: 6,
    borderWidth: 1,
    borderColor: Colors.border.default,
  },
  legendItem: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  legendDot: { width: 8, height: 8, borderRadius: 4 },
  legendText: { fontSize: Typography.xs, color: Colors.text.secondary },

  // Marqueur
  markerContainer: { alignItems: 'center' },
  markerOuter: {
    width: 38,
    height: 38,
    borderRadius: 19,
    borderWidth: 2.5,
    backgroundColor: 'rgba(13,27,42,0.85)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  markerInner: {
    width: 28,
    height: 28,
    borderRadius: 14,
    alignItems: 'center',
    justifyContent: 'center',
  },
  markerInitial: { color: '#fff', fontWeight: '700', fontSize: 13 },
  markerTail: { width: 2.5, height: 8, borderRadius: 1 },

  // Info sheet
  infoSheet: {
    position: 'absolute',
    bottom: 0,
    left: 0,
    right: 0,
    backgroundColor: Colors.bg.card,
    borderTopLeftRadius: Radius.xl,
    borderTopRightRadius: Radius.xl,
    padding: Spacing.base,
    paddingBottom: Spacing['2xl'],
    borderTopWidth: 1,
    borderColor: Colors.border.default,
  },
  infoSheetHandle: {
    width: 36,
    height: 4,
    borderRadius: 2,
    backgroundColor: Colors.border.default,
    alignSelf: 'center',
    marginBottom: Spacing.base,
  },
  infoSheetHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.sm,
    marginBottom: Spacing.base,
  },
  infoAnimalAvatar: {
    width: 46,
    height: 46,
    borderRadius: Radius.full,
    alignItems: 'center',
    justifyContent: 'center',
  },
  infoAvatarText: { fontWeight: '700', fontSize: Typography.lg },
  infoSheetTitle: { flex: 1 },
  infoAnimalName: {
    fontSize: Typography.md,
    fontWeight: '700',
    color: Colors.text.primary,
  },
  infoDeviceId: { fontSize: Typography.xs, color: Colors.text.muted, marginTop: 2 },
  infoStats: {
    flexDirection: 'row',
    justifyContent: 'space-around',
    backgroundColor: Colors.bg.elevated,
    borderRadius: Radius.lg,
    padding: Spacing.md,
    marginBottom: Spacing.md,
  },
  infoStat: { alignItems: 'center', gap: 6 },
  infoStatIcon: {
    width: 40,
    height: 40,
    borderRadius: Radius.md,
    alignItems: 'center',
    justifyContent: 'center',
  },
  infoStatLabel: { fontSize: Typography.xs, color: Colors.text.muted },
  infoStatValue: { fontSize: Typography.sm, fontWeight: '700', color: Colors.text.primary },
  infoFooter: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  infoUpdated: { fontSize: Typography.xs, color: Colors.text.muted },
  infoDetailBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  infoDetailBtnText: { color: Colors.primary, fontWeight: '600', fontSize: Typography.sm },
});
