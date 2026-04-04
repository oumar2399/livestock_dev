/**
 * DrawerScreenBase - Base pour tous les écrans drawer
 * Header : ← retour | Titre | ☰ hamburger | action droite optionnelle
 */
import React from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, SafeAreaView, StatusBar, Platform,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useNavigation, DrawerActions } from '@react-navigation/native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Colors, Spacing, Typography, Radius } from '../../constants/config';

interface Props {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
  rightAction?: React.ReactNode;
  showBack?: boolean;
}

export default function DrawerScreenBase({
  title,
  subtitle,
  children,
  rightAction,
  showBack = true,
}: Props) {
  const navigation = useNavigation<any>();
  const insets = useSafeAreaInsets();

  return (
    <View style={styles.screen}>
      {/* Header avec padding SafeArea */}
      <View style={[styles.header, { paddingTop: insets.top + Spacing.sm }]}>
        {/* Bouton retour */}
        {showBack ? (
          <TouchableOpacity
            onPress={() => navigation.goBack()}
            hitSlop={12}
            style={styles.iconBtn}
          >
            <Ionicons name="arrow-back" size={24} color={Colors.text.primary} />
          </TouchableOpacity>
        ) : (
          <View style={styles.iconBtn} />
        )}

        {/* Titre + sous-titre */}
        <View style={styles.titleBlock}>
          <Text style={styles.title} numberOfLines={1}>{title}</Text>
          {subtitle && <Text style={styles.subtitle} numberOfLines={1}>{subtitle}</Text>}
        </View>

        {/* Action droite optionnelle */}
        {rightAction && <View style={styles.rightAction}>{rightAction}</View>}

        {/* Bouton hamburger ☰ */}
        <TouchableOpacity
          onPress={() => navigation.dispatch(DrawerActions.openDrawer())}
          hitSlop={12}
          style={styles.iconBtn}
        >
          <Ionicons name="menu-outline" size={26} color={Colors.text.primary} />
        </TouchableOpacity>
      </View>

      {/* Séparateur */}
      <View style={styles.separator} />

      {/* Contenu */}
      <View style={styles.content}>{children}</View>
    </View>
  );
}

export function ComingSoonPlaceholder({ feature }: { feature: string }) {
  return (
    <View style={styles.placeholder}>
      <View style={styles.placeholderIcon}>
        <Ionicons name="time-outline" size={48} color={Colors.text.muted} />
      </View>
      <Text style={styles.placeholderTitle}>{feature}</Text>
      <Text style={styles.placeholderText}>
        This feature is coming soon! We're working hard to bring it to you in a future update. Stay tuned!
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: Colors.bg.primary },

  header: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: Spacing.sm,
    paddingBottom: Spacing.sm,
    backgroundColor: Colors.bg.primary,
    gap: Spacing.xs,
  },
  iconBtn: {
    width: 44, height: 44,
    alignItems: 'center', justifyContent: 'center',
    borderRadius: Radius.full,
  },
  titleBlock: { flex: 1, paddingHorizontal: Spacing.xs },
  title: {
    fontSize: Typography.md, fontWeight: '700', color: Colors.text.primary,
  },
  subtitle: {
    fontSize: Typography.xs, color: Colors.text.muted, marginTop: 1,
  },
  rightAction: { marginRight: Spacing.xs },
  separator: {
    height: 1, backgroundColor: Colors.border.default,
    marginHorizontal: 0,
  },
  content: { flex: 1 },

  placeholder: {
    flex: 1, alignItems: 'center', justifyContent: 'center',
    padding: Spacing['2xl'], gap: Spacing.md,
  },
  placeholderIcon: {
    width: 88, height: 88, borderRadius: 44,
    backgroundColor: Colors.bg.elevated,
    alignItems: 'center', justifyContent: 'center', marginBottom: Spacing.sm,
  },
  placeholderTitle: {
    fontSize: Typography.lg, fontWeight: '700', color: Colors.text.primary, textAlign: 'center',
  },
  placeholderText: {
    fontSize: Typography.base, color: Colors.text.muted, textAlign: 'center', lineHeight: 22,
  },
});