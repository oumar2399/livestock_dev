import React from 'react';
import {
  ActivityIndicator, Alert, Linking, ScrollView, StyleSheet, Text,
  TouchableOpacity, View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { format } from 'date-fns';

import DrawerScreenBase from './DrawerScreenBase';
import { Colors, Config, Radius, Spacing, Typography } from '../../constants/config';
import { useDailyJobRuns, useRunDailyJobs, useSystemStatus } from '../../hooks/useSystemStatus';
import { useAuthStore } from '../../store/authStore';

function StatusRow({ label, value, state }: {
  label: string;
  value: string;
  state?: 'good' | 'warning' | 'bad';
}) {
  const color = state === 'good'
    ? Colors.status.healthy
    : state === 'bad'
      ? Colors.status.critical
      : state === 'warning'
        ? Colors.status.warning
        : Colors.text.secondary;
  return (
    <View style={styles.statusRow}>
      <Text style={styles.statusLabel}>{label}</Text>
      <View style={styles.statusValueWrap}>
        {state && <View style={[styles.statusDot, { backgroundColor: color }]} />}
        <Text style={[styles.statusValue, { color }]} numberOfLines={1}>{value}</Text>
      </View>
    </View>
  );
}

export default function AppServSettings() {
  const role = useAuthStore((state) => state.role);
  const user = useAuthStore((state) => state.user);
  const logout = useAuthStore((state) => state.logout);
  const isAdmin = role === 'admin';
  const statusQuery = useSystemStatus(isAdmin);
  const jobsQuery = useDailyJobRuns(isAdmin);
  const runJobs = useRunDailyJobs();
  const system = statusQuery.data;

  const refresh = () => {
    statusQuery.refetch();
    jobsQuery.refetch();
  };

  const confirmRun = () => {
    Alert.alert('Run daily pipeline', 'Run the pipeline for yesterday in the target timezone?', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Run',
        onPress: async () => {
          try {
            await runJobs.mutateAsync(undefined);
            Alert.alert('Pipeline completed', 'The execution was added to the history.');
          } catch (error) {
            Alert.alert('Pipeline failed', error instanceof Error ? error.message : 'Unable to run the pipeline.');
          }
        },
      },
    ]);
  };

  const confirmLogout = () => {
    Alert.alert('Logout', 'Do you want to logout?', [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Logout', style: 'destructive', onPress: logout },
    ]);
  };

  return (
    <DrawerScreenBase
      title="App & Server"
      subtitle={user?.email}
      rightAction={isAdmin ? (
        <TouchableOpacity style={styles.iconButton} onPress={refresh} accessibilityLabel="Refresh status">
          <Ionicons name="refresh" size={21} color={Colors.primary} />
        </TouchableOpacity>
      ) : undefined}
    >
      <ScrollView contentContainerStyle={styles.content}>
        {isAdmin && (
          <>
            <Text style={styles.sectionLabel}>SYSTEM STATUS</Text>
            {statusQuery.isLoading ? (
              <ActivityIndicator color={Colors.primary} style={styles.loader} />
            ) : statusQuery.isError || !system ? (
              <TouchableOpacity style={styles.errorRow} onPress={() => statusQuery.refetch()}>
                <Ionicons name="cloud-offline-outline" size={20} color={Colors.status.critical} />
                <Text style={styles.errorText}>Status unavailable. Tap to retry.</Text>
              </TouchableOpacity>
            ) : (
              <View style={styles.group}>
                <StatusRow label="Overall" value={system.status}
                  state={system.status === 'healthy' ? 'good' : system.status === 'unhealthy' ? 'bad' : 'warning'} />
                <StatusRow label="Database"
                  value={system.database.latency_ms === null ? system.database.status : system.database.status + ' · ' + system.database.latency_ms.toFixed(1) + ' ms'}
                  state={system.database.status === 'up' ? 'good' : 'bad'} />
                <StatusRow label="ML model" value={system.model.status}
                  state={system.model.status === 'loaded' ? 'good' : 'bad'} />
                <StatusRow label="Schema" value={system.schema.revision ?? 'unknown'}
                  state={system.schema.revision ? 'good' : 'warning'} />
                <StatusRow label="Scheduler" value={system.scheduler.running ? 'running' : system.scheduler.enabled ? 'stopped' : 'disabled'}
                  state={system.scheduler.running ? 'good' : system.scheduler.enabled ? 'bad' : 'warning'} />
                <StatusRow label="Target timezone" value={system.target_timezone} />
              </View>
            )}

            <View style={styles.sectionHeading}>
              <Text style={styles.sectionLabel}>DAILY PIPELINE</Text>
              <TouchableOpacity style={[styles.runButton, runJobs.isPending && styles.disabled]}
                onPress={confirmRun} disabled={runJobs.isPending}>
                {runJobs.isPending
                  ? <ActivityIndicator size="small" color="#fff" />
                  : <Ionicons name="play" size={14} color="#fff" />}
                <Text style={styles.runText}>Run</Text>
              </TouchableOpacity>
            </View>
            <View style={styles.group}>
              {jobsQuery.isLoading ? (
                <ActivityIndicator color={Colors.primary} style={styles.loader} />
              ) : (jobsQuery.data?.runs.length ?? 0) === 0 ? (
                <Text style={styles.emptyText}>No recorded executions.</Text>
              ) : jobsQuery.data?.runs.slice(0, 10).map((run) => {
                const color = run.status === 'success'
                  ? Colors.status.healthy
                  : run.status === 'failed'
                    ? Colors.status.critical
                    : Colors.status.warning;
                return (
                  <View key={run.id} style={styles.jobRow}>
                    <View style={[styles.jobIcon, { backgroundColor: color + '20' }]}>
                      <Ionicons name={run.status === 'success' ? 'checkmark' : run.status === 'failed' ? 'close' : 'hourglass-outline'}
                        size={17} color={color} />
                    </View>
                    <View style={styles.jobBody}>
                      <Text style={styles.jobTitle}>{run.target_date} · {run.trigger_source}</Text>
                      <Text style={styles.jobMeta}>{format(new Date(run.started_at), 'MMM d, HH:mm')} · {run.timezone_name}</Text>
                      {run.error_message ? <Text style={styles.jobError} numberOfLines={2}>{run.error_message}</Text> : null}
                    </View>
                    <Text style={[styles.jobStatus, { color }]}>{run.status}</Text>
                  </View>
                );
              })}
            </View>
          </>
        )}

        <Text style={styles.sectionLabel}>CONNECTION</Text>
        <View style={styles.group}>
          <StatusRow label="API server" value={Config.API_BASE_URL} />
          <TouchableOpacity style={styles.linkRow}
            onPress={() => Linking.openURL(Config.API_BASE_URL.replace('/api/v1', '') + '/docs')}>
            <Ionicons name="document-text-outline" size={18} color={Colors.primary} />
            <Text style={styles.linkText}>Open API documentation</Text>
            <Ionicons name="open-outline" size={17} color={Colors.text.muted} />
          </TouchableOpacity>
        </View>

        <Text style={styles.sectionLabel}>APPLICATION</Text>
        <View style={styles.group}>
          <StatusRow label="Version" value="1.0.0" />
          <StatusRow label="Backend" value="FastAPI + PostgreSQL" />
          <StatusRow label="Map refresh" value={Config.MAP_REFRESH_INTERVAL / 1000 + ' seconds'} />
        </View>

        <TouchableOpacity style={styles.logoutButton} onPress={confirmLogout}>
          <Ionicons name="log-out-outline" size={19} color={Colors.status.critical} />
          <Text style={styles.logoutText}>Logout</Text>
        </TouchableOpacity>
      </ScrollView>
    </DrawerScreenBase>
  );
}

const styles = StyleSheet.create({
  content: { padding: Spacing.base, paddingBottom: Spacing['3xl'] },
  sectionLabel: { fontSize: Typography.xs, fontWeight: '700', color: Colors.text.muted, marginTop: Spacing.lg, marginBottom: Spacing.sm },
  sectionHeading: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: Spacing.lg },
  group: { borderRadius: Radius.sm, borderWidth: 1, borderColor: Colors.border.default, backgroundColor: Colors.bg.card, overflow: 'hidden' },
  statusRow: { minHeight: 46, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: Spacing.md, paddingHorizontal: Spacing.md, borderBottomWidth: StyleSheet.hairlineWidth, borderColor: Colors.border.default },
  statusLabel: { color: Colors.text.secondary, fontSize: Typography.sm },
  statusValueWrap: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'flex-end', gap: Spacing.xs },
  statusValue: { maxWidth: '80%', textAlign: 'right', color: Colors.text.primary, fontSize: Typography.xs, fontWeight: '700' },
  statusDot: { width: 8, height: 8, borderRadius: 4 },
  iconButton: { width: 40, height: 40, alignItems: 'center', justifyContent: 'center' },
  loader: { margin: Spacing.lg },
  errorRow: { minHeight: 50, flexDirection: 'row', alignItems: 'center', gap: Spacing.sm, padding: Spacing.md, borderRadius: Radius.sm, borderWidth: 1, borderColor: Colors.status.critical + '50' },
  errorText: { color: Colors.text.secondary, fontSize: Typography.sm },
  runButton: { height: 34, minWidth: 72, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: Spacing.xs, borderRadius: Radius.sm, backgroundColor: Colors.primary },
  runText: { color: '#fff', fontSize: Typography.xs, fontWeight: '700' },
  disabled: { opacity: 0.6 },
  jobRow: { minHeight: 62, flexDirection: 'row', alignItems: 'center', gap: Spacing.sm, padding: Spacing.md, borderBottomWidth: StyleSheet.hairlineWidth, borderColor: Colors.border.default },
  jobIcon: { width: 32, height: 32, borderRadius: Radius.sm, alignItems: 'center', justifyContent: 'center' },
  jobBody: { flex: 1 },
  jobTitle: { color: Colors.text.primary, fontSize: Typography.sm, fontWeight: '700' },
  jobMeta: { color: Colors.text.muted, fontSize: Typography.xs, marginTop: 2 },
  jobError: { color: Colors.status.critical, fontSize: Typography.xs, marginTop: 3 },
  jobStatus: { fontSize: Typography.xs, fontWeight: '700' },
  emptyText: { color: Colors.text.muted, fontSize: Typography.sm, padding: Spacing.md, textAlign: 'center' },
  linkRow: { minHeight: 48, flexDirection: 'row', alignItems: 'center', gap: Spacing.sm, paddingHorizontal: Spacing.md },
  linkText: { flex: 1, color: Colors.text.primary, fontSize: Typography.sm, fontWeight: '600' },
  logoutButton: { height: 48, marginTop: Spacing.xl, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: Spacing.sm, borderRadius: Radius.sm, borderWidth: 1, borderColor: Colors.status.critical + '60' },
  logoutText: { color: Colors.status.critical, fontWeight: '700' },
});
