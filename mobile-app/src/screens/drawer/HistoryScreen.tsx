import React from 'react';
import { View, Text, StyleSheet, ScrollView } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import DrawerScreenBase, { ComingSoonPlaceholder } from './DrawerScreenBase';
import { Colors, Spacing, Typography, Radius } from '../../constants/config';

// ─── HistoryScreen ───────────────────────────────────────────────────────────
export default function HistoryScreen() {
  return (
    <DrawerScreenBase title="Farm History">
      <ComingSoonPlaceholder feature="History" />
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