/**
 * App.tsx - Point d'entrée principal
 * Providers : QueryClient, NavigationContainer, SafeArea
 */
import React, { useEffect } from 'react';
import { StatusBar } from 'expo-status-bar';
import { NavigationContainer } from '@react-navigation/native';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { StyleSheet } from 'react-native';

import RootNavigator from './src/navigation/RootNavigator';
import { useAuthStore } from './src/store/authStore';
import { Colors } from './src/constants/config';

// ─── React Query Client ───────────────────────────────────────────────────────

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 2,
      retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 30_000),
      // Ne pas refetch au focus si données < 10s
      staleTime: 10_000,
    },
    mutations: {
      retry: 1,
    },
  },
});

// ─── App ──────────────────────────────────────────────────────────────────────

export default function App() {
  const hydrate = useAuthStore((s) => s.hydrate);

  // Charger token depuis AsyncStorage au démarrage
  useEffect(() => {
    hydrate();
  }, []);

  return (
    <GestureHandlerRootView style={styles.root}>
      <SafeAreaProvider>
        <QueryClientProvider client={queryClient}>
          <NavigationContainer>
            <StatusBar style="light" backgroundColor={Colors.bg.primary} />
            <RootNavigator />
          </NavigationContainer>
        </QueryClientProvider>
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
});
