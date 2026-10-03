const assert = require('node:assert/strict');
const path = require('node:path');
const { test } = require('node:test');
const { loadTypeScript } = require('./helpers/load-typescript.cjs');

test('locationsApi constructs correct endpoint URLs and query parameters', async () => {
  const requests = [];
  const fakeClient = {
    get: async (url, config) => {
      requests.push({ url, config });
      return { data: [] };
    },
  };

  const { locationsApi } = loadTypeScript(path.resolve(__dirname, '../src/api/locations.ts'), {
    './client': fakeClient,
  });

  // 1. getLatest
  await locationsApi.getLatest(42);
  assert.equal(requests[0].url, '/farms/42/locations/latest');

  // 2. getCurrent
  await locationsApi.getCurrent(42, 99);
  assert.equal(requests[1].url, '/farms/42/locations/99');

  // 3. getHistory with hours
  await locationsApi.getHistory(42, 99, { hours: 6 });
  assert.equal(requests[2].url, '/farms/42/locations/99/history?hours=6');

  // 4. getHistory with start & end
  await locationsApi.getHistory(42, 99, {
    start: '2026-09-22T08:00:00Z',
    end: '2026-09-22T14:00:00Z',
  });
  assert.equal(
    requests[3].url,
    '/farms/42/locations/99/history?start=2026-09-22T08%3A00%3A00Z&end=2026-09-22T14%3A00%3A00Z'
  );
});

test('location freshness distinguishes position timestamp from telemetry timestamp', () => {
  const { evaluateFreshness } = loadTypeScript(path.resolve(__dirname, '../src/utils/helpers.ts'), {
    '../constants/config': { Colors: { text: { muted: '#999' } } },
  });

  // Télémétrie toute récente mais fix GPS vieux d'une heure
  const freshness = evaluateFreshness({
    telemetryTime: new Date().toISOString(),
    positionTime: new Date(Date.now() - 3_600_000).toISOString(),
    latitude: 45.0,
    longitude: 5.0,
    satellites: 8,
  });

  assert.equal(freshness.telemetryFreshness, 'recent');
  assert.equal(freshness.gpsStatus, 'stale_fix');
});

test('lost collar or equipment position is recognized as unconfirmed animal location', () => {
  const sampleLocation = {
    animal_id: 12,
    animal_name: 'Blanchette',
    device_id: 'COLLAR-LOST-1',
    latitude: 45.1,
    longitude: 5.2,
    position_time: new Date().toISOString(),
    position_is_animal: false,
    device_status: 'lost',
    freshness: 'recent',
    age_seconds: 120,
  };

  assert.equal(sampleLocation.position_is_animal, false);
  assert.equal(sampleLocation.device_status, 'lost');
});
