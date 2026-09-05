import React, { useState } from 'react';
import {
  KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Colors, Typography } from '../../constants/config';
import { PreviewIconButton, PreviewScreen } from '../../components/ServicePreview';

const QUESTIONS = [
  { icon: 'pulse-outline', title: 'Herd activity', question: 'Which animals have an unusual activity pattern?' },
  { icon: 'notifications-outline', title: 'Recent alerts', question: 'Can you summarize the recent alerts for this farm?' },
  { icon: 'leaf-outline', title: 'Daily care', question: 'What should I include in a daily herd check?' },
] as const;
const MAX_DRAFT_LENGTH = 2000;

function AssistantWorkspace() {
  const insets = useSafeAreaInsets();
  const [draft, setDraft] = useState('');
  return (
    <KeyboardAvoidingView style={styles.root} behavior={Platform.OS === 'ios' ? 'padding' : 'height'}>
      <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={styles.content}>
        <View style={styles.conversationHeader}>
          <View style={styles.assistantIcon}><Ionicons name="chatbubbles-outline" size={28} color={Colors.primaryLight} /></View>
          <View style={styles.flex}>
            <Text style={styles.title}>New conversation</Text>
            <Text style={styles.secondary}>AI service unavailable</Text>
          </View>
          <PreviewIconButton icon="trash-outline" label="Clear draft" disabled={!draft} onPress={() => setDraft('')} />
        </View>
        <View style={styles.conversationState}>
          <Ionicons name="chatbubble-ellipses-outline" size={40} color={Colors.text.muted} />
          <Text style={styles.emptyTitle}>No messages yet</Text>
          <Text style={styles.secondary}>Farm data is not shared with an AI service.</Text>
        </View>
        <Text style={styles.sectionTitle}>Suggested questions</Text>
        {QUESTIONS.map((item) => (
          <Pressable key={item.title} accessibilityRole="button" accessibilityLabel={`Draft: ${item.title}`}
            onPress={() => setDraft(item.question)} style={styles.question}>
            <Ionicons name={item.icon} size={22} color={Colors.primaryLight} />
            <View style={styles.flex}>
              <Text style={styles.questionTitle}>{item.title}</Text>
              <Text style={styles.secondary}>{item.question}</Text>
            </View>
            <Ionicons name="arrow-down-outline" size={18} color={Colors.text.muted} />
          </Pressable>
        ))}
      </ScrollView>
      <View style={[styles.composerBand, { paddingBottom: Math.max(insets.bottom, 12) }]}>
        <View style={styles.composerWidth}>
          <View style={styles.draftHeading}>
            <Text style={styles.secondary}>Local draft</Text>
            <Text style={styles.secondary}>{draft.length}/{MAX_DRAFT_LENGTH}</Text>
          </View>
          <View style={styles.composer}>
            <TextInput accessibilityLabel="Message draft" value={draft} onChangeText={setDraft}
              placeholder="Your question..." placeholderTextColor={Colors.text.muted}
              maxLength={MAX_DRAFT_LENGTH} multiline textAlignVertical="top" style={styles.input} />
            <PreviewIconButton icon="arrow-up" label="Send unavailable: AI service not connected" disabled />
          </View>
          <Text style={styles.notSent}>Not sent / Session only</Text>
        </View>
      </View>
    </KeyboardAvoidingView>
  );
}

export default function AIAssistantScreen() {
  return <PreviewScreen title="AI Assistant"><AssistantWorkspace /></PreviewScreen>;
}

const styles = StyleSheet.create({
  root: { flex: 1 },
  flex: { flex: 1 },
  content: { flexGrow: 1, width: '100%', maxWidth: 760, alignSelf: 'center', padding: 16 },
  conversationHeader: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  assistantIcon: { width: 48, height: 48, alignItems: 'center', justifyContent: 'center',
    backgroundColor: Colors.primaryMuted, borderRadius: 8 },
  title: { color: Colors.text.primary, fontSize: Typography.base, fontWeight: '600', marginBottom: 4 },
  secondary: { color: Colors.text.secondary, fontSize: Typography.sm, lineHeight: 19 },
  conversationState: { flexGrow: 1, minHeight: 170, alignItems: 'center', justifyContent: 'center', gap: 10,
    paddingHorizontal: 12, paddingVertical: 24 },
  emptyTitle: { color: Colors.text.primary, fontSize: Typography.base, fontWeight: '600' },
  sectionTitle: { fontSize: Typography.sm, fontWeight: '600', color: Colors.text.secondary, marginBottom: 12 },
  question: { flexDirection: 'row', gap: 12, alignItems: 'center', borderBottomWidth: 1,
    borderBottomColor: Colors.border.default, paddingVertical: 14 },
  questionTitle: { color: Colors.text.primary, fontSize: Typography.sm, fontWeight: '600', marginBottom: 4 },
  composerBand: { paddingTop: 12, paddingHorizontal: 16, borderTopWidth: 1, borderTopColor: Colors.border.default },
  composerWidth: { width: '100%', maxWidth: 728, alignSelf: 'center', gap: 8 },
  draftHeading: { flexDirection: 'row', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 },
  composer: { flexDirection: 'row', alignItems: 'flex-end', borderWidth: 1, borderColor: Colors.border.default,
    borderRadius: 8, padding: 6, backgroundColor: Colors.bg.input },
  input: { flex: 1, minWidth: 0, minHeight: 66, maxHeight: 128, padding: 8,
    fontSize: Typography.base, lineHeight: 22, color: Colors.text.primary },
  notSent: { color: Colors.text.secondary, fontSize: Typography.xs, lineHeight: 16 },
});
