import React, { useCallback, useEffect, useState } from 'react';
import {
  View, Text, StyleSheet, FlatList, TouchableOpacity,
  ActivityIndicator, TextInput,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import DrawerScreenBase from './DrawerScreenBase';
import { Colors, Spacing, Typography, Radius } from '../../constants/config';
import { useAuthStore } from '../../store/authStore';
import { useFarmStore } from '../../store/farmStore';
import apiClient from '../../api/client';
import { showApiError } from '../../utils/apiErrors';
import { FarmMembership, FarmMembershipList } from '../../types';
import { showDialog } from '../../components/dialog';
import AppModal, { ModalButton } from '../../components/AppModal';

const ROLE_LABELS: Record<string, string> = {
  farmer: 'Farmer', owner: 'Owner', vet: 'Veterinarian', admin: 'Admin',
};
const ROLE_COLORS: Record<string, string> = {
  farmer: Colors.primary, owner: '#3498DB', vet: '#9B59B6', admin: '#E74C3C',
};
export default function UsersScreen() {
  const { isAdmin, user } = useAuthStore();
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
      showApiError(error, 'Could not load members', 'Unable to load members');
    } finally {
      setLoading(false);
    }
  }, [currentFarmId]);

  useEffect(() => { load(); }, [load]);
  const handleChangeRole = (membershipId: number, newRole: string) => {
    if (!currentFarmId) return;
    showDialog('Change Role', `Assign role "${ROLE_LABELS[newRole]}" ?`, [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Confirm', onPress: async () => {
          try {
            await apiClient.patch(`/farms/${currentFarmId}/members/${membershipId}`, { role: newRole });
            load();
          } catch (error) {
            showApiError(error, 'Could not change role', 'Unable to change role');
          }
        },
      },
    ]);
  };

  const sendInvite = async () => {
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
      showDialog('Success', `${inviteForm.email} was added to ${currentFarm?.name ?? 'the farm'}`);
    } catch (error) {
      showApiError(error, 'Could not invite', 'Unable to invite this member');
    }
  };

  // The invitation targets the selected farm: say which one before anything is sent.
  const handleInvite = () => {
    if (!currentFarmId || !currentFarm) return;
    const email = inviteForm.email.trim();
    if (!email) {
      showDialog('Required field', 'Enter the email address to invite.');
      return;
    }
    showDialog(
      'Confirm invitation',
      `Invite ${email} as ${ROLE_LABELS[inviteForm.role]} into ${currentFarm.name}?`,
      [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Invite', onPress: () => { void sendInvite(); } },
      ],
    );
  };

  const handleRevoke = (membership: FarmMembership) => {
    if (!currentFarmId) return;
    showDialog('Revoke access', `Remove ${membership.user_name ?? membership.user_email} from this farm?`, [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Revoke',
        style: 'destructive',
        onPress: async () => {
          try {
            await apiClient.delete(`/farms/${currentFarmId}/members/${membership.id}`);
            load();
          } catch (error) {
            showApiError(error, 'Could not revoke access', 'Unable to revoke access');
          }
        },
      },
    ]);
  };

  return (
    <DrawerScreenBase
      title="Users"
      subtitle={`${currentFarm?.name ?? 'No farm selected'} · ${users.length} member${users.length === 1 ? '' : 's'}`}
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
              {item.user_id === user?.id ? (
                // Nobody changes or revokes their own membership (the server refuses it too).
                <Text style={styles.youText}>You</Text>
              ) : canManage && item.status !== 'revoked' ? (
                <View style={styles.memberActions}>
                  <TouchableOpacity
                    style={styles.memberActionBtn}
                    onPress={() => {
                      showDialog(
                        'Change role',
                        `New role for ${item.user_name ?? item.user_email}:`,
                        [
                          ...['farmer', 'owner', 'vet'].filter(r => r !== item.role).map(r => ({
                            text: ROLE_LABELS[r],
                            onPress: () => handleChangeRole(item.id, r),
                          })),
                          { text: 'Cancel', style: 'cancel' as const, onPress: () => {} },
                        ]
                      );
                    }}
                  >
                    <Text style={styles.memberActionText}>Change role</Text>
                  </TouchableOpacity>
                  <TouchableOpacity style={[styles.memberActionBtn, styles.memberActionDanger]} onPress={() => handleRevoke(item)}>
                    <Text style={[styles.memberActionText, styles.memberActionDangerText]}>Revoke</Text>
                  </TouchableOpacity>
                </View>
              ) : null}
            </View>
          )}
        />
      )}
      {/* Invitation */}
      <AppModal
        visible={showInvite}
        title="Invite Member"
        subtitle={`Into farm: ${currentFarm?.name ?? '—'}`}
        onClose={() => setShowInvite(false)}
        primaryAction={{ label: 'Invite', onPress: handleInvite }}
        footer={(
          <>
            <ModalButton label="Cancel" kind="secondary" onPress={() => setShowInvite(false)} />
            <ModalButton label="Invite" onPress={handleInvite} />
          </>
        )}
      >
        {[
          { label: 'Email', key: 'email', placeholder: 'email@example.com' },
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
      </AppModal>
    </DrawerScreenBase>
  );
}

const styles = StyleSheet.create({
  memberActions: { gap: Spacing.xs, alignItems: 'flex-end' },
  memberActionBtn: {
    paddingHorizontal: Spacing.sm, paddingVertical: 6, borderRadius: Radius.md,
    borderWidth: 1, borderColor: Colors.border.default, backgroundColor: Colors.bg.elevated,
  },
  memberActionText: { fontSize: Typography.xs, fontWeight: '600', color: Colors.text.secondary },
  memberActionDanger: { borderColor: Colors.severity.critical },
  memberActionDangerText: { color: Colors.severity.critical },
  youText: { fontSize: Typography.xs, fontWeight: '700', color: Colors.text.muted },
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
  field: { marginBottom: Spacing.md },
  fieldLabel: { fontSize: Typography.sm, color: Colors.text.secondary, marginBottom: 4 },
  input: { backgroundColor: Colors.bg.input, borderRadius: Radius.md, borderWidth: 1, borderColor: Colors.border.default, paddingHorizontal: Spacing.md, paddingVertical: Spacing.sm, color: Colors.text.primary },
  roleRow: { flexDirection: 'row', gap: Spacing.sm, marginTop: 4 },
  roleBtn: { flex: 1, paddingVertical: Spacing.sm, borderRadius: Radius.md, borderWidth: 1, borderColor: Colors.border.default, alignItems: 'center' },
  roleBtnText: { fontSize: Typography.sm, color: Colors.text.secondary },
});
