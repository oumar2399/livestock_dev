/**
 * Create a farm (platform admin only). The admin is not added as a member: after
 * creation, the admin invites the farm's owner from the Users screen.
 */
import React, { useState, useEffect } from 'react';
import { View, Text, TextInput, StyleSheet } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { Colors, Spacing, Typography, Radius } from '../constants/config';
import { useCreateFarm } from '../hooks/useFarms';
import { generateUUID } from '../utils/uuid';
import { FarmAccess } from '../types';
import AppModal, { ModalButton } from './AppModal';

interface FarmCreateModalProps {
  visible: boolean;
  onClose: () => void;
  onSuccess?: (farm: FarmAccess) => void;
}

export default function FarmCreateModal({ visible, onClose, onSuccess }: FarmCreateModalProps) {
  const [name, setName] = useState('');
  const [address, setAddress] = useState('');
  const [sizeHectares, setSizeHectares] = useState('');
  const [requestId, setRequestId] = useState('');
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const createFarmMutation = useCreateFarm();

  // Generate a fresh idempotency key when the modal is opened
  useEffect(() => {
    if (visible) {
      setName('');
      setAddress('');
      setSizeHectares('');
      setErrorMsg(null);
      setRequestId(generateUUID());
    }
  }, [visible]);

  const handleSubmit = async () => {
    const trimmedName = name.trim();
    if (!trimmedName) {
      setErrorMsg('The farm name is required.');
      return;
    }

    setErrorMsg(null);

    const parsedSize = sizeHectares.trim() ? parseFloat(sizeHectares.replace(',', '.')) : null;
    if (parsedSize !== null && (isNaN(parsedSize) || parsedSize < 0)) {
      setErrorMsg('The area must be a valid positive number.');
      return;
    }

    try {
      const createdFarm = await createFarmMutation.mutateAsync({
        name: trimmedName,
        address: address.trim() || null,
        size_hectares: parsedSize,
        client_request_id: requestId,
      });

      onClose();
      if (onSuccess) {
        onSuccess(createdFarm);
      }
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      if (typeof detail === 'string') {
        setErrorMsg(detail);
      } else {
        setErrorMsg('Could not create the farm. Check your connection.');
      }
    }
  };

  const saving = createFarmMutation.isPending;

  return (
    <AppModal
      visible={visible}
      title="Create a farm"
      subtitle="Then invite its owner from Users"
      onClose={onClose}
      primaryAction={{ label: 'Create', onPress: handleSubmit, busy: saving }}
      footer={(
        <>
          <ModalButton label="Cancel" kind="secondary" onPress={onClose} disabled={saving} />
          <ModalButton label="Create farm" onPress={handleSubmit} busy={saving} />
        </>
      )}
    >
      {errorMsg ? (
        <View style={styles.errorBanner}>
          <Ionicons name="alert-circle-outline" size={18} color={Colors.severity.critical} />
          <Text style={styles.errorBannerText}>{errorMsg}</Text>
        </View>
      ) : null}

      {/* Field: Name */}
      <View style={styles.field}>
        <Text style={styles.label}>
          Farm name <Text style={styles.required}>*</Text>
        </Text>
        <TextInput
          style={styles.input}
          value={name}
          onChangeText={setName}
          placeholder="E.g. Hill Farm"
          placeholderTextColor={Colors.text.muted}
          maxLength={255}
          autoFocus
        />
      </View>

      {/* Field: Address */}
      <View style={styles.field}>
        <Text style={styles.label}>Location / Address</Text>
        <TextInput
          style={styles.input}
          value={address}
          onChangeText={setAddress}
          placeholder="E.g. Korhogo, North pasture"
          placeholderTextColor={Colors.text.muted}
          maxLength={255}
        />
      </View>

      {/* Field: Size */}
      <View style={styles.field}>
        <Text style={styles.label}>Estimated area (hectares)</Text>
        <TextInput
          style={styles.input}
          value={sizeHectares}
          onChangeText={setSizeHectares}
          placeholder="E.g. 50.5"
          placeholderTextColor={Colors.text.muted}
          keyboardType="decimal-pad"
        />
      </View>

      <View style={styles.infoNote}>
        <Ionicons name="information-circle-outline" size={16} color={Colors.text.secondary} />
        <Text style={styles.infoNoteText}>
          After creating the farm, invite its owner from Users. Animals, collars and grazing zones can then be added.
        </Text>
      </View>
    </AppModal>
  );
}

const styles = StyleSheet.create({
  errorBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.xs,
    backgroundColor: Colors.severity.critical + '18',
    borderColor: Colors.severity.critical,
    borderWidth: 1,
    borderRadius: Radius.md,
    padding: Spacing.sm,
    marginBottom: Spacing.md,
  },
  errorBannerText: {
    flex: 1,
    color: Colors.severity.critical,
    fontSize: Typography.xs,
    fontWeight: '500',
  },
  field: {
    marginBottom: Spacing.md,
  },
  label: {
    fontSize: Typography.sm,
    fontWeight: '600',
    color: Colors.text.secondary,
    marginBottom: 6,
  },
  required: {
    color: Colors.severity.critical,
  },
  input: {
    backgroundColor: Colors.bg.input,
    borderWidth: 1,
    borderColor: Colors.border.default,
    borderRadius: Radius.md,
    paddingHorizontal: Spacing.md,
    paddingVertical: Spacing.sm,
    fontSize: Typography.base,
    color: Colors.text.primary,
  },
  infoNote: {
    flexDirection: 'row',
    gap: Spacing.xs,
    backgroundColor: Colors.bg.input,
    padding: Spacing.sm,
    borderRadius: Radius.md,
  },
  infoNoteText: {
    flex: 1,
    fontSize: Typography.xs,
    color: Colors.text.muted,
    lineHeight: 16,
  },
});
