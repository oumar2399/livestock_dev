/* global __dirname */
const assert = require('node:assert/strict');
const path = require('node:path');
const { test } = require('node:test');
const { loadTypeScript } = require('./helpers/load-typescript.cjs');
const { isMapPoint, mapAnimals, positionRecency, editablePoints, initialMapRegion, RECENT_POSITION_MS } =
  loadTypeScript(path.resolve(__dirname, '../src/utils/geofenceMap.ts'));

test('accepts geographic bounds and rejects malformed coordinates', () => {
  for (const point of [{ latitude: 0, longitude: 0 }, { latitude: -90, longitude: 180 }]) {
    assert.equal(isMapPoint(point), true);
  }
  for (const point of [
    { latitude: 91, longitude: 0 }, { latitude: 0, longitude: -181 },
    { latitude: NaN, longitude: 0 }, { latitude: 0, longitude: Infinity },
    { latitude: null, longitude: 0 }, { latitude: '', longitude: 0 },
  ]) assert.equal(isMapPoint(point), false);
});

test('keeps old fictional positions, filters invalid points and does not reorder the cache', () => {
  const records = [
    { animal_name: 'Zoe', latitude: 5, longitude: -4, last_update: '2020-01-01T00:00:00Z' },
    { animal_name: 'Ari', latitude: 35, longitude: 139 },
    { animal_name: 'Invalid', latitude: 1000, longitude: 0 },
  ];
  assert.deepEqual(mapAnimals(records).map((animal) => animal.animal_name), ['Ari', 'Zoe']);
  assert.equal(records[0].animal_name, 'Zoe');
});

test('uses a strict 30-minute freshness threshold without calling old data online', () => {
  const now = Date.parse('2026-09-05T03:00:00Z');
  assert.equal(positionRecency(new Date(now - RECENT_POSITION_MS + 1).toISOString(), now), 'recent');
  assert.equal(positionRecency(new Date(now - RECENT_POSITION_MS).toISOString(), now), 'old');
  assert.equal(positionRecency('2020-01-01T00:00:00Z', now), 'old');
  assert.equal(positionRecency('2026-09-05T11:59:00+09:00', now), 'recent');
  assert.equal(positionRecency('invalid', now), 'unknown');
  assert.equal(positionRecency(new Date(now + 1000).toISOString(), now), 'unknown');
});

test('opens a closed ring for editing without mutating saved zone geometry', () => {
  const ring = [{ latitude: 1, longitude: 1 }, { latitude: 2, longitude: 1 }, { latitude: 2, longitude: 2 }, { latitude: 1, longitude: 1 }];
  const points = editablePoints(ring);
  assert.equal(points.length, 3);
  points[0].latitude = 10;
  assert.equal(ring.length, 4);
  assert.equal(ring[0].latitude, 1);
  assert.equal(editablePoints(ring.slice(0, 3)).length, 3);
  assert.deepEqual(editablePoints([]), []);
});

test('initial framing uses real input coordinates and no fixed Tokyo location', () => {
  const region = initialMapRegion([{ latitude: 5.3, longitude: -4, animal_name: 'Ari' }]);
  assert.deepEqual(region, { latitude: 5.3, longitude: -4, latitudeDelta: 0.02, longitudeDelta: 0.02 });
  assert.equal(initialMapRegion([]).longitudeDelta, 300);
});
