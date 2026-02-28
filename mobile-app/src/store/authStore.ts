/**
 * Store Auth - Zustand
 * Gestion authentification, token JWT, session
 *
 * NOTE : JWT "à venir" selon main.py
 * Ce store est prêt pour implémentation future :
 * - hydrate() charge le token depuis AsyncStorage au démarrage
 * - Pour l'instant l'app bypass le login si SKIP_AUTH=true
 */
import { create } from 'zustand';
import AsyncStorage from '@react-native-async-storage/async-storage';
import apiClient from '../api/client';
import { Config } from '../constants/config';
import { AuthTokens, LoginCredentials } from '../types';

// ─── Types ────────────────────────────────────────────────────────────────────

interface AuthState {
  isAuthenticated: boolean;
  isLoading: boolean;
  token: string | null;
  error: string | null;

  // Actions
  login: (credentials: LoginCredentials) => Promise<void>;
  logout: () => Promise<void>;
  hydrate: () => Promise<void>;
  clearError: () => void;
}

// ─── Constante dev : passer le login si auth pas encore implémentée ───────────
// Mettre à false quand le backend aura /auth/login
const BYPASS_AUTH_IN_DEV = __DEV__ && true;

// ─── Store ────────────────────────────────────────────────────────────────────

export const useAuthStore = create<AuthState>((set, get) => ({
  isAuthenticated: false,
  isLoading: false,
  token: null,
  error: null,

  /**
   * Charge le token depuis AsyncStorage au démarrage de l'app
   * Appelé dans App.tsx au mount
   */
  hydrate: async () => {
    // Mode développement : bypass auth
    if (BYPASS_AUTH_IN_DEV) {
      set({ isAuthenticated: true, isLoading: false });
      return;
    }

    try {
      const token = await AsyncStorage.getItem(Config.STORAGE.ACCESS_TOKEN);
      if (token) {
        set({ isAuthenticated: true, token, isLoading: false });
      } else {
        set({ isAuthenticated: false, isLoading: false });
      }
    } catch {
      set({ isAuthenticated: false, isLoading: false });
    }
  },

  /**
   * Login avec email/password
   * TODO: Activer quand POST /auth/login sera implémenté dans le backend
   */
  login: async (credentials: LoginCredentials) => {
    set({ isLoading: true, error: null });

    try {
      // FastAPI OAuth2PasswordRequestForm = form-data, pas JSON
      const formData = new URLSearchParams();
      formData.append('username', credentials.username);
      formData.append('password', credentials.password);

      const { data } = await apiClient.post<AuthTokens>('/auth/login', formData, {
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      });

      await AsyncStorage.setItem(Config.STORAGE.ACCESS_TOKEN, data.access_token);
      set({ isAuthenticated: true, token: data.access_token, isLoading: false });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Erreur de connexion';
      set({ error: message, isLoading: false });
    }
  },

  /**
   * Déconnexion - supprime token et réinitialise état
   */
  logout: async () => {
    await AsyncStorage.multiRemove([
      Config.STORAGE.ACCESS_TOKEN,
      Config.STORAGE.USER_PROFILE,
    ]);
    set({ isAuthenticated: false, token: null });
  },

  clearError: () => set({ error: null }),
}));
