import { create } from 'zustand';
import AsyncStorage from '@react-native-async-storage/async-storage';

import apiClient from '../api/client';
import { FarmAccess } from '../types';
import { getSessionEpoch, withSessionStorage } from './sessionLifecycle';


const CURRENT_FARM_KEY = '@livestock/current_farm_id';
let farmRequest = 0;

interface FarmState {
  farms: FarmAccess[];
  currentFarmId: number | null;
  isLoading: boolean;
  error: string | null;
  loadFarms: () => Promise<void>;
  selectFarm: (farmId: number) => Promise<boolean>;
  clear: () => Promise<void>;
}

export const useFarmStore = create<FarmState>((set, get) => ({
  farms: [],
  currentFarmId: null,
  isLoading: false,
  error: null,

  loadFarms: async () => {
    const request = ++farmRequest;
    const epoch = getSessionEpoch();
    const isCurrent = () => request === farmRequest && epoch === getSessionEpoch();
    set({ isLoading: true, error: null });
    try {
      const { data } = await apiClient.get<FarmAccess[]>('/farms/');
      if (!isCurrent()) return;
      const selected = await withSessionStorage(async () => {
        if (!isCurrent()) return null;
        const savedValue = await AsyncStorage.getItem(CURRENT_FARM_KEY);
        if (!isCurrent()) return null;
        const savedId = savedValue ? Number(savedValue) : null;
        const farm = data.find((item) => item.id === savedId) ?? data[0] ?? null;
        if (farm) {
          await AsyncStorage.setItem(CURRENT_FARM_KEY, String(farm.id));
        } else {
          await AsyncStorage.removeItem(CURRENT_FARM_KEY);
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
    await withSessionStorage(async () => {
      if (isCurrent()) await AsyncStorage.setItem(CURRENT_FARM_KEY, String(farmId));
    });
    if (!isCurrent()) return false;
    set({ currentFarmId: farmId, isLoading: false });
    return true;
  },

  clear: async () => {
    ++farmRequest;
    set({ farms: [], currentFarmId: null, isLoading: false, error: null });
    await withSessionStorage(() => AsyncStorage.removeItem(CURRENT_FARM_KEY));
  },
}));
