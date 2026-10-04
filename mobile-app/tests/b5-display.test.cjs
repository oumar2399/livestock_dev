/* global __dirname */
const assert = require('node:assert/strict');
const path = require('node:path');
const { test } = require('node:test');
const { loadTypeScript } = require('./helpers/load-typescript.cjs');

const helpers = loadTypeScript(path.resolve(__dirname, '../src/utils/helpers.ts'));
const { eventVisual } = loadTypeScript(path.resolve(__dirname, '../src/utils/timelineVisuals.ts'));
const { entryTypeLabel } = loadTypeScript(path.resolve(__dirname, '../src/utils/veterinaryLabels.ts'));

const danger = (meta) => ({ type: 'geofence', alert_metadata: { sub_type: 'danger_zone_entry', ...meta } });

test('danger alert still inside shows only the last detection time', () => {
  const lines = helpers.dangerZonePresence(danger({ last_detected_inside_at: '2026-10-04T03:15:00+00:00', left_zone_at: null }));
  assert.equal(lines.length, 1);
  assert.match(lines[0], /^Last detected inside: /);
  assert.doesNotMatch(lines[0], /–/);
});

test('danger alert after leaving the zone says it is no longer detected inside', () => {
  const lines = helpers.dangerZonePresence(danger({
    last_detected_inside_at: '2026-10-04T03:15:00+00:00', left_zone_at: '2026-10-04T03:20:00+00:00',
  }));
  assert.equal(lines.length, 2);
  assert.match(lines[0], /^Last detected inside: /);
  assert.match(lines[1], /^No longer detected inside \(since .+\)$/);
});

test('presence lines only apply to danger-zone geofence alerts with metadata', () => {
  assert.deepEqual(helpers.dangerZonePresence({ type: 'geofence', alert_metadata: null }), []);
  assert.deepEqual(helpers.dangerZonePresence({ type: 'geofence', alert_metadata: { sub_type: 'pasture_exit', left_zone_at: 'x' } }), []);
  assert.deepEqual(helpers.dangerZonePresence({ type: 'battery', alert_metadata: { sub_type: 'danger_zone_entry', left_zone_at: 'x' } }), []);
  assert.deepEqual(helpers.dangerZonePresence(danger({})), []);
});

test('unknown battery is displayed as "Unknown", never "null" or a guessed value', () => {
  for (const level of [null, undefined, NaN, 255, -1]) {
    assert.equal(helpers.formatBattery(level), 'Unknown');
  }
  assert.equal(helpers.formatBattery(0), '0%');
  assert.equal(helpers.formatBattery(78), '78%');
});

test('timeline gives veterinary entries their own visual and never fails on a new type', () => {
  const vet = eventVisual('veterinary_entry');
  assert.equal(vet.icon, 'medkit-outline');
  const unknown = eventVisual('future_event_type');
  assert.equal(typeof unknown.icon, 'string');
  assert.equal(typeof unknown.color, 'string');
  assert.equal(eventVisual('toString').icon, unknown.icon);
  assert.equal(eventVisual('alert').icon, 'warning-outline');
});

test('veterinary journal header is readable for status_change entries', () => {
  assert.equal(entryTypeLabel('status_change'), 'STATUS CHANGE');
  assert.equal(entryTypeLabel('observation'), 'OBSERVATION');
});
