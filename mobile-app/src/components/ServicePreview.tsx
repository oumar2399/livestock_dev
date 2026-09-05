import React, { useState } from 'react';
import { Modal, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Colors, Typography } from '../constants/config';
import { useFarmStore } from '../store/farmStore';
import DrawerScreenBase from '../screens/drawer/DrawerScreenBase';

type IconName = React.ComponentProps<typeof Ionicons>['name'];

export function PreviewScreen({ title, children }: { title: string; children: React.ReactNode }) {
  const farm = useFarmStore((state) => state.farms.find((item) => item.id === state.currentFarmId));
  return (
    <DrawerScreenBase title={title} subtitle={farm?.name}>
      <View style={styles.status}>
        <Ionicons name="flask-outline" size={16} color={Colors.severity.warning} />
        <Text style={styles.statusTitle}>Preview</Text>
        <Text style={styles.statusDetail}>Service not connected</Text>
      </View>
      {farm ? <React.Fragment key={farm.id}>{children}</React.Fragment> : (
        <PreviewEmptyState icon="business-outline" title="No farm selected" />
      )}
    </DrawerScreenBase>
  );
}

export function PreviewTabs<T extends string>({ options, value, onChange }: {
  options: readonly { value: T; label: string }[];
  value: T;
  onChange: (value: T) => void;
}) {
  return (
    <View style={styles.tabs}>
      {options.map((option) => (
        <Pressable key={option.value} accessibilityRole="tab" accessibilityLabel={option.label}
          accessibilityState={{ selected: value === option.value }}
          onPress={() => onChange(option.value)}
          style={[styles.tab, value === option.value && styles.activeTab]}>
          <Text style={[styles.tabText, value === option.value && styles.activeText]}>{option.label}</Text>
        </Pressable>
      ))}
    </View>
  );
}

export function PreviewIconButton({ icon, label, onPress, disabled = false, selected = false }: {
  icon: IconName; label: string; onPress?: () => void; disabled?: boolean; selected?: boolean;
}) {
  const [tooltip, setTooltip] = useState(false);
  return (
    <View style={styles.iconContainer}>
      <Pressable accessibilityRole="button" accessibilityLabel={label}
        accessibilityState={{ disabled, selected }} disabled={disabled} onPress={onPress}
        onHoverIn={() => setTooltip(true)} onHoverOut={() => setTooltip(false)}
        onLongPress={() => setTooltip(true)} onPressOut={() => setTooltip(false)}
        style={[styles.iconButton, selected && styles.selectedButton]}>
        <Ionicons name={icon} size={22}
          color={disabled ? Colors.text.muted : selected ? Colors.primaryLight : Colors.text.primary} />
      </Pressable>
      {tooltip && <View pointerEvents="none" style={styles.tooltip}><Text style={styles.tooltipText}>{label}</Text></View>}
    </View>
  );
}

export function PreviewEmptyState({ icon, title, detail }: { icon: IconName; title: string; detail?: string }) {
  return (
    <View style={styles.empty}>
      <Ionicons name={icon} size={32} color={Colors.text.muted} />
      <Text style={styles.emptyTitle}>{title}</Text>
      {detail && <Text style={styles.emptyDetail}>{detail}</Text>}
    </View>
  );
}

export function PreviewSheet({ title, onClose, children }: {
  title: string; onClose: () => void; children: React.ReactNode;
}) {
  const insets = useSafeAreaInsets();
  return (
    <Modal transparent animationType="slide" onRequestClose={onClose}>
      <View style={[styles.scrim, { paddingTop: insets.top + 16, paddingBottom: insets.bottom }]}>
        <Pressable accessibilityRole="button" accessibilityLabel="Dismiss details"
          onPress={onClose} style={StyleSheet.absoluteFillObject} />
        <View accessibilityViewIsModal style={styles.sheet}>
          <View style={styles.sheetHeader}>
            <Text style={styles.sheetTitle}>{title}</Text>
            <PreviewIconButton icon="close-outline" label="Close details" onPress={onClose} />
          </View>
          <ScrollView contentContainerStyle={styles.sheetContent}>{children}</ScrollView>
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  status: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: 8, paddingHorizontal: 16,
    paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: Colors.border.default },
  statusTitle: { color: Colors.severity.warning, fontSize: Typography.sm, fontWeight: '600' },
  statusDetail: { color: Colors.text.secondary, fontSize: Typography.sm, flexShrink: 1 },
  tabs: { flexDirection: 'row', borderBottomWidth: 1, borderBottomColor: Colors.border.default },
  tab: { flex: 1, minHeight: 48, paddingHorizontal: 8, paddingVertical: 12,
    alignItems: 'center', justifyContent: 'center', borderBottomWidth: 2, borderBottomColor: 'transparent' },
  activeTab: { borderBottomColor: Colors.primaryLight },
  tabText: { fontSize: Typography.sm, fontWeight: '600', color: Colors.text.secondary, textAlign: 'center' },
  activeText: { color: Colors.primaryLight },
  iconContainer: { position: 'relative', zIndex: 1 },
  iconButton: { width: 44, height: 44, alignItems: 'center', justifyContent: 'center', borderRadius: 8 },
  selectedButton: { backgroundColor: Colors.primaryMuted },
  tooltip: { position: 'absolute', top: 46, right: 0, width: 152, borderRadius: 6,
    backgroundColor: Colors.bg.elevated, padding: 8, zIndex: 10 },
  tooltipText: { color: Colors.text.primary, fontSize: Typography.xs, textAlign: 'center' },
  empty: { flexGrow: 1, alignItems: 'center', justifyContent: 'center', padding: 32, gap: 12 },
  emptyTitle: { color: Colors.text.primary, fontSize: Typography.base, fontWeight: '600', textAlign: 'center' },
  emptyDetail: { color: Colors.text.secondary, fontSize: Typography.sm, lineHeight: 20, textAlign: 'center' },
  scrim: { flex: 1, backgroundColor: Colors.overlay, alignItems: 'center', justifyContent: 'flex-end' },
  sheet: { width: '100%', maxWidth: 680, maxHeight: '95%', backgroundColor: Colors.bg.primary,
    borderTopLeftRadius: 8, borderTopRightRadius: 8, overflow: 'hidden' },
  sheetHeader: { flexDirection: 'row', alignItems: 'center', padding: 12,
    borderBottomWidth: 1, borderBottomColor: Colors.border.default },
  sheetTitle: { flex: 1, color: Colors.text.primary, fontSize: Typography.md, fontWeight: '600' },
  sheetContent: { padding: 16, gap: 16 },
});
