import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  Switch,
  TouchableOpacity,
  ActivityIndicator,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import DrawerScreenBase from './DrawerScreenBase';
import { Colors, Spacing, Typography, Radius } from '../../constants/config';
import {
  useNotificationPreferences,
  useUpdateNotificationPreferences,
} from '../../hooks/useNotifications';
import { useFarmStore } from '../../store/farmStore';

// ─── SettingsScreen ───────────────────────────────────────────────────────────
export default function SettingsScreen() {
  const currentFarmId = useFarmStore((state) => state.currentFarmId);
  const { data: preferencesList, isLoading: isPrefsLoading } = useNotificationPreferences();
  const updatePrefsMutation = useUpdateNotificationPreferences();

  // Préférence active (pour la ferme courante ou globale)
  const currentPref = preferencesList?.[0] || {
    enabled: true,
    min_severity: 'info' as const,
    categories: ['geofence', 'health', 'battery', 'offline'],
  };

  const [enabled, setEnabled] = useState<boolean>(currentPref.enabled);
  const [minSeverity, setMinSeverity] = useState<'info' | 'warning' | 'critical'>(
    currentPref.min_severity,
  );
  const [categories, setCategories] = useState<string[]>(currentPref.categories);

  useEffect(() => {
    if (preferencesList && preferencesList.length > 0) {
      setEnabled(preferencesList[0].enabled);
      setMinSeverity(preferencesList[0].min_severity);
      setCategories(preferencesList[0].categories);
    }
  }, [preferencesList]);

  const handleToggleCategory = (cat: string) => {
    const next = categories.includes(cat)
      ? categories.filter((c) => c !== cat)
      : [...categories, cat];
    setCategories(next);
    updatePrefsMutation.mutate({
      farm_id: currentFarmId,
      categories: next,
      min_severity: minSeverity,
      enabled,
    });
  };

  const handleToggleEnabled = (val: boolean) => {
    setEnabled(val);
    updatePrefsMutation.mutate({
      farm_id: currentFarmId,
      categories,
      min_severity: minSeverity,
      enabled: val,
    });
  };

  const handleSelectSeverity = (sev: 'info' | 'warning' | 'critical') => {
    setMinSeverity(sev);
    updatePrefsMutation.mutate({
      farm_id: currentFarmId,
      categories,
      min_severity: sev,
      enabled,
    });
  };

  return (
    <DrawerScreenBase title="Paramètres">
      <ScrollView contentContainerStyle={styles.content}>
        {/* Notifications */}
        <Text style={styles.sectionTitle}>Notifications Push</Text>
        <View style={styles.settingRow}>
          <View style={styles.rowLabelContainer}>
            <Ionicons name="notifications-outline" size={20} color={Colors.text.primary} />
            <Text style={styles.settingLabel}>Activer les alertes push</Text>
          </View>
          {isPrefsLoading ? (
            <ActivityIndicator size="small" color={Colors.primary} />
          ) : (
            <Switch
              value={enabled}
              onValueChange={handleToggleEnabled}
              trackColor={{ false: Colors.bg.elevated, true: Colors.primary }}
              thumbColor="#FFFFFF"
            />
          )}
        </View>

        {enabled && (
          <>
            <View style={styles.cardBlock}>
              <Text style={styles.subTitle}>Sévérité minimale</Text>
              <View style={styles.chipRow}>
                {(['info', 'warning', 'critical'] as const).map((sev) => {
                  const isSelected = minSeverity === sev;
                  return (
                    <TouchableOpacity
                      key={sev}
                      style={[
                        styles.chip,
                        isSelected && styles.chipSelected,
                      ]}
                      onPress={() => handleSelectSeverity(sev)}
                    >
                      <Text
                        style={[
                          styles.chipText,
                          isSelected && styles.chipTextSelected,
                        ]}
                      >
                        {sev.toUpperCase()}
                      </Text>
                    </TouchableOpacity>
                  );
                })}
              </View>
            </View>

            <View style={styles.cardBlock}>
              <Text style={styles.subTitle}>Catégories autorisées</Text>
              <View style={styles.categoryGrid}>
                {[
                  { id: 'geofence', label: 'Géofencing', icon: 'map-outline' },
                  { id: 'health', label: 'Santé / Activité', icon: 'fitness-outline' },
                  { id: 'battery', label: 'Batterie', icon: 'battery-charging-outline' },
                  { id: 'offline', label: 'Hors-ligne', icon: 'cloud-offline-outline' },
                ].map((item) => {
                  const isChecked = categories.includes(item.id);
                  return (
                    <TouchableOpacity
                      key={item.id}
                      style={[styles.catChip, isChecked && styles.catChipChecked]}
                      onPress={() => handleToggleCategory(item.id)}
                    >
                      <Ionicons
                        name={item.icon as any}
                        size={16}
                        color={isChecked ? Colors.primary : Colors.text.muted}
                      />
                      <Text
                        style={[
                          styles.catText,
                          isChecked && styles.catTextChecked,
                        ]}
                      >
                        {item.label}
                      </Text>
                    </TouchableOpacity>
                  );
                })}
              </View>
            </View>
          </>
        )}

        {/* Connexion */}
        <Text style={styles.sectionTitle}>Connexion</Text>
        {[
          { label: 'API Server', value: 'config.ts → API_BASE_URL' },
          { label: 'Request Timeout', value: '15 seconds' },
          { label: 'Map Refresh', value: '10 seconds' },
          { label: 'Alerts Refresh', value: '15 seconds' },
          { label: 'Dashboard Refresh', value: '30 seconds' },
        ].map(({ label, value }) => (
          <View key={label} style={styles.settingRow}>
            <Text style={styles.settingLabel}>{label}</Text>
            <Text style={styles.settingValue}>{value}</Text>
          </View>
        ))}

        {/* Seuils */}
        <Text style={styles.sectionTitle}>Seuils d'alerte</Text>
        {[
          { label: 'Battery Warning', value: '< 20%' },
          { label: 'Battery Critical', value: '< 10%' },
          { label: 'Device Offline', value: '> 30 min' },
          { label: 'Inactivity Alert', value: '< 30% pendant 6h' },
          { label: 'Herd Isolation', value: '> 3 km du centre' },
        ].map(({ label, value }) => (
          <View key={label} style={styles.settingRow}>
            <Text style={styles.settingLabel}>{label}</Text>
            <Text style={styles.settingValue}>{value}</Text>
          </View>
        ))}

        {/* Application */}
        <Text style={styles.sectionTitle}>Application</Text>
        {[
          { label: 'Version', value: '2.0.0' },
          { label: 'Backend', value: 'FastAPI + PostgreSQL' },
          { label: 'Hardware', value: 'M5Stack ESP32 + GPS NEO-M8N' },
        ].map(({ label, value }) => (
          <View key={label} style={styles.settingRow}>
            <Text style={styles.settingLabel}>{label}</Text>
            <Text style={styles.settingValue}>{value}</Text>
          </View>
        ))}
      </ScrollView>
    </DrawerScreenBase>
  );
}

// ─── Styles ──────────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
  content: { padding: Spacing.base, gap: Spacing.sm },
  sectionTitle: {
    fontSize: Typography.xs,
    fontWeight: '700',
    color: Colors.text.muted,
    textTransform: 'uppercase',
    letterSpacing: 0.8,
    marginTop: Spacing.md,
    marginBottom: Spacing.xs,
  },
  subTitle: {
    fontSize: Typography.xs,
    fontWeight: '600',
    color: Colors.text.secondary,
    marginBottom: Spacing.xs,
  },
  settingRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    backgroundColor: Colors.bg.card,
    borderRadius: Radius.md,
    paddingHorizontal: Spacing.md,
    paddingVertical: Spacing.sm,
    borderWidth: 1,
    borderColor: Colors.border.default,
  },
  rowLabelContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.sm,
  },
  settingLabel: { fontSize: Typography.sm, color: Colors.text.secondary },
  settingValue: { fontSize: Typography.sm, fontWeight: '600', color: Colors.text.primary },
  cardBlock: {
    backgroundColor: Colors.bg.card,
    borderRadius: Radius.md,
    padding: Spacing.md,
    borderWidth: 1,
    borderColor: Colors.border.default,
    gap: Spacing.xs,
  },
  chipRow: {
    flexDirection: 'row',
    gap: Spacing.sm,
    marginTop: Spacing.xs,
  },
  chip: {
    flex: 1,
    paddingVertical: Spacing.xs,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: Radius.sm,
    backgroundColor: Colors.bg.elevated,
    borderWidth: 1,
    borderColor: 'transparent',
  },
  chipSelected: {
    backgroundColor: Colors.primary + '25',
    borderColor: Colors.primary,
  },
  chipText: {
    fontSize: Typography.xs,
    fontWeight: '600',
    color: Colors.text.muted,
  },
  chipTextSelected: {
    color: Colors.primary,
  },
  categoryGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: Spacing.sm,
    marginTop: Spacing.xs,
  },
  catChip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingHorizontal: Spacing.sm,
    paddingVertical: Spacing.xs,
    borderRadius: Radius.sm,
    backgroundColor: Colors.bg.elevated,
    borderWidth: 1,
    borderColor: 'transparent',
  },
  catChipChecked: {
    backgroundColor: Colors.primary + '20',
    borderColor: Colors.primary,
  },
  catText: {
    fontSize: Typography.xs,
    color: Colors.text.muted,
  },
  catTextChecked: {
    color: Colors.text.primary,
    fontWeight: '600',
  },
});