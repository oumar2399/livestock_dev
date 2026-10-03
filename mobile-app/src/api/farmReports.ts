import AsyncStorage from '@react-native-async-storage/async-storage';
import * as FileSystem from 'expo-file-system/legacy';
import * as Sharing from 'expo-sharing';
import { Config } from '../constants/config';
import {
  FarmOverviewResponse,
  FarmQualityResponse,
  FarmReportDataset,
  FarmReportPreview,
} from '../types';
import apiClient from './client';
import { getSessionEpoch, onSessionChange } from '../store/sessionLifecycle';
import { useFarmStore } from '../store/farmStore';
import { generateUUID } from '../utils/uuid';

export interface FarmReportParams {
  farmId: number;
  dateFrom: string;
  dateTo: string;
}

export interface FarmPreviewParams extends FarmReportParams {
  dataset: FarmReportDataset;
  limit?: number;
}

export async function getFarmOverview(
  params: FarmReportParams,
  signal?: AbortSignal,
): Promise<FarmOverviewResponse> {
  const query = new URLSearchParams({
    date_from: params.dateFrom,
    date_to: params.dateTo,
  });
  const { data } = await apiClient.get<FarmOverviewResponse>(
    `/farms/${params.farmId}/reports/overview?${query}`,
    { signal },
  );
  return data;
}

export async function getFarmQuality(
  params: FarmReportParams,
  signal?: AbortSignal,
): Promise<FarmQualityResponse> {
  const query = new URLSearchParams({
    date_from: params.dateFrom,
    date_to: params.dateTo,
  });
  const { data } = await apiClient.get<FarmQualityResponse>(
    `/farms/${params.farmId}/reports/quality?${query}`,
    { signal },
  );
  return data;
}

export async function getFarmReportPreview(
  params: FarmPreviewParams,
  signal?: AbortSignal,
): Promise<FarmReportPreview> {
  const query = new URLSearchParams({
    date_from: params.dateFrom,
    date_to: params.dateTo,
    limit: String(params.limit ?? 20),
  });
  const { data } = await apiClient.get<FarmReportPreview>(
    `/farms/${params.farmId}/reports/preview/${params.dataset}?${query}`,
    { signal },
  );
  return data;
}

export async function downloadAndShareFarmReport(
  params: FarmPreviewParams,
): Promise<string> {
  const epoch = getSessionEpoch();
  let invalidated = false;
  let download: ReturnType<typeof FileSystem.createDownloadResumable> | undefined;
  const cancel = () => {
    invalidated = true;
    void download?.cancelAsync().catch(() => undefined);
  };
  const unsubscribeSession = onSessionChange(cancel);
  const unsubscribeFarm = useFarmStore.subscribe((state) => {
    if (state.currentFarmId !== params.farmId) cancel();
  });
  const assertCurrent = () => {
    if (invalidated || epoch !== getSessionEpoch() || useFarmStore.getState().currentFarmId !== params.farmId) {
      throw new Error('Export cancelled: session or farm changed.');
    }
  };
  let uri: string | undefined;
  try {
    assertCurrent();
    const token = await AsyncStorage.getItem(Config.STORAGE.ACCESS_TOKEN);
    assertCurrent();
    if (!token) throw new Error('Session expired. Please sign in again.');
    if (!FileSystem.cacheDirectory) throw new Error('Download storage is unavailable.');

    const query = new URLSearchParams({
      date_from: params.dateFrom,
      date_to: params.dateTo,
    });
    const url = `${Config.API_BASE_URL}/farms/${params.farmId}/reports/export/${params.dataset}?${query}`;
    const fileName = `farm_${params.farmId}_${params.dataset}_${epoch}_${generateUUID()}.csv`;
    uri = `${FileSystem.cacheDirectory}${fileName}`;
    download = FileSystem.createDownloadResumable(
      url,
      uri,
      {
        headers: {
          Authorization: `Bearer ${token}`,
          'ngrok-skip-browser-warning': 'true',
        },
      },
    );
    const result = await download.downloadAsync();
    assertCurrent();
    if (!result) throw new Error('Export cancelled.');

    if (result.status < 200 || result.status >= 300) {
      await FileSystem.deleteAsync(result.uri, { idempotent: true });
      throw new Error(`Export failed (HTTP ${result.status}).`);
    }
    if (!(await Sharing.isAvailableAsync())) {
      throw new Error('File sharing is unavailable on this device.');
    }
    // Recheck server permissions immediately before sharing a downloaded copy.
    assertCurrent();
    await apiClient.get(`/farms/${params.farmId}/reports/preview/${params.dataset}`, {
      params: { date_from: params.dateFrom, date_to: params.dateTo, limit: 1 },
    });
    assertCurrent();
    await Sharing.shareAsync(result.uri, {
      mimeType: 'text/csv',
      dialogTitle: 'Share Farm Report CSV',
      UTI: 'public.comma-separated-values-text',
    });
    return result.uri;
  } finally {
    unsubscribeSession();
    unsubscribeFarm();
    if (uri) await FileSystem.deleteAsync(uri, { idempotent: true }).catch(() => undefined);
  }
}
