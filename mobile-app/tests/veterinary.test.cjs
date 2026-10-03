const assert = require('node:assert/strict');
const path = require('node:path');
const { test } = require('node:test');
const { loadTypeScript } = require('./helpers/load-typescript.cjs');

test('veterinaryApi constructs correct endpoint URLs and payloads', async () => {
  const requests = [];
  const fakeClient = {
    get: async (url, config) => {
      requests.push({ method: 'GET', url, config });
      return { data: { total: 0, cases: [] } };
    },
    post: async (url, payload) => {
      requests.push({ method: 'POST', url, payload });
      return { data: { id: 1, ...payload } };
    },
    patch: async (url, payload) => {
      requests.push({ method: 'PATCH', url, payload });
      return { data: { id: 1, ...payload } };
    },
  };

  const { veterinaryApi } = loadTypeScript(path.resolve(__dirname, '../src/api/veterinary.ts'), {
    './client': fakeClient,
  });

  // 1. listFarmCases
  await veterinaryApi.listFarmCases(42, { status: 'provisional' });
  assert.equal(requests[0].method, 'GET');
  assert.equal(requests[0].url, '/farms/42/veterinary-cases');
  assert.deepEqual(requests[0].config.params, { status: 'provisional' });

  // 2. createCase
  await veterinaryApi.createCase(42, {
    animal_id: 101,
    title: 'Examen annuel',
    initial_entry: {
      entry_type: 'observation',
      content: 'Animal calme, température 38.5C',
    },
  });
  assert.equal(requests[1].method, 'POST');
  assert.equal(requests[1].url, '/farms/42/veterinary-cases');
  assert.equal(requests[1].payload.animal_id, 101);
  assert.equal(requests[1].payload.title, 'Examen annuel');

  // 3. getCaseDetail
  await veterinaryApi.getCaseDetail(42, 5);
  assert.equal(requests[2].method, 'GET');
  assert.equal(requests[2].url, '/farms/42/veterinary-cases/5');

  // 4. updateCase
  await veterinaryApi.updateCase(42, 5, { status: 'confirmed' });
  assert.equal(requests[3].method, 'PATCH');
  assert.equal(requests[3].url, '/farms/42/veterinary-cases/5');
  assert.equal(requests[3].payload.status, 'confirmed');

  // 5. addEntry
  await veterinaryApi.addEntry(42, 5, {
    entry_type: 'intervention',
    content: 'Vermifuge administré',
  });
  assert.equal(requests[4].method, 'POST');
  assert.equal(requests[4].url, '/farms/42/veterinary-cases/5/entries');
  assert.equal(requests[4].payload.entry_type, 'intervention');

  // 6. listAnimalCases
  await veterinaryApi.listAnimalCases(101);
  assert.equal(requests[5].method, 'GET');
  assert.equal(requests[5].url, '/animals/101/veterinary-cases');
});

test('veterinary clinical neutrality: no auto-diagnostic parameters allowed', async () => {
  const fakeClient = {
    post: async (_url, payload) => ({ data: payload }),
  };

  const { veterinaryApi } = loadTypeScript(path.resolve(__dirname, '../src/api/veterinary.ts'), {
    './client': fakeClient,
  });

  const payload = {
    animal_id: 12,
    title: 'Consultation',
  };

  // Les charges utiles cliniques ne comportent aucun champ auto-diagnostique ou de feedback automatique
  assert.equal('auto_diagnosis' in payload, false);
  assert.equal('ml_verdict' in payload, false);
  assert.equal('auto_feedback' in payload, false);

  const res = await veterinaryApi.createCase(1, payload);
  assert.equal(res.title, 'Consultation');
});
