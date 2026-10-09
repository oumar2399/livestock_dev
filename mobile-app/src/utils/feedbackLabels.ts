/**
 * Behaviour correction in prediction feedback: the app sends a stable code and shows an
 * English label. The backend stores the value as free text (max 50 characters) and does
 * not restrict it.
 *
 * Before Phase 4 the app sent the displayed text itself; those rows are not migrated and
 * are read through LEGACY_CORRECTION_CODES.
 */

export type CorrectionCode = 'active' | 'resting' | 'grazing' | 'walking' | 'lying' | 'running';

export const BEHAVIOR_CORRECTIONS: { code: CorrectionCode; label: string }[] = [
  { code: 'active', label: 'Active' },
  { code: 'resting', label: 'Resting' },
  { code: 'grazing', label: 'Grazing' },
  { code: 'walking', label: 'Walking' },
  { code: 'lying', label: 'Lying' },
  { code: 'running', label: 'Running' },
];

/** Values stored before Phase 4 (the displayed text at the time) → code. */
export const LEGACY_CORRECTION_CODES: Record<string, CorrectionCode> = {
  'Active': 'active',
  'Resting': 'resting',
  'Grazing (Pâturage)': 'grazing',
  'Walking (Marche)': 'walking',
  'Lying (Couché)': 'lying',
  'Running (Course)': 'running',
};

export function correctionCode(stored: string | null | undefined): CorrectionCode | null {
  if (!stored) return null;
  if (BEHAVIOR_CORRECTIONS.some((item) => item.code === stored)) return stored as CorrectionCode;
  return LEGACY_CORRECTION_CODES[stored] ?? null;
}

/** English label for a stored value; an unknown value is shown as stored. */
export function correctionLabel(stored: string | null | undefined): string {
  const code = correctionCode(stored);
  if (code) return BEHAVIOR_CORRECTIONS.find((item) => item.code === code)!.label;
  return stored ?? '';
}
