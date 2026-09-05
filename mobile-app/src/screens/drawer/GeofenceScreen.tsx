import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator, Alert, FlatList, KeyboardAvoidingView, Linking, Platform,
  Pressable, ScrollView, StyleSheet, Switch, Text, TextInput, TouchableOpacity,
  useWindowDimensions, View,
} from 'react-native';
import MapView, { MapPressEvent, Marker, Polygon, Polyline, PROVIDER_DEFAULT } from 'react-native-maps';
import { Ionicons } from '@expo/vector-icons';
import { useIsFocused } from '@react-navigation/native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import * as Location from 'expo-location';

import DrawerScreenBase from './DrawerScreenBase';
import { Colors, Radius, Typography } from '../../constants/config';
import { useCreateGeofence, useDeleteGeofence, useGeofences, useUpdateGeofence } from '../../hooks/useGeofences';
import { useTelemetryLatest } from '../../hooks/useTelemetry';
import { useAuthStore } from '../../store/authStore';
import { useFarmStore } from '../../store/farmStore';
import { FarmAccess, GeoPoint, Geofence, GeofenceType, TelemetryLatest } from '../../types';
import { timeAgo } from '../../utils/helpers';
import {
  editablePoints, GEOFENCE_POSITION_LIMIT, initialMapRegion, isMapPoint,
  mapAnimals, positionRecency,
} from '../../utils/geofenceMap';

type IconName = React.ComponentProps<typeof Ionicons>['name'];

function MapTool({ icon, label, onPress, disabled = false, busy = false }: {
  icon: IconName; label: string; onPress: () => void; disabled?: boolean; busy?: boolean;
}) {
  const [tooltip, setTooltip] = useState(false);
  return (
    <View style={styles.toolWrapper}>
      <Pressable accessibilityRole="button" accessibilityLabel={label}
        accessibilityState={{ disabled: disabled || busy, busy }} disabled={disabled || busy}
        onPress={onPress} onHoverIn={() => setTooltip(true)} onHoverOut={() => setTooltip(false)}
        onLongPress={() => setTooltip(true)} onPressOut={() => setTooltip(false)}
        style={({ pressed }) => [styles.toolButton, pressed && styles.pressed]}>
        {busy ? <ActivityIndicator color={Colors.primary} />
          : <Ionicons name={icon} size={21} color={disabled ? Colors.text.disabled : Colors.text.primary} />}
      </Pressable>
      {tooltip && <View pointerEvents="none" style={styles.tooltip}><Text style={styles.tooltipText}>{label}</Text></View>}
    </View>
  );
}

export default function GeofenceScreen() {
  const currentFarm = useFarmStore((state) => state.farms.find((farm) => farm.id === state.currentFarmId));
  const role = useAuthStore((state) => state.role);
  if (!currentFarm) {
    return (
      <DrawerScreenBase title="Geofencing Zones">
        <View style={styles.state}><Text style={styles.stateText}>No farm assigned.</Text></View>
      </DrawerScreenBase>
    );
  }
  // Remount so drafts, locations and selections cannot cross farm boundaries.
  return <GeofenceWorkspace key={currentFarm.id} farm={currentFarm}
    canManage={role === 'admin' || currentFarm.permissions.includes('manage_farm')} />;
}

function GeofenceWorkspace({ farm, canManage }: { farm: FarmAccess; canManage: boolean }) {
  const mapRef = useRef<MapView>(null);
  const framed = useRef(false);
  const locationRequest = useRef(0);
  const isFocused = useIsFocused();
  const insets = useSafeAreaInsets();
  const { height } = useWindowDimensions();
  const geofencesQuery = useGeofences(farm.id);
  const telemetryQuery = useTelemetryLatest({ limit: GEOFENCE_POSITION_LIMIT }, { enabled: isFocused });
  const createGeofence = useCreateGeofence(farm.id);
  const updateGeofence = useUpdateGeofence(farm.id);
  const deleteGeofence = useDeleteGeofence(farm.id);

  const [mapReady, setMapReady] = useState(false);
  const [mapType, setMapType] = useState<'hybrid' | 'standard'>('hybrid');
  const [locationAllowed, setLocationAllowed] = useState(false);
  const [locating, setLocating] = useState(false);
  const [panelTab, setPanelTab] = useState<'zones' | 'animals'>('zones');
  const [selectedAnimalId, setSelectedAnimalId] = useState<number | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [drawing, setDrawing] = useState(false);
  const [name, setName] = useState('');
  const [type, setType] = useState<GeofenceType>('pasture');
  const [points, setPoints] = useState<GeoPoint[]>([]);
  const [now, setNow] = useState(Date.now);
  const zones = useMemo(() => (geofencesQuery.data ?? []).filter((zone) => zone.farm_id === farm.id), [geofencesQuery.data, farm.id]);
  const animals = useMemo(() => mapAnimals(telemetryQuery.data ?? []), [telemetryQuery.data]);
  const zoneCoordinates = useMemo(() => zones.flatMap((zone) => zone.points).filter(isMapPoint), [zones]);
  const saving = createGeofence.isPending || updateGeofence.isPending;
  const recentCount = animals.filter((animal) => positionRecency(animal.last_update, now) === 'recent').length;
  const initialRegion = useRef(initialMapRegion(animals.length ? animals : zoneCoordinates)).current;

  const takeMapControl = useCallback(() => {
    framed.current = true;
    locationRequest.current += 1;
    setLocating(false);
  }, []);

  const focusCoordinates = useCallback((coordinates: GeoPoint[]) => {
    const valid = coordinates.filter(isMapPoint).map(({ latitude, longitude }) => ({ latitude, longitude }));
    if (!mapReady || !valid.length) return;
    takeMapControl();
    if (valid.every((point) => point.latitude === valid[0].latitude && point.longitude === valid[0].longitude)) {
      mapRef.current?.animateToRegion({
        latitude: valid[0].latitude, longitude: valid[0].longitude,
        latitudeDelta: 0.008, longitudeDelta: 0.008,
      }, 400);
    } else {
      mapRef.current?.fitToCoordinates(valid, {
        edgePadding: { top: 100, right: 115, bottom: 65, left: 45 }, animated: true,
      });
    }
  }, [mapReady, takeMapControl]);

  useEffect(() => {
    if (framed.current || drawing || !isFocused || telemetryQuery.isLoading) return;
    focusCoordinates(animals.length ? animals : zoneCoordinates);
  }, [animals, zoneCoordinates, drawing, isFocused, telemetryQuery.isLoading, focusCoordinates]);

  useEffect(() => {
    if (!isFocused) return;
    setNow(Date.now());
    const timer = setInterval(() => setNow(Date.now()), 60_000);
    return () => clearInterval(timer);
  }, [isFocused]);

  useEffect(() => {
    let active = true;
    if (isFocused) {
      Location.getForegroundPermissionsAsync().then((permission) => {
        if (active) setLocationAllowed(permission.granted);
      }).catch(() => { if (active) setLocationAllowed(false); });
    }
    setLocating(false);
    return () => { active = false; locationRequest.current += 1; };
  }, [isFocused]);

  const resetEditor = useCallback(() => {
    setEditingId(null);
    setDrawing(false);
    setName('');
    setType('pasture');
    setPoints([]);
  }, []);

  useEffect(() => { if (!canManage) resetEditor(); }, [canManage, resetEditor]);

  const locatePhone = async () => {
    const requestId = ++locationRequest.current;
    let timeout: ReturnType<typeof setTimeout> | undefined;
    setLocating(true);
    framed.current = true;
    try {
      const permission = await Location.requestForegroundPermissionsAsync();
      if (requestId !== locationRequest.current) return;
      setLocationAllowed(permission.granted);
      if (!permission.granted) {
        Alert.alert('Location permission needed', 'Your position is optional. Animal positions and zone editing remain available.',
          permission.canAskAgain ? [{ text: 'OK' }] : [
            { text: 'Cancel', style: 'cancel' },
            { text: 'Open settings', onPress: () => { void Linking.openSettings().catch(() => Alert.alert('Unable to open settings')); } },
          ]);
        return;
      }
      const position = await Promise.race([
        Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced }),
        new Promise<never>((_, reject) => {
          timeout = setTimeout(() => reject(new Error('Location timeout')), 15_000);
        }),
      ]);
      if (requestId === locationRequest.current) focusCoordinates([position.coords]);
    } catch {
      if (requestId === locationRequest.current) {
        Alert.alert('Position unavailable', 'Check that location services are enabled, then try again.');
      }
    } finally {
      if (timeout) clearTimeout(timeout);
      if (requestId === locationRequest.current) setLocating(false);
    }
  };

  const startCreate = () => {
    if (!canManage) return;
    takeMapControl();
    resetEditor();
    setDrawing(true);
  };

  const startEdit = (zone: Geofence) => {
    if (!canManage) return;
    setEditingId(zone.id);
    setName(zone.name);
    setType(zone.type);
    setPoints(editablePoints(zone.points));
    setDrawing(true);
    focusCoordinates(zone.points);
  };

  const handleMapPress = (event: MapPressEvent) => {
    if (event.nativeEvent.action === 'marker-press') return;
    takeMapControl();
    if (!drawing || !canManage || saving) return;
    const coordinate = event.nativeEvent.coordinate;
    if (isMapPoint(coordinate)) setPoints((current) => [...current, coordinate]);
  };

  const handleSave = async () => {
    if (!canManage || saving || !name.trim() || points.length < 3) return;
    try {
      if (editingId !== null) {
        await updateGeofence.mutateAsync({ id: editingId, payload: { name: name.trim(), type, points } });
      } else {
        await createGeofence.mutateAsync({ farm_id: farm.id, name: name.trim(), type, points });
      }
      resetEditor();
      setPanelTab('zones');
    } catch (error) {
      Alert.alert('Unable to save zone', error instanceof Error ? error.message : 'The polygon is invalid.');
    }
  };

  const confirmDelete = (zone: Geofence) => {
    if (!canManage) return;
    Alert.alert('Delete zone', 'This permanently removes the selected zone.', [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Delete', style: 'destructive', onPress: async () => {
        try { await deleteGeofence.mutateAsync(zone.id); }
        catch { Alert.alert('Unable to delete zone'); }
      } },
    ]);
  };

  const selectAnimal = (animal: TelemetryLatest, recenter: boolean) => {
    takeMapControl();
    setSelectedAnimalId(animal.animal_id);
    if (!drawing) setPanelTab('animals');
    if (recenter) focusCoordinates([animal]);
  };

  const refresh = () => { void geofencesQuery.refetch(); void telemetryQuery.refetch(); };
  const panelHeight = drawing ? (height < 700 ? 236 : 254) : (height < 700 ? 180 : 218);

  return (
    <DrawerScreenBase title="Geofencing Zones" subtitle={farm.name}
      rightAction={canManage && !drawing ? (
        <TouchableOpacity style={styles.iconButton} onPress={startCreate} accessibilityRole="button" accessibilityLabel="Create zone">
          <Ionicons name="add" size={24} color={Colors.primary} />
        </TouchableOpacity>
      ) : undefined}>
      <KeyboardAvoidingView style={styles.screen} behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        keyboardVerticalOffset={insets.top + 64}>
        <View style={styles.mapArea}>
          <MapView ref={mapRef} style={StyleSheet.absoluteFillObject} provider={PROVIDER_DEFAULT}
            initialRegion={initialRegion} mapType={mapType} showsUserLocation={isFocused && locationAllowed}
            showsMyLocationButton={false} showsCompass={false} rotateEnabled={false} pitchEnabled={false}
            onMapReady={() => setMapReady(true)} onPanDrag={takeMapControl} onPress={handleMapPress}>
            {zones.map((zone) => (
              <Polygon key={zone.id} coordinates={zone.points}
                strokeColor={zone.type === 'danger' ? Colors.severity.critical : Colors.primary}
                fillColor={(zone.type === 'danger' ? Colors.severity.critical : Colors.primary) + (zone.active ? '30' : '10')}
                strokeWidth={editingId === zone.id ? 4 : 2} />
            ))}
            {animals.map((animal) => {
              const recent = positionRecency(animal.last_update, now) === 'recent';
              return (
                <Marker key={'animal-' + animal.animal_id} identifier={'animal-' + animal.animal_id} coordinate={animal}
                  title={animal.animal_name} description={'Last update ' + timeAgo(animal.last_update)}
                  pinColor={recent ? Colors.primary : Colors.status.offline}
                  zIndex={selectedAnimalId === animal.animal_id ? 3 : 2} stopPropagation
                  onPress={(event) => { event.stopPropagation(); selectAnimal(animal, false); }} />
              );
            })}
            {drawing && points.length >= 3 && (
              <Polygon coordinates={points} strokeColor={Colors.severity.info} fillColor={Colors.severity.info + '25'} strokeWidth={3} />
            )}
            {drawing && points.length === 2 && <Polyline coordinates={points} strokeColor={Colors.severity.info} strokeWidth={3} />}
            {drawing && points.map((point, index) => (
              <Marker key={'vertex-' + index} coordinate={point} title={'Point ' + (index + 1)} zIndex={4}
                pinColor={Colors.severity.info} draggable={canManage && !saving} stopPropagation
                onPress={(event) => event.stopPropagation()}
                onDragEnd={(event) => {
                  const coordinate = event.nativeEvent.coordinate;
                  if (canManage && !saving && isMapPoint(coordinate)) {
                    setPoints((current) => current.map((value, i) => i === index ? coordinate : value));
                  }
                }} />
            ))}
          </MapView>

          <View pointerEvents="none" style={styles.mapStatus}>
            {telemetryQuery.isLoading ? <Text style={styles.statusText}>Loading positions...</Text>
              : <Text style={styles.statusText}>{animals.length} positions{animals.length >= GEOFENCE_POSITION_LIMIT ? ' (limit)' : ''}</Text>}
            {animals.length > 0 && <Text style={styles.statusDetail}>{recentCount} recent (&lt;30 min) / {animals.length - recentCount} older or undated</Text>}
            {telemetryQuery.isError && <Text style={styles.warningText}>Position update failed</Text>}
            {geofencesQuery.isError && <Text style={styles.warningText}>Zone update failed</Text>}
          </View>
          <View style={styles.mapToolbar}>
            <MapTool icon="paw-outline" label="Center on animals" disabled={!mapReady || !animals.length} onPress={() => focusCoordinates(animals)} />
            <MapTool icon="map-outline" label="Center on zones" disabled={!mapReady || !zoneCoordinates.length} onPress={() => focusCoordinates(zoneCoordinates)} />
            <MapTool icon="locate-outline" label="My position" disabled={!mapReady} busy={locating} onPress={locatePhone} />
            <MapTool icon="layers-outline" label={mapType === 'hybrid' ? 'Show street map' : 'Show satellite map'}
              onPress={() => setMapType((value) => value === 'hybrid' ? 'standard' : 'hybrid')} />
          </View>
          {drawing && <View style={styles.drawingToolbar}>
            <MapTool icon="arrow-undo" label="Undo last point" disabled={!points.length || saving} onPress={() => setPoints((current) => current.slice(0, -1))} />
            <MapTool icon="trash-bin-outline" label="Clear drawn points" disabled={!points.length || saving} onPress={() => setPoints([])} />
          </View>}
        </View>

        <View style={[styles.panel, { height: panelHeight + insets.bottom, paddingBottom: insets.bottom }]}>
          {drawing ? (
            <ScrollView contentContainerStyle={styles.editor} keyboardShouldPersistTaps="handled">
              <View style={styles.editorHeading}>
                <Text style={styles.panelTitle}>{editingId === null ? 'New zone' : 'Edit zone'}</Text>
                <Text style={styles.meta}>{points.length} points</Text>
              </View>
              <TextInput value={name} onChangeText={setName} placeholder="Zone name" editable={!saving}
                accessibilityLabel="Zone name" placeholderTextColor={Colors.text.muted} style={styles.input} />
              <View style={styles.typeSegment}>
                {(['pasture', 'danger'] as GeofenceType[]).map((value) => (
                  <TouchableOpacity key={value} style={[styles.typeButton, type === value && styles.typeActive]}
                    disabled={saving} accessibilityRole="radio" accessibilityState={{ checked: type === value }} onPress={() => setType(value)}>
                    <View style={[styles.swatch, { backgroundColor: value === 'danger' ? Colors.severity.critical : Colors.primary }]} />
                    <Text style={styles.typeText}>{value === 'pasture' ? 'Pasture' : 'Danger'}</Text>
                  </TouchableOpacity>
                ))}
              </View>
              <View style={styles.editorActions}>
                <TouchableOpacity style={styles.secondaryButton} onPress={resetEditor} disabled={saving} accessibilityRole="button">
                  <Text style={styles.secondaryText}>Cancel</Text>
                </TouchableOpacity>
                <TouchableOpacity style={[styles.primaryButton, (saving || points.length < 3 || !name.trim()) && styles.disabled]}
                  onPress={handleSave} disabled={saving || points.length < 3 || !name.trim()} accessibilityRole="button">
                  {saving ? <ActivityIndicator color="#fff" /> : <Ionicons name="save-outline" size={18} color="#fff" />}
                  <Text style={styles.primaryText}>Save</Text>
                </TouchableOpacity>
              </View>
            </ScrollView>
          ) : (
            <>
              <View style={styles.panelTabs}>
                {(['zones', 'animals'] as const).map((tab) => (
                  <TouchableOpacity key={tab} accessibilityRole="tab" accessibilityState={{ selected: panelTab === tab }}
                    style={[styles.panelTab, panelTab === tab && styles.panelTabActive]} onPress={() => setPanelTab(tab)}>
                    <Ionicons name={tab === 'zones' ? 'map-outline' : 'paw-outline'} size={17}
                      color={panelTab === tab ? Colors.primaryLight : Colors.text.secondary} />
                    <Text style={[styles.tabText, panelTab === tab && styles.tabTextActive]}>
                      {tab === 'zones' ? 'Zones (' + zones.length + ')' : 'Animals (' + animals.length + ')'}
                    </Text>
                  </TouchableOpacity>
                ))}
                <TouchableOpacity style={styles.iconButton} accessibilityRole="button" accessibilityLabel="Refresh map data" onPress={refresh}
                  disabled={geofencesQuery.isFetching || telemetryQuery.isFetching}>
                  {geofencesQuery.isFetching || telemetryQuery.isFetching ? <ActivityIndicator size="small" color={Colors.primary} />
                    : <Ionicons name="refresh-outline" size={20} color={Colors.text.secondary} />}
                </TouchableOpacity>
              </View>
              {panelTab === 'animals' ? (
                <FlatList data={animals} keyExtractor={(animal) => String(animal.animal_id)} contentContainerStyle={styles.list}
                  ListEmptyComponent={<View style={styles.state}>
                    <Text style={styles.stateText}>{telemetryQuery.isLoading ? 'Loading positions...' : telemetryQuery.isError ? 'Unable to load animal positions.' : 'No animal positions received for this farm.'}</Text>
                  </View>}
                  renderItem={({ item: animal }) => {
                    const recency = positionRecency(animal.last_update, now);
                    const color = recency === 'recent' ? Colors.primary : Colors.status.offline;
                    return (
                      <TouchableOpacity style={[styles.animalRow, selectedAnimalId === animal.animal_id && styles.selectedRow]}
                        accessibilityRole="button" accessibilityLabel={'Locate ' + animal.animal_name}
                        onPress={() => selectAnimal(animal, true)}>
                        <Ionicons name="paw" size={20} color={color} />
                        <View style={styles.rowBody}>
                          <Text style={styles.rowName} numberOfLines={1}>{animal.animal_name}</Text>
                          <Text style={styles.meta}>{recency === 'unknown' ? 'Update time unknown' : 'Last update ' + timeAgo(animal.last_update)}</Text>
                          <Text style={styles.coordinates}>{animal.latitude.toFixed(5)}, {animal.longitude.toFixed(5)}</Text>
                        </View>
                        <Ionicons name="locate-outline" size={20} color={Colors.text.secondary} />
                      </TouchableOpacity>
                    );
                  }} />
              ) : geofencesQuery.isLoading ? <View style={styles.state}><ActivityIndicator color={Colors.primary} /></View>
                : geofencesQuery.isError && !zones.length ? <View style={styles.state}><Text style={styles.stateText}>Unable to load zones.</Text></View>
                  : <FlatList data={zones} keyExtractor={(zone) => String(zone.id)} contentContainerStyle={styles.list}
                    ListEmptyComponent={<View style={styles.state}><Text style={styles.stateText}>No zones configured for this farm.</Text></View>}
                    renderItem={({ item: zone }) => (
                      <View style={styles.zoneRow}>
                        <View style={[styles.zoneMark, { backgroundColor: zone.type === 'danger' ? Colors.severity.critical : Colors.primary }]} />
                        <TouchableOpacity style={styles.rowBody} onPress={() => focusCoordinates(zone.points)} accessibilityRole="button" accessibilityLabel={'Locate ' + zone.name}>
                          <Text style={styles.rowName} numberOfLines={1}>{zone.name}</Text>
                          <Text style={styles.meta}>{zone.type} / {editablePoints(zone.points).length} points{!zone.active ? ' / inactive' : ''}</Text>
                        </TouchableOpacity>
                        {canManage && <>
                          <Switch value={zone.active} disabled={saving} accessibilityLabel={'Activate ' + zone.name}
                            onValueChange={(active) => updateGeofence.mutate({ id: zone.id, payload: { active } }, {
                              onError: () => Alert.alert('Unable to update zone'),
                            })} trackColor={{ true: Colors.primary, false: Colors.bg.elevated }} />
                          <TouchableOpacity style={styles.rowAction} onPress={() => startEdit(zone)} disabled={saving} accessibilityRole="button" accessibilityLabel={'Edit ' + zone.name}>
                            <Ionicons name="create-outline" size={19} color={Colors.text.secondary} />
                          </TouchableOpacity>
                          <TouchableOpacity style={styles.rowAction} onPress={() => confirmDelete(zone)} disabled={deleteGeofence.isPending}
                            accessibilityRole="button" accessibilityLabel={'Delete ' + zone.name}>
                            <Ionicons name="trash-outline" size={19} color={Colors.severity.critical} />
                          </TouchableOpacity>
                        </>}
                      </View>
                    )} />}
            </>
          )}
        </View>
      </KeyboardAvoidingView>
    </DrawerScreenBase>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  mapArea: { flex: 1, minHeight: 0, overflow: 'hidden' },
  panel: { backgroundColor: Colors.bg.primary, borderTopWidth: 1, borderColor: Colors.border.default },
  iconButton: { width: 44, height: 44, alignItems: 'center', justifyContent: 'center' },
  mapStatus: { position: 'absolute', top: 12, left: 12, right: 120, padding: 10, borderRadius: Radius.sm, backgroundColor: Colors.bg.primary },
  statusText: { color: Colors.text.primary, fontSize: Typography.sm, fontWeight: '700' },
  statusDetail: { color: Colors.text.secondary, fontSize: Typography.xs, marginTop: 3 },
  warningText: { color: Colors.severity.warning, fontSize: Typography.xs, marginTop: 3 },
  mapToolbar: { position: 'absolute', top: 12, right: 12, width: 96, flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  drawingToolbar: { position: 'absolute', bottom: 12, right: 12, flexDirection: 'row', gap: 8 },
  toolWrapper: { width: 44, height: 44, zIndex: 1 },
  toolButton: { width: 44, height: 44, alignItems: 'center', justifyContent: 'center', borderRadius: Radius.sm, backgroundColor: Colors.bg.primary, borderWidth: 1, borderColor: Colors.border.default },
  pressed: { backgroundColor: Colors.bg.elevated },
  tooltip: { position: 'absolute', right: 50, top: 0, width: 148, minHeight: 44, justifyContent: 'center', padding: 8, borderRadius: Radius.sm, backgroundColor: Colors.bg.primary },
  tooltipText: { color: Colors.text.primary, fontSize: Typography.sm },
  panelTabs: { flexDirection: 'row', borderBottomWidth: 1, borderColor: Colors.border.default, paddingHorizontal: 8 },
  panelTab: { flex: 1, height: 44, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, borderBottomWidth: 2, borderColor: 'transparent' },
  panelTabActive: { borderColor: Colors.primary },
  tabText: { color: Colors.text.secondary, fontSize: Typography.sm, fontWeight: '600' },
  tabTextActive: { color: Colors.primaryLight },
  list: { paddingHorizontal: 12, paddingBottom: 8, flexGrow: 1 },
  animalRow: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 10, paddingHorizontal: 4, minHeight: 72, borderBottomWidth: 1, borderColor: Colors.border.default },
  selectedRow: { backgroundColor: Colors.bg.elevated },
  zoneRow: { minHeight: 68, flexDirection: 'row', alignItems: 'center', gap: 4, borderBottomWidth: 1, borderColor: Colors.border.default },
  zoneMark: { width: 4, height: 30, borderRadius: 2, marginRight: 6 },
  rowBody: { flex: 1, minWidth: 0, paddingVertical: 6 },
  rowName: { color: Colors.text.primary, fontSize: Typography.sm, fontWeight: '700' },
  meta: { color: Colors.text.secondary, fontSize: Typography.xs, marginTop: 3 },
  coordinates: { color: Colors.text.muted, fontSize: Typography.xs, marginTop: 3 },
  rowAction: { width: 40, height: 44, alignItems: 'center', justifyContent: 'center' },
  editor: { padding: 12, gap: 10 },
  editorHeading: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  panelTitle: { color: Colors.text.primary, fontSize: Typography.base, fontWeight: '700' },
  input: { minHeight: 44, borderRadius: Radius.sm, borderWidth: 1, borderColor: Colors.border.default, backgroundColor: Colors.bg.input, color: Colors.text.primary, paddingHorizontal: 12 },
  typeSegment: { flexDirection: 'row', gap: 8 },
  typeButton: { flex: 1, height: 40, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, borderRadius: Radius.sm, borderWidth: 1, borderColor: Colors.border.default },
  typeActive: { borderColor: Colors.primary, backgroundColor: Colors.bg.card },
  typeText: { color: Colors.text.primary, fontSize: Typography.sm, fontWeight: '600' },
  swatch: { width: 12, height: 12, borderRadius: 2 },
  editorActions: { flexDirection: 'row', gap: 8 },
  secondaryButton: { flex: 1, height: 44, alignItems: 'center', justifyContent: 'center', borderRadius: Radius.sm, borderWidth: 1, borderColor: Colors.border.default },
  secondaryText: { color: Colors.text.secondary, fontWeight: '700' },
  primaryButton: { flex: 1, height: 44, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, borderRadius: Radius.sm, backgroundColor: Colors.primary },
  primaryText: { color: '#fff', fontWeight: '700' },
  disabled: { opacity: 0.5 },
  state: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 16 },
  stateText: { color: Colors.text.secondary, fontSize: Typography.sm, textAlign: 'center' },
});
