const assert = require('node:assert/strict');
const path = require('node:path');
const { test } = require('node:test');
const { loadTypeScript } = require('./helpers/load-typescript.cjs');

function createAsyncStorageMock() {
  const store = new Map();
  return {
    getItem: async (key) => (store.has(key) ? store.get(key) : null),
    setItem: async (key, val) => {
      store.set(key, String(val));
    },
    removeItem: async (key) => {
      store.delete(key);
    },
    getAllKeys: async () => Array.from(store.keys()),
    multiRemove: async (keys) => {
      keys.forEach((k) => store.delete(k));
    },
    _raw: store,
  };
}

test('offlineCache enforces allowlist of read-only resources', async () => {
  const asyncStorageMock = createAsyncStorageMock();
  let currentEpoch = 1;

  const sessionLifecycleMock = {
    getSessionEpoch: () => currentEpoch,
    advanceSessionEpoch: () => ++currentEpoch,
    onSessionChange: () => () => {},
    withSessionStorage: (op) => op(),
  };

  const {
    saveToOfflineCache,
    loadFromOfflineCache,
    isResourceAllowlisted,
  } = loadTypeScript(path.resolve(__dirname, '../src/utils/offlineCache.ts'), {
    '@react-native-async-storage/async-storage': asyncStorageMock,
    '../store/sessionLifecycle': sessionLifecycleMock,
  });

  // 1. Types autorisés
  assert.equal(isResourceAllowlisted('animals_list'), true);
  assert.equal(isResourceAllowlisted('animal_detail'), true);
  assert.equal(isResourceAllowlisted('alerts_list'), true);
  assert.equal(isResourceAllowlisted('locations_latest'), true);

  // 2. Types strictement exclus
  assert.equal(isResourceAllowlisted('raw_telemetry'), false);
  assert.equal(isResourceAllowlisted('telemetry_export'), false);
  assert.equal(isResourceAllowlisted('geofences_write'), false);

  // 3. Sauvegarde d'un type exclu rejetée
  const savedNonAllowlisted = await saveToOfflineCache({
    userId: 1,
    farmId: 10,
    resourceType: 'raw_telemetry',
    resourceKey: 'telemetry_123',
    payload: { samples: [1, 2, 3] },
  });
  assert.equal(savedNonAllowlisted, false);
});

test('offlineCache isolates data by user, farm and session', async () => {
  const asyncStorageMock = createAsyncStorageMock();
  let currentEpoch = 1;
  const sessionListeners = new Set();

  const sessionLifecycleMock = {
    getSessionEpoch: () => currentEpoch,
    advanceSessionEpoch: () => {
      ++currentEpoch;
      sessionListeners.forEach((fn) => fn(currentEpoch));
      return currentEpoch;
    },
    onSessionChange: (listener) => {
      sessionListeners.add(listener);
      return () => sessionListeners.delete(listener);
    },
    withSessionStorage: (op) => op(),
  };

  const {
    saveToOfflineCache,
    loadFromOfflineCache,
  } = loadTypeScript(path.resolve(__dirname, '../src/utils/offlineCache.ts'), {
    '@react-native-async-storage/async-storage': asyncStorageMock,
    '../store/sessionLifecycle': sessionLifecycleMock,
  });

  const animalListPayload = [{ id: 101, name: 'Daisy' }, { id: 102, name: 'Bessie' }];

  // Sauvegarde pour User 1, Farm 10
  const saved = await saveToOfflineCache({
    userId: 1,
    farmId: 10,
    resourceType: 'animals_list',
    resourceKey: 'list',
    payload: animalListPayload,
  });
  assert.equal(saved, true);

  // 1. Lecture réussie par User 1, Farm 10
  const entry = await loadFromOfflineCache({
    userId: 1,
    farmId: 10,
    resourceType: 'animals_list',
    resourceKey: 'list',
  });
  assert.notEqual(entry, null);
  assert.deepEqual(entry.payload, animalListPayload);
  assert.equal(entry.user_id, 1);
  assert.equal(entry.farm_id, 10);

  // 2. Échec de lecture par un autre utilisateur (User 2) -> isolation stricte
  const crossUserEntry = await loadFromOfflineCache({
    userId: 2,
    farmId: 10,
    resourceType: 'animals_list',
    resourceKey: 'list',
  });
  assert.equal(crossUserEntry, null);

  // 3. Échec de lecture pour une autre ferme (Farm 20) -> isolation stricte
  const crossFarmEntry = await loadFromOfflineCache({
    userId: 1,
    farmId: 20,
    resourceType: 'animals_list',
    resourceKey: 'list',
  });
  assert.equal(crossFarmEntry, null);

  // 4. Invalidation de session (Logout) -> purge du cache
  sessionLifecycleMock.advanceSessionEpoch();

  const entryAfterLogout = await loadFromOfflineCache({
    userId: 1,
    farmId: 10,
    resourceType: 'animals_list',
    resourceKey: 'list',
  });
  assert.equal(entryAfterLogout, null);
});

test('offlineCache discards late responses from earlier sessions', async () => {
  const asyncStorageMock = createAsyncStorageMock();
  let currentEpoch = 1;

  const sessionLifecycleMock = {
    getSessionEpoch: () => currentEpoch,
    advanceSessionEpoch: () => ++currentEpoch,
    onSessionChange: () => () => {},
    withSessionStorage: (op) => op(),
  };

  const {
    saveToOfflineCache,
  } = loadTypeScript(path.resolve(__dirname, '../src/utils/offlineCache.ts'), {
    '@react-native-async-storage/async-storage': asyncStorageMock,
    '../store/sessionLifecycle': sessionLifecycleMock,
  });

  // Requête démarrée à l'epoch 1
  const requestEpoch = currentEpoch;

  // L'utilisateur change de compte (epoch passe à 2)
  sessionLifecycleMock.advanceSessionEpoch();

  // La réponse tardive arrive enfin
  const savedLate = await saveToOfflineCache({
    userId: 1,
    farmId: 10,
    resourceType: 'animals_list',
    resourceKey: 'list',
    payload: [{ id: 999 }],
    requestEpoch,
  });

  // Doit être ignorée pour ne pas corrompre la nouvelle session
  assert.equal(savedLate, false);
});

test('offlineCache handles corrupted storage gracefully', async () => {
  const asyncStorageMock = createAsyncStorageMock();
  let currentEpoch = 1;

  const sessionLifecycleMock = {
    getSessionEpoch: () => currentEpoch,
    advanceSessionEpoch: () => ++currentEpoch,
    onSessionChange: () => () => {},
    withSessionStorage: (op) => op(),
  };

  const {
    loadFromOfflineCache,
  } = loadTypeScript(path.resolve(__dirname, '../src/utils/offlineCache.ts'), {
    '@react-native-async-storage/async-storage': asyncStorageMock,
    '../store/sessionLifecycle': sessionLifecycleMock,
  });

  // Injecter du JSON corrompu
  await asyncStorageMock.setItem('@offline_cache:1:10:animals_list:list', '{ invalid json ...');

  const result = await loadFromOfflineCache({
    userId: 1,
    farmId: 10,
    resourceType: 'animals_list',
    resourceKey: 'list',
  });

  assert.equal(result, null);
  // La clé corrompue doit avoir été purgée
  assert.equal(await asyncStorageMock.getItem('@offline_cache:1:10:animals_list:list'), null);
});

test('formatTimeAgo calculates friendly text', () => {
  const { formatTimeAgo } = loadTypeScript(path.resolve(__dirname, '../src/components/OfflineBanner.tsx'), {
    'react-native': { View: () => null, Text: () => null, StyleSheet: { create: (s) => s } },
    '@expo/vector-icons': { Ionicons: () => null },
    '../constants/config': {
      Colors: { severity: { warning: '#f39c12' }, text: { secondary: '#999' } },
      Spacing: { md: 12, sm: 8, base: 16, xs: 4 },
      Typography: { xs: 11 },
      Radius: { md: 10 },
    },
  });

  assert.equal(formatTimeAgo(null), 'inconnue');
  assert.equal(formatTimeAgo(undefined), 'inconnue');

  const now = Date.now();
  assert.equal(formatTimeAgo(new Date(now - 10_000).toISOString()), 'à l\'instant');
  assert.equal(formatTimeAgo(new Date(now - 15 * 60_000).toISOString()), 'il y a 15 min');
  assert.equal(formatTimeAgo(new Date(now - 2 * 3600_000).toISOString()), 'il y a 2 h');
  assert.equal(formatTimeAgo(new Date(now - 3 * 86400_000).toISOString()), 'il y a 3 j');
});
