/* global __dirname */
const assert = require('node:assert/strict');
const path = require('node:path');
const { afterEach, test } = require('node:test');
const React = require('react');
const { act, create } = require('react-test-renderer');
const { loadTypeScript } = require('./helpers/load-typescript.cjs');

global.IS_REACT_ACT_ENVIRONMENT = true;
const mounted = [];
afterEach(async () => { for (const renderer of mounted.splice(0)) await act(async () => renderer.unmount()); });

async function harness(screen, options = {}) {
  const state = { farmId: 1, width: 390, fontScale: 1, ...options };
  const native = Object.fromEntries(['View', 'Text', 'Pressable', 'ScrollView', 'TextInput', 'Modal',
    'KeyboardAvoidingView'].map((name) => [name, name]));
  native.StyleSheet = { create: (styles) => styles, absoluteFillObject: {} };
  native.Platform = { OS: 'android' };
  native.useWindowDimensions = () => ({ width: state.width, height: 844, fontScale: state.fontScale });
  native.FlatList = function TestList({ data, renderItem, ListEmptyComponent, ...props }) {
    return React.createElement('FlatList', { ...props, data }, data.length
      ? data.map((item) => React.createElement(React.Fragment, { key: item.id }, renderItem({ item })))
      : ListEmptyComponent);
  };
  const Component = loadTypeScript(path.resolve(__dirname, `../src/screens/drawer/${screen}.tsx`), {
    'react-native': native,
    '@expo/vector-icons': { Ionicons: 'Ionicons' },
    'react-native-safe-area-context': { useSafeAreaInsets: () => ({ top: 24, bottom: 16 }) },
    '../store/farmStore': { useFarmStore: (selector) => selector({ currentFarmId: state.farmId,
      farms: [1, 2].map((id) => ({ id, name: `Farm ${id}` })) }) },
    '../screens/drawer/DrawerScreenBase': { __esModule: true,
      default: ({ children, ...props }) => React.createElement('Screen', props, children) },
  }).default;
  let renderer;
  await act(async () => { renderer = create(React.createElement(Component)); });
  mounted.push(renderer);
  const host = (type) => renderer.root.findAllByType(type);
  const control = (label) => renderer.root.findAll((node) => typeof node.type === 'string' && node.props.accessibilityLabel === label)[0];
  const press = async (label) => {
    const button = control(label);
    assert.ok(button, `Missing control: ${label}`);
    assert.notEqual(button.props.disabled, true, `Disabled control: ${label}`);
    await act(async () => button.props.onPress());
  };
  const update = async () => { await act(async () => renderer.update(React.createElement(Component))); };
  const text = () => host('Text').map((node) => node.props.children).flat().join(' ');
  return { state, host, control, press, update, text };
}

for (const screen of ['VideoMonitoring', 'AIAssistantScreen', 'MarketplaceScreen']) {
  test(`${screen}: honest preview status, no content without an assigned farm`, async () => {
    const h = await harness(screen, { farmId: null });
    assert.match(h.text(), /Preview.*Service not connected/);
    assert.match(h.text(), /No farm selected/);
    assert.equal(h.host('TextInput').length, 0);
    assert.equal(h.host('Modal').length, 0);
    h.state.farmId = 999;
    await h.update();
    assert.match(h.text(), /No farm selected/);
  });
}

test('video: select a sample camera and close enlarged view with Android back', async () => {
  const h = await harness('VideoMonitoring');
  await h.press('Select Pasture camera');
  assert.equal(h.control('Select Pasture camera').props.accessibilityState.selected, true);
  await h.press('Expand camera');
  assert.equal(h.host('Modal').length, 1);
  assert.match(h.text(), /Sample camera.*No video source/);
  assert.equal(h.control('Snapshot unavailable').props.disabled, true);
  assert.equal(h.control('Audio unavailable').props.onPress, undefined);
  await act(async () => h.host('Modal')[0].props.onRequestClose());
  assert.equal(h.host('Modal').length, 0);
});

test('video: recordings have no fake history, and farm change closes the modal and resets selection', async () => {
  const h = await harness('VideoMonitoring');
  await h.press('Recordings');
  assert.match(h.text(), /No recordings/);
  assert.equal(h.control('Expand camera'), undefined);
  await h.press('Cameras');
  await h.press('Select Entrance camera');
  await h.press('Expand camera');
  h.state.farmId = 2;
  await h.update();
  assert.equal(h.host('Modal').length, 0);
  assert.equal(h.control('Select Barn camera').props.accessibilityState.selected, true);
  assert.equal(h.host('Screen')[0].props.subtitle, 'Farm 2');
});

test('assistant: suggested questions populate an editable draft but never enable sending', async () => {
  const h = await harness('AIAssistantScreen');
  await h.press('Draft: Herd activity');
  assert.match(h.control('Message draft').props.value, /unusual activity/);
  await act(async () => h.control('Message draft').props.onChangeText('My question'));
  assert.equal(h.control('Message draft').props.value, 'My question');
  assert.equal(h.control('Message draft').props.maxLength, 2000);
  const send = h.control('Send unavailable: AI service not connected');
  assert.equal(send.props.disabled, true);
  assert.equal(send.props.onPress, undefined);
  assert.match(h.text(), /No messages yet/);
  await h.press('Clear draft');
  assert.equal(h.control('Message draft').props.value, '');
  assert.equal(h.control('Clear draft').props.disabled, true);
});

test('assistant: a private draft is discarded on farm change and loss of access', async () => {
  const h = await harness('AIAssistantScreen');
  await h.press('Draft: Recent alerts');
  h.state.farmId = 2;
  await h.update();
  assert.equal(h.control('Message draft').props.value, '');
  await h.press('Draft: Daily care');
  h.state.farmId = null;
  await h.update();
  assert.equal(h.host('TextInput').length, 0);
  h.state.farmId = 2;
  await h.update();
  assert.equal(h.control('Message draft').props.value, '');
});

test('marketplace: search and category filters combine, including the empty state', async () => {
  const h = await harness('MarketplaceScreen');
  assert.equal(h.host('FlatList')[0].props.data.length, 6);
  await h.press('Equipment');
  assert.equal(h.host('FlatList')[0].props.data.length, 3);
  await act(async () => h.control('Search sample products').props.onChangeText(' WATER '));
  assert.deepEqual(h.host('FlatList')[0].props.data.map((item) => item.id), ['trough']);
  await h.press('Feed');
  assert.match(h.text(), /No matching products/);
  await h.press('Clear search');
  assert.equal(h.host('FlatList')[0].props.data.length, 2);
});

test('marketplace: local saved items filter and detail view, no purchase callback', async () => {
  const h = await harness('MarketplaceScreen');
  await h.press('Save Feed pellets');
  await h.press('Show saved items');
  assert.deepEqual(h.host('FlatList')[0].props.data.map((item) => item.id), ['feed']);
  await h.press('View Feed pellets');
  assert.equal(h.host('Modal').length, 1);
  assert.equal(h.control('Ordering unavailable').props.disabled, true);
  assert.equal(h.control('Ordering unavailable').props.onPress, undefined);
  assert.match(h.text(), /Seller \/ Price Not available/);
  await h.press('Close details');
  await h.press('Save Feed pellets');
  assert.match(h.text(), /No saved items match/);
});

test('marketplace: a farm switch clears search, saved items and open product details', async () => {
  const h = await harness('MarketplaceScreen');
  await h.press('Save Feed pellets');
  await h.press('View Feed pellets');
  h.state.farmId = 2;
  await h.update();
  assert.equal(h.host('Modal').length, 0);
  assert.equal(h.control('Save Feed pellets').props.accessibilityState.selected, false);
  assert.equal(h.control('Search sample products').props.value, '');
  assert.equal(h.host('FlatList')[0].props.data.length, 6);
});

test('marketplace: the grid adapts to narrow phones, tablets and large text', async () => {
  const h = await harness('MarketplaceScreen', { width: 320 });
  assert.equal(h.host('FlatList')[0].props.numColumns, 1);
  h.state.width = 390;
  await h.update();
  assert.equal(h.host('FlatList')[0].props.numColumns, 2);
  h.state.width = 1024;
  await h.update();
  assert.equal(h.host('FlatList')[0].props.numColumns, 3);
  h.state.fontScale = 1.5;
  await h.update();
  assert.equal(h.host('FlatList')[0].props.numColumns, 1);
});

test('icon actions expose a tooltip on hover', async () => {
  const h = await harness('MarketplaceScreen');
  await act(async () => h.control('Show saved items').props.onHoverIn());
  assert.match(h.text(), /Show saved items/);
  await act(async () => h.control('Show saved items').props.onHoverOut());
  assert.doesNotMatch(h.text(), /Show saved items/);
});
