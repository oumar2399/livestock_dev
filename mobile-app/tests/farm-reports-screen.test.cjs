/* global __dirname */
const assert = require('node:assert/strict');
const path = require('node:path');
const { afterEach, mock, test } = require('node:test');
const React = require('react');
const { act, create } = require('react-test-renderer');
const { loadTypeScript } = require('./helpers/load-typescript.cjs');
const { buttonsLabelled, sharedUiOverrides } = require('./helpers/shared-ui.cjs');

global.IS_REACT_ACT_ENVIRONMENT = true;
const mounted = [];
afterEach(async () => {
  for (const renderer of mounted.splice(0)) {
    await act(async () => renderer.unmount());
  }
});

async function harness(options = {}) {
  const state = {
    role: options.role || 'farmer',
    membershipRole: options.membershipRole || 'owner',
    currentFarmId: options.currentFarmId !== undefined ? options.currentFarmId : 1,
    overview: options.overview || {
      farm_id: 1,
      farm_name: 'Ferme Test',
      generated_at: '2026-09-22T10:00:00Z',
      target_timezone: 'Asia/Tokyo',
      current_state: {
        generated_at: '2026-09-22T10:00:00Z',
        total_animals: 5,
        animals_by_status: { active: 5 },
        total_devices: 5,
        devices_by_status: { active: 5 },
        assigned_devices_count: 5,
        unassigned_devices_count: 0,
        last_reception: { freshness_status: 'recent', age_seconds: 120 },
        gps_freshness: { status: 'active_fix', age_seconds: 120, satellites: 8 },
        battery_summary: { min_pct: 80, avg_pct: 88, low_battery_count: 0, monitored_devices_count: 5 },
        active_alerts_count: 0,
      },
      period_summary: {
        date_from: '2026-09-15',
        date_to: '2026-09-22',
        effective_start: '2026-09-14T15:00:00Z',
        effective_end: '2026-09-22T10:00:00Z',
        scope_status: 'available',
        dated_windows_count: 1200,
        proven_tracking_seconds: 86400,
        dated_coverage_seconds: 43200,
        dated_coverage_ratio: 0.5,
        behavioral_coverage_seconds: 40000,
        behavioral_coverage_ratio: 0.463,
        behavior_breakdown: { active_count: 600, resting_count: 600, active_ratio: 0.5, label: 'share of observed classified windows' },
        gps_presence_ratio: 0.95,
        behavioral_exclusions: {},
        reception_delay: { median_seconds: 2.1, p95_seconds: 4.5, negative_anomalies_count: 0 },
        unobserved_gaps: { gap_count: 1, longest_gap_seconds: 420.0, total_unobserved_seconds: 420.0 },
        alerts_triggered_in_period: 2,
        alerts_resolved_in_period: 2,
        limitations: [
          'The activity share represents the share of observed classified windows and not a total time over 24h.',
          'Data without historical proof of attachment to the farm is excluded from this summary.',
        ],
      },
      untimed_summary: {
        untimed_count: 12,
        breakdown_by_reason: {},
        breakdown_by_attribution: {},
        mandatory_label: 'Archives received by collars attached to this farm at reception',
      },
    },
    preview: options.preview || {
      farm_id: 1,
      dataset: 'farm_summary',
      date_from: '2026-09-15',
      date_to: '2026-09-22',
      generated_at: '2026-09-22T10:00:00Z',
      target_timezone: 'Asia/Tokyo',
      columns: ['Metric', 'Value', 'Unit', 'Status', 'Temporal Basis', 'Notes'],
      rows: [
        ['Dated Windows', '1200', 'windows', 'available', '2026-09-15 to 2026-09-22', 'Strictly proven windows'],
      ],
      total_rows: 1,
      has_more: false,
      limit: 20,
    },
    exportReport: mock.fn(async () => 'farm_report.csv'),
  };

  const native = Object.fromEntries(
    ['View', 'Text', 'TouchableOpacity', 'ScrollView', 'TextInput', 'ActivityIndicator'].map((name) => [name, name])
  );
  native.StyleSheet = { create: (styles) => styles };
  native.Alert = { alert: mock.fn() };

  const Component = loadTypeScript(path.resolve(__dirname, '../src/screens/drawer/FarmReportsScreen.tsx'), {
    ...sharedUiOverrides(native),
    '@expo/vector-icons': { Ionicons: 'Ionicons' },
    './DrawerScreenBase': {
      __esModule: true,
      default: ({ children, title }) => React.createElement('Screen', { title }, children),
    },
    '../../components/ReportPreviewTable': {
      __esModule: true,
      default: (props) => React.createElement('PreviewTable', props),
    },
    '../../store/authStore': {
      useAuthStore: (selector) => selector({ role: state.role }),
    },
    '../../store/farmStore': {
      useFarmStore: (selector) => {
        const full = {
          currentFarmId: state.currentFarmId,
          farms: state.currentFarmId ? [{ id: state.currentFarmId, name: 'Ferme Alpha', role: state.membershipRole }] : [],
        };
        return typeof selector === 'function' ? selector(full) : full;
      },
    },
    '../../utils/selectedFarmRole': {
      selectedFarmRole: () => (state.role === 'admin' ? 'admin' : state.membershipRole),
    },
    '../../hooks/useFarmReports': {
      useFarmOverview: () => ({
        data: state.overview,
        isLoading: false,
        isError: false,
        error: null,
      }),
      useFarmReportPreview: () => ({
        data: state.preview,
        isLoading: false,
        isError: false,
        error: null,
      }),
      useFarmReportExport: () => ({
        isPending: false,
        mutateAsync: state.exportReport,
      }),
    },
  }).default;

  let renderer;
  await act(async () => {
    renderer = create(React.createElement(Component));
  });
  mounted.push(renderer);

  const host = (type) => renderer.root.findAllByType(type);
  const text = () => host('Text').map((node) => node.props.children).flat(Infinity).join(' ');

  return { state, renderer, host, text };
}

test('shows "No Farm Selected" if currentFarmId is null', async () => {
  const h = await harness({ currentFarmId: null });
  assert.match(h.text(), /No Farm Selected/);
  assert.match(h.text(), /Please select a farm from the drawer/);
});

test('shows "Owner Access Required" if user is a standard farmer without owner rights', async () => {
  const h = await harness({ role: 'farmer', membershipRole: 'farmer' });
  assert.match(h.text(), /Owner Access Required/);
  assert.match(h.text(), /reserved for farm owners and administrators/);
});

test('renders complete overview, quality, untimed archives, and export for owner', async () => {
  const h = await harness({ role: 'farmer', membershipRole: 'owner' });

  const screenText = h.text();

  // Titres et sections
  assert.match(screenText, /Report Period/);
  assert.match(screenText, /Current Status/);
  assert.match(screenText, /Total Herd/);
  assert.match(screenText, /Collar Devices/);
  assert.match(screenText, /Period Coverage & Quality/);
  assert.match(screenText, /Dated Windows/);
  assert.match(screenText, /Active Behavior/);
  assert.match(screenText, /Transport & Reception Quality/);
  assert.match(screenText, /Methodological Notes/);

  // Archive v3 avec libellé obligatoire
  assert.match(screenText, /Untimed Archives \(v3\)/);
  assert.match(screenText, /12\s+windows/);
  assert.match(screenText, /Archives received by collars attached to this farm at reception/);

  // Tableau d'aperçu et bouton d'export
  assert.equal(h.host('PreviewTable').length, 1);
  assert.match(screenText, /Export\s+Summary\s+CSV/);
});
