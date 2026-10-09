/**
 * Add a collar to the selected farm (owner, farmer, admin). The server picks the
 * transport ID and generates the secret, returned ONCE: it is shown here as text and
 * QR code with the device_config.py lines to copy by hand (LoRaWAN pairing comes later).
 */
import React, { useState } from 'react';
import { View, Text, StyleSheet, TextInput, Share } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import QRCode from 'react-native-qrcode-svg';

import { Colors, Radius, Spacing, Typography } from '../constants/config';
import { ProvisionedDevice, useCreateDevice } from '../hooks/useDevices';
import { showApiError } from '../utils/apiErrors';
import { deviceConfigLines } from '../utils/deviceStatus';
import AppModal, { ModalButton } from './AppModal';

interface Props {
  visible: boolean;
  farmId: number;
  farmName: string;
  onClose: () => void;
}

export default function AddDeviceModal({ visible, farmId, farmName, onClose }: Props) {
  const [deviceId, setDeviceId] = useState('');
  const [created, setCreated] = useState<ProvisionedDevice | null>(null);
  const createDevice = useCreateDevice();

  const close = () => {
    // The secret leaves memory with the dialog; it can never be fetched again.
    setDeviceId('');
    setCreated(null);
    onClose();
  };

  const submit = async () => {
    try {
      setCreated(await createDevice.mutateAsync({ device_id: deviceId.trim().toUpperCase(), farm_id: farmId }));
    } catch (error) {
      showApiError(error, 'Could not add device', 'Unable to add this device.');
    }
  };

  const config = created ? deviceConfigLines(created.id, created.transport_id, created.device_secret) : '';

  const canSubmit = !createDevice.isPending && deviceId.trim().length >= 3;

  // One modal for both steps, so the dialog does not close and reopen when the device is created.
  return (
    <AppModal
      visible={visible}
      title={created ? `Device ${created.id} added` : 'Add a device'}
      subtitle={created ? undefined : `Into farm: ${farmName}`}
      onClose={close}
      primaryAction={created ? undefined
        : { label: 'Add', onPress: submit, disabled: !canSubmit, busy: createDevice.isPending }}
      footer={created ? (
        <>
          <ModalButton label="Share" kind="secondary" onPress={() => { void Share.share({ message: config }); }} />
          <ModalButton label="I copied it" onPress={close} />
        </>
      ) : (
        <>
          <ModalButton label="Cancel" kind="secondary" onPress={close} />
          <ModalButton label="Add device" onPress={submit} disabled={!canSubmit} busy={createDevice.isPending} />
        </>
      )}
    >
      {created ? (
        <View style={styles.result}>
          <View style={styles.warning}>
            <Ionicons name="warning-outline" size={18} color={Colors.severity.critical} />
            <Text style={styles.warningText}>This secret is shown only once. Copy it now.</Text>
          </View>
          <Text style={styles.label}>Transport ID</Text>
          <Text selectable style={styles.value}>{created.transport_id}</Text>
          <Text style={styles.label}>Device secret</Text>
          <Text selectable style={styles.secret}>{created.device_secret}</Text>
          <View style={styles.qr}>
            <QRCode value={config} size={180} backgroundColor="#FFFFFF" color="#000000" />
          </View>
          <Text style={styles.label}>Lines for device_config.py</Text>
          <Text selectable style={styles.code}>{config}</Text>
        </View>
      ) : (
        <>
          <Text style={styles.label}>Device ID</Text>
          <TextInput
            style={styles.input}
            value={deviceId}
            onChangeText={setDeviceId}
            placeholder="E.g. M5-COLLAR-07"
            placeholderTextColor={Colors.text.muted}
            autoCapitalize="characters"
            autoCorrect={false}
          />
          <Text style={styles.hint}>3 to 50 characters: letters, digits, - or _.</Text>
        </>
      )}
    </AppModal>
  );
}

const styles = StyleSheet.create({
  label: { fontSize: Typography.sm, fontWeight: '600', color: Colors.text.secondary, marginTop: Spacing.xs, marginBottom: Spacing.xs },
  hint: { fontSize: Typography.xs, color: Colors.text.muted, marginTop: Spacing.xs },
  input: {
    minHeight: 44, backgroundColor: Colors.bg.input, borderRadius: Radius.md, borderWidth: 1,
    borderColor: Colors.border.default, paddingHorizontal: Spacing.md, color: Colors.text.primary, fontSize: Typography.base,
  },
  result: { gap: Spacing.xs },
  warning: {
    flexDirection: 'row', alignItems: 'center', gap: Spacing.xs, padding: Spacing.sm, borderRadius: Radius.md,
    borderWidth: 1, borderColor: Colors.severity.critical, backgroundColor: Colors.severity.critical + '18',
  },
  warningText: { flex: 1, color: Colors.severity.critical, fontWeight: '700', fontSize: Typography.sm },
  value: { fontSize: Typography.base, color: Colors.text.primary, fontWeight: '700' },
  secret: { fontSize: Typography.sm, color: Colors.text.primary, fontFamily: 'monospace' },
  code: { fontSize: Typography.xs, color: Colors.text.primary, fontFamily: 'monospace', backgroundColor: Colors.bg.input, padding: Spacing.sm, borderRadius: Radius.sm },
  qr: { alignSelf: 'center', padding: Spacing.sm, backgroundColor: '#FFFFFF', borderRadius: Radius.md, marginVertical: Spacing.sm },
});
