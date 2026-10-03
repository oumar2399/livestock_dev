import React, { useState, useEffect } from 'react';
import {
  Modal,
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { Colors, Spacing, Typography, Radius } from '../constants/config';
import { useCreateFarm } from '../hooks/useFarms';
import { generateUUID } from '../utils/uuid';
import { FarmAccess } from '../types';

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
      setErrorMsg('Le nom de la ferme est obligatoire.');
      return;
    }

    setErrorMsg(null);

    const parsedSize = sizeHectares.trim() ? parseFloat(sizeHectares.replace(',', '.')) : null;
    if (parsedSize !== null && (isNaN(parsedSize) || parsedSize < 0)) {
      setErrorMsg('La superficie doit être un nombre positif valide.');
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
        setErrorMsg('Échec de la création de la ferme. Vérifiez votre connexion.');
      }
    }
  };

  return (
    <Modal visible={visible} animationType="slide" transparent onRequestClose={onClose}>
      <KeyboardAvoidingView
        style={styles.overlay}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      >
        <View style={styles.sheet}>
          {/* Header */}
          <View style={styles.header}>
            <View style={styles.headerTitleRow}>
              <View style={styles.iconCircle}>
                <Ionicons name="business" size={22} color={Colors.primary} />
              </View>
              <View>
                <Text style={styles.title}>Créer une exploitation</Text>
                <Text style={styles.subtitle}>Vous en serez le propriétaire (Owner)</Text>
              </View>
            </View>
            <TouchableOpacity onPress={onClose} hitSlop={10} style={styles.closeBtn}>
              <Ionicons name="close" size={22} color={Colors.text.muted} />
            </TouchableOpacity>
          </View>

          <ScrollView style={styles.body} showsVerticalScrollIndicator={false}>
            {errorMsg ? (
              <View style={styles.errorBanner}>
                <Ionicons name="alert-circle-outline" size={18} color={Colors.severity.critical} />
                <Text style={styles.errorBannerText}>{errorMsg}</Text>
              </View>
            ) : null}

            {/* Field: Name */}
            <View style={styles.field}>
              <Text style={styles.label}>
                Nom de la ferme <Text style={styles.required}>*</Text>
              </Text>
              <TextInput
                style={styles.input}
                value={name}
                onChangeText={setName}
                placeholder="Ex: Domaine des Collines"
                placeholderTextColor={Colors.text.muted}
                maxLength={255}
                autoFocus
              />
            </View>

            {/* Field: Address */}
            <View style={styles.field}>
              <Text style={styles.label}>Localisation / Adresse</Text>
              <TextInput
                style={styles.input}
                value={address}
                onChangeText={setAddress}
                placeholder="Ex: Val-d'Or, Pâturage Nord"
                placeholderTextColor={Colors.text.muted}
                maxLength={255}
              />
            </View>

            {/* Field: Size */}
            <View style={styles.field}>
              <Text style={styles.label}>Superficie estimée (hectares)</Text>
              <TextInput
                style={styles.input}
                value={sizeHectares}
                onChangeText={setSizeHectares}
                placeholder="Ex: 50.5"
                placeholderTextColor={Colors.text.muted}
                keyboardType="decimal-pad"
              />
            </View>

            <View style={styles.infoNote}>
              <Ionicons name="information-circle-outline" size={16} color={Colors.text.secondary} />
              <Text style={styles.infoNoteText}>
                Après création, vous pourrez ajouter vos animaux, rattacher des colliers M5Stack autorisés et définir vos zones de pâturage.
              </Text>
            </View>
          </ScrollView>

          {/* Footer Actions */}
          <View style={styles.footer}>
            <TouchableOpacity
              style={styles.cancelBtn}
              onPress={onClose}
              disabled={createFarmMutation.isPending}
            >
              <Text style={styles.cancelBtnText}>Annuler</Text>
            </TouchableOpacity>

            <TouchableOpacity
              style={[styles.submitBtn, createFarmMutation.isPending && styles.btnDisabled]}
              onPress={handleSubmit}
              disabled={createFarmMutation.isPending}
            >
              {createFarmMutation.isPending ? (
                <ActivityIndicator color="#fff" size="small" />
              ) : (
                <>
                  <Ionicons name="checkmark-circle-outline" size={18} color="#fff" />
                  <Text style={styles.submitBtnText}>Créer la ferme</Text>
                </>
              )}
            </TouchableOpacity>
          </View>
        </View>
      </KeyboardAvoidingView>
    </Modal>
  );
}

const styles = StyleSheet.create({
  overlay: {
    flex: 1,
    backgroundColor: 'rgba(0, 0, 0, 0.6)',
    justifyContent: 'flex-end',
  },
  sheet: {
    backgroundColor: Colors.bg.card,
    borderTopLeftRadius: Radius.xl,
    borderTopRightRadius: Radius.xl,
    paddingTop: Spacing.base,
    paddingBottom: Platform.OS === 'ios' ? 36 : Spacing.base,
    maxHeight: '90%',
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: Spacing.base,
    paddingBottom: Spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: Colors.border.default,
  },
  headerTitleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.sm,
  },
  iconCircle: {
    width: 40,
    height: 40,
    borderRadius: Radius.full,
    backgroundColor: Colors.primary + '20',
    alignItems: 'center',
    justifyContent: 'center',
  },
  title: {
    fontSize: Typography.base,
    fontWeight: '700',
    color: Colors.text.primary,
  },
  subtitle: {
    fontSize: Typography.xs,
    color: Colors.text.secondary,
  },
  closeBtn: {
    padding: Spacing.xs,
  },
  body: {
    paddingHorizontal: Spacing.base,
    paddingVertical: Spacing.md,
  },
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
    marginBottom: Spacing.lg,
  },
  infoNoteText: {
    flex: 1,
    fontSize: Typography.xs,
    color: Colors.text.muted,
    lineHeight: 16,
  },
  footer: {
    flexDirection: 'row',
    gap: Spacing.sm,
    paddingHorizontal: Spacing.base,
    paddingTop: Spacing.sm,
  },
  cancelBtn: {
    flex: 1,
    paddingVertical: Spacing.md,
    borderRadius: Radius.md,
    backgroundColor: Colors.bg.input,
    alignItems: 'center',
    justifyContent: 'center',
  },
  cancelBtnText: {
    color: Colors.text.secondary,
    fontSize: Typography.sm,
    fontWeight: '600',
  },
  submitBtn: {
    flex: 2,
    flexDirection: 'row',
    gap: Spacing.xs,
    paddingVertical: Spacing.md,
    borderRadius: Radius.md,
    backgroundColor: Colors.primary,
    alignItems: 'center',
    justifyContent: 'center',
  },
  btnDisabled: {
    opacity: 0.6,
  },
  submitBtnText: {
    color: '#fff',
    fontSize: Typography.sm,
    fontWeight: '700',
  },
});
