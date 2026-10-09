/* global __dirname */
// Phase 4 shared UI in screen tests: AppModal, the dialog and KeyboardAwareForm need a few
// more native APIs than the older mocks provide. showDialog takes the same arguments as
// Alert.alert, so screen tests keep asserting on their Alert.alert mock; the dialog itself
// is tested in phase4.test.cjs.
const path = require('node:path');
const React = require('react');
const { loadTypeScript } = require('./load-typescript.cjs');

const SRC = path.join(__dirname, '../../src');

function completeNative(native) {
  native.Keyboard = native.Keyboard ?? { addListener: () => ({ remove() {} }) };
  native.Platform = native.Platform ?? { OS: 'android' };
  for (const name of ['View', 'Text', 'TextInput', 'Pressable', 'ScrollView', 'ActivityIndicator']) {
    native[name] = native[name] ?? name;
  }
  native.StyleSheet = { absoluteFill: {}, absoluteFillObject: {}, hairlineWidth: 1, ...native.StyleSheet };
  native.Modal = native.Modal ?? (({ visible, children, ...props }) =>
    (visible ? React.createElement('Modal', props, children) : null));
  native.Alert = native.Alert ?? { alert: () => {} };
  native.FlatList = native.FlatList ?? (({ data, renderItem, keyExtractor, ListEmptyComponent, ListHeaderComponent }) =>
    React.createElement('List', null, ListHeaderComponent ?? null,
      (data ?? []).length === 0 ? ListEmptyComponent ?? null
        : data.map((item, index) => React.createElement(React.Fragment,
          { key: keyExtractor ? keyExtractor(item) : index }, renderItem({ item, index })))));
  return native;
}

/** Module overrides for a screen test: react-native, icons, and the dialog (to Alert.alert). */
function sharedUiOverrides(native) {
  completeNative(native);
  const real = loadTypeScript(path.join(SRC, 'components/dialog.tsx'), {
    'react-native': native, '@expo/vector-icons': { Ionicons: 'Ionicons' },
  });
  const dialog = { ...real, showDialog: (...args) => native.Alert.alert(...args) };
  return {
    'react-native': native,
    '@expo/vector-icons': { Ionicons: 'Ionicons' },
    './dialog': dialog,
    '../components/dialog': dialog,
    '../../components/dialog': dialog,
  };
}

/** Buttons whose label is `label`, whatever draws them (TouchableOpacity, Pressable...). */
function buttonsLabelled(root, label) {
  return root.findAll((node) => typeof node.type === 'string' && typeof node.props.onPress === 'function'
    && (node.props.accessibilityLabel === label
      || node.findAllByType('Text').some((text) => [].concat(text.props.children).join('') === label)));
}

module.exports = { completeNative, sharedUiOverrides, buttonsLabelled };
