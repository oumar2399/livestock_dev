/**
 * Client HTTP - Axios configuré pour le backend FastAPI
 *
 * Fonctionnalités :
 * - Base URL configurable via Config.API_BASE_URL
 * - Injection automatique du token JWT dans les headers
 * - Gestion centralisée des erreurs HTTP
 * - Refresh token automatique (prêt pour implémentation future)
 * - Logging en développement
 */

import axios, {
  AxiosError,
  AxiosInstance,
  AxiosResponse,
  CanceledError,
  InternalAxiosRequestConfig,
  isCancel,
} from 'axios';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { Config } from '../constants/config';
import { getSessionEpoch, onSessionChange, withSessionStorage } from '../store/sessionLifecycle';

// ─── Types d'erreur ───────────────────────────────────────────────────────────

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly message: string,
    public readonly detail?: unknown,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

export class NetworkError extends Error {
  constructor() {
    super('Impossible de joindre le serveur. Vérifiez votre connexion réseau.');
    this.name = 'NetworkError';
  }
}

// ─── Création instance Axios ──────────────────────────────────────────────────

const apiClient: AxiosInstance = axios.create({
  baseURL: Config.API_BASE_URL,
  timeout: Config.REQUEST_TIMEOUT,
  headers: {
    'Content-Type': 'application/json',
    Accept: 'application/json',
    'ngrok-skip-browser-warning': 'true',
  },
});

interface RetryableRequestConfig extends InternalAxiosRequestConfig {
  _retry?: boolean;
  _sessionEpoch?: number;
}

// Axios copies defaults when a request is called, before its async interceptors.
const sessionDefaults = apiClient.defaults as typeof apiClient.defaults & { _sessionEpoch: number };
sessionDefaults._sessionEpoch = getSessionEpoch();
onSessionChange((epoch) => { sessionDefaults._sessionEpoch = epoch; });

function assertCurrentSession(config?: RetryableRequestConfig) {
  if (config?._sessionEpoch !== undefined && config._sessionEpoch !== getSessionEpoch()) {
    throw new CanceledError('Session changed');
  }
}

// ─── Intercepteur REQUEST - injection token ───────────────────────────────────

apiClient.interceptors.request.use(
  async (config: RetryableRequestConfig) => {
    config._sessionEpoch ??= getSessionEpoch();
    assertCurrentSession(config);
    // Récupérer token depuis AsyncStorage
    const token = await withSessionStorage(() => AsyncStorage.getItem(Config.STORAGE.ACCESS_TOKEN));
    assertCurrentSession(config);

    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    } else {
      config.headers.delete('Authorization');
    }

    // Log en dev uniquement
    if (__DEV__) {
      console.log(`[API] → ${config.method?.toUpperCase()} ${config.url}`);
    }

    return config;
  },
  (error) => Promise.reject(error),
);

// ─── Intercepteur RESPONSE - gestion erreurs centralisée ─────────────────────

apiClient.interceptors.response.use(
  (response: AxiosResponse) => {
    assertCurrentSession(response.config);
    if (__DEV__) {
      console.log(`[API] ← ${response.status} ${response.config.url}`);
    }
    return response;
  },
  async (error: AxiosError) => {
    if (isCancel(error)) return Promise.reject(error);
    assertCurrentSession(error.config);
    // Pas de réponse = problème réseau / serveur non joignable
    if (!error.response) {
      return Promise.reject(new NetworkError());
    }

    const { status, data } = error.response;

    // Extraire message d'erreur FastAPI (format: { detail: "..." })
    const detail = (data as { detail?: unknown })?.detail;
    const message = typeof detail === 'string' ? detail : getDefaultMessage(status);

    const requestConfig = error.config as RetryableRequestConfig | undefined;
    const isAuthenticationRequest = [
      '/auth/login',
      '/auth/login/form',
      '/auth/refresh',
    ].some((path) => requestConfig?.url?.includes(path));

    if (status === 401 && requestConfig && !requestConfig._retry && !isAuthenticationRequest) {
      requestConfig._retry = true;

      const { useAuthStore } = await import('../store/authStore');
      assertCurrentSession(requestConfig);
      // The store coalesces refreshes within this session, never across accounts.
      if (await useAuthStore.getState().refreshToken()) {
        assertCurrentSession(requestConfig);
        return apiClient(requestConfig);
      }
    }

    return Promise.reject(new ApiError(status, message, data));
  },
);

// ─── Helper messages HTTP ─────────────────────────────────────────────────────

function getDefaultMessage(status: number): string {
  const messages: Record<number, string> = {
    400: 'Données invalides',
    401: 'Non authentifié',
    403: 'Accès non autorisé',
    404: 'Ressource introuvable',
    409: 'Conflit - ressource déjà existante',
    422: 'Erreur de validation',
    500: 'Erreur interne du serveur',
    503: 'Service temporairement indisponible',
  };
  return messages[status] ?? `Erreur HTTP ${status}`;
}

export default apiClient;
