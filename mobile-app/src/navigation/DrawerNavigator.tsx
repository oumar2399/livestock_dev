/**
 * DrawerNavigator - Menu latéral
 * Architecture :
 *   DrawerNavigator (overlay)
 *   └── AppStack (NativeStack)
 *       ├── HomeTabs (BottomTabs) ← écran principal avec tabs
 *       ├── Farm, Users, Devices...← écrans secondaires sans tabs
 *
 * Le drawer reste accessible depuis tous les écrans via
 * DrawerActions.openDrawer() ou swipe depuis la gauche.
 */
import React, { useEffect } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, ScrollView, Alert,
} from 'react-native';
import {
  createDrawerNavigator,
  DrawerContentComponentProps,
} from '@react-navigation/drawer';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useQueryClient } from '@tanstack/react-query';

import { Colors, Spacing, Typography, Radius } from '../constants/config';
import { useAuthStore } from '../store/authStore';
import { useFarmStore } from '../store/farmStore';

import MainNavigator    from './MainNavigator';
import FarmScreen       from '../screens/drawer/FarmScreen';
import UsersScreen      from '../screens/drawer/UsersScreen';
import DevicesScreen    from '../screens/drawer/DevicesScreen';
import GeofenceScreen   from '../screens/drawer/GeofenceScreen';
import ReportsScreen    from '../screens/drawer/ReportsScreen';
import VetOptionsScreen from '../screens/drawer/VetOptionsScreen';
import SettingsScreen   from '../screens/drawer/SettingsScreen';
import AIAssistantScreen from '../screens/drawer/AIAssistantScreen';
import MarketplaceScreen from '../screens/drawer/MarketplaceScreen';
import HistoryScreen from '../screens/drawer/HistoryScreen';
import VideoMonitoring from '../screens/drawer/VideoMonitoring';
import AppServSettings from '../screens/drawer/AppServSettings';

// ─── AppStack ─────────────────────────────────────────────────────────────────
// Stack qui contient HomeTabs + tous les écrans secondaires.
// Étant dans le DrawerNavigator, le drawer reste accessible partout.

const AppStack = createNativeStackNavigator();

function AppStackNavigator() {
  return (
    <AppStack.Navigator screenOptions={{ headerShown: false }}>
      <AppStack.Screen name="HomeTabs"    component={MainNavigator} />
      <AppStack.Screen name="Farm"        component={FarmScreen} />
      <AppStack.Screen name="Users"       component={UsersScreen} />
      <AppStack.Screen name="Devices"     component={DevicesScreen} />
      <AppStack.Screen name="Geofence"    component={GeofenceScreen} />
      <AppStack.Screen name="Reports"     component={ReportsScreen} />
      <AppStack.Screen name="VetOptions"  component={VetOptionsScreen} />
      <AppStack.Screen name="Settings"    component={SettingsScreen} />
      <AppStack.Screen name="Chatbot"     component={AIAssistantScreen} />
      <AppStack.Screen name="Marketplace" component={MarketplaceScreen} />
      <AppStack.Screen name="History"     component={HistoryScreen} />
      <AppStack.Screen name="VideoMonitoring" component={VideoMonitoring} />
      <AppStack.Screen name="AppServSettings" component={AppServSettings} />
    </AppStack.Navigator>
  );
}
// ─── Menu structure ───────────────────────────────────────────────────────────

const SECTIONS = [
  {
    title: 'Farm',
    items: [
      { label: 'Herd',         icon: 'paw-outline',           route: 'HomeTabs' },
      { label: 'Farm Management',    icon: 'home-outline',          route: 'Farm' },
      { label: 'Devices M5Stack',  icon: 'hardware-chip-outline', route: 'Devices' },
      { label: 'Video Monitoring', icon: 'videocam-outline',       route: 'VideoMonitoring', preview: true },
    ],
  },
  {
    title: 'Team & Services',
    items: [
      { label: 'Users',          icon: 'people-outline', route: 'Users' },
      { label: 'Vet Options',  icon: 'medkit-outline', route: 'VetOptions' },
    ],
  },
  {
    title: 'Land',
    items: [
      { label: 'Geofence', icon: 'map-outline', route: 'Geofence' },
    ],
  },
  {
    title: 'Data & Analytics',
    items: [
      { label: 'Reports / Exports', icon: 'bar-chart-outline', route: 'Reports' },
      { label: 'History', icon: 'time-outline', route: 'History' },
    ],
  },
  {
    title: 'Services',
    items: [
      { label: 'AI Assistant', icon: 'chatbubble-ellipses-outline', route: 'Chatbot',     preview: true },
      { label: 'Marketplace',  icon: 'storefront-outline',          route: 'Marketplace', preview: true },
      { label: 'App & Serveur', icon: 'server-outline',             route: 'AppServSettings' },
    ],
  },
];

const ROLE_LABELS: Record<string, string> = {
  farmer: 'Farmer', owner: 'Owner', vet: 'Veterinarian', admin: 'Admin',
};
const ROLE_COLORS: Record<string, string> = {
  farmer: Colors.primary, owner: '#3498DB', vet: '#9B59B6', admin: '#E74C3C',
};

// ─── Contenu drawer ───────────────────────────────────────────────────────────

function DrawerContent(props: DrawerContentComponentProps) {
  const insets = useSafeAreaInsets();
  const { user, role, logout } = useAuthStore();
  const queryClient = useQueryClient();
  const { farms, currentFarmId, selectFarm, clear: clearFarms } = useFarmStore();
  const currentFarm = farms.find((farm) => farm.id === currentFarmId) ?? null;
  const currentRole = role === 'admin' ? 'admin' : currentFarm?.membership_role;

  const go = (route: string) => {
    props.navigation.closeDrawer();
    setTimeout(() => props.navigation.navigate('App', { screen: route } as any), 100);
  };
  const handleFarmChange = async (farmId: number) => {
    if (farmId === currentFarmId) return;
    if (await selectFarm(farmId)) {
      queryClient.clear();
      go('HomeTabs');
    }
  };
  const handleLogout = () => {
    Alert.alert('Logout', 'Do you want to logout?', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Logout',
        style: 'destructive',
        onPress: async () => {
          queryClient.clear();
          await clearFarms();
          await logout();
        },
      },
    ]);
  };

  return (
    <View style={[styles.drawer, { paddingTop: insets.top }]}>
      {/* Profil */}
      <View style={styles.profile}>
        <View style={styles.avatar}>
          <Text style={styles.avatarText}>
            {(user?.name ?? user?.email ?? '?')[0].toUpperCase()}
          </Text>
        </View>
        <View style={{ flex: 1 }}>
          <Text style={styles.profileName} numberOfLines={1}>
            {user?.name ?? 'User'}
          </Text>
          <Text style={styles.profileEmail} numberOfLines={1}>
            {user?.email}
          </Text>
          {currentRole && (
            <View style={[styles.roleBadge, { backgroundColor: (ROLE_COLORS[currentRole] ?? Colors.primary) + '20' }]}>
              <Text style={[styles.roleText, { color: ROLE_COLORS[currentRole] ?? Colors.primary }]}>
                {ROLE_LABELS[currentRole] ?? currentRole}
              </Text>
            </View>
          )}
        </View>
      </View>

      {/* Menu */}
      <ScrollView style={{ flex: 1 }} showsVerticalScrollIndicator={false}>
        {farms.length > 0 && (
          <View style={styles.farmSection}>
            <Text style={styles.sectionTitle}>Current Farm</Text>
            {farms.map((farm) => {
              const active = farm.id === currentFarmId;
              return (
                <TouchableOpacity
                  key={farm.id}
                  style={[styles.farmItem, active && styles.farmItemActive]}
                  onPress={() => handleFarmChange(farm.id)}
                  activeOpacity={0.7}
                >
                  <Ionicons
                    name={active ? 'business' : 'business-outline'}
                    size={19}
                    color={active ? Colors.primary : Colors.text.secondary}
                  />
                  <Text style={[styles.farmName, active && styles.farmNameActive]} numberOfLines={1}>
                    {farm.name}
                  </Text>
                  {active && <Ionicons name="checkmark" size={18} color={Colors.primary} />}
                </TouchableOpacity>
              );
            })}
          </View>
        )}
        {SECTIONS.map((section) => (
          <View key={section.title} style={styles.section}>
            <Text style={styles.sectionTitle}>{section.title}</Text>
            {section.items.map((item) => (
              <TouchableOpacity
                key={item.route}
                style={styles.item}
                onPress={() => go(item.route)}
                activeOpacity={0.7}
              >
                <Ionicons name={item.icon as any} size={20} color={Colors.text.secondary} />
                <Text style={styles.itemLabel}>{item.label}</Text>
                {'preview' in item && item.preview && (
                  <View style={styles.soon}>
                    <Text style={styles.soonText}>Preview</Text>
                  </View>
                )}
              </TouchableOpacity>
            ))}
          </View>
        ))}
      </ScrollView>

      {/* Footer */}
      <View style={[styles.footer, { paddingBottom: insets.bottom + Spacing.sm }]}>
        <TouchableOpacity style={styles.footerItem} onPress={() => go('Settings')}>
          <Ionicons name="settings-outline" size={20} color={Colors.text.secondary} />
          <Text style={styles.footerText}>Settings</Text>
        </TouchableOpacity>
        <TouchableOpacity style={styles.footerItem} onPress={handleLogout}>
          <Ionicons name="log-out-outline" size={20} color={Colors.severity.critical} />
          <Text style={[styles.footerText, { color: Colors.severity.critical }]}>Logout</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

// ─── Export ───────────────────────────────────────────────────────────────────

const Drawer = createDrawerNavigator();

export default function DrawerNavigator() {
  const loadFarms = useFarmStore((state) => state.loadFarms);

  useEffect(() => {
    loadFarms();
  }, [loadFarms]);

  return (
    <Drawer.Navigator
      drawerContent={(props) => <DrawerContent {...props} />}
      screenOptions={{
        headerShown: false,
        drawerType: 'front',
        drawerStyle: { width: 300, backgroundColor: Colors.bg.card },
        overlayColor: 'rgba(0,0,0,0.55)',
        swipeEdgeWidth: 50,
      }}
    >
      <Drawer.Screen name="App" component={AppStackNavigator} />
    </Drawer.Navigator>
  );
}

// ─── Styles ──────────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
  drawer: { flex: 1, backgroundColor: Colors.bg.card },
  profile: {
    flexDirection: 'row', alignItems: 'center', gap: Spacing.md,
    padding: Spacing.base, paddingBottom: Spacing.md,
    borderBottomWidth: 1, borderBottomColor: Colors.border.default,
  },
  avatar: {
    width: 50, height: 50, borderRadius: 25,
    backgroundColor: Colors.primary + '20', borderWidth: 2,
    borderColor: Colors.primary + '40', alignItems: 'center', justifyContent: 'center',
  },
  avatarText:   { fontSize: 20, fontWeight: '700', color: Colors.primary },
  profileName:  { fontSize: Typography.base, fontWeight: '700', color: Colors.text.primary },
  profileEmail: { fontSize: Typography.xs, color: Colors.text.muted, marginTop: 2 },
  roleBadge: {
    alignSelf: 'flex-start', marginTop: 4,
    paddingHorizontal: 8, paddingVertical: 2, borderRadius: Radius.full,
  },
  roleText: { fontSize: Typography.xs, fontWeight: '700' },

  farmSection: {
    paddingTop: Spacing.md,
    paddingBottom: Spacing.xs,
    borderBottomWidth: 1,
    borderBottomColor: Colors.border.default,
  },
  farmItem: {
    minHeight: 42,
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.sm,
    marginHorizontal: Spacing.sm,
    paddingHorizontal: Spacing.md,
    borderRadius: Radius.md,
  },
  farmItemActive: { backgroundColor: Colors.primary + '15' },
  farmName: { flex: 1, fontSize: Typography.sm, color: Colors.text.secondary },
  farmNameActive: { color: Colors.primary, fontWeight: '700' },

  section: { paddingTop: Spacing.md },
  sectionTitle: {
    fontSize: Typography.xs, fontWeight: '700', color: Colors.text.muted,
    textTransform: 'uppercase', letterSpacing: 0.8,
    paddingHorizontal: Spacing.base, paddingBottom: Spacing.xs,
  },
  item: {
    flexDirection: 'row', alignItems: 'center', gap: Spacing.md,
    paddingHorizontal: Spacing.base, paddingVertical: Spacing.sm + 2,
    marginHorizontal: Spacing.sm, borderRadius: Radius.md,
  },
  itemLabel: { flex: 1, fontSize: Typography.base, color: Colors.text.secondary },
  soon: {
    backgroundColor: Colors.severity.warning + '20',
    paddingHorizontal: 6, paddingVertical: 2, borderRadius: Radius.full,
  },
  soonText: { fontSize: 10, color: Colors.severity.warning, fontWeight: '700' },

  footer: { borderTopWidth: 1, borderTopColor: Colors.border.default, padding: Spacing.sm, gap: 2 },
  footerItem: {
    flexDirection: 'row', alignItems: 'center', gap: Spacing.md,
    paddingHorizontal: Spacing.md, paddingVertical: Spacing.sm, borderRadius: Radius.md,
  },
  footerText: { fontSize: Typography.base, color: Colors.text.secondary },
});
