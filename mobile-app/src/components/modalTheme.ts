/**
 * One look for every popup: the scrim, the card and the title are shared by AppModal
 * (forms, pickers, previews) and the dialog (confirmations, choices, messages).
 */
import { StyleSheet } from 'react-native';

import { Colors, Radius, Spacing, Typography } from '../constants/config';

export const MODAL_ANIMATION = 'fade' as const;
export const MODAL_MAX_WIDTH = 520;

export const modalStyles = StyleSheet.create({
  scrim: {
    flex: 1,
    backgroundColor: Colors.overlay,
    alignItems: 'center',
    justifyContent: 'center',
    padding: Spacing.base,
  },
  card: {
    width: '100%',
    maxWidth: MODAL_MAX_WIDTH,
    maxHeight: '100%',
    flexShrink: 1,
    backgroundColor: Colors.bg.card,
    borderRadius: Radius.lg,
    borderWidth: 1,
    borderColor: Colors.border.default,
    overflow: 'hidden',
  },
  title: {
    fontSize: Typography.md,
    fontWeight: '700',
    color: Colors.text.primary,
  },
  subtitle: {
    fontSize: Typography.sm,
    color: Colors.text.secondary,
    marginTop: 2,
  },
});
