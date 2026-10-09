/* global __dirname */
// Phase 4 (acceptance test 2026-10-07, user experience): shared dialog and modal, keyboard
// handling, searchable picker.
const assert = require('node:assert/strict');
const path = require('node:path');
const { afterEach, mock, test } = require('node:test');
const React = require('react');
const { act, create } = require('react-test-renderer');
const { loadTypeScript } = require('./helpers/load-typescript.cjs');

global.IS_REACT_ACT_ENVIRONMENT = true;
const SRC = path.join(__dirname, '../src');
const mounted = [];
afterEach(async () => {
  for (const renderer of mounted.splice(0)) await act(async () => renderer.unmount());
});

async function mount(element) {
  let renderer;
  await act(async () => { renderer = create(element); });
  mounted.push(renderer);
  return renderer;
}

const textOf = (node) => node.findAllByType('Text').map((t) => t.props.children).flat(Infinity).join(' ');

function nativeMock() {
  const keyboardListeners = {};
  const host = (name) => (props) => React.createElement(name, props);
  const native = Object.fromEntries(['View', 'Text', 'ScrollView', 'Pressable', 'ActivityIndicator'].map((n) => [n, n]));
  native.TextInput = Object.assign(host('TextInput'), { State: { currentlyFocusedInput: () => null } });
  native.StyleSheet = { create: (styles) => styles, absoluteFill: {}, hairlineWidth: 1 };
  native.Platform = { OS: 'android' };
  native.Keyboard = {
    addListener: (event, handler) => {
      keyboardListeners[event] = handler;
      return { remove: () => { delete keyboardListeners[event]; } };
    },
  };
  native.Modal = ({ visible, children, ...props }) => (visible ? React.createElement('Modal', props, children) : null);
  native.FlatList = ({ data, renderItem, keyExtractor, ListEmptyComponent, ListHeaderComponent }) =>
    React.createElement('List', null, ListHeaderComponent ?? null,
      (data ?? []).length === 0 ? ListEmptyComponent ?? null
        : data.map((item) => React.createElement(React.Fragment, { key: keyExtractor(item) }, renderItem({ item }))));
  return { native, keyboardListeners };
}

// One module cache per test so AppModal, the dialog host and the picker share one dialog store.
function loadPhase4() {
  const { native, keyboardListeners } = nativeMock();
  const cache = new Map();
  const overrides = { 'react-native': native, '@expo/vector-icons': { Ionicons: 'Ionicons' } };
  const load = (file) => loadTypeScript(path.join(SRC, file), overrides, cache);
  return {
    native,
    keyboardListeners,
    dialog: load('components/dialog.tsx'),
    keyboard: load('components/KeyboardAwareForm.tsx'),
    AppModal: load('components/AppModal.tsx'),
    picker: load('components/SearchablePicker.tsx'),
  };
}

const buttonNamed = (node, label) => node.findAll((n) => n.type === 'Pressable'
  && n.findAllByType('Text').some((t) => t.props.children === label))[0];

// ── 4.3 Shared dialog ──────────────────────────────────────────────────────

test('showDialog without buttons shows a single OK, and dialogs queue in order', async () => {
  const { dialog } = loadPhase4();
  const renderer = await mount(React.createElement(dialog.DialogHost));
  await act(async () => {
    dialog.showDialog('Saved', 'The farm was updated.');
    dialog.showDialog('Second');
  });
  assert.match(textOf(renderer.root), /Saved The farm was updated\. OK/);
  await act(async () => buttonNamed(renderer.root, 'OK').props.onPress());
  assert.match(textOf(renderer.root), /Second/);
  assert.doesNotMatch(textOf(renderer.root), /Saved/);
});

test('a button closes its dialog before its action runs, so the action can open the next dialog', async () => {
  const { dialog } = loadPhase4();
  const renderer = await mount(React.createElement(dialog.DialogHost));
  const seen = [];
  await act(async () => dialog.showDialog('Delete zone', 'Sure?', [
    { text: 'Cancel', style: 'cancel' },
    { text: 'Delete', style: 'destructive', onPress: () => {
      seen.push(dialog.useDialogStore.getState().queue.length);
      dialog.showDialog('Unable to delete zone');
    } },
  ]));
  await act(async () => buttonNamed(renderer.root, 'Delete').props.onPress());
  assert.deepEqual(seen, [0], 'the confirmation is gone when the action runs');
  assert.match(textOf(renderer.root), /Unable to delete zone/);
});

test('Android back closes the dialog: Cancel when present, OK for a message, nothing chosen otherwise', async () => {
  const { dialog } = loadPhase4();
  const renderer = await mount(React.createElement(dialog.DialogHost));
  const cancel = mock.fn();
  const confirm = mock.fn();
  await act(async () => dialog.showDialog('Logout', 'Do you want to log out?', [
    { text: 'Cancel', style: 'cancel', onPress: cancel }, { text: 'Logout', onPress: confirm },
  ]));
  await act(async () => renderer.root.findByType('Modal').props.onRequestClose());
  assert.equal(cancel.mock.callCount(), 1);
  assert.equal(confirm.mock.callCount(), 0);
  assert.equal(renderer.root.findAllByType('Modal').length, 0, 'the dialog is closed');

  const choice = mock.fn();
  assert.equal(dialog.backButtonFor([{ text: 'Farmer', onPress: choice }, { text: 'Owner', onPress: choice }]), undefined);
  const ok = { text: 'OK' };
  assert.equal(dialog.backButtonFor([ok]), ok);
  assert.equal(dialog.dismissCurrentDialog(), false, 'nothing to close');
});

test('two buttons sit side by side with Cancel first; longer choice lists stack with Cancel last', () => {
  const { dialog } = loadPhase4();
  const short = dialog.arrangeButtons([{ text: 'Delete', style: 'destructive' }, { text: 'Cancel', style: 'cancel' }]);
  assert.equal(short.stacked, false);
  assert.deepEqual(short.buttons.map((b) => b.text), ['Cancel', 'Delete']);
  const long = dialog.arrangeButtons([{ text: 'Cancel', style: 'cancel' }, { text: 'Active' }, { text: 'Lost' }]);
  assert.equal(long.stacked, true);
  assert.deepEqual(long.buttons.map((b) => b.text), ['Active', 'Lost', 'Cancel']);
});

// ── 4.3 Shared modal ───────────────────────────────────────────────────────

test('AppModal: Close on the left, Save at the top right, footer kept at the bottom', async () => {
  const { AppModal } = loadPhase4();
  const onClose = mock.fn();
  const onSave = mock.fn();
  const renderer = await mount(React.createElement(AppModal.default, {
    visible: true, title: 'Invite member', onClose,
    primaryAction: { label: 'Save', onPress: onSave },
    footer: React.createElement(AppModal.ModalButton, { label: 'Save', onPress: onSave }),
  }, React.createElement('Text', null, 'Email')));
  const saves = renderer.root.findAll((n) => n.type === 'Pressable' && n.props.accessibilityLabel === 'Save');
  assert.equal(saves.length, 2, 'Save at the top right and at the bottom');
  await act(async () => saves[0].props.onPress());
  await act(async () => saves[1].props.onPress());
  assert.equal(onSave.mock.callCount(), 2);
  const close = renderer.root.find((n) => n.type === 'Pressable' && n.props.accessibilityLabel === 'Close');
  await act(async () => close.props.onPress());
  assert.equal(onClose.mock.callCount(), 1);
});

test('a disabled or busy header action cannot be pressed', async () => {
  const { AppModal } = loadPhase4();
  const renderer = await mount(React.createElement(AppModal.default, {
    visible: true, title: 'New zone', onClose: () => {},
    primaryAction: { label: 'Save', onPress: () => {}, disabled: true },
  }, null));
  const save = renderer.root.find((n) => n.type === 'Pressable' && n.props.accessibilityLabel === 'Save');
  assert.equal(save.props.disabled, true);
});

test('a dialog opened over an AppModal is drawn inside it; back closes the dialog, then the modal', async () => {
  const { dialog, AppModal } = loadPhase4();
  const onClose = mock.fn();
  const cancel = mock.fn();
  const renderer = await mount(React.createElement(React.Fragment, null,
    React.createElement(AppModal.default, { visible: true, title: 'Transfer Bella', onClose }, null),
    React.createElement(dialog.DialogHost)));
  await act(async () => dialog.showDialog('Confirm transfer', 'Transfer Bella?', [
    { text: 'Cancel', style: 'cancel', onPress: cancel }, { text: 'Transfer' },
  ]));
  const modals = renderer.root.findAllByType('Modal');
  assert.equal(modals.length, 1, 'no second native Modal on top of the open one');
  assert.match(textOf(modals[0]), /Confirm transfer/);

  await act(async () => modals[0].props.onRequestClose());
  assert.equal(cancel.mock.callCount(), 1, 'first back: the dialog is cancelled');
  assert.equal(onClose.mock.callCount(), 0);
  assert.doesNotMatch(textOf(renderer.root), /Confirm transfer/);
  await act(async () => renderer.root.findByType('Modal').props.onRequestClose());
  assert.equal(onClose.mock.callCount(), 1, 'second back: the modal closes');
});

test('closing an AppModal hands dialogs back to the root host', async () => {
  const { dialog, AppModal } = loadPhase4();
  const view = (visible) => React.createElement(React.Fragment, null,
    React.createElement(AppModal.default, { visible, title: 'Add device', onClose: () => {} }, null),
    React.createElement(dialog.DialogHost));
  const renderer = await mount(view(true));
  await act(async () => renderer.update(view(false)));
  assert.deepEqual(dialog.useDialogStore.getState().modalStack, []);
  await act(async () => dialog.showDialog('Device added'));
  assert.match(textOf(renderer.root.findByType('Modal')), /Device added/);
});

// ── 4.2 Keyboard ───────────────────────────────────────────────────────────

test('keyboard overlap is measured: 0 when the window was resized, the covered part otherwise', () => {
  const { keyboard } = loadPhase4();
  assert.equal(keyboard.keyboardOverlap(800, 500), 300, 'edge-to-edge: the keyboard covers 300');
  assert.equal(keyboard.keyboardOverlap(500, 500), 0, 'adjustResize: nothing to add');
  assert.equal(keyboard.keyboardOverlap(480, 500), 0);
});

test('the focused input is scrolled just above the visible bottom, keeping a tall field top visible', () => {
  const { keyboard } = loadPhase4();
  const frame = { top: 100, bottom: 500 };
  assert.equal(keyboard.revealDelta({ top: 200, bottom: 250 }, frame, 16), 0, 'already visible');
  assert.equal(keyboard.revealDelta({ top: 520, bottom: 568 }, frame, 16), 84, 'below: scroll down');
  assert.equal(keyboard.revealDelta({ top: 60, bottom: 110 }, frame, 16), -56, 'above: scroll up');
  assert.equal(keyboard.revealDelta({ top: 150, bottom: 700 }, frame, 16), 34, 'tall field: its top stays visible');
});

test('KeyboardAwareForm pads itself by the measured overlap and clears it when the keyboard hides', async () => {
  const { keyboard, keyboardListeners } = loadPhase4();
  // The test renderer has no native views: every View measures as a full 400 x 800 screen.
  let renderer;
  await act(async () => {
    renderer = create(React.createElement(keyboard.default, null, React.createElement('Text', null, 'Name')), {
      createNodeMock: () => ({ measureInWindow: (callback) => callback(0, 0, 400, 800) }),
    });
  });
  mounted.push(renderer);
  const padding = () => renderer.root.findAll((n) => n.type === 'View')[0].props.style[1].paddingBottom;
  assert.equal(padding(), 0);
  await act(async () => keyboardListeners.keyboardDidShow({ endCoordinates: { screenY: 500 } }));
  assert.equal(padding(), 300, 'Android edge-to-edge: the keyboard covers the bottom 300');
  await act(async () => keyboardListeners.keyboardDidHide({}));
  assert.equal(padding(), 0);
});

// ── 4.4 Searchable picker ──────────────────────────────────────────────────

const ANIMALS = [
  { id: 12, name: 'Hanako', official_id: 'JP-WAG-001', status: 'active' },
  { id: 7, name: 'Bella', official_id: null, status: 'sick' },
  { id: 31, name: 'Léa', official_id: 'CI-NDA-031', status: 'active' },
];

test('picker search matches name, ear tag and ID, ignoring case, accents and a leading #', () => {
  const { picker } = loadPhase4();
  const options = ANIMALS.map(picker.animalOption);
  const names = (query) => picker.filterOptions(options, query).map((o) => o.label);
  assert.deepEqual(names(''), ['Hanako', 'Bella', 'Léa']);
  assert.deepEqual(names('hana'), ['Hanako']);
  assert.deepEqual(names('wag-001'), ['Hanako']);
  assert.deepEqual(names('#7'), ['Bella']);
  assert.deepEqual(names('lea'), ['Léa']);
  assert.deepEqual(names('nobody'), []);
  assert.equal(options[0].detail, 'Ear tag JP-WAG-001 · ID 12 · Active');
});

test('choosing an animal in the picker sets the value and closes the list', async () => {
  const { picker } = loadPhase4();
  const onChange = mock.fn();
  const renderer = await mount(React.createElement(picker.default, {
    label: 'Animal', options: ANIMALS.map(picker.animalOption), value: null, onChange,
  }));
  assert.equal(renderer.root.findAllByType('Modal').length, 0);
  await act(async () => renderer.root.find((n) => n.type === 'Pressable' && /^Animal:/.test(n.props.accessibilityLabel)).props.onPress());
  const search = renderer.root.find((n) => n.props.accessibilityLabel === 'Search' && n.props.onChangeText);
  await act(async () => search.props.onChangeText('bel'));
  assert.doesNotMatch(textOf(renderer.root.findByType('Modal')), /Hanako/);
  await act(async () => buttonNamed(renderer.root.findByType('Modal'), 'Bella').props.onPress());
  assert.deepEqual(onChange.mock.calls[0].arguments, [7]);
  assert.equal(renderer.root.findAllByType('Modal').length, 0, 'the list closes after a choice');
});

test('the picker can offer a "none" row that clears the choice', async () => {
  const { picker } = loadPhase4();
  const onChange = mock.fn();
  const renderer = await mount(React.createElement(picker.default, {
    label: 'Collar', options: [{ value: 'SIM-001', label: 'SIM-001' }], value: 'SIM-001', onChange, clearLabel: 'No collar',
  }));
  await act(async () => renderer.root.find((n) => n.type === 'Pressable' && /^Collar:/.test(n.props.accessibilityLabel)).props.onPress());
  await act(async () => buttonNamed(renderer.root.findByType('Modal'), 'No collar').props.onPress());
  assert.deepEqual(onChange.mock.calls[0].arguments, [null]);
});

// ── 4.4 Collar picker ──────────────────────────────────────────────────────

test('a collar option shows its status and health, and matches its transport ID', () => {
  const { native } = nativeMock();
  const status = loadTypeScript(path.join(SRC, 'utils/deviceStatus.ts'), {
    'react-native': native, '../api/client': { __esModule: true, default: {} },
    '../components/dialog': { showDialog: () => {} },
  });
  const option = status.deviceOption({ id: 'SIM-001', status: 'maintenance', transport_id: 103,
    health: { offline: false, offline_since: null, last_fix_at: null, needs_attention: ['low_battery'] } });
  assert.deepEqual(option, { value: 'SIM-001', label: 'SIM-001', detail: 'Maintenance · needs attention', keywords: ['103'] });
});

// ── 4.1 Behaviour correction: stable code sent, English label shown ────────

test('corrections are sent as stable codes and shown with English labels', () => {
  const labels = loadTypeScript(path.join(SRC, 'utils/feedbackLabels.ts'));
  assert.deepEqual(labels.BEHAVIOR_CORRECTIONS.map((item) => item.code),
    ['active', 'resting', 'grazing', 'walking', 'lying', 'running']);
  assert.ok(labels.BEHAVIOR_CORRECTIONS.every((item) => /^[a-z]+$/.test(item.code) && item.code.length <= 50),
    'codes fit the backend column (free text, max 50)');
  assert.equal(labels.correctionLabel('grazing'), 'Grazing');
  assert.equal(labels.correctionLabel('resting'), 'Resting');
});

test('values stored before Phase 4 are read through the documented mapping, unknown ones as stored', () => {
  const labels = loadTypeScript(path.join(SRC, 'utils/feedbackLabels.ts'));
  assert.deepEqual(labels.LEGACY_CORRECTION_CODES, {
    'Active': 'active', 'Resting': 'resting', 'Grazing (Pâturage)': 'grazing',
    'Walking (Marche)': 'walking', 'Lying (Couché)': 'lying', 'Running (Course)': 'running',
  });
  assert.equal(labels.correctionCode('Lying (Couché)'), 'lying');
  assert.equal(labels.correctionLabel('Walking (Marche)'), 'Walking');
  assert.equal(labels.correctionLabel('Active'), 'Active');
  assert.equal(labels.correctionLabel('standing'), 'standing', 'an unknown value is shown as stored');
  assert.equal(labels.correctionLabel(null), '');
});

// ── 4.7 Report table: columns sized from their content ────────────────────

function loadTable() {
  const { native } = nativeMock();
  native.useWindowDimensions = () => ({ width: 390, height: 844 });
  const cache = new Map();
  return { native, table: loadTypeScript(path.join(SRC, 'components/ReportPreviewTable.tsx'),
    { 'react-native': native, '@expo/vector-icons': { Ionicons: 'Ionicons' } }, cache) };
}

test('a column is as wide as its header or longest value, between 72 and 220', () => {
  const { table } = loadTable();
  const widths = table.estimateColumnWidths(
    ['id', 'animal_name', 'message'],
    [['1', 'Bella', 'x'.repeat(80)], ['12', 'Hanako', 'short']],
  );
  assert.equal(widths[0], table.MIN_COLUMN_WIDTH, 'a short column keeps a usable minimum');
  assert.equal(widths[1], 97, 'animal_name: the header is the widest text (11 × 7 + 20)');
  assert.equal(widths[2], table.MAX_COLUMN_WIDTH, 'a long value is capped and wraps instead');
  assert.deepEqual(table.estimateColumnWidths(['date'], []), [table.MIN_COLUMN_WIDTH], 'no rows: header only');
});

test('a table narrower than the screen is stretched to its width, a wider one scrolls', () => {
  const { table } = loadTable();
  const stretched = table.fitToWidth([72, 128], 336);
  assert.ok(stretched[0] > 72 && stretched[1] > 128);
  assert.ok(table.INDEX_WIDTH + stretched[0] + stretched[1] <= 336, 'never wider than the space');
  assert.ok(table.INDEX_WIDTH + stretched[0] + stretched[1] >= 335, 'fills it (rounding aside)');
  assert.deepEqual(table.fitToWidth([200, 220, 180], 336), [200, 220, 180], 'too wide: unchanged, scrolls');
  assert.deepEqual(table.fitToWidth([100], 0), [100], 'before the first layout: unchanged');
});

test('the table uses the measured widths, wraps headers on two lines and opens a cell in full', async () => {
  const { table } = loadTable();
  const preview = { columns: ['animal_name', 'notes'], rows: [['Bella', 'Limping on the left foreleg since Monday']] };
  const renderer = await mount(React.createElement(table.default, { preview }));
  const headers = renderer.root.findAll((n) => n.type === 'Text' && n.props.numberOfLines === 2
    && ['animal_name', 'notes'].includes(n.props.children));
  assert.equal(headers.length, 2, 'headers wrap to two lines');
  const widths = table.estimateColumnWidths(preview.columns, preview.rows);
  assert.equal(headers[0].props.style[1].width, widths[0]);
  await act(async () => renderer.root.find((n) => n.type === 'View' && n.props.onLayout)
    .props.onLayout({ nativeEvent: { layout: { width: 600 } } }));
  const stretched = renderer.root.findAll((n) => n.type === 'Text' && n.props.children === 'animal_name')[0];
  assert.ok(stretched.props.style[1].width > widths[0], 'stretched once the available width is known');
  await act(async () => renderer.root.find((n) => n.type === 'Pressable' && /Row 1, notes/.test(n.props.accessibilityLabel)).props.onPress());
  assert.match(textOf(renderer.root.findByType('Modal')), /Limping on the left foreleg since Monday/);
});

// ── 4.5 Herd list ──────────────────────────────────────────────────────────

async function renderHerd() {
  const { native } = nativeMock();
  native.TouchableOpacity = 'TouchableOpacity';
  native.RefreshControl = 'RefreshControl';
  const animals = [
    { id: 1, farm_id: 17, name: 'Hanako', official_id: 'JP-001', species: 'bovine', breed: 'Wagyu', sex: 'F',
      birth_date: null, assigned_device: null, status: 'active', last_update: null },
    { id: 2, farm_id: 17, name: 'Bella', official_id: 'CI-002', species: 'bovine', breed: null, sex: 'F',
      birth_date: null, assigned_device: null, status: 'sick', last_update: null },
  ];
  const Component = loadTypeScript(path.join(SRC, 'screens/AnimalsListScreen.tsx'), {
    'react-native': native,
    '@expo/vector-icons': { Ionicons: 'Ionicons' },
    'react-native-safe-area-context': { useSafeAreaInsets: () => ({ top: 30, bottom: 0 }) },
    '@react-navigation/native': { useNavigation: () => ({ navigate() {}, dispatch() {} }), DrawerActions: { openDrawer: () => ({}) } },
    '../hooks/useAnimals': { useAnimals: () => ({ data: { total: 2, animals }, isLoading: false, isError: false,
      refetch() {}, isRefetching: false }) },
    '../hooks/useTelemetry': { useTelemetryLatest: () => ({ data: [] }) },
    '../hooks/useDevices': { useFarmDevices: () => ({ data: [] }) },
    '../utils/deviceStatus': { collarHealthSuffix: () => '' },
    '../store/farmStore': { useFarmStore: (selector) => selector({ currentFarmId: 17,
      farms: [{ id: 17, name: 'Test Farm A', permissions: ['edit_animals'] }] }) },
  }).default;
  const renderer = await mount(React.createElement(Component));
  const names = () => textOf(renderer.root).match(/Hanako|Bella/g) ?? [];
  const press = async (label) => act(async () => renderer.root.find((n) => n.props.accessibilityLabel === label
    && typeof n.props.onPress === 'function').props.onPress());
  return { renderer, names, press };
}

test('herd list: search sits behind an icon in the header; closing it clears the search', async () => {
  const h = await renderHerd();
  // The count is nested in the title Text: one line, not a second line under it.
  const title = h.renderer.root.find((n) => n.type === 'Text' && [].concat(n.props.children).includes('Herd'));
  assert.match(textOf(title), /·\s+2 animals/, 'count on the title line');
  assert.equal(h.renderer.root.findAll((n) => n.type === 'TextInput').length, 0, 'no search bar until asked');
  await h.press('Search animals');
  const input = () => h.renderer.root.find((n) => n.type === 'TextInput');
  assert.equal(input().props.autoFocus, true);
  await act(async () => input().props.onChangeText('ci-002'));
  assert.deepEqual(h.names(), ['Bella']);
  await h.press('Close search');
  assert.equal(h.renderer.root.findAll((n) => n.type === 'TextInput').length, 0);
  assert.deepEqual(h.names(), ['Hanako', 'Bella'], 'a closed search never filters the list');
});

test('herd list: one top safe area (from the header) and status filters on one scrolling row', async () => {
  const h = await renderHerd();
  const screen = h.renderer.root.findAll((n) => n.type === 'View')[0];
  assert.ok(![].concat(screen.props.style).some((style) => style && style.paddingTop), 'no second top inset');
  const filterRow = h.renderer.root.find((n) => n.type === 'ScrollView' && n.props.horizontal);
  assert.match(textOf(filterRow), /All Active Sick Sold Deceased/);
});

// ── A21 App & Server stays read-only ───────────────────────────────────────

async function renderAppServer(role) {
  const { native } = nativeMock();
  native.TouchableOpacity = 'TouchableOpacity';
  native.Linking = { openURL() {} };
  const query = { data: undefined, isLoading: true, isError: false, refetch() {} };
  const Component = loadTypeScript(path.join(SRC, 'screens/drawer/AppServSettings.tsx'), {
    'react-native': native,
    '@expo/vector-icons': { Ionicons: 'Ionicons' },
    './DrawerScreenBase': { __esModule: true, default: ({ children }) => React.createElement('Screen', null, children) },
    '../../hooks/useSystemStatus': { useSystemStatus: () => query, useDailyJobRuns: () => query,
      useRunDailyJobs: () => ({ mutateAsync: async () => {}, isPending: false }) },
    '../../store/authStore': { useAuthStore: (selector) => selector({ role, user: { email: 'a@example.com' }, logout() {} }) },
    '../../components/dialog': { showDialog() {} },
  }).default;
  return mount(React.createElement(Component));
}

test('App & Server says it is read-only; the admin is pointed to the admin actions', async () => {
  const admin = textOf((await renderAppServer('admin')).root);
  assert.match(admin, /Settings are read-only\. Admin actions below\./);
  assert.match(admin, /DAILY PIPELINE/);
  const farmer = textOf((await renderAppServer('farmer')).root);
  assert.match(farmer, /Settings are read-only\./);
  assert.doesNotMatch(farmer, /Admin actions|DAILY PIPELINE/);
});

test('no screen adds the top safe area again on top of ScreenHeader (which already adds it)', () => {
  const fs = require('node:fs');
  const files = [];
  const walk = (dir) => fs.readdirSync(dir, { withFileTypes: true }).forEach((entry) => {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) walk(full);
    else if (entry.name.endsWith('.tsx')) files.push(full);
  });
  walk(path.join(SRC, 'screens'));
  const offenders = files.filter((file) => {
    const source = fs.readFileSync(file, 'utf8');
    return source.includes('<ScreenHeader') && /paddingTop:\s*insets\.top\b/.test(source);
  }).map((file) => path.relative(SRC, file));
  assert.deepEqual(offenders, []);
  assert.ok(files.some((file) => fs.readFileSync(file, 'utf8').includes('<ScreenHeader')), 'the scan found ScreenHeader screens');
});
