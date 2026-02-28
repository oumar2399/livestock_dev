// ─── Types 100% calqués sur les schémas Pydantic du backend ─────────────────
// Référence : schemas/animal.py, alert.py, telemetry.py

// ─── Animal ───────────────────────────────────────────────────────────────────

/** Correspond à AnimalResponse (schemas/animal.py) */
export interface Animal {
  id: number;
  farm_id: number;
  name: string;
  official_id: string | null;
  species: string;
  breed: string | null;
  sex: 'M' | 'F' | null;
  birth_date: string | null;       // "YYYY-MM-DD"
  weight: number | null;
  photo_url: string | null;
  assigned_device: string | null;  // ex: "M5-001"
  status: AnimalStatus;
  created_at: string;              // ISO datetime
  updated_at: string;
  // Calculés depuis dernière télémétrie
  last_latitude: number | null;
  last_longitude: number | null;
  last_update: string | null;
}

export type AnimalStatus = 'active' | 'sick' | 'sold' | 'deceased';

/** Correspond à AnimalList */
export interface AnimalList {
  total: number;
  animals: Animal[];
  page: number;
  page_size: number;
}

export interface AnimalCreate {
  name: string;
  farm_id: number;
  official_id?: string;
  species?: string;
  breed?: string;
  sex?: 'M' | 'F';
  birth_date?: string;
  weight?: number;
  assigned_device?: string;
}

export interface AnimalUpdate {
  name?: string;
  official_id?: string;
  breed?: string;
  sex?: 'M' | 'F';
  birth_date?: string;
  weight?: number;
  assigned_device?: string;
  status?: AnimalStatus;
}

// ─── Telemetry ────────────────────────────────────────────────────────────────

/** États calculés par calculate_activity_state() dans telemetry.py */
export type ActivityState = 'lying' | 'standing' | 'walking' | 'running';

/** Correspond à TelemetryResponse */
export interface TelemetryRecord {
  time: string;
  device_id: string;
  animal_id: number | null;
  latitude: number;
  longitude: number;
  altitude: number | null;
  speed: number | null;
  satellites: number | null;
  activity: number;                // accéléromètre en g
  activity_state: ActivityState | null;
  temperature: number | null;      // °C
  battery: number;                 // 0-100 (alias battery_level)
}

/** Correspond à TelemetryLatest - vue optimisée pour carte temps réel */
export interface TelemetryLatest {
  animal_id: number;
  animal_name: string;
  device_id: string;
  latitude: number;
  longitude: number;
  activity: number;
  battery: number;
  last_update: string;
}

export interface TelemetryCreate {
  device_id: string;
  latitude: number;
  longitude: number;
  altitude?: number;
  speed?: number;
  satellites?: number;
  activity: number;
  temperature?: number;
  battery: number;
}

// ─── Alerts ───────────────────────────────────────────────────────────────────

export type AlertType = 'health' | 'geofence' | 'battery' | 'offline' | 'custom';
export type AlertSeverity = 'info' | 'warning' | 'critical';

/** Correspond à AlertResponse */
export interface Alert {
  id: number;
  animal_id: number;
  animal_name: string | null;
  type: AlertType;
  severity: AlertSeverity;
  title: string;
  message: string | null;
  alert_metadata: Record<string, unknown> | null;
  triggered_at: string;
  acknowledged_at: string | null;
  resolved_at: string | null;
}

/** Correspond à AlertList */
export interface AlertList {
  total: number;
  alerts: Alert[];
  unresolved_count: number;
}

export interface AlertUpdate {
  acknowledged_at?: string;
  acknowledged_by?: number;
  resolved_at?: string;
}

// ─── Query Params ─────────────────────────────────────────────────────────────

export interface AnimalsQueryParams {
  farm_id?: number;
  status?: AnimalStatus;
  page?: number;
  page_size?: number;
}

export interface AlertsQueryParams {
  resolved?: boolean;
  severity?: AlertSeverity;
  animal_id?: number;
  limit?: number;
}

export interface TelemetryLatestParams {
  limit?: number;
  animal_id?: number;
}

// ─── Auth (préparé pour implémentation future JWT) ────────────────────────────

export interface LoginCredentials {
  username: string;
  password: string;
}

export interface AuthTokens {
  access_token: string;
  token_type: 'bearer';
}

// ─── Navigation ───────────────────────────────────────────────────────────────

export type RootStackParamList = {
  Login: undefined;
  Main: undefined;
};

export type MainTabParamList = {
  Dashboard: undefined;
  Map: undefined;
  Animals: undefined;
  Alerts: undefined;
  Profile: undefined;
};

export type AnimalsStackParamList = {
  AnimalsList: undefined;
  AnimalDetail: { animalId: number };
};

export type AlertsStackParamList = {
  AlertsList: undefined;
};
