import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  ActivityIndicator,
  RefreshControl,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useNavigation } from '@react-navigation/native';
import { useQuery } from '@tanstack/react-query';

import DrawerScreenBase from './DrawerScreenBase';
import { Colors, Spacing, Typography, Radius } from '../../constants/config';
import { useAuthStore } from '../../store/authStore';
import { useFarmStore } from '../../store/farmStore';
import { useFarm } from '../../hooks/useFarms';
import { useAnimals } from '../../hooks/useAnimals';
import { useGeofences } from '../../hooks/useGeofences';
import apiClient from '../../api/client';
import { FarmMembershipList } from '../../types';
import FarmCreateModal from '../../components/FarmCreateModal';

interface StepItem {
  id: string;
  title: string;
  description: string;
  completed: boolean;
  completedDetail?: string;
  actionLabel: string;
  actionIcon: keyof typeof Ionicons.glyphMap;
  onPress: () => void;
}

export default function FarmOnboardingScreen() {
  const navigation = useNavigation<any>();
  const { currentFarmId, farms, loadFarms } = useFarmStore();
  const [createModalVisible, setCreateModalVisible] = useState(false);
  const canCreateFarm = useAuthStore((state) => state.role) === 'admin';

  // Queries for live server state
  const { data: farm, isLoading: farmLoading, refetch: refetchFarm } = useFarm(currentFarmId);
  const { data: animalsData, isLoading: animalsLoading, refetch: refetchAnimals } = useAnimals();
  const { data: geofences, isLoading: geofencesLoading, refetch: refetchGeofences } = useGeofences(currentFarmId);

  // Query members count
  const {
    data: membersData,
    isLoading: membersLoading,
    refetch: refetchMembers,
  } = useQuery({
    queryKey: ['farm-members-count', currentFarmId],
    queryFn: async () => {
      if (!currentFarmId) return null;
      const { data } = await apiClient.get<FarmMembershipList>(`/farms/${currentFarmId}/members`);
      return data;
    },
    enabled: currentFarmId !== null,
  });

  const isRefreshing = farmLoading || animalsLoading || geofencesLoading || membersLoading;

  const handleRefresh = async () => {
    await loadFarms();
    if (currentFarmId) {
      await Promise.all([
        refetchFarm(),
        refetchAnimals(),
        refetchGeofences(),
        refetchMembers(),
      ]);
    }
  };

  // Deducing completion strictly from live server state
  const hasFarm = currentFarmId !== null && !!farm;
  const animalsList = animalsData?.animals ?? [];
  const animalsCount = animalsList.length;
  const hasAnimals = animalsCount > 0;

  const assignedDevicesCount = animalsList.filter((a) => !!a.assigned_device).length;
  const hasCollar = assignedDevicesCount > 0;

  const geofencesCount = geofences?.length ?? 0;
  const hasGeofence = geofencesCount > 0;

  const membersCount = membersData?.members?.length ?? 1;
  const hasTeam = membersCount > 1;

  const steps: StepItem[] = [
    {
      id: 'farm',
      title: '1. Farm creation',
      description: 'Set the name, address and size of your farm.',
      completed: hasFarm,
      completedDetail: farm ? `${farm.name} (${farm.size_hectares ? `${farm.size_hectares} ha` : 'Size not provided'})` : undefined,
      actionLabel: hasFarm ? 'Edit' : 'Create my farm',
      actionIcon: hasFarm ? 'create-outline' : 'add-circle-outline',
      onPress: () => {
        if (hasFarm || !canCreateFarm) {
          // Only the admin creates farms; others open the farm screen (which explains it).
          navigation.navigate('Farm');
        } else {
          setCreateModalVisible(true);
        }
      },
    },
    {
      id: 'animals',
      title: '2. Register the first animal',
      description: 'Add cattle, sheep or goats to your herd to start tracking.',
      completed: hasAnimals,
      completedDetail: hasAnimals ? `${animalsCount} registered animal(s)` : undefined,
      actionLabel: hasAnimals ? 'View herd' : 'Add an animal',
      actionIcon: hasAnimals ? 'list-outline' : 'paw-outline',
      onPress: () => {
        if (hasAnimals) {
          navigation.navigate('HomeTabs', { screen: 'Animals' });
        } else {
          navigation.navigate('HomeTabs', {
            screen: 'Animals',
            params: { screen: 'AnimalForm' },
          });
        }
      },
    },
    {
      id: 'collar',
      title: '3. M5Stack collar association',
      description: 'Attach an authorized telemetry device to an animal to collect positions and activities.',
      completed: hasCollar,
      completedDetail: hasCollar ? `${assignedDevicesCount} equipped animal(s)` : undefined,
      actionLabel: 'Manage collars',
      actionIcon: 'hardware-chip-outline',
      onPress: () => navigation.navigate('Devices'),
    },
    {
      id: 'geofence',
      title: '4. Pasture & danger perimeters',
      description: 'Draw the allowed zones on the map to turn on automatic boundary-crossing alerts.',
      completed: hasGeofence,
      completedDetail: hasGeofence ? `${geofencesCount} configured zone(s)` : undefined,
      actionLabel: 'Set a zone',
      actionIcon: 'map-outline',
      onPress: () => navigation.navigate('Geofence'),
    },
    {
      id: 'team',
      title: '5. Team invitation',
      description: 'Add a shepherd or veterinarian to share access to alerts and tracking.',
      completed: hasTeam,
      completedDetail: hasTeam ? `${membersCount} active member(s)` : undefined,
      actionLabel: 'Manage members',
      actionIcon: 'people-outline',
      onPress: () => navigation.navigate('Users'),
    },
  ];

  const completedCount = steps.filter((s) => s.completed).length;
  const progressPct = Math.round((completedCount / steps.length) * 100);

  return (
    <DrawerScreenBase
      title="Setup guide"
      subtitle="Step-by-step setup"
    >
      <ScrollView
        style={styles.container}
        contentContainerStyle={styles.content}
        refreshControl={
          <RefreshControl
            refreshing={isRefreshing}
            onRefresh={handleRefresh}
            tintColor={Colors.primary}
          />
        }
      >
        {/* Progress Card */}
        <View style={styles.progressCard}>
          <View style={styles.progressHeader}>
            <View>
              <Text style={styles.progressTitle}>Setup progress</Text>
              <Text style={styles.progressSubtitle}>
                {completedCount} out of {steps.length} steps completed ({progressPct}%)
              </Text>
            </View>
            <View style={styles.progressBadge}>
              <Text style={styles.progressBadgeText}>{progressPct}%</Text>
            </View>
          </View>

          <View style={styles.progressBarBackground}>
            <View style={[styles.progressBarFill, { width: `${progressPct}%` }]} />
          </View>

          <Text style={styles.progressHint}>
            Each step is independent. You can leave and resume this guide at any time without losing anything.
          </Text>
        </View>

        {/* Steps Checklist */}
        <View style={styles.stepsList}>
          {steps.map((step, idx) => (
            <View
              key={step.id}
              style={[
                styles.stepCard,
                step.completed && styles.stepCardCompleted,
              ]}
            >
              <View style={styles.stepHeaderRow}>
                <View
                  style={[
                    styles.statusIndicator,
                    step.completed ? styles.indicatorDone : styles.indicatorPending,
                  ]}
                >
                  <Ionicons
                    name={step.completed ? 'checkmark-sharp' : 'ellipse-outline'}
                    size={16}
                    color={step.completed ? '#fff' : Colors.text.muted}
                  />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={[styles.stepTitle, step.completed && styles.stepTitleDone]}>
                    {step.title}
                  </Text>
                  {step.completed && step.completedDetail ? (
                    <Text style={styles.stepCompletedDetail}>
                      ✓ {step.completedDetail}
                    </Text>
                  ) : (
                    <Text style={styles.stepDescription}>{step.description}</Text>
                  )}
                </View>
              </View>

              <View style={styles.stepActionRow}>
                <TouchableOpacity
                  style={[
                    styles.stepActionBtn,
                    step.completed && styles.stepActionBtnCompleted,
                  ]}
                  onPress={step.onPress}
                  activeOpacity={0.8}
                >
                  <Ionicons
                    name={step.actionIcon}
                    size={16}
                    color={step.completed ? Colors.primary : '#fff'}
                  />
                  <Text
                    style={[
                      styles.stepActionText,
                      step.completed && styles.stepActionTextCompleted,
                    ]}
                  >
                    {step.actionLabel}
                  </Text>
                </TouchableOpacity>
              </View>
            </View>
          ))}
        </View>

        {/* Dashboard Shortcut CTA */}
        <View style={styles.bottomCtaContainer}>
          <TouchableOpacity
            style={styles.dashboardBtn}
            onPress={() => navigation.navigate('HomeTabs', { screen: 'Dashboard' })}
            activeOpacity={0.85}
          >
            <Ionicons name="speedometer-outline" size={20} color="#fff" />
            <Text style={styles.dashboardBtnText}>Go to Dashboard</Text>
          </TouchableOpacity>
        </View>
      </ScrollView>

      {/* Modal de création de ferme */}
      <FarmCreateModal
        visible={createModalVisible}
        onClose={() => setCreateModalVisible(false)}
        onSuccess={() => {
          handleRefresh();
        }}
      />
    </DrawerScreenBase>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.bg.primary,
  },
  content: {
    padding: Spacing.base,
    paddingBottom: Spacing.xl * 2,
  },
  progressCard: {
    backgroundColor: Colors.bg.card,
    borderRadius: Radius.lg,
    padding: Spacing.base,
    borderWidth: 1,
    borderColor: Colors.border.default,
    marginBottom: Spacing.base,
  },
  progressHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: Spacing.md,
  },
  progressTitle: {
    fontSize: Typography.base,
    fontWeight: '700',
    color: Colors.text.primary,
  },
  progressSubtitle: {
    fontSize: Typography.xs,
    color: Colors.text.secondary,
    marginTop: 2,
  },
  progressBadge: {
    paddingHorizontal: Spacing.sm,
    paddingVertical: 4,
    borderRadius: Radius.full,
    backgroundColor: Colors.primary + '20',
  },
  progressBadgeText: {
    fontSize: Typography.xs,
    fontWeight: '700',
    color: Colors.primary,
  },
  progressBarBackground: {
    height: 8,
    borderRadius: Radius.full,
    backgroundColor: Colors.bg.input,
    overflow: 'hidden',
    marginBottom: Spacing.sm,
  },
  progressBarFill: {
    height: '100%',
    backgroundColor: Colors.primary,
    borderRadius: Radius.full,
  },
  progressHint: {
    fontSize: Typography.xs,
    color: Colors.text.muted,
    lineHeight: 16,
  },
  stepsList: {
    gap: Spacing.sm,
    marginBottom: Spacing.base,
  },
  stepCard: {
    backgroundColor: Colors.bg.card,
    borderRadius: Radius.md,
    padding: Spacing.md,
    borderWidth: 1,
    borderColor: Colors.border.default,
  },
  stepCardCompleted: {
    borderColor: Colors.status.healthy + '40',
    backgroundColor: Colors.status.healthy + '08',
  },
  stepHeaderRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: Spacing.sm,
  },
  statusIndicator: {
    width: 26,
    height: 26,
    borderRadius: 13,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 2,
  },
  indicatorDone: {
    backgroundColor: Colors.status.healthy,
  },
  indicatorPending: {
    backgroundColor: Colors.bg.input,
    borderWidth: 1,
    borderColor: Colors.border.default,
  },
  stepTitle: {
    fontSize: Typography.sm,
    fontWeight: '700',
    color: Colors.text.primary,
    marginBottom: 4,
  },
  stepTitleDone: {
    color: Colors.text.primary,
  },
  stepDescription: {
    fontSize: Typography.xs,
    color: Colors.text.secondary,
    lineHeight: 16,
  },
  stepCompletedDetail: {
    fontSize: Typography.xs,
    fontWeight: '600',
    color: Colors.status.healthy,
  },
  stepActionRow: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    marginTop: Spacing.sm,
    paddingTop: Spacing.xs,
  },
  stepActionBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.xs,
    backgroundColor: Colors.primary,
    paddingHorizontal: Spacing.md,
    paddingVertical: Spacing.xs + 2,
    borderRadius: Radius.md,
  },
  stepActionBtnCompleted: {
    backgroundColor: Colors.primary + '18',
    borderWidth: 1,
    borderColor: Colors.primary + '40',
  },
  stepActionText: {
    fontSize: Typography.xs,
    fontWeight: '600',
    color: '#fff',
  },
  stepActionTextCompleted: {
    color: Colors.primary,
  },
  bottomCtaContainer: {
    marginTop: Spacing.sm,
  },
  dashboardBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: Spacing.sm,
    backgroundColor: Colors.primary,
    paddingVertical: Spacing.md,
    borderRadius: Radius.md,
    shadowColor: Colors.primary,
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.25,
    shadowRadius: 8,
    elevation: 3,
  },
  dashboardBtnText: {
    color: '#fff',
    fontSize: Typography.base,
    fontWeight: '700',
  },
});
