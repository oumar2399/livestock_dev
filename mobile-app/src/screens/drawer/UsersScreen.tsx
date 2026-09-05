import React, { useCallback, useEffect, useState } from 'react';
import {
  View, Text, StyleSheet, FlatList, TouchableOpacity,
  Alert, ActivityIndicator, Modal, TextInput,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import DrawerScreenBase from './DrawerScreenBase';
import { Colors, Spacing, Typography, Radius } from '../../constants/config';
import { useAuthStore } from '../../store/authStore';
import { useFarmStore } from '../../store/farmStore';
import apiClient from '../../api/client';
import { FarmMembership, FarmMembershipList } from '../../types';

const ROLE_LABELS: Record<string, string> = {
  farmer: 'Farmer', owner: 'Owner', vet: 'Veterinarian', admin: 'Admin',
};
const ROLE_COLORS: Record<string, string> = {
  farmer: Colors.primary, owner: '#3498DB', vet: '#9B59B6', admin: '#E74C3C',
};
export default function UsersScreen() {
  const { isAdmin } = useAuthStore();
  const { farms, currentFarmId } = useFarmStore();
  const currentFarm = farms.find((farm) => farm.id === currentFarmId) ?? null;
  const canManage = isAdmin() || (currentFarm?.permissions.includes('invite_members') ?? false);
  const [users, setUsers]     = useState<FarmMembership[]>([]);
  const [loading, setLoading] = useState(true);
  const [showInvite, setShowInvite] = useState(false);
  const [inviteForm, setInviteForm] = useState({ email: '', name: '', role: 'vet', password: '' });

  const load = useCallback(async () => {
    if (!currentFarmId) {
      setUsers([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const { data } = await apiClient.get<FarmMembershipList>(`/farms/${currentFarmId}/members`);
      setUsers(data.members);
    } catch (error) {
      Alert.alert('Error', error instanceof Error ? error.message : 'Unable to load members');
    } finally {
      setLoading(false);
    }
  }, [currentFarmId]);

  useEffect(() => { load(); }, [load]);
  const handleChangeRole = (membershipId: number, newRole: string) => {
    if (!currentFarmId) return;
    Alert.alert('Change Role', `Assign role "${ROLE_LABELS[newRole]}" ?`, [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Confirm', onPress: async () => {
          try {
            await apiClient.patch(`/farms/${currentFarmId}/members/${membershipId}`, { role: newRole });
            load();
          } catch (error) {
            Alert.alert('Error', error instanceof Error ? error.message : 'Unable to change role');
          }
        },
      },
    ]);
  };

  const handleInvite = async () => {
    if (!currentFarmId) return;
    try {
      await apiClient.post(`/farms/${currentFarmId}/members`, {
        user_email: inviteForm.email.trim(),
        name: inviteForm.name.trim() || null,
        password: inviteForm.password || null,
        role: inviteForm.role,
      });
      setShowInvite(false);
      setInviteForm({ email: '', name: '', role: 'vet', password: '' });
      load();
      Alert.alert('Success', `${inviteForm.email} was added to ${currentFarm?.name ?? 'the farm'}`);
    } catch (error) {
      Alert.alert('Error', error instanceof Error ? error.message : 'Error inviting member');
    }
  };

  const handleRevoke = (membership: FarmMembership) => {
    if (!currentFarmId) return;
    Alert.alert('Revoke access', `Remove ${membership.user_name ?? membership.user_email} from this farm?`, [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Revoke',
        style: 'destructive',
        onPress: async () => {
          try {
            await apiClient.delete(`/farms/${currentFarmId}/members/${membership.id}`);
            load();
          } catch (error) {
            Alert.alert('Error', error instanceof Error ? error.message : 'Unable to revoke access');
          }
        },
      },
    ]);
  };

  return (
    <DrawerScreenBase
      title="Users"
      subtitle={`${users.length} member${users.length > 1 ? 's' : ''}`}
      rightAction={
        canManage ? (
          <TouchableOpacity style={styles.addBtn} onPress={() => setShowInvite(true)}>
            <Ionicons name="person-add-outline" size={20} color={Colors.primary} />
          </TouchableOpacity>
        ) : undefined
      }
    >
      {loading ? (
        <View style={styles.center}><ActivityIndicator color={Colors.primary} /></View>
      ) : (
        <FlatList
          data={users}
          keyExtractor={membership => String(membership.id)}
          contentContainerStyle={styles.list}
          renderItem={({ item }) => (
            <View style={styles.card}>
              <View style={[styles.avatar, { backgroundColor: (ROLE_COLORS[item.role] ?? Colors.primary) + '20' }]}>
                <Text style={[styles.avatarText, { color: ROLE_COLORS[item.role] ?? Colors.primary }]}>
                  {(item.user_name ?? item.user_email ?? '?')[0].toUpperCase()}
                </Text>
              </View>
              <View style={styles.info}>
                <Text style={styles.name}>{item.user_name ?? item.user_email}</Text>
                <Text style={styles.email}>{item.user_email}</Text>
                <View style={[styles.roleBadge, { backgroundColor: (ROLE_COLORS[item.role] ?? Colors.primary) + '20' }]}>
                  <Text style={[styles.roleText, { color: ROLE_COLORS[item.role] ?? Colors.primary }]}>
                    {ROLE_LABELS[item.role] ?? item.role}
                  </Text>
                </View>
              </View>
              {canManage && item.status !== 'revoked' && (
                <TouchableOpacity
                  onPress={() => {
                    const roles = ['farmer', 'owner', 'vet'];
                    Alert.alert(
                      'Manage Member',
                      `Choose an action for ${item.user_name ?? item.user_email}:`,
                      [
                        ...roles.map(r => ({
                          text: ROLE_LABELS[r],
                          onPress: () => handleChangeRole(item.id, r),
                        })),
                        { text: 'Revoke access', style: 'destructive' as const, onPress: () => handleRevoke(item) },
                        { text: 'Cancel', style: 'cancel' as const, onPress: () => {} },
                      ]
                    );
                  }}
                >
                  <Ionicons name="chevron-forward" size={18} color={Colors.text.muted} />
                </TouchableOpacity>
              )}
            </View>
          )}
        />
      )}
      {/* Modal invitation */}
      <Modal visible={showInvite} transparent animationType="slide">
        <View style={styles.modalOverlay}>
          <View style={styles.modal}>
            <Text style={styles.modalTitle}>Invite Member</Text>
            {[
              { label: 'Email', key: 'email', placeholder: 'email@exemple.com' },
              { label: 'Name', key: 'name', placeholder: 'First Last' },
              { label: 'Password', key: 'password', placeholder: 'Min 8 characters' },
            ].map(({ label, key, placeholder }) => (
              <View key={key} style={styles.field}>
                <Text style={styles.fieldLabel}>{label}</Text>
                <TextInput
                  style={styles.input}
                  value={inviteForm[key as keyof typeof inviteForm]}
                  onChangeText={v => setInviteForm(p => ({ ...p, [key]: v }))}
                  placeholder={placeholder}
                  placeholderTextColor={Colors.text.muted}
                  secureTextEntry={key === 'password'}
                />
              </View>
            ))}
            <Text style={styles.fieldLabel}>Role</Text>
            <View style={styles.roleRow}>
              {['farmer', 'owner', 'vet'].map(r => (
                <TouchableOpacity
                  key={r}
                  style={[styles.roleBtn, inviteForm.role === r && { backgroundColor: (ROLE_COLORS[r]) + '20', borderColor: ROLE_COLORS[r] }]}
                  onPress={() => setInviteForm(p => ({ ...p, role: r }))}
                >
                  <Text style={[styles.roleBtnText, inviteForm.role === r && { color: ROLE_COLORS[r] }]}>
                    {ROLE_LABELS[r]}
                  </Text>
                </TouchableOpacity>
              ))}
            </View>
            <View style={styles.modalActions}>
              <TouchableOpacity style={styles.cancelBtn} onPress={() => setShowInvite(false)}>
                <Text style={styles.cancelText}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity style={styles.confirmBtn} onPress={handleInvite}>
                <Text style={styles.confirmText}>Invite</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>
    </DrawerScreenBase>
  );
}

const styles = StyleSheet.create({
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  list:   { padding: Spacing.base, gap: Spacing.sm },
  addBtn: { width: 36, height: 36, borderRadius: Radius.full, backgroundColor: Colors.primary + '20', alignItems: 'center', justifyContent: 'center' },
  card: { flexDirection: 'row', alignItems: 'center', backgroundColor: Colors.bg.card, borderRadius: Radius.lg, padding: Spacing.md, gap: Spacing.md, borderWidth: 1, borderColor: Colors.border.default },
  avatar: { width: 44, height: 44, borderRadius: 22, alignItems: 'center', justifyContent: 'center' },
  avatarText: { fontSize: 18, fontWeight: '700' },
  info: { flex: 1 },
  name: { fontSize: Typography.base, fontWeight: '600', color: Colors.text.primary },
  email: { fontSize: Typography.xs, color: Colors.text.muted, marginTop: 2 },
  roleBadge: { alignSelf: 'flex-start', marginTop: 4, paddingHorizontal: 8, paddingVertical: 2, borderRadius: Radius.full },
  roleText: { fontSize: Typography.xs, fontWeight: '700' },
  modalOverlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.6)', justifyContent: 'flex-end' },
  modal: { backgroundColor: Colors.bg.card, borderTopLeftRadius: 20, borderTopRightRadius: 20, padding: Spacing.base, paddingBottom: 40 },
  modalTitle: { fontSize: Typography.lg, fontWeight: '700', color: Colors.text.primary, marginBottom: Spacing.base },
  field: { marginBottom: Spacing.md },
  fieldLabel: { fontSize: Typography.sm, color: Colors.text.secondary, marginBottom: 4 },
  input: { backgroundColor: Colors.bg.input, borderRadius: Radius.md, borderWidth: 1, borderColor: Colors.border.default, paddingHorizontal: Spacing.md, paddingVertical: Spacing.sm, color: Colors.text.primary },
  roleRow: { flexDirection: 'row', gap: Spacing.sm, marginTop: 4, marginBottom: Spacing.base },
  roleBtn: { flex: 1, paddingVertical: Spacing.sm, borderRadius: Radius.md, borderWidth: 1, borderColor: Colors.border.default, alignItems: 'center' },
  roleBtnText: { fontSize: Typography.sm, color: Colors.text.secondary },
  modalActions: { flexDirection: 'row', gap: Spacing.sm, marginTop: Spacing.sm },
  cancelBtn: { flex: 1, padding: Spacing.md, borderRadius: Radius.md, borderWidth: 1, borderColor: Colors.border.default, alignItems: 'center' },
  cancelText: { color: Colors.text.secondary },
  confirmBtn: { flex: 1, padding: Spacing.md, borderRadius: Radius.md, backgroundColor: Colors.primary, alignItems: 'center' },
  confirmText: { color: '#fff', fontWeight: '700' },
});
