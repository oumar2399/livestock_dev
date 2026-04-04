/**
 * Fonctions utilitaires - Formatage et logique métier
 * Basées sur les valeurs réelles du backend (enums, seuils)
 */
import { format, formatDistanceToNow, parseISO } from 'date-fns';
import { fr } from 'date-fns/locale';
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
  return sex === 'M' ? 'Mâle' : 'Femelle';
}

/** Âge en années depuis birth_date (format "YYYY-MM-DD") */
export function animalAge(birthDate: string | null): string {
  if (!birthDate) return '–';
  const birth = new Date(birthDate);
  const now = new Date();
  const years = now.getFullYear() - birth.getFullYear();
  const months = now.getMonth() - birth.getMonth();
  const totalMonths = years * 12 + months;

  if (totalMonths < 1) return '< 1 mois';
  if (totalMonths < 12) return `${totalMonths} mois`;
  const y = Math.floor(totalMonths / 12);
  const m = totalMonths % 12;
  return m > 0 ? `${y} ans ${m} mois` : `${y} an${y > 1 ? 's' : ''}`;
}

/** Indicateur de fraîcheur de la donnée GPS */
export function isRecentUpdate(lastUpdate: string | null, maxMinutes = 30): boolean {
  if (!lastUpdate) return false;
  const diff = Date.now() - new Date(lastUpdate).getTime();
  return diff < maxMinutes * 60 * 1000;
}

// ─── Télémétrie / Comportement ────────────────────────────────────────────────

/** Label lisible de l'état d'activité */
export function activityStateLabel(state: ActivityState | null | undefined): string {
  if (!state) return '–';
  const labels: Record<ActivityState, string> = {
    lying: 'Lying',
    standing: 'Standing',
    walking: 'Walking',
    running: 'Running',
  };
  return labels[state];
}

/** Couleur de l'état d'activité */
export function activityStateColor(state: ActivityState | null | undefined): string {
  if (!state) return Colors.status.unknown;
  return Colors.behavior[state] ?? Colors.status.unknown;
}

/** Icône Ionicons pour état d'activité */
export function activityStateIcon(state: ActivityState | null | undefined): string {
  const icons: Record<ActivityState, string> = {
    lying: 'bed-outline',
    standing: 'body-outline',
    walking: 'walk-outline',
    running: 'fitness-outline',
  };
  return state ? (icons[state] ?? 'help-circle-outline') : 'help-circle-outline';
}

/**
 * Couleur batterie
 * Seuils cohérents avec alerts backend :
 * - Warning <20% (alert type "battery" severity "warning")
 * - Critical <10% (alert type "battery" severity "critical")
 */
export function batteryColor(level: number): string {
  if (level >= 50) return Colors.battery.full;
  if (level >= 20) return Colors.battery.medium;
  return Colors.battery.low;
}

/** Icône batterie Ionicons */
export function batteryIcon(level: number): string {
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
    return formatDistanceToNow(parseISO(isoDate), { addSuffix: true, locale: fr });
  } catch {
    return '–';
  }
}

/** Formate une date ISO en "14 mars 2024, 10:30" */
export function formatDateTime(isoDate: string | null): string {
  if (!isoDate) return '–';
  try {
    return format(parseISO(isoDate), "d MMM yyyy, HH:mm", { locale: fr });
  } catch {
    return '–';
  }
}

/** Formate une date ISO en "14/03/2024" */
export function formatDate(isoDate: string | null): string {
  if (!isoDate) return '–';
  try {
    return format(parseISO(isoDate), 'dd/MM/yyyy');
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

/** Formate température en "38.5 °C" */
export function formatTemperature(celsius: number | null): string {
  if (celsius === null) return '–';
  return `${celsius.toFixed(1)} °C`;
}

/** Formate activité en g avec indicateur qualitatif */
export function formatActivity(g: number): string {
  return `${g.toFixed(2)} g`;
}

/** Formate coordonnées GPS */
export function formatCoords(lat: number | null, lon: number | null): string {
  if (lat === null || lon === null) return 'Position inconnue';
  return `${lat.toFixed(5)}° N, ${lon.toFixed(5)}° E`;
}
