/**
 * Client API Workflow Vétérinaire (Lot E)
 */
import apiClient from './client';

export interface VeterinaryEntry {
  id: number;
  case_id: number;
  author_user_id?: number | null;
  author_name?: string | null;
  entry_type: 'observation' | 'intervention' | 'follow_up' | 'assessment' | 'note';
  content: string;
  occurred_at: string;
  created_at: string;
}

export interface VeterinaryCase {
  id: number;
  farm_id: number;
  animal_id: number;
  animal_name?: string | null;
  linked_alert_id?: number | null;
  title: string;
  status: 'provisional' | 'confirmed' | 'ruled_out' | 'closed';
  opened_by?: number | null;
  opener_name?: string | null;
  opened_at: string;
  closed_at?: string | null;
  created_at: string;
  updated_at: string;
  entries_count: number;
  entries: VeterinaryEntry[];
}

export interface VeterinaryCaseListResponse {
  total: number;
  cases: VeterinaryCase[];
}

export interface VeterinaryCaseCreatePayload {
  animal_id: number;
  linked_alert_id?: number | null;
  title: string;
  initial_entry?: {
    entry_type: 'observation' | 'intervention' | 'follow_up' | 'assessment' | 'note';
    content: string;
    occurred_at?: string | null;
  };
}

export interface VeterinaryCaseUpdatePayload {
  title?: string;
  status?: 'provisional' | 'confirmed' | 'ruled_out' | 'closed';
}

export interface VeterinaryEntryCreatePayload {
  entry_type: 'observation' | 'intervention' | 'follow_up' | 'assessment' | 'note';
  content: string;
  occurred_at?: string | null;
}

export const veterinaryApi = {
  listFarmCases: async (
    farmId: number,
    params?: { animal_id?: number; status?: string; linked_alert_id?: number; limit?: number },
  ): Promise<VeterinaryCaseListResponse> => {
    const response = await apiClient.get<VeterinaryCaseListResponse>(
      `/farms/${farmId}/veterinary-cases`,
      { params },
    );
    return response.data;
  },

  createCase: async (
    farmId: number,
    payload: VeterinaryCaseCreatePayload,
  ): Promise<VeterinaryCase> => {
    const response = await apiClient.post<VeterinaryCase>(
      `/farms/${farmId}/veterinary-cases`,
      payload,
    );
    return response.data;
  },

  getCaseDetail: async (farmId: number, caseId: number): Promise<VeterinaryCase> => {
    const response = await apiClient.get<VeterinaryCase>(
      `/farms/${farmId}/veterinary-cases/${caseId}`,
    );
    return response.data;
  },

  updateCase: async (
    farmId: number,
    caseId: number,
    payload: VeterinaryCaseUpdatePayload,
  ): Promise<VeterinaryCase> => {
    const response = await apiClient.patch<VeterinaryCase>(
      `/farms/${farmId}/veterinary-cases/${caseId}`,
      payload,
    );
    return response.data;
  },

  addEntry: async (
    farmId: number,
    caseId: number,
    payload: VeterinaryEntryCreatePayload,
  ): Promise<VeterinaryEntry> => {
    const response = await apiClient.post<VeterinaryEntry>(
      `/farms/${farmId}/veterinary-cases/${caseId}/entries`,
      payload,
    );
    return response.data;
  },

  listAnimalCases: async (animalId: number): Promise<VeterinaryCaseListResponse> => {
    const response = await apiClient.get<VeterinaryCaseListResponse>(
      `/animals/${animalId}/veterinary-cases`,
    );
    return response.data;
  },
};
