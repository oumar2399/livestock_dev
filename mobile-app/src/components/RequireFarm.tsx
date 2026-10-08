import React from 'react';
import { DrawerActions, useNavigation } from '@react-navigation/native';

import { useFarmStore } from '../store/farmStore';
import { EmptyState, LoadingState } from './ui';

/**
 * Farm-scoped tab screens render only once a farm is selected. The admin starts
 * with no farm (never an arbitrary real one), so these screens ask for a choice
 * instead of showing data from every farm.
 */
export function withFarm<P extends object>(Screen: React.ComponentType<P>) {
  function FarmScopedScreen(props: P) {
    const navigation = useNavigation();
    const { currentFarmId, isLoading } = useFarmStore();
    if (currentFarmId !== null) return <Screen {...props} />;
    if (isLoading) return <LoadingState message="Loading farms..." />;
    return (
      <EmptyState
        icon="business-outline"
        title="No farm selected"
        message="Choose a farm in the menu to see its herd, map and alerts."
        action={{ label: 'Open menu', onPress: () => navigation.dispatch(DrawerActions.openDrawer()) }}
      />
    );
  }
  FarmScopedScreen.displayName = `withFarm(${Screen.displayName ?? Screen.name ?? 'Screen'})`;
  return FarmScopedScreen;
}
