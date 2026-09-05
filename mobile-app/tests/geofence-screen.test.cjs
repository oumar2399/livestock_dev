/* global __dirname */
const assert = require('node:assert/strict');
const path = require('node:path');
const { afterEach, mock, test } = require('node:test');
const React = require('react');
const { act, create } = require('react-test-renderer');
const { loadTypeScript } = require('./helpers/load-typescript.cjs');

global.IS_REACT_ACT_ENVIRONMENT = true;
const mounted = [];
afterEach(async () => { for (const renderer of mounted.splice(0)) await act(async () => renderer.unmount()); });

const ring = [{ latitude: 5, longitude: -4 }, { latitude: 5.1, longitude: -4 }, { latitude: 5.1, longitude: -3.9 }, { latitude: 5, longitude: -4 }];
const sampleAnimal = (id, name, time) => ({ animal_id: id, animal_name: name, device_id: 'M5-' + id,
  latitude: 5 + id / 100, longitude: -4, battery: 80, activity: 0.1, activity_state: 'Resting', last_update: time });

async function harness(options = {}) {
  const state = {
    farmId: 1, focused: true, canManage: true, loading: false,
    animals: [sampleAnimal(1, 'Ari', new Date(Date.now() - 1000).toISOString()), sampleAnimal(2, 'Zoe', '2020-01-01T00:00:00Z')],
    zones: [{ id: 10, farm_id: 1, name: 'Pasture A', type: 'pasture', active: true, points: ring }],
    ...options,
  };
  const camera = { fitToCoordinates: mock.fn(), animateToRegion: mock.fn() };
  const alerts = mock.fn();
  const createZone = mock.fn(async () => ({}));
  const updateZone = mock.fn(async () => ({}));
  const deleteZone = mock.fn(async () => ({}));
  const location = {
    Accuracy: { Balanced: 3 },
    getForegroundPermissionsAsync: mock.fn(async () => ({ granted: false })),
    requestForegroundPermissionsAsync: mock.fn(async () => ({ granted: false, canAskAgain: true })),
    getCurrentPositionAsync: mock.fn(async () => ({ coords: { latitude: 35, longitude: 139 } })),
  };
  const native = Object.fromEntries(['View', 'Text', 'TouchableOpacity', 'Pressable', 'ScrollView', 'TextInput',
    'ActivityIndicator', 'Switch', 'KeyboardAvoidingView'].map((name) => [name, name]));
  native.StyleSheet = { create: (styles) => styles, absoluteFillObject: {} };
  native.Platform = { OS: 'android' };
  native.useWindowDimensions = () => ({ width: 360, height: 800 });
  native.Alert = { alert: alerts };
  native.Linking = { openSettings: mock.fn(async () => {}) };
  native.FlatList = function TestFlatList({ data, renderItem, ListEmptyComponent, ...props }) {
    return React.createElement('FlatList', props,
      data.length ? data.map((item, index) => React.createElement(React.Fragment, { key: index }, renderItem({ item, index }))) : ListEmptyComponent);
  };
  const Map = React.forwardRef((props, ref) => {
    React.useImperativeHandle(ref, () => camera);
    return React.createElement('MapView', props, props.children);
  });
  Map.displayName = 'TestMap';
  const mutation = (fn) => ({ isPending: false, mutateAsync: fn, mutate: fn });
  const query = (data) => ({ data, isLoading: false, isError: false, isFetching: false, refetch: mock.fn(async () => {}) });
  const Component = loadTypeScript(path.resolve(__dirname, '../src/screens/drawer/GeofenceScreen.tsx'), {
    'react-native': native,
    'react-native-maps': { __esModule: true, default: Map, Marker: 'Marker', Polygon: 'Polygon', Polyline: 'Polyline', PROVIDER_DEFAULT: null },
    '@expo/vector-icons': { Ionicons: 'Ionicons' },
    '@react-navigation/native': { useIsFocused: () => state.focused },
    'react-native-safe-area-context': { useSafeAreaInsets: () => ({ top: 24, bottom: 16 }) },
    'expo-location': location,
    './DrawerScreenBase': { __esModule: true, default: ({ children, rightAction, ...props }) => React.createElement('Screen', props, rightAction, children) },
    '../../store/farmStore': { useFarmStore: (selector) => selector({ currentFarmId: state.farmId,
      farms: [1, 2].map((id) => ({ id, name: 'Farm ' + id, permissions: state.canManage ? ['manage_farm'] : ['view_animals'] })) }) },
    '../../store/authStore': { useAuthStore: (selector) => selector({ role: 'farmer' }) },
    '../../hooks/useTelemetry': { useTelemetryLatest: () => ({ ...query(state.animals), isLoading: state.loading }) },
    '../../hooks/useGeofences': {
      useGeofences: () => query(state.zones), useCreateGeofence: () => mutation(createZone),
      useUpdateGeofence: () => mutation(updateZone), useDeleteGeofence: () => mutation(deleteZone),
    },
  }).default;
  let renderer;
  await act(async () => { renderer = create(React.createElement(Component)); });
  mounted.push(renderer);
  const root = () => renderer.root;
  const host = (type) => root().findAllByType(type);
  const button = (label) => root().findAll((node) => typeof node.type === 'string' && node.props.accessibilityLabel === label)[0];
  const update = async () => { await act(async () => renderer.update(React.createElement(Component))); };
  const press = async (label) => { await act(async () => { await button(label).props.onPress(); }); };
  const ready = async () => { await act(async () => host('MapView')[0].props.onMapReady()); };
  const tap = async (coordinate, action = 'press') => { await act(async () => host('MapView')[0].props.onPress({ nativeEvent: { coordinate, action } })); };
  return { state, camera, alerts, createZone, updateZone, location, host, button, update, press, ready, tap };
}

test('renders recent and old animal positions and initially frames the herd', async () => {
  const h = await harness();
  await h.ready();
  assert.equal(h.host('Marker').length, 2);
  assert.notEqual(h.host('Marker')[0].props.pinColor, h.host('Marker')[1].props.pinColor);
  assert.equal(h.camera.fitToCoordinates.mock.calls[0].arguments[0].length, 2);
  assert.equal(h.location.requestForegroundPermissionsAsync.mock.callCount(), 0);
});

test('data refresh does not recenter a map the user is already looking at', async () => {
  const h = await harness();
  await h.ready();
  const before = h.camera.fitToCoordinates.mock.callCount();
  h.state.animals = h.state.animals.map((animal) => ({ ...animal, latitude: animal.latitude + 0.01 }));
  await h.update();
  assert.equal(h.camera.fitToCoordinates.mock.callCount(), before);
});

test('drawing survives refresh, marker taps do not add vertices, and points can be moved', async () => {
  const h = await harness();
  await h.ready();
  await h.press('Create zone');
  await h.tap(ring[0]);
  await h.tap(ring[1]);
  assert.equal(h.host('Polyline').length, 1);
  const vertices = () => h.host('Marker').filter((marker) => marker.props.title.startsWith('Point '));
  await h.tap(ring[2], 'marker-press');
  assert.equal(vertices().length, 2);
  await act(async () => h.host('Marker')[0].props.onPress({ stopPropagation() {} }));
  assert.equal(vertices().length, 2);
  await h.tap(ring[2]);
  assert.equal(h.host('Polyline').length, 0);
  const cameraCalls = h.camera.fitToCoordinates.mock.callCount();
  h.state.zones = h.state.zones.map((zone) => ({ ...zone }));
  await h.update();
  assert.equal(vertices().length, 3);
  assert.equal(h.camera.fitToCoordinates.mock.callCount(), cameraCalls);
  const moved = { latitude: 5.2, longitude: -3.8 };
  await act(async () => vertices()[1].props.onDragEnd({ nativeEvent: { coordinate: moved } }));
  await act(async () => h.host('TextInput')[0].props.onChangeText('  New pasture  '));
  const save = h.host('TouchableOpacity').find((node) => node.findAllByType('Text').some((text) => text.props.children === 'Save'));
  await act(async () => save.props.onPress());
  assert.deepEqual(h.createZone.mock.calls[0].arguments[0], { farm_id: 1, name: 'New pasture', type: 'pasture', points: [ring[0], moved, ring[2]] });
});

test('changing farm clears the draft and the previous animal selection', async () => {
  const h = await harness();
  await h.ready();
  await h.press('Create zone');
  await h.tap(ring[0]);
  h.state.farmId = 2;
  h.state.animals = [sampleAnimal(3, 'Other farm', '2020-01-01T00:00:00Z')];
  await h.update();
  assert.equal(h.host('TextInput').length, 0);
  assert.equal(h.host('Polygon').length, 0);
  assert.equal(h.host('Marker').length, 1);
  assert.equal(h.host('Marker')[0].props.title, 'Other farm');
  assert.ok(h.button('Create zone'));
});

test('denied phone location does not block drawing or fetch a GPS position', async () => {
  const h = await harness();
  await h.ready();
  await h.press('My position');
  assert.equal(h.alerts.mock.calls[0].arguments[0], 'Location permission needed');
  assert.equal(h.location.getCurrentPositionAsync.mock.callCount(), 0);
  assert.equal(h.host('MapView')[0].props.showsUserLocation, false);
  await h.press('Create zone');
  await h.tap(ring[0]);
  assert.equal(h.host('Marker').filter((node) => node.props.title === 'Point 1').length, 1);
});

test('allowed phone location recenters separately from animals', async () => {
  const h = await harness();
  await h.ready();
  h.location.requestForegroundPermissionsAsync.mock.mockImplementation(async () => ({ granted: true }));
  await h.press('My position');
  assert.equal(h.host('MapView')[0].props.showsUserLocation, true);
  assert.equal(h.camera.animateToRegion.mock.calls.at(-1).arguments[0].latitude, 35);
});

test('late phone location cannot move the map after changing farms', async () => {
  const h = await harness();
  await h.ready();
  h.location.requestForegroundPermissionsAsync.mock.mockImplementation(async () => ({ granted: true }));
  let resolvePosition;
  h.location.getCurrentPositionAsync.mock.mockImplementation(() => new Promise((resolve) => { resolvePosition = resolve; }));
  let pending;
  await act(async () => { pending = h.button('My position').props.onPress(); });
  h.state.farmId = 2;
  await h.update();
  await act(async () => { resolvePosition({ coords: { latitude: 35, longitude: 139 } }); await pending; });
  assert.equal(h.camera.animateToRegion.mock.callCount(), 0);
});

test('view-only users cannot create or edit zones', async () => {
  const h = await harness({ canManage: false });
  await h.ready();
  assert.equal(h.button('Create zone'), undefined);
  assert.equal(h.button('Edit Pasture A'), undefined);
  assert.equal(h.host('Switch').length, 0);
  await h.tap(ring[0]);
  assert.equal(h.host('TextInput').length, 0);
});

test('with no positions the map uses zones, and missing data does not fabricate markers', async () => {
  const h = await harness({ animals: [] });
  await h.ready();
  assert.equal(h.host('Marker').length, 0);
  assert.deepEqual(h.camera.fitToCoordinates.mock.calls[0].arguments[0], ring);
  assert.equal(h.button('Center on animals').props.disabled, true);
});

test('the editor removes the closing vertex and updates the existing zone', async () => {
  const h = await harness();
  await h.ready();
  await h.press('Edit Pasture A');
  assert.equal(h.host('Marker').filter((node) => node.props.title.startsWith('Point ')).length, 3);
  const save = h.host('TouchableOpacity').find((node) => node.findAllByType('Text').some((text) => text.props.children === 'Save'));
  await act(async () => save.props.onPress());
  assert.equal(h.updateZone.mock.calls[0].arguments[0].id, 10);
  assert.equal(h.updateZone.mock.calls[0].arguments[0].payload.points.length, 3);
  assert.equal(h.createZone.mock.callCount(), 0);
});

test('starting a drawing cancels the camera effect of an outstanding GPS request', async () => {
  const h = await harness();
  await h.ready();
  h.location.requestForegroundPermissionsAsync.mock.mockImplementation(async () => ({ granted: true }));
  let resolvePosition;
  h.location.getCurrentPositionAsync.mock.mockImplementation(() => new Promise((resolve) => { resolvePosition = resolve; }));
  let pending;
  await act(async () => { pending = h.button('My position').props.onPress(); });
  await h.press('Create zone');
  await h.tap(ring[0]);
  await act(async () => { resolvePosition({ coords: { latitude: 35, longitude: 139 } }); await pending; });
  assert.equal(h.camera.animateToRegion.mock.callCount(), 0);
  assert.equal(h.host('TextInput').length, 1);
  assert.equal(h.host('Marker').filter((node) => node.props.title === 'Point 1').length, 1);
});

test('a failed GPS fix releases the location button and leaves the editor available', async () => {
  const h = await harness();
  await h.ready();
  h.location.requestForegroundPermissionsAsync.mock.mockImplementation(async () => ({ granted: true }));
  h.location.getCurrentPositionAsync.mock.mockImplementation(async () => { throw new Error('GPS unavailable'); });
  await h.press('My position');
  assert.equal(h.alerts.mock.calls[0].arguments[0], 'Position unavailable');
  assert.equal(h.button('My position').props.disabled, false);
  await h.press('Create zone');
  assert.equal(h.host('TextInput').length, 1);
});

test('coincident animals use a usable zoom instead of a zero-area bounding box', async () => {
  const animal = sampleAnimal(1, 'Ari', '2020-01-01T00:00:00Z');
  const h = await harness({ animals: [animal, { ...animal, animal_id: 2, animal_name: 'Zoe' }] });
  await h.ready();
  assert.equal(h.host('Marker').length, 2);
  assert.equal(h.camera.fitToCoordinates.mock.callCount(), 0);
  assert.equal(h.camera.animateToRegion.mock.calls[0].arguments[0].latitudeDelta, 0.008);
});
