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
import MapView, { Marker, PROVIDER_DEFAULT, Circle } from 'react-native-maps';
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

// ─── Helpers ──────────────────────────────────────────────────────────────────

function getActivityState(activity: number): ActivityState {
  if (activity < 0.15) return 'lying';
  if (activity < 0.5)  return 'standing';
  if (activity < 1.0)  return 'walking';
  return 'running';
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
  const state = getActivityState(point.activity);
  const color = isIsolated ? Colors.severity.critical : activityStateColor(state);

  return (
    <Marker
      coordinate={{ latitude: point.latitude, longitude: point.longitude }}
      onPress={onPress}
      tracksViewChanges={false}
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
  const maxActivity = Math.max(...cluster.points.map((p) => p.activity));
  const state = getActivityState(maxActivity);
  const color = activityStateColor(state);

  return (
    <Marker
      coordinate={{ latitude: cluster.latitude, longitude: cluster.longitude }}
      onPress={onPress}
      tracksViewChanges={false}
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
}: {
  point: TelemetryLatest | null;
  isIsolated: boolean;
  onClose: () => void;
  onNavigate: (id: number) => void;
}) {
  if (!point) return null;
  const state      = getActivityState(point.activity);
  const stateColor = activityStateColor(state);
  const batColor   = batteryColor(point.battery);

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

      <View style={styles.infoSheetHeader}>
        <View style={[styles.infoAnimalAvatar, { backgroundColor: stateColor + '20' }]}>
          <Text style={[styles.infoAvatarText, { color: stateColor }]}>
            {point.animal_name[0].toUpperCase()}
          </Text>
        </View>
        <View style={styles.infoSheetTitle}>
          <Text style={styles.infoAnimalName}>{point.animal_name}</Text>
          <Text style={styles.infoDeviceId}>Appareil : {point.device_id}</Text>
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
          <Text style={styles.infoStatLabel}>Comportement</Text>
          <Text style={[styles.infoStatValue, { color: stateColor }]}>
            {activityStateLabel(state)}
          </Text>
        </View>
        <View style={styles.infoStat}>
          <View style={[styles.infoStatIcon, { backgroundColor: Colors.primary + '20' }]}>
            <Ionicons name="pulse-outline" size={18} color={Colors.primary} />
          </View>
          <Text style={styles.infoStatLabel}>Activité</Text>
          <Text style={styles.infoStatValue}>{point.activity.toFixed(2)} g</Text>
        </View>
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
        <TouchableOpacity style={styles.infoDetailBtn} onPress={() => onNavigate(point.animal_id)}>
          <Text style={styles.infoDetailBtnText}>Voir fiche complète</Text>
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
          {cluster.points.length} animaux au même endroit
        </Text>
        <TouchableOpacity onPress={onClose} hitSlop={12}>
          <Ionicons name="close" size={22} color={Colors.text.secondary} />
        </TouchableOpacity>
      </View>

      {cluster.points.map((point) => {
        const state = getActivityState(point.activity);
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

  const allPoints = useMemo(() => {
  return (data ?? []).map(p => ({
    ...p,
    latitude:  parseFloat(String(p.latitude)),
    longitude: parseFloat(String(p.longitude)),
    activity:  parseFloat(String(p.activity)),
    battery:   parseInt(String(p.battery), 10),
    })).filter(p => !isNaN(p.latitude) && !isNaN(p.longitude));
  }, [data]);

  const { points, distantAnimals } = useMemo(() => {
    if (allPoints.length === 0) return { points: [], distantAnimals: [] as any[] };
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
    return { points: local, distantAnimals: distant };
  }, [allPoints]);

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

  if (isLoading && !data) return <LoadingState message="Chargement des positions…" />;
  if (isError && !data)   return <ErrorState message="Impossible de charger les positions" onRetry={refetch} />;

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
      </MapView>

      {/* ── Header ───────────────────────────────────────────────────── */}
      <View style={[styles.headerOverlay, { paddingTop: insets.top + Spacing.sm }]}>
        <View style={styles.headerCard}>
          <Ionicons name="map" size={16} color={Colors.primary} />
          <Text style={styles.headerText}>
            {points.length} Animal{points.length > 1 ? 's' : ''}
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
          <View style={styles.liveIndicator}>
            <View style={styles.liveDot} />
            <Text style={styles.liveText}>Live</Text>
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
        <TouchableOpacity style={styles.fab} onPress={refetch}>
          <Ionicons name="refresh-outline" size={22} color={Colors.text.primary} />
        </TouchableOpacity>
        <TouchableOpacity style={styles.fab} onPress={fitToHerd}>
          <Ionicons name="locate-outline" size={22} color={Colors.text.primary} />
        </TouchableOpacity>
      </View>

      {/* ── Légende ──────────────────────────────────────────────────── */}
      {!sheetOpen && (
        <View style={[styles.legend, { bottom: insets.bottom + 90 }]}>
          {(['lying', 'standing', 'walking', 'running'] as ActivityState[]).map((s) => (
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
          onClose={() => setSelectedAnimal(null)}
          onNavigate={(id) => {
            setSelectedAnimal(null);
            navigation.navigate('Animals', { screen: 'AnimalDetail', params: { animalId: id } });
          }}
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
              Hors zone ({distantAnimals.length})
            </Text>
            <TouchableOpacity onPress={() => setShowDistantSheet(false)} hitSlop={12}>
              <Ionicons name="close" size={22} color={Colors.text.secondary} />
            </TouchableOpacity>
          </View>
          {distantAnimals.map((p: any) => (
            <View key={p.animal_id} style={styles.clusterItem}>
              <View style={[styles.clusterItemAvatar, { backgroundColor: '#9B59B620' }]}>
                <Text style={[styles.clusterItemInitial, { color: '#9B59B6' }]}>
                  {p.animal_name[0].toUpperCase()}
                </Text>
              </View>
              <View style={styles.clusterItemInfo}>
                <Text style={styles.clusterItemName}>{p.animal_name}</Text>
                <Text style={{ fontSize: Typography.xs, color: '#9B59B6' }}>
                  À {p._distanceKm} km du troupeau
                </Text>
              </View>
              <Text style={styles.clusterItemBattery}>{p.battery}%</Text>
            </View>
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
});