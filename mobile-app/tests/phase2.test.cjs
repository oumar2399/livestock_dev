/* global __dirname */
// Phase 2 regression tests (acceptance test 2026-10-07): A1 invite target, A3 stale
// animal polling, A4 collar vs animal status, A6 error dialogs.
const assert = require('node:assert/strict');
const fs = require('node:fs');
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
const policy = loadTypeScript(path.join(SRC, 'api/queryPolicy.ts'), { './client': api });
const helpers = loadTypeScript(path.join(SRC, 'utils/helpers.ts'));

function nativeMock() {
  const native = Object.fromEntries(
    ['View', 'Text', 'TouchableOpacity', 'ScrollView', 'TextInput', 'ActivityIndicator'].map((n) => [n, n]));
  native.StyleSheet = { create: (styles) => styles };
  native.Alert = { alert: mock.fn() };
  native.Modal = ({ visible, children }) => (visible ? React.createElement('Modal', null, children) : null);
  native.FlatList = ({ data, renderItem, keyExtractor }) => React.createElement('List', null,
    (data ?? []).map((item) => React.createElement(React.Fragment, { key: keyExtractor(item) }, renderItem({ item }))));
  return native;
}

const textOf = (renderer) => renderer.root.findAllByType('Text')
  .map((node) => node.props.children).flat(Infinity).join('');

// ── A1: invitations say which farm they target and ask first ────────────────

async function renderUsers() {
  const native = nativeMock();
  const client = {
    __esModule: true,
    default: {
      get: mock.fn(async () => ({ data: { members: [] } })),
      post: mock.fn(async () => ({ data: {} })),
      patch: mock.fn(), delete: mock.fn(),
    },
    ApiError: api.ApiError, NetworkError: api.NetworkError,
  };
  const farmState = {
    currentFarmId: 17,
    farms: [{ id: 17, name: 'Test Farm A', membership_role: 'owner', permissions: ['invite_members'] }],
  };
  const Component = loadTypeScript(path.join(SRC, 'screens/drawer/UsersScreen.tsx'), {
    ...sharedUiOverrides(native),
    '@expo/vector-icons': { Ionicons: 'Ionicons' },
    './DrawerScreenBase': {
      __esModule: true,
      default: ({ children, title, subtitle, rightAction }) =>
        React.createElement('Screen', null, React.createElement('Text', null, title),
          React.createElement('Text', null, subtitle), rightAction, children),
    },
    '../../store/authStore': { useAuthStore: () => ({ isAdmin: () => false }) },
    '../../store/farmStore': { useFarmStore: () => farmState },
    '../../api/client': client,
    '../api/client': client,
  }).default;
  let renderer;
  await act(async () => { renderer = create(React.createElement(Component)); });
  mounted.push(renderer);
  return { renderer, native, client };
}

test('Users screen names the target farm and confirms before inviting', async () => {
  const { renderer, native, client } = await renderUsers();
  assert.match(textOf(renderer), /Test Farm A · 0 members/);
  const buttons = () => renderer.root.findAllByType('TouchableOpacity');
  await act(async () => buttons()[0].props.onPress());  // header "add member"
  assert.match(textOf(renderer), /Into farm: Test Farm A/);
  const email = renderer.root.findAllByType('TextInput').find((n) => n.props.placeholder === 'email@example.com');
  await act(async () => email.props.onChangeText('vet@example.com'));
  // Invite is both at the top right and at the bottom of the form (Phase 4); the bottom one here.
  assert.equal(buttonsLabelled(renderer.root, 'Invite').length, 2);
  const invite = buttonsLabelled(renderer.root, 'Invite').at(-1);
  await act(async () => invite.props.onPress());

  const [title, message, choices] = native.Alert.alert.mock.calls.at(-1).arguments;
  assert.equal(title, 'Confirm invitation');
  assert.equal(message, 'Invite vet@example.com as Veterinarian into Test Farm A?');
  assert.equal(client.default.post.mock.callCount(), 0, 'nothing is sent before confirmation');
  assert.equal(choices[0].text, 'Cancel');
  await act(async () => choices[1].onPress());
  assert.equal(client.default.post.mock.callCount(), 1);
  assert.equal(client.default.post.mock.calls[0].arguments[0], '/farms/17/members');
  assert.equal(client.default.post.mock.calls[0].arguments[1].role, 'vet');
});

// ── A1: farm-scoped tabs with no farm selected ──────────────────────────────

function loadWithFarm(state) {
  const dispatch = mock.fn();
  const module = loadTypeScript(path.join(SRC, 'components/RequireFarm.tsx'), {
    '@react-navigation/native': {
      DrawerActions: { openDrawer: () => ({ type: 'OPEN_DRAWER' }) },
      useNavigation: () => ({ dispatch }),
    },
    '../store/farmStore': { useFarmStore: () => state },
    './ui': {
      EmptyState: (props) => React.createElement('Empty', props),
      LoadingState: (props) => React.createElement('Loading', props),
    },
  });
  return { withFarm: module.withFarm, dispatch };
}

test('farm-scoped screens ask for a farm instead of loading data when none is selected', async () => {
  const Inner = () => React.createElement('Text', null, 'herd data');
  const { withFarm, dispatch } = loadWithFarm({ currentFarmId: null, isLoading: false });
  let renderer;
  await act(async () => { renderer = create(React.createElement(withFarm(Inner))); });
  mounted.push(renderer);
  const empty = renderer.root.findByType('Empty');
  assert.equal(empty.props.title, 'No farm selected');
  assert.equal(renderer.root.findAllByType(Inner).length, 0);
  empty.props.action.onPress();
  assert.deepEqual(dispatch.mock.calls[0].arguments[0], { type: 'OPEN_DRAWER' });

  const selected = loadWithFarm({ currentFarmId: 17, isLoading: false });
  await act(async () => { renderer = create(React.createElement(selected.withFarm(Inner))); });
  mounted.push(renderer);
  assert.equal(renderer.root.findAllByType(Inner).length, 1);
});

// ── A3: a deleted animal is not polled forever ──────────────────────────────

test('4xx answers are not retried; network and server errors are', () => {
  assert.equal(policy.retryUnlessClientError(0, new api.ApiError(404, 'Animal not found')), false);
  assert.equal(policy.retryUnlessClientError(0, new api.ApiError(403, 'Access denied')), false);
  assert.equal(policy.retryUnlessClientError(0, new api.ApiError(503, 'down')), true);
  assert.equal(policy.retryUnlessClientError(1, new api.NetworkError()), true);
  assert.equal(policy.retryUnlessClientError(2, new api.NetworkError()), false);
});

test('polling stops after a 403/404 and continues otherwise', () => {
  const interval = policy.pollUnlessGone(10_000);
  const query = (error) => ({ state: { error } });
  assert.equal(interval(query(new api.ApiError(404, 'Animal not found'))), false);
  assert.equal(interval(query(new api.ApiError(403, 'Access denied'))), false);
  assert.equal(interval(query(new api.ApiError(500, 'boom'))), 10_000);
  assert.equal(interval(query(null)), 10_000);
});

test('no screen goes back to the herd list by pushing a new one', () => {
  const screens = [];
  const walk = (dir) => fs.readdirSync(dir, { withFileTypes: true }).forEach((entry) => {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) walk(full);
    else if (entry.name.endsWith('.tsx')) screens.push(full);
  });
  walk(path.join(SRC, 'screens'));
  const offenders = screens.filter((file) => /navigate\(\s*['"]AnimalsList['"]\s*\)/.test(fs.readFileSync(file, 'utf8')));
  assert.deepEqual(offenders, []);
});

// ── A4: collar status shown apart from the animal status ────────────────────

test('collar labels never reuse the animal status words', () => {
  assert.equal(helpers.collarStatus('maintenance').label, 'Collar in maintenance');
  assert.equal(helpers.collarStatus('lost').label, 'Collar lost');
  assert.equal(helpers.collarStatus('retired').label, 'Collar retired');
  assert.equal(helpers.collarStatus('active').label, 'Collar active');
  assert.equal(helpers.collarStatus(null).label, 'Collar unknown');
});

test('the farm device list wins over telemetry for the collar status', () => {
  const devices = [{ id: 'SIM-001', status: 'maintenance' }];
  assert.equal(helpers.animalCollarStatus('SIM-001', devices, 'active').label, 'Collar in maintenance');
  assert.equal(helpers.animalCollarStatus('M5-1', devices, 'lost').label, 'Collar lost');
  assert.equal(helpers.animalCollarStatus(null, devices, 'active').label, 'No collar');
});

test('map markers follow the collar status', () => {
  assert.deepEqual(helpers.collarMarkerStyle('maintenance', '#2ECC71'),
    { color: '#7F8C8D', dashed: false, badge: 'maintenance', opacity: 1 });
  assert.deepEqual(helpers.collarMarkerStyle('lost', '#2ECC71'),
    { color: '#E74C3C', dashed: true, badge: 'lost', opacity: 1 });
  assert.equal(helpers.collarMarkerStyle('retired', '#2ECC71').opacity, 0.5);
  assert.equal(helpers.collarMarkerStyle('active', '#2ECC71').color, '#2ECC71');
  assert.equal(helpers.collarMarkerLabel('SIM-001', 'lost'), 'Collar SIM-001 — lost');
});

// ── A6: error dialogs with a clear title and the server's reason ────────────

test('error titles say what happened and keep the server reason', () => {
  const errors = loadTypeScript(path.join(SRC, 'utils/apiErrors.ts'), {
    '../api/client': api, '../components/dialog': { showDialog: mock.fn() },
  });
  const ownRole = new api.ApiError(403, 'You cannot change your own role.');
  assert.equal(errors.apiErrorTitle(ownRole, 'Could not change role'), 'Not allowed');
  assert.equal(errors.apiErrorMessage(ownRole, 'x'), 'You cannot change your own role.');
  assert.equal(errors.apiErrorTitle(new api.ApiError(404, 'Animal not found'), 'x'), 'Not found');
  assert.equal(errors.apiErrorTitle(new api.ApiError(422, 'bad'), 'x'), 'Could not save');
  assert.equal(errors.apiErrorTitle(new api.ApiError(409, 'dup'), 'x'), 'Conflict');
  assert.equal(errors.apiErrorTitle(new api.NetworkError(), 'x'), 'No connection');
  assert.equal(errors.apiErrorTitle(new Error('?'), 'Could not save'), 'Could not save');
  assert.notEqual(errors.apiErrorTitle(new Error('?'), 'Could not save'), 'Error');
});

test('FastAPI validation errors become a readable reason', () => {
  assert.equal(api.validationMessage([
    { loc: ['body', 'user_email'], msg: 'value is not a valid email address' },
    { loc: ['body', 'role'], msg: 'String should match pattern' },
  ]), 'user_email: value is not a valid email address; role: String should match pattern');
  assert.equal(api.validationMessage('plain'), null);
});
