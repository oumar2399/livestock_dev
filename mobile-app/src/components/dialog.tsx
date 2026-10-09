/**
 * Shared dialog for every confirmation, choice list and message in the app.
 *
 * showDialog() takes the same arguments as Alert.alert, so call sites keep their shape.
 * Dialogs are queued: a dialog opened from a button of another one shows after it closes.
 *
 * Where it is drawn: on iOS a Modal cannot open while another Modal is shown, so when an
 * AppModal is open the dialog is drawn inside the topmost one (DialogOutlet); otherwise the
 * root DialogHost draws it in its own Modal. The Android back button closes the dialog
 * (see backButtonFor).
 */
import React from 'react';
import { Modal, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { create } from 'zustand';

import { Colors, Radius, Spacing, Typography } from '../constants/config';
import { MODAL_ANIMATION, modalStyles } from './modalTheme';

export interface DialogButton {
  text?: string;
  style?: 'default' | 'cancel' | 'destructive';
  onPress?: () => void;
}

export interface DialogRequest {
  id: number;
  title: string;
  message?: string;
  buttons: DialogButton[];
}

interface DialogState {
  queue: DialogRequest[];
  // Open AppModals, topmost last.
  modalStack: number[];
}

export const useDialogStore = create<DialogState>(() => ({ queue: [], modalStack: [] }));

let nextDialogId = 1;
let nextModalId = 1;

export function showDialog(title: string, message?: string, buttons?: DialogButton[]): void {
  const list = buttons && buttons.length > 0 ? buttons : [{ text: 'OK' }];
  const dialog = { id: nextDialogId++, title, message, buttons: list };
  useDialogStore.setState((state) => ({ queue: [...state.queue, dialog] }));
}

/** Closes the dialog first, then runs the chosen action (which may open the next dialog). */
export function pressDialogButton(id: number, button?: DialogButton): void {
  useDialogStore.setState((state) => ({ queue: state.queue.filter((dialog) => dialog.id !== id) }));
  button?.onPress?.();
}

/**
 * What the Android back button means: the Cancel button if there is one, the only button
 * of a message (OK), otherwise close without choosing anything.
 */
export function backButtonFor(buttons: DialogButton[]): DialogButton | undefined {
  return buttons.find((button) => button.style === 'cancel') ?? (buttons.length === 1 ? buttons[0] : undefined);
}

/** Returns false when no dialog was open, so the caller can handle the back press itself. */
export function dismissCurrentDialog(): boolean {
  const current = useDialogStore.getState().queue[0];
  if (!current) return false;
  pressDialogButton(current.id, backButtonFor(current.buttons));
  return true;
}

export function newModalId(): number {
  return nextModalId++;
}

export function registerModal(id: number): void {
  useDialogStore.setState((state) => ({ modalStack: [...state.modalStack.filter((value) => value !== id), id] }));
}

export function unregisterModal(id: number): void {
  useDialogStore.setState((state) => ({ modalStack: state.modalStack.filter((value) => value !== id) }));
}

/** Up to two buttons sit side by side (Cancel on the left); longer choice lists stack, Cancel last. */
export function arrangeButtons(buttons: DialogButton[]): { stacked: boolean; buttons: DialogButton[] } {
  const cancel = buttons.filter((button) => button.style === 'cancel');
  const others = buttons.filter((button) => button.style !== 'cancel');
  if (buttons.length > 2) return { stacked: true, buttons: [...others, ...cancel] };
  return { stacked: false, buttons: [...cancel, ...others] };
}

export function DialogSurface({ dialog }: { dialog: DialogRequest }) {
  const { stacked, buttons } = arrangeButtons(dialog.buttons);
  return (
    <View style={modalStyles.scrim}>
      <View accessibilityViewIsModal style={[modalStyles.card, styles.card]}>
        <Text accessibilityRole="header" style={modalStyles.title}>{dialog.title}</Text>
        {dialog.message ? (
          <ScrollView style={styles.messageScroll}>
            <Text style={styles.message}>{dialog.message}</Text>
          </ScrollView>
        ) : null}
        <View style={stacked ? styles.column : styles.row}>
          {buttons.map((button, index) => {
            const kind = button.style ?? 'default';
            return (
              <Pressable
                key={index + ':' + (button.text ?? 'OK')}
                accessibilityRole="button"
                onPress={() => pressDialogButton(dialog.id, button)}
                style={({ pressed }) => [
                  styles.button,
                  stacked ? styles.buttonStacked : styles.buttonInline,
                  stacked ? stackedStyles[kind] : inlineStyles[kind],
                  pressed && styles.pressed,
                ]}
              >
                <Text style={[styles.buttonText, stacked ? stackedText[kind] : inlineText[kind]]}>
                  {button.text ?? 'OK'}
                </Text>
              </Pressable>
            );
          })}
        </View>
      </View>
    </View>
  );
}

/** Root host: draws the dialog when no AppModal is open (an open one draws it itself). */
export function DialogHost() {
  const current = useDialogStore((state) => state.queue[0]);
  const modalOpen = useDialogStore((state) => state.modalStack.length > 0);
  if (!current || modalOpen) return null;
  return (
    <Modal visible transparent animationType={MODAL_ANIMATION} statusBarTranslucent
      onRequestClose={dismissCurrentDialog}>
      <DialogSurface dialog={current} />
    </Modal>
  );
}

/** Drawn inside an AppModal; only the topmost open AppModal shows the dialog. */
export function DialogOutlet({ modalId }: { modalId: number }) {
  const current = useDialogStore((state) => state.queue[0]);
  const isTop = useDialogStore((state) => state.modalStack[state.modalStack.length - 1] === modalId);
  if (!current || !isTop) return null;
  return (
    <View style={StyleSheet.absoluteFill}>
      <DialogSurface dialog={current} />
    </View>
  );
}

const styles = StyleSheet.create({
  card: { padding: Spacing.base, gap: Spacing.md, maxWidth: 420 },
  messageScroll: { flexGrow: 0, flexShrink: 1 },
  message: { fontSize: Typography.base, color: Colors.text.secondary, lineHeight: 21 },
  row: { flexDirection: 'row', gap: Spacing.sm, marginTop: Spacing.xs },
  column: { gap: Spacing.sm, marginTop: Spacing.xs },
  button: { minHeight: 44, borderRadius: Radius.md, alignItems: 'center', justifyContent: 'center', paddingHorizontal: Spacing.md },
  buttonInline: { flex: 1 },
  buttonStacked: { alignSelf: 'stretch' },
  buttonText: { fontSize: Typography.sm, fontWeight: '700' },
  pressed: { opacity: 0.75 },
});

const inlineStyles = StyleSheet.create({
  default: { backgroundColor: Colors.primary },
  destructive: { backgroundColor: Colors.severity.critical },
  cancel: { backgroundColor: Colors.bg.input, borderWidth: 1, borderColor: Colors.border.default },
});

const inlineText = StyleSheet.create({
  default: { color: '#FFFFFF' },
  destructive: { color: '#FFFFFF' },
  cancel: { color: Colors.text.secondary },
});

const stackedStyles = StyleSheet.create({
  default: { backgroundColor: Colors.bg.elevated, borderWidth: 1, borderColor: Colors.primary + '60' },
  destructive: { backgroundColor: Colors.bg.elevated, borderWidth: 1, borderColor: Colors.severity.critical + '80' },
  cancel: { backgroundColor: Colors.bg.input, borderWidth: 1, borderColor: Colors.border.default },
});

const stackedText = StyleSheet.create({
  default: { color: Colors.primary },
  destructive: { color: Colors.severity.critical },
  cancel: { color: Colors.text.secondary },
});
