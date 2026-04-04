/**
 * MainNavigator - Bottom tab navigation
 * ☰ hamburger en haut à gauche sur tous les écrans principaux
 * ← retour sur écrans profonds (AnimalDetail, AnimalForm)
 */
import React from 'react';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { View, Text, StyleSheet, TouchableOpacity } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useNavigation, DrawerActions } from '@react-navigation/native';

import { MainTabParamList, AnimalsStackParamList, AlertsStackParamList } from '../types';
import { Colors, Spacing, Typography } from '../constants/config';
import { useActiveAlerts } from '../hooks/useAlerts';

import DashboardScreen  from '../screens/DashboardScreen';
import MapScreen        from '../screens/MapScreen';
import AnimalsListScreen from '../screens/AnimalsListScreen';
import AnimalDetailScreen from '../screens/AnimalDetailScreen';
import AnimalFormScreen  from '../screens/AnimalFormScreen';
import AlertsListScreen  from '../screens/AlertsListScreen';
import ProfileScreen     from '../screens/ProfileScreen';

// ─── Bouton hamburger ─────────────────────────────────────────────────────────

function HamburgerButton() {
  const navigation = useNavigation<any>();
  return (
    <TouchableOpacity
      onPress={() => navigation.dispatch(DrawerActions.openDrawer())}
      hitSlop={12}
      style={{ padding: 4, marginLeft: 8 }}
    >
      <Ionicons name="menu-outline" size={26} color={Colors.text.primary} />
    </TouchableOpacity>
  );
}

// ─── Stacks ───────────────────────────────────────────────────────────────────

const AnimalsStack = createNativeStackNavigator<AnimalsStackParamList>();
function AnimalsNavigator() {
  return (
    <AnimalsStack.Navigator screenOptions={{ headerShown: false }}>
      <AnimalsStack.Screen name="AnimalsList"  component={AnimalsListScreen} />
      <AnimalsStack.Screen name="AnimalDetail" component={AnimalDetailScreen} />
      <AnimalsStack.Screen name="AnimalForm"   component={AnimalFormScreen} />
    </AnimalsStack.Navigator>
  );
}

const AlertsStack = createNativeStackNavigator<AlertsStackParamList>();
function AlertsNavigator() {
  return (
    <AlertsStack.Navigator screenOptions={{ headerShown: false }}>
      <AlertsStack.Screen name="AlertsList" component={AlertsListScreen} />
    </AlertsStack.Navigator>
  );
}

// ─── Badge aleres ────────────────────────────────────────────────────────────
function AlertsBadge({ count }: { count: number }) {
  if (count <= 0) return null;
  return (
    <View style={styles.badge}>
      <Text style={styles.badgeText}>{count > 99 ? '99+' : count}</Text>
    </View>
  );
}

// ─── Tab Navigator ────────────────────────────────────────────────────────────

const Tab = createBottomTabNavigator<MainTabParamList>();

const TAB_TITLES: Record<string, string> = {
  Dashboard: 'Dashboard',
  Alerts:    'Alerts',
  Profile:   'Profile',
};

export default function MainNavigator() {
  const { data: alertsData } = useActiveAlerts();
  const unresolvedCount = alertsData?.unresolved_count ?? 0;

  return (
    <Tab.Navigator
      screenOptions={({ route }) => ({
        // Header natif avec ☰ pour Dashboard, Alerts, Profile
        headerShown: !!TAB_TITLES[route.name],
        headerStyle: styles.tabHeader,
        headerTitleStyle: styles.tabHeaderTitle,
        headerShadowVisible: false,
        headerTitle: TAB_TITLES[route.name] ?? '',
        headerLeft: () => <HamburgerButton />,

        // Tab bar
        tabBarStyle: styles.tabBar,
        tabBarActiveTintColor: Colors.primary,
        tabBarInactiveTintColor: Colors.text.muted,
        tabBarLabelStyle: styles.tabLabel,
        tabBarIcon: ({ color, size, focused }) => {
          const icons: Record<string, [string, string]> = {
            Dashboard: ['grid',          'grid-outline'],
            Map:       ['map',           'map-outline'],
            Animals:   ['paw',           'paw-outline'],
            Alerts:    ['notifications', 'notifications-outline'],
            Profile:   ['person',        'person-outline'],
          };
          const [active, inactive] = icons[route.name] ?? ['help-circle', 'help-circle-outline'];
          return <Ionicons name={(focused ? active : inactive) as any} size={size} color={color} />;
        },
      })}
    >
      <Tab.Screen
        name="Dashboard"
        component={DashboardScreen}
        options={{ tabBarLabel: 'Home' }}
      />
      {/* Map : header géré par MapScreen lui-même (overlay transparent) */}
      <Tab.Screen
        name="Map"
        component={MapScreen}
        options={{ tabBarLabel: 'Map', headerShown: false }}
      />
      {/* Troupeau : header géré par AnimalsListScreen (ScreenHeader component) */}
      <Tab.Screen
        name="Animals"
        component={AnimalsNavigator}
        options={{ tabBarLabel: 'Herd', headerShown: false }}
      />
      <Tab.Screen
        name="Alerts"
        component={AlertsNavigator}
        options={{
          tabBarLabel: 'Alerts',
          tabBarBadge: unresolvedCount > 0 ? unresolvedCount : undefined,
          tabBarBadgeStyle: styles.tabBadge,
        }}
      />
      <Tab.Screen
        name="Profile"
        component={ProfileScreen}
        options={{ tabBarLabel: 'Profile' }}
      />
    </Tab.Navigator>
  );
}

// ─── Styles ──────────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
  tabHeader: {
    backgroundColor: Colors.bg.primary,
    borderBottomWidth: 1,
    borderBottomColor: Colors.border.default,
    elevation: 0,
  },
  tabHeaderTitle: {
    fontSize: Typography.md,
    fontWeight: '700',
    color: Colors.text.primary,
  },
  tabBar: {
    backgroundColor: Colors.bg.card,
    borderTopColor: Colors.border.default,
    borderTopWidth: 1,
    paddingBottom: 4,
    paddingTop: 6,
    height: 62,
  },
  tabLabel: {
    fontSize: Typography.xs,
    fontWeight: '500',
  },
  tabBadge: {
    backgroundColor: Colors.severity.critical,
    fontSize: 10,
    fontWeight: '700',
  },
  badge: {
    position: 'absolute',
    top: -4,
    right: -8,
    backgroundColor: Colors.severity.critical,
    borderRadius: 9,
    minWidth: 18,
    height: 18,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 4,
  },
  badgeText: {
    color: '#fff',
    fontSize: 10,
    fontWeight: '700',
  },
});