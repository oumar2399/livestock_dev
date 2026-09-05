/**
 * Service API - Feedbacks berger/vétérinaire
 * Endpoints :
 *  - POST /feedback/predictions     → Feedback prédiction comportementale ML
 *  - POST /feedback/alerts/{id}     → Feedback alerte déviation comportementale
 *  - GET  /feedback/stats           → Statistiques globales d'annotation
 */
import apiClient from './client';
import {
  FeedbackCreate,
  FeedbackResponse,
  AlertFeedbackCreate,
  AlertFeedbackResponse,
  FeedbackStatsResponse,
} from '../types';

const BASE = '/feedback';

export const feedbackApi = {
  /**
   * POST /api/v1/feedback/predictions
   * Soumettre ou mettre à jour un feedback sur une prédiction comportementale ML (Active/Resting)
   */
  submitPredictionFeedback: async (payload: FeedbackCreate): Promise<FeedbackResponse> => {
    const { data } = await apiClient.post<FeedbackResponse>(`${BASE}/predictions`, payload);
    return data;
  },

  /**
   * POST /api/v1/feedback/alerts/{alertId}
   * Soumettre ou mettre à jour un feedback sur une alerte d'anomalie ('confirmed_issue' | 'false_alarm')
   */
  submitAlertFeedback: async (alertId: number, payload: AlertFeedbackCreate): Promise<AlertFeedbackResponse> => {
    const { data } = await apiClient.post<AlertFeedbackResponse>(`${BASE}/alerts/${alertId}`, payload);
    return data;
  },

  /**
   * GET /api/v1/feedback/stats
   * Obtenir les statistiques d'annotation et de précision terrain
   */
  getStats: async (): Promise<FeedbackStatsResponse> => {
    const { data } = await apiClient.get<FeedbackStatsResponse>(`${BASE}/stats`);
    return data;
  },
};
