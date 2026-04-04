import React from 'react';
import { View, Text, StyleSheet, ScrollView } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import DrawerScreenBase, { ComingSoonPlaceholder } from './DrawerScreenBase';
import { Colors, Spacing, Typography, Radius } from '../../constants/config';

// ─── VetOptionsScreen ─────────────────────────────────────────────────────────
export default function VetOptionsScreen() {
  const options = [
    { icon: 'thermometer-outline',   title: 'Temperature Monitoring',     desc: 'History and fever alerts' },
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