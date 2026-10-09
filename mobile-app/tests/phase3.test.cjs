/* global __dirname */
// Phase 3 regression tests (acceptance test 2026-10-07): roles per farm in the UI,
// admin-only farm creation, member actions.
const assert = require('node:assert/strict');
const path = require('node:path');
const { afterEach, mock, test } = require('node:test');
const React = require('react');
const { act, create } = require('react-test-renderer');
const { loadTypeScript } = require('./helpers/load-typescript.cjs');
const { buttonsLabelled, sharedUiOverrides } = require('./helpers/shared-ui.cjs');

global.IS_REACT_ACT_ENVIRONMENT = true;
const SRC = path.join(__dirname, '../src');
const mounted = [];
afterEach(async () => {
  for (const renderer of mounted.splice(0)) await act(async () => renderer.unmount());
});

const api = loadTypeScript(path.join(SRC, 'api/client.ts'));

function nativeMock() {
  const native = Object.fromEntries(['View', 'Text', 'TouchableOpacity', 'ScrollView', 'TextInput',
    'ActivityIndicator', 'RefreshControl'].map((n) => [n, n]));
  native.StyleSheet = { create: (styles) => styles };
  native.Alert = { alert: mock.fn() };
  native.Modal = ({ visible, children }) => (visible ? React.createElement('Modal', null, children) : null);
  native.FlatList = ({ data, renderItem, keyExtractor, ListEmptyComponent }) => React.createElement('List', null,
    (data ?? []).length === 0 ? ListEmptyComponent ?? null
      : data.map((item) => React.createElement(React.Fragment, { key: keyExtractor(item) }, renderItem({ item }))));
  return native;
}

async function mount(element) {
  let renderer;
  await act(async () => { renderer = create(element); });
  mounted.push(renderer);
  return renderer;
}

const textOf = (renderer) => renderer.root.findAllByType('Text')
  .map((node) => node.props.children).flat(Infinity).join(' ');

function screenBase() {
  return {
    __esModule: true,
    default: ({ children, title, subtitle, rightAction }) => React.createElement('Screen', null,
      React.createElement('Text', null, title), React.createElement('Text', null, subtitle), rightAction, children),
  };
}

function clientMock(getData) {
  return {
    __esModule: true,
    default: { get: mock.fn(async () => ({ data: getData })), post: mock.fn(), patch: mock.fn(), put: mock.fn(), delete: mock.fn() },
    ApiError: api.ApiError, NetworkError: api.NetworkError,
  };
}

// ── 3.3 Members: explicit actions, never on one's own row ──────────────────

const MEMBERS = [
  { id: 1, user_id: 10, user_email: 'owner1@example.com', user_name: 'Owner One', role: 'owner', status: 'active' },
  { id: 2, user_id: 11, user_email: 'vet@example.com', user_name: 'Vet', role: 'vet', status: 'active' },
];

async function renderUsers({ permissions, userId = 10 }) {
  const native = nativeMock();
  const client = clientMock({ members: MEMBERS });
  const Component = loadTypeScript(path.join(SRC, 'screens/drawer/UsersScreen.tsx'), {
    ...sharedUiOverrides(native),
    '@expo/vector-icons': { Ionicons: 'Ionicons' },
    './DrawerScreenBase': screenBase(),
    '../../store/authStore': { useAuthStore: () => ({ isAdmin: () => false, user: { id: userId } }) },
    '../../store/farmStore': { useFarmStore: () => ({ currentFarmId: 17,
      farms: [{ id: 17, name: 'Test Farm A', membership_role: 'owner', permissions }] }) },
    '../../api/client': client, '../api/client': client,
  }).default;
  const renderer = await mount(React.createElement(Component));
  return { renderer, native };
}

test('owner sees Change role and Revoke on other members, and "You" on its own row', async () => {
  const { renderer, native } = await renderUsers({ permissions: ['invite_members'] });
  const text = textOf(renderer);
  assert.match(text, /You/);
  assert.equal((text.match(/Change role/g) ?? []).length, 1, 'only the other member gets actions');
  assert.equal((text.match(/Revoke/g) ?? []).length, 1);
  const changeRole = renderer.root.findAllByType('TouchableOpacity')
    .find((b) => b.findAllByType('Text').some((t) => t.props.children === 'Change role'));
  await act(async () => changeRole.props.onPress());
  const [title, , choices] = native.Alert.alert.mock.calls.at(-1).arguments;
  assert.equal(title, 'Change role');
  assert.deepEqual(choices.map((c) => c.text), ['Farmer', 'Owner', 'Cancel'], 'the current role is not offered');
});

test('a member without invite_members sees no member actions', async () => {
  const { renderer } = await renderUsers({ permissions: ['view_animals', 'edit_animals'], userId: 99 });
  assert.doesNotMatch(textOf(renderer), /Change role|Revoke/);
});

// ── 3.1 Alerts: acknowledge/resolve and feedback follow the permissions ────

async function renderAlerts(permissions) {
  const native = nativeMock();
  const alert = { id: 5, animal_id: 1, animal_name: 'Bella', type: 'activity_deviation_low', severity: 'warning',
    title: 'Low activity', message: null, alert_metadata: null, triggered_at: '2026-10-08T00:00:00Z',
    acknowledged_at: null, resolved_at: null };
  const ui = loadTypeScript(path.join(SRC, 'components/ui.tsx'), {
    ...sharedUiOverrides(native), '@expo/vector-icons': { Ionicons: 'Ionicons' },
    'react-native-safe-area-context': { useSafeAreaInsets: () => ({ top: 0, bottom: 0 }) },
  });
  const Component = loadTypeScript(path.join(SRC, 'screens/AlertsListScreen.tsx'), {
    ...sharedUiOverrides(native),
    '@expo/vector-icons': { Ionicons: 'Ionicons' },
    'react-native-safe-area-context': { useSafeAreaInsets: () => ({ top: 0, bottom: 0 }) },
    '../hooks/useAlerts': {
      useAlerts: () => ({ data: { total: 1, alerts: [alert], unresolved_count: 1 }, isLoading: false,
        isError: false, refetch: () => {}, isRefetching: false }),
      useAcknowledgeAlert: () => ({ mutate: mock.fn(), isPending: false }),
      useResolveAlert: () => ({ mutate: mock.fn(), isPending: false }),
    },
    '../hooks/useFeedback': { useSubmitAlertFeedback: () => ({ mutate: mock.fn(), isPending: false }) },
    '../store/farmStore': { useFarmStore: (selector) => selector({ currentFarmId: 1,
      farms: [{ id: 1, name: 'Farm', permissions }] }) },
    '../components/ui': ui,
  }).default;
  const renderer = await mount(React.createElement(Component));
  const header = renderer.root.findAllByType('TouchableOpacity')
    .find((b) => b.findAllByType('Text').some((t) => t.props.children === 'Low activity'));
  await act(async () => header.props.onPress());  // expand the card
  const labels = renderer.root.findAllByType('Text').map((t) => [].concat(t.props.children).join(''));
  return { text: textOf(renderer), labels };
}

test('a vet sees alerts but cannot acknowledge, resolve or give feedback', async () => {
  const { text, labels } = await renderAlerts(['view_animals', 'view_veterinary', 'manage_veterinary']);
  assert.match(text, /Low activity/);
  assert.equal(labels.includes('Acknowledge'), false);
  assert.equal(labels.includes('Resolve'), false);
  assert.doesNotMatch(text, /Field Feedback/);
});

test('a farmer acknowledges, resolves and gives feedback', async () => {
  const { text, labels } = await renderAlerts(['view_animals', 'manage_alerts', 'give_feedback']);
  assert.ok(labels.includes('Acknowledge'));
  assert.ok(labels.includes('Resolve'));
  assert.match(text, /Field Feedback/);
});

// ── 3.2 Farm creation: platform admin only ─────────────────────────────────

async function renderFarmScreen(role) {
  const native = nativeMock();
  const client = clientMock({});
  const Component = loadTypeScript(path.join(SRC, 'screens/drawer/FarmScreen.tsx'), {
    ...sharedUiOverrides(native),
    '@expo/vector-icons': { Ionicons: 'Ionicons' },
    '@react-navigation/native': { useNavigation: () => ({ navigate: mock.fn() }) },
    './DrawerScreenBase': screenBase(),
    '../../api/client': client, '../api/client': client,
    '../../store/authStore': { useAuthStore: (selector) => selector({ role }) },
    '../../store/farmStore': { useFarmStore: () => ({ farms: [], currentFarmId: null, loadFarms: mock.fn(), selectFarm: mock.fn() }) },
    '../../components/FarmCreateModal': { __esModule: true, default: () => null },
  }).default;
  return textOf(await mount(React.createElement(Component)));
}

test('only the platform admin is offered farm creation', async () => {
  const owner = await renderFarmScreen('owner');
  assert.doesNotMatch(owner, /Create a farm/);
  assert.match(owner, /Farms are created by the administrator/);
  const admin = await renderFarmScreen('admin');
  assert.match(admin, /Create a farm/);
});

// ── 3.4 / 3.5 / 3.7 devices ─────────────────────────────────────────────────

function loadDeviceStatus(native = nativeMock()) {
  return loadTypeScript(path.join(SRC, 'utils/deviceStatus.ts'), {
    ...sharedUiOverrides(native), '../api/client': clientMock({}),
  });
}

test('health indicators become readable lines; offline is critical', () => {
  const status = loadDeviceStatus();
  const since = new Date(Date.now() - 2 * 3600_000).toISOString();
  const lines = status.deviceHealthLines({ offline: true, offline_since: since, last_fix_at: null,
    needs_attention: ['low_battery'] });
  assert.match(lines[0].label, /^Offline since about 2 hours ago$/);
  assert.equal(lines[0].critical, true);
  assert.deepEqual(lines[1], { label: 'Low battery (≤ 25 %)', critical: false });
  assert.deepEqual(status.deviceHealthLines({ offline: true, offline_since: null, last_fix_at: null, needs_attention: [] }),
    [{ label: 'Never reported', critical: true }]);
  assert.match(status.collarHealthSuffix({ offline: true, offline_since: since, last_fix_at: null, needs_attention: [] }),
    /^ · offline about 2 hours ago$/);
  assert.equal(status.collarHealthSuffix({ offline: false, offline_since: null, last_fix_at: null,
    needs_attention: ['no_gps_fix'] }), ' · needs attention');
  assert.equal(status.collarHealthSuffix(null), '');
});

test('device picker lists free collars and the animal\'s own collar only', () => {
  const status = loadDeviceStatus();
  const devices = [{ id: 'FREE' }, { id: 'MINE', assigned_animal: { id: 7 } }, { id: 'OTHER', assigned_animal: { id: 8 } }];
  assert.deepEqual(status.assignableDevices(devices, 7).map((d) => d.id), ['FREE', 'MINE']);
  assert.deepEqual(status.assignableDevices(devices, undefined).map((d) => d.id), ['FREE']);
  assert.deepEqual(status.assignableDevices(undefined, 7), []);
});

test('device_config.py lines use the firmware variable names', () => {
  assert.equal(loadDeviceStatus().deviceConfigLines('SIM-002', 101, 'ab'.repeat(32)),
    `DEVICE_ID = "SIM-002"\nTRANSPORT_ID = 101\nDEVICE_SECRET = "${'ab'.repeat(32)}"`);
});

test('adding a device shows the secret once, as text and QR code, then forgets it', async () => {
  const native = nativeMock();
  native.Share = { share: mock.fn(async () => ({})) };
  const secret = 'cd'.repeat(32);
  const create = mock.fn(async (payload) => ({ id: payload.device_id, farm_id: 17, transport_id: 103,
    device_secret: secret, status: 'active', last_seen: null, battery_capacity: null }));
  const qrValues = [];
  const onClose = mock.fn();
  const Component = loadTypeScript(path.join(SRC, 'components/AddDeviceModal.tsx'), {
    ...sharedUiOverrides(native),
    '@expo/vector-icons': { Ionicons: 'Ionicons' },
    'react-native-qrcode-svg': { __esModule: true, default: ({ value }) => { qrValues.push(value); return null; } },
    '../hooks/useDevices': { useCreateDevice: () => ({ mutateAsync: create, isPending: false }) },
    '../api/client': clientMock({}),
  }).default;
  const renderer = await mount(React.createElement(Component, { visible: true, farmId: 17, farmName: 'Test Farm A', onClose }));
  assert.match(textOf(renderer), /Into farm:\s+Test Farm A/);
  await act(async () => renderer.root.findByType('TextInput').props.onChangeText('sim-002'));
  const press = async (label) => {
    const button = buttonsLabelled(renderer.root, label).at(-1);
    await act(async () => button.props.onPress());
  };
  await press('Add device');
  assert.deepEqual(create.mock.calls[0].arguments[0], { device_id: 'SIM-002', farm_id: 17 });
  const text = textOf(renderer);
  assert.match(text, /This secret is shown only once. Copy it now./);
  assert.match(text, new RegExp(secret));
  assert.match(text, /DEVICE_SECRET = /);
  assert.equal(qrValues.at(-1), `DEVICE_ID = "SIM-002"\nTRANSPORT_ID = 103\nDEVICE_SECRET = "${secret}"`);
  await press('Share');
  assert.equal(native.Share.share.mock.calls[0].arguments[0].message, qrValues.at(-1));
  await press('I copied it');
  assert.equal(onClose.mock.callCount(), 1);
  assert.doesNotMatch(textOf(renderer), new RegExp(secret), 'the secret is gone once the dialog is closed');
});

// ── 3.6 transfer ────────────────────────────────────────────────────────────

test('the transfer confirmation names both farms, the collar and the visibility rule', () => {
  const { transferMessage } = loadTypeScript(path.join(SRC, 'components/TransferAnimalModal.tsx'), {
    ...sharedUiOverrides(nativeMock()), '../api/client': clientMock({}),
  });
  assert.equal(transferMessage('Bella', 'Test Farm A', 'Test Farm B', 'SIM-001'),
    'Transfer Bella from Test Farm A to Test Farm B? Collar SIM-001 moves with it. Test Farm B will see its health history, not its past locations.');
  assert.equal(transferMessage('Bella', 'Test Farm A', 'Test Farm B', null),
    'Transfer Bella from Test Farm A to Test Farm B? Test Farm B will see its health history, not its past locations.');
});

test('the transfer is sent only after confirmation, to the chosen farm', async () => {
  const native = nativeMock();
  const client = clientMock({});
  client.default.post = mock.fn(async () => ({ data: {} }));
  const onTransferred = mock.fn();
  const Component = loadTypeScript(path.join(SRC, 'components/TransferAnimalModal.tsx'), {
    ...sharedUiOverrides(native), '../api/client': client,
  }).default;
  const renderer = await mount(React.createElement(Component, {
    visible: true, animal: { id: 9, name: 'Bella', farm_id: 1, assigned_device: 'SIM-001' },
    farms: [{ id: 1, name: 'Test Farm A' }, { id: 2, name: 'Test Farm B' }],
    onClose: () => {}, onTransferred,
  }));
  const targetNames = renderer.root.findAllByType('TouchableOpacity')
    .flatMap((b) => b.findAllByType('Text').map((t) => t.props.children));
  assert.ok(!targetNames.includes('Test Farm A'), 'the current farm is not a target');
  const target = renderer.root.findAllByType('TouchableOpacity')
    .find((b) => b.findAllByType('Text').some((t) => t.props.children === 'Test Farm B'));
  await act(async () => target.props.onPress());
  assert.equal(client.default.post.mock.callCount(), 0);
  const [, , choices] = native.Alert.alert.mock.calls.at(-1).arguments;
  await act(async () => choices[1].onPress());
  assert.deepEqual(client.default.post.mock.calls[0].arguments, ['/animals/9/transfer', { target_farm_id: 2 }]);
  assert.equal(onTransferred.mock.callCount(), 1);
});
