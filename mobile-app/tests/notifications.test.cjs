const assert = require('node:assert/strict');
const path = require('node:path');
const { test } = require('node:test');
const { loadTypeScript } = require('./helpers/load-typescript.cjs');

test('notificationsApi makes expected HTTP requests', async () => {
  const requests = [];
  const fakeClient = {
    post: async (url, payload) => {
      requests.push({ method: 'POST', url, payload });
      return { data: { id: 1, ...payload, active: true } };
    },
    delete: async (url) => {
      requests.push({ method: 'DELETE', url });
      return { data: null };
    },
    get: async (url, config) => {
      requests.push({ method: 'GET', url, config });
      return { data: [] };
    },
    put: async (url, payload) => {
      requests.push({ method: 'PUT', url, payload });
      return { data: { id: 1, ...payload } };
    },
  };

  const {
    registerPushDevice,
    deactivatePushDevice,
    getNotificationPreferences,
    updateNotificationPreferences,
  } = loadTypeScript(path.resolve(__dirname, '../src/api/notifications.ts'), {
    './client': fakeClient,
  });

  // 1. Enregistrement d'un device
  const device = await registerPushDevice('ExponentPushToken[xyz123]', 'ios', 'expo');
  assert.equal(requests[0].method, 'POST');
  assert.equal(requests[0].url, '/notifications/devices');
  assert.equal(requests[0].payload.push_token, 'ExponentPushToken[xyz123]');
  assert.equal(requests[0].payload.platform, 'ios');
  assert.equal(device.active, true);

  // 2. Désactivation d'un device
  await deactivatePushDevice('ExponentPushToken[xyz123]');
  assert.equal(requests[1].method, 'DELETE');
  assert.equal(requests[1].url, '/notifications/devices/ExponentPushToken%5Bxyz123%5D');

  // 3. Lecture des préférences
  await getNotificationPreferences(42);
  assert.equal(requests[2].method, 'GET');
  assert.equal(requests[2].url, '/notifications/preferences');
  assert.deepEqual(requests[2].config.params, { farm_id: 42 });

  // 4. Mise à jour des préférences
  await updateNotificationPreferences({
    farm_id: 42,
    categories: ['geofence', 'health'],
    min_severity: 'warning',
    enabled: true,
  });
  assert.equal(requests[3].method, 'PUT');
  assert.equal(requests[3].url, '/notifications/preferences');
  assert.equal(requests[3].payload.min_severity, 'warning');
  assert.deepEqual(requests[3].payload.categories, ['geofence', 'health']);
});

test('notification category and severity client-side evaluation', () => {
  const categories = ['geofence', 'health', 'battery'];
  const minSeverity = 'warning';

  const severityRank = { info: 1, warning: 2, critical: 3 };

  const shouldNotify = (alertType, alertSeverity) => {
    if (!categories.includes(alertType)) return false;
    return severityRank[alertSeverity] >= severityRank[minSeverity];
  };

  // Info geofence -> filtré car < warning
  assert.equal(shouldNotify('geofence', 'info'), false);
  // Warning geofence -> accepté
  assert.equal(shouldNotify('geofence', 'warning'), true);
  // Critical health -> accepté
  assert.equal(shouldNotify('health', 'critical'), true);
  // Critical offline -> filtré car offline n'est pas dans categories
  assert.equal(shouldNotify('offline', 'critical'), false);
});
