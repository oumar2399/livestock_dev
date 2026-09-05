/**
 * Hooks React Query - Feedback
 *
 * useSubmitPredictionFeedback() → mutation feedback prédiction ML
 * useSubmitAlertFeedback()      → mutation feedback alerte anomalie
 * useFeedbackStats()            → hook de lecture des statistiques
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { feedbackApi } from '../api/feedback';
import {
  FeedbackCreate,
  AlertFeedbackCreate,
} from '../types';
import { alertKeys } from './useAlerts';
import { telemetryKeys } from './useTelemetry';

export const feedbackKeys = {
  all: ['feedback'] as const,
  stats: () => [...feedbackKeys.all, 'stats'] as const,
};

/**
 * Mutation pour envoyer/mettre à jour un feedback sur une prédiction comportementale ML
 */
export function useSubmitPredictionFeedback() {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: (payload: FeedbackCreate) => feedbackApi.submitPredictionFeedback(payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: telemetryKeys.all });
      qc.invalidateQueries({ queryKey: feedbackKeys.stats() });
    },
  });
}

/**
 * Mutation pour envoyer/mettre à jour un feedback sur une alerte d'anomalie
 */
export function useSubmitAlertFeedback() {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: ({ alertId, payload }: { alertId: number; payload: AlertFeedbackCreate }) =>
      feedbackApi.submitAlertFeedback(alertId, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: alertKeys.lists() });
      qc.invalidateQueries({ queryKey: feedbackKeys.stats() });
    },
  });
}

/**
 * Hook de lecture des statistiques globales d'annotation
 */
export function useFeedbackStats() {
  return useQuery({
    queryKey: feedbackKeys.stats(),
    queryFn: () => feedbackApi.getStats(),
    staleTime: 60_000, // 1 minute
  });
}
