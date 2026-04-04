/**
 * ProfileScreen - Paramètres et infos connexion
 */
import React from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  Alert,
  Linking,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';

import { useAuthStore } from '../../store/authStore';
import { Colors, Radius, Spacing, Typography } from '../../constants/config';
import { Config } from '../../constants/config';
import { ScreenHeader } from '../../components/ui';

// ─── Menu item ────────────────────────────────────────────────────────────────

interface MenuItemProps {
  icon: string;
  label: string;
  value?: string;
  onPress?: () => void;
  danger?: boolean;
  last?: boolean;
}

function MenuItem({ icon, label, value, onPress, danger, last }: MenuItemProps) {
  const color = danger ? Colors.severity.critical : Colors.text.primary;
  return (
    <TouchableOpacity
      style={[styles.menuItem, last && styles.menuItemLast]}
      onPress={onPress}
      disabled={!onPress}
      activeOpacity={0.7}
    >
      <View style={[styles.menuIconBg, { backgroundColor: (danger ? Colors.severity.critical : Colors.primary) + '18' }]}>
        <Ionicons name={icon as any} size={18} color={danger ? Colors.severity.critical : Colors.primary} />
      </View>
      <Text style={[styles.menuLabel, { color }]}>{label}</Text>
      {value && <Text style={styles.menuValue}>{value}</Text>}
      {onPress && !value && (
        <Ionicons name="chevron-forward" size={16} color={Colors.text.muted} />
      )}
    </TouchableOpacity>
  );
}


// ─── Screen ───────────────────────────────────────────────────────────────────

export default function ProfileScreen() {
  const insets = useSafeAreaInsets();
  const logout = useAuthStore((s) => s.logout);

  const handleLogout = () => {
    Alert.alert(
      'Logout',
      'Do you want to logout?',
      [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Logout', style: 'destructive', onPress: logout },
      ],
    );
  };

  const handleOpenDocs = () => {
    Linking.openURL(`${Config.API_BASE_URL.replace('/api/v1', '')}/docs`);
  };

  return (
    <View style={[styles.screen, { paddingTop: insets.top }]}>
      <ScreenHeader title="Profile & Settings" />

      <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
        {/* Avatar */}
        <View style={styles.avatarSection}>
          <View style={styles.avatar}>
            <Ionicons name="person" size={36} color={Colors.primary} />
          </View>
          <Text style={styles.avatarTitle}>Farmer</Text>
          <Text style={styles.avatarSub}>Livestock Monitoring v1.0</Text>
        </View>

        {/* Connexion */}
        <View style={styles.section}>
          <Text style={styles.sectionLabel}>CONNEXION</Text>
          <View style={styles.menuGroup}>
            <MenuItem
              icon="server-outline"
              label="API Server"
              value={Config.API_BASE_URL}
            />
            <MenuItem
              icon="document-text-outline"
              label="Documentation API"
              onPress={handleOpenDocs}
              last
            />
          </View>
        </View>

        {/* Paramètres temps réel */}
        <View style={styles.section}>
          <Text style={styles.sectionLabel}>ACTUALISATION</Text>
          <View style={styles.menuGroup}>
            <MenuItem
              icon="map-outline"
              label="Carte (positions)"
              value={`Toutes les ${Config.MAP_REFRESH_INTERVAL / 1000}s`}
            />
            <MenuItem
              icon="notifications-outline"
              label="Alerts"
              value={`Toutes les ${Config.ALERTS_REFRESH_INTERVAL / 1000}s`}
            />
            <MenuItem
              icon="grid-outline"
              label="Dashboard"
              value={`Toutes les ${Config.DASHBOARD_REFRESH_INTERVAL / 1000}s`}
              last
            />
          </View>
        </View>

        {/* Capteurs */}
        <View style={styles.section}>
          <Text style={styles.sectionLabel}>SEUILS COMPORTEMENT M5STACK</Text>
          <View style={styles.menuGroup}>
            <MenuItem icon="bed-outline" label="Lying" value="< 0.15 g" />
            <MenuItem icon="body-outline" label="Standing" value="0.15 – 0.5 g" />
            <MenuItem icon="walk-outline" label="Walking" value="0.5 – 1.0 g" />
            <MenuItem icon="fitness-outline" label="Running" value="> 1.0 g" last />
          </View>
        </View>

        {/* À propos */}
        <View style={styles.section}>
          <Text style={styles.sectionLabel}>À PROPOS</Text>
          <View style={styles.menuGroup}>
            <MenuItem icon="code-slash-outline" label="Version" value="1.0.0" />
            <MenuItem icon="school-outline" label="Projet" value="Master Recherche Japon" />
            <MenuItem icon="leaf-outline" label="Backend" value="FastAPI + PostgreSQL" last />
          </View>
        </View>

        {/* Déconnexion */}
        <View style={styles.section}>
          <View style={styles.menuGroup}>
            <MenuItem
              icon="log-out-outline"
              label="Se déconnecter"
              onPress={handleLogout}
              danger
              last
            />
          </View>
        </View>
      </ScrollView>
    </View>
  );
}

// ─── Styles ──────────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: Colors.bg.primary },
  content: { paddingBottom: Spacing['3xl'] },

  avatarSection: {
    alignItems: 'center',
    paddingVertical: Spacing['2xl'],
    paddingHorizontal: Spacing.base,
  },
  avatar: {
    width: 80,
    height: 80,
    borderRadius: Radius.full,
    backgroundColor: Colors.primaryMuted,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: Spacing.md,
    borderWidth: 2,
    borderColor: Colors.primary + '40',
  },
  avatarTitle: {
    fontSize: Typography.xl,
    fontWeight: '700',
    color: Colors.text.primary,
    marginBottom: 4,
  },
  avatarSub: { fontSize: Typography.sm, color: Colors.text.muted },

  section: { paddingHorizontal: Spacing.base, marginBottom: Spacing.base },
  sectionLabel: {
    fontSize: Typography.xs,
    fontWeight: '700',
    color: Colors.text.muted,
    letterSpacing: 1,
    marginBottom: Spacing.sm,
    marginLeft: 4,
  },
  menuGroup: {
    backgroundColor: Colors.bg.card,
    borderRadius: Radius.xl,
    borderWidth: 1,
    borderColor: Colors.border.default,
    overflow: 'hidden',
  },
  menuItem: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: Spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: Colors.border.default,
    gap: Spacing.md,
  },
  menuItemLast: { borderBottomWidth: 0 },
  menuIconBg: {
    width: 34,
    height: 34,
    borderRadius: Radius.md,
    alignItems: 'center',
    justifyContent: 'center',
  },
  menuLabel: { flex: 1, fontSize: Typography.base, fontWeight: '500' },
  menuValue: { fontSize: Typography.sm, color: Colors.text.muted, maxWidth: 160, textAlign: 'right' },
});
