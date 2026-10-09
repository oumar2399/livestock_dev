/**
 * AnimalFormScreen - add / edit an animal
 * Add mode : navigation without params
 * Edit mode: navigation with { animalId: number }
 * Save is at the top right and at the bottom; fields stay above the keyboard.
 */
import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TextInput,
  TouchableOpacity,
  ActivityIndicator,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useNavigation, useRoute } from '@react-navigation/native';
import { useQueryClient } from '@tanstack/react-query';

import { Colors, Radius, Spacing, Typography } from '../constants/config';
import apiClient from '../api/client';
import { useFarmStore } from '../store/farmStore';
import { useFarmDevices } from '../hooks/useDevices';
import { assignableDevices, deviceOption } from '../utils/deviceStatus';
import { showApiError } from '../utils/apiErrors';
import { showDialog } from '../components/dialog';
import { HeaderAction } from '../components/AppModal';
import KeyboardAwareForm from '../components/KeyboardAwareForm';
import SearchablePicker from '../components/SearchablePicker';

// ─── Types ────────────────────────────────────────────────────────────────────

interface FormData {
  name: string;
  official_id: string;
  breed: string;
  sex: 'M' | 'F' | '';
  birth_date: string;
  weight: string;
  status: 'active' | 'sick' | 'sold' | 'deceased';
  assigned_device: string;
  species: string;
  farm_id: number;
}

const DEFAULT_FORM: FormData = {
  name: '',
  official_id: '',
  breed: '',
  sex: '',
  birth_date: '',
  weight: '',
  status: 'active',
  assigned_device: '',
  species: 'bovine',
  farm_id: 0,
};

// ─── UI components ────────────────────────────────────────────────────────────

function FieldLabel({ label, required }: { label: string; required?: boolean }) {
  return (
    <Text style={styles.fieldLabel}>
      {label}
      {required && <Text style={{ color: Colors.severity.critical }}> *</Text>}
    </Text>
  );
}

function Field({
  label, value, onChangeText, placeholder, required, keyboardType, autoCapitalize,
}: {
  label: string;
  value: string;
  onChangeText: (v: string) => void;
  placeholder?: string;
  required?: boolean;
  keyboardType?: 'default' | 'numeric' | 'decimal-pad';
  autoCapitalize?: 'none' | 'characters' | 'words' | 'sentences';
}) {
  return (
    <View style={styles.fieldContainer}>
      <FieldLabel label={label} required={required} />
      <TextInput
        style={styles.input}
        value={value}
        onChangeText={onChangeText}
        placeholder={placeholder ?? label}
        placeholderTextColor={Colors.text.muted}
        keyboardType={keyboardType ?? 'default'}
        autoCapitalize={autoCapitalize ?? 'sentences'}
      />
    </View>
  );
}

function SegmentedField<T extends string>({
  label, value, options, onSelect, required,
}: {
  label: string;
  value: T;
  options: { label: string; value: T; color?: string }[];
  onSelect: (v: T) => void;
  required?: boolean;
}) {
  return (
    <View style={styles.fieldContainer}>
      <FieldLabel label={label} required={required} />
      <View style={styles.segmentRow}>
        {options.map((opt) => {
          const active = value === opt.value;
          const color = opt.color ?? Colors.primary;
          return (
            <TouchableOpacity
              key={opt.value}
              style={[
                styles.segmentBtn,
                active && { backgroundColor: color + '20', borderColor: color },
              ]}
              onPress={() => onSelect(opt.value)}
            >
              <Text style={[styles.segmentText, active && { color, fontWeight: '700' }]}>
                {opt.label}
              </Text>
            </TouchableOpacity>
          );
        })}
      </View>
    </View>
  );
}

// ─── Screen ───────────────────────────────────────────────────────────────────

export default function AnimalFormScreen() {
  const insets      = useSafeAreaInsets();
  const navigation  = useNavigation<any>();
  const route       = useRoute<any>();
  const queryClient = useQueryClient();
  const currentFarmId = useFarmStore((state) => state.currentFarmId);

  const animalId: number | undefined = route.params?.animalId;
  const isEdit = !!animalId;
  const { data: farmDevices } = useFarmDevices();
  const deviceChoices = assignableDevices(farmDevices, animalId);

  const [form, setForm]         = useState<FormData>(DEFAULT_FORM);
  const [loading, setLoading]   = useState(false);
  const [fetching, setFetching] = useState(isEdit);
  const [errors, setErrors]     = useState<Partial<Record<keyof FormData, string>>>({});

  useEffect(() => {
    if (!isEdit && currentFarmId) {
      setForm((previous) => ({ ...previous, farm_id: currentFarmId }));
    }
  }, [currentFarmId, isEdit]);

  // Load the existing data in edit mode
  useEffect(() => {
    if (!isEdit) return;
    setFetching(true);
    apiClient.get(`/animals/${animalId}`)
      .then(({ data }) => {
        setForm({
          name:            data.name ?? '',
          official_id:     data.official_id ?? '',
          breed:           data.breed ?? '',
          sex:             data.sex ?? '',
          birth_date:      data.birth_date ?? '',
          weight:          data.weight ? String(data.weight) : '',
          status:          data.status ?? 'active',
          assigned_device: data.assigned_device ?? '',
          species:         data.species ?? 'bovine',
          farm_id:         data.farm_id,
        });
      })
      .catch((error) => showApiError(error, 'Could not load', 'Unable to load the animal'))
      .finally(() => setFetching(false));
  }, [animalId, isEdit]);

  const set = (key: keyof FormData) => (value: string) =>
    setForm(prev => ({ ...prev, [key]: value }));

  const validate = (): boolean => {
    const errs: Partial<Record<keyof FormData, string>> = {};
    if (!form.name.trim()) errs.name = 'The name is required';
    if (!form.farm_id) errs.farm_id = 'No farm selected';
    if (form.weight && isNaN(parseFloat(form.weight)))
      errs.weight = 'Invalid weight';
    if (form.birth_date && !/^\d{4}-\d{2}-\d{2}$/.test(form.birth_date))
      errs.birth_date = 'Format : YYYY-MM-DD';
    setErrors(errs);
    return Object.keys(errs).length === 0;
  };

  const handleSubmit = async () => {
    if (!validate()) return;
    setLoading(true);
    try {
      const payload: any = {
        name:            form.name.trim(),
        official_id:     form.official_id.trim() || null,
        breed:           form.breed.trim() || null,
        sex:             form.sex || null,
        birth_date:      form.birth_date || null,
        weight:          form.weight ? parseFloat(form.weight) : null,
        status:          form.status,
        assigned_device: form.assigned_device.trim() || null,
        species:         form.species,
        farm_id:         form.farm_id,
      };

      if (isEdit) await apiClient.put(`/animals/${animalId}`, payload);
      else        await apiClient.post('/animals/', payload);

      queryClient.invalidateQueries({ queryKey: ['animals'] });
      queryClient.invalidateQueries({ queryKey: ['animal', animalId] });

      showDialog(
        'Success',
        isEdit ? 'Animal modified successfully' : 'Animal added successfully',
        [{ text: 'OK', onPress: () => navigation.goBack() }]
      );
    } catch (error) {
      showApiError(error, 'Could not save', 'Unable to save the animal');
    } finally {
      setLoading(false);
    }
  };
  const handleDelete = () => {
    showDialog(
      'Delete Animal',
      `Delete ${form.name}? This action will also delete all its telemetry and alert data.`,
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Delete',
          style: 'destructive',
          onPress: async () => {
            try {
              await apiClient.delete(`/animals/${animalId}`);
              queryClient.invalidateQueries({ queryKey: ['animals'] });
              // Go back to the existing list: navigate() would push a new one and keep this
              // deleted animal's screen mounted (and polling) underneath.
              navigation.popTo('AnimalsList');
            } catch (error) {
              showApiError(error, 'Could not delete', 'Failed to delete the animal');
            }
          },
        },
      ]
    );
  };

  if (fetching) {
    return (
      <View style={[styles.screen, styles.center]}>
        <ActivityIndicator color={Colors.primary} size="large" />
      </View>
    );
  }

  return (
    <View style={styles.screen}>
      {/* ── Header: back, centered title, Save ───────────────────────── */}
      <View style={[styles.header, { paddingTop: insets.top + Spacing.sm }]}>
        <TouchableOpacity onPress={() => navigation.goBack()} hitSlop={12} style={styles.headerBtn}>
          <Ionicons name="arrow-back" size={24} color={Colors.text.primary} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>
          {isEdit ? 'Modify Animal' : 'New Animal'}
        </Text>
        <View style={styles.headerAction}>
          <HeaderAction action={{ label: isEdit ? 'Save' : 'Add', onPress: handleSubmit, busy: loading }} />
        </View>
      </View>

      <KeyboardAwareForm
        style={styles.scroll}
        contentContainerStyle={{ paddingBottom: insets.bottom + 40 }}
      >
        {/* ── Identity ─────────────────────────────────────────────── */}
        <Text style={styles.sectionTitle}>Identity</Text>

        <Field
          label="Name" value={form.name} onChangeText={set('name')}
          required placeholder="Ex: 花子"
        />
        {errors.name && <Text style={styles.errorText}>{errors.name}</Text>}

        <Field
          label="Ear Tag Number" value={form.official_id}
          onChangeText={set('official_id')} placeholder="Ex: JP-WAG-001"
          autoCapitalize="characters"
        />

        <Field
          label="Breed" value={form.breed} onChangeText={set('breed')}
          placeholder="Ex: Wagyu, Holstein"
        />
        <SegmentedField
          label="Sex"
          value={form.sex as any}
          options={[
            { label: 'Female', value: 'F' as any },
            { label: 'Male',   value: 'M' as any },
          ]}
          onSelect={(v) => setForm(p => ({ ...p, sex: v }))}
        />
        {/* ── Physical information ──────────────────────────────────────── */}
        <Text style={styles.sectionTitle}>Physical Information</Text>

        <Field
          label="Date of Birth" value={form.birth_date}
          onChangeText={set('birth_date')} placeholder="YYYY-MM-DD"
          keyboardType="numeric"
        />
        {errors.birth_date && <Text style={styles.errorText}>{errors.birth_date}</Text>}

        <Field
          label="Weight (kg)" value={form.weight} onChangeText={set('weight')}
          placeholder="Ex: 480" keyboardType="decimal-pad"
        />
        {errors.weight && <Text style={styles.errorText}>{errors.weight}</Text>}

        {/* ── Status ───────────────────────────────────────────────── */}
        <Text style={styles.sectionTitle}>Health Status</Text>

        <SegmentedField
          label="Health Status"
          value={form.status}
          options={[
            { label: 'Active',   value: 'active',   color: Colors.animalStatus.active },
            { label: 'Sick',  value: 'sick',     color: Colors.animalStatus.sick },
            { label: 'Sold',   value: 'sold',     color: Colors.animalStatus.sold },
            { label: 'Deceased', value: 'deceased', color: Colors.animalStatus.deceased },
          ]}
          onSelect={(v) => setForm(p => ({ ...p, status: v }))}
        />

        {/* ── Device M5Stack ───────────────────────────────────────── */}
        <Text style={styles.sectionTitle}>M5Stack Sensor</Text>

        <View style={styles.fieldContainer}>
          <FieldLabel label="Assigned Device" />
          {/* Only the farm's collars not assigned to another animal */}
          <SearchablePicker
            label="Assigned Device"
            options={deviceChoices.map(deviceOption)}
            value={form.assigned_device || null}
            onChange={(value) => setForm(p => ({ ...p, assigned_device: value === null ? '' : String(value) }))}
            clearLabel="No device"
            searchPlaceholder="Search by collar ID"
            emptyText="No collar matches"
          />
          <Text style={styles.fieldHint}>
            {deviceChoices.length === 0
              ? 'No free collar in this farm. Add one in Devices.'
              : 'Collars already on another animal are not listed.'}
          </Text>
        </View>

        {/* ── Save button (full width, bottom; also at the top right) ───────────── */}
        <TouchableOpacity
          style={[styles.submitBtn, loading && { opacity: 0.6 }]}
          onPress={handleSubmit}
          disabled={loading}
        >
          {loading ? (
            <ActivityIndicator color="#fff" size="small" />
          ) : (
            <>
              <Ionicons name="checkmark-circle-outline" size={20} color="#fff" />
              <Text style={styles.submitBtnText}>
                {isEdit ? 'Save Changes' : 'Add Animal'}
              </Text>
            </>
          )}
        </TouchableOpacity>

        {/* ── Delete button (edit mode, after Save) ───── */}
        {isEdit && (
          <TouchableOpacity style={styles.deleteBtn} onPress={handleDelete}>
            <Ionicons name="trash-outline" size={18} color={Colors.severity.critical} />
            <Text style={styles.deleteBtnText}>Delete this animal</Text>
          </TouchableOpacity>
        )}

      </KeyboardAwareForm>
    </View>
  );
}

// ─── Styles ──────────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: Colors.bg.primary },
  center: { alignItems: 'center', justifyContent: 'center' },
  scroll: { flex: 1, paddingHorizontal: Spacing.base },

  // Header
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: Spacing.sm,
    paddingBottom: Spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: Colors.border.default,
    backgroundColor: Colors.bg.primary,
  },
  headerAction: { minWidth: 40, alignItems: 'flex-end' },
  headerBtn: {
    width: 44, height: 44,
    alignItems: 'center', justifyContent: 'center',
  },
  headerTitle: {
    flex: 1, textAlign: 'center',
    fontSize: Typography.md, fontWeight: '700', color: Colors.text.primary,
  },

  // Sections
  sectionTitle: {
    fontSize: Typography.xs, fontWeight: '700', color: Colors.text.muted,
    textTransform: 'uppercase', letterSpacing: 0.8,
    marginTop: Spacing.xl, marginBottom: Spacing.sm,
  },

  // Champs
  fieldContainer: { marginBottom: Spacing.md },
  fieldLabel: {
    fontSize: Typography.sm, color: Colors.text.secondary,
    marginBottom: Spacing.xs, fontWeight: '500',
  },
  input: {
    backgroundColor: Colors.bg.input,
    borderWidth: 1, borderColor: Colors.border.default,
    borderRadius: Radius.md,
    paddingHorizontal: Spacing.md, paddingVertical: Spacing.sm + 2,
    color: Colors.text.primary, fontSize: Typography.base,
  },
  errorText: {
    fontSize: Typography.xs, color: Colors.severity.critical,
    marginTop: -Spacing.sm, marginBottom: Spacing.sm,
  },
  fieldHint: { fontSize: Typography.xs, color: Colors.text.muted, marginTop: Spacing.xs },

  // Segments
  segmentRow: { flexDirection: 'row', gap: Spacing.sm, flexWrap: 'wrap' },
  segmentBtn: {
    paddingHorizontal: Spacing.md, paddingVertical: Spacing.sm,
    borderRadius: Radius.md, borderWidth: 1,
    borderColor: Colors.border.default, backgroundColor: Colors.bg.elevated,
  },
  segmentText: { fontSize: Typography.sm, color: Colors.text.secondary },

  // Device
  deviceRow: { flexDirection: 'row', alignItems: 'center', gap: Spacing.sm },
  clearDeviceBtn: { padding: Spacing.xs },

  // ✅ Save button: green, full width, at the bottom of the form (also at the top right)
  submitBtn: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    gap: Spacing.sm, backgroundColor: Colors.primary,
    padding: Spacing.md + 2, borderRadius: Radius.md,
    marginTop: Spacing['2xl'],
  },
  submitBtnText: { color: '#fff', fontWeight: '700', fontSize: Typography.base },

  // 🗑️ Delete button: discreet red, after the Save button
  deleteBtn: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    gap: Spacing.sm,
    marginTop: Spacing.base, marginBottom: Spacing.base,
    padding: Spacing.md, borderRadius: Radius.md,
    borderWidth: 1, borderColor: Colors.severity.critical + '50',
    backgroundColor: Colors.severity.critical + '10',
  },
  deleteBtnText: {
    color: Colors.severity.critical, fontSize: Typography.sm, fontWeight: '600',
  },
});
