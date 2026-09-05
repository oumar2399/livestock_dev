/**
 * Store Auth - Zustand
 * Gestion authentification JWT, rôles, refresh token
 * Compatible avec POST /api/v1/auth/login du backend
 */
import { create } from 'zustand';
import AsyncStorage from '@react-native-async-storage/async-storage';
import apiClient from '../api/client';
import { Config } from '../constants/config';
import { LoginCredentials } from '../types';

// ─── Storage Keys ─────────────────────────────────────────────────────────────

const STORAGE_KEYS = {
  ACCESS_TOKEN:  Config.STORAGE.ACCESS_TOKEN,
  REFRESH_TOKEN: Config.STORAGE.REFRESH_TOKEN,
  USER_ROLE:     Config.STORAGE.USER_ROLE,
  USER_NAME:     Config.STORAGE.USER_NAME,
  USER_EMAIL:    Config.STORAGE.USER_EMAIL,
} as const;

// ─── Types ────────────────────────────────────────────────────────────────────

export type UserRole = 'farmer' | 'owner' | 'vet' | 'admin';

export interface UserProfile {
  id: number;
  email: string;
  name: string | null;
  role: UserRole;
  phone: string | null;
}

// Correspond exactement à TokenResponse (schemas/auth.py backend)
interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: 'bearer';
  expires_in: number;
  user: UserProfile;
}

interface AuthState {
  isAuthenticated: boolean;
  isLoading: boolean;
  token: string | null;
  role: UserRole | null;
  user: UserProfile | null;
  error: string | null;

  // Actions
  login: (credentials: LoginCredentials) => Promise<void>;
  logout: () => Promise<void>;
  hydrate: () => Promise<void>;
  refreshToken: () => Promise<boolean>;
  clearError: () => void;

  // Helpers rôles - utilisés dans l'UI pour afficher/cacher des actions
  isAdmin: () => boolean;
  isFarmer: () => boolean;
  isVet: () => boolean;
  isOwner: () => boolean;
  canEdit: () => boolean;       // farmer ou admin → peut modifier/supprimer
  canViewHealth: () => boolean; // vet, farmer ou admin → données santé
}

// ─── Store ────────────────────────────────────────────────────────────────────

export const useAuthStore = create<AuthState>((set, get) => ({
  isAuthenticated: false,
  isLoading: true,  // true au départ, hydrate() le passera à false
  token: null,
  role: null,
  user: null,
  error: null,

  // ─── Hydrate : restaure la session depuis AsyncStorage au démarrage ───────

  hydrate: async () => {
    try {
      const results = await AsyncStorage.multiGet([
        STORAGE_KEYS.ACCESS_TOKEN,
        STORAGE_KEYS.REFRESH_TOKEN,
        STORAGE_KEYS.USER_ROLE,
        STORAGE_KEYS.USER_NAME,
        STORAGE_KEYS.USER_EMAIL,
      ]);

      const savedToken = results[0][1];
      const savedRefreshToken = results[1][1];

      if (savedToken && savedRefreshToken) {
        const { data: profile } = await apiClient.get<UserProfile>('/auth/me');
        const activeToken = await AsyncStorage.getItem(STORAGE_KEYS.ACCESS_TOKEN);
        await AsyncStorage.multiSet([
          [STORAGE_KEYS.USER_ROLE, profile.role],
          [STORAGE_KEYS.USER_NAME, profile.name ?? ''],
          [STORAGE_KEYS.USER_EMAIL, profile.email],
        ]);
        set({
          isAuthenticated: true,
          token: activeToken,
          role: profile.role,
          user: profile,
          isLoading: false,
        });
      } else {
        await get().logout();
      }
    } catch {
      await get().logout();
    }
  },

  // ─── Login ────────────────────────────────────────────────────────────────

  login: async (credentials: LoginCredentials) => {
    set({ isLoading: true, error: null });

    try {
      // POST /api/v1/auth/login → body JSON avec email + password
      const { data } = await apiClient.post<TokenResponse>('/auth/login', {
        email: credentials.username,
        password: credentials.password,
      });

      // Persister en AsyncStorage pour restaurer la session au prochain lancement
      await AsyncStorage.multiSet([
        [STORAGE_KEYS.ACCESS_TOKEN,  data.access_token],
        [STORAGE_KEYS.REFRESH_TOKEN, data.refresh_token],
        [STORAGE_KEYS.USER_ROLE,     data.user.role],
        [STORAGE_KEYS.USER_NAME,     data.user.name ?? ''],
        [STORAGE_KEYS.USER_EMAIL,    data.user.email],
      ]);

      set({
        isAuthenticated: true,
        token: data.access_token,
        role: data.user.role,
        user: data.user,
        isLoading: false,
        error: null,
      });

    } catch (err) {
      const message = err instanceof Error ? err.message : 'Email ou mot de passe incorrect';
      set({ error: message, isLoading: false });
    }
  },

  // ─── Refresh Token ────────────────────────────────────────────────────────

  refreshToken: async (): Promise<boolean> => {
    try {
      const savedRefreshToken = await AsyncStorage.getItem(STORAGE_KEYS.REFRESH_TOKEN);
      if (!savedRefreshToken) {
        await get().logout();
        return false;
      }

      const { data } = await apiClient.post<TokenResponse>('/auth/refresh', {
        refresh_token: savedRefreshToken,
      });

      await AsyncStorage.multiSet([
        [STORAGE_KEYS.ACCESS_TOKEN,  data.access_token],
        [STORAGE_KEYS.REFRESH_TOKEN, data.refresh_token],
        [STORAGE_KEYS.USER_ROLE,     data.user.role],
        [STORAGE_KEYS.USER_NAME,     data.user.name ?? ''],
        [STORAGE_KEYS.USER_EMAIL,    data.user.email],
      ]);

      set({
        token: data.access_token,
        role: data.user.role,
        user: data.user,
        isAuthenticated: true,
      });

      return true;

    } catch {
      // Refresh échoué (token expiré) → forcer reconnexion
      await get().logout();
      return false;
    }
  },

  // ─── Logout ───────────────────────────────────────────────────────────────

  logout: async () => {
    await AsyncStorage.multiRemove(Object.values(STORAGE_KEYS));
    set({
      isAuthenticated: false,
      token: null,
      role: null,
      user: null,
      error: null,
      isLoading: false,
    });
  },

  clearError: () => set({ error: null }),

  // ─── Helpers rôles ────────────────────────────────────────────────────────
  // Utilisés dans l'UI : if (canEdit()) → afficher bouton Supprimer

  isAdmin:       () => get().role === 'admin',
  isFarmer:      () => get().role === 'farmer',
  isVet:         () => get().role === 'vet',
  isOwner:       () => get().role === 'owner',
  canEdit:       () => ['farmer', 'admin'].includes(get().role ?? ''),
  canViewHealth: () => ['vet', 'farmer', 'admin'].includes(get().role ?? ''),
}));
