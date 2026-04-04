/**
 * ProfileScreen - User profile management
 * Displays user info, allows editing name/phone/password
 * Role display only — role changes are admin-only (via Users screen)
 */
import React, { useState, useEffect } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TextInput,
  TouchableOpacity, Alert, ActivityIndicator,
  KeyboardAvoidingView, Platform,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { DrawerActions } from '@react-navigation/native';
import { useNavigation } from '@react-navigation/native';
import { useAuthStore } from '../store/authStore';
import { Colors, Radius, Spacing, Typography } from '../constants/config';
import apiClient from '../api/client';

// ─── Role config ──────────────────────────────────────────────────────────────

const ROLE_LABELS: Record<string, string> = {
  farmer: 'Farmer',
  owner:  'Farm Owner',
  vet:    'Veterinarian',
  admin:  'Administrator',
};

const ROLE_COLORS: Record<string, string> = {
  farmer: Colors.primary,
  owner:  '#3498DB',
  vet:    '#9B59B6',
  admin:  '#E74C3C',
};

const ROLE_ICONS: Record<string, string> = {
  farmer: 'leaf-outline',
  owner:  'briefcase-outline',
  vet:    'medkit-outline',
  admin:  'shield-outline',
};

// ─── Sub-components ───────────────────────────────────────────────────────────

function SectionTitle({ title }: { title: string }) {
  return <Text style={styles.sectionTitle}>{title}</Text>;
}

function InfoRow({
  icon, label, value, last,
}: {
  icon: string; label: string; value: string; last?: boolean;
}) {
  return (
    <View style={[styles.infoRow, last && { borderBottomWidth: 0 }]}>
      <View style={styles.infoIconBg}>
        <Ionicons name={icon as any} size={16} color={Colors.primary} />
      </View>
      <Text style={styles.infoLabel}>{label}</Text>
      <Text style={styles.infoValue} numberOfLines={1}>{value || '—'}</Text>
    </View>
  );
}

function EditableField({
  label, value, onChangeText, placeholder, secureTextEntry, keyboardType,
}: {
  label: string;
  value: string;
  onChangeText: (v: string) => void;
  placeholder?: string;
  secureTextEntry?: boolean;
  keyboardType?: 'default' | 'email-address' | 'phone-pad';
}) {
  return (
    <View style={styles.fieldContainer}>
      <Text style={styles.fieldLabel}>{label}</Text>
      <TextInput
        style={styles.input}
        value={value}
        onChangeText={onChangeText}
        placeholder={placeholder}
        placeholderTextColor={Colors.text.muted}
        secureTextEntry={secureTextEntry}
        keyboardType={keyboardType ?? 'default'}
        autoCapitalize="none"
      />
    </View>
  );
}

// ─── Screen ───────────────────────────────────────────────────────────────────

export default function ProfileScreen() {
  const navigation = useNavigation<any>();
  const { user, role, logout, token } = useAuthStore();

  const [editing, setEditing]   = useState(false);
  const [saving, setSaving]     = useState(false);
  const [loading, setLoading]   = useState(true);

  // Full profile from API (more complete than store)
  const [profile, setProfile] = useState<any>(null);

  // Edit form state
  const [form, setForm] = useState({
    name:             '',
    phone:            '',
    currentPassword:  '',
    newPassword:      '',
    confirmPassword:  '',
  });

  // Load full profile on mount
  useEffect(() => {
    apiClient.get('/auth/me')
      .then(({ data }) => {
        setProfile(data);
        setForm(f => ({
          ...f,
          name:  data.name  ?? '',
          phone: data.phone ?? '',
        }));
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const set = (key: keyof typeof form) => (value: string) =>
    setForm(prev => ({ ...prev, [key]: value }));

  const handleSave = async () => {
    // Validate password change if requested
    if (form.newPassword) {
      if (form.newPassword.length < 6) {
        Alert.alert('Error', 'New password must be at least 6 characters.');
        return;
      }
      if (form.newPassword !== form.confirmPassword) {
        Alert.alert('Error', 'Passwords do not match.');
        return;
      }
    }

    setSaving(true);
    try {
      const payload: any = {
        name:  form.name.trim()  || null,
        phone: form.phone.trim() || null,
      };
      if (form.newPassword) {
        payload.password = form.newPassword;
      }

      const { data } = await apiClient.put('/auth/me', payload);

      // Update local store with new info
      setProfile(data);
      setForm(f => ({
        ...f,
        name:            data.name  ?? '',
        phone:           data.phone ?? '',
        currentPassword: '',
        newPassword:     '',
        confirmPassword: '',
      }));

      setEditing(false);
      Alert.alert('Success', 'Profile updated successfully.');
    } catch (err: any) {
      Alert.alert('Error', err.response?.data?.detail ?? 'Failed to update profile.');
    } finally {
      setSaving(false);
    }
  };

  const handleLogout = () => {
    Alert.alert('Sign Out', 'Are you sure you want to sign out?', [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Sign Out', style: 'destructive', onPress: logout },
    ]);
  };

  const cancelEdit = () => {
    // Reset form to current profile values
    setForm({
      name:            profile?.name  ?? '',
      phone:           profile?.phone ?? '',
      currentPassword: '',
      newPassword:     '',
      confirmPassword: '',
    });
    setEditing(false);
  };

  const roleColor = ROLE_COLORS[role ?? ''] ?? Colors.primary;
  const roleLabel = ROLE_LABELS[role ?? ''] ?? role ?? 'Unknown';
  const roleIcon  = ROLE_ICONS[role ?? '']  ?? 'person-outline';

  // Initials for avatar
  const initials = (profile?.name ?? profile?.email ?? '?')
    .split(' ')
    .map((w: string) => w[0])
    .join('')
    .toUpperCase()
    .slice(0, 2);

  if (loading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator color={Colors.primary} size="large" />
      </View>
    );
  }

  return (
    <KeyboardAvoidingView
      style={styles.screen}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <ScrollView
        contentContainerStyle={styles.content}
        showsVerticalScrollIndicator={false}
        keyboardShouldPersistTaps="handled"
      >

        {/* ── Avatar + role badge ──────────────────────────────────── */}
        <View style={styles.heroSection}>
          <View style={[styles.avatar, { borderColor: roleColor + '60' }]}>
            <Text style={[styles.avatarInitials, { color: roleColor }]}>{initials}</Text>
          </View>

          <Text style={styles.heroName}>{profile?.name ?? 'No name set'}</Text>
          <Text style={styles.heroEmail}>{profile?.email}</Text>

          <View style={[styles.roleBadge, { backgroundColor: roleColor + '20', borderColor: roleColor + '40' }]}>
            <Ionicons name={roleIcon as any} size={14} color={roleColor} />
            <Text style={[styles.roleText, { color: roleColor }]}>{roleLabel}</Text>
          </View>

          {/* Role info note */}
          <Text style={styles.roleNote}>
            Role changes can only be made by an administrator.
          </Text>
        </View>

        {/* ── Account info (read-only) ─────────────────────────────── */}
        {!editing && (
          <>
            <SectionTitle title="Account Information" />
            <View style={styles.card}>
              <InfoRow icon="person-outline"   label="Full name" value={profile?.name ?? ''} />
              <InfoRow icon="mail-outline"      label="Email"     value={profile?.email ?? ''} />
              <InfoRow icon="call-outline"      label="Phone"     value={profile?.phone ?? ''} />
              <InfoRow
                icon="calendar-outline"
                label="Member since"
                value={profile?.created_at
                  ? new Date(profile.created_at).toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' })
                  : ''}
              />
              <InfoRow
                icon="time-outline"
                label="Last login"
                value={profile?.last_login
                  ? new Date(profile.last_login).toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric', hour: '2-digit', minute: '2-digit' })
                  : 'Never'}
                last
              />
            </View>

            {/* Edit button */}
            <TouchableOpacity style={styles.editBtn} onPress={() => setEditing(true)}>
              <Ionicons name="create-outline" size={18} color="#fff" />
              <Text style={styles.editBtnText}>Edit Profile</Text>
            </TouchableOpacity>
          </>
        )}

        {/* ── Edit form ────────────────────────────────────────────── */}
        {editing && (
          <>
            <SectionTitle title="Edit Profile" />
            <View style={styles.card}>
              <View style={styles.cardInner}>
                <EditableField
                  label="Full name"
                  value={form.name}
                  onChangeText={set('name')}
                  placeholder="Your full name"
                  keyboardType="default"
                />
                <EditableField
                  label="Phone number"
                  value={form.phone}
                  onChangeText={set('phone')}
                  placeholder="+1 234 567 8900"
                  keyboardType="phone-pad"
                />
              </View>
            </View>

            <SectionTitle title="Change Password" />
            <Text style={styles.passwordNote}>Leave blank to keep your current password.</Text>
            <View style={styles.card}>
              <View style={styles.cardInner}>
                <EditableField
                  label="New password"
                  value={form.newPassword}
                  onChangeText={set('newPassword')}
                  placeholder="Min. 6 characters"
                  secureTextEntry
                />
                <EditableField
                  label="Confirm new password"
                  value={form.confirmPassword}
                  onChangeText={set('confirmPassword')}
                  placeholder="Repeat new password"
                  secureTextEntry
                />
              </View>
            </View>

            {/* Save / Cancel */}
            <TouchableOpacity
              style={[styles.saveBtn, saving && { opacity: 0.6 }]}
              onPress={handleSave}
              disabled={saving}
            >
              {saving
                ? <ActivityIndicator color="#fff" size="small" />
                : <>
                    <Ionicons name="checkmark-circle-outline" size={18} color="#fff" />
                    <Text style={styles.saveBtnText}>Save Changes</Text>
                  </>
              }
            </TouchableOpacity>

            <TouchableOpacity style={styles.cancelBtn} onPress={cancelEdit}>
              <Text style={styles.cancelBtnText}>Cancel</Text>
            </TouchableOpacity>
          </>
        )}

        {/* ── Danger zone ──────────────────────────────────────────── */}
        <SectionTitle title="Session" />
        <TouchableOpacity style={styles.logoutBtn} onPress={handleLogout}>
          <Ionicons name="log-out-outline" size={18} color={Colors.severity.critical} />
          <Text style={styles.logoutBtnText}>Sign Out</Text>
        </TouchableOpacity>

      </ScrollView>
    </KeyboardAvoidingView>
  );
}

// ─── Styles ──────────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
  screen:  { flex: 1, backgroundColor: Colors.bg.primary },
  center:  { flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: Colors.bg.primary },
  content: { padding: Spacing.base, paddingBottom: 60 },

  // Hero
  heroSection: {
    alignItems: 'center',
    paddingVertical: Spacing['2xl'],
  },
  avatar: {
    width: 88, height: 88, borderRadius: 44,
    backgroundColor: Colors.bg.elevated,
    alignItems: 'center', justifyContent: 'center',
    borderWidth: 3, marginBottom: Spacing.md,
  },
  avatarInitials: {
    fontSize: Typography['2xl'], fontWeight: '700',
  },
  heroName: {
    fontSize: Typography.xl, fontWeight: '700',
    color: Colors.text.primary, marginBottom: 4,
  },
  heroEmail: {
    fontSize: Typography.sm, color: Colors.text.muted,
    marginBottom: Spacing.md,
  },
  roleBadge: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    paddingHorizontal: Spacing.md, paddingVertical: 6,
    borderRadius: Radius.full, borderWidth: 1,
    marginBottom: Spacing.sm,
  },
  roleText:  { fontSize: Typography.sm, fontWeight: '700' },
  roleNote:  {
    fontSize: Typography.xs, color: Colors.text.muted,
    textAlign: 'center', paddingHorizontal: Spacing.xl,
  },

  // Section title
  sectionTitle: {
    fontSize: Typography.xs, fontWeight: '700', color: Colors.text.muted,
    textTransform: 'uppercase', letterSpacing: 0.8,
    marginTop: Spacing.xl, marginBottom: Spacing.sm,
  },

  // Info card
  card: {
    backgroundColor: Colors.bg.card, borderRadius: Radius.lg,
    borderWidth: 1, borderColor: Colors.border.default, overflow: 'hidden',
  },
  cardInner: { padding: Spacing.md, gap: Spacing.md },
  infoRow: {
    flexDirection: 'row', alignItems: 'center',
    padding: Spacing.md, gap: Spacing.md,
    borderBottomWidth: 1, borderBottomColor: Colors.border.default,
  },
  infoIconBg: {
    width: 32, height: 32, borderRadius: Radius.md,
    backgroundColor: Colors.primary + '15',
    alignItems: 'center', justifyContent: 'center',
  },
  infoLabel: { flex: 1, fontSize: Typography.sm, color: Colors.text.secondary },
  infoValue: { fontSize: Typography.sm, fontWeight: '600', color: Colors.text.primary, maxWidth: '50%', textAlign: 'right' },

  // Edit form
  fieldContainer:  { gap: 6 },
  fieldLabel:      { fontSize: Typography.sm, color: Colors.text.secondary, fontWeight: '500' },
  input: {
    backgroundColor: Colors.bg.input, borderWidth: 1,
    borderColor: Colors.border.default, borderRadius: Radius.md,
    paddingHorizontal: Spacing.md, paddingVertical: Spacing.sm + 2,
    color: Colors.text.primary, fontSize: Typography.base,
  },
  passwordNote: { fontSize: Typography.xs, color: Colors.text.muted, marginBottom: Spacing.sm },

  // Buttons
  editBtn: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    gap: Spacing.sm, backgroundColor: Colors.primary,
    padding: Spacing.md, borderRadius: Radius.md, marginTop: Spacing.base,
  },
  editBtnText:  { color: '#fff', fontWeight: '700', fontSize: Typography.base },

  saveBtn: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    gap: Spacing.sm, backgroundColor: Colors.primary,
    padding: Spacing.md, borderRadius: Radius.md, marginTop: Spacing.base,
  },
  saveBtnText:  { color: '#fff', fontWeight: '700', fontSize: Typography.base },

  cancelBtn: {
    alignItems: 'center', padding: Spacing.md,
    borderRadius: Radius.md, marginTop: Spacing.sm,
    borderWidth: 1, borderColor: Colors.border.default,
  },
  cancelBtnText: { color: Colors.text.secondary, fontSize: Typography.base },

  logoutBtn: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    gap: Spacing.sm, padding: Spacing.md, borderRadius: Radius.md,
    borderWidth: 1, borderColor: Colors.severity.critical + '50',
    backgroundColor: Colors.severity.critical + '10',
    marginTop: Spacing.sm,
  },
  logoutBtnText: { color: Colors.severity.critical, fontWeight: '600', fontSize: Typography.base },
});