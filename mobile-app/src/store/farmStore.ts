import { create } from 'zustand';
import AsyncStorage from '@react-native-async-storage/async-storage';

import apiClient from '../api/client';
import { FarmAccess } from '../types';


const CURRENT_FARM_KEY = '@livestock/current_farm_id';

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
    set({ isLoading: true, error: null });
    try {
      const { data } = await apiClient.get<FarmAccess[]>('/farms/');
      const savedValue = await AsyncStorage.getItem(CURRENT_FARM_KEY);
      const savedId = savedValue ? Number(savedValue) : null;
      const selected = data.find((farm) => farm.id === savedId) ?? data[0] ?? null;

      if (selected) {
        await AsyncStorage.setItem(CURRENT_FARM_KEY, String(selected.id));
      } else {
        await AsyncStorage.removeItem(CURRENT_FARM_KEY);
      }

      set({ farms: data, currentFarmId: selected?.id ?? null, isLoading: false });
    } catch {
      set({ farms: [], currentFarmId: null, isLoading: false, error: 'Unable to load farms' });
    }
  },

  selectFarm: async (farmId: number) => {
    if (!get().farms.some((farm) => farm.id === farmId)) return false;
    await AsyncStorage.setItem(CURRENT_FARM_KEY, String(farmId));
    set({ currentFarmId: farmId });
    return true;
  },

  clear: async () => {
    await AsyncStorage.removeItem(CURRENT_FARM_KEY);
    set({ farms: [], currentFarmId: null, isLoading: false, error: null });
  },
}));
