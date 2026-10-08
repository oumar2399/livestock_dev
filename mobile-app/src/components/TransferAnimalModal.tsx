/**
 * Transfer an animal to another farm (platform admin only). The collar moves with it;
 * the receiving farm sees its health history, not its past locations, and the previous
 * farm's open alerts on it are resolved as "animal transferred".
 */
import React from 'react';
import { View, Text, StyleSheet, Modal, TouchableOpacity, ScrollView, Alert } from 'react-native';

import apiClient from '../api/client';
import { Colors, Radius, Spacing, Typography } from '../constants/config';
import { showApiError } from '../utils/apiErrors';

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
    Alert.alert('Confirm transfer', transferMessage(animal.name, fromFarm, target.name, animal.assigned_device), [
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
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <View style={styles.overlay}>
        <View style={styles.sheet}>
          <Text style={styles.title}>Transfer {animal.name}</Text>
          <Text style={styles.sub}>From {fromFarm} to:</Text>
          <ScrollView style={styles.list}>
            {targets.length === 0 && <Text style={styles.sub}>No other farm.</Text>}
            {targets.map((farm) => (
              <TouchableOpacity key={farm.id} style={styles.farm} onPress={() => confirm(farm)}>
                <Text style={styles.farmName}>{farm.name}</Text>
              </TouchableOpacity>
            ))}
          </ScrollView>
          <TouchableOpacity style={styles.cancel} onPress={onClose}>
            <Text style={styles.cancelText}>Cancel</Text>
          </TouchableOpacity>
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  overlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.7)', justifyContent: 'center', padding: Spacing.base },
  sheet: { maxHeight: '80%', backgroundColor: Colors.bg.card, borderRadius: Radius.lg, padding: Spacing.base, gap: Spacing.sm },
  title: { fontSize: Typography.md, fontWeight: '700', color: Colors.text.primary },
  sub: { fontSize: Typography.sm, color: Colors.text.secondary },
  list: { flexGrow: 0 },
  farm: { paddingVertical: Spacing.md, paddingHorizontal: Spacing.sm, borderBottomWidth: 1, borderBottomColor: Colors.border.default },
  farmName: { fontSize: Typography.base, color: Colors.text.primary },
  cancel: { paddingVertical: Spacing.md, borderRadius: Radius.md, backgroundColor: Colors.bg.input, alignItems: 'center' },
  cancelText: { color: Colors.text.secondary, fontWeight: '600', fontSize: Typography.sm },
});
