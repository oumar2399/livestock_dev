/**
 * Add a collar to the selected farm (owner, farmer, admin). The server picks the
 * transport ID and generates the secret, returned ONCE: it is shown here as text and
 * QR code with the device_config.py lines to copy by hand (LoRaWAN pairing comes later).
 */
import React, { useState } from 'react';
import {
  View, Text, StyleSheet, Modal, TextInput, TouchableOpacity, ActivityIndicator, ScrollView, Share,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import QRCode from 'react-native-qrcode-svg';

import { Colors, Radius, Spacing, Typography } from '../constants/config';
import { ProvisionedDevice, useCreateDevice } from '../hooks/useDevices';
import { showApiError } from '../utils/apiErrors';
import { deviceConfigLines } from '../utils/deviceStatus';

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

  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={close}>
      <View style={styles.overlay}>
        <View style={styles.sheet}>
          {!created ? (
            <>
              <Text style={styles.title}>Add a device</Text>
              <Text style={styles.label}>Into farm: {farmName}</Text>
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
              <View style={styles.actions}>
                <TouchableOpacity style={styles.cancelBtn} onPress={close}>
                  <Text style={styles.cancelText}>Cancel</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={styles.submitBtn}
                  onPress={submit}
                  disabled={createDevice.isPending || deviceId.trim().length < 3}
                >
                  {createDevice.isPending
                    ? <ActivityIndicator color="#fff" />
                    : <Text style={styles.submitText}>Add device</Text>}
                </TouchableOpacity>
              </View>
            </>
          ) : (
            <ScrollView contentContainerStyle={styles.result}>
              <Text style={styles.title}>Device {created.id} added</Text>
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
              <View style={styles.actions}>
                <TouchableOpacity style={styles.cancelBtn} onPress={() => { void Share.share({ message: config }); }}>
                  <Text style={styles.cancelText}>Share</Text>
                </TouchableOpacity>
                <TouchableOpacity style={styles.submitBtn} onPress={close}>
                  <Text style={styles.submitText}>I copied it</Text>
                </TouchableOpacity>
              </View>
            </ScrollView>
          )}
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  overlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.7)', justifyContent: 'center', padding: Spacing.base },
  sheet: { maxHeight: '90%', backgroundColor: Colors.bg.card, borderRadius: Radius.lg, padding: Spacing.base, gap: Spacing.sm },
  title: { fontSize: Typography.md, fontWeight: '700', color: Colors.text.primary },
  label: { fontSize: Typography.sm, fontWeight: '600', color: Colors.text.secondary, marginTop: Spacing.xs },
  hint: { fontSize: Typography.xs, color: Colors.text.muted },
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
  actions: { flexDirection: 'row', gap: Spacing.sm, marginTop: Spacing.sm },
  cancelBtn: { flex: 1, paddingVertical: Spacing.md, borderRadius: Radius.md, backgroundColor: Colors.bg.input, alignItems: 'center' },
  cancelText: { color: Colors.text.secondary, fontWeight: '600', fontSize: Typography.sm },
  submitBtn: { flex: 2, paddingVertical: Spacing.md, borderRadius: Radius.md, backgroundColor: Colors.primary, alignItems: 'center' },
  submitText: { color: '#fff', fontWeight: '700', fontSize: Typography.sm },
});
