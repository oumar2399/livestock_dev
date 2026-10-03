import React, { useState, useMemo } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  ActivityIndicator,
  Alert,
  TextInput,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { format, subDays, isMatch } from 'date-fns';

import DrawerScreenBase from './DrawerScreenBase';
import { Colors, Radius, Spacing, Typography } from '../../constants/config';
import { useAuthStore } from '../../store/authStore';
import { useFarmStore } from '../../store/farmStore';
import { selectedFarmRole } from '../../utils/selectedFarmRole';
import {
  useFarmOverview,
  useFarmReportPreview,
  useFarmReportExport,
} from '../../hooks/useFarmReports';
import ReportPreviewTable from '../../components/ReportPreviewTable';
import { FarmReportDataset, ReportPreview } from '../../types';

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

export default function FarmReportsScreen() {
  const role = useAuthStore((state) => state.role);
  const farmState = useFarmStore();
  const currentFarmId = farmState.currentFarmId;
  const currentFarm = farmState.farms.find((f) => f.id === currentFarmId);
  const effectiveRole = selectedFarmRole(role, farmState);

  // Seuls les owners et admins de la ferme peuvent accéder aux rapports
  const isAuthorized = role === 'admin' || effectiveRole === 'owner';

  if (!currentFarmId) {
    return (
      <DrawerScreenBase title="Farm Reports & Quality">
        <View style={styles.centerState}>
          <Ionicons name="home-outline" size={48} color={Colors.text.muted} />
          <Text style={styles.stateTitle}>No Farm Selected</Text>
          <Text style={styles.stateText}>
            Please select a farm from the drawer to view its activity and quality reports.
          </Text>
        </View>
      </DrawerScreenBase>
    );
  }

  if (!isAuthorized) {
    return (
      <DrawerScreenBase title="Farm Reports & Quality">
        <View style={styles.centerState}>
          <Ionicons name="lock-closed-outline" size={48} color={Colors.text.muted} />
          <Text style={styles.stateTitle}>Owner Access Required</Text>
          <Text style={styles.stateText}>
            Farm reports and data quality indicators are reserved for farm owners and administrators.
          </Text>
        </View>
      </DrawerScreenBase>
    );
  }

  return (
    <DrawerScreenBase title={`Reports — ${currentFarm?.name ?? 'Farm'}`}>
      <FarmReportsWorkspace key={currentFarmId} farmId={currentFarmId} />
    </DrawerScreenBase>
  );
}

function FarmReportsWorkspace({ farmId }: { farmId: number }) {
  // Période par défaut : 7 derniers jours
  const [preset, setPreset] = useState<'7d' | '30d' | 'custom'>('7d');
  const [dateFrom, setDateFrom] = useState(format(subDays(new Date(), 6), 'yyyy-MM-dd'));
  const [dateTo, setDateTo] = useState(format(new Date(), 'yyyy-MM-dd'));
  const [selectedDataset, setSelectedDataset] = useState<FarmReportDataset>('farm_summary');

  const exportMutation = useFarmReportExport();

  const handleSelectPreset = (newPreset: '7d' | '30d' | 'custom') => {
    setPreset(newPreset);
    if (newPreset === '7d') {
      setDateFrom(format(subDays(new Date(), 6), 'yyyy-MM-dd'));
      setDateTo(format(new Date(), 'yyyy-MM-dd'));
    } else if (newPreset === '30d') {
      setDateFrom(format(subDays(new Date(), 29), 'yyyy-MM-dd'));
      setDateTo(format(new Date(), 'yyyy-MM-dd'));
    }
  };

  const datesValid = useMemo(() => {
    return (
      ISO_DATE.test(dateFrom) &&
      isMatch(dateFrom, 'yyyy-MM-dd') &&
      ISO_DATE.test(dateTo) &&
      isMatch(dateTo, 'yyyy-MM-dd') &&
      dateTo >= dateFrom
    );
  }, [dateFrom, dateTo]);

  const overviewParams = useMemo(
    () => ({ farmId, dateFrom, dateTo }),
    [farmId, dateFrom, dateTo],
  );

  const previewParams = useMemo(
    () => ({ farmId, dataset: selectedDataset, dateFrom, dateTo, limit: 20 }),
    [farmId, selectedDataset, dateFrom, dateTo],
  );

  const overviewQuery = useFarmOverview(overviewParams, datesValid);
  const previewQuery = useFarmReportPreview(previewParams, datesValid);

  const overview = overviewQuery.data;
  const preview = previewQuery.data;
  const exportDisabled = exportMutation.isPending || !datesValid || !preview || previewQuery.isFetching || previewQuery.isError;

  const handleExport = async () => {
    if (exportDisabled) return;
    if (!datesValid) {
      Alert.alert('Invalid Dates', 'Please provide valid start and end dates (YYYY-MM-DD).');
      return;
    }
    try {
      await exportMutation.mutateAsync({
        farmId,
        dataset: selectedDataset,
        dateFrom,
        dateTo,
      });
    } catch (err: any) {
      Alert.alert('Export Failed', err.message || 'An error occurred while downloading the report.');
    }
  };

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      {/* ── Sélecteur de période ── */}
      <View style={styles.card}>
        <Text style={styles.cardTitle}>Report Period</Text>
        <View style={styles.presetsRow}>
          <TouchableOpacity
            style={[styles.presetBtn, preset === '7d' && styles.presetBtnActive]}
            onPress={() => handleSelectPreset('7d')}
          >
            <Text style={[styles.presetText, preset === '7d' && styles.presetTextActive]}>
              Last 7 Days
            </Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[styles.presetBtn, preset === '30d' && styles.presetBtnActive]}
            onPress={() => handleSelectPreset('30d')}
          >
            <Text style={[styles.presetText, preset === '30d' && styles.presetTextActive]}>
              Last 30 Days
            </Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[styles.presetBtn, preset === 'custom' && styles.presetBtnActive]}
            onPress={() => handleSelectPreset('custom')}
          >
            <Text style={[styles.presetText, preset === 'custom' && styles.presetTextActive]}>
              Custom (max 31d)
            </Text>
          </TouchableOpacity>
        </View>

        {preset === 'custom' && (
          <View style={styles.customDateRow}>
            <View style={styles.dateInputGroup}>
              <Text style={styles.dateLabel}>From:</Text>
              <TextInput
                style={styles.dateInput}
                value={dateFrom}
                onChangeText={setDateFrom}
                placeholder="YYYY-MM-DD"
                maxLength={10}
              />
            </View>
            <View style={styles.dateInputGroup}>
              <Text style={styles.dateLabel}>To:</Text>
              <TextInput
                style={styles.dateInput}
                value={dateTo}
                onChangeText={setDateTo}
                placeholder="YYYY-MM-DD"
                maxLength={10}
              />
            </View>
          </View>
        )}
      </View>

      {/* ── Chargement ou Erreur ── */}
      {overviewQuery.isLoading && (
        <View style={styles.loadingBox}>
          <ActivityIndicator size="large" color={Colors.primary} />
          <Text style={styles.loadingText}>Computing quality metrics & farm overview...</Text>
        </View>
      )}

      {overviewQuery.isError && (
        <View style={styles.errorBox}>
          <Ionicons name="alert-circle-outline" size={32} color={Colors.severity.critical} />
          <Text style={styles.errorText}>
            {overviewQuery.error?.message || 'Failed to load report overview.'}
          </Text>
        </View>
      )}

      {overview && (
        <>
          {/* ── 1. État Actuel de la Ferme ── */}
          <View style={styles.card}>
            <View style={styles.cardHeaderRow}>
              <Text style={styles.cardTitle}>Current Status</Text>
              <Text style={styles.subtext}>
                at {format(new Date(overview.generated_at), 'HH:mm:ss')} (Tokyo)
              </Text>
            </View>

            <View style={styles.metricsGrid}>
              <View style={styles.metricItem}>
                <Text style={styles.metricLabel}>Total Herd</Text>
                <Text style={styles.metricValue}>{overview.current_state.total_animals}</Text>
                <Text style={styles.metricSub}>
                  {overview.current_state.animals_by_status.active ?? 0} active
                </Text>
              </View>
              <View style={styles.metricItem}>
                <Text style={styles.metricLabel}>Collar Devices</Text>
                <Text style={styles.metricValue}>{overview.current_state.total_devices}</Text>
                <Text style={styles.metricSub}>
                  {overview.current_state.assigned_devices_count} assigned
                </Text>
              </View>
              <View style={styles.metricItem}>
                <Text style={styles.metricLabel}>Telemetry Reception</Text>
                <Text style={styles.metricValue}>
                  {overview.current_state.last_reception?.freshness_status ?? 'No signal'}
                </Text>
                <Text style={styles.metricSub}>
                  {overview.current_state.last_reception
                    ? `${Math.round(overview.current_state.last_reception.age_seconds / 60)}m ago`
                    : 'Never received'}
                </Text>
              </View>
              <View style={styles.metricItem}>
                <Text style={styles.metricLabel}>Open Alerts</Text>
                <Text
                  style={[
                    styles.metricValue,
                    overview.current_state.active_alerts_count > 0 && { color: Colors.severity.critical },
                  ]}
                >
                  {overview.current_state.active_alerts_count}
                </Text>
                <Text style={styles.metricSub}>Requires attention</Text>
              </View>
            </View>
          </View>

          {/* ── 2. Bilan Période & Qualité des Données ── */}
          <View style={styles.card}>
            <View style={styles.cardHeaderRow}>
              <Text style={styles.cardTitle}>Period Coverage & Quality</Text>
              <View
                style={[
                  styles.statusBadge,
                  overview.period_summary.scope_status === 'available' && styles.statusBadgeGreen,
                  overview.period_summary.scope_status === 'partial' && styles.statusBadgeYellow,
                ]}
              >
                <Text style={styles.statusBadgeText}>
                  {overview.period_summary.scope_status.toUpperCase()}
                </Text>
              </View>
            </View>

            <View style={styles.metricsGrid}>
              <View style={styles.metricItem}>
                <Text style={styles.metricLabel}>Dated Windows</Text>
                <Text style={styles.metricValue}>{overview.period_summary.dated_windows_count}</Text>
                <Text style={styles.metricSub}>Strictly proven</Text>
              </View>
              <View style={styles.metricItem}>
                <Text style={styles.metricLabel}>Dated Coverage</Text>
                <Text style={styles.metricValue}>
                  {overview.period_summary.dated_coverage_ratio !== null &&
                  overview.period_summary.dated_coverage_ratio !== undefined
                    ? `${(overview.period_summary.dated_coverage_ratio * 100).toFixed(1)}%`
                    : '\u2014'}
                </Text>
                <Text style={styles.metricSub}>
                  {Math.round(overview.period_summary.dated_coverage_seconds / 3600)}h observed
                </Text>
              </View>
              <View style={styles.metricItem}>
                <Text style={styles.metricLabel}>Active Behavior</Text>
                <Text style={styles.metricValue}>
                  {overview.period_summary.behavior_breakdown.active_ratio !== null &&
                  overview.period_summary.behavior_breakdown.active_ratio !== undefined
                    ? `${(overview.period_summary.behavior_breakdown.active_ratio * 100).toFixed(1)}%`
                    : '\u2014'}
                </Text>
                <Text style={styles.metricSub}>
                  {overview.period_summary.behavior_breakdown.active_count} active windows
                </Text>
              </View>
              <View style={styles.metricItem}>
                <Text style={styles.metricLabel}>GPS Presence</Text>
                <Text style={styles.metricValue}>
                  {overview.period_summary.gps_presence_ratio !== null &&
                  overview.period_summary.gps_presence_ratio !== undefined
                    ? `${(overview.period_summary.gps_presence_ratio * 100).toFixed(1)}%`
                    : '\u2014'}
                </Text>
                <Text style={styles.metricSub}>Valid coordinates</Text>
              </View>
            </View>

            {/* Délais & Lacunes */}
            <View style={styles.subCard}>
              <Text style={styles.subCardTitle}>Transport & Reception Quality</Text>
              <Text style={styles.subCardText}>
                Median delay:{' '}
                {overview.period_summary.reception_delay.median_seconds !== null &&
                overview.period_summary.reception_delay.median_seconds !== undefined
                  ? `${overview.period_summary.reception_delay.median_seconds}s`
                  : 'N/A'}{' '}
                | P95:{' '}
                {overview.period_summary.reception_delay.p95_seconds !== null &&
                overview.period_summary.reception_delay.p95_seconds !== undefined
                  ? `${overview.period_summary.reception_delay.p95_seconds}s`
                  : 'N/A'}
              </Text>
              {overview.period_summary.reception_delay.negative_anomalies_count > 0 && (
                <Text style={styles.subCardWarning}>
                  ⚠️ {overview.period_summary.reception_delay.negative_anomalies_count} clock
                  timestamp anomalies detected (device time ahead of reception).
                </Text>
              )}
              <Text style={styles.subCardText}>
                {'Unobserved gaps (>5m): '}{overview.period_summary.unobserved_gaps.gap_count} (longest:{' '}
                {Math.round(
                  overview.period_summary.unobserved_gaps.longest_gap_seconds / 60,
                )}
                m)
              </Text>
            </View>

            {/* Avertissements & Limites */}
            <View style={styles.limitationsBox}>
              <Text style={styles.limitationsTitle}>Methodological Notes:</Text>
              {overview.period_summary.limitations.map((lim, idx) => (
                <Text key={idx} style={styles.limitationItem}>
                  • {lim}
                </Text>
              ))}
            </View>
          </View>

          {/* ── 3. Archives sans heure fiable (v3) ── */}
          <View style={styles.card}>
            <View style={styles.cardHeaderRow}>
              <Text style={styles.cardTitle}>Untimed Archives (v3)</Text>
              <Text style={styles.untimedCount}>
                {overview.untimed_summary.untimed_count} windows
              </Text>
            </View>
            <Text style={styles.untimedLabel}>{overview.untimed_summary.mandatory_label}</Text>
          </View>

          {/* ── 4. Aperçu & Export CSV ── */}
          <View style={styles.card}>
            <Text style={styles.cardTitle}>Dataset Preview & Export</Text>
            <View style={styles.datasetTabs}>
              <TouchableOpacity
                style={[
                  styles.datasetTab,
                  selectedDataset === 'farm_summary' && styles.datasetTabActive,
                ]}
                onPress={() => setSelectedDataset('farm_summary')}
              >
                <Text
                  style={[
                    styles.datasetTabText,
                    selectedDataset === 'farm_summary' && styles.datasetTabTextActive,
                  ]}
                >
                  Farm Summary
                </Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[
                  styles.datasetTab,
                  selectedDataset === 'animal_quality' && styles.datasetTabActive,
                ]}
                onPress={() => setSelectedDataset('animal_quality')}
              >
                <Text
                  style={[
                    styles.datasetTabText,
                    selectedDataset === 'animal_quality' && styles.datasetTabTextActive,
                  ]}
                >
                  Animal Quality (Daily)
                </Text>
              </TouchableOpacity>
            </View>

            {previewQuery.isLoading && (
              <ActivityIndicator style={{ marginVertical: 20 }} color={Colors.primary} />
            )}

            {preview && (
              <View style={styles.previewContainer}>
                <ReportPreviewTable preview={preview as unknown as ReportPreview} />
                <TouchableOpacity
                  style={[styles.exportBtn, exportDisabled && styles.exportBtnDisabled]}
                  onPress={handleExport}
                  disabled={exportDisabled}
                >
                  {exportMutation.isPending ? (
                    <ActivityIndicator color="#FFF" />
                  ) : (
                    <>
                      <Ionicons name="download-outline" size={20} color="#FFF" />
                      <Text style={styles.exportBtnText}>
                        Export {selectedDataset === 'farm_summary' ? 'Summary' : 'Quality'} CSV
                      </Text>
                    </>
                  )}
                </TouchableOpacity>
              </View>
            )}
          </View>
        </>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.bg.primary,
  },
  content: {
    padding: Spacing.md,
    gap: Spacing.md,
  },
  centerState: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: Spacing.xl,
    gap: Spacing.md,
  },
  stateTitle: {
    fontSize: Typography.xl,
    fontWeight: '700',
    color: Colors.text.primary,
    textAlign: 'center',
  },
  stateText: {
    fontSize: Typography.base,
    color: Colors.text.secondary,
    textAlign: 'center',
  },
  card: {
    backgroundColor: Colors.bg.card,
    borderRadius: Radius.md,
    padding: Spacing.md,
    borderWidth: 1,
    borderColor: Colors.border.default,
    gap: Spacing.sm,
  },
  cardHeaderRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  cardTitle: {
    fontSize: Typography.base,
    fontWeight: '700',
    color: Colors.text.primary,
  },
  subtext: {
    fontSize: Typography.xs,
    color: Colors.text.muted,
  },
  presetsRow: {
    flexDirection: 'row',
    gap: Spacing.xs,
    marginTop: Spacing.xs,
  },
  presetBtn: {
    flex: 1,
    paddingVertical: Spacing.xs,
    paddingHorizontal: Spacing.sm,
    borderRadius: Radius.sm,
    borderWidth: 1,
    borderColor: Colors.border.default,
    alignItems: 'center',
  },
  presetBtnActive: {
    backgroundColor: Colors.primary,
    borderColor: Colors.primary,
  },
  presetText: {
    fontSize: Typography.xs,
    color: Colors.text.secondary,
    fontWeight: '600',
  },
  presetTextActive: {
    color: '#FFF',
  },
  customDateRow: {
    flexDirection: 'row',
    gap: Spacing.sm,
    marginTop: Spacing.xs,
  },
  dateInputGroup: {
    flex: 1,
  },
  dateLabel: {
    fontSize: Typography.xs,
    color: Colors.text.muted,
    marginBottom: 2,
  },
  dateInput: {
    borderWidth: 1,
    borderColor: Colors.border.default,
    borderRadius: Radius.sm,
    paddingHorizontal: Spacing.sm,
    paddingVertical: 6,
    fontSize: Typography.sm,
    color: Colors.text.primary,
    backgroundColor: Colors.bg.input,
  },
  loadingBox: {
    padding: Spacing.xl,
    alignItems: 'center',
    gap: Spacing.sm,
  },
  loadingText: {
    fontSize: Typography.sm,
    color: Colors.text.muted,
  },
  errorBox: {
    padding: Spacing.md,
    backgroundColor: 'rgba(231, 76, 60, 0.15)',
    borderRadius: Radius.sm,
    borderWidth: 1,
    borderColor: Colors.severity.critical,
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.sm,
  },
  errorText: {
    fontSize: Typography.sm,
    color: Colors.severity.critical,
    flex: 1,
  },
  metricsGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: Spacing.sm,
    marginTop: Spacing.xs,
  },
  metricItem: {
    flex: 1,
    minWidth: '45%',
    backgroundColor: Colors.bg.elevated,
    padding: Spacing.sm,
    borderRadius: Radius.sm,
    borderWidth: 1,
    borderColor: Colors.border.default,
  },
  metricLabel: {
    fontSize: Typography.xs,
    color: Colors.text.muted,
    textTransform: 'uppercase',
  },
  metricValue: {
    fontSize: Typography.xl,
    fontWeight: '700',
    color: Colors.text.primary,
    marginVertical: 2,
  },
  metricSub: {
    fontSize: Typography.xs,
    color: Colors.text.secondary,
  },
  statusBadge: {
    paddingHorizontal: Spacing.sm,
    paddingVertical: 2,
    borderRadius: Radius.sm,
    backgroundColor: Colors.border.default,
  },
  statusBadgeGreen: {
    backgroundColor: Colors.primaryMuted,
  },
  statusBadgeYellow: {
    backgroundColor: 'rgba(243, 156, 18, 0.2)',
  },
  statusBadgeText: {
    fontSize: Typography.xs,
    fontWeight: '700',
    color: Colors.text.primary,
  },
  subCard: {
    backgroundColor: Colors.bg.elevated,
    padding: Spacing.sm,
    borderRadius: Radius.sm,
    gap: 4,
    marginTop: Spacing.xs,
  },
  subCardTitle: {
    fontSize: Typography.xs,
    fontWeight: '700',
    color: Colors.text.primary,
  },
  subCardText: {
    fontSize: Typography.xs,
    color: Colors.text.secondary,
  },
  subCardWarning: {
    fontSize: Typography.xs,
    color: Colors.severity.critical,
    fontWeight: '600',
  },
  limitationsBox: {
    backgroundColor: Colors.bg.elevated,
    padding: Spacing.sm,
    borderRadius: Radius.sm,
    borderLeftWidth: 3,
    borderLeftColor: Colors.primary,
    gap: 2,
    marginTop: Spacing.xs,
  },
  limitationsTitle: {
    fontSize: Typography.xs,
    fontWeight: '700',
    color: Colors.text.primary,
  },
  limitationItem: {
    fontSize: Typography.xs,
    color: Colors.text.secondary,
  },
  untimedCount: {
    fontSize: Typography.base,
    fontWeight: '700',
    color: Colors.text.primary,
  },
  untimedLabel: {
    fontSize: Typography.xs,
    color: Colors.text.muted,
    fontStyle: 'italic',
  },
  datasetTabs: {
    flexDirection: 'row',
    gap: Spacing.xs,
    marginBottom: Spacing.sm,
  },
  datasetTab: {
    flex: 1,
    paddingVertical: Spacing.xs,
    alignItems: 'center',
    borderRadius: Radius.sm,
    borderWidth: 1,
    borderColor: Colors.border.default,
  },
  datasetTabActive: {
    backgroundColor: Colors.primary,
    borderColor: Colors.primary,
  },
  datasetTabText: {
    fontSize: Typography.xs,
    color: Colors.text.secondary,
    fontWeight: '600',
  },
  datasetTabTextActive: {
    color: '#FFF',
  },
  previewContainer: {
    gap: Spacing.md,
  },
  exportBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: Spacing.xs,
    backgroundColor: Colors.primary,
    paddingVertical: Spacing.sm,
    borderRadius: Radius.sm,
  },
  exportBtnDisabled: {
    opacity: 0.6,
  },
  exportBtnText: {
    fontSize: Typography.sm,
    color: '#FFF',
    fontWeight: '600',
  },
});
