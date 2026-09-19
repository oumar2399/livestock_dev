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

async function harness(options = {}) {
  const state = {
    role: 'admin', rows: [['2026-09-01T00:00:00Z', '1', 'Farm 1']],
    columns: ['time_utc', 'farm_id', 'farm_name'], hasMore: false,
    fetching: false, loading: false, error: null, ...options,
  };
  const previewCalls = [];
  const refetch = mock.fn(async () => ({}));
  const exportReport = mock.fn(async () => 'report.csv');
  const native = Object.fromEntries(['View', 'Text', 'TouchableOpacity', 'ScrollView', 'TextInput',
    'ActivityIndicator'].map((name) => [name, name]));
  native.StyleSheet = { create: (styles) => styles };
  native.Alert = { alert: mock.fn() };
  const Component = loadTypeScript(path.resolve(__dirname, '../src/screens/drawer/ReportsScreen.tsx'), {
    'react-native': native,
    '@expo/vector-icons': { Ionicons: 'Ionicons' },
    './DrawerScreenBase': { __esModule: true,
      default: ({ children, ...props }) => React.createElement('Screen', props, children) },
    '../../components/ReportPreviewTable': { __esModule: true,
      default: (props) => React.createElement('PreviewTable', props) },
    '../../store/authStore': { useAuthStore: (selector) => selector({ role: state.role }) },
    '../../store/farmStore': { useFarmStore: (selector) => selector({ currentFarmId: 1,
      farms: [{ id: 1, name: 'Farm 1' }] }) },
    '../../hooks/useReports': {
      useReportPreview: (params, enabled) => {
        previewCalls.push({ params, enabled });
        return {
          data: state.error ? undefined : { dataset: params.dataset, columns: state.columns,
            rows: state.rows, has_more: state.hasMore, limit: 20, target_timezone: 'Asia/Tokyo',
            generated_at: '2026-09-05T00:00:00Z' },
          isFetching: state.fetching, isLoading: state.loading, isError: !!state.error,
          error: state.error, refetch,
        };
      },
      useReportExport: () => ({ isPending: false, mutateAsync: exportReport }),
    },
  }).default;
  let renderer;
  await act(async () => { renderer = create(React.createElement(Component)); });
  mounted.push(renderer);
  const host = (type) => renderer.root.findAllByType(type);
  const control = (label) => renderer.root.findAll((node) =>
    typeof node.type === 'string' && node.props.accessibilityLabel === label)[0];
  const text = () => host('Text').map((node) => node.props.children).flat(Infinity).join(' ');
  const change = async (label, value) => { await act(async () => control(label).props.onChangeText(value)); };
  const update = async () => { await act(async () => renderer.update(React.createElement(Component))); };
  return { state, previewCalls, refetch, exportReport, renderer, host, control, text, change, update };
}

test('loads a bounded preview automatically and enables export for its current filters', async () => {
  const h = await harness();
  assert.equal(h.previewCalls.at(-1).enabled, true);
  assert.equal(h.host('PreviewTable').length, 1);
  assert.equal(h.host('PreviewTable')[0].props.preview.limit, 20);
  assert.match(h.text(), /Data preview.*1 rows.*Asia\/Tokyo/);
  assert.equal(h.control('Export and share CSV').props.disabled, false);
  await act(async () => h.control('Export and share CSV').props.onPress());
  assert.equal(h.exportReport.mock.callCount(), 1);
  assert.equal(h.exportReport.mock.calls[0].arguments[0].farmId, 1);
});

test('hides stale rows while filters settle, then loads the matching preview', async () => {
  const h = await harness();
  await h.change('From date', '2026-08-01');
  assert.equal(h.previewCalls.at(-1).enabled, false);
  assert.equal(h.host('PreviewTable').length, 0);
  assert.equal(h.control('Export and share CSV').props.disabled, true);
  assert.match(h.text(), /Updating preview/);
  await act(async () => new Promise((resolve) => setTimeout(resolve, 650)));
  assert.equal(h.previewCalls.at(-1).enabled, true);
  assert.equal(h.previewCalls.at(-1).params.dateFrom, '2026-08-01');
  assert.equal(h.host('PreviewTable').length, 1);
  assert.equal(h.control('Export and share CSV').props.disabled, false);
});

test('invalid telemetry dates do not launch a preview or permit export', async () => {
  const h = await harness();
  await h.change('From date', 'not-a-date');
  assert.equal(h.previewCalls.at(-1).enabled, false);
  assert.match(h.text(), /Select a valid period.*Telemetry requires both dates/);
  assert.equal(h.host('PreviewTable').length, 0);
  assert.equal(h.control('Export and share CSV').props.disabled, true);
});

test('an empty preview is visible but cannot be exported', async () => {
  const h = await harness({ rows: [] });
  assert.match(h.text(), /0 rows.*No data for these filters/);
  assert.equal(h.control('Export and share CSV').props.disabled, true);
});

test('preview errors provide a retry without enabling export', async () => {
  const h = await harness({ error: new Error('Network unavailable') });
  assert.match(h.text(), /Preview unavailable.*Network unavailable/);
  assert.equal(h.control('Export and share CSV').props.disabled, true);
  await act(async () => h.control('Retry preview').props.onPress());
  assert.equal(h.refetch.mock.callCount(), 1);
});

test('non-admin users cannot request or export report data', async () => {
  const h = await harness({ role: 'farmer' });
  assert.match(h.text(), /Administrator access required/);
  assert.equal(h.previewCalls.length, 0);
  assert.equal(h.control('Export and share CSV'), undefined);
});

test('untimed archive uses reception dates and identical device filters for preview and export', async () => {
  const h = await harness();
  await act(async () => h.control('Untimed windows').props.onPress());
  assert.match(h.text(), /RECEPTION PERIOD.*Received from.*Received to/);
  assert.equal(h.host('Screen')[0].props.subtitle, 'Reception context: Farm 1');
  assert.equal(h.control('Device ID').props.maxLength, 50);
  await h.change('Device ID', ' COLLAR-1 ');
  await act(async () => new Promise((resolve) => setTimeout(resolve, 650)));
  const params = h.previewCalls.at(-1).params;
  assert.equal(params.dataset, 'untimed_telemetry');
  assert.equal(params.deviceId, 'COLLAR-1');
  await act(async () => h.control('Export and share CSV').props.onPress());
  assert.deepEqual(h.exportReport.mock.calls[0].arguments[0], params);
  await act(async () => h.control('Telemetry').props.onPress());
  await act(async () => new Promise((resolve) => setTimeout(resolve, 650)));
  assert.equal(h.previewCalls.at(-1).params.deviceId, undefined);
  assert.equal(h.control('Device ID'), undefined);
});

test('untimed archive requires both reception dates', async () => {
  const h = await harness();
  await act(async () => h.control('Untimed windows').props.onPress());
  await h.change('Received from date', '');
  assert.equal(h.previewCalls.at(-1).enabled, false);
  assert.equal(h.control('Export and share CSV').props.disabled, true);
  assert.match(h.text(), /Both reception dates are required/);
});
