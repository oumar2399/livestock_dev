import { useMutation, useQuery } from '@tanstack/react-query';
import { downloadAndShareReport, getReportPreview, ReportExportParams } from '../api/reports';

export function useReportPreview(params: ReportExportParams, enabled = false) {
  return useQuery({
    queryKey: ['report-preview', params],
    queryFn: ({ signal }) => getReportPreview(params, signal),
    enabled,
    retry: false,
    gcTime: 0,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  });
}

export function useReportExport() {
  return useMutation({ mutationFn: downloadAndShareReport });
}
