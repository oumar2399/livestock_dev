import React, { useState, useEffect } from 'react';
import {
  View, Text, StyleSheet, ScrollView,
  TextInput, TouchableOpacity, Alert, ActivityIndicator,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import DrawerScreenBase from './DrawerScreenBase';
import { Colors, Spacing, Typography, Radius } from '../../constants/config';
import apiClient from '../../api/client';

export default function FarmScreen() {
  const [farm, setFarm]       = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(false);
  const [form, setForm]       = useState({ name: '', address: '', size_hectares: '' });

  useEffect(() => {
    apiClient.get('/farms/1')
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
  }, []);

  const handleSave = async () => {
    try {
      await apiClient.put('/farms/1', {
        name: form.name,
        address: form.address,
        size_hectares: form.size_hectares ? parseFloat(form.size_hectares) : null,
      });
      setEditing(false);
      Alert.alert('Succès', 'Ferme mise à jour');
    } catch {
      Alert.alert('Erreur', 'Impossible de mettre à jour la ferme');
    }
  };

  return (
    <DrawerScreenBase
      title="Gestion ferme"
      rightAction={
        !loading && (
          <TouchableOpacity onPress={() => editing ? handleSave() : setEditing(true)} style={styles.editBtn}>
            <Ionicons name={editing ? 'checkmark' : 'create-outline'} size={20} color={Colors.primary} />
          </TouchableOpacity>
        )
      }
    >
      {loading ? (
        <View style={styles.center}><ActivityIndicator color={Colors.primary} /></View>
      ) : (
        <ScrollView contentContainerStyle={styles.content}>
          <View style={styles.card}>
            <View style={styles.farmIcon}>
              <Ionicons name="home" size={32} color={Colors.primary} />
            </View>

            {editing ? (
              <>
                {[
                  { label: 'Nom de la ferme', key: 'name' },
                  { label: 'Adresse', key: 'address' },
                  { label: 'Superficie (ha)', key: 'size_hectares', numeric: true },
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
                <TouchableOpacity style={styles.cancelBtn} onPress={() => setEditing(false)}>
                  <Text style={styles.cancelText}>Annuler</Text>
                </TouchableOpacity>
              </>
            ) : (
              <>
                {[
                  { label: 'Nom', value: farm?.name, icon: 'home-outline' },
                  { label: 'Adresse', value: farm?.address, icon: 'location-outline' },
                  { label: 'Superficie', value: farm?.size_hectares ? `${farm.size_hectares} ha` : '-', icon: 'resize-outline' },
                  { label: 'Propriétaire ID', value: farm?.owner_id ? `#${farm.owner_id}` : '-', icon: 'person-outline' },
                  { label: 'Créée le', value: farm?.created_at ? new Date(farm.created_at).toLocaleDateString('fr-FR') : '-', icon: 'calendar-outline' },
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
  cancelBtn: { alignItems: 'center', marginTop: Spacing.sm, padding: Spacing.sm },
  cancelText: { color: Colors.text.muted, fontSize: Typography.sm },
});