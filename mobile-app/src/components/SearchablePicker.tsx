/**
 * Searchable single-choice picker: a field showing the current choice that opens an
 * AppModal with a search box and the list of options. Used for animals and collars.
 */
import React, { useMemo, useState } from 'react';
import { FlatList, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { Colors, Radius, Spacing, Typography } from '../constants/config';
import { AnimalStatus } from '../types';
import { animalStatusLabel } from '../utils/helpers';
import AppModal from './AppModal';

export type PickerValue = string | number;

export interface PickerOption {
  value: PickerValue;
  label: string;
  detail?: string;
  /** Extra words that match the search (ear tag, ID...). */
  keywords?: string[];
}

/** Lower case, without accents or a leading "#", so "#12", "hanako" and "Hánako" all match. */
export function normalizeSearch(text: string): string {
  return text.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().trim().replace(/^#/, '');
}

export function filterOptions(options: PickerOption[], query: string): PickerOption[] {
  const needle = normalizeSearch(query);
  if (!needle) return options;
  return options.filter((option) =>
    [option.label, option.detail ?? '', String(option.value), ...(option.keywords ?? [])]
      .some((text) => normalizeSearch(text).includes(needle)));
}

export function animalOption(animal: {
  id: number; name: string; official_id?: string | null; status?: AnimalStatus;
}): PickerOption {
  const parts = [
    animal.official_id ? `Ear tag ${animal.official_id}` : null,
    `ID ${animal.id}`,
    animal.status ? animalStatusLabel(animal.status) : null,
  ].filter(Boolean);
  return {
    value: animal.id,
    label: animal.name,
    detail: parts.join(' · '),
    keywords: [animal.official_id ?? '', String(animal.id)],
  };
}

interface SearchablePickerProps {
  /** Field label, also the title of the picker. */
  label: string;
  options: PickerOption[];
  value: PickerValue | null;
  onChange: (value: PickerValue | null) => void;
  placeholder?: string;
  searchPlaceholder?: string;
  emptyText?: string;
  /** Adds a first row that clears the choice (e.g. "No collar"). */
  clearLabel?: string;
  disabled?: boolean;
}

export default function SearchablePicker({
  label, options, value, onChange, placeholder = 'Select…', searchPlaceholder = 'Search',
  emptyText = 'No match', clearLabel, disabled = false,
}: SearchablePickerProps) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const selected = options.find((option) => option.value === value) ?? null;
  const results = useMemo(() => filterOptions(options, query), [options, query]);

  const close = () => {
    setOpen(false);
    setQuery('');
  };
  const choose = (next: PickerValue | null) => {
    onChange(next);
    close();
  };

  return (
    <>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={`${label}: ${selected ? selected.label : placeholder}`}
        accessibilityState={{ disabled }}
        disabled={disabled}
        onPress={() => setOpen(true)}
        style={[styles.field, disabled && styles.disabled]}
      >
        <View style={styles.fieldText}>
          <Text style={selected ? styles.value : styles.placeholder} numberOfLines={1}>
            {selected ? selected.label : (value === null && clearLabel) ? clearLabel : placeholder}
          </Text>
          {selected?.detail ? <Text style={styles.detail} numberOfLines={1}>{selected.detail}</Text> : null}
        </View>
        <Ionicons name="search-outline" size={18} color={Colors.text.muted} />
      </Pressable>

      <AppModal visible={open} title={label} onClose={close} scroll={false}>
        <View style={styles.searchBar}>
          <Ionicons name="search-outline" size={18} color={Colors.text.muted} />
          <TextInput
            accessibilityLabel={searchPlaceholder}
            style={styles.searchInput}
            placeholder={searchPlaceholder}
            placeholderTextColor={Colors.text.muted}
            value={query}
            onChangeText={setQuery}
            autoCorrect={false}
            autoCapitalize="none"
            returnKeyType="search"
          />
          {query ? (
            <Pressable accessibilityRole="button" accessibilityLabel="Clear search" hitSlop={8} onPress={() => setQuery('')}>
              <Ionicons name="close-circle" size={18} color={Colors.text.muted} />
            </Pressable>
          ) : null}
        </View>
        <FlatList
          style={styles.list}
          data={results}
          keyExtractor={(option) => String(option.value)}
          keyboardShouldPersistTaps="handled"
          ListHeaderComponent={clearLabel && !query ? (
            <OptionRow label={clearLabel} selected={value === null} onPress={() => choose(null)} />
          ) : null}
          ListEmptyComponent={<Text style={styles.empty}>{emptyText}</Text>}
          renderItem={({ item }) => (
            <OptionRow label={item.label} detail={item.detail} selected={item.value === value}
              onPress={() => choose(item.value)} />
          )}
        />
      </AppModal>
    </>
  );
}

function OptionRow({ label, detail, selected, onPress }: {
  label: string; detail?: string; selected: boolean; onPress: () => void;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityState={{ selected }}
      onPress={onPress}
      style={({ pressed }) => [styles.row, selected && styles.rowSelected, pressed && styles.pressed]}
    >
      <View style={styles.fieldText}>
        <Text style={[styles.rowLabel, selected && styles.rowLabelSelected]} numberOfLines={1}>{label}</Text>
        {detail ? <Text style={styles.detail} numberOfLines={1}>{detail}</Text> : null}
      </View>
      {selected && <Ionicons name="checkmark" size={18} color={Colors.primary} />}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  field: {
    minHeight: 48,
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.sm,
    paddingHorizontal: Spacing.md,
    paddingVertical: Spacing.sm,
    backgroundColor: Colors.bg.input,
    borderRadius: Radius.md,
    borderWidth: 1,
    borderColor: Colors.border.default,
  },
  disabled: { opacity: 0.5 },
  fieldText: { flex: 1 },
  value: { fontSize: Typography.base, color: Colors.text.primary, fontWeight: '600' },
  placeholder: { fontSize: Typography.base, color: Colors.text.muted },
  detail: { fontSize: Typography.xs, color: Colors.text.secondary, marginTop: 2 },
  searchBar: {
    height: 44,
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.sm,
    paddingHorizontal: Spacing.md,
    backgroundColor: Colors.bg.input,
    borderRadius: Radius.md,
    borderWidth: 1,
    borderColor: Colors.border.default,
    marginBottom: Spacing.sm,
  },
  searchInput: { flex: 1, color: Colors.text.primary, fontSize: Typography.base },
  list: { maxHeight: 360, flexGrow: 0, flexShrink: 1 },
  row: {
    minHeight: 52,
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.sm,
    paddingHorizontal: Spacing.sm,
    paddingVertical: Spacing.sm,
    borderBottomWidth: 1,
    borderBottomColor: Colors.border.default,
  },
  rowSelected: { backgroundColor: Colors.primaryMuted },
  rowLabel: { fontSize: Typography.base, color: Colors.text.primary },
  rowLabelSelected: { color: Colors.primary, fontWeight: '700' },
  pressed: { opacity: 0.75 },
  empty: { padding: Spacing.base, textAlign: 'center', color: Colors.text.muted, fontSize: Typography.sm },
});
