import { create } from 'zustand';
import AsyncStorage from '@react-native-async-storage/async-storage';

import apiClient from '../api/client';
import { queryClient } from '../api/queryClient';
import { FarmAccess } from '../types';
import { clearAllOfflineCache } from '../utils/offlineCache';
import { getSessionEpoch, withSessionStorage } from './sessionLifecycle';


// One remembered farm per user. The old phone-wide key is only ever removed.
const LEGACY_FARM_KEY = '@livestock/current_farm_id';
export const farmKeyFor = (userId: number) => `${LEGACY_FARM_KEY}:${userId}`;
let farmRequest = 0;

export interface FarmUser {
  id: number;
  isAdmin: boolean;
}

interface FarmState {
  user: FarmUser | null;
  farms: FarmAccess[];
  currentFarmId: number | null;
  isLoading: boolean;
  error: string | null;
  setUser: (user: FarmUser | null) => void;
  loadFarms: () => Promise<void>;
  selectFarm: (farmId: number) => Promise<boolean>;
  clear: () => Promise<void>;
}

export const useFarmStore = create<FarmState>((set, get) => ({
  user: null,
  farms: [],
  currentFarmId: null,
  isLoading: false,
  error: null,

  setUser: (user) => set({ user }),

  loadFarms: async () => {
    const request = ++farmRequest;
    const epoch = getSessionEpoch();
    const isCurrent = () => request === farmRequest && epoch === getSessionEpoch();
    const user = get().user;
    set({ isLoading: true, error: null });
    try {
      const { data } = await apiClient.get<FarmAccess[]>('/farms/');
      if (!isCurrent()) return;
      const selected = await withSessionStorage(async () => {
        if (!isCurrent()) return null;
        await AsyncStorage.removeItem(LEGACY_FARM_KEY);
        if (!user) return null;
        const key = farmKeyFor(user.id);
        const savedValue = await AsyncStorage.getItem(key);
        if (!isCurrent()) return null;
        const savedId = savedValue ? Number(savedValue) : null;
        // Only a farm still in this user's list is restored. With nothing saved the
        // admin starts with no farm (never an arbitrary real farm); others get their first.
        const farm = data.find((item) => item.id === savedId) ?? (user.isAdmin ? null : data[0] ?? null);
        if (farm) {
          await AsyncStorage.setItem(key, String(farm.id));
        } else if (savedValue !== null) {
          await AsyncStorage.removeItem(key);
        }
        return farm;
      });
      if (!isCurrent()) return;

      set({ farms: data, currentFarmId: selected?.id ?? null, isLoading: false });
    } catch {
      if (!isCurrent()) return;
      set({ farms: [], currentFarmId: null, isLoading: false, error: 'Unable to load farms' });
    }
  },

  selectFarm: async (farmId: number) => {
    if (!get().farms.some((farm) => farm.id === farmId)) return false;
    const request = ++farmRequest;
    const epoch = getSessionEpoch();
    const isCurrent = () => request === farmRequest && epoch === getSessionEpoch();
    const user = get().user;
    await withSessionStorage(async () => {
      if (isCurrent() && user) await AsyncStorage.setItem(farmKeyFor(user.id), String(farmId));
    });
    if (!isCurrent()) return false;
    const changed = get().currentFarmId !== farmId;
    // Drop the previous farm's data before any screen can render it under the new farm.
    if (changed) queryClient.clear();
    set({ currentFarmId: farmId, isLoading: false });
    // Outside withSessionStorage: the purge takes the same storage queue itself.
    if (changed) await clearAllOfflineCache();
    return true;
  },

  // Session change (login, logout): forget the in-memory state only. Each user's
  // remembered farm stays saved and is checked against their farm list on next load.
  clear: async () => {
    ++farmRequest;
    set({ user: null, farms: [], currentFarmId: null, isLoading: false, error: null });
  },
}));
