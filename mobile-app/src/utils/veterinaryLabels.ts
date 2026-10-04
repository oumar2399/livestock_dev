import type { VeterinaryEntry } from '../api/veterinary';

/** Journal header for an entry. The backend writes status_change entries itself
 * (content "Status: provisional → closed"), so only their header needs a label. */
export function entryTypeLabel(entryType: VeterinaryEntry['entry_type']): string {
  return entryType === 'status_change' ? 'STATUS CHANGE' : entryType.toUpperCase();
}
