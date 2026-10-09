/**
 * Transfer an animal to another farm (platform admin only). The collar moves with it;
 * the receiving farm sees its health history, not its past locations, and the previous
 * farm's open alerts on it are resolved as "animal transferred".
 */
import React from 'react';
import { Text, StyleSheet, TouchableOpacity } from 'react-native';
import { showDialog } from './dialog';

import apiClient from '../api/client';
import { Colors, Spacing, Typography } from '../constants/config';
import { showApiError } from '../utils/apiErrors';
import AppModal, { ModalButton } from './AppModal';

interface FarmOption { id: number; name: string }

interface Props {
  visible: boolean;
  animal: { id: number; name: string; farm_id: number; assigned_device?: string | null };
  farms: FarmOption[];
  onClose: () => void;
  onTransferred: () => void;
}

export function transferMessage(animalName: string, fromFarm: string, toFarm: string, collar?: string | null): string {
  const collarLine = collar ? ` Collar ${collar} moves with it.` : '';
  return `Transfer ${animalName} from ${fromFarm} to ${toFarm}?${collarLine} ${toFarm} will see its health history, not its past locations.`;
}

export default function TransferAnimalModal({ visible, animal, farms, onClose, onTransferred }: Props) {
  const fromFarm = farms.find((farm) => farm.id === animal.farm_id)?.name ?? 'its farm';
  const targets = farms.filter((farm) => farm.id !== animal.farm_id);

  const confirm = (target: FarmOption) => {
    showDialog('Confirm transfer', transferMessage(animal.name, fromFarm, target.name, animal.assigned_device), [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Transfer',
        style: 'destructive',
        onPress: async () => {
          try {
            await apiClient.post(`/animals/${animal.id}/transfer`, { target_farm_id: target.id });
            onTransferred();
          } catch (error) {
            showApiError(error, 'Could not transfer', 'Unable to transfer the animal.');
          }
        },
      },
    ]);
  };

  return (
    <AppModal visible={visible} title={`Transfer ${animal.name}`} subtitle={`From ${fromFarm} to:`} onClose={onClose}
      footer={<ModalButton label="Cancel" kind="secondary" onPress={onClose} />}>
      {targets.length === 0 && <Text style={styles.sub}>No other farm.</Text>}
      {targets.map((farm) => (
        <TouchableOpacity key={farm.id} style={styles.farm} onPress={() => confirm(farm)}>
          <Text style={styles.farmName}>{farm.name}</Text>
        </TouchableOpacity>
      ))}
    </AppModal>
  );
}

const styles = StyleSheet.create({
  sub: { fontSize: Typography.sm, color: Colors.text.secondary },
  farm: { paddingVertical: Spacing.md, paddingHorizontal: Spacing.sm, borderBottomWidth: 1, borderBottomColor: Colors.border.default },
  farmName: { fontSize: Typography.base, color: Colors.text.primary },
});
