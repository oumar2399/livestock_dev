import { useMutation, useQuery } from '@tanstack/react-query';
import {
  getFarmOverview,
  getFarmQuality,
  getFarmReportPreview,
  downloadAndShareFarmReport,
  FarmReportParams,
  FarmPreviewParams,
} from '../api/farmReports';

export function useFarmOverview(params: FarmReportParams, enabled = true) {
  return useQuery({
    queryKey: ['farm-report-overview', params],
    queryFn: ({ signal }) => getFarmOverview(params, signal),
    enabled: enabled && !!params.farmId && !!params.dateFrom && !!params.dateTo,
    retry: false,
    refetchOnWindowFocus: false,
  });
}

export function useFarmQuality(params: FarmReportParams, enabled = true) {
  return useQuery({
    queryKey: ['farm-report-quality', params],
    queryFn: ({ signal }) => getFarmQuality(params, signal),
    enabled: enabled && !!params.farmId && !!params.dateFrom && !!params.dateTo,
    retry: false,
    refetchOnWindowFocus: false,
  });
}

export function useFarmReportPreview(params: FarmPreviewParams, enabled = false) {
  return useQuery({
    queryKey: ['farm-report-preview', params],
    queryFn: ({ signal }) => getFarmReportPreview(params, signal),
    enabled: enabled && !!params.farmId && !!params.dateFrom && !!params.dateTo,
    retry: false,
    gcTime: 0,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  });
}

export function useFarmReportExport() {
  return useMutation({
    mutationFn: downloadAndShareFarmReport,
  });
}
