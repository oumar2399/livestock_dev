import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TextInput,
  TouchableOpacity,
  Alert,
  ActivityIndicator,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useNavigation } from '@react-navigation/native';
import DrawerScreenBase from './DrawerScreenBase';
import { Colors, Spacing, Typography, Radius } from '../../constants/config';
import apiClient from '../../api/client';
import { useFarmStore } from '../../store/farmStore';
import FarmCreateModal from '../../components/FarmCreateModal';

export default function FarmScreen() {
  const navigation = useNavigation<any>();
  const { farms, currentFarmId, loadFarms, selectFarm } = useFarmStore();
  const currentFarm = farms.find((item) => item.id === currentFarmId) ?? null;
  const canManageFarm = currentFarm?.permissions.includes('manage_farm') ?? false;

  const [farm, setFarm] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({ name: '', address: '', size_hectares: '' });
  const [saving, setSaving] = useState(false);
  const [showCreateModal, setShowCreateModal] = useState(false);

  useEffect(() => {
    if (!currentFarmId) {
      setFarm(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    setEditing(false);
    apiClient
      .get(`/farms/${currentFarmId}`)
      .then(({ data }) => {
        setFarm(data);
        setForm({
          name: data.name ?? '',
          address: data.address ?? '',
          size_hectares: data.size_hectares ? String(data.size_hectares) : '',
        });
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [currentFarmId]);

  const handleSave = async () => {
    if (!currentFarmId) return;
    setSaving(true);
    try {
      await apiClient.put(`/farms/${currentFarmId}`, {
        name: form.name,
        address: form.address,
        size_hectares: form.size_hectares ? parseFloat(form.size_hectares) : null,
      });
      setEditing(false);
      Alert.alert('Succès', 'Ferme mise à jour avec succès');
      const { data } = await apiClient.get(`/farms/${currentFarmId}`);
      setFarm(data);
      await loadFarms();
    } catch {
      Alert.alert('Erreur', 'Impossible de modifier la ferme');
    } finally {
      setSaving(false);
    }
  };

  return (
    <DrawerScreenBase
      title="Gestion de l'exploitation"
      rightAction={
        <View style={{ flexDirection: 'row', gap: Spacing.xs, alignItems: 'center' }}>
          {!loading && !editing && canManageFarm && (
            <TouchableOpacity onPress={() => setEditing(true)} style={styles.editBtn}>
              <Ionicons name="create-outline" size={20} color={Colors.primary} />
            </TouchableOpacity>
          )}
          <TouchableOpacity onPress={() => setShowCreateModal(true)} style={styles.addBtn}>
            <Ionicons name="add" size={20} color="#fff" />
          </TouchableOpacity>
        </View>
      }
    >
      {loading ? (
        <View style={styles.center}>
          <ActivityIndicator color={Colors.primary} />
        </View>
      ) : !farm ? (
        <View style={styles.emptyContainer}>
          <View style={styles.emptyIconCircle}>
            <Ionicons name="business-outline" size={48} color={Colors.primary} />
          </View>
          <Text style={styles.emptyTitle}>Aucune ferme associée</Text>
          <Text style={styles.emptySub}>
            Créez votre première exploitation pour commencer à enregistrer vos animaux et colliers.
          </Text>
          <TouchableOpacity
            style={styles.createFarmBtn}
            onPress={() => setShowCreateModal(true)}
            activeOpacity={0.8}
          >
            <Ionicons name="add-circle-outline" size={20} color="#fff" />
            <Text style={styles.createFarmBtnText}>Créer une exploitation</Text>
          </TouchableOpacity>
        </View>
      ) : (
        <ScrollView contentContainerStyle={styles.content}>
          {/* Onboarding Quicklink Banner */}
          <TouchableOpacity
            style={styles.onboardingBanner}
            onPress={() => navigation.navigate('FarmOnboarding')}
            activeOpacity={0.85}
          >
            <View style={styles.bannerIconCircle}>
              <Ionicons name="checkbox-outline" size={22} color={Colors.primary} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={styles.bannerTitle}>Guide de mise en route</Text>
              <Text style={styles.bannerSubtitle}>
                Vérifier les étapes de configuration (animaux, colliers, zones)
              </Text>
            </View>
            <Ionicons name="chevron-forward" size={20} color={Colors.text.muted} />
          </TouchableOpacity>

          <View style={styles.card}>
            <View style={styles.farmIcon}>
              <Ionicons name="home" size={32} color={Colors.primary} />
            </View>

            {editing ? (
              <>
                {[
                  { label: 'Nom de la ferme', key: 'name' },
                  { label: 'Adresse / Localisation', key: 'address' },
                  { label: 'Superficie (ha)', key: 'size_hectares', numeric: true },
                ].map(({ label, key, numeric }) => (
                  <View key={key} style={styles.field}>
                    <Text style={styles.fieldLabel}>{label}</Text>
                    <TextInput
                      style={styles.input}
                      value={form[key as keyof typeof form]}
                      onChangeText={(v) => setForm((p) => ({ ...p, [key]: v }))}
                      keyboardType={numeric ? 'decimal-pad' : 'default'}
                      placeholderTextColor={Colors.text.muted}
                    />
                  </View>
                ))}
                <TouchableOpacity style={styles.saveBtn} onPress={handleSave} disabled={saving}>
                  {saving ? <ActivityIndicator color="#fff" /> : <Text style={styles.saveBtnText}>Enregistrer</Text>}
                </TouchableOpacity>
                <TouchableOpacity
                  style={styles.cancelBtn}
                  onPress={() => setEditing(false)}
                  disabled={saving}
                >
                  <Text style={styles.cancelText}>Annuler</Text>
                </TouchableOpacity>
              </>
            ) : (
              <>
                {[
                  { label: 'Nom', value: farm?.name, icon: 'home-outline' },
                  { label: 'Adresse', value: farm?.address, icon: 'location-outline' },
                  {
                    label: 'Superficie',
                    value: farm?.size_hectares ? `${farm.size_hectares} ha` : '-',
                    icon: 'resize-outline',
                  },
                  {
                    label: 'Rôle sur l’exploitation',
                    value: farm?.membership_role ? String(farm.membership_role).toUpperCase() : 'MEMBRE',
                    icon: 'shield-checkmark-outline',
                  },
                  {
                    label: 'Créée le',
                    value: farm?.created_at
                      ? new Date(farm.created_at).toLocaleDateString('fr-FR')
                      : '-',
                    icon: 'calendar-outline',
                  },
                ].map(({ label, value, icon }) => (
                  <View key={label} style={styles.infoRow}>
                    <Ionicons name={icon as any} size={16} color={Colors.text.muted} />
                    <Text style={styles.infoLabel}>{label}</Text>
                    <Text style={styles.infoValue}>{value ?? '-'}</Text>
                  </View>
                ))}
              </>
            )}
          </View>
        </ScrollView>
      )}

      {/* Farm creation modal */}
      <FarmCreateModal
        visible={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        onSuccess={async (newFarm) => {
          await loadFarms();
          await selectFarm(newFarm.id);
          navigation.navigate('FarmOnboarding');
        }}
      />
    </DrawerScreenBase>
  );
}

const styles = StyleSheet.create({
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  content: { padding: Spacing.base },
  emptyContainer: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: Spacing.xl,
  },
  emptyIconCircle: {
    width: 80,
    height: 80,
    borderRadius: 40,
    backgroundColor: Colors.primary + '18',
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: Spacing.base,
  },
  emptyTitle: {
    fontSize: Typography.lg,
    fontWeight: '700',
    color: Colors.text.primary,
    marginBottom: Spacing.xs,
    textAlign: 'center',
  },
  emptySub: {
    fontSize: Typography.sm,
    color: Colors.text.secondary,
    textAlign: 'center',
    lineHeight: 20,
    marginBottom: Spacing.lg,
  },
  createFarmBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.xs,
    backgroundColor: Colors.primary,
    paddingHorizontal: Spacing.lg,
    paddingVertical: Spacing.md,
    borderRadius: Radius.md,
  },
  createFarmBtnText: {
    color: '#fff',
    fontSize: Typography.base,
    fontWeight: '700',
  },
  onboardingBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.sm,
    backgroundColor: Colors.primary + '14',
    borderColor: Colors.primary + '30',
    borderWidth: 1,
    borderRadius: Radius.lg,
    padding: Spacing.md,
    marginBottom: Spacing.base,
  },
  bannerIconCircle: {
    width: 40,
    height: 40,
    borderRadius: Radius.full,
    backgroundColor: Colors.primary + '25',
    alignItems: 'center',
    justifyContent: 'center',
  },
  bannerTitle: {
    fontSize: Typography.sm,
    fontWeight: '700',
    color: Colors.text.primary,
  },
  bannerSubtitle: {
    fontSize: Typography.xs,
    color: Colors.text.secondary,
    marginTop: 2,
  },
  card: {
    backgroundColor: Colors.bg.card,
    borderRadius: Radius.lg,
    padding: Spacing.base,
    borderWidth: 1,
    borderColor: Colors.border.default,
  },
  farmIcon: {
    width: 64,
    height: 64,
    borderRadius: 32,
    backgroundColor: Colors.primary + '20',
    alignItems: 'center',
    justifyContent: 'center',
    alignSelf: 'center',
    marginBottom: Spacing.base,
  },
  infoRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.sm,
    paddingVertical: Spacing.sm,
    borderBottomWidth: 1,
    borderBottomColor: Colors.border.default,
  },
  infoLabel: { flex: 1, fontSize: Typography.sm, color: Colors.text.muted },
  infoValue: { fontSize: Typography.sm, fontWeight: '600', color: Colors.text.primary },
  editBtn: {
    width: 36,
    height: 36,
    borderRadius: Radius.full,
    backgroundColor: Colors.primary + '20',
    alignItems: 'center',
    justifyContent: 'center',
  },
  addBtn: {
    width: 36,
    height: 36,
    borderRadius: Radius.full,
    backgroundColor: Colors.primary,
    alignItems: 'center',
    justifyContent: 'center',
  },
  field: { marginBottom: Spacing.md },
  fieldLabel: { fontSize: Typography.sm, color: Colors.text.secondary, marginBottom: 4 },
  input: {
    backgroundColor: Colors.bg.input,
    borderRadius: Radius.md,
    borderWidth: 1,
    borderColor: Colors.border.default,
    paddingHorizontal: Spacing.md,
    paddingVertical: Spacing.sm,
    color: Colors.text.primary,
    fontSize: Typography.base,
  },
  saveBtn: {
    backgroundColor: Colors.primary,
    borderRadius: Radius.md,
    padding: Spacing.md,
    alignItems: 'center',
    marginTop: Spacing.lg,
  },
  saveBtnText: { color: '#fff', fontSize: Typography.base, fontWeight: '600' },
  cancelBtn: { alignItems: 'center', marginTop: Spacing.sm, padding: Spacing.sm },
  cancelText: { color: Colors.text.muted, fontSize: Typography.sm },
});
