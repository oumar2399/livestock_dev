const assert = require('node:assert/strict');
const path = require('node:path');
const { test } = require('node:test');
const { loadTypeScript } = require('./helpers/load-typescript.cjs');

test('new behavior data cannot make an old GPS fix recent', () => {
  const { evaluateFreshness } = loadTypeScript(path.resolve(__dirname, '../src/utils/helpers.ts'), {
    '../constants/config': { Colors: { text: { muted: '#999' } } },
  });
  const freshness = evaluateFreshness({
    telemetryTime: new Date().toISOString(),
    positionTime: new Date(Date.now() - 3_600_000).toISOString(),
    latitude: 5, longitude: 2, satellites: 8,
  });
  assert.equal(freshness.telemetryFreshness, 'recent');
  assert.equal(freshness.gpsStatus, 'stale_fix');
});

test('coordinates without a fix timestamp never reuse the telemetry timestamp', () => {
  const { evaluateFreshness } = loadTypeScript(path.resolve(__dirname, '../src/utils/helpers.ts'), {
    '../constants/config': { Colors: { text: { muted: '#999' } } },
  });
  const freshness = evaluateFreshness({ telemetryTime: new Date().toISOString(), latitude: 5, longitude: 2 });
  assert.equal(freshness.gpsStatus, 'stale_fix');
  assert.equal(freshness.gpsLabel, 'GPS time unknown');
});

function exportHarness() {
  let epoch = 1;
  let farm = 7;
  let sessionListener;
  let farmListener;
  let finish;
  const calls = { shares: 0, cancels: 0, deleted: [], checks: 0 };
  const pending = new Promise((resolve) => { finish = resolve; });
  const service = loadTypeScript(path.resolve(__dirname, '../src/api/farmReports.ts'), {
    '@react-native-async-storage/async-storage': { getItem: async () => 'token' },
    'expo-file-system/legacy': {
      cacheDirectory: '/cache/',
      createDownloadResumable: (_url, uri) => ({
        downloadAsync: async () => { await pending; return { status: 200, uri }; },
        cancelAsync: async () => { calls.cancels++; },
      }),
      deleteAsync: async (uri) => { calls.deleted.push(uri); },
    },
    'expo-sharing': { isAvailableAsync: async () => true, shareAsync: async () => { calls.shares++; } },
    '../constants/config': { Config: { STORAGE: { ACCESS_TOKEN: 'token' }, API_BASE_URL: 'http://test' } },
    './client': { get: async () => { calls.checks++; return {}; } },
    '../store/sessionLifecycle': {
      getSessionEpoch: () => epoch,
      onSessionChange: (listener) => { sessionListener = listener; return () => {}; },
    },
    '../store/farmStore': { useFarmStore: {
      getState: () => ({ currentFarmId: farm }),
      subscribe: (listener) => { farmListener = listener; return () => {}; },
    } },
    '../utils/uuid': { generateUUID: () => 'unique' },
  });
  return {
    calls, finish,
    run: () => service.downloadAndShareFarmReport({ farmId: 7, dataset: 'farm_summary', dateFrom: '2026-09-01', dateTo: '2026-09-02' }),
    logout: () => { epoch++; sessionListener(epoch); },
    switchFarm: () => { farm = 8; farmListener({ currentFarmId: farm }); },
  };
}

for (const action of ['logout', 'switchFarm']) {
  test(`export cancels on ${action}, never shares old data and cleans temporary file`, async () => {
    const h = exportHarness();
    const task = h.run();
    await new Promise(setImmediate);
    h[action]();
    h.finish();
    await assert.rejects(task, /cancelled/);
    assert.equal(h.calls.cancels, 1);
    assert.equal(h.calls.shares, 0);
    assert.equal(h.calls.deleted.length, 1);
  });
}

test('successful export rechecks access and removes its private temporary copy', async () => {
  const h = exportHarness();
  const task = h.run();
  h.finish();
  await task;
  assert.equal(h.calls.checks, 1);
  assert.equal(h.calls.shares, 1);
  assert.equal(h.calls.deleted.length, 1);
});

test('complete herd hook loads animals beyond the first 100', async () => {
  const pages = [];
  const module = loadTypeScript(path.resolve(__dirname, '../src/hooks/useAnimals.ts'), {
    '@tanstack/react-query': { useQuery: (options) => options },
    '../api/animals': { animalsApi: { list: async ({ page }) => {
      pages.push(page);
      return { total: 121, animals: Array.from({ length: page === 1 ? 100 : 21 }, (_, i) => ({ id: (page - 1) * 100 + i + 1 })) };
    } } },
    '../constants/config': { Config: {} },
    '../store/farmStore': { useFarmStore: (selector) => selector({ currentFarmId: 7 }) },
  });
  const query = module.useAnimals({}, undefined, true);
  const result = await query.queryFn({ signal: new AbortController().signal });
  assert.equal(result.animals.length, 121);
  assert.deepEqual(pages, [1, 2]);
});

test('complete telemetry hook advances a stable animal cursor past 100', async () => {
  const cursors = [];
  const module = loadTypeScript(path.resolve(__dirname, '../src/hooks/useTelemetry.ts'), {
    '@tanstack/react-query': { useQuery: (options) => options },
    '../api/telemetry': { telemetryApi: { getLatest: async ({ after_animal_id }) => {
      cursors.push(after_animal_id);
      return Array.from({ length: after_animal_id === 0 ? 100 : 21 }, (_, i) => ({ animal_id: after_animal_id + i + 1 }));
    } } },
    '../constants/config': { Config: {} },
    '../store/farmStore': { useFarmStore: (selector) => selector({ currentFarmId: 7 }) },
  });
  const query = module.useTelemetryLatest({}, undefined, true);
  const result = await query.queryFn({ signal: new AbortController().signal });
  assert.equal(result.length, 121);
  assert.deepEqual(cursors, [0, 100]);
});
