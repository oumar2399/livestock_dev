import AsyncStorage from '@react-native-async-storage/async-storage';
import * as FileSystem from 'expo-file-system/legacy';
import * as Sharing from 'expo-sharing';
import { Config } from '../constants/config';
import { ReportDataset, ReportPreview } from '../types';
import apiClient from './client';

export interface ReportExportParams {
  dataset: ReportDataset;
  farmId?: number;
  animalId?: number;
  dateFrom?: string;
  dateTo?: string;
  resolved?: boolean;
}

function reportQuery(params: ReportExportParams): URLSearchParams {
  const query = new URLSearchParams();
  if (params.farmId) query.set('farm_id', String(params.farmId));
  if (params.animalId) query.set('animal_id', String(params.animalId));
  if (params.dateFrom) query.set('date_from', params.dateFrom);
  if (params.dateTo) query.set('date_to', params.dateTo);
  if (params.resolved !== undefined) query.set('resolved', String(params.resolved));
  return query;
}

export async function getReportPreview(params: ReportExportParams, signal?: AbortSignal): Promise<ReportPreview> {
  const query = reportQuery(params);
  query.set('limit', '20');
  const { data } = await apiClient.get<ReportPreview>(`/reports/preview/${params.dataset}?${query}`, { signal });
  return data;
}

export async function downloadAndShareReport(params: ReportExportParams): Promise<string> {
  const token = await AsyncStorage.getItem(Config.STORAGE.ACCESS_TOKEN);
  if (!token) throw new Error('Session expired. Please sign in again.');
  if (!FileSystem.cacheDirectory) throw new Error('Download storage is unavailable.');

  const suffix = reportQuery(params).toString();
  const url = `${Config.API_BASE_URL}/reports/export/${params.dataset}${suffix ? `?${suffix}` : ''}`;
  const fileName = `${params.dataset}_${params.dateFrom ?? 'all'}_${params.dateTo ?? 'all'}.csv`;
  const result = await FileSystem.downloadAsync(url, `${FileSystem.cacheDirectory}${fileName}`, {
    headers: { Authorization: `Bearer ${token}`, 'ngrok-skip-browser-warning': 'true' },
  });

  if (result.status < 200 || result.status >= 300) {
    await FileSystem.deleteAsync(result.uri, { idempotent: true });
    throw new Error(`Export failed (HTTP ${result.status}).`);
  }
  if (!(await Sharing.isAvailableAsync())) throw new Error('File sharing is unavailable.');
  await Sharing.shareAsync(result.uri, {
    mimeType: 'text/csv',
    dialogTitle: 'Share CSV export',
    UTI: 'public.comma-separated-values-text',
  });
  return result.uri;
}
