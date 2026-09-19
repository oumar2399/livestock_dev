/**
 * Store Auth - Zustand
 * Gestion authentification JWT, rôles, refresh token
 * Compatible avec POST /api/v1/auth/login du backend
 */
import { create } from 'zustand';
import AsyncStorage from '@react-native-async-storage/async-storage';
import apiClient, { ApiError } from '../api/client';
import { queryClient } from '../api/queryClient';
import { useFarmStore } from './farmStore';
import { advanceSessionEpoch, getSessionEpoch, withSessionStorage } from './sessionLifecycle';
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

const SIGNED_OUT = {
  isAuthenticated: false, isLoading: false, token: null, role: null, user: null, error: null,
};

let refreshInFlight: { epoch: number; promise: Promise<boolean> } | null = null;

function resetSession() {
  const epoch = advanceSessionEpoch();
  queryClient.clear();
  const cleanup = Promise.all([
    useFarmStore.getState().clear(),
    withSessionStorage(() => AsyncStorage.multiRemove(Object.values(STORAGE_KEYS))),
  ]);
  return { epoch, cleanup };
}

async function persistTokens(data: TokenResponse, epoch: number): Promise<boolean> {
  return withSessionStorage(async () => {
    if (epoch !== getSessionEpoch()) return false;
    await AsyncStorage.multiSet([
      [STORAGE_KEYS.ACCESS_TOKEN, data.access_token],
      [STORAGE_KEYS.REFRESH_TOKEN, data.refresh_token],
      [STORAGE_KEYS.USER_ROLE, data.user.role],
      [STORAGE_KEYS.USER_NAME, data.user.name ?? ''],
      [STORAGE_KEYS.USER_EMAIL, data.user.email],
    ]);
    return epoch === getSessionEpoch();
  });
}

const tokenState = (data: TokenResponse) => ({
  token: data.access_token, role: data.user.role, user: data.user,
  isAuthenticated: true, error: null,
});

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
    const epoch = getSessionEpoch();
    try {
      const results = await withSessionStorage(() => AsyncStorage.multiGet([
        STORAGE_KEYS.ACCESS_TOKEN,
        STORAGE_KEYS.REFRESH_TOKEN,
        STORAGE_KEYS.USER_ROLE,
        STORAGE_KEYS.USER_NAME,
        STORAGE_KEYS.USER_EMAIL,
      ]));
      if (epoch !== getSessionEpoch()) return;

      const savedToken = results[0][1];
      const savedRefreshToken = results[1][1];

      if (savedToken && savedRefreshToken) {
        const { data: profile } = await apiClient.get<UserProfile>('/auth/me');
        if (epoch !== getSessionEpoch()) return;
        const activeToken = await withSessionStorage(async () => {
          if (epoch !== getSessionEpoch()) return null;
          const token = await AsyncStorage.getItem(STORAGE_KEYS.ACCESS_TOKEN);
          if (epoch !== getSessionEpoch()) return null;
          await AsyncStorage.multiSet([
            [STORAGE_KEYS.USER_ROLE, profile.role],
            [STORAGE_KEYS.USER_NAME, profile.name ?? ''],
            [STORAGE_KEYS.USER_EMAIL, profile.email],
          ]);
          return token;
        });
        if (epoch !== getSessionEpoch()) return;
        if (!activeToken) {
          await get().logout();
          return;
        }
        set({
          isAuthenticated: true,
          token: activeToken,
          role: profile.role,
          user: profile,
          isLoading: false,
          error: null,
        });
      } else {
        await get().logout();
      }
    } catch (err) {
      if (epoch !== getSessionEpoch()) return;
      if (err instanceof ApiError && err.status === 401) {
        await get().logout();
      } else {
        // Keep credentials for a later verification; do not grant offline access.
        set({ isLoading: false, error: err instanceof Error ? err.message : 'Session verification unavailable' });
      }
    }
  },

  // ─── Login ────────────────────────────────────────────────────────────────

  login: async (credentials: LoginCredentials) => {
    const { epoch, cleanup } = resetSession();
    set({ ...SIGNED_OUT, isLoading: true });

    try {
      await cleanup;
      if (epoch !== getSessionEpoch()) return;
      // POST /api/v1/auth/login → body JSON avec email + password
      const { data } = await apiClient.post<TokenResponse>('/auth/login', {
        email: credentials.username,
        password: credentials.password,
      });

      if (await persistTokens(data, epoch) && epoch === getSessionEpoch()) {
        set({ ...tokenState(data), isLoading: false });
      }

    } catch (err) {
      if (epoch !== getSessionEpoch()) return;
      const message = err instanceof Error ? err.message : 'Email ou mot de passe incorrect';
      set({ error: message, isLoading: false });
    }
  },

  // ─── Refresh Token ────────────────────────────────────────────────────────

  refreshToken: (): Promise<boolean> => {
    const epoch = getSessionEpoch();
    if (refreshInFlight?.epoch === epoch) return refreshInFlight.promise;
    const promise = (async () => {
      try {
        const savedRefreshToken = await withSessionStorage(() => AsyncStorage.getItem(STORAGE_KEYS.REFRESH_TOKEN));
        if (epoch !== getSessionEpoch()) return false;
        if (!savedRefreshToken) {
          await get().logout();
          return false;
        }
        const { data } = await apiClient.post<TokenResponse>('/auth/refresh', {
          refresh_token: savedRefreshToken,
        });
        if (!(await persistTokens(data, epoch)) || epoch !== getSessionEpoch()) return false;
        set(tokenState(data));
        return true;
      } catch (err) {
        if (epoch !== getSessionEpoch()) return false;
        if (err instanceof ApiError && err.status === 401) {
          await get().logout();
          return false;
        }
        set({ error: err instanceof Error ? err.message : 'Session refresh unavailable' });
        // Propagate transient failures so a caller does not mistake them for a 401.
        throw err;
      }
    })();
    const pending = { epoch, promise };
    refreshInFlight = pending;
    const clear = () => { if (refreshInFlight === pending) refreshInFlight = null; };
    void promise.then(clear, clear);
    return promise;
  },

  // ─── Logout ───────────────────────────────────────────────────────────────

  logout: async () => {
    const { epoch, cleanup } = resetSession();
    set(SIGNED_OUT);
    try {
      await cleanup;
    } catch {
      if (epoch === getSessionEpoch()) set({ error: 'Unable to clear saved session' });
    }
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
