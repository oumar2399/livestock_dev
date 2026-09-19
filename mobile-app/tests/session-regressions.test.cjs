/* global __dirname */
const assert = require('node:assert/strict');
const path = require('node:path');
const { afterEach, test } = require('node:test');
const axios = require('axios');
const { MutationObserver } = require('@tanstack/react-query');
const { loadTypeScript } = require('./helpers/load-typescript.cjs');

global.__DEV__ = false;
const clients = [];
afterEach(() => { for (const client of clients.splice(0)) client.clear(); });

function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

async function until(predicate) {
  for (let attempt = 0; attempt < 100; attempt++) {
    if (predicate()) return;
    await new Promise((resolve) => setImmediate(resolve));
  }
  assert.fail('Expected asynchronous operation did not start');
}

function tokens(account = 'A', suffix = '') {
  return { access_token: `access-${account}${suffix}`, refresh_token: `refresh-${account}${suffix}`,
    token_type: 'bearer', expires_in: 86400,
    user: { id: account === 'A' ? 1 : 2, email: `${account}@example.com`, name: account, role: 'owner', phone: null } };
}

function response(config, data, status = 200) {
  return { config, data, status, statusText: String(status), headers: {} };
}

function httpError(config, status) {
  return new axios.AxiosError('HTTP failure', undefined, config, {}, response(config, { detail: 'Failure' }, status));
}

function harness() {
  const saved = new Map();
  const h = { saved, calls: [], beforeWrite: null, onRequest: null };
  const storage = {
    getItem: async (key) => saved.get(key) ?? null,
    multiGet: async (keys) => keys.map((key) => [key, saved.get(key) ?? null]),
    multiSet: async (pairs) => {
      if (h.beforeWrite) await h.beforeWrite(pairs);
      pairs.forEach(([key, value]) => saved.set(key, value));
    },
    multiRemove: async (keys) => keys.forEach((key) => saved.delete(key)),
    setItem: async (key, value) => saved.set(key, value),
    removeItem: async (key) => saved.delete(key),
  };
  const overrides = { '@react-native-async-storage/async-storage': storage };
  const cache = new Map();
  const load = (file) => loadTypeScript(path.resolve(__dirname, '../src', file), overrides, cache);
  h.auth = load('store/authStore.ts').useAuthStore;
  h.farms = load('store/farmStore.ts').useFarmStore;
  const api = load('api/client.ts');
  h.api = api.default;
  h.ApiError = api.ApiError;
  h.NetworkError = api.NetworkError;
  h.queryClient = load('api/queryClient.ts').queryClient;
  h.keys = load('constants/config.ts').Config.STORAGE;
  h.lifecycle = load('store/sessionLifecycle.ts');
  clients.push(h.queryClient);
  h.api.defaults.adapter = async (config) => {
    h.calls.push(config);
    if (h.onRequest) return h.onRequest(config);
    assert.equal(config.url, '/auth/login');
    return response(config, tokens(JSON.parse(config.data).email));
  };
  h.login = (account = 'A') => h.auth.getState().login({ username: account, password: 'test-only' });
  h.seed = (account = 'A') => {
    const data = tokens(account);
    saved.set(h.keys.ACCESS_TOKEN, data.access_token);
    saved.set(h.keys.REFRESH_TOKEN, data.refresh_token);
    saved.set(h.keys.USER_ROLE, data.user.role);
    saved.set(h.keys.USER_NAME, data.user.name);
    saved.set(h.keys.USER_EMAIL, data.user.email);
  };
  return h;
}

test('all direct logouts immediately clear auth, farm state and the shared query cache', async () => {
  const h = harness();
  await h.login();
  h.farms.setState({ farms: [{ id: 17 }], currentFarmId: 17 });
  h.saved.set('@livestock/current_farm_id', '17');
  h.queryClient.setQueryData(['animals', 17], [{ id: 1 }]);
  const logout = h.auth.getState().logout();
  assert.equal(h.auth.getState().isAuthenticated, false);
  assert.equal(h.farms.getState().currentFarmId, null);
  assert.deepEqual(h.farms.getState().farms, []);
  assert.equal(h.queryClient.getQueryData(['animals', 17]), undefined);
  await logout;
  assert.equal(h.saved.size, 0);
});

test('a refresh response arriving after logout cannot restore credentials', async () => {
  const h = harness();
  await h.login();
  const pending = deferred();
  h.onRequest = async (config) => { await pending.promise; return response(config, tokens('A', '-new')); };
  const refresh = h.auth.getState().refreshToken();
  await until(() => h.calls.some((c) => c.url === '/auth/refresh'));
  await h.auth.getState().logout();
  pending.resolve();
  assert.equal(await refresh, false);
  assert.equal(h.auth.getState().isAuthenticated, false);
  assert.equal(h.saved.size, 0);
});

test('a delayed refresh write cannot overwrite logout followed by another login', async () => {
  const h = harness();
  await h.login();
  const writing = deferred(), release = deferred();
  h.beforeWrite = async (pairs) => {
    if (pairs.some(([, value]) => value === 'access-A-new')) { writing.resolve(); await release.promise; }
  };
  h.onRequest = async (config) => response(config, tokens(config.url === '/auth/login' ? 'B' : 'A',
    config.url === '/auth/login' ? '' : '-new'));
  const refresh = h.auth.getState().refreshToken();
  await writing.promise;
  const logout = h.auth.getState().logout();
  const login = h.login('B');
  release.resolve();
  await Promise.all([refresh, logout, login]);
  assert.equal(h.auth.getState().user.name, 'B');
  assert.equal(h.saved.get(h.keys.ACCESS_TOKEN), 'access-B');
  assert.equal(h.saved.get(h.keys.REFRESH_TOKEN), 'refresh-B');
});

test('a late login response cannot resurrect a logged out account', async () => {
  const h = harness(), pending = deferred();
  h.onRequest = async (config) => { await pending.promise; return response(config, tokens()); };
  const login = h.login();
  await until(() => h.calls.length === 1);
  await h.auth.getState().logout();
  pending.resolve();
  await login;
  assert.equal(h.auth.getState().isAuthenticated, false);
  assert.equal(h.saved.size, 0);
});

test('a stale hydration cannot overwrite a newer login', async () => {
  const h = harness(), pending = deferred();
  h.seed();
  h.onRequest = async (config) => {
    if (config.url === '/auth/me') { await pending.promise; return response(config, tokens().user); }
    return response(config, tokens('B'));
  };
  const hydrate = h.auth.getState().hydrate();
  await until(() => h.calls.length === 1);
  await h.login('B');
  pending.resolve();
  await hydrate;
  assert.equal(h.auth.getState().user.name, 'B');
  assert.equal(h.saved.get(h.keys.ACCESS_TOKEN), 'access-B');
});

for (const failure of ['offline', 500, 503]) {
  test(`hydration preserves saved credentials on ${failure} without granting offline access`, async () => {
    const h = harness();
    h.seed();
    h.onRequest = async (config) => { throw failure === 'offline' ? new axios.AxiosError('Offline', 'ERR_NETWORK', config) : httpError(config, failure); };
    await h.auth.getState().hydrate();
    assert.equal(h.saved.get(h.keys.ACCESS_TOKEN), 'access-A');
    assert.equal(h.saved.get(h.keys.REFRESH_TOKEN), 'refresh-A');
    assert.equal(h.auth.getState().isAuthenticated, false);
    assert.equal(h.auth.getState().isLoading, false);
    assert.ok(h.auth.getState().error);
    h.onRequest = async (config) => response(config, tokens().user);
    await h.auth.getState().hydrate();
    assert.equal(h.auth.getState().isAuthenticated, true);
  });
}

test('an expired access token plus a refresh network failure is not treated as invalid credentials', async () => {
  const h = harness();
  h.seed();
  h.onRequest = async (config) => {
    if (config.url === '/auth/me') throw httpError(config, 401);
    throw new axios.AxiosError('Timeout', 'ECONNABORTED', config);
  };
  await h.auth.getState().hydrate();
  assert.equal(h.saved.get(h.keys.REFRESH_TOKEN), 'refresh-A');
  assert.equal(h.auth.getState().isAuthenticated, false);
  assert.match(h.auth.getState().error, /serveur/);
});

test('a confirmed invalid refresh token clears session and farm data', async () => {
  const h = harness();
  await h.login();
  h.farms.setState({ farms: [{ id: 17 }], currentFarmId: 17 });
  h.onRequest = async (config) => { throw httpError(config, 401); };
  assert.equal(await h.auth.getState().refreshToken(), false);
  assert.equal(h.auth.getState().isAuthenticated, false);
  assert.equal(h.farms.getState().currentFarmId, null);
  assert.equal(h.saved.size, 0);
});

test('a transient refresh failure keeps an already authenticated account and permits retry', async () => {
  const h = harness();
  await h.login();
  h.onRequest = async (config) => { throw httpError(config, 503); };
  await assert.rejects(h.auth.getState().refreshToken(), (error) => error.status === 503);
  assert.equal(h.auth.getState().isAuthenticated, true);
  assert.equal(h.saved.get(h.keys.REFRESH_TOKEN), 'refresh-A');
  h.onRequest = async (config) => response(config, tokens('A', '-new'));
  assert.equal(await h.auth.getState().refreshToken(), true);
  assert.equal(h.saved.get(h.keys.ACCESS_TOKEN), 'access-A-new');
});

test('concurrent 401 responses share one refresh and replay with the new token', async () => {
  const h = harness();
  await h.login();
  const pending = deferred();
  let refreshes = 0, expired = 0;
  h.onRequest = async (config) => {
    if (config.url === '/auth/refresh') {
      refreshes++;
      await pending.promise;
      return response(config, tokens('A', '-new'));
    }
    if (!config._retry) { expired++; throw httpError(config, 401); }
    assert.equal(config.headers.Authorization, 'Bearer access-A-new');
    return response(config, []);
  };
  const requests = [h.api.get('/animals/'), h.api.get('/devices/')];
  await until(() => expired === 2 && refreshes === 1);
  pending.resolve();
  await Promise.all(requests);
  assert.equal(refreshes, 1);
});

test('new-account refresh does not join the previous account pending refresh', async () => {
  const h = harness();
  await h.login();
  const pending = deferred();
  h.onRequest = async (config) => {
    if (config.url === '/auth/login') return response(config, tokens('B'));
    const account = JSON.parse(config.data).refresh_token.includes('A') ? 'A' : 'B';
    if (account === 'A') await pending.promise;
    return response(config, tokens(account, '-new'));
  };
  const oldRefresh = h.auth.getState().refreshToken();
  await until(() => h.calls.some((c) => c.url === '/auth/refresh'));
  await h.auth.getState().logout();
  await h.login('B');
  assert.equal(await h.auth.getState().refreshToken(), true);
  pending.resolve();
  assert.equal(await oldRefresh, false);
  assert.equal(h.auth.getState().user.name, 'B');
  assert.equal(h.saved.get(h.keys.ACCESS_TOKEN), 'access-B-new');
});

test('a previous-account 401 cannot refresh or replay a request as the new account', async () => {
  const h = harness();
  await h.login();
  const pending = deferred();
  h.onRequest = async (config) => {
    if (config.url === '/auth/login') return response(config, tokens('B'));
    await pending.promise;
    throw httpError(config, 401);
  };
  const request = h.api.get('/animals/');
  const rejection = assert.rejects(request, (error) => axios.isCancel(error));
  await until(() => h.calls.some((c) => c.url === '/animals/'));
  await h.login('B');
  pending.resolve();
  await rejection;
  assert.equal(h.calls.filter((c) => c.url === '/auth/refresh').length, 0);
  assert.equal(h.calls.filter((c) => c.url === '/animals/').length, 1);
});

test('a request queued just before logout cannot start under the next session', async () => {
  const h = harness();
  await h.login();
  h.onRequest = async (config) => response(config, tokens('B'));
  const request = h.api.post('/animals/', { name: 'Old account request' });
  const rejection = assert.rejects(request, (error) => axios.isCancel(error));
  const login = h.login('B');
  await Promise.all([rejection, login]);
  assert.equal(h.calls.filter((c) => c.url === '/animals/').length, 0);
  assert.equal(h.auth.getState().user.name, 'B');
});

test('late farm responses cannot restore the previous account farms', async () => {
  const h = harness();
  await h.login();
  const pending = deferred();
  h.onRequest = async (config) => {
    if (config.url === '/auth/login') return response(config, tokens('B'));
    if (config.headers.Authorization === 'Bearer access-A') {
      await pending.promise;
      return response(config, [{ id: 17, name: 'Farm A' }]);
    }
    return response(config, [{ id: 25, name: 'Farm B' }]);
  };
  const oldLoad = h.farms.getState().loadFarms();
  await until(() => h.calls.some((c) => c.url === '/farms/'));
  await h.login('B');
  await h.farms.getState().loadFarms();
  pending.resolve();
  await oldLoad;
  assert.deepEqual(h.farms.getState().farms, [{ id: 25, name: 'Farm B' }]);
  assert.equal(h.saved.get('@livestock/current_farm_id'), '25');
});

test('farm selection supports multiple assigned farms and rejects unassigned ids', async () => {
  const h = harness();
  await h.login();
  h.onRequest = async (config) => response(config, [{ id: 17 }, { id: 25 }]);
  h.saved.set('@livestock/current_farm_id', '999');
  await h.farms.getState().loadFarms();
  assert.equal(h.farms.getState().currentFarmId, 17);
  assert.equal(await h.farms.getState().selectFarm(999), false);
  assert.equal(await h.farms.getState().selectFarm(25), true);
  await h.farms.getState().loadFarms();
  assert.equal(h.farms.getState().currentFarmId, 25);
});

test('clearing farms invalidates a pending selection before it can restore state', async () => {
  const h = harness();
  await h.login();
  h.farms.setState({ farms: [{ id: 17 }, { id: 25 }], currentFarmId: 17 });
  const pending = deferred();
  const blocked = h.lifecycle.withSessionStorage(() => pending.promise);
  const selecting = h.farms.getState().selectFarm(25);
  const clearing = h.farms.getState().clear();
  pending.resolve();
  await Promise.all([blocked, clearing]);
  assert.equal(await selecting, false);
  assert.equal(h.farms.getState().currentFarmId, null);
  assert.equal(h.saved.has('@livestock/current_farm_id'), false);
});

test('logout cancels cached queries and late success cannot repopulate them', async () => {
  const h = harness();
  await h.login();
  const pending = deferred();
  h.onRequest = async (config) => { await pending.promise; return response(config, [{ id: 17 }]); };
  const query = h.queryClient.fetchQuery({ queryKey: ['animals', 17], queryFn: () => h.api.get('/animals/') });
  const rejection = assert.rejects(query);
  await until(() => h.calls.some((c) => c.url === '/animals/'));
  await h.auth.getState().logout();
  pending.resolve();
  await rejection;
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(h.queryClient.getQueryData(['animals', 17]), undefined);
});

test('mutations do not repeat a creation after its response is lost', async () => {
  const h = harness();
  await h.login();
  let creations = 0;
  h.onRequest = async (config) => {
    creations++;
    throw new axios.AxiosError('Response lost after commit', 'ERR_NETWORK', config);
  };
  const observer = new MutationObserver(h.queryClient, { mutationFn: () => h.api.post('/geofences/', { name: 'Zone' }) });
  await assert.rejects(observer.mutate(), (error) => error instanceof h.NetworkError);
  assert.equal(creations, 1);
  assert.equal(h.queryClient.getDefaultOptions().queries.retry, 2);
});

test('request cancellation and structured validation errors keep their correct types', async () => {
  const h = harness();
  h.onRequest = async () => { throw new axios.CanceledError('Cancelled'); };
  await assert.rejects(h.api.get('/animals/'), (error) => axios.isCancel(error));
  h.onRequest = async (config) => {
    throw new axios.AxiosError('Validation', undefined, config, {},
      response(config, { detail: [{ loc: ['body', 'name'], msg: 'Invalid' }] }, 422));
  };
  await assert.rejects(h.api.put('/animals/1', { name: null }), (error) =>
    error instanceof h.ApiError && error.status === 422 && typeof error.message === 'string');
});
