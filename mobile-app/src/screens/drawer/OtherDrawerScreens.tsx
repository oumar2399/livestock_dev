import React from 'react';
import { View, Text, StyleSheet, ScrollView } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import DrawerScreenBase, { ComingSoonPlaceholder } from './DrawerScreenBase';
import { Colors, Spacing, Typography, Radius } from '../../constants/config';

// ─── VetOptionsScreen ─────────────────────────────────────────────────────────

export function VetOptionsScreen() {
  const options = [
    { icon: 'thermometer-outline',   title: 'Temperature Tracking',     desc: 'History and fever alerts' },
    { icon: 'pulse-outline',          title: 'Health Alerts',           desc: 'Inactivity, abnormal behavior' },
    { icon: 'document-text-outline', title: 'Medical Records',        desc: 'Notes and treatments per animal' },
    { icon: 'calendar-outline',      title: 'Post-Treatment Follow-up',   desc: 'Reminders and treatment tracking' },
    { icon: 'analytics-outline',     title: 'Health Trends',         desc: 'Behavioral analysis with ML' },
  ];

  return (
    <DrawerScreenBase title="Veterinary Options">
      <ScrollView contentContainerStyle={styles.content}>
        {options.map((opt) => (
          <View key={opt.title} style={styles.card}>
            <View style={styles.optIcon}>
              <Ionicons name={opt.icon as any} size={24} color={Colors.primary} />
            </View>
            <View style={styles.optInfo}>
              <Text style={styles.optTitle}>{opt.title}</Text>
              <Text style={styles.optDesc}>{opt.desc}</Text>
            </View>
            <View style={styles.soonBadge}>
              <Text style={styles.soonText}>Soon</Text>
            </View>
          </View>
        ))}
      </ScrollView>
    </DrawerScreenBase>
  );
}

// ─── GeofenceScreen ───────────────────────────────────────────────────────────
export function GeofenceScreen() {
  return (
    <DrawerScreenBase title="Zones Geofencing">
      <ComingSoonPlaceholder feature="Geofencing" />
    </DrawerScreenBase>
  );
}

// ─── ReportsScreen ────────────────────────────────────────────────────────────
export function ReportsScreen() {
  const reports = [
    { icon: 'bar-chart-outline',  title: 'Activity Report',    desc: 'Behaviors over 7/30 days' },
    { icon: 'location-outline',   title: 'GPS Report',          desc: 'Distances traveled, frequently visited areas' },
    { icon: 'battery-half-outline', title: 'Devices Report',   desc: 'Battery levels, availability' },
    { icon: 'alert-circle-outline', title: 'Alerts Report',   desc: 'History and resolution of alerts' },
    { icon: 'download-outline',   title: 'Export CSV',           desc: 'Export raw data' },
  ];

  return (
    <DrawerScreenBase title="Reports & Exports">
      <ScrollView contentContainerStyle={styles.content}>
        {reports.map((r) => (
          <View key={r.title} style={styles.card}>
            <View style={styles.optIcon}>
              <Ionicons name={r.icon as any} size={24} color='#3498DB' />
            </View>
            <View style={styles.optInfo}>
              <Text style={styles.optTitle}>{r.title}</Text>
              <Text style={styles.optDesc}>{r.desc}</Text>
            </View>
            <View style={[styles.soonBadge, { backgroundColor: '#3498DB20' }]}>
              <Text style={[styles.soonText, { color: '#3498DB' }]}>Soon</Text>
            </View>
          </View>
        ))}
      </ScrollView>
    </DrawerScreenBase>
  );
}

// ─── SettingsScreen ───────────────────────────────────────────────────────────
export function SettingsScreen() {
  return (
    <DrawerScreenBase title="Paramètres">
      <ScrollView contentContainerStyle={styles.content}>
        <Text style={styles.sectionTitle}>Connexion</Text>
        {[
          { label: 'API Server',         value: 'config.ts → API_BASE_URL' },
          { label: 'Request Timeout',    value: '15 seconds' },
          { label: 'Map Refresh',        value: '10 seconds' },
          { label: 'Alerts Refresh',     value: '15 seconds' },
          { label: 'Dashboard Refresh',  value: '30 seconds' },
        ].map(({ label, value }) => (
          <View key={label} style={styles.settingRow}>
            <Text style={styles.settingLabel}>{label}</Text>
            <Text style={styles.settingValue}>{value}</Text>
          </View>
        ))}

        <Text style={styles.sectionTitle}>Alert Thresholds</Text>
        {[
          { label: 'Battery Warning',    value: '< 20%' },
          { label: 'Battery Critical',   value: '< 10%' },
          { label: 'Device Offline',      value: '> 30 min' },
          { label: 'Inactivity Alert',   value: '< 30% pendant 6h' },
          { label: 'Herd Isolation',  value: '> 3 km du centre' },
        ].map(({ label, value }) => (
          <View key={label} style={styles.settingRow}>
            <Text style={styles.settingLabel}>{label}</Text>
            <Text style={styles.settingValue}>{value}</Text>
          </View>
        ))}

        <Text style={styles.sectionTitle}>Application</Text>
        {[
          { label: 'Version',   value: '2.0.0' },
          { label: 'Backend',   value: 'FastAPI + PostgreSQL' },
          { label: 'Hardware',  value: 'M5Stack ESP32 + GPS NEO-M8N' },
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

// ─── Styles partagés ─────────────────────────────────────────────────────────

const styles = StyleSheet.create({
  content: { padding: Spacing.base, gap: Spacing.sm },
  card: {
    flexDirection: 'row', alignItems: 'center',
    backgroundColor: Colors.bg.card, borderRadius: Radius.lg,
    padding: Spacing.md, gap: Spacing.md,
    borderWidth: 1, borderColor: Colors.border.default,
  },
  optIcon: {
    width: 48, height: 48, borderRadius: 24,
    backgroundColor: Colors.primary + '15',
    alignItems: 'center', justifyContent: 'center',
  },
  optInfo: { flex: 1 },
  optTitle: { fontSize: Typography.base, fontWeight: '600', color: Colors.text.primary },
  optDesc:  { fontSize: Typography.xs, color: Colors.text.muted, marginTop: 2 },
  soonBadge: {
    backgroundColor: Colors.severity.warning + '20',
    paddingHorizontal: 7, paddingVertical: 3, borderRadius: Radius.full,
  },
  soonText: { fontSize: 10, color: Colors.severity.warning, fontWeight: '700' },
  sectionTitle: {
    fontSize: Typography.xs, fontWeight: '700', color: Colors.text.muted,
    textTransform: 'uppercase', letterSpacing: 0.8,
    marginTop: Spacing.md, marginBottom: Spacing.xs,
  },
  settingRow: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
    backgroundColor: Colors.bg.card, borderRadius: Radius.md,
    paddingHorizontal: Spacing.md, paddingVertical: Spacing.sm,
    borderWidth: 1, borderColor: Colors.border.default,
  },
  settingLabel: { fontSize: Typography.sm, color: Colors.text.secondary },
  settingValue: { fontSize: Typography.sm, fontWeight: '600', color: Colors.text.primary },
});