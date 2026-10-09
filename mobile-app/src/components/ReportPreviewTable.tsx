/**
 * Preview table of a report or export. Columns are sized from their content (header and
 * longest value, between MIN and MAX), headers wrap to two lines, rows grow with their
 * content, and a table narrower than the screen is stretched to its full width. Tapping a
 * cell shows its full value.
 */
import React, { useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, useWindowDimensions, View } from 'react-native';
import { Colors, Typography } from '../constants/config';
import { ReportPreview } from '../types';
import AppModal from './AppModal';

export const MIN_COLUMN_WIDTH = 72;
export const MAX_COLUMN_WIDTH = 220;
export const INDEX_WIDTH = 36;
// Average character widths at Typography.xs (bold header, regular value) and cell padding.
const HEADER_CHAR = 7;
const VALUE_CHAR = 6.5;
const CELL_PADDING = 20;

/** Width of each column from its header and its longest value, clamped to MIN..MAX. */
export function estimateColumnWidths(columns: string[], rows: string[][]): number[] {
  return columns.map((column, index) => {
    const longest = rows.reduce((max, row) => Math.max(max, String(row[index] ?? '').length), 0);
    const needed = Math.ceil(Math.max(column.length * HEADER_CHAR, longest * VALUE_CHAR)) + CELL_PADDING;
    return Math.min(MAX_COLUMN_WIDTH, Math.max(MIN_COLUMN_WIDTH, needed));
  });
}

/** Spreads the free space over the columns (in proportion) when the table is narrower than the screen. */
export function fitToWidth(widths: number[], available: number): number[] {
  const total = INDEX_WIDTH + widths.reduce((sum, value) => sum + value, 0);
  if (available <= total || widths.length === 0) return widths;
  const content = total - INDEX_WIDTH;
  return widths.map((value) => Math.floor(value + (available - total) * (value / content)));
}

export default function ReportPreviewTable({ preview }: { preview: ReportPreview }) {
  const [cell, setCell] = useState<{ column: string; value: string } | null>(null);
  const [available, setAvailable] = useState(0);
  const { height } = useWindowDimensions();
  const widths = fitToWidth(estimateColumnWidths(preview.columns, preview.rows), available);
  const width = INDEX_WIDTH + widths.reduce((sum, value) => sum + value, 0);
  const maxHeight = Math.round(Math.min(480, Math.max(240, height * 0.5)));
  return (
    <>
      <View style={styles.table} onLayout={(event) => setAvailable(Math.floor(event.nativeEvent.layout.width) - 2)}>
        <ScrollView horizontal showsHorizontalScrollIndicator>
          <ScrollView nestedScrollEnabled stickyHeaderIndices={[0]} style={{ width, maxHeight }}>
            <View style={[styles.row, styles.header]}>
              <Text style={[styles.heading, styles.index]}>#</Text>
              {preview.columns.map((column, index) => (
                <Text key={column} numberOfLines={2} style={[styles.heading, { width: widths[index] }]}>{column}</Text>
              ))}
            </View>
            {preview.rows.map((row, rowIndex) => (
              <View key={rowIndex} style={[styles.row, rowIndex % 2 === 0 && styles.alternate]}>
                <Text style={[styles.value, styles.index]}>{rowIndex + 1}</Text>
                {row.map((value, columnIndex) => (
                  <Pressable key={preview.columns[columnIndex]} accessibilityRole="button"
                    accessibilityLabel={`Row ${rowIndex + 1}, ${preview.columns[columnIndex]}: ${value || 'Empty'}`}
                    onPress={() => setCell({ column: preview.columns[columnIndex], value })}
                    style={[styles.cell, { width: widths[columnIndex] }]}>
                    <Text numberOfLines={2} style={styles.value}>{value || '\u2014'}</Text>
                  </Pressable>
                ))}
              </View>
            ))}
          </ScrollView>
        </ScrollView>
      </View>
      <AppModal visible={cell !== null} title={cell?.column ?? ''} onClose={() => setCell(null)}
        closeLabel="Close cell value" closeOnBackdrop>
        <Text selectable style={styles.fullValue}>{cell?.value || 'Empty value'}</Text>
      </AppModal>
    </>
  );
}

const styles = StyleSheet.create({
  table: { borderWidth: 1, borderColor: Colors.border.default, borderRadius: 6, overflow: 'hidden', marginTop: 12 },
  row: { flexDirection: 'row', minHeight: 40, alignItems: 'stretch', borderBottomWidth: 1, borderBottomColor: Colors.border.default },
  header: { backgroundColor: Colors.bg.elevated, minHeight: 44 },
  heading: {
    color: Colors.text.primary, fontSize: Typography.xs, fontWeight: '700', lineHeight: 15,
    paddingHorizontal: 10, paddingVertical: 7, alignSelf: 'center',
  },
  index: { width: INDEX_WIDTH, textAlign: 'center', paddingHorizontal: 4, alignSelf: 'center' },
  alternate: { backgroundColor: Colors.bg.card },
  cell: { justifyContent: 'center', paddingHorizontal: 10, paddingVertical: 6, borderLeftWidth: 1, borderLeftColor: Colors.border.default },
  value: { color: Colors.text.secondary, fontSize: Typography.xs, lineHeight: 16 },
  fullValue: { color: Colors.text.primary, fontSize: Typography.sm, lineHeight: 21 },
});
