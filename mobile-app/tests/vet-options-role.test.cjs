/* global __dirname */
const assert = require('node:assert/strict');
const path = require('node:path');
const { afterEach, mock, test } = require('node:test');
const React = require('react');
const { act, create } = require('react-test-renderer');
const { loadTypeScript } = require('./helpers/load-typescript.cjs');

global.IS_REACT_ACT_ENVIRONMENT = true;
const mounted = [];
afterEach(async () => {
  for (const renderer of mounted.splice(0)) {
    await act(async () => renderer.unmount());
  }
});

// One account, two farms: vet in farm 1 (A), owner in farm 2 (B), farmer in farm 3 (C).
const FARMS = [
  { id: 1, name: 'Farm A', membership_role: 'vet', permissions: [] },
  { id: 2, name: 'Farm B', membership_role: 'owner', permissions: [] },
  { id: 3, name: 'Farm C', membership_role: 'farmer', permissions: [] },
];

const CASE = {
  id: 7, farm_id: 1, animal_id: 11, animal_name: 'Bella', title: 'Lameness',
  status: 'closed', opened_by: 4, opener_name: 'Vet', opened_at: '2026-10-01T08:00:00Z',
  entries_count: 1,
};

const DETAIL = {
  ...CASE,
  entries: [{
    id: 1, case_id: 7, author_name: 'Vet', entry_type: 'status_change',
    content: 'Status: provisional → closed',
    occurred_at: '2026-10-02T08:00:00Z', created_at: '2026-10-02T08:00:00Z',
  }],
};

async function render({ accountRole = 'vet', currentFarmId, caseFarmId = currentFarmId }) {
  // The case belongs to the viewed farm unless a test says otherwise (Phase 3 transfer).
  const caseRow = { ...CASE, farm_id: caseFarmId };
  const detailRow = { ...DETAIL, farm_id: caseFarmId };
  const native = Object.fromEntries(
    ['View', 'Text', 'TouchableOpacity', 'ScrollView', 'TextInput', 'ActivityIndicator'].map((name) => [name, name])
  );
  native.StyleSheet = { create: (styles) => styles };
  native.Alert = { alert: mock.fn() };
  native.Modal = ({ visible, children }) => (visible ? React.createElement('Modal', null, children) : null);

  const farmState = { farms: FARMS, currentFarmId, isLoading: false, error: null };
  // Flip saves.fail to make the next save reject (the screen then shows an error popup).
  const saves = { fail: false, calls: [] };
  const mutation = () => ({
    isPending: false,
    mutateAsync: async (variables) => {
      saves.calls.push(variables);
      if (saves.fail) throw new Error('Network down');
      return {};
    },
  });

  const Component = loadTypeScript(path.resolve(__dirname, '../src/screens/drawer/VetOptionsScreen.tsx'), {
    'react-native': native,
    '@expo/vector-icons': { Ionicons: 'Ionicons' },
    './DrawerScreenBase': {
      __esModule: true,
      default: ({ children, title, subtitle }) => React.createElement('Screen', { title, subtitle }, children),
    },
    '../../store/authStore': {
      useAuthStore: (selector) => selector({ role: accountRole }),
    },
    '../../store/farmStore': {
      useFarmStore: (selector) => (typeof selector === 'function' ? selector(farmState) : farmState),
    },
    '../../hooks/useVeterinary': {
      useFarmVeterinaryCases: () => ({ data: { total: 1, cases: [caseRow] }, isLoading: false, refetch: () => {} }),
      useVeterinaryCaseDetail: (id) => ({ data: id ? detailRow : undefined, isLoading: false }),
      useCreateVeterinaryCase: mutation,
      useUpdateVeterinaryCase: mutation,
      useAddCaseEntry: mutation,
    },
    '../../hooks/useAnimals': { useAnimals: () => ({ data: { animals: [{ id: 11, name: 'Bella' }] } }) },
  }).default;

  let renderer;
  await act(async () => { renderer = create(React.createElement(Component)); });
  mounted.push(renderer);

  const text = () => renderer.root.findAllByType('Text')
    .map((node) => node.props.children).flat(Infinity).join(' ');
  const openCase = async () => {
    const card = renderer.root.findAllByType('TouchableOpacity').find((node) =>
      node.findAll((child) => child.type === 'Text' && child.props.children === 'Lameness').length > 0);
    await act(async () => card.props.onPress());
  };
  const press = async (label) => {
    const button = renderer.root.findAllByType('TouchableOpacity').find((node) =>
      node.findAll((child) => child.type === 'Text' && [].concat(child.props.children).join('') === label).length > 0);
    assert.ok(button, `button "${label}" not found`);
    await act(async () => button.props.onPress());
  };
  const input = (placeholder) => renderer.root.findAllByType('TextInput')
    .find((node) => node.props.placeholder === placeholder);
  const type = async (placeholder, value) => {
    await act(async () => input(placeholder).props.onChangeText(value));
  };
  const modalOpen = () => renderer.root.findAllByType('Modal').length > 0;
  const subtitle = () => renderer.root.findByType('Screen').props.subtitle;
  return { text, subtitle, openCase, press, input, type, modalOpen, saves, alert: native.Alert.alert };
}

test('vet in farm A sees the write actions in farm A', async () => {
  const h = await render({ currentFarmId: 1 });
  assert.match(h.text(), /New case/);
  await h.openCase();
  assert.match(h.text(), /Add note/);
  assert.match(h.text(), /Change status:/);
});

test('the same account sees no write action in farm B where it is owner', async () => {
  const h = await render({ currentFarmId: 2 });
  assert.match(h.text(), /1\s+clinical case/);
  assert.doesNotMatch(h.text(), /New case/);
  await h.openCase();
  assert.match(h.text(), /Case journal/);
  assert.doesNotMatch(h.text(), /Add note/);
  assert.doesNotMatch(h.text(), /Change status:/);
});

// Phase 3: farmers read the cases and add observation notes only.
test('in farm C where it is farmer, the same account reads cases and only adds observations', async () => {
  const h = await render({ currentFarmId: 3 });
  assert.doesNotMatch(h.text(), /Restricted access/);
  assert.doesNotMatch(h.text(), /New case/);
  await h.openCase();
  assert.match(h.text(), /Add observation/);
  assert.doesNotMatch(h.text(), /Change status:/);
});

test('platform admin keeps write actions whatever the farm membership', async () => {
  const h = await render({ accountRole: 'admin', currentFarmId: 3 });
  assert.match(h.text(), /New case/);
});

test('status_change journal entries show a readable header and the status transition', async () => {
  const h = await render({ currentFarmId: 1 });
  await h.openCase();
  assert.match(h.text(), /STATUS CHANGE/);
  assert.doesNotMatch(h.text(), /STATUS_CHANGE/);
  assert.match(h.text(), /Status: provisional → closed/);
});

const TITLE = 'E.g. hoof examination, suspected cough...';
const INITIAL = 'Clinical observations made by the practitioner...';
const NOTE = 'Observation details, treatment given, recommendations...';

test('New case form is empty again after Cancel', async () => {
  const h = await render({ currentFarmId: 1 });
  await h.press('New case');
  await h.type(TITLE, 'Lameness check');
  await h.type(INITIAL, 'Limping on left foreleg');
  await h.press('Cancel');
  assert.equal(h.modalOpen(), false);
  await h.press('New case');
  assert.equal(h.input(TITLE).props.value, '');
  assert.equal(h.input(INITIAL).props.value, '');
});

test('New case form keeps the text after a failed save and is empty after a successful one', async () => {
  const h = await render({ currentFarmId: 1 });
  await h.press('New case');
  await h.press('Bella (#11)');
  await h.type(TITLE, 'Lameness check');
  await h.type(INITIAL, 'Limping on left foreleg');
  h.saves.fail = true;
  await h.press('Create case');
  assert.equal(h.alert.mock.calls.at(-1).arguments[0], 'Could not create case');
  assert.equal(h.modalOpen(), true);
  assert.equal(h.input(TITLE).props.value, 'Lameness check');
  assert.equal(h.input(INITIAL).props.value, 'Limping on left foreleg');

  h.saves.fail = false;
  await h.press('Create case');
  assert.equal(h.modalOpen(), false);
  await h.press('New case');
  assert.equal(h.input(TITLE).props.value, '');
  assert.equal(h.input(INITIAL).props.value, '');
});

test('Add note form is empty again after Cancel', async () => {
  const h = await render({ currentFarmId: 1 });
  await h.openCase();
  await h.press('Add note');
  await h.type(NOTE, 'Hoof cleaned');
  await h.press('Cancel');
  await h.press('Add note');
  assert.equal(h.input(NOTE).props.value, '');
});

test('Add note form keeps the text after a failed save and is empty after a successful one', async () => {
  const h = await render({ currentFarmId: 1 });
  await h.openCase();
  await h.press('Add note');
  await h.type(NOTE, 'Hoof cleaned');
  h.saves.fail = true;
  await h.press('Save');
  assert.equal(h.alert.mock.calls.at(-1).arguments[0], 'Could not add note');
  assert.equal(h.input(NOTE).props.value, 'Hoof cleaned');

  h.saves.fail = false;
  await h.press('Save');
  assert.equal(h.input(NOTE), undefined);
  await h.press('Add note');
  assert.equal(h.input(NOTE).props.value, '');
});

// Phase 2 (A2): an invited vet has account role "farmer" and farm role "vet".
test('an invited vet (account role farmer) gets the write actions and sees its role', async () => {
  const h = await render({ accountRole: 'farmer', currentFarmId: 1 });
  assert.match(h.text(), /New case/);
  assert.match(h.subtitle(), /Your role in Farm A: Veterinarian/);
  await h.openCase();
  assert.match(h.text(), /Add note/);
  assert.match(h.text(), /Change status:/);
});

// Phase 3: owner and farmer add observation notes only; no entry-type picker.
test('a farmer adds an observation: no type picker, always sent as observation', async () => {
  const h = await render({ accountRole: 'farmer', currentFarmId: 3 });
  await h.openCase();
  await h.press('Add observation');
  assert.match(h.text(), /Add an Observation/);
  assert.doesNotMatch(h.text(), /Entry type/);
  await h.type(NOTE, 'Gave the morning dose');
  await h.press('Save');
  assert.deepEqual(h.saves.calls.at(-1).payload, { entry_type: 'observation', content: 'Gave the morning dose' });
});

// Phase 3: after a transfer, a case opened by the previous farm is read-only here.
test('a case opened by a previous farm is read-only, even for the vet', async () => {
  const h = await render({ currentFarmId: 1, caseFarmId: 2 });
  await h.openCase();
  assert.match(h.text(), /Opened by a previous farm — read only/);
  assert.doesNotMatch(h.text(), /Add note|Add observation/);
  assert.doesNotMatch(h.text(), /Change status:/);
});
