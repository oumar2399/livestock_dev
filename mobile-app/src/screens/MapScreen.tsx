/**
 * MapScreen - Carte temps réel du troupeau
 * - Clustering automatique des marqueurs proches
 * - Détection animal isolé du troupeau
 * - Deux modes : troupeau principal / vue globale
 */
import React, { useRef, useState, useEffect, useCallback, useMemo } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
} from 'react-native';
import MapView, { Marker, PROVIDER_DEFAULT, Circle, Polyline } from 'react-native-maps';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useNavigation, useRoute } from '@react-navigation/native';

import { useTelemetryLatest } from '../hooks/useTelemetry';
import { useLocationHistory } from '../hooks/useLocations';
import { Colors, Radius, Spacing, Typography } from '../constants/config';
import { PositionedTelemetry as TelemetryLatest, ActivityState, LocationHistoryResponse } from '../types';
import { mapAnimals, positionRecency } from '../utils/geofenceMap';
import {
  activityStateColor,
  activityStateLabel,
  timeAgo,
  batteryColor,
  batteryIcon,
  formatBattery,
} from '../utils/helpers';
import { LoadingState, ErrorState } from '../components/ui';

// ─── Helpers ──────────────────────────────────────────────────────────────────

/**
 * Fallback: derive activity state from raw g value.
 * Only used when the backend does not provide activity_state (legacy data).
 * For new data the ML model prediction (Active/Resting) is used directly.
 */
function getActivityStateFallback(activity: number): ActivityState {
  return activity < 0.5 ? 'Resting' : 'Active';
}

/** Resolve the activity state from a TelemetryLatest point.
 *  Prefers the backend ML prediction; falls back to threshold if null. */
function resolveActivityState(point: TelemetryLatest): ActivityState | null {
  if (point.behavior_eligible === false) return null;
  return (point.activity_state as ActivityState) ?? getActivityStateFallback(point.activity);
}

/** Distance en km entre deux points GPS (formule Haversine) */
function distanceKm(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const R = 6371;
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLon = ((lon2 - lon1) * Math.PI) / 180;
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos((lat1 * Math.PI) / 180) *
    Math.cos((lat2 * Math.PI) / 180) *
    Math.sin(dLon / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

/** Centre géographique d'un groupe de points */
function centroid(points: TelemetryLatest[]) {
  const lat = points.reduce((s, p) => s + p.latitude, 0) / points.length;
  const lon = points.reduce((s, p) => s + p.longitude, 0) / points.length;
  return { latitude: lat, longitude: lon };
}

/**
 * Détecte les animaux isolés du troupeau principal.
 * Un animal est "isolé" s'il est à plus de ISOLATION_THRESHOLD_KM
 * du centre du troupeau.
 */
const ISOLATION_THRESHOLD_KM = 0.8; // 2km

function detectIsolatedAnimals(points: TelemetryLatest[]): Set<number> {
  points = points.filter((point) => positionRecency(point.last_update, Date.now()) === 'recent');
  if (points.length <= 2) return new Set();
  const sortedLats = [...points.map(p => p.latitude)].sort((a, b) => a - b);
  const sortedLons = [...points.map(p => p.longitude)].sort((a, b) => a - b);
  const medLat = sortedLats[Math.floor(sortedLats.length / 2)];
  const medLon = sortedLons[Math.floor(sortedLons.length / 2)];
  const isolated = new Set<number>();
  points.forEach(p => {
    const dist = distanceKm(p.latitude, p.longitude, medLat, medLon);
    if (dist > ISOLATION_THRESHOLD_KM) isolated.add(p.animal_id);
  });
  return isolated;
}

/**
 * Groupe les marqueurs trop proches pour éviter superposition.
 * Seuil : animaux à moins de CLUSTER_THRESHOLD_DEG degrés → cluster.
 */
const CLUSTER_THRESHOLD_DEG = 0.0005; // ~50m

interface ClusterOrPoint {
  type: 'single' | 'cluster';
  points: TelemetryLatest[];
  latitude: number;
  longitude: number;
}

function clusterPoints(points: TelemetryLatest[]): ClusterOrPoint[] {
  const visited = new Set<number>();
  const clusters: ClusterOrPoint[] = [];

  points.forEach((p, i) => {
    if (visited.has(i)) return;
    const group = [p];
    visited.add(i);

    points.forEach((q, j) => {
      if (visited.has(j)) return;
      const dLat = Math.abs(p.latitude - q.latitude);
      const dLon = Math.abs(p.longitude - q.longitude);
      if (dLat < CLUSTER_THRESHOLD_DEG && dLon < CLUSTER_THRESHOLD_DEG) {
        group.push(q);
        visited.add(j);
      }
    });

    const c = centroid(group);
    clusters.push({
      type: group.length === 1 ? 'single' : 'cluster',
      points: group,
      latitude: c.latitude,
      longitude: c.longitude,
    });
  });

  return clusters;
}

// ─── Marqueur individuel ──────────────────────────────────────────────────────

function AnimalMarker({
  point,
  isIsolated,
  onPress,
}: {
  point: TelemetryLatest;
  isIsolated: boolean;
  onPress: () => void;
}) {
  const state = resolveActivityState(point);
  const color = isIsolated ? Colors.severity.critical : activityStateColor(state);

  return (
    <Marker
      coordinate={{ latitude: point.latitude, longitude: point.longitude }}
      onPress={onPress}
    >
      <View style={styles.markerContainer}>
        {/* Halo rouge si isolé */}
        {isIsolated && <View style={styles.isolatedHalo} />}
        <View style={[styles.markerOuter, { borderColor: color }]}>
          <View style={[styles.markerInner, { backgroundColor: color }]}>
            <Text style={styles.markerInitial}>
              {point.animal_name[0].toUpperCase()}
            </Text>
          </View>
        </View>
        <View style={[styles.markerTail, { backgroundColor: color }]} />
        {/* Icône alerte si isolé */}
        {isIsolated && (
          <View style={styles.isolatedBadge}>
            <Text style={styles.isolatedBadgeText}>!</Text>
          </View>
        )}
      </View>
    </Marker>
  );
}

// ─── Marqueur cluster ─────────────────────────────────────────────────────────

function ClusterMarker({
  cluster,
  onPress,
}: {
  cluster: ClusterOrPoint;
  onPress: () => void;
}) {
  const count = cluster.points.length;
  // Couleur dominante du cluster (état le plus actif)
  const states = cluster.points.map(resolveActivityState).filter(Boolean);
  const dominantState = states.length ? (states.includes('Active') ? 'Active' : 'Resting') : null;
  const color = activityStateColor(dominantState);

  return (
    <Marker
      coordinate={{ latitude: cluster.latitude, longitude: cluster.longitude }}
      onPress={onPress}
    >
      <View style={styles.clusterContainer}>
        <View style={[styles.clusterOuter, { borderColor: color }]}>
          <View style={[styles.clusterInner, { backgroundColor: color }]}>
            <Text style={styles.clusterCount}>{count}</Text>
            <Text style={styles.clusterLabel}>🐄</Text>
          </View>
        </View>
      </View>
    </Marker>
  );
}

// ─── Bottom sheet animal ──────────────────────────────────────────────────────

function AnimalInfoSheet({
  point,
  isIsolated,
  onClose,
  onNavigate,
  showTrack,
  onToggleTrack,
  trackHours,
  onSelectHours,
  historyData,
  isHistoryLoading,
  onFitTrack,
}: {
  point: TelemetryLatest | null;
  isIsolated: boolean;
  onClose: () => void;
  onNavigate: (id: number) => void;
  showTrack: boolean;
  onToggleTrack: () => void;
  trackHours: number;
  onSelectHours: (hours: number) => void;
  historyData?: LocationHistoryResponse;
  isHistoryLoading: boolean;
  onFitTrack: () => void;
}) {
  if (!point) return null;
  const state      = resolveActivityState(point);
  const stateColor = activityStateColor(state);
  const batColor   = batteryColor(point.battery);

  const isLostOrEquipmentOnly = point.position_is_animal === false || point.device_status === 'lost';

  return (
    <View style={styles.infoSheet}>
      <View style={styles.infoSheetHandle} />

      {/* Bannière alerte isolement */}
      {isIsolated && (
        <View style={styles.isolationBanner}>
          <Ionicons name="warning-outline" size={16} color={Colors.severity.critical} />
          <Text style={styles.isolationText}>
            Animal away from the herd (&gt; {ISOLATION_THRESHOLD_KM * 1000}m)
          </Text>
        </View>
      )}

      {/* Bannière collier perdu / matériel seul (Lot B) */}
      {isLostOrEquipmentOnly && (
        <View style={styles.lostCollarMapBanner}>
          <Ionicons name="alert-circle-outline" size={16} color="#E67E22" />
          <Text style={styles.lostCollarMapText}>
            {point.device_status === 'lost'
              ? 'Collier égaré — position du matériel seul, pas de l’animal.'
              : 'Matériel seul — position non garantie de l’animal.'}
          </Text>
        </View>
      )}

      <View style={styles.infoSheetHeader}>
        <View style={[styles.infoAnimalAvatar, { backgroundColor: stateColor + '20' }]}>
          <Text style={[styles.infoAvatarText, { color: stateColor }]}>
            {point.animal_name[0].toUpperCase()}
          </Text>
        </View>
        <View style={styles.infoSheetTitle}>
          <Text style={styles.infoAnimalName}>{point.animal_name}</Text>
          <Text style={styles.infoDeviceId}>Device: {point.device_id}</Text>
        </View>
        <TouchableOpacity onPress={onClose} hitSlop={12}>
          <Ionicons name="close" size={22} color={Colors.text.secondary} />
        </TouchableOpacity>
      </View>

      <View style={styles.infoStats}>
        <View style={styles.infoStat}>
          <View style={[styles.infoStatIcon, { backgroundColor: stateColor + '20' }]}>
            <Ionicons name="walk-outline" size={18} color={stateColor} />
          </View>
          <Text style={styles.infoStatLabel}>Behavior</Text>
          <Text style={[styles.infoStatValue, { color: stateColor }]}>
            {activityStateLabel(state)}
          </Text>
        </View>
        <View style={styles.infoStat}>
          <View style={[styles.infoStatIcon, { backgroundColor: Colors.primary + '20' }]}>
            <Ionicons name="pulse-outline" size={18} color={Colors.primary} />
          </View>
          <Text style={styles.infoStatLabel}>Activity</Text>
          <Text style={styles.infoStatValue}>{point.behavior_eligible === false ? 'Unavailable' : point.activity.toFixed(2) + ' g'}</Text>
        </View>
        <View style={styles.infoStat}>
          <View style={[styles.infoStatIcon, { backgroundColor: batColor + '20' }]}>
            <Ionicons name={batteryIcon(point.battery) as any} size={18} color={batColor} />
          </View>
          <Text style={styles.infoStatLabel}>Battery</Text>
          <Text style={[styles.infoStatValue, { color: batColor }]}>{formatBattery(point.battery)}</Text>
        </View>
      </View>

      {/* Trajet GPS controls (Lot B) */}
      <View style={styles.trackActionSection}>
        <View style={styles.trackActionHeader}>
          <TouchableOpacity
            style={[styles.trackToggleBtn, showTrack && styles.trackToggleBtnActive]}
            onPress={onToggleTrack}
            activeOpacity={0.7}
          >
            <Ionicons
              name={showTrack ? 'trail-sign' : 'trail-sign-outline'}
              size={16}
              color={showTrack ? '#fff' : Colors.primary}
            />
            <Text style={[styles.trackToggleBtnText, showTrack && styles.trackToggleBtnTextActive]}>
              {showTrack ? 'Masquer trajet' : 'Voir trajet GPS'}
            </Text>
          </TouchableOpacity>

          {showTrack && (
            <TouchableOpacity style={styles.fitTrackBtn} onPress={onFitTrack} activeOpacity={0.7}>
              <Ionicons name="scan-outline" size={16} color={Colors.primary} />
              <Text style={styles.fitTrackBtnText}>Centrer trajet</Text>
            </TouchableOpacity>
          )}
        </View>

        {showTrack && (
          <View style={styles.trackPeriodRow}>
            {[1, 6, 24].map((h) => (
              <TouchableOpacity
                key={h}
                style={[styles.periodChip, trackHours === h && styles.periodChipActive]}
                onPress={() => onSelectHours(h)}
              >
                <Text style={[styles.periodChipText, trackHours === h && styles.periodChipTextActive]}>
                  {h} h
                </Text>
              </TouchableOpacity>
            ))}

            <View style={styles.trackSummaryMeta}>
              {isHistoryLoading ? (
                <Text style={styles.trackSummaryText}>Chargement...</Text>
              ) : historyData ? (
                <Text style={styles.trackSummaryText}>
                  {historyData.total_points} pts
                  {historyData.proven_coverage_ratio != null ? ` · ${Math.round(historyData.proven_coverage_ratio * 100)}% couv.` : ''}
                  {historyData.gaps.length > 0 ? ` · ${historyData.gaps.length} coupure(s)` : ''}
                </Text>
              ) : null}
            </View>
          </View>
        )}
      </View>

      {/* Timestamps distincts : Position vs Télémétrie (Lot B) */}
      <View style={styles.timestampContainer}>
        <View style={styles.timestampRow}>
          <Text style={styles.timestampLabel}>Position fixée :</Text>
          <Text style={styles.timestampValue}>
            {point.position_time ? timeAgo(point.position_time) : 'Inconnue'}
          </Text>
        </View>
        <View style={styles.timestampRow}>
          <Text style={styles.timestampLabel}>Dernière télémétrie :</Text>
          <Text style={styles.timestampValue}>
            {point.last_update ? timeAgo(point.last_update) : 'Inconnue'}
          </Text>
        </View>
      </View>

      <View style={styles.infoFooter}>
        <TouchableOpacity style={styles.infoDetailBtn} onPress={() => onNavigate(point.animal_id)}>
          <Text style={styles.infoDetailBtnText}>View full profile</Text>
          <Ionicons name="arrow-forward" size={16} color={Colors.primary} />
        </TouchableOpacity>
      </View>
    </View>
  );
}

// ─── Bottom sheet cluster ─────────────────────────────────────────────────────

function ClusterSheet({
  cluster,
  isolatedIds,
  onClose,
  onSelectAnimal,
}: {
  cluster: ClusterOrPoint | null;
  isolatedIds: Set<number>;
  onClose: () => void;
  onSelectAnimal: (point: TelemetryLatest) => void;
}) {
  if (!cluster) return null;

  return (
    <View style={styles.infoSheet}>
      <View style={styles.infoSheetHandle} />
      <View style={styles.clusterSheetHeader}>
        <Text style={styles.clusterSheetTitle}>
          {cluster.points.length} animals at same location
        </Text>
        <TouchableOpacity onPress={onClose} hitSlop={12}>
          <Ionicons name="close" size={22} color={Colors.text.secondary} />
        </TouchableOpacity>
      </View>

      {cluster.points.map((point) => {
        const state = resolveActivityState(point);
        const color = activityStateColor(state);
        const isIsolated = isolatedIds.has(point.animal_id);
        return (
          <TouchableOpacity
            key={point.animal_id}
            style={styles.clusterItem}
            onPress={() => onSelectAnimal(point)}
          >
            <View style={[styles.clusterItemAvatar, { backgroundColor: color + '20' }]}>
              <Text style={[styles.clusterItemInitial, { color }]}>
                {point.animal_name[0].toUpperCase()}
              </Text>
            </View>
            <View style={styles.clusterItemInfo}>
              <Text style={styles.clusterItemName}>{point.animal_name}</Text>
              <Text style={[styles.clusterItemState, { color }]}>
                {activityStateLabel(state)}
              </Text>
            </View>
            {isIsolated && (
              <Ionicons name="warning" size={16} color={Colors.severity.critical} />
            )}
            <Text style={styles.clusterItemBattery}>{point.battery}%</Text>
            <Ionicons name="chevron-forward" size={16} color={Colors.text.muted} />
          </TouchableOpacity>
        );
      })}
    </View>
  );
}

// ─── Screen principal ─────────────────────────────────────────────────────────

type ViewMode = 'herd' | 'global';

export default function MapScreen() {
  const insets     = useSafeAreaInsets();
  const navigation = useNavigation<any>();
  const mapRef     = useRef<MapView>(null);
  const [mapReady, setMapReady]           = useState(false);
  const [viewMode, setViewMode]           = useState<ViewMode>('herd');
  const [selectedAnimal, setSelectedAnimal] = useState<TelemetryLatest | null>(null);
  const [selectedCluster, setSelectedCluster] = useState<ClusterOrPoint | null>(null);

  const { data, isLoading, isError, refetch } = useTelemetryLatest({ limit: 100 });
  const [showDistantSheet, setShowDistantSheet] = useState(false);

  const mostRecentTimestamp = useMemo(() => {
    if (!data || data.length === 0) return null;
    let newest = 0;
    for (const p of data) {
      const ts = p.position_time ?? p.last_update;
      if (ts) {
        const t = new Date(ts).getTime();
        if (t > newest) newest = t;
      }
    }
    return newest > 0 ? newest : null;
  }, [data]);

  const mapFreshness = useMemo(() => {
    if (!mostRecentTimestamp) return { label: 'No fix', color: '#95A5A6', isRecent: false };
    const diffMin = Math.floor((Date.now() - mostRecentTimestamp) / 60000);
    if (diffMin < 5) return { label: diffMin === 0 ? 'Recent (< 1m)' : `Recent (${diffMin}m)`, color: '#27AE60', isRecent: true };
    if (diffMin < 30) return { label: `Stale (${diffMin}m)`, color: '#F39C12', isRecent: false };
    const hours = Math.floor(diffMin / 60);
    return { label: hours > 0 ? `Last fix ${hours}h ago` : `Last fix ${diffMin}m ago`, color: '#95A5A6', isRecent: false };
  }, [mostRecentTimestamp]);

  const allPoints = useMemo(() => {
  return mapAnimals(data ?? []).filter(p => p.position_is_animal !== false).map(p => ({
    ...p,
    latitude:  parseFloat(String(p.latitude)),
    longitude: parseFloat(String(p.longitude)),
    activity:  parseFloat(String(p.activity)),
    battery:   parseInt(String(p.battery), 10),
    })).filter(p => !isNaN(p.latitude) && !isNaN(p.longitude));
  }, [data]);

  useEffect(() => {
    setSelectedAnimal((current) => current ? allPoints.find((point) => point.animal_id === current.animal_id) ?? null : null);
    setSelectedCluster((current) => {
      if (!current) return null;
      const ids = new Set(current.points.map((point) => point.animal_id));
      const members = allPoints.filter((point) => ids.has(point.animal_id));
      return members.length ? { ...current, points: members, ...centroid(members) } : null;
    });
  }, [allPoints]);

  const [showTrack, setShowTrack] = useState(false);
  const [trackHours, setTrackHours] = useState(24);

  const historyQuery = useLocationHistory(
    showTrack && selectedAnimal ? selectedAnimal.animal_id : null,
    { hours: trackHours },
  );
  const historyData = historyQuery.data;

  const allTrackCoords = useMemo(() => {
    if (!historyData) return [];
    return historyData.segments.flatMap((s) =>
      s.points.map((p) => ({ latitude: p.latitude, longitude: p.longitude }))
    );
  }, [historyData]);

  const firstTrackPoint = useMemo(() => {
    if (!historyData || historyData.segments.length === 0) return null;
    const firstSeg = historyData.segments[0];
    return firstSeg.points.length > 0 ? firstSeg.points[0] : null;
  }, [historyData]);

  const fitToTrack = useCallback(() => {
    if (allTrackCoords.length === 0 || !mapRef.current) return;
    if (allTrackCoords.length === 1) {
      mapRef.current.animateToRegion({
        latitude: allTrackCoords[0].latitude,
        longitude: allTrackCoords[0].longitude,
        latitudeDelta: 0.005,
        longitudeDelta: 0.005,
      }, 600);
      return;
    }
    mapRef.current.fitToCoordinates(allTrackCoords, {
      edgePadding: { top: 120, right: 60, bottom: 280, left: 60 },
      animated: true,
    });
  }, [allTrackCoords]);

  // Center on track once loaded
  useEffect(() => {
    if (showTrack && allTrackCoords.length > 0) {
      fitToTrack();
    }
  }, [showTrack, historyData?.period_start]);

  const route = useRoute<any>();
  const focusAnimalId = route.params?.focusAnimalId;
  const initialShowTrack = route.params?.showTrack;

  useEffect(() => {
    if (focusAnimalId && allPoints.length > 0) {
      const target = allPoints.find((point) => point.animal_id === focusAnimalId);
      if (target) {
        setSelectedAnimal(target);
        if (initialShowTrack) {
          setShowTrack(true);
        }
        if (mapRef.current && !initialShowTrack) {
          mapRef.current.animateToRegion({
            latitude: target.latitude,
            longitude: target.longitude,
            latitudeDelta: 0.005,
            longitudeDelta: 0.005,
          }, 600);
        }
      }
    }
  }, [focusAnimalId, initialShowTrack, allPoints]);

  const { localPoints, distantAnimals } = useMemo(() => {
    if (allPoints.length === 0) return { localPoints: [], distantAnimals: [] as any[] };
    const sortedLats = [...allPoints.map(p => p.latitude)].sort((a, b) => a - b);
    const sortedLons = [...allPoints.map(p => p.longitude)].sort((a, b) => a - b);
    const medLat = sortedLats[Math.floor(sortedLats.length / 2)];
    const medLon = sortedLons[Math.floor(sortedLons.length / 2)];
    const local: TelemetryLatest[] = [];
    const distant: any[] = [];
    allPoints.forEach(p => {
      const dist = distanceKm(p.latitude, p.longitude, medLat, medLon);
      if (dist < 100) local.push(p);
      else distant.push({ ...p, _distanceKm: Math.round(dist) });
    });
    return { localPoints: local, distantAnimals: distant };
  }, [allPoints]);

  const points = useMemo(() => {
    return viewMode === 'global' ? allPoints : localPoints;
  }, [viewMode, allPoints, localPoints]);

  // Calculs dérivés
  const isolatedIds = useMemo(() => detectIsolatedAnimals(points), [points]);
  const clusters    = useMemo(() => clusterPoints(points), [points]);
  
  const herdCenter = useMemo(() => {
    if (!points.length) return null;
    const sortedLats = [...points.map(p => p.latitude)].sort((a, b) => a - b);
    const sortedLons = [...points.map(p => p.longitude)].sort((a, b) => a - b);
    return {
      latitude:  sortedLats[Math.floor(sortedLats.length / 2)],
      longitude: sortedLons[Math.floor(sortedLons.length / 2)],
    };
  }, [points]);

  const mainHerd    = useMemo(
    () => points.filter((p) => !isolatedIds.has(p.animal_id)),
    [points, isolatedIds],
  );

  // ── Zoom troupeau principal ────────────────────────────────────────────────
  const fitToHerd = useCallback(() => {
    if (!mapRef.current) return;
    const target = points;
    if (!target.length) return;

    if (target.length === 1) {
      mapRef.current.animateToRegion({
        latitude: target[0].latitude,
        longitude: target[0].longitude,
        latitudeDelta: 0.005,
        longitudeDelta: 0.005,
      }, 600);
      return;
    }

    const lats = target.map((p) => p.latitude);
    const lons = target.map((p) => p.longitude);
    const dLat = Math.max(...lats) - Math.min(...lats);
    const dLon = Math.max(...lons) - Math.min(...lons);

    if (dLat < 0.005 && dLon < 0.005) {
      // Animaux très proches → zoom fixe
      mapRef.current.animateToRegion({
        latitude: lats.reduce((a, b) => a + b, 0) / lats.length,
        longitude: lons.reduce((a, b) => a + b, 0) / lons.length,
        latitudeDelta: 0.008,
        longitudeDelta: 0.008,
      }, 600);
    } else {
      mapRef.current.fitToCoordinates(
        target.map((p) => ({ latitude: p.latitude, longitude: p.longitude })),
        { edgePadding: { top: 80, right: 40, bottom: 160, left: 40 }, animated: true },
      );
    }
  }, [points, mainHerd, viewMode]);

  // Auto-zoom au chargement
  useEffect(() => {
    if (mapReady && points.length > 0) {
      const t = setTimeout(fitToHerd, 400);
      return () => clearTimeout(t);
    }
  }, [mapReady, points.length]);

  // Zoom sur animal isolé
  const zoomToIsolated = useCallback(() => {
    const isolated = points.filter((p) => isolatedIds.has(p.animal_id));
    if (!isolated.length || !mapRef.current) return;
    mapRef.current.animateToRegion({
      latitude: isolated[0].latitude,
      longitude: isolated[0].longitude,
      latitudeDelta: 0.005,
      longitudeDelta: 0.005,
    }, 600);
  }, [points, isolatedIds]);

  const handleClusterPress = (cluster: ClusterOrPoint) => {
    if (cluster.type === 'single') {
      setSelectedAnimal(cluster.points[0]);
    } else {
      setSelectedCluster(cluster);
    }
  };

  const initialRegion = points.length > 0
    ? { latitude: points[0].latitude, longitude: points[0].longitude, latitudeDelta: 0.02, longitudeDelta: 0.02 }
    : { latitude: 36.2048, longitude: 138.2529, latitudeDelta: 8, longitudeDelta: 8 };

  if (isLoading && !data) return <LoadingState message="Loading positions..." />;
  if (isError && !data)   return <ErrorState message="Failed to load positions" onRetry={refetch} />;

  const sheetOpen = !!selectedAnimal || !!selectedCluster || showDistantSheet;

  return (
    <View style={styles.screen}>
      {/* ── Carte ────────────────────────────────────────────────────── */}
      <MapView
        ref={mapRef}
        style={StyleSheet.absoluteFillObject}
        provider={PROVIDER_DEFAULT}
        initialRegion={initialRegion}
        mapType="satellite"
        showsUserLocation
        showsCompass
        onMapReady={() => setMapReady(true)}
        onPress={() => { setSelectedAnimal(null); setSelectedCluster(null); }}
      >
        {/* Cercle zone troupeau */}
        {herdCenter && mainHerd.length > 1 && (
          <Circle
            center={herdCenter}
            radius={ISOLATION_THRESHOLD_KM * 1000}
            strokeColor={Colors.primary + '60'}
            fillColor={Colors.primary + '10'}
            strokeWidth={1.5}
          />
        )}

        {/* Marqueurs (clusters ou individuels) */}
        {clusters.map((cluster, idx) =>
          cluster.type === 'cluster' ? (
            <ClusterMarker
              key={`cluster-${idx}`}
              cluster={cluster}
              onPress={() => handleClusterPress(cluster)}
            />
          ) : (
            <AnimalMarker
              key={`animal-${cluster.points[0].animal_id}`}
              point={cluster.points[0]}
              isIsolated={isolatedIds.has(cluster.points[0].animal_id)}
              onPress={() => setSelectedAnimal(cluster.points[0])}
            />
          ),
        )}

        {/* Marqueurs animaux distants (violet) */}
        {distantAnimals.map((p: any) => (
          <Marker
            key={`distant-${p.animal_id}`}
            coordinate={{ latitude: p.latitude, longitude: p.longitude }}
            onPress={() => setSelectedAnimal(p)}
          >
            <View style={styles.markerContainer}>
              <View style={[styles.markerOuter, { borderColor: '#9B59B6' }]}>
                <View style={[styles.markerInner, { backgroundColor: '#9B59B6' }]}>
                  <Text style={styles.markerInitial}>
                    {p.animal_name[0].toUpperCase()}
                  </Text>
                </View>
              </View>
              <View style={[styles.markerTail, { backgroundColor: '#9B59B6' }]} />
            </View>
          </Marker>
        ))}

        {/* ── Trajectoire historique GPS (Lot B) ── */}
        {showTrack && historyData && historyData.segments.map((segment, sIdx) => {
          const coords = segment.points.map(pt => ({
            latitude: pt.latitude,
            longitude: pt.longitude,
          }));
          const strokeColor =
            segment.quality === 'reliable'
              ? '#2E86DE'
              : segment.quality === 'degraded'
              ? '#E67E22'
              : '#7F8C8D';

          return (
            <Polyline
              key={`segment-${sIdx}`}
              coordinates={coords}
              strokeColor={strokeColor}
              strokeWidth={segment.quality === 'uncertain' ? 2 : 3.5}
              lineDashPattern={segment.quality === 'uncertain' ? [6, 4] : undefined}
            />
          );
        })}

        {/* Lignes en pointillés pour matérialiser les trous entre segments (Lot B) */}
        {showTrack && historyData && historyData.segments.length > 1 &&
          historyData.segments.slice(0, -1).map((seg, idx) => {
            const nextSeg = historyData.segments[idx + 1];
            const p1 = seg.points[seg.points.length - 1];
            const p2 = nextSeg.points[0];
            if (!p1 || !p2) return null;
            return (
              <Polyline
                key={`gap-link-${idx}`}
                coordinates={[
                  { latitude: p1.latitude, longitude: p1.longitude },
                  { latitude: p2.latitude, longitude: p2.longitude },
                ]}
                strokeColor="#BDC3C7"
                strokeWidth={1.5}
                lineDashPattern={[4, 4]}
              />
            );
          })
        }

        {/* Marqueur de début de parcours (Lot B) */}
        {showTrack && firstTrackPoint && (
          <Marker
            coordinate={{ latitude: firstTrackPoint.latitude, longitude: firstTrackPoint.longitude }}
            anchor={{ x: 0.5, y: 0.5 }}
          >
            <View style={styles.trackStartMarker}>
              <Ionicons name="flag" size={14} color="#27AE60" />
            </View>
          </Marker>
        )}
      </MapView>

      {/* ── Header ───────────────────────────────────────────────────── */}
      <View style={[styles.headerOverlay, { paddingTop: insets.top + Spacing.sm }]}>
        <View style={styles.headerCard}>
          <Ionicons name="map" size={16} color={Colors.primary} />
          <Text style={styles.headerText}>
            {allPoints.length} Animal{allPoints.length > 1 ? 's' : ''}
          </Text>
          {isolatedIds.size > 0 && (
            <TouchableOpacity style={styles.isolatedBtn} onPress={zoomToIsolated}>
              <Ionicons name="warning" size={12} color={Colors.severity.critical} />
              <Text style={styles.isolatedBtnText}>
                {isolatedIds.size} Isolated{isolatedIds.size > 1 ? 's' : ''}
              </Text>
            </TouchableOpacity>
          )}
          {distantAnimals.length > 0 && (
            <TouchableOpacity
              style={styles.distantBtn}
              onPress={() => { setShowDistantSheet(true); setSelectedAnimal(null); setSelectedCluster(null); }}
            >
              <Ionicons name="navigate-outline" size={12} color="#9B59B6" />
              <Text style={styles.distantBtnText}>
                {distantAnimals.length} Away
              </Text>
            </TouchableOpacity>
          )}
          <View style={[styles.liveIndicator, { borderColor: mapFreshness.color + '40', backgroundColor: Colors.bg.card }]}>
            <View style={[styles.liveDot, { backgroundColor: mapFreshness.color }]} />
            <Text style={[styles.liveText, { color: mapFreshness.color }]}>{mapFreshness.label}</Text>
          </View>
        </View>
      </View>

      {/* ── Toggle mode vue ──────────────────────────────────────────── */}
      <View style={[styles.modeToggle, { top: insets.top + 56 }]}>
        <TouchableOpacity
          style={[styles.modeBtn, viewMode === 'herd' && styles.modeBtnActive]}
          onPress={() => { setViewMode('herd'); fitToHerd(); }}
        >
          <Ionicons name="people-outline" size={14} color={viewMode === 'herd' ? Colors.primary : Colors.text.muted} />
          <Text style={[styles.modeBtnText, viewMode === 'herd' && { color: Colors.primary }]}>
            Herd
          </Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.modeBtn, viewMode === 'global' && styles.modeBtnActive]}
          onPress={() => { setViewMode('global'); fitToHerd(); }}
        >
          <Ionicons name="globe-outline" size={14} color={viewMode === 'global' ? Colors.primary : Colors.text.muted} />
          <Text style={[styles.modeBtnText, viewMode === 'global' && { color: Colors.primary }]}>
            All
          </Text>
        </TouchableOpacity>
      </View>

      {/* ── FAB ──────────────────────────────────────────────────────── */}
      <View style={[styles.fabContainer, { bottom: insets.bottom + (sheetOpen ? 230 : 90) }]}>
        <TouchableOpacity style={styles.fab} onPress={() => refetch()}>
          <Ionicons name="refresh-outline" size={22} color={Colors.text.primary} />
        </TouchableOpacity>
        <TouchableOpacity style={styles.fab} onPress={fitToHerd}>
          <Ionicons name="locate-outline" size={22} color={Colors.text.primary} />
        </TouchableOpacity>
      </View>

      {/* ── Légende ──────────────────────────────────────────────────── */}
      {!sheetOpen && (
        <View style={[styles.legend, { bottom: insets.bottom + 90 }]}>
          {(['Active', 'Resting'] as ActivityState[]).map((s) => (
            <View key={s} style={styles.legendItem}>
              <View style={[styles.legendDot, { backgroundColor: activityStateColor(s) }]} />
              <Text style={styles.legendText}>{activityStateLabel(s)}</Text>
            </View>
          ))}
          {isolatedIds.size > 0 && (
            <View style={styles.legendItem}>
              <View style={[styles.legendDot, { backgroundColor: Colors.severity.critical }]} />
              <Text style={styles.legendText}>Isolated</Text>
            </View>
          )}
        </View>
      )}

      {/* ── Sheets ───────────────────────────────────────────────────── */}
      {selectedAnimal && (
        <AnimalInfoSheet
          point={selectedAnimal}
          isIsolated={isolatedIds.has(selectedAnimal.animal_id)}
          onClose={() => {
            setSelectedAnimal(null);
            setShowTrack(false);
          }}
          onNavigate={(id) => {
            setSelectedAnimal(null);
            setShowTrack(false);
            navigation.navigate('Animals', { screen: 'AnimalDetail', params: { animalId: id } });
          }}
          showTrack={showTrack}
          onToggleTrack={() => setShowTrack((prev) => !prev)}
          trackHours={trackHours}
          onSelectHours={setTrackHours}
          historyData={historyData}
          isHistoryLoading={historyQuery.isLoading}
          onFitTrack={fitToTrack}
        />
      )}
      {selectedCluster && !selectedAnimal && (
        <ClusterSheet
          cluster={selectedCluster}
          isolatedIds={isolatedIds}
          onClose={() => setSelectedCluster(null)}
          onSelectAnimal={(p) => { setSelectedCluster(null); setSelectedAnimal(p); }}
        />
      )}
      
      {/* Sheet animaux distants */}
      {showDistantSheet && (
        <View style={styles.infoSheet}>
          <View style={styles.infoSheetHandle} />
          <View style={styles.clusterSheetHeader}>
            <Text style={styles.clusterSheetTitle}>
              Out of zone ({distantAnimals.length})
            </Text>
            <TouchableOpacity onPress={() => setShowDistantSheet(false)} hitSlop={12}>
              <Ionicons name="close" size={22} color={Colors.text.secondary} />
            </TouchableOpacity>
          </View>
          {distantAnimals.map((p: any) => (
            <TouchableOpacity
              key={p.animal_id}
              style={styles.clusterItem}
              onPress={() => {
                setShowDistantSheet(false);
                setSelectedAnimal(p);
                mapRef.current?.animateToRegion({
                  latitude: p.latitude,
                  longitude: p.longitude,
                  latitudeDelta: 0.01,
                  longitudeDelta: 0.01,
                }, 600);
              }}
            >
              <View style={[styles.clusterItemAvatar, { backgroundColor: '#9B59B620' }]}>
                <Text style={[styles.clusterItemInitial, { color: '#9B59B6' }]}>
                  {p.animal_name[0].toUpperCase()}
                </Text>
              </View>
              <View style={styles.clusterItemInfo}>
                <Text style={styles.clusterItemName}>{p.animal_name}</Text>
                <Text style={{ fontSize: Typography.xs, color: '#9B59B6' }}>
                  {p._distanceKm} km from herd
                </Text>
              </View>
              <Text style={styles.clusterItemBattery}>{p.battery}%</Text>
              <Ionicons name="chevron-forward" size={16} color={Colors.text.muted} />
            </TouchableOpacity>
          ))}
        </View>
      )}
    </View>
  );
}

// ─── Styles ──────────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: Colors.bg.primary },

  headerOverlay: { position: 'absolute', top: 0, left: 0, right: 0, alignItems: 'center', paddingHorizontal: Spacing.base },
  headerCard: {
    flexDirection: 'row', alignItems: 'center',
    backgroundColor: 'rgba(13,27,42,0.92)', borderRadius: Radius.full,
    paddingHorizontal: Spacing.base, paddingVertical: Spacing.sm,
    gap: Spacing.sm, borderWidth: 1, borderColor: Colors.border.default,
  },
  headerText: { fontSize: Typography.sm, color: Colors.text.primary, fontWeight: '600' },
  liveIndicator: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  liveDot: { width: 7, height: 7, borderRadius: 4, backgroundColor: Colors.primary },
  liveText: { fontSize: Typography.xs, color: Colors.primary, fontWeight: '700' },
  isolatedBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 3,
    backgroundColor: Colors.severity.critical + '20',
    paddingHorizontal: 6, paddingVertical: 2, borderRadius: Radius.full,
    borderWidth: 1, borderColor: Colors.severity.critical + '50',
  },
  isolatedBtnText: { fontSize: Typography.xs, color: Colors.severity.critical, fontWeight: '700' },

  modeToggle: {
    position: 'absolute', alignSelf: 'center', left: '50%',
    transform: [{ translateX: -60 }],
    flexDirection: 'row',
    backgroundColor: 'rgba(13,27,42,0.92)', borderRadius: Radius.full,
    borderWidth: 1, borderColor: Colors.border.default, padding: 3,
  },
  modeBtn: { flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 10, paddingVertical: 5, borderRadius: Radius.full },
  modeBtnActive: { backgroundColor: Colors.primary + '20' },
  modeBtnText: { fontSize: Typography.xs, color: Colors.text.muted, fontWeight: '600' },

  fabContainer: { position: 'absolute', right: Spacing.base, gap: Spacing.sm },
  fab: {
    width: 44, height: 44, borderRadius: Radius.full,
    backgroundColor: 'rgba(13,27,42,0.92)', alignItems: 'center', justifyContent: 'center',
    borderWidth: 1, borderColor: Colors.border.default,
  },

  legend: {
    position: 'absolute', left: Spacing.base,
    backgroundColor: 'rgba(13,27,42,0.92)', borderRadius: Radius.md,
    padding: Spacing.sm, gap: 6, borderWidth: 1, borderColor: Colors.border.default,
  },
  legendItem: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  legendDot: { width: 8, height: 8, borderRadius: 4 },
  legendText: { fontSize: Typography.xs, color: Colors.text.secondary },

  // Marqueur individuel
  markerContainer: { alignItems: 'center' },
  markerOuter: { width: 38, height: 38, borderRadius: 19, borderWidth: 2.5, backgroundColor: 'rgba(13,27,42,0.85)', alignItems: 'center', justifyContent: 'center' },
  markerInner: { width: 28, height: 28, borderRadius: 14, alignItems: 'center', justifyContent: 'center' },
  markerInitial: { color: '#fff', fontWeight: '700', fontSize: 13 },
  markerTail: { width: 2.5, height: 8, borderRadius: 1 },
  isolatedHalo: { position: 'absolute', width: 50, height: 50, borderRadius: 25, backgroundColor: Colors.severity.critical + '25', top: -6, left: -6 },
  isolatedBadge: { position: 'absolute', top: -4, right: -4, width: 16, height: 16, borderRadius: 8, backgroundColor: Colors.severity.critical, alignItems: 'center', justifyContent: 'center' },
  isolatedBadgeText: { color: '#fff', fontSize: 10, fontWeight: '900' },

  // Cluster
  clusterContainer: { alignItems: 'center' },
  clusterOuter: { width: 50, height: 50, borderRadius: 25, borderWidth: 2.5, backgroundColor: 'rgba(13,27,42,0.9)', alignItems: 'center', justifyContent: 'center' },
  clusterInner: { width: 40, height: 40, borderRadius: 20, alignItems: 'center', justifyContent: 'center' },
  clusterCount: { color: '#fff', fontWeight: '800', fontSize: 14, lineHeight: 16 },
  clusterLabel: { fontSize: 8 },

  // Info sheet
  infoSheet: {
    position: 'absolute', bottom: 0, left: 0, right: 0,
    backgroundColor: Colors.bg.card, borderTopLeftRadius: Radius.xl, borderTopRightRadius: Radius.xl,
    padding: Spacing.base, paddingBottom: Spacing['2xl'],
    borderTopWidth: 1, borderColor: Colors.border.default,
  },
  infoSheetHandle: { width: 36, height: 4, borderRadius: 2, backgroundColor: Colors.border.default, alignSelf: 'center', marginBottom: Spacing.base },
  isolationBanner: {
    flexDirection: 'row', alignItems: 'center', gap: Spacing.sm,
    backgroundColor: Colors.severity.critical + '15', borderRadius: Radius.md,
    padding: Spacing.sm, marginBottom: Spacing.sm,
    borderWidth: 1, borderColor: Colors.severity.critical + '30',
  },
  isolationText: { fontSize: Typography.xs, color: Colors.severity.critical, fontWeight: '600' },
  infoSheetHeader: { flexDirection: 'row', alignItems: 'center', gap: Spacing.sm, marginBottom: Spacing.base },
  infoAnimalAvatar: { width: 46, height: 46, borderRadius: Radius.full, alignItems: 'center', justifyContent: 'center' },
  infoAvatarText: { fontWeight: '700', fontSize: Typography.lg },
  infoSheetTitle: { flex: 1 },
  infoAnimalName: { fontSize: Typography.md, fontWeight: '700', color: Colors.text.primary },
  infoDeviceId: { fontSize: Typography.xs, color: Colors.text.muted, marginTop: 2 },
  infoStats: { flexDirection: 'row', justifyContent: 'space-around', backgroundColor: Colors.bg.elevated, borderRadius: Radius.lg, padding: Spacing.md, marginBottom: Spacing.md },
  infoStat: { alignItems: 'center', gap: 6 },
  infoStatIcon: { width: 40, height: 40, borderRadius: Radius.md, alignItems: 'center', justifyContent: 'center' },
  infoStatLabel: { fontSize: Typography.xs, color: Colors.text.muted },
  infoStatValue: { fontSize: Typography.sm, fontWeight: '700', color: Colors.text.primary },
  infoFooter: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  infoUpdated: { fontSize: Typography.xs, color: Colors.text.muted },
  infoDetailBtn: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  infoDetailBtnText: { color: Colors.primary, fontWeight: '600', fontSize: Typography.sm },

  // Cluster sheet
  clusterSheetHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: Spacing.md },
  clusterSheetTitle: { fontSize: Typography.md, fontWeight: '700', color: Colors.text.primary },
  clusterItem: { flexDirection: 'row', alignItems: 'center', paddingVertical: Spacing.sm, borderBottomWidth: 1, borderBottomColor: Colors.border.default, gap: Spacing.sm },
  clusterItemAvatar: { width: 36, height: 36, borderRadius: Radius.full, alignItems: 'center', justifyContent: 'center' },
  clusterItemInitial: { fontWeight: '700', fontSize: Typography.base },
  clusterItemInfo: { flex: 1 },
  clusterItemName: { fontSize: Typography.sm, fontWeight: '600', color: Colors.text.primary },
  clusterItemState: { fontSize: Typography.xs, marginTop: 1 },
  clusterItemBattery: { fontSize: Typography.xs, color: Colors.text.muted },

  distantBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 3,
    backgroundColor: '#9B59B620',
    paddingHorizontal: 6, paddingVertical: 2, borderRadius: Radius.full,
    borderWidth: 1, borderColor: '#9B59B650',
  },
  distantBtnText: { fontSize: Typography.xs, color: '#9B59B6', fontWeight: '700' },

  // ── Trajectoire & Localisation (Lot B) ──
  trackStartMarker: {
    width: 28, height: 28, borderRadius: 14,
    backgroundColor: '#fff', alignItems: 'center', justifyContent: 'center',
    borderWidth: 2, borderColor: '#27AE60',
    shadowColor: '#000', shadowOffset: { width: 0, height: 2 }, shadowOpacity: 0.25, shadowRadius: 3, elevation: 4,
  },
  trackActionSection: {
    backgroundColor: Colors.bg.elevated,
    borderRadius: Radius.lg,
    padding: Spacing.sm,
    marginBottom: Spacing.sm,
    gap: Spacing.xs,
  },
  trackActionHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: Spacing.sm,
  },
  trackToggleBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingHorizontal: Spacing.md,
    paddingVertical: 7,
    borderRadius: Radius.md,
    backgroundColor: Colors.primary + '18',
    borderWidth: 1,
    borderColor: Colors.primary + '40',
  },
  trackToggleBtnActive: {
    backgroundColor: Colors.primary,
    borderColor: Colors.primary,
  },
  trackToggleBtnText: {
    fontSize: Typography.xs,
    fontWeight: '700',
    color: Colors.primary,
  },
  trackToggleBtnTextActive: {
    color: '#fff',
  },
  fitTrackBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: Spacing.sm,
    paddingVertical: 6,
    borderRadius: Radius.sm,
    backgroundColor: Colors.bg.card,
    borderWidth: 1,
    borderColor: Colors.border.default,
  },
  fitTrackBtnText: {
    fontSize: Typography.xs,
    color: Colors.text.primary,
    fontWeight: '600',
  },
  trackPeriodRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    marginTop: 4,
  },
  periodChip: {
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: Radius.sm,
    backgroundColor: Colors.bg.card,
    borderWidth: 1,
    borderColor: Colors.border.default,
  },
  periodChipActive: {
    backgroundColor: Colors.primary,
    borderColor: Colors.primary,
  },
  periodChipText: {
    fontSize: Typography.xs,
    color: Colors.text.secondary,
    fontWeight: '600',
  },
  periodChipTextActive: {
    color: '#fff',
    fontWeight: '700',
  },
  trackSummaryMeta: {
    flex: 1,
    alignItems: 'flex-end',
  },
  trackSummaryText: {
    fontSize: Typography.xs,
    color: Colors.text.muted,
  },
  timestampContainer: {
    marginBottom: Spacing.sm,
    gap: 3,
  },
  timestampRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  timestampLabel: {
    fontSize: Typography.xs,
    color: Colors.text.muted,
  },
  timestampValue: {
    fontSize: Typography.xs,
    color: Colors.text.secondary,
    fontWeight: '500',
  },
  lostCollarMapBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.xs,
    backgroundColor: '#E67E2218',
    padding: Spacing.sm,
    borderRadius: Radius.md,
    marginBottom: Spacing.sm,
    borderWidth: 1,
    borderColor: '#E67E2240',
  },
  lostCollarMapText: {
    flex: 1,
    fontSize: Typography.xs,
    color: '#E67E22',
    fontWeight: '600',
  },
});
