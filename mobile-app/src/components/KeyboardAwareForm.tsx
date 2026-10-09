/**
 * Keeps form fields above the keyboard on iOS and Android.
 *
 * The overlap between the keyboard and the container is measured, not assumed: when the
 * system already resized the window (Android adjustResize) the overlap is 0 and nothing is
 * added; with edge-to-edge (no resize) the container gets that overlap as bottom padding,
 * so the scroll area ends at the top of the keyboard. Whenever the scroll area changes
 * size, the focused input is scrolled into view.
 */
import React, { RefObject, useCallback, useEffect, useRef, useState } from 'react';
import {
  Keyboard, NativeScrollEvent, NativeSyntheticEvent, Platform, ScrollView, ScrollViewProps,
  StyleProp, StyleSheet, TextInput, View, ViewStyle,
} from 'react-native';

import { Spacing } from '../constants/config';
import { useDialogStore } from './dialog';

/** How much of the container the keyboard covers (0 when the window was resized). */
export function keyboardOverlap(containerBottom: number, keyboardTop: number): number {
  return Math.max(0, Math.round(containerBottom - keyboardTop));
}

/**
 * Scroll distance that brings an input inside the visible frame with a margin: positive
 * scrolls down, negative scrolls up. A field taller than the frame keeps its top visible.
 */
export function revealDelta(
  input: { top: number; bottom: number },
  frame: { top: number; bottom: number },
  margin: number = Spacing.base,
): number {
  if (input.bottom + margin > frame.bottom) {
    return Math.max(0, Math.min(input.bottom + margin - frame.bottom, input.top - margin - frame.top));
  }
  if (input.top - margin < frame.top) return input.top - margin - frame.top;
  return 0;
}

/** Bottom padding that keeps `containerRef` clear of the keyboard. */
export function useKeyboardInset(containerRef: RefObject<View | null>): number {
  const [inset, setInset] = useState(0);
  useEffect(() => {
    const showEvent = Platform.OS === 'ios' ? 'keyboardWillShow' : 'keyboardDidShow';
    const hideEvent = Platform.OS === 'ios' ? 'keyboardWillHide' : 'keyboardDidHide';
    const show = Keyboard.addListener(showEvent, (event) => {
      const keyboardTop = event.endCoordinates.screenY;
      containerRef.current?.measureInWindow((_x, y, _width, height) => {
        setInset(keyboardOverlap(y + height, keyboardTop));
      });
    });
    const hide = Keyboard.addListener(hideEvent, () => setInset(0));
    return () => {
      show.remove();
      hide.remove();
    };
  }, [containerRef]);
  return inset;
}

interface FormScrollProps extends ScrollViewProps {
  /** Style of the frame around the scroll view (flex: 1 on screens, shrinkable in modals). */
  frameStyle?: StyleProp<ViewStyle>;
  /** Set inside an AppModal: only the topmost modal (or a screen with none open) reveals inputs. */
  modalId?: number;
}

/** Scroll view that brings the focused input into view whenever its frame changes size. */
export function FormScroll({ frameStyle, modalId, onScroll, children, ...scrollProps }: FormScrollProps) {
  const frameRef = useRef<View>(null);
  const scrollRef = useRef<ScrollView>(null);
  const offset = useRef(0);

  const reveal = useCallback(() => {
    const stack = useDialogStore.getState().modalStack;
    const isActive = modalId === undefined ? stack.length === 0 : stack[stack.length - 1] === modalId;
    const input = TextInput.State.currentlyFocusedInput?.();
    const frame = frameRef.current;
    if (!isActive || !input || !frame) return;
    frame.measureInWindow((_fx, frameTop, _fw, frameHeight) => {
      input.measureInWindow((_ix, inputTop, _iw, inputHeight) => {
        const delta = revealDelta(
          { top: inputTop, bottom: inputTop + inputHeight },
          { top: frameTop, bottom: frameTop + frameHeight },
        );
        if (delta !== 0) scrollRef.current?.scrollTo({ y: Math.max(0, offset.current + delta), animated: true });
      });
    });
  }, [modalId]);

  const handleScroll = (event: NativeSyntheticEvent<NativeScrollEvent>) => {
    offset.current = event.nativeEvent.contentOffset.y;
    onScroll?.(event);
  };

  return (
    <View ref={frameRef} style={frameStyle} onLayout={reveal}>
      <ScrollView
        ref={scrollRef}
        keyboardShouldPersistTaps="handled"
        scrollEventThrottle={16}
        onScroll={handleScroll}
        {...scrollProps}
      >
        {children}
      </ScrollView>
    </View>
  );
}

/** Full-screen form: fills the screen and stays above the keyboard. */
export default function KeyboardAwareForm({ frameStyle, ...props }: FormScrollProps) {
  const containerRef = useRef<View>(null);
  const inset = useKeyboardInset(containerRef);
  return (
    <View ref={containerRef} style={[styles.fill, { paddingBottom: inset }]}>
      <FormScroll frameStyle={[styles.fill, frameStyle]} {...props} />
    </View>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
});
