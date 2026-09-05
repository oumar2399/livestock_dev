import React, { useState, useEffect } from 'react';
import {
  View, Text, StyleSheet, ScrollView,
  TextInput, TouchableOpacity, Alert, ActivityIndicator,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import DrawerScreenBase from './DrawerScreenBase';
import { Colors, Spacing, Typography, Radius } from '../../constants/config';
import apiClient from '../../api/client';
import { useFarmStore } from '../../store/farmStore';

export default function FarmScreen() {
  const { farms, currentFarmId, loadFarms } = useFarmStore();
  const currentFarm = farms.find((item) => item.id === currentFarmId) ?? null;
  const canManageFarm = currentFarm?.permissions.includes('manage_farm') ?? false;
  const [farm, setFarm]       = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(false);
  const [form, setForm]       = useState({ name: '', address: '', size_hectares: '' });
  const [saving, setSaving]   = useState(false);

  useEffect(() => {
    if (!currentFarmId) {
      setFarm(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    setEditing(false);
    apiClient.get(`/farms/${currentFarmId}`)
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
      Alert.alert('Success', 'Farm updated successfully');
      // Refresh farm data
      const { data } = await apiClient.get(`/farms/${currentFarmId}`);
      setFarm(data);
      await loadFarms();
    } catch {
      Alert.alert('Error', 'Cannot update farm');
    } finally {
      setSaving(false);
    }
  };

  return (
    <DrawerScreenBase
      title="Farm Management"
      rightAction={
        !loading && !editing && canManageFarm && (
          <TouchableOpacity onPress={() => setEditing(true)} style={styles.editBtn}>
            <Ionicons name="create-outline" size={20} color={Colors.primary} />
          </TouchableOpacity>
        )
      }
    >
      {loading ? (
        <View style={styles.center}><ActivityIndicator color={Colors.primary} /></View>
      ) : !farm ? (
        <View style={styles.center}>
          <Text style={styles.emptyText}>No farm assigned</Text>
        </View>
      ) : (
        <ScrollView contentContainerStyle={styles.content}>
          <View style={styles.card}>
            <View style={styles.farmIcon}>
              <Ionicons name="home" size={32} color={Colors.primary} />
            </View>

            {editing ? (
              <>
                {[
                  { label: 'Farm Name', key: 'name' },
                  { label: 'Address', key: 'address' },
                  { label: 'Size (ha)', key: 'size_hectares', numeric: true },
                ].map(({ label, key, numeric }) => (
                  <View key={key} style={styles.field}>
                    <Text style={styles.fieldLabel}>{label}</Text>
                    <TextInput
                      style={styles.input}
                      value={form[key as keyof typeof form]}
                      onChangeText={v => setForm(p => ({ ...p, [key]: v }))}
                      keyboardType={numeric ? 'decimal-pad' : 'default'}
                      placeholderTextColor={Colors.text.muted}
                    />
                  </View>
                ))}
                <TouchableOpacity style={styles.saveBtn} onPress={handleSave} disabled={saving}>
                  {saving ? <ActivityIndicator color="#fff" /> : <Text style={styles.saveBtnText}>Save</Text>}
                </TouchableOpacity>
                <TouchableOpacity style={styles.cancelBtn} onPress={() => setEditing(false)} disabled={saving}>
                  <Text style={styles.cancelText}>Cancel</Text>
                </TouchableOpacity>
              </>
            ) : (
              <>
                {[
                  { label: 'Name', value: farm?.name, icon: 'home-outline' },
                  { label: 'Address', value: farm?.address, icon: 'location-outline' },
                  { label: 'Size', value: farm?.size_hectares ? `${farm.size_hectares} ha` : '-', icon: 'resize-outline' },
                  { label: 'Owner ID', value: farm?.owner_id ? `#${farm.owner_id}` : '-', icon: 'person-outline' },
                  { label: 'Created at', value: farm?.created_at ? new Date(farm.created_at).toLocaleDateString('en-US') : '-', icon: 'calendar-outline' },
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
    </DrawerScreenBase>
  );
}

const styles = StyleSheet.create({
  center:  { flex: 1, alignItems: 'center', justifyContent: 'center' },
  emptyText: { fontSize: Typography.sm, color: Colors.text.muted },
  content: { padding: Spacing.base },
  card: {
    backgroundColor: Colors.bg.card,
    borderRadius: Radius.lg,
    padding: Spacing.base,
    borderWidth: 1,
    borderColor: Colors.border.default,
  },
  farmIcon: {
    width: 64, height: 64, borderRadius: 32,
    backgroundColor: Colors.primary + '20',
    alignItems: 'center', justifyContent: 'center',
    alignSelf: 'center', marginBottom: Spacing.base,
  },
  infoRow: {
    flexDirection: 'row', alignItems: 'center',
    gap: Spacing.sm, paddingVertical: Spacing.sm,
    borderBottomWidth: 1, borderBottomColor: Colors.border.default,
  },
  infoLabel: { flex: 1, fontSize: Typography.sm, color: Colors.text.muted },
  infoValue: { fontSize: Typography.sm, fontWeight: '600', color: Colors.text.primary },
  editBtn: {
    width: 36, height: 36, borderRadius: Radius.full,
    backgroundColor: Colors.primary + '20',
    alignItems: 'center', justifyContent: 'center',
  },
  field: { marginBottom: Spacing.md },
  fieldLabel: { fontSize: Typography.sm, color: Colors.text.secondary, marginBottom: 4 },
  input: {
    backgroundColor: Colors.bg.input, borderRadius: Radius.md,
    borderWidth: 1, borderColor: Colors.border.default,
    paddingHorizontal: Spacing.md, paddingVertical: Spacing.sm,
    color: Colors.text.primary, fontSize: Typography.base,
  },
  saveBtn: {
    backgroundColor: Colors.primary, borderRadius: Radius.md,
    padding: Spacing.md, alignItems: 'center', marginTop: Spacing.lg,
  },
  saveBtnText: { color: '#fff', fontSize: Typography.base, fontWeight: '600' },
  cancelBtn: { alignItems: 'center', marginTop: Spacing.sm, padding: Spacing.sm },
  cancelText: { color: Colors.text.muted, fontSize: Typography.sm },
});
