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

// ─── VetOptionsScreen ─────────────────────────────────────────────────────────
export default function VetOptionsScreen() {
  const role = useAuthStore((state) => state.role);
  const currentFarmId = useFarmStore((state) => state.currentFarmId);
  const isVetOrAdmin = role === 'vet' || role === 'admin';
  const isOwner = role === 'owner';

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

  const handleCreateCase = async () => {
    if (!selectedAnimalId || !caseTitle.trim()) {
      Alert.alert('Champs obligatoires', 'Veuillez sélectionner un animal et indiquer un titre.');
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
      setShowCreateModal(false);
      setCaseTitle('');
      setInitialContent('');
      setSelectedAnimalId(null);
      refetch();
    } catch (err: any) {
      Alert.alert('Erreur', err?.message || 'Impossible de créer le dossier.');
    }
  };

  const handleAddEntry = async () => {
    if (!selectedCaseId || !newContent.trim()) {
      Alert.alert('Erreur', 'Veuillez saisir le contenu de la note.');
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
      setShowAddEntryModal(false);
      setNewContent('');
    } catch (err: any) {
      Alert.alert('Erreur', err?.message || "Impossible d'ajouter l'entrée.");
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
      Alert.alert('Erreur', err?.message || 'Impossible de modifier le statut.');
    }
  };

  if (!isVetOrAdmin && !isOwner) {
    return (
      <DrawerScreenBase title="Dossiers Vétérinaires">
        <View style={styles.restrictedContainer}>
          <Ionicons name="lock-closed-outline" size={48} color={Colors.text.muted} />
          <Text style={styles.restrictedTitle}>Accès réservé</Text>
          <Text style={styles.restrictedDesc}>
            Les dossiers cliniques et interventions médicales sont réservés aux vétérinaires et propriétaires de la ferme.
          </Text>
        </View>
      </DrawerScreenBase>
    );
  }

  const cases = casesData?.cases || [];

  return (
    <DrawerScreenBase title="Suivi Vétérinaire">
      <View style={styles.container}>
        {/* Header avec action de création si VET/ADMIN */}
        <View style={styles.topBar}>
          <Text style={styles.headerSubtitle}>
            {cases.length} dossier{cases.length > 1 ? 's' : ''} clinique{cases.length > 1 ? 's' : ''}
          </Text>
          {isVetOrAdmin && (
            <TouchableOpacity
              style={styles.createButton}
              onPress={() => setShowCreateModal(true)}
            >
              <Ionicons name="add" size={18} color="#FFFFFF" />
              <Text style={styles.createButtonText}>Nouveau dossier</Text>
            </TouchableOpacity>
          )}
        </View>

        {/* Filtres de statut */}
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          contentContainerStyle={styles.filterScroll}
        >
          {[
            { label: 'Tous', value: undefined },
            { label: 'En cours', value: 'provisional' },
            { label: 'Confirmés', value: 'confirmed' },
            { label: 'Écartés', value: 'ruled_out' },
            { label: 'Fermés', value: 'closed' },
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
            <Text style={styles.emptyText}>Aucun dossier vétérinaire trouvé</Text>
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
                    <Text style={styles.caseTitle}>{c.title}</Text>
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
                    Animal : {c.animal_name || `#${c.animal_id}`}
                  </Text>
                  <Text style={styles.caseEntries}>
                    {c.entries_count} note{c.entries_count > 1 ? 's' : ''}
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
                  {caseDetail?.title || 'Dossier clinique'}
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
                      Animal : {caseDetail.animal_name || `#${caseDetail.animal_id}`}
                    </Text>
                    <Text style={styles.detailOpener}>
                      Ouvert par : {caseDetail.opener_name || `Utilisateur #${caseDetail.opened_by}`}
                    </Text>
                    <Text style={styles.detailDate}>
                      Date : {new Date(caseDetail.opened_at).toLocaleDateString()}
                    </Text>

                    {isVetOrAdmin && (
                      <View style={styles.statusButtonsRow}>
                        <Text style={styles.statusLabel}>Modifier statut :</Text>
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
                    <Text style={styles.journalTitle}>Journal d'interventions</Text>
                    {isVetOrAdmin && (
                      <TouchableOpacity
                        style={styles.addEntryBtn}
                        onPress={() => setShowAddEntryModal(true)}
                      >
                        <Ionicons name="add-circle-outline" size={16} color={Colors.primary} />
                        <Text style={styles.addEntryBtnText}>Ajouter note</Text>
                      </TouchableOpacity>
                    )}
                  </View>

                  {caseDetail.entries.length === 0 ? (
                    <Text style={styles.emptyEntries}>Aucune note enregistrée.</Text>
                  ) : (
                    caseDetail.entries.map((entry) => (
                      <View key={entry.id} style={styles.entryCard}>
                        <View style={styles.entryHeader}>
                          <Text style={styles.entryType}>
                            {entry.entry_type.toUpperCase()}
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
          onRequestClose={() => setShowCreateModal(false)}
        >
          <View style={styles.modalOverlay}>
            <View style={styles.createModalContent}>
              <Text style={styles.modalTitle}>Nouveau Dossier Clinique</Text>

              {/* Sélection de l'animal */}
              <Text style={styles.inputLabel}>Sélectionner un animal</Text>
              <ScrollView
                horizontal
                showsHorizontalScrollIndicator={false}
                style={styles.animalPicker}
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
              <Text style={styles.inputLabel}>Intitulé du suivi</Text>
              <TextInput
                style={styles.textInput}
                placeholder="Ex : Examen podologique, toux suspecte..."
                placeholderTextColor={Colors.text.muted}
                value={caseTitle}
                onChangeText={setCaseTitle}
              />

              {/* Note initiale */}
              <Text style={styles.inputLabel}>Observation initiale (optionnelle)</Text>
              <TextInput
                style={[styles.textInput, styles.textArea]}
                placeholder="Observations cliniques constatées par le praticien..."
                placeholderTextColor={Colors.text.muted}
                multiline
                numberOfLines={3}
                value={initialContent}
                onChangeText={setInitialContent}
              />

              <View style={styles.modalActions}>
                <TouchableOpacity
                  style={styles.cancelBtn}
                  onPress={() => setShowCreateModal(false)}
                >
                  <Text style={styles.cancelBtnText}>Annuler</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={styles.submitBtn}
                  onPress={handleCreateCase}
                  disabled={createCaseMutation.isPending}
                >
                  {createCaseMutation.isPending ? (
                    <ActivityIndicator size="small" color="#FFFFFF" />
                  ) : (
                    <Text style={styles.submitBtnText}>Créer le dossier</Text>
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
          onRequestClose={() => setShowAddEntryModal(false)}
        >
          <View style={styles.modalOverlay}>
            <View style={styles.createModalContent}>
              <Text style={styles.modalTitle}>Ajouter une Note Clinique</Text>

              <Text style={styles.inputLabel}>Type d'acte</Text>
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

              <Text style={styles.inputLabel}>Contenu de la note</Text>
              <TextInput
                style={[styles.textInput, styles.textArea]}
                placeholder="Détail de l'observation, traitement administré, recommandations..."
                placeholderTextColor={Colors.text.muted}
                multiline
                numberOfLines={4}
                value={newContent}
                onChangeText={setNewContent}
              />

              <View style={styles.modalActions}>
                <TouchableOpacity
                  style={styles.cancelBtn}
                  onPress={() => setShowAddEntryModal(false)}
                >
                  <Text style={styles.cancelBtnText}>Annuler</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={styles.submitBtn}
                  onPress={handleAddEntry}
                  disabled={addEntryMutation.isPending}
                >
                  {addEntryMutation.isPending ? (
                    <ActivityIndicator size="small" color="#FFFFFF" />
                  ) : (
                    <Text style={styles.submitBtnText}>Enregistrer</Text>
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
  filterScroll: {
    paddingHorizontal: Spacing.base,
    gap: Spacing.xs,
    paddingBottom: Spacing.xs,
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
    fontSize: Typography.xs,
    color: Colors.text.muted,
    fontWeight: '600',
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
    borderRadius: Radius.md,
    padding: Spacing.md,
    borderWidth: 1,
    borderColor: Colors.border.default,
    gap: Spacing.xs,
  },
  caseHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  caseTitleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.xs,
    flex: 1,
  },
  caseTitle: {
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
    backgroundColor: Colors.bg.card,
    borderRadius: Radius.lg,
    padding: Spacing.md,
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
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: Radius.sm,
    backgroundColor: Colors.bg.card,
  },
  stButtonActive: {
    backgroundColor: Colors.primary,
  },
  stButtonText: {
    fontSize: 10,
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
  inputLabel: {
    fontSize: Typography.xs,
    fontWeight: '600',
    color: Colors.text.secondary,
    marginTop: Spacing.xs,
  },
  textInput: {
    backgroundColor: Colors.bg.input,
    borderRadius: Radius.sm,
    paddingHorizontal: Spacing.sm,
    paddingVertical: 8,
    color: Colors.text.primary,
    fontSize: Typography.sm,
    borderWidth: 1,
    borderColor: Colors.border.default,
  },
  textArea: {
    height: 70,
    textAlignVertical: 'top',
  },
  animalPicker: {
    flexDirection: 'row',
    marginVertical: 4,
  },
  animalChip: {
    paddingHorizontal: Spacing.sm,
    paddingVertical: 6,
    borderRadius: Radius.sm,
    backgroundColor: Colors.bg.elevated,
    marginRight: Spacing.xs,
  },
  animalChipSelected: {
    backgroundColor: Colors.primary + '25',
    borderColor: Colors.primary,
    borderWidth: 1,
  },
  animalChipText: {
    fontSize: Typography.xs,
    color: Colors.text.secondary,
  },
  animalChipTextSelected: {
    color: Colors.primary,
    fontWeight: '700',
  },
  entryTypeRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: Spacing.xs,
    marginVertical: 4,
  },
  entryTypeChip: {
    paddingHorizontal: Spacing.sm,
    paddingVertical: 4,
    borderRadius: Radius.sm,
    backgroundColor: Colors.bg.elevated,
  },
  entryTypeChipSelected: {
    backgroundColor: Colors.primary + '25',
    borderColor: Colors.primary,
    borderWidth: 1,
  },
  entryTypeText: {
    fontSize: 10,
    color: Colors.text.secondary,
  },
  entryTypeTextSelected: {
    color: Colors.primary,
    fontWeight: '700',
  },
  modalActions: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    gap: Spacing.sm,
    marginTop: Spacing.md,
  },
  cancelBtn: {
    paddingHorizontal: Spacing.md,
    paddingVertical: Spacing.sm,
  },
  cancelBtnText: {
    fontSize: Typography.sm,
    color: Colors.text.muted,
  },
  submitBtn: {
    backgroundColor: Colors.primary,
    paddingHorizontal: Spacing.md,
    paddingVertical: Spacing.sm,
    borderRadius: Radius.sm,
  },
  submitBtnText: {
    fontSize: Typography.sm,
    fontWeight: '700',
    color: '#FFFFFF',
  },
});