import React, { useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { Colors, Typography } from '../constants/config';
import { ReportPreview } from '../types';
import AppModal from './AppModal';

export default function ReportPreviewTable({ preview }: { preview: ReportPreview }) {
  const [cell, setCell] = useState<{ column: string; value: string } | null>(null);
  const widths = preview.columns.map((column) => /time|date|name|message|notes|metadata/.test(column) ? 200 : 156);
  const width = 44 + widths.reduce((sum, value) => sum + value, 0);
  return (
    <>
      <View style={styles.table}>
        <ScrollView horizontal showsHorizontalScrollIndicator>
          <ScrollView nestedScrollEnabled stickyHeaderIndices={[0]} style={{ width, maxHeight: 340 }}>
            <View style={[styles.row, styles.header]}>
              <Text style={[styles.heading, styles.index]}>#</Text>
              {preview.columns.map((column, index) => (
                <Text key={column} style={[styles.heading, { width: widths[index] }]}>{column}</Text>
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
  row: { flexDirection: 'row', height: 56, alignItems: 'center', borderBottomWidth: 1, borderBottomColor: Colors.border.default },
  header: { backgroundColor: Colors.bg.elevated },
  heading: { color: Colors.text.primary, fontSize: Typography.xs, fontWeight: '700', paddingHorizontal: 10 },
  index: { width: 44, textAlign: 'center', paddingHorizontal: 4 },
  alternate: { backgroundColor: Colors.bg.card },
  cell: { height: 56, justifyContent: 'center', paddingHorizontal: 10, borderLeftWidth: 1, borderLeftColor: Colors.border.default },
  value: { color: Colors.text.secondary, fontSize: Typography.xs, lineHeight: 17 },
  fullValue: { color: Colors.text.primary, fontSize: Typography.sm, lineHeight: 21 },
});
