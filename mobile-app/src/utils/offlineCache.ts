/**
 * Cache Offline en lecture seule (Lot D)
 *
 * Principes stricts :
 * - Allowlist stricte des ressources en lecture seule
 * - Schéma versionné (SCHEMA_VERSION = 1)
 * - Clés de stockage isolées : user + farm + resourceType + resourceKey
 * - Protection contre les réponses tardives via sessionEpoch
 * - Purge systématique au logout ou changement de session
 * - Aucune donnée modifiable ou mutable offline
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { getSessionEpoch, onSessionChange, withSessionStorage } from '../store/sessionLifecycle';

export const CACHE_SCHEMA_VERSION = 1;
const CACHE_PREFIX = '@offline_cache:';

export type AllowlistedResourceType =
  | 'animals_list'
  | 'animal_detail'
  | 'alerts_list'
  | 'farm_summary'
  | 'locations_latest'
  | 'location_current';

const ALLOWLISTED_RESOURCES: ReadonlySet<AllowlistedResourceType> = new Set([
  'animals_list',
  'animal_detail',
  'alerts_list',
  'farm_summary',
  'locations_latest',
  'location_current',
]);

export interface CacheEntry<T = unknown> {
  schema_version: number;
  epoch: number;
  user_id: number;
  farm_id: number;
  resource_type: AllowlistedResourceType;
  resource_key: string;
  server_generated_at: string;
  cached_at: string;
  payload: T;
}

export function isResourceAllowlisted(type: string): type is AllowlistedResourceType {
  return ALLOWLISTED_RESOURCES.has(type as AllowlistedResourceType);
}

function buildCacheStorageKey(
  userId: number,
  farmId: number,
  resourceType: AllowlistedResourceType,
  resourceKey: string,
): string {
  return `${CACHE_PREFIX}${userId}:${farmId}:${resourceType}:${resourceKey}`;
}

/**
 * Enregistre une réponse API réussie dans le cache offline (si allowlistée).
 * Protégé contre les réponses tardives (ignore si l'epoch a changé).
 */
export async function saveToOfflineCache<T>(params: {
  userId: number;
  farmId: number;
  resourceType: AllowlistedResourceType;
  resourceKey: string;
  payload: T;
  serverGeneratedAt?: string;
  requestEpoch?: number;
}): Promise<boolean> {
  if (!isResourceAllowlisted(params.resourceType)) {
    return false;
  }

  const currentEpoch = getSessionEpoch();
  const requestEpoch = params.requestEpoch ?? currentEpoch;

  // Protection stricte contre les réponses tardives d'une session précédente
  if (requestEpoch !== currentEpoch) {
    return false;
  }

  const entry: CacheEntry<T> = {
    schema_version: CACHE_SCHEMA_VERSION,
    epoch: currentEpoch,
    user_id: params.userId,
    farm_id: params.farmId,
    resource_type: params.resourceType,
    resource_key: params.resourceKey,
    server_generated_at: params.serverGeneratedAt || new Date().toISOString(),
    cached_at: new Date().toISOString(),
    payload: params.payload,
  };

  const storageKey = buildCacheStorageKey(
    params.userId,
    params.farmId,
    params.resourceType,
    params.resourceKey,
  );

  return withSessionStorage(async () => {
    // Re-vérifier l'epoch à l'intérieur du verrou de stockage
    if (getSessionEpoch() !== currentEpoch) {
      return false;
    }
    await AsyncStorage.setItem(storageKey, JSON.stringify(entry));
    return true;
  });
}

/**
 * Récupère une entrée du cache offline.
 * Vérifie l'appartenance à la session, au compte et à la ferme.
 */
export async function loadFromOfflineCache<T>(params: {
  userId: number;
  farmId: number;
  resourceType: AllowlistedResourceType;
  resourceKey: string;
}): Promise<CacheEntry<T> | null> {
  if (!isResourceAllowlisted(params.resourceType)) {
    return null;
  }

  const currentEpoch = getSessionEpoch();
  const storageKey = buildCacheStorageKey(
    params.userId,
    params.farmId,
    params.resourceType,
    params.resourceKey,
  );

  return withSessionStorage(async () => {
    const raw = await AsyncStorage.getItem(storageKey);
    if (!raw) return null;

    try {
      const parsed = JSON.parse(raw) as CacheEntry<T>;

      // Contrôles d'intégrité et de sécurité stricts
      if (
        parsed.schema_version !== CACHE_SCHEMA_VERSION ||
        parsed.epoch !== currentEpoch ||
        parsed.user_id !== params.userId ||
        parsed.farm_id !== params.farmId ||
        parsed.resource_type !== params.resourceType
      ) {
        // Invalide ou appartenant à une autre session : supprimer
        await AsyncStorage.removeItem(storageKey);
        return null;
      }

      return parsed;
    } catch {
      // Données corrompues : supprimer
      await AsyncStorage.removeItem(storageKey);
      return null;
    }
  });
}

/**
 * Purge toutes les entrées du cache offline.
 */
export async function clearAllOfflineCache(): Promise<void> {
  return withSessionStorage(async () => {
    const allKeys = await AsyncStorage.getAllKeys();
    const cacheKeys = allKeys.filter((k) => k.startsWith(CACHE_PREFIX));
    if (cacheKeys.length > 0) {
      await AsyncStorage.multiRemove(cacheKeys);
    }
  });
}

/**
 * Purge le cache d'une ferme spécifique.
 */
export async function clearOfflineCacheForFarm(farmId: number): Promise<void> {
  return withSessionStorage(async () => {
    const allKeys = await AsyncStorage.getAllKeys();
    const farmPrefix = `${CACHE_PREFIX}`;
    const targetKeys = allKeys.filter((k) => {
      if (!k.startsWith(farmPrefix)) return false;
      const parts = k.slice(farmPrefix.length).split(':');
      // parts = [userId, farmId, ...]
      return parts.length >= 2 && parseInt(parts[1], 10) === farmId;
    });
    if (targetKeys.length > 0) {
      await AsyncStorage.multiRemove(targetKeys);
    }
  });
}

// Inscription au cycle de vie de session :
// Tout changement d'epoch (ex: logout, changement de compte) déclenche la purge immédiate
onSessionChange(() => {
  void clearAllOfflineCache();
});
