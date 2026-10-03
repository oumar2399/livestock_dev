import type { FarmAccess, FarmMembershipRole } from '../types';

interface FarmRoleState {
  farms: FarmAccess[];
  currentFarmId: number | null;
  isLoading: boolean;
  error: string | null;
}

/** Display only. API authorization remains the source of access decisions. */
export function selectedFarmRole(accountRole: string | null, state: FarmRoleState): FarmMembershipRole | null {
  if (accountRole === 'admin') return 'admin';
  if (!accountRole || state.isLoading || state.error) return null;
  const role = state.farms.find(farm => farm.id === state.currentFarmId)?.membership_role;
  return role === 'owner' || role === 'farmer' || role === 'vet' ? role : null;
}
