import type { GeoPoint, TelemetryLatest } from '../types';

// Freshness of received telemetry, not a guarantee of a live GPS fix.
export const RECENT_POSITION_MS = 30 * 60 * 1000;
export const GEOFENCE_POSITION_LIMIT = 100;

export function isMapPoint(point: GeoPoint): boolean {
  return Number.isFinite(point.latitude) && Number.isFinite(point.longitude)
    && Math.abs(point.latitude) <= 90 && Math.abs(point.longitude) <= 180;
}

export function mapAnimals(records: TelemetryLatest[]): TelemetryLatest[] {
  return records.filter((record) => isMapPoint(record))
    .sort((a, b) => a.animal_name.localeCompare(b.animal_name));
}

export function positionRecency(timestamp: string, now: number): 'recent' | 'old' | 'unknown' {
  const age = now - Date.parse(timestamp);
  if (!Number.isFinite(age) || age < 0) return 'unknown';
  return age < RECENT_POSITION_MS ? 'recent' : 'old';
}

export function editablePoints(points: GeoPoint[]): GeoPoint[] {
  const copy = points.map((point) => ({ ...point }));
  if (copy.length > 3) {
    const first = copy[0];
    const last = copy[copy.length - 1];
    if (first.latitude === last.latitude && first.longitude === last.longitude) copy.pop();
  }
  return copy;
}

export function initialMapRegion(coordinates: GeoPoint[]) {
  const point = coordinates.find(isMapPoint);
  return point
    ? { latitude: point.latitude, longitude: point.longitude, latitudeDelta: 0.02, longitudeDelta: 0.02 }
    : { latitude: 0, longitude: 0, latitudeDelta: 150, longitudeDelta: 300 };
}
