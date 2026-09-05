import React, { useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Colors, Typography } from '../../constants/config';
import {
  PreviewEmptyState, PreviewIconButton, PreviewScreen, PreviewSheet, PreviewTabs,
} from '../../components/ServicePreview';

const SAMPLE_CAMERAS = [
  { id: 'barn', name: 'Barn', area: 'Shelter', icon: 'home-outline' },
  { id: 'pasture', name: 'Pasture', area: 'Grazing area', icon: 'leaf-outline' },
  { id: 'entrance', name: 'Entrance', area: 'Access gate', icon: 'log-in-outline' },
] as const;
type Camera = typeof SAMPLE_CAMERAS[number];
const TABS = [{ value: 'cameras', label: 'Cameras' }, { value: 'recordings', label: 'Recordings' }] as const;

function CameraViewport({ camera }: { camera: Camera }) {
  return (
    <View style={styles.viewport}>
      <View style={styles.viewportTop}>
        <Text style={styles.viewportName}>{camera.name}</Text>
        <Text style={styles.sampleLabel}>Sample camera</Text>
      </View>
      <View style={styles.noSignal}>
        <Ionicons name="videocam-off-outline" size={36} color={Colors.text.muted} />
        <Text style={styles.noSignalTitle}>No video source</Text>
        <Text style={styles.secondary}>Not connected</Text>
      </View>
    </View>
  );
}

function VideoWorkspace() {
  const insets = useSafeAreaInsets();
  const [tab, setTab] = useState<'cameras' | 'recordings'>('cameras');
  const [camera, setCamera] = useState<Camera>(SAMPLE_CAMERAS[0]);
  const [expanded, setExpanded] = useState(false);
  return (
    <View style={styles.root}>
      <PreviewTabs options={TABS} value={tab} onChange={setTab} />
      <ScrollView contentContainerStyle={[styles.content, { paddingBottom: insets.bottom + 24 }]}>
        {tab === 'cameras' ? (
          <>
            <CameraViewport camera={camera} />
            <View style={styles.playbackBar}>
              <Text style={[styles.secondary, styles.flex]}>Stream unavailable</Text>
              <PreviewIconButton icon="volume-mute-outline" label="Audio unavailable" disabled />
              <PreviewIconButton icon="camera-outline" label="Snapshot unavailable" disabled />
              <PreviewIconButton icon="expand-outline" label="Expand camera" onPress={() => setExpanded(true)} />
            </View>
            <View style={styles.sectionHeading}>
              <Text style={styles.sectionTitle}>Camera preview</Text>
              <Text style={styles.secondary}>3 samples</Text>
            </View>
            {SAMPLE_CAMERAS.map((item) => (
              <Pressable key={item.id} accessibilityRole="button" accessibilityLabel={`Select ${item.name} camera`}
                accessibilityState={{ selected: item.id === camera.id }} onPress={() => setCamera(item)}
                style={[styles.cameraRow, item.id === camera.id && styles.selectedRow]}>
                <View style={styles.cameraIcon}><Ionicons name={item.icon} size={24} color={Colors.text.secondary} /></View>
                <View style={styles.flex}>
                  <Text style={styles.cameraName}>{item.name}</Text>
                  <Text style={styles.secondary}>{item.area} / Sample</Text>
                </View>
                <Ionicons name={item.id === camera.id ? 'checkmark-circle' : 'ellipse-outline'} size={22}
                  color={item.id === camera.id ? Colors.primaryLight : Colors.text.muted} />
              </Pressable>
            ))}
          </>
        ) : (
          <PreviewEmptyState icon="film-outline" title="No recordings" detail="Recording service not connected." />
        )}
      </ScrollView>
      {expanded && <PreviewSheet title={camera.name} onClose={() => setExpanded(false)}>
        <CameraViewport camera={camera} />
        <Text style={styles.secondary}>Sample camera / No video source</Text>
      </PreviewSheet>}
    </View>
  );
}

export default function VideoMonitoring() {
  return <PreviewScreen title="Video Monitoring"><VideoWorkspace /></PreviewScreen>;
}

const styles = StyleSheet.create({
  root: { flex: 1 },
  flex: { flex: 1 },
  content: { flexGrow: 1, paddingHorizontal: 16, paddingTop: 16, width: '100%', maxWidth: 840, alignSelf: 'center' },
  viewport: { aspectRatio: 16 / 9, minHeight: 190, backgroundColor: '#090F14', borderRadius: 8, overflow: 'hidden' },
  viewportTop: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: 8, padding: 12 },
  viewportName: { color: Colors.text.primary, fontSize: Typography.sm, fontWeight: '600', flexGrow: 1 },
  sampleLabel: { color: Colors.severity.warning, fontSize: Typography.xs },
  noSignal: { flex: 1, justifyContent: 'center', alignItems: 'center', gap: 8, paddingHorizontal: 12, paddingBottom: 16 },
  noSignalTitle: { fontSize: Typography.base, fontWeight: '600', color: Colors.text.secondary },
  secondary: { fontSize: Typography.sm, color: Colors.text.secondary, lineHeight: 20 },
  playbackBar: { flexDirection: 'row', alignItems: 'center', gap: 4, paddingVertical: 8,
    borderBottomWidth: 1, borderBottomColor: Colors.border.default },
  sectionHeading: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between', gap: 8, paddingVertical: 20 },
  sectionTitle: { fontSize: Typography.base, fontWeight: '600', color: Colors.text.primary },
  cameraRow: { flexDirection: 'row', alignItems: 'center', gap: 12, padding: 12, marginBottom: 8,
    borderRadius: 8, backgroundColor: Colors.bg.card, borderWidth: 1, borderColor: Colors.border.default },
  selectedRow: { borderColor: Colors.primary, backgroundColor: Colors.primaryMuted },
  cameraIcon: { width: 48, height: 48, alignItems: 'center', justifyContent: 'center' },
  cameraName: { fontSize: Typography.base, color: Colors.text.primary, fontWeight: '600', marginBottom: 4 },
});
