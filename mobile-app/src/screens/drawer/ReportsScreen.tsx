import React, { useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator, Alert, ScrollView, StyleSheet, Text, TextInput,
  TouchableOpacity, View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { format, isMatch, subDays } from 'date-fns';

import DrawerScreenBase from './DrawerScreenBase';
import { Colors, Radius, Spacing, Typography } from '../../constants/config';
import { useReportExport, useReportPreview } from '../../hooks/useReports';
import ReportPreviewTable from '../../components/ReportPreviewTable';
import { useAuthStore } from '../../store/authStore';
import { useFarmStore } from '../../store/farmStore';
import { ReportDataset } from '../../types';

const DATASETS: { value: ReportDataset; label: string; icon: string }[] = [
  { value: 'telemetry', label: 'Telemetry', icon: 'pulse-outline' },
  { value: 'untimed_telemetry', label: 'Untimed windows', icon: 'time-outline' },
  { value: 'daily_summaries', label: 'Daily summaries', icon: 'calendar-outline' },
  { value: 'alerts', label: 'Alerts', icon: 'warning-outline' },
  { value: 'prediction_feedbacks', label: 'Prediction feedback', icon: 'analytics-outline' },
  { value: 'alert_feedbacks', label: 'Alert feedback', icon: 'checkmark-done-outline' },
];

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
const PREVIEW_DELAY_MS = 600;

function useDebouncedValue<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timeout = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timeout);
  }, [delay, value]);
  return debounced;
}

export default function ReportsScreen() {
  const role = useAuthStore((state) => state.role);
  const currentFarmId = useFarmStore((state) => state.currentFarmId);
  const currentFarm = useFarmStore((state) =>
    state.farms.find((farm) => farm.id === state.currentFarmId),
  );
  if (role !== 'admin') {
    return (
      <DrawerScreenBase title="Reports & Exports">
        <View style={styles.centerState}>
          <Ionicons name="lock-closed-outline" size={42} color={Colors.text.muted} />
          <Text style={styles.stateTitle}>Administrator access required</Text>
        </View>
      </DrawerScreenBase>
    );
  }
  return <ReportsWorkspace key={currentFarmId ?? 'all'} farmId={currentFarmId ?? undefined}
    farmName={currentFarm?.name ?? 'All farms'} />;
}

function ReportsWorkspace({ farmId, farmName }: { farmId?: number; farmName: string }) {
  const [dataset, setDataset] = useState<ReportDataset>('telemetry');
  const [deviceId, setDeviceId] = useState('');
  const [dateFrom, setDateFrom] = useState(format(subDays(new Date(), 7), 'yyyy-MM-dd'));
  const [dateTo, setDateTo] = useState(format(new Date(), 'yyyy-MM-dd'));
  const exportReport = useReportExport();
  const untimed = dataset === 'untimed_telemetry';
  const datesRequired = dataset === 'telemetry' || untimed;
  const datesValid = useMemo(
    () => (!dateFrom || (ISO_DATE.test(dateFrom) && isMatch(dateFrom, 'yyyy-MM-dd'))) &&
      (!dateTo || (ISO_DATE.test(dateTo) && isMatch(dateTo, 'yyyy-MM-dd'))),
    [dateFrom, dateTo],
  );
  const params = useMemo(() => ({ dataset, farmId, dateFrom: dateFrom || undefined, dateTo: dateTo || undefined,
    ...(untimed && deviceId.trim() ? { deviceId: deviceId.trim() } : {}) }),
    [dataset, farmId, dateFrom, dateTo, untimed, deviceId]);
  const filterKey = JSON.stringify(params);
  const debouncedParams = useDebouncedValue(params, PREVIEW_DELAY_MS);
  const debouncedKey = JSON.stringify(debouncedParams);
  const periodValid = datesValid && (!datesRequired || (!!dateFrom && !!dateTo)) &&
    (!dateFrom || !dateTo || dateTo >= dateFrom);
  const filtersSettled = filterKey === debouncedKey;
  const previewQuery = useReportPreview(debouncedParams, periodValid && filtersSettled);
  const previewIsCurrent = filtersSettled && previewQuery.data?.dataset === dataset;
  const preview = previewIsCurrent && !previewQuery.isError ? previewQuery.data : undefined;
  const previewPending = periodValid && (!filtersSettled || previewQuery.isFetching || previewQuery.isLoading);
  const busy = exportReport.isPending;

  const validatePeriod = () => {
    if (datesRequired && (!dateFrom || !dateTo)) {
      Alert.alert('Dates required', untimed ? 'Both reception dates are required.' : 'Telemetry exports require a start and end date.');
      return false;
    }
    if (!datesValid || (dateFrom && dateTo && dateTo < dateFrom)) {
      Alert.alert('Invalid period', 'Use YYYY-MM-DD and ensure the end date follows the start date.');
      return false;
    }
    return true;
  };

  const handleExport = async () => {
    if (!validatePeriod() || !previewIsCurrent || !preview?.rows.length || busy || previewQuery.isFetching) return;
    try {
      await exportReport.mutateAsync(params);
    } catch (error) {
      Alert.alert('Export unavailable', error instanceof Error ? error.message : 'Unable to export data.');
    }
  };

  return (
    <DrawerScreenBase title="Reports & Exports" subtitle={untimed ? `Reception context: ${farmName}` : farmName}>
      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        <Text style={styles.sectionLabel}>DATASET</Text>
        <View style={styles.datasetGrid}>
          {DATASETS.map((item) => {
            const selected = item.value === dataset;
            return (
              <TouchableOpacity
                key={item.value}
                style={[styles.datasetButton, selected && styles.datasetButtonActive]}
                onPress={() => setDataset(item.value)}
                disabled={exportReport.isPending}
                accessibilityLabel={item.label}
                accessibilityRole="radio"
                accessibilityState={{ checked: selected }}
              >
                <Ionicons name={item.icon as any} size={18} color={selected ? Colors.primary : Colors.text.muted} />
                <Text style={[styles.datasetText, selected && styles.datasetTextActive]}>{item.label}</Text>
              </TouchableOpacity>
            );
          })}
        </View>

        {untimed && <View>
          <Text style={styles.sectionLabel}>DEVICE</Text>
          <TextInput accessibilityLabel="Device ID" maxLength={50} autoCapitalize="none"
            value={deviceId} onChangeText={setDeviceId} editable={!busy} placeholder="All devices"
            placeholderTextColor={Colors.text.disabled} style={styles.input} />
        </View>}
        <Text style={styles.sectionLabel}>{untimed ? 'RECEPTION PERIOD' : 'PERIOD'}</Text>
        <View style={styles.dateRow}>
          <View style={styles.field}>
            <Text style={styles.fieldLabel}>{untimed ? 'Received from' : 'From'}</Text>
            <TextInput accessibilityLabel={untimed ? 'Received from date' : 'From date'} editable={!exportReport.isPending}
              value={dateFrom} onChangeText={setDateFrom} placeholder="YYYY-MM-DD"
              placeholderTextColor={Colors.text.disabled} style={styles.input} autoCapitalize="none" />
          </View>
          <View style={styles.field}>
            <Text style={styles.fieldLabel}>{untimed ? 'Received to' : 'To'}</Text>
            <TextInput accessibilityLabel={untimed ? 'Received to date' : 'To date'} editable={!exportReport.isPending}
              value={dateTo} onChangeText={setDateTo} placeholder="YYYY-MM-DD"
              placeholderTextColor={Colors.text.disabled} style={styles.input} autoCapitalize="none" />
          </View>
        </View>
        {!datesRequired && <Text style={styles.hint}>Leave both dates empty to export the full history.</Text>}

        <View style={styles.previewSection}>
          <View style={styles.previewHeading}>
            <View style={styles.previewLabel}>
              <Ionicons name="eye-outline" size={19} color={Colors.primaryLight} />
              <Text style={styles.previewTitle}>Data preview</Text>
            </View>
            {preview && <Text style={styles.rowCount}>
              {preview.has_more ? `First ${preview.rows.length} rows` : `${preview.rows.length} rows`}
            </Text>}
          </View>
          {!periodValid ? (
            <View style={styles.previewState} accessibilityLiveRegion="polite">
              <Ionicons name="calendar-outline" size={28} color={Colors.text.muted} />
              <Text style={styles.stateTitle}>Select a valid period</Text>
              {datesRequired && <Text style={styles.hint}>{untimed ? 'Both reception dates are required.' : 'Telemetry requires both dates.'}</Text>}
            </View>
          ) : previewPending ? (
            <View style={styles.previewState} accessibilityLiveRegion="polite">
              <ActivityIndicator color={Colors.primaryLight} />
              <Text style={styles.stateTitle}>Updating preview...</Text>
              <Text style={styles.hint}>Up to 20 rows will be loaded.</Text>
            </View>
          ) : previewQuery.isError ? (
            <View style={styles.previewState} accessibilityLiveRegion="polite">
              <Ionicons name="alert-circle-outline" size={28} color={Colors.severity.warning} />
              <Text style={styles.stateTitle}>Preview unavailable</Text>
              <Text style={styles.hint}>{previewQuery.error instanceof Error
                ? previewQuery.error.message : 'Unable to load data.'}</Text>
              <TouchableOpacity accessibilityRole="button" accessibilityLabel="Retry preview"
                disabled={previewQuery.isFetching} onPress={() => void previewQuery.refetch()} style={styles.retryButton}>
                <Ionicons name="refresh-outline" size={18} color={Colors.primaryLight} />
                <Text style={styles.retryText}>Try again</Text>
              </TouchableOpacity>
            </View>
          ) : preview ? <>
          <Text style={styles.hint}>Period: {preview.target_timezone} / Timestamps: UTC</Text>
          <Text style={styles.hint}>Captured: {new Date(preview.generated_at).toLocaleString('en-GB', { timeZone: 'UTC' })} UTC</Text>
          {preview.rows.length ? <ReportPreviewTable key={JSON.stringify(params)} preview={preview} /> : (
            <View style={styles.previewState}>
              <Ionicons name="file-tray-outline" size={30} color={Colors.text.muted} />
              <Text style={styles.stateTitle}>No data for these filters</Text>
            </View>
          )}
          {preview.has_more && <Text style={styles.hint}>More rows available in the full CSV.</Text>}
          <Text style={styles.hint}>Data may change between preview and export.</Text>
          </> : null}
        </View>
        <TouchableOpacity
          accessibilityRole="button" accessibilityLabel="Export and share CSV"
          accessibilityState={{ disabled: busy || previewQuery.isFetching || !preview?.rows.length }}
          style={[styles.exportButton, (busy || previewQuery.isFetching || !preview?.rows.length) && styles.buttonDisabled]}
          onPress={handleExport}
          disabled={busy || previewQuery.isFetching || !preview?.rows.length}
        >
          {exportReport.isPending
            ? <ActivityIndicator color="#fff" />
            : <Ionicons name="download-outline" size={20} color="#fff" />}
          <Text style={styles.exportText}>{exportReport.isPending ? 'Preparing CSV...' : 'Export and share CSV'}</Text>
        </TouchableOpacity>
      </ScrollView>
    </DrawerScreenBase>
  );
}

const styles = StyleSheet.create({
  content: { padding: Spacing.base, paddingBottom: Spacing['3xl'] },
  sectionLabel: { fontSize: Typography.xs, fontWeight: '700', color: Colors.text.muted, marginBottom: Spacing.sm, marginTop: Spacing.md },
  datasetGrid: { gap: Spacing.sm },
  datasetButton: { minHeight: 46, flexDirection: 'row', alignItems: 'center', gap: Spacing.sm, paddingHorizontal: Spacing.md, borderRadius: Radius.sm, borderWidth: 1, borderColor: Colors.border.default, backgroundColor: Colors.bg.card },
  datasetButtonActive: { borderColor: Colors.primary, backgroundColor: Colors.primaryMuted },
  datasetText: { color: Colors.text.secondary, fontSize: Typography.sm, fontWeight: '600', flexShrink: 1 },
  datasetTextActive: { color: Colors.text.primary },
  dateRow: { flexDirection: 'row', gap: Spacing.sm },
  field: { flex: 1 },
  fieldLabel: { color: Colors.text.secondary, fontSize: Typography.xs, marginBottom: Spacing.xs },
  input: { minHeight: 46, borderRadius: Radius.sm, borderWidth: 1, borderColor: Colors.border.default, backgroundColor: Colors.bg.input, color: Colors.text.primary, paddingHorizontal: Spacing.md, fontSize: Typography.sm },
  hint: { color: Colors.text.muted, fontSize: Typography.xs, marginTop: Spacing.sm },
  previewSection: { marginTop: Spacing.xl, padding: Spacing.md, borderRadius: Radius.sm,
    borderWidth: 1, borderColor: Colors.border.default, backgroundColor: Colors.bg.card },
  previewHeading: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', gap: Spacing.sm },
  previewLabel: { flexDirection: 'row', alignItems: 'center', gap: Spacing.sm },
  previewTitle: { color: Colors.text.primary, fontSize: Typography.base, fontWeight: '700' },
  rowCount: { color: Colors.text.secondary, fontSize: Typography.xs },
  previewState: { minHeight: 150, paddingVertical: Spacing.xl, alignItems: 'center', justifyContent: 'center', gap: Spacing.sm },
  retryButton: { minHeight: 44, marginTop: Spacing.sm, paddingHorizontal: Spacing.md, flexDirection: 'row',
    alignItems: 'center', justifyContent: 'center', gap: Spacing.sm, borderRadius: Radius.sm,
    borderWidth: 1, borderColor: Colors.primary },
  retryText: { color: Colors.primaryLight, fontSize: Typography.sm, fontWeight: '600' },
  exportButton: { minHeight: 50, marginTop: Spacing.xl, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: Spacing.sm, backgroundColor: Colors.primary, borderRadius: Radius.sm },
  buttonDisabled: { opacity: 0.6 },
  exportText: { color: '#fff', fontWeight: '700', fontSize: Typography.base },
  centerState: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: Spacing.md, padding: Spacing.xl },
  stateTitle: { color: Colors.text.secondary, fontSize: Typography.base, textAlign: 'center' },
});
