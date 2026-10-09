/**
 * The one popup frame of the app: forms, pickers and previews.
 *
 * Header: Close on the left, the title, and an optional primary action (e.g. Save) on the
 * right. An optional footer keeps bottom buttons (forms show Save in both places). The body
 * scrolls and stays above the keyboard. The Android back button first closes a dialog shown
 * on top of the modal, then the modal itself.
 */
import React, { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Modal, Pressable, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { Colors, Radius, Spacing, Typography } from '../constants/config';
import { DialogOutlet, dismissCurrentDialog, newModalId, registerModal, unregisterModal, useDialogStore } from './dialog';
import { FormScroll, useKeyboardInset } from './KeyboardAwareForm';
import { MODAL_ANIMATION, modalStyles } from './modalTheme';

export interface ModalAction {
  label: string;
  onPress: () => void;
  disabled?: boolean;
  busy?: boolean;
  destructive?: boolean;
}

interface AppModalProps {
  visible: boolean;
  title: string;
  subtitle?: string;
  onClose: () => void;
  /** Accessibility label of the Close button (default "Close"). */
  closeLabel?: string;
  /** Shown at the top right of the header. */
  primaryAction?: ModalAction;
  /** Bottom bar (e.g. Cancel / Save). */
  footer?: React.ReactNode;
  /** false when the body manages its own scrolling (lists, tables). Default true. */
  scroll?: boolean;
  /** Default false, so a stray tap never loses a half-filled form. */
  closeOnBackdrop?: boolean;
  children: React.ReactNode;
}

export function HeaderAction({ action }: { action: ModalAction }) {
  const inactive = action.disabled || action.busy;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={action.label}
      accessibilityState={{ disabled: !!inactive, busy: !!action.busy }}
      disabled={inactive}
      onPress={action.onPress}
      hitSlop={8}
      style={({ pressed }) => [
        styles.action,
        { backgroundColor: action.destructive ? Colors.severity.critical : Colors.primary },
        inactive && styles.inactive,
        pressed && styles.pressed,
      ]}
    >
      {action.busy ? <ActivityIndicator size="small" color="#FFFFFF" />
        : <Text style={styles.actionText}>{action.label}</Text>}
    </Pressable>
  );
}

/** Footer button; the footer lays them out side by side. */
export function ModalButton({ label, onPress, kind = 'primary', disabled, busy }: {
  label: string;
  onPress: () => void;
  kind?: 'primary' | 'secondary' | 'destructive';
  disabled?: boolean;
  busy?: boolean;
}) {
  const inactive = disabled || busy;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityState={{ disabled: !!inactive, busy: !!busy }}
      disabled={inactive}
      onPress={onPress}
      style={({ pressed }) => [styles.footerButton, footerKinds[kind], inactive && styles.inactive, pressed && styles.pressed]}
    >
      {busy ? <ActivityIndicator size="small" color={kind === 'secondary' ? Colors.text.secondary : '#FFFFFF'} />
        : <Text style={[styles.footerText, kind === 'secondary' && styles.footerTextSecondary]}>{label}</Text>}
    </Pressable>
  );
}

export default function AppModal({
  visible, title, subtitle, onClose, closeLabel = 'Close', primaryAction, footer,
  scroll = true, closeOnBackdrop = false, children,
}: AppModalProps) {
  const [modalId] = useState(newModalId);
  const scrimRef = useRef<View>(null);
  const inset = useKeyboardInset(scrimRef);

  useEffect(() => {
    if (!visible) return;
    registerModal(modalId);
    return () => unregisterModal(modalId);
  }, [visible, modalId]);

  const handleBack = () => {
    const stack = useDialogStore.getState().modalStack;
    if (stack[stack.length - 1] === modalId && dismissCurrentDialog()) return;
    onClose();
  };

  return (
    <Modal visible={visible} transparent animationType={MODAL_ANIMATION} statusBarTranslucent
      onRequestClose={handleBack}>
      <View ref={scrimRef} style={[modalStyles.scrim, { paddingBottom: Spacing.base + inset }]}>
        {closeOnBackdrop && (
          <Pressable accessibilityRole="button" accessibilityLabel={closeLabel}
            style={StyleSheet.absoluteFill} onPress={onClose} />
        )}
        <View accessibilityViewIsModal style={modalStyles.card}>
          <View style={styles.header}>
            <Pressable accessibilityRole="button" accessibilityLabel={closeLabel} onPress={onClose}
              hitSlop={8} style={styles.close}>
              <Ionicons name="close" size={22} color={Colors.text.primary} />
            </Pressable>
            <View style={styles.titleBlock}>
              <Text accessibilityRole="header" style={modalStyles.title} numberOfLines={2}>{title}</Text>
              {subtitle ? <Text style={modalStyles.subtitle} numberOfLines={2}>{subtitle}</Text> : null}
            </View>
            {primaryAction && <HeaderAction action={primaryAction} />}
          </View>
          {scroll ? (
            <FormScroll modalId={modalId} frameStyle={styles.body} contentContainerStyle={styles.bodyContent}>
              {children}
            </FormScroll>
          ) : (
            <View style={[styles.body, styles.bodyContent]}>{children}</View>
          )}
          {footer ? <View style={styles.footer}>{footer}</View> : null}
        </View>
      </View>
      <DialogOutlet modalId={modalId} />
    </Modal>
  );
}

const styles = StyleSheet.create({
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.sm,
    paddingHorizontal: Spacing.sm,
    paddingVertical: Spacing.sm,
    borderBottomWidth: 1,
    borderBottomColor: Colors.border.default,
  },
  close: { width: 40, height: 40, alignItems: 'center', justifyContent: 'center' },
  titleBlock: { flex: 1 },
  action: {
    minWidth: 64,
    height: 36,
    paddingHorizontal: Spacing.md,
    borderRadius: Radius.md,
    alignItems: 'center',
    justifyContent: 'center',
  },
  actionText: { color: '#FFFFFF', fontSize: Typography.sm, fontWeight: '700' },
  inactive: { opacity: 0.5 },
  pressed: { opacity: 0.75 },
  body: { flexGrow: 0, flexShrink: 1 },
  bodyContent: { padding: Spacing.base },
  footer: {
    flexDirection: 'row',
    gap: Spacing.sm,
    padding: Spacing.base,
    borderTopWidth: 1,
    borderTopColor: Colors.border.default,
  },
  footerButton: {
    flex: 1,
    minHeight: 44,
    borderRadius: Radius.md,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: Spacing.md,
  },
  footerText: { color: '#FFFFFF', fontSize: Typography.sm, fontWeight: '700' },
  footerTextSecondary: { color: Colors.text.secondary },
});

const footerKinds = StyleSheet.create({
  primary: { backgroundColor: Colors.primary },
  destructive: { backgroundColor: Colors.severity.critical },
  secondary: { backgroundColor: Colors.bg.input, borderWidth: 1, borderColor: Colors.border.default },
});
