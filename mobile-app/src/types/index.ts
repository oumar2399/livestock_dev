// ─── Types 100% calqués sur les schémas Pydantic du backend ─────────────────

// ─── Animal ───────────────────────────────────────────────────────────────────

export interface Animal {
  id: number;
  farm_id: number;
  name: string;
  official_id: string | null;
  species: string;
  breed: string | null;
  sex: 'M' | 'F' | null;
  birth_date: string | null;
  weight: number | null;
  photo_url: string | null;
  assigned_device: string | null;
  status: AnimalStatus;
  created_at: string;
  updated_at: string;
  last_latitude: number | null;
  last_longitude: number | null;
  last_update: string | null;
}

export type AnimalStatus = 'active' | 'sick' | 'sold' | 'deceased';

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

export type ActivityState = 'lying' | 'standing' | 'walking' | 'running';

export interface TelemetryRecord {
  time: string;
  device_id: string;
  animal_id: number | null;
  latitude: number;
  longitude: number;
  altitude: number | null;
  speed: number | null;
  satellites: number | null;
  activity: number;
  activity_state: ActivityState | null;
  temperature: number | null;
  battery: number;
}

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

// ─── Auth ─────────────────────────────────────────────────────────────────────

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

// Onglets du bas (inchangés)
export type MainTabParamList = {
  Dashboard: undefined;
  Map: undefined;
  Animals: undefined;
  Alerts: undefined;
  Profile: undefined;
};

// Stack animaux (AnimalForm ajouté)
export type AnimalsStackParamList = {
  AnimalsList: undefined;
  AnimalDetail: { animalId: number };
  AnimalForm: { animalId?: number } | undefined;
};

export type AlertsStackParamList = {
  AlertsList: undefined;
};

// Drawer (menu latéral)
export type DrawerParamList = {
  HomeTabs: undefined;        // Wraps les bottom tabs
  Farm: undefined;
  Users: undefined;
  Devices: undefined;
  Geofence: undefined;
  Reports: undefined;
  VetOptions: undefined;
  Settings: undefined;
  Chatbot: undefined;         // À venir
  Marketplace: undefined;     // À venir
};