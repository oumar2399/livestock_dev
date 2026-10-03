/**
 * Fonctions utilitaires - Formatage et logique métier
 * Basées sur les valeurs réelles du backend (enums, seuils)
 */
import { format, formatDistanceToNow, parseISO } from 'date-fns';
import { enUS } from 'date-fns/locale';
import {
  ActivityState,
  Alert,
  AlertSeverity,
  AlertType,
  Animal,
  AnimalStatus,
} from '../types';
import { Colors } from '../constants/config';

// ─── Animaux ──────────────────────────────────────────────────────────────────

/** Label lisible du statut animal */
export function animalStatusLabel(status: AnimalStatus): string {
  const labels: Record<AnimalStatus, string> = {
    active: 'Active',
    sick: 'Sick',
    sold: 'Sold',
    deceased: 'Deceased',
  };
  return labels[status] ?? status;
}

/** Couleur du statut animal */
export function animalStatusColor(status: AnimalStatus): string {
  return Colors.animalStatus[status] ?? Colors.status.unknown;
}

/** Sexe lisible */
export function animalSexLabel(sex: 'M' | 'F' | null): string {
  if (!sex) return '–';
  return sex === 'M' ? 'Male' : 'Female';
}

/** Âge en années depuis birth_date (format "YYYY-MM-DD") */
export function animalAge(birthDate: string | null): string {
  if (!birthDate) return '–';
  const birth = new Date(birthDate);
  const now = new Date();
  const years = now.getFullYear() - birth.getFullYear();
  const months = now.getMonth() - birth.getMonth();
  const totalMonths = years * 12 + months;

  if (totalMonths < 1) return '< 1 month';
  if (totalMonths < 12) return `${totalMonths} months`;
  const y = Math.floor(totalMonths / 12);
  const m = totalMonths % 12;
  return m > 0 ? `${y} yrs ${m} mo` : `${y} yr${y > 1 ? 's' : ''}`;
}

/**
 * Fraîcheur des données et statut opérationnel (Lot 1)
 * Séparation stricte de 3 dimensions :
 * 1. Fraîcheur Télémétrie (IMU / capteurs)
 * 2. Statut & Fraîcheur GPS (Fix, satellites, coordonnées)
 * 3. Statut Matériel du boîtier (Actif, perdu, maintenance, etc.)
 */
export type TelemetryFreshness = 'recent' | 'stale' | 'silent';
export type GpsFixStatus = 'fix' | 'weak_fix' | 'stale_fix' | 'no_fix';
export type DeviceState = 'active' | 'lost' | 'maintenance' | 'retired' | 'revoked' | 'unknown';

export interface FreshnessAssessment {
  telemetryFreshness: TelemetryFreshness;
  telemetryLabel: string;
  telemetryColor: string;
  telemetryAgeMinutes: number | null;

  gpsStatus: GpsFixStatus;
  gpsLabel: string;
  gpsColor: string;
  hasValidCoords: boolean;

  deviceState: DeviceState;
  deviceLabel: string;
  deviceColor: string;

  batteryLabel: string;
  batteryColor: string;
}

export const FRESH_TELEMETRY_MINUTES = 5;
export const STALE_TELEMETRY_MINUTES = 30;

/** Vrai si la donnée a été reçue récemment (< 5 minutes par défaut) */
export function isRecentUpdate(lastUpdate: string | null, maxMinutes = FRESH_TELEMETRY_MINUTES): boolean {
  if (!lastUpdate) return false;
  const diff = Date.now() - new Date(lastUpdate).getTime();
  return diff < maxMinutes * 60 * 1000;
}

/**
 * Évalue la fraîcheur et la qualité des données de façon transparente et indépendante
 */
export function evaluateFreshness(params: {
  telemetryTime?: string | null;
  positionTime?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  satellites?: number | null;
  deviceStatus?: string | null;
  battery?: number | null;
}): FreshnessAssessment {
  const {
    telemetryTime,
    positionTime,
    latitude,
    longitude,
    satellites,
    deviceStatus,
    battery,
  } = params;

  // 1. Télémétrie
  let telemetryFreshness: TelemetryFreshness = 'silent';
  let telemetryAgeMinutes: number | null = null;
  let telemetryLabel = 'No telemetry';
  let telemetryColor = '#95A5A6'; // Gris

  if (telemetryTime) {
    const diffMs = Date.now() - new Date(telemetryTime).getTime();
    telemetryAgeMinutes = Math.max(0, Math.floor(diffMs / (60 * 1000)));

    if (telemetryAgeMinutes < FRESH_TELEMETRY_MINUTES) {
      telemetryFreshness = 'recent';
      telemetryLabel = telemetryAgeMinutes === 0 ? 'Recent (< 1 min)' : `Recent (${telemetryAgeMinutes} min ago)`;
      telemetryColor = '#27AE60'; // Vert
    } else if (telemetryAgeMinutes < STALE_TELEMETRY_MINUTES) {
      telemetryFreshness = 'stale';
      telemetryLabel = `Stale (${telemetryAgeMinutes} min ago)`;
      telemetryColor = '#F39C12'; // Orange
    } else {
      telemetryFreshness = 'silent';
      const hours = Math.floor(telemetryAgeMinutes / 60);
      telemetryLabel = hours > 0 ? `Silent (${hours}h ago)` : `Silent (${telemetryAgeMinutes} min ago)`;
      telemetryColor = '#95A5A6'; // Gris
    }
  }

  // 2. GPS
  const hasCoords = latitude !== null && latitude !== undefined && longitude !== null && longitude !== undefined;
  const satCount = satellites ?? 0;
  let gpsStatus: GpsFixStatus = 'no_fix';
  let gpsLabel = 'No GPS fix';
  let gpsColor = '#95A5A6';

  if (hasCoords) {
    const positionAge = positionTime ? Date.now() - new Date(positionTime).getTime() : NaN;
    if (!Number.isFinite(positionAge) || positionAge < 0 || positionAge >= STALE_TELEMETRY_MINUTES * 60_000) {
      gpsStatus = 'stale_fix';
      gpsLabel = positionTime && Number.isFinite(positionAge) && positionAge >= 0
        ? `Last fix ${timeAgo(positionTime)}` : 'GPS time unknown';
    } else if (satellites !== null && satellites !== undefined && satCount < 4) {
      gpsStatus = 'weak_fix';
      gpsLabel = `Weak fix (${satCount} sats)`;
      gpsColor = '#E67E22'; // Orange foncé
    } else {
      gpsStatus = 'fix';
      const posAge = positionTime ? timeAgo(positionTime) : null;
      gpsLabel = posAge ? `Fix ${posAge}` : 'GPS Fix valid';
      gpsColor = '#27AE60';
    }
  }

  // 3. Statut Matériel
  const rawStatus = (deviceStatus ?? 'unknown').toLowerCase();
  let deviceState: DeviceState = 'unknown';
  let deviceLabel = 'Collar unknown';
  let deviceColor = '#95A5A6';

  if (rawStatus === 'active') {
    deviceState = 'active';
    deviceLabel = 'Collar active';
    deviceColor = '#27AE60';
  } else if (rawStatus === 'lost') {
    deviceState = 'lost';
    deviceLabel = 'Collar lost';
    deviceColor = '#E74C3C'; // Rouge
  } else if (rawStatus === 'maintenance') {
    deviceState = 'maintenance';
    deviceLabel = 'In maintenance';
    deviceColor = '#9B59B6'; // Violet
  } else if (rawStatus === 'retired' || rawStatus === 'revoked') {
    deviceState = 'retired';
    deviceLabel = 'Collar retired';
    deviceColor = '#7F8C8D';
  }

  // Batterie
  const batteryLabel = formatBattery(battery);
  const batteryColorVal = batteryColor(battery ?? null);

  return {
    telemetryFreshness,
    telemetryLabel,
    telemetryColor,
    telemetryAgeMinutes,
    gpsStatus,
    gpsLabel,
    gpsColor,
    hasValidCoords: hasCoords,
    deviceState,
    deviceLabel,
    deviceColor,
    batteryLabel,
    batteryColor: batteryColorVal,
  };
}

// ─── Télémétrie / Comportement ────────────────────────────────────────────────

/** Label lisible de l'état d'activité */
export function activityStateLabel(state: ActivityState | null | undefined): string {
  if (!state) return '–';
  const labels: Record<ActivityState, string> = {
    // Binary ML states (primary)
    Active: 'Active',
    Resting: 'Resting',
    // Legacy 4-class states (backward compat)
    lying: 'Resting',
    standing: 'Resting',
    walking: 'Active',
    running: 'Active',
  };
  return labels[state] ?? state;
}

/** Couleur de l'état d'activité */
export function activityStateColor(state: ActivityState | null | undefined): string {
  if (!state) return Colors.status.unknown;
  return Colors.behavior[state] ?? Colors.status.unknown;
}

/** Icône Ionicons pour état d'activité */
export function activityStateIcon(state: ActivityState | null | undefined): string {
  const icons: Record<ActivityState, string> = {
    Active: 'walk-outline',
    Resting: 'bed-outline',
    lying: 'bed-outline',
    standing: 'bed-outline',
    walking: 'walk-outline',
    running: 'walk-outline',
  };
  return state ? (icons[state] ?? 'help-circle-outline') : 'help-circle-outline';
}

/**
 * Couleur batterie
 * Seuils cohérents avec alerts backend :
 * - Warning <20% (alert type "battery" severity "warning")
 * - Critical <10% (alert type "battery" severity "critical")
 */
export function formatBattery(level: number | null | undefined): string {
  if (level == null || isNaN(level) || level < 0 || level > 100) return 'Unknown';
  return `${Math.round(level)}%`;
}

export function batteryColor(level: number | null | undefined): string {
  if (level == null || isNaN(level) || level < 0 || level > 100) return Colors.text.muted;
  if (level >= 50) return Colors.battery.full;
  if (level >= 20) return Colors.battery.medium;
  return Colors.battery.low;
}

/** Icône batterie Ionicons */
export function batteryIcon(level: number | null | undefined): string {
  if (level == null || isNaN(level) || level < 0 || level > 100) return 'battery-dead-outline';
  if (level >= 80) return 'battery-full-outline';
  if (level >= 50) return 'battery-half-outline';
  if (level >= 20) return 'battery-dead-outline';
  return 'battery-dead';
}

// ─── Alerts ──────────────────────────────────────────────────────────────────

/** Label lisible du type d'alerte */
export function alertTypeLabel(type: AlertType): string {
  const labels: Record<AlertType, string> = {
    health: 'Health',
    geofence: 'Geofencing',
    battery: 'Battery',
    offline: 'Offline',
    activity_deviation_low: 'Low Activity',
    activity_deviation_high: 'High Activity',
    custom: 'Custom',
  };
  return labels[type] ?? type;
}

/** Icône Ionicons pour type d'alerte */
export function alertTypeIcon(type: AlertType): string {
  const icons: Record<AlertType, string> = {
    health: 'heart-outline',
    geofence: 'location-outline',
    battery: 'battery-dead-outline',
    offline: 'wifi-outline',
    activity_deviation_low: 'trending-down-outline',
    activity_deviation_high: 'trending-up-outline',
    custom: 'alert-circle-outline',
  };
  return icons[type] ?? 'alert-circle-outline';
}

/** Couleur de sévérité */
export function alertSeverityColor(severity: AlertSeverity): string {
  return Colors.severity[severity];
}

/** Label sévérité */

export function alertSeverityLabel(severity: AlertSeverity): string {
  const labels: Record<AlertSeverity, string> = {
    info: 'Info',
    warning: 'Warning',
    critical: 'Critical',
  };
  return labels[severity];
}

/** Vrai si alerte encore active (non résolue) */
export function isAlertActive(alert: Alert): boolean {
  return alert.resolved_at === null;
}

/** Vrai si alerte acquittée mais non résolue */
export function isAlertAcknowledged(alert: Alert): boolean {
  return alert.acknowledged_at !== null && alert.resolved_at === null;
}

// ─── Dates ────────────────────────────────────────────────────────────────────

/** Formate une date ISO en français "Il y a 5 minutes" */
export function timeAgo(isoDate: string | null): string {
  if (!isoDate) return '–';
  try {
    return formatDistanceToNow(parseISO(isoDate), { addSuffix: true, locale: enUS });
  } catch {
    return '–';
  }
}

/** Formate une date ISO en "14 mars 2024, 10:30" */
export function formatDateTime(isoDate: string | null): string {
  if (!isoDate) return '–';
  try {
    return format(parseISO(isoDate), "MMM d, yyyy, HH:mm", { locale: enUS });
  } catch {
    return '–';
  }
}

/** Formate une date ISO en "14/03/2024" */
export function formatDate(isoDate: string | null): string {
  if (!isoDate) return '–';
  try {
    return format(parseISO(isoDate), 'MM/dd/yyyy');
  } catch {
    return '–';
  }
}

// ─── Nombres ──────────────────────────────────────────────────────────────────

/** Formate poids en "450 kg" */
export function formatWeight(kg: number | null): string {
  if (kg === null) return '–';
  return `${kg.toFixed(0)} kg`;
}

/** Formate température boîtier (capteur interne/électronique, pas une température corporelle) */
export function formatTemperature(celsius: number | null | undefined): string {
  if (celsius === null || celsius === undefined || isNaN(celsius)) return '–';
  return `${celsius.toFixed(1)} °C`;
}

/** Formate température avec mention explicite boîtier pour éviter toute confusion médicale */
export function formatDeviceTemperature(celsius: number | null | undefined): string {
  if (celsius === null || celsius === undefined || isNaN(celsius)) return '–';
  return `${celsius.toFixed(1)} °C (device)`;
}

/** Formate activité en g avec indicateur qualitatif */
export function formatActivity(g: number): string {
  return `${g.toFixed(2)} g`;
}

/** Formate coordonnées GPS */
export function formatCoords(lat: number | null, lon: number | null): string {
  if (lat === null || lon === null) return 'Unknown position';
  return `${lat.toFixed(5)}° N, ${lon.toFixed(5)}° E`;
}

// ─── Machine Learning ─────────────────────────────────────────────────────────

/**
 * Returns a color based on ML confidence score (0.0 to 1.0).
 * >80% = Green (High), >50% = Orange (Medium), else Red (Low)
 */
export function confidenceColor(confidence: number | null | undefined): string {
  if (confidence == null) return Colors.text.muted;
  if (confidence >= 0.8) return '#27AE60'; // Green
  if (confidence >= 0.5) return '#F39C12'; // Orange
  return '#E74C3C'; // Red
}
