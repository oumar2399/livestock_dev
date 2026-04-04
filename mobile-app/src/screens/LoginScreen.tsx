/**
 * LoginScreen - Écran de connexion
 * Prêt pour JWT quand POST /auth/login sera implémenté
 * En dev : bouton "Bypass" pour passer directement
 */
import React, { useState } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  KeyboardAvoidingView,
  ScrollView,
  Platform,
  ActivityIndicator,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';

import { useAuthStore } from '../store/authStore';
import { Colors, Radius, Spacing, Typography } from '../constants/config';

export default function LoginScreen() {
  const insets = useSafeAreaInsets();
  const { login, hydrate, isLoading, error, clearError } = useAuthStore();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);

  const handleLogin = () => {
    if (!email.trim() || !password.trim()) return;
    clearError();
    login({ username: email.trim(), password });
  };

  // Dev only : bypass auth
  const handleDevBypass = () => {
    hydrate();
  };

  return (
    <KeyboardAvoidingView
      style={styles.screen}
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
      keyboardVerticalOffset={Platform.OS === 'ios' ? 0 : 24}
    >
      <ScrollView
        contentContainerStyle={[
          styles.scrollContent,
          { paddingTop: insets.top + Spacing.xl, paddingBottom: insets.bottom + Spacing['2xl'] },
        ]}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
      >
      {/* Logo */}
      <View style={styles.logoSection}>
        <View style={styles.logoCircle}>
          <Text style={styles.logoEmoji}>🐄</Text>
        </View>
        <Text style={styles.appName}>Livestock Monitor</Text>
        <Text style={styles.appTagline}>Surveillance intelligente de troupeau</Text>
      </View>

      {/* Form */}
      <View style={styles.form}>
        {/* Note JWT */}
        <View style={styles.noteBanner}>
          <Ionicons name="information-circle-outline" size={16} color={Colors.status.warning} />
          <Text style={styles.noteText}>
            Authentification en cours d'implémentation backend
          </Text>
        </View>

        {/* Email */}
        <View style={styles.field}>
          <Text style={styles.fieldLabel}>Email</Text>
          <View style={styles.inputWrapper}>
            <Ionicons name="mail-outline" size={18} color={Colors.text.muted} style={styles.inputIcon} />
            <TextInput
              style={styles.input}
              placeholder="votre@email.com"
              placeholderTextColor={Colors.text.muted}
              value={email}
              onChangeText={setEmail}
              autoCapitalize="none"
              keyboardType="email-address"
              autoComplete="email"
            />
          </View>
        </View>

        {/* Password */}
        <View style={styles.field}>
          <Text style={styles.fieldLabel}>Mot de passe</Text>
          <View style={styles.inputWrapper}>
            <Ionicons name="lock-closed-outline" size={18} color={Colors.text.muted} style={styles.inputIcon} />
            <TextInput
              style={styles.input}
              placeholder="••••••••"
              placeholderTextColor={Colors.text.muted}
              value={password}
              onChangeText={setPassword}
              secureTextEntry={!showPassword}
              autoComplete="password"
            />
            <TouchableOpacity onPress={() => setShowPassword(!showPassword)} hitSlop={12}>
              <Ionicons
                name={showPassword ? 'eye-off-outline' : 'eye-outline'}
                size={18}
                color={Colors.text.muted}
              />
            </TouchableOpacity>
          </View>
        </View>

        {/* Erreur */}
        {error && (
          <View style={styles.errorBanner}>
            <Ionicons name="alert-circle-outline" size={16} color={Colors.severity.critical} />
            <Text style={styles.errorText}>{error}</Text>
          </View>
        )}

        {/* Bouton connexion */}
        <TouchableOpacity
          style={[styles.loginBtn, isLoading && styles.loginBtnDisabled]}
          onPress={handleLogin}
          disabled={isLoading}
          activeOpacity={0.85}
        >
          {isLoading ? (
            <ActivityIndicator size="small" color="#fff" />
          ) : (
            <Text style={styles.loginBtnText}>Se connecter</Text>
          )}
        </TouchableOpacity>

        {/* Dev bypass */}
        {__DEV__ && (
          <TouchableOpacity style={styles.bypassBtn} onPress={handleDevBypass}>
            <Ionicons name="code-slash-outline" size={14} color={Colors.text.muted} />
            <Text style={styles.bypassText}>Mode développement (bypass auth)</Text>
          </TouchableOpacity>
        )}
      </View>

      <Text style={styles.footer}>
        Backend : FastAPI + PostgreSQL · Master Recherche Japon
      </Text>

      </ScrollView>
    </KeyboardAvoidingView>
  );
}

// ─── Styles ──────────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: Colors.bg.primary,
  },
  scrollContent: {
    flexGrow: 1,
    paddingHorizontal: Spacing.base,
    justifyContent: 'center',
  },

  logoSection: { alignItems: 'center', marginBottom: Spacing['3xl'] },
  logoCircle: {
    width: 88,
    height: 88,
    borderRadius: Radius.full,
    backgroundColor: Colors.primaryMuted,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: Spacing.base,
    borderWidth: 2,
    borderColor: Colors.primary + '50',
  },
  logoEmoji: { fontSize: 44 },
  appName: {
    fontSize: Typography['2xl'],
    fontWeight: '800',
    color: Colors.text.primary,
    letterSpacing: -0.5,
    marginBottom: 4,
  },
  appTagline: { fontSize: Typography.sm, color: Colors.text.secondary },

  form: { gap: Spacing.md },

  noteBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: Colors.status.warning + '15',
    borderRadius: Radius.md,
    padding: Spacing.sm,
    gap: Spacing.xs,
    borderWidth: 1,
    borderColor: Colors.status.warning + '30',
  },
  noteText: { flex: 1, fontSize: Typography.xs, color: Colors.status.warning },

  field: { gap: Spacing.xs },
  fieldLabel: { fontSize: Typography.sm, fontWeight: '600', color: Colors.text.secondary, marginLeft: 2 },
  inputWrapper: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: Colors.bg.input,
    borderRadius: Radius.lg,
    paddingHorizontal: Spacing.md,
    height: 52,
    borderWidth: 1,
    borderColor: Colors.border.default,
    gap: Spacing.sm,
  },
  inputIcon: {},
  input: { flex: 1, color: Colors.text.primary, fontSize: Typography.base },

  errorBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: Colors.severity.critical + '15',
    borderRadius: Radius.md,
    padding: Spacing.sm,
    gap: Spacing.xs,
    borderWidth: 1,
    borderColor: Colors.severity.critical + '30',
  },
  errorText: { flex: 1, fontSize: Typography.sm, color: Colors.severity.critical },

  loginBtn: {
    backgroundColor: Colors.primary,
    borderRadius: Radius.lg,
    height: 52,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: Spacing.sm,
  },
  loginBtnDisabled: { opacity: 0.6 },
  loginBtnText: { color: '#fff', fontSize: Typography.md, fontWeight: '700' },

  bypassBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 5,
    paddingVertical: Spacing.sm,
  },
  bypassText: { fontSize: Typography.xs, color: Colors.text.muted },

  footer: {
    textAlign: 'center',
    fontSize: Typography.xs,
    color: Colors.text.muted,
    marginTop: Spacing.xl,
  },
});