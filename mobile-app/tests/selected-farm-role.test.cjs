const assert = require('node:assert/strict');
const path = require('node:path');
const { test } = require('node:test');
const { createStore } = require('zustand/vanilla');
const { loadTypeScript } = require('./helpers/load-typescript.cjs');
const { selectedFarmRole } = loadTypeScript(path.join(__dirname, '../src/utils/selectedFarmRole.ts'));

test('farm/session transitions never fall back to the global non-admin role', () => {
  const store = createStore(() => ({ farms: [{ id: 1, membership_role: 'owner' },
    { id: 2, membership_role: 'vet' }], currentFarmId: 1, isLoading: false, error: null }));
  const seen = [];
  const unsubscribe = store.subscribe(state => seen.push(selectedFarmRole('farmer', state)));
  assert.equal(selectedFarmRole('farmer', store.getState()), 'owner');
  store.setState({ currentFarmId: 2 });
  store.setState({ isLoading: true });
  store.setState({ isLoading: false, error: 'failed' });
  store.setState({ farms: [{ id: 1, membership_role: 'owner' }], error: null });
  store.setState({ farms: [], currentFarmId: null });
  store.setState({ farms: [{ id: 3, membership_role: 'farmer' }], currentFarmId: 3 });
  assert.deepEqual(seen, ['vet', null, null, null, null, 'farmer']);
  assert.equal(selectedFarmRole(null, store.getState()), null);
  unsubscribe();
});

test('platform admin is distinct from memberships, including loading and no farms', () => {
  for (const isLoading of [true, false]) {
    assert.equal(selectedFarmRole('admin', { farms: [], currentFarmId: null, isLoading, error: 'offline' }), 'admin');
  }
  assert.equal(selectedFarmRole('vet', { farms: [{ id: 1, membership_role: 'admin' }],
    currentFarmId: 1, isLoading: false, error: null }), null);
});
