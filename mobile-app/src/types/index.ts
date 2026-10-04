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

// Binary states from the ML model (Active/Resting).
// Legacy 4-class states kept for backward compatibility with old DB records.
export type ActivityState = 'Active' | 'Resting' | 'lying' | 'standing' | 'walking' | 'running';

export interface TelemetryRecord {
  time: string;
  device_id: string;
  animal_id: number | null;
  latitude: number | null;
  longitude: number | null;
  behavior_eligible?: boolean | null;
  exclusion_reason?: string | null;
  received_at?: string | null;
  time_source?: string | null;
  altitude: number | null;
  speed: number | null;
  satellites: number | null;
  activity: number;
  activity_state: ActivityState | null;
  predicted_behavior?: string | null;
  behavior_confidence?: number | null;
  has_feedback?: boolean;
  feedback_verdict?: string | null;
  feedback_correction?: string | null;
  temperature: number | null;
  battery: number | null;
}

export interface TelemetryLatest {
  animal_id: number;
  animal_name: string;
  device_id: string;
  latitude: number | null;
  longitude: number | null;
  position_time?: string | null;
  position_is_animal?: boolean;
  device_status?: string | null;
  behavior_eligible?: boolean | null;
  activity: number;
  activity_state: ActivityState | null;
  predicted_behavior?: string | null;
  behavior_confidence?: number | null;
  battery: number | null;
  last_update: string;
}

export type PositionedTelemetry = TelemetryLatest & { latitude: number; longitude: number };

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

export type AlertType = 'health' | 'geofence' | 'battery' | 'offline' | 'activity_deviation_low' | 'activity_deviation_high' | 'custom';
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
  farm_id?: number;
  resolved?: boolean;
  severity?: AlertSeverity;
  animal_id?: number;
  limit?: number;
}

export interface TelemetryLatestParams {
  after_animal_id?: number;
  farm_id?: number;
  limit?: number;
  animal_id?: number;
}

// ─── Farms ────────────────────────────────────────────────────────────────────

export type FarmMembershipRole = 'owner' | 'farmer' | 'vet' | 'admin';

export interface FarmAccess {
  id: number;
  name: string;
  address: string | null;
  size_hectares: number | null;
  owner_id: number | null;
  created_at: string | null;
  membership_role: FarmMembershipRole;
  permissions: string[];
}

export interface FarmCreateInput {
  name: string;
  address?: string | null;
  size_hectares?: number | null;
  client_request_id?: string;
}

export interface FarmUpdateInput {
  name: string;
  address?: string | null;
  size_hectares?: number | null;
}


export interface FarmMembership {
  id: number;
  user_id: number;
  user_name: string | null;
  user_email: string | null;
  farm_id: number;
  farm_name: string | null;
  role: Exclude<FarmMembershipRole, 'admin'>;
  status: 'pending' | 'active' | 'revoked';
  permissions: string[];
  invited_by_id: number | null;
  created_at: string;
  updated_at: string;
}

export interface FarmMembershipList {
  total: number;
  members: FarmMembership[];
}

// ─── Feedback ─────────────────────────────────────────────────────────────────

export type FeedbackVerdict = 'correct' | 'incorrect';

export interface FeedbackCreate {
  animal_id: number;
  telemetry_time?: string;
  verdict: FeedbackVerdict;
  correction?: string;
}

export interface FeedbackResponse {
  id: number;
  animal_id: number;
  user_id: number | null;
  telemetry_time: string | null;
  predicted_behavior: string | null;
  confidence: number | null;
  verdict: FeedbackVerdict;
  correction: string | null;
  created_at: string;
}

export type AlertFeedbackVerdict = 'confirmed_issue' | 'false_alarm';

export interface AlertFeedbackCreate {
  verdict: AlertFeedbackVerdict;
  notes?: string;
}

export interface AlertFeedbackResponse {
  id: number;
  alert_id: number;
  animal_id: number;
  user_id: number;
  alert_type: string;
  z_score?: number | null;
  verdict: AlertFeedbackVerdict;
  notes?: string | null;
  created_at: string;
}

export interface FeedbackStatsResponse {
  total_prediction_feedbacks: number;
  prediction_accuracy_pct: number;
  total_alert_feedbacks: number;
  confirmed_alert_pct: number;
}

// ─── Operations, exports and history ─────────────────────────────────────────

export type ReportDataset =
  | 'untimed_telemetry'
  | 'telemetry'
  | 'daily_summaries'
  | 'alerts'
  | 'prediction_feedbacks'
  | 'alert_feedbacks';

export interface ReportPreview {
  dataset: ReportDataset;
  columns: string[];
  rows: string[][];
  has_more: boolean;
  limit: number;
  target_timezone: string;
  generated_at: string;
}

export interface SystemStatus {
  status: 'healthy' | 'degraded' | 'unhealthy';
  checked_at: string;
  target_timezone: string;
  database: { status: 'up' | 'down'; latency_ms: number | null };
  model: { status: 'loaded' | 'unavailable'; classes: string[] };
  schema: { revision: string | null };
  scheduler: { enabled: boolean; running: boolean; next_run_at: string | null };
}

export interface DailyJobRun {
  id: number;
  job_name: string;
  trigger_source: 'scheduled' | 'manual';
  target_date: string;
  timezone_name: string;
  status: 'running' | 'success' | 'failed';
  started_at: string;
  finished_at: string | null;
  initiated_by: number | null;
  summaries_created: number | null;
  alerts_created: number | null;
  error_message: string | null;
}

export interface DailyJobRunList {
  total: number;
  runs: DailyJobRun[];
  limit: number;
  offset: number;
}

export type TimelineEventType =
  | 'alert'
  | 'prediction_feedback'
  | 'alert_feedback'
  | 'daily_summary'
  | 'veterinary_entry';

export interface TimelineItem {
  id: string;
  source_id: number;
  event_type: TimelineEventType;
  occurred_at: string;
  title: string;
  summary: string | null;
  severity: string | null;
  data: Record<string, unknown>;
}

export interface TimelinePage {
  items: TimelineItem[];
  next_cursor: string | null;
}

export type GeofenceType = 'pasture' | 'danger';

export interface GeoPoint {
  latitude: number;
  longitude: number;
}

export interface Geofence {
  id: number;
  farm_id: number;
  name: string;
  type: GeofenceType;
  active: boolean;
  points: GeoPoint[];
  created_at: string | null;
}

export interface GeofenceCreate {
  farm_id: number;
  name: string;
  type: GeofenceType;
  active?: boolean;
  points: GeoPoint[];
}

export interface GeofenceUpdate {
  name?: string;
  type?: GeofenceType;
  active?: boolean;
  points?: GeoPoint[];
}

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

// Onglets du bas
export type MainTabParamList = {
  Dashboard: undefined;
  Map: { focusAnimalId?: number; showTrack?: boolean } | undefined;
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
  FarmOnboarding: undefined;
  Users: undefined;
  Devices: undefined;
  Geofence: undefined;
  Reports: undefined;
  FarmReports: undefined;
  VetOptions: undefined;
  Settings: undefined;
  Chatbot: undefined;         // À venir
  Marketplace: undefined;     // À venir
};

// ─── Farm Reports & Data Quality (Lots G & H) ──────────────────────────────────

export type FarmReportDataset = 'farm_summary' | 'animal_quality';

export interface FarmCurrentState {
  generated_at: string;
  total_animals: number;
  animals_by_status: Record<string, number>;
  total_devices: number;
  devices_by_status: Record<string, number>;
  assigned_devices_count: number;
  unassigned_devices_count: number;
  last_reception?: {
    last_seen_at: string;
    age_seconds: number;
    freshness_status: 'recent' | 'delayed' | 'silent';
  } | null;
  gps_freshness?: {
    last_fix_at: string;
    age_seconds: number;
    satellites: number;
    status: string;
  } | null;
  battery_summary?: {
    min_pct?: number;
    avg_pct?: number;
    low_battery_count?: number;
    monitored_devices_count?: number;
  } | null;
  active_alerts_count: number;
}

export interface FarmPeriodSummary {
  date_from: string;
  date_to: string;
  effective_start: string;
  effective_end: string;
  provenance_available_from?: string | null;
  scope_status: 'available' | 'no_data' | 'not_computable' | 'partial';
  dated_windows_count: number;
  proven_tracking_seconds: number;
  dated_coverage_seconds: number;
  dated_coverage_ratio?: number | null;
  behavioral_coverage_seconds: number;
  behavioral_coverage_ratio?: number | null;
  behavior_breakdown: {
    active_count: number;
    resting_count: number;
    active_ratio?: number | null;
    label: string;
  };
  gps_presence_ratio?: number | null;
  behavioral_exclusions: Record<string, number>;
  reception_delay: {
    median_seconds?: number | null;
    p95_seconds?: number | null;
    negative_anomalies_count: number;
  };
  unobserved_gaps: {
    gap_count: number;
    longest_gap_seconds: number;
    total_unobserved_seconds: number;
  };
  alerts_triggered_in_period: number;
  alerts_resolved_in_period: number;
  limitations: string[];
}

export interface FarmUntimedSummary {
  untimed_count: number;
  breakdown_by_reason: Record<string, number>;
  breakdown_by_attribution: Record<string, number>;
  mandatory_label: string;
}

export interface FarmOverviewResponse {
  farm_id: number;
  farm_name: string;
  generated_at: string;
  target_timezone: string;
  current_state: FarmCurrentState;
  period_summary: FarmPeriodSummary;
  untimed_summary: FarmUntimedSummary;
}

export interface FarmQualityItem {
  animal_id: number;
  animal_name: string;
  date: string;
  dated_windows_count: number;
  covered_seconds: number;
  coverage_ratio?: number | null;
  active_count: number;
  resting_count: number;
  active_ratio?: number | null;
  gps_presence_ratio?: number | null;
  exclusions_count: number;
  status: string;
}

export interface FarmQualityResponse {
  farm_id: number;
  farm_name: string;
  generated_at: string;
  target_timezone: string;
  date_from: string;
  date_to: string;
  items: FarmQualityItem[];
}

export interface FarmReportPreview {
  farm_id: number;
  dataset: FarmReportDataset;
  date_from: string;
  date_to: string;
  generated_at: string;
  target_timezone: string;
  columns: string[];
  rows: string[][];
  total_rows: number;
  has_more: boolean;
  limit: number;
}

// ─── Location & GPS Track (Lot B) ───────────────────────────────────────────

export interface LocationPoint {
  animal_id: number;
  animal_name: string;
  device_id: string | null;
  latitude: number;
  longitude: number;
  position_time: string;
  position_is_animal: boolean;
  device_status: string | null;
  freshness: 'recent' | 'stale' | 'old';
  age_seconds: number;
}

export interface TrackPoint {
  latitude: number;
  longitude: number;
  time: string;
  speed: number | null;
  satellites: number | null;
  is_reliable: boolean;
}

export interface TrackSegment {
  points: TrackPoint[];
  start_time: string;
  end_time: string;
  is_proven: boolean;
  quality: 'reliable' | 'degraded';
}

export interface GapInfo {
  start_time: string;
  end_time: string;
  duration_seconds: number;
  reason: 'no_data' | 'loss_period' | 'unproven';
}

export interface LocationHistoryResponse {
  animal_id: number;
  animal_name: string;
  device_id: string | null;
  position_is_animal: boolean;
  segments: TrackSegment[];
  gaps: GapInfo[];
  period_start: string;
  period_end: string;
  total_points: number;
  proven_coverage_ratio: number | null;
}
