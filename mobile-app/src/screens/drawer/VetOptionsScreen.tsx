import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  Modal,
  TextInput,
  ActivityIndicator,
  Alert,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import DrawerScreenBase from './DrawerScreenBase';
import { Colors, Spacing, Typography, Radius } from '../../constants/config';
import { useAuthStore } from '../../store/authStore';
import { useFarmStore } from '../../store/farmStore';
import {
  useFarmVeterinaryCases,
  useVeterinaryCaseDetail,
  useCreateVeterinaryCase,
  useUpdateVeterinaryCase,
  useAddCaseEntry,
} from '../../hooks/useVeterinary';
import { useAnimals } from '../../hooks/useAnimals';
import { VeterinaryCase, VeterinaryEntry } from '../../api/veterinary';
import { selectedFarmRole } from '../../utils/selectedFarmRole';
import { entryTypeLabel } from '../../utils/veterinaryLabels';

// ─── VetOptionsScreen ─────────────────────────────────────────────────────────
export default function VetOptionsScreen() {
  const role = useAuthStore((state) => state.role);
  const farmState = useFarmStore();
  const currentFarmId = farmState.currentFarmId;
  // Same source as Profile / Drawer: the role in the selected farm (platform admin aside).
  const farmRole = selectedFarmRole(role, farmState);
  const isVetOrAdmin = farmRole === 'vet' || farmRole === 'admin';
  const isOwner = farmRole === 'owner';

  const [statusFilter, setStatusFilter] = useState<string | undefined>(undefined);
  const [selectedCaseId, setSelectedCaseId] = useState<number | null>(null);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showAddEntryModal, setShowAddEntryModal] = useState(false);

  // Form states - Create case
  const [selectedAnimalId, setSelectedAnimalId] = useState<number | null>(null);
  const [caseTitle, setCaseTitle] = useState('');
  const [initialEntryType, setInitialEntryType] = useState<
    'observation' | 'intervention' | 'follow_up' | 'assessment' | 'note'
  >('observation');
  const [initialContent, setInitialContent] = useState('');

  // Form states - Add entry
  const [newEntryType, setNewEntryType] = useState<
    'observation' | 'intervention' | 'follow_up' | 'assessment' | 'note'
  >('observation');
  const [newContent, setNewContent] = useState('');

  // Queries
  const { data: casesData, isLoading, refetch } = useFarmVeterinaryCases({
    status: statusFilter,
  });
  const { data: animalsList } = useAnimals();
  const { data: caseDetail, isLoading: isDetailLoading } = useVeterinaryCaseDetail(
    selectedCaseId ?? undefined,
  );

  // Mutations
  const createCaseMutation = useCreateVeterinaryCase();
  const updateCaseMutation = useUpdateVeterinaryCase();
  const addEntryMutation = useAddCaseEntry();

  // A form opens empty after Cancel / close or a successful save; a failed save keeps the text.
  const resetCreateForm = () => {
    setSelectedAnimalId(null);
    setCaseTitle('');
    setInitialEntryType('observation');
    setInitialContent('');
  };

  const resetEntryForm = () => {
    setNewEntryType('observation');
    setNewContent('');
  };

  const closeCreateModal = () => {
    setShowCreateModal(false);
    resetCreateForm();
  };

  const closeAddEntryModal = () => {
    setShowAddEntryModal(false);
    resetEntryForm();
  };

  const handleCreateCase = async () => {
    if (!selectedAnimalId || !caseTitle.trim()) {
      Alert.alert('Required fields', 'Please select an animal and enter a title.');
      return;
    }

    try {
      await createCaseMutation.mutateAsync({
        animal_id: selectedAnimalId,
        title: caseTitle.trim(),
        initial_entry: initialContent.trim()
          ? {
              entry_type: initialEntryType,
              content: initialContent.trim(),
            }
          : undefined,
      });
      closeCreateModal();
      refetch();
    } catch (err: any) {
      Alert.alert('Error', err?.message || 'Unable to create the case.');
    }
  };

  const handleAddEntry = async () => {
    if (!selectedCaseId || !newContent.trim()) {
      Alert.alert('Error', 'Please enter the note content.');
      return;
    }

    try {
      await addEntryMutation.mutateAsync({
        caseId: selectedCaseId,
        payload: {
          entry_type: newEntryType,
          content: newContent.trim(),
        },
      });
      closeAddEntryModal();
    } catch (err: any) {
      Alert.alert('Error', err?.message || 'Unable to add the entry.');
    }
  };

  const handleStatusChange = async (newStatus: 'provisional' | 'confirmed' | 'ruled_out' | 'closed') => {
    if (!selectedCaseId) return;
    try {
      await updateCaseMutation.mutateAsync({
        caseId: selectedCaseId,
        payload: { status: newStatus },
      });
    } catch (err: any) {
      Alert.alert('Error', err?.message || 'Unable to change the status.');
    }
  };

  if (!isVetOrAdmin && !isOwner) {
    return (
      <DrawerScreenBase title="Veterinary Records">
        <View style={styles.restrictedContainer}>
          <Ionicons name="lock-closed-outline" size={48} color={Colors.text.muted} />
          <Text style={styles.restrictedTitle}>Restricted access</Text>
          <Text style={styles.restrictedDesc}>
            Clinical records and medical interventions are restricted to the farm's veterinarians and owners.
          </Text>
        </View>
      </DrawerScreenBase>
    );
  }

  const cases = casesData?.cases || [];

  return (
    <DrawerScreenBase title="Veterinary Follow-up">
      <View style={styles.container}>
        {/* Header avec action de création si VET/ADMIN */}
        <View style={styles.topBar}>
          <Text style={styles.headerSubtitle}>
            {cases.length} clinical case{cases.length === 1 ? '' : 's'}
          </Text>
          {isVetOrAdmin && (
            <TouchableOpacity
              style={styles.createButton}
              onPress={() => setShowCreateModal(true)}
            >
              <Ionicons name="add" size={18} color="#FFFFFF" />
              <Text style={styles.createButtonText}>New case</Text>
            </TouchableOpacity>
          )}
        </View>

        {/* Filtres de statut */}
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          style={styles.filterBar}
          contentContainerStyle={styles.filterScroll}
        >
          {[
            { label: 'All', value: undefined },
            { label: 'Provisional', value: 'provisional' },
            { label: 'Confirmed', value: 'confirmed' },
            { label: 'Ruled out', value: 'ruled_out' },
            { label: 'Closed', value: 'closed' },
          ].map((f) => {
            const isSelected = statusFilter === f.value;
            return (
              <TouchableOpacity
                key={f.label}
                style={[styles.filterChip, isSelected && styles.filterChipSelected]}
                onPress={() => setStatusFilter(f.value)}
              >
                <Text style={[styles.filterText, isSelected && styles.filterTextSelected]}>
                  {f.label}
                </Text>
              </TouchableOpacity>
            );
          })}
        </ScrollView>

        {/* Liste des dossiers */}
        {isLoading ? (
          <View style={styles.centerContainer}>
            <ActivityIndicator size="large" color={Colors.primary} />
          </View>
        ) : cases.length === 0 ? (
          <View style={styles.centerContainer}>
            <Ionicons name="medical-outline" size={48} color={Colors.text.muted} />
            <Text style={styles.emptyText}>No veterinary cases found</Text>
          </View>
        ) : (
          <ScrollView contentContainerStyle={styles.caseList}>
            {cases.map((c) => (
              <TouchableOpacity
                key={c.id}
                style={styles.caseCard}
                onPress={() => setSelectedCaseId(c.id)}
              >
                <View style={styles.caseHeader}>
                  <View style={styles.caseTitleRow}>
                    <Ionicons name="document-text-outline" size={18} color={Colors.primary} />
                    <Text style={styles.caseTitle} numberOfLines={2}>{c.title}</Text>
                  </View>
                  <View
                    style={[
                      styles.statusBadge,
                      c.status === 'confirmed' && styles.statusConfirmed,
                      c.status === 'closed' && styles.statusClosed,
                      c.status === 'ruled_out' && styles.statusRuledOut,
                    ]}
                  >
                    <Text style={styles.statusText}>{c.status.toUpperCase()}</Text>
                  </View>
                </View>

                <View style={styles.caseMetaRow}>
                  <Text style={styles.caseAnimal}>
                    Animal: {c.animal_name || `#${c.animal_id}`}
                  </Text>
                  <Text style={styles.caseEntries}>
                    {c.entries_count} note{c.entries_count === 1 ? '' : 's'}
                  </Text>
                </View>
              </TouchableOpacity>
            ))}
          </ScrollView>
        )}

        {/* MODAL DÉTAIL DU DOSSIER */}
        <Modal
          visible={selectedCaseId !== null}
          animationType="slide"
          transparent={true}
          onRequestClose={() => setSelectedCaseId(null)}
        >
          <View style={styles.modalOverlay}>
            <View style={styles.detailModalContent}>
              <View style={styles.modalHeader}>
                <Text style={styles.modalTitle} numberOfLines={1}>
                  {caseDetail?.title || 'Clinical case'}
                </Text>
                <TouchableOpacity onPress={() => setSelectedCaseId(null)}>
                  <Ionicons name="close" size={24} color={Colors.text.primary} />
                </TouchableOpacity>
              </View>

              {isDetailLoading || !caseDetail ? (
                <View style={styles.centerContainer}>
                  <ActivityIndicator size="small" color={Colors.primary} />
                </View>
              ) : (
                <ScrollView contentContainerStyle={styles.detailScroll}>
                  {/* Statut & Actions */}
                  <View style={styles.detailInfoBox}>
                    <Text style={styles.detailAnimalName}>
                      Animal: {caseDetail.animal_name || `#${caseDetail.animal_id}`}
                    </Text>
                    <Text style={styles.detailOpener}>
                      Opened by: {caseDetail.opener_name || `User #${caseDetail.opened_by}`}
                    </Text>
                    <Text style={styles.detailDate}>
                      Date: {new Date(caseDetail.opened_at).toLocaleDateString()}
                    </Text>

                    {isVetOrAdmin && (
                      <View style={styles.statusButtonsRow}>
                        <Text style={styles.statusLabel}>Change status:</Text>
                        {(['provisional', 'confirmed', 'ruled_out', 'closed'] as const).map(
                          (st) => (
                            <TouchableOpacity
                              key={st}
                              style={[
                                styles.stButton,
                                caseDetail.status === st && styles.stButtonActive,
                              ]}
                              onPress={() => handleStatusChange(st)}
                            >
                              <Text
                                style={[
                                  styles.stButtonText,
                                  caseDetail.status === st && styles.stButtonTextActive,
                                ]}
                              >
                                {st}
                              </Text>
                            </TouchableOpacity>
                          ),
                        )}
                      </View>
                    )}
                  </View>

                  {/* Journal des entrées */}
                  <View style={styles.journalHeader}>
                    <Text style={styles.journalTitle}>Case journal</Text>
                    {isVetOrAdmin && (
                      <TouchableOpacity
                        style={styles.addEntryBtn}
                        onPress={() => setShowAddEntryModal(true)}
                      >
                        <Ionicons name="add-circle-outline" size={16} color={Colors.primary} />
                        <Text style={styles.addEntryBtnText}>Add note</Text>
                      </TouchableOpacity>
                    )}
                  </View>

                  {caseDetail.entries.length === 0 ? (
                    <Text style={styles.emptyEntries}>No notes recorded.</Text>
                  ) : (
                    caseDetail.entries.map((entry) => (
                      <View key={entry.id} style={styles.entryCard}>
                        <View style={styles.entryHeader}>
                          <Text style={styles.entryType}>
                            {entryTypeLabel(entry.entry_type)}
                          </Text>
                          <Text style={styles.entryDate}>
                            {new Date(entry.occurred_at).toLocaleString()}
                          </Text>
                        </View>
                        <Text style={styles.entryContent}>{entry.content}</Text>
                        {entry.author_name && (
                          <Text style={styles.entryAuthor}>Dr. {entry.author_name}</Text>
                        )}
                      </View>
                    ))
                  )}
                </ScrollView>
              )}
            </View>
          </View>
        </Modal>

        {/* MODAL CRÉATION DOSSIER */}
        <Modal
          visible={showCreateModal}
          animationType="fade"
          transparent={true}
          onRequestClose={closeCreateModal}
        >
          <View style={styles.modalOverlay}>
            <View style={styles.createModalContent}>
              <Text style={styles.modalTitle}>New Clinical Case</Text>

              <ScrollView style={styles.formScroll} contentContainerStyle={styles.formBody} keyboardShouldPersistTaps="handled">
              {/* Sélection de l'animal */}
              <Text style={styles.inputLabel}>Select an animal</Text>
              <ScrollView
                horizontal
                showsHorizontalScrollIndicator={false}
                style={styles.animalPicker}
                contentContainerStyle={styles.animalPickerContent}
              >
                {(animalsList?.animals || []).map((a) => {
                  const isSelected = selectedAnimalId === a.id;
                  return (
                    <TouchableOpacity
                      key={a.id}
                      style={[styles.animalChip, isSelected && styles.animalChipSelected]}
                      onPress={() => setSelectedAnimalId(a.id)}
                    >
                      <Text style={[styles.animalChipText, isSelected && styles.animalChipTextSelected]}>
                        {a.name} (#{a.id})
                      </Text>
                    </TouchableOpacity>
                  );
                })}
              </ScrollView>

              {/* Titre */}
              <Text style={styles.inputLabel}>Case title</Text>
              <TextInput
                style={styles.textInput}
                placeholder="E.g. hoof examination, suspected cough..."
                placeholderTextColor={Colors.text.muted}
                value={caseTitle}
                onChangeText={setCaseTitle}
              />

              {/* Note initiale */}
              <Text style={styles.inputLabel}>Initial observation (optional)</Text>
              <TextInput
                style={[styles.textInput, styles.textArea]}
                placeholder="Clinical observations made by the practitioner..."
                placeholderTextColor={Colors.text.muted}
                multiline
                numberOfLines={3}
                value={initialContent}
                onChangeText={setInitialContent}
              />
              </ScrollView>

              <View style={styles.modalActions}>
                <TouchableOpacity
                  style={styles.cancelBtn}
                  onPress={closeCreateModal}
                >
                  <Text style={styles.cancelBtnText}>Cancel</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={styles.submitBtn}
                  onPress={handleCreateCase}
                  disabled={createCaseMutation.isPending}
                >
                  {createCaseMutation.isPending ? (
                    <ActivityIndicator size="small" color="#FFFFFF" />
                  ) : (
                    <Text style={styles.submitBtnText}>Create case</Text>
                  )}
                </TouchableOpacity>
              </View>
            </View>
          </View>
        </Modal>

        {/* MODAL AJOUT NOTE / INTERVENTION */}
        <Modal
          visible={showAddEntryModal}
          animationType="fade"
          transparent={true}
          onRequestClose={closeAddEntryModal}
        >
          <View style={styles.modalOverlay}>
            <View style={styles.createModalContent}>
              <Text style={styles.modalTitle}>Add a Clinical Note</Text>

              <ScrollView style={styles.formScroll} contentContainerStyle={styles.formBody} keyboardShouldPersistTaps="handled">
              <Text style={styles.inputLabel}>Entry type</Text>
              <View style={styles.entryTypeRow}>
                {(['observation', 'intervention', 'follow_up', 'note'] as const).map(
                  (t) => {
                    const isSelected = newEntryType === t;
                    return (
                      <TouchableOpacity
                        key={t}
                        style={[styles.entryTypeChip, isSelected && styles.entryTypeChipSelected]}
                        onPress={() => setNewEntryType(t)}
                      >
                        <Text
                          style={[
                            styles.entryTypeText,
                            isSelected && styles.entryTypeTextSelected,
                          ]}
                        >
                          {t}
                        </Text>
                      </TouchableOpacity>
                    );
                  },
                )}
              </View>

              <Text style={styles.inputLabel}>Note content</Text>
              <TextInput
                style={[styles.textInput, styles.textArea]}
                placeholder="Observation details, treatment given, recommendations..."
                placeholderTextColor={Colors.text.muted}
                multiline
                numberOfLines={4}
                value={newContent}
                onChangeText={setNewContent}
              />
              </ScrollView>

              <View style={styles.modalActions}>
                <TouchableOpacity
                  style={styles.cancelBtn}
                  onPress={closeAddEntryModal}
                >
                  <Text style={styles.cancelBtnText}>Cancel</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={styles.submitBtn}
                  onPress={handleAddEntry}
                  disabled={addEntryMutation.isPending}
                >
                  {addEntryMutation.isPending ? (
                    <ActivityIndicator size="small" color="#FFFFFF" />
                  ) : (
                    <Text style={styles.submitBtnText}>Save</Text>
                  )}
                </TouchableOpacity>
              </View>
            </View>
          </View>
        </Modal>
      </View>
    </DrawerScreenBase>
  );
}

// ─── Styles ──────────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.bg.primary },
  topBar: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: Spacing.base,
    paddingVertical: Spacing.sm,
  },
  headerSubtitle: {
    fontSize: Typography.sm,
    color: Colors.text.secondary,
    fontWeight: '600',
  },
  createButton: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: Colors.primary,
    paddingHorizontal: Spacing.sm,
    paddingVertical: 6,
    borderRadius: Radius.md,
    gap: 4,
  },
  createButtonText: {
    fontSize: Typography.xs,
    color: '#FFFFFF',
    fontWeight: '700',
  },
  // A horizontal ScrollView grows to fill the column unless told not to (chips became tall boxes).
  filterBar: {
    flexGrow: 0,
    flexShrink: 0,
  },
  filterScroll: {
    paddingHorizontal: Spacing.base,
    gap: Spacing.sm,
    paddingBottom: Spacing.sm,
    alignItems: 'center',
  },
  filterChip: {
    paddingHorizontal: Spacing.md,
    paddingVertical: 6,
    borderRadius: Radius.full,
    backgroundColor: Colors.bg.card,
    borderWidth: 1,
    borderColor: Colors.border.default,
  },
  filterChipSelected: {
    backgroundColor: Colors.primary + '25',
    borderColor: Colors.primary,
  },
  filterText: {
    fontSize: Typography.sm,
    color: Colors.text.secondary,
    fontWeight: '500',
  },
  filterTextSelected: {
    color: Colors.primary,
  },
  caseList: {
    padding: Spacing.base,
    gap: Spacing.sm,
  },
  caseCard: {
    backgroundColor: Colors.bg.card,
    borderRadius: Radius.lg,
    padding: Spacing.md,
    borderWidth: 1,
    borderColor: Colors.border.default,
    gap: Spacing.xs,
  },
  caseHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    gap: Spacing.sm,
  },
  caseTitleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.xs,
    flex: 1,
  },
  caseTitle: {
    flexShrink: 1,
    fontSize: Typography.base,
    fontWeight: '600',
    color: Colors.text.primary,
  },
  statusBadge: {
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: Radius.sm,
    backgroundColor: Colors.severity.warning + '25',
  },
  statusConfirmed: {
    backgroundColor: Colors.primary + '25',
  },
  statusClosed: {
    backgroundColor: Colors.text.muted + '25',
  },
  statusRuledOut: {
    backgroundColor: Colors.severity.critical + '25',
  },
  statusText: {
    fontSize: 10,
    fontWeight: '700',
    color: Colors.text.primary,
  },
  caseMetaRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginTop: 4,
  },
  caseAnimal: {
    fontSize: Typography.xs,
    color: Colors.text.secondary,
  },
  caseEntries: {
    fontSize: Typography.xs,
    color: Colors.text.muted,
  },
  centerContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: Spacing.xl,
    gap: Spacing.sm,
  },
  emptyText: {
    fontSize: Typography.sm,
    color: Colors.text.muted,
  },
  restrictedContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: Spacing.xl,
    gap: Spacing.md,
  },
  restrictedTitle: {
    fontSize: Typography.lg,
    fontWeight: '700',
    color: Colors.text.primary,
  },
  restrictedDesc: {
    fontSize: Typography.sm,
    color: Colors.text.muted,
    textAlign: 'center',
    lineHeight: 20,
  },
  // Modal styles
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.7)',
    justifyContent: 'center',
    alignItems: 'center',
    padding: Spacing.base,
  },
  detailModalContent: {
    width: '100%',
    maxHeight: '85%',
    backgroundColor: Colors.bg.card,
    borderRadius: Radius.lg,
    padding: Spacing.md,
  },
  createModalContent: {
    width: '100%',
    maxHeight: '85%',
    backgroundColor: Colors.bg.card,
    borderRadius: Radius.lg,
    padding: Spacing.base,
    gap: Spacing.sm,
  },
  formScroll: {
    flexGrow: 0,
  },
  formBody: {
    gap: Spacing.xs,
  },
  modalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    borderBottomWidth: 1,
    borderBottomColor: Colors.border.default,
    paddingBottom: Spacing.sm,
  },
  modalTitle: {
    fontSize: Typography.md,
    fontWeight: '700',
    color: Colors.text.primary,
    flex: 1,
  },
  detailScroll: {
    paddingVertical: Spacing.md,
    gap: Spacing.md,
  },
  detailInfoBox: {
    backgroundColor: Colors.bg.elevated,
    padding: Spacing.sm,
    borderRadius: Radius.md,
    gap: 4,
  },
  detailAnimalName: {
    fontSize: Typography.sm,
    fontWeight: '600',
    color: Colors.text.primary,
  },
  detailOpener: {
    fontSize: Typography.xs,
    color: Colors.text.secondary,
  },
  detailDate: {
    fontSize: Typography.xs,
    color: Colors.text.muted,
  },
  statusButtonsRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 4,
    alignItems: 'center',
    marginTop: 6,
  },
  statusLabel: {
    fontSize: Typography.xs,
    color: Colors.text.muted,
    marginRight: 4,
  },
  stButton: {
    paddingHorizontal: Spacing.sm,
    paddingVertical: Spacing.xs,
    borderRadius: Radius.full,
    borderWidth: 1,
    borderColor: Colors.border.default,
    backgroundColor: Colors.bg.card,
  },
  stButtonActive: {
    backgroundColor: Colors.primary,
  },
  stButtonText: {
    fontSize: Typography.xs,
    color: Colors.text.secondary,
  },
  stButtonTextActive: {
    color: '#FFFFFF',
    fontWeight: '700',
  },
  journalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginTop: Spacing.xs,
  },
  journalTitle: {
    fontSize: Typography.sm,
    fontWeight: '700',
    color: Colors.text.primary,
  },
  addEntryBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  addEntryBtnText: {
    fontSize: Typography.xs,
    color: Colors.primary,
    fontWeight: '600',
  },
  emptyEntries: {
    fontSize: Typography.xs,
    color: Colors.text.muted,
    fontStyle: 'italic',
  },
  entryCard: {
    backgroundColor: Colors.bg.elevated,
    borderRadius: Radius.sm,
    padding: Spacing.sm,
    gap: 4,
  },
  entryHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  entryType: {
    fontSize: 10,
    fontWeight: '700',
    color: Colors.primary,
  },
  entryDate: {
    fontSize: 10,
    color: Colors.text.muted,
  },
  entryContent: {
    fontSize: Typography.xs,
    color: Colors.text.primary,
    lineHeight: 16,
  },
  entryAuthor: {
    fontSize: 10,
    color: Colors.text.secondary,
    fontStyle: 'italic',
    textAlign: 'right',
  },
  // Inputs and labels follow FarmCreateModal / AnimalFormScreen.
  inputLabel: {
    fontSize: Typography.sm,
    fontWeight: '600',
    color: Colors.text.secondary,
    marginTop: Spacing.sm,
    marginBottom: 2,
  },
  textInput: {
    minHeight: 44,
    backgroundColor: Colors.bg.input,
    borderRadius: Radius.md,
    paddingHorizontal: Spacing.md,
    paddingVertical: Spacing.sm + 2,
    color: Colors.text.primary,
    fontSize: Typography.base,
    borderWidth: 1,
    borderColor: Colors.border.default,
  },
  textArea: {
    minHeight: 100,
    maxHeight: 160,
    textAlignVertical: 'top',
  },
  animalPicker: {
    flexGrow: 0,
    flexShrink: 0,
    marginVertical: Spacing.xs,
  },
  animalPickerContent: {
    alignItems: 'center',
    gap: Spacing.sm,
  },
  animalChip: {
    paddingHorizontal: Spacing.md,
    paddingVertical: 6,
    borderRadius: Radius.full,
    borderWidth: 1,
    borderColor: Colors.border.default,
    backgroundColor: Colors.bg.elevated,
  },
  animalChipSelected: {
    backgroundColor: Colors.primary + '25',
    borderColor: Colors.primary,
    borderWidth: 1,
  },
  animalChipText: {
    fontSize: Typography.sm,
    color: Colors.text.secondary,
  },
  animalChipTextSelected: {
    color: Colors.primary,
    fontWeight: '700',
  },
  entryTypeRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: Spacing.sm,
    marginVertical: Spacing.xs,
  },
  entryTypeChip: {
    paddingHorizontal: Spacing.md,
    paddingVertical: 6,
    borderRadius: Radius.full,
    borderWidth: 1,
    borderColor: Colors.border.default,
    backgroundColor: Colors.bg.elevated,
  },
  entryTypeChipSelected: {
    backgroundColor: Colors.primary + '25',
    borderColor: Colors.primary,
    borderWidth: 1,
  },
  entryTypeText: {
    fontSize: Typography.sm,
    color: Colors.text.secondary,
  },
  entryTypeTextSelected: {
    color: Colors.primary,
    fontWeight: '700',
  },
  // Footer buttons follow FarmCreateModal.
  modalActions: {
    flexDirection: 'row',
    gap: Spacing.sm,
    marginTop: Spacing.sm,
  },
  cancelBtn: {
    flex: 1,
    paddingVertical: Spacing.md,
    borderRadius: Radius.md,
    backgroundColor: Colors.bg.input,
    alignItems: 'center',
    justifyContent: 'center',
  },
  cancelBtnText: {
    fontSize: Typography.sm,
    fontWeight: '600',
    color: Colors.text.secondary,
  },
  submitBtn: {
    flex: 2,
    backgroundColor: Colors.primary,
    paddingVertical: Spacing.md,
    borderRadius: Radius.md,
    alignItems: 'center',
    justifyContent: 'center',
  },
  submitBtnText: {
    fontSize: Typography.sm,
    fontWeight: '700',
    color: '#FFFFFF',
  },
});