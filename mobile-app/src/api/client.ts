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
  InternalAxiosRequestConfig,
} from 'axios';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { Config } from '../constants/config';

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
  },
});

// ─── Intercepteur REQUEST - injection token ───────────────────────────────────

apiClient.interceptors.request.use(
  async (config: InternalAxiosRequestConfig) => {
    // Récupérer token depuis AsyncStorage
    const token = await AsyncStorage.getItem(Config.STORAGE.ACCESS_TOKEN);

    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
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
    if (__DEV__) {
      console.log(`[API] ← ${response.status} ${response.config.url}`);
    }
    return response;
  },
  async (error: AxiosError) => {
    // Pas de réponse = problème réseau / serveur non joignable
    if (!error.response) {
      return Promise.reject(new NetworkError());
    }

    const { status, data } = error.response;

    // Extraire message d'erreur FastAPI (format: { detail: "..." })
    const detail = (data as { detail?: string })?.detail;
    const message = detail ?? getDefaultMessage(status);

    // 401 : token expiré ou invalide → déconnexion
    // TODO: implémenter refresh token ici quand backend l'aura
    if (status === 401) {
      await AsyncStorage.removeItem(Config.STORAGE.ACCESS_TOKEN);
      // L'AuthStore détectera l'absence de token au prochain check
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
