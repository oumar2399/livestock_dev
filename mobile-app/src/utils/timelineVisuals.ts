import { Colors } from '../constants/config';
import type { TimelineEventType } from '../types';

export interface EventVisual { icon: string; color: string }

const eventVisuals: Record<TimelineEventType, EventVisual> = {
  alert: { icon: 'warning-outline', color: Colors.severity.warning },
  daily_summary: { icon: 'calendar-outline', color: Colors.severity.info },
  prediction_feedback: { icon: 'analytics-outline', color: Colors.primary },
  alert_feedback: { icon: 'checkmark-done-outline', color: '#9B59B6' },
  veterinary_entry: { icon: 'medkit-outline', color: Colors.severity.critical },
};

const FALLBACK_VISUAL: EventVisual = { icon: 'ellipse-outline', color: Colors.text.muted };

/** Icon and color for a timeline event; a type the app does not know yet gets a neutral visual. */
export function eventVisual(eventType: string): EventVisual {
  return Object.prototype.hasOwnProperty.call(eventVisuals, eventType)
    ? eventVisuals[eventType as TimelineEventType]
    : FALLBACK_VISUAL;
}
