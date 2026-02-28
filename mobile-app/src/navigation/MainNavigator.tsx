/**
 * MainNavigator - Bottom tab navigation
 * 5 onglets : Dashboard, Carte, Animaux, Alertes, Profil
 * Badge dynamique sur l'onglet Alertes (unresolved_count)
 */
import React from 'react';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { View, Text, StyleSheet } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { MainTabParamList, AnimalsStackParamList, AlertsStackParamList } from '../types';
import { Colors, Spacing, Typography } from '../constants/config';
import { useActiveAlerts } from '../hooks/useAlerts';

// Screens
import DashboardScreen from '../screens/DashboardScreen';
import MapScreen from '../screens/MapScreen';
import AnimalsListScreen from '../screens/AnimalsListScreen';
import AnimalDetailScreen from '../screens/AnimalDetailScreen';
import AlertsListScreen from '../screens/AlertsListScreen';
import ProfileScreen from '../screens/ProfileScreen';

// ─── Stacks imbriqués ─────────────────────────────────────────────────────────

const AnimalsStack = createNativeStackNavigator<AnimalsStackParamList>();
function AnimalsNavigator() {
  return (
    <AnimalsStack.Navigator screenOptions={{ headerShown: false }}>
      <AnimalsStack.Screen name="AnimalsList" component={AnimalsListScreen} />
      <AnimalsStack.Screen name="AnimalDetail" component={AnimalDetailScreen} />
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

// ─── Badge composant ──────────────────────────────────────────────────────────

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

export default function MainNavigator() {
  const { data: alertsData } = useActiveAlerts();
  const unresolvedCount = alertsData?.unresolved_count ?? 0;

  return (
    <Tab.Navigator
      screenOptions={({ route }) => ({
        headerShown: false,
        tabBarStyle: styles.tabBar,
        tabBarActiveTintColor: Colors.primary,
        tabBarInactiveTintColor: Colors.text.muted,
        tabBarLabelStyle: styles.tabLabel,
        tabBarIcon: ({ color, size, focused }) => {
          const icons: Record<string, [string, string]> = {
            Dashboard: ['grid', 'grid-outline'],
            Map: ['map', 'map-outline'],
            Animals: ['paw', 'paw-outline'],
            Alerts: ['notifications', 'notifications-outline'],
            Profile: ['person', 'person-outline'],
          };
          const [active, inactive] = icons[route.name] ?? ['help-circle', 'help-circle-outline'];
          return <Ionicons name={(focused ? active : inactive) as any} size={size} color={color} />;
        },
      })}
    >
      <Tab.Screen name="Dashboard" component={DashboardScreen} options={{ tabBarLabel: 'Accueil' }} />
      <Tab.Screen name="Map" component={MapScreen} options={{ tabBarLabel: 'Carte' }} />
      <Tab.Screen name="Animals" component={AnimalsNavigator} options={{ tabBarLabel: 'Troupeau' }} />
      <Tab.Screen
        name="Alerts"
        component={AlertsNavigator}
        options={{
          tabBarLabel: 'Alertes',
          tabBarBadge: unresolvedCount > 0 ? unresolvedCount : undefined,
          tabBarBadgeStyle: styles.tabBadge,
        }}
      />
      <Tab.Screen name="Profile" component={ProfileScreen} options={{ tabBarLabel: 'Profil' }} />
    </Tab.Navigator>
  );
}

const styles = StyleSheet.create({
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
