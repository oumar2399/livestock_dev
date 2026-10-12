/* global __dirname */
// The Dashboard header shows the current farm name (with an icon) in place of the
// in-screen "Dashboard" title. The navigator header still says "Dashboard".
const assert = require('node:assert/strict');
const path = require('node:path');
const { afterEach, mock, test } = require('node:test');
const React = require('react');
const { act, create } = require('react-test-renderer');
const { create: createStore } = require('zustand');
const { loadTypeScript } = require('./helpers/load-typescript.cjs');

global.IS_REACT_ACT_ENVIRONMENT = true;
const SRC = path.resolve(__dirname, '../src');
const { Colors, Typography } = loadTypeScript(path.join(SRC, 'constants/config.ts'));

const mounted = [];
afterEach(async () => {
  for (const renderer of mounted.splice(0)) {
    await act(async () => renderer.unmount());
  }
});

const query = (data) => ({ data, isLoading: false, isError: false, isRefetching: false, refetch: () => {} });

function nativeMock() {
  const native = Object.fromEntries(
    ['View', 'Text', 'ScrollView', 'TouchableOpacity', 'RefreshControl', 'ActivityIndicator'].map((name) => [name, name]),
  );
  native.StyleSheet = { create: (styles) => styles };
  return native;
}

const textOf = (node) => [].concat(node.props.children).join('');

/** Mounts the real DashboardScreen over a real zustand store holding the farm state. */
async function mountDashboard(initial) {
  const store = createStore(() => initial);
  const native = nativeMock();
  const Dashboard = loadTypeScript(path.join(SRC, 'screens/DashboardScreen.tsx'), {
    'react-native': native,
    '@expo/vector-icons': { Ionicons: 'Ionicons' },
    '@react-navigation/native': { useNavigation: () => ({ navigate: mock.fn() }) },
    'react-native-safe-area-context': { useSafeAreaInsets: () => ({ top: 0 }) },
    '../store/farmStore': { useFarmStore: store },
    '../hooks/useAnimals': { useAnimals: () => query({ animals: [], total: 0 }) },
    '../hooks/useAlerts': {
      useActiveAlerts: () => query({ alerts: [], unresolved_count: 0 }),
      useAcknowledgeAlert: () => ({ mutate: () => {}, isPending: false }),
    },
    '../hooks/useTelemetry': { useTelemetryLatest: () => query([]) },
    '../hooks/useDevices': { useFarmDevices: () => ({ data: [] }) },
    '../components/ui': {
      StatCard: 'StatCard', SectionTitle: 'SectionTitle', EmptyState: 'EmptyState',
      LoadingState: 'LoadingState', ErrorState: 'ErrorState',
    },
  }).default;

  let renderer;
  await act(async () => {
    renderer = create(React.createElement(Dashboard));
  });
  mounted.push(renderer);
  const root = renderer.root;
  return {
    store,
    texts: () => root.findAllByType('Text').map(textOf),
    icons: () => root.findAllByType('Ionicons'),
    farmRow: (name) => root.findAllByType('Text').find((node) => textOf(node) === name)?.parent,
  };
}

const farm = (id, name) => ({ id, name });

test('farm selected: its name replaces the in-screen title, after the greeting, with an icon', async () => {
  const screen = await mountDashboard({ farms: [farm(1, 'Ferme Alpha')], currentFarmId: 1 });
  const texts = screen.texts();
  assert.ok(texts.includes('Ferme Alpha'));
  assert.ok(!texts.includes('Dashboard'), 'the second "Dashboard" title is gone');
  assert.ok(texts.indexOf('Pastoral Overview 👋') < texts.indexOf('Ferme Alpha'));

  const row = screen.farmRow('Ferme Alpha');
  const [icon, title] = row.children;
  assert.equal(icon.props.name, 'business-outline');
  assert.equal(title.props.children, 'Ferme Alpha');
});

test('icon and title use the existing theme tokens', async () => {
  const screen = await mountDashboard({ farms: [farm(1, 'Ferme Alpha')], currentFarmId: 1 });
  const [icon] = screen.farmRow('Ferme Alpha').children;
  assert.equal(icon.props.color, Colors.primary);
  assert.equal(icon.props.size, Typography.xl);
  const title = screen.farmRow('Ferme Alpha').children[1];
  assert.equal(title.props.style.fontSize, Typography['2xl']);
  assert.equal(title.props.style.color, Colors.text.primary);
});

test('long name: one line, ellipsis, and the text box shrinks instead of pushing the bell', async () => {
  const longName = 'Exploitation Agricole Familiale du Grand Plateau Nord-Est et Dependances';
  const screen = await mountDashboard({ farms: [farm(1, longName)], currentFarmId: 1 });
  const row = screen.farmRow(longName);
  const title = row.children[1];
  assert.equal(title.props.numberOfLines, 1);
  assert.equal(title.props.ellipsizeMode, 'tail');
  assert.equal(title.props.style.flexShrink, 1);
  assert.equal(row.parent.props.style.flex, 1);
  assert.equal(row.parent.props.style.minWidth, 0);
});

test('name not found in the farm list: no farm row, no crash, the original title stays', async () => {
  const screen = await mountDashboard({ farms: [], currentFarmId: 7 });
  assert.ok(screen.texts().includes('Dashboard'));
  assert.equal(screen.icons().filter((icon) => icon.props.name === 'business-outline').length, 0);
});

test('switching farm (as the drawer does) updates the name', async () => {
  const screen = await mountDashboard({ farms: [farm(1, 'Ferme Alpha'), farm(2, 'Ferme Beta')], currentFarmId: 1 });
  assert.ok(screen.texts().includes('Ferme Alpha'));
  await act(async () => screen.store.setState({ currentFarmId: 2 }));
  assert.ok(screen.texts().includes('Ferme Beta'));
  assert.ok(!screen.texts().includes('Ferme Alpha'));
});

test('no farm selected (admin): withFarm still shows "No farm selected" and never mounts the Dashboard', async () => {
  let dashboardMounted = false;
  const Probe = () => {
    dashboardMounted = true;
    return null;
  };
  const { withFarm } = loadTypeScript(path.join(SRC, 'components/RequireFarm.tsx'), {
    '@react-navigation/native': { useNavigation: () => ({ dispatch: () => {} }), DrawerActions: { openDrawer: () => ({}) } },
    '../store/farmStore': { useFarmStore: () => ({ currentFarmId: null, isLoading: false }) },
    './ui': {
      EmptyState: (props) => React.createElement('EmptyState', props),
      LoadingState: 'LoadingState',
    },
  });
  let renderer;
  await act(async () => {
    renderer = create(React.createElement(withFarm(Probe)));
  });
  mounted.push(renderer);
  const empty = renderer.root.findByType('EmptyState');
  assert.equal(empty.props.title, 'No farm selected');
  assert.equal(empty.props.message, 'Choose a farm in the menu to see its herd, map and alerts.');
  assert.equal(dashboardMounted, false);
});
