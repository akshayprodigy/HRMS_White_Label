import { useRef } from 'react';

/**
 * Remembers the element that had focus when the dialog mounted (the trigger
 * button) and returns focus to it when the dialog closes. Spread the returned
 * handler onto <DialogContent onCloseAutoFocus=...>.
 */
export const useRestoreFocus = () => {
  const ref = useRef<HTMLElement | null>(null);
  if (ref.current === null && typeof document !== 'undefined') {
    const el = document.activeElement;
    if (el instanceof HTMLElement && el !== document.body) ref.current = el;
  }
  return (e: Event) => {
    const el = ref.current;
    if (el && el.isConnected) {
      e.preventDefault();
      el.focus();
    }
  };
};

/**
 * For dialogs that are always mounted and opened by state (no Radix trigger):
 * call `capture()` in the opener to remember the focused element, spread
 * `onCloseAutoFocus` on <DialogContent> to return focus to it on close.
 */
export const useReturnFocus = () => {
  const ref = useRef<HTMLElement | null>(null);
  const capture = () => {
    const el = typeof document !== 'undefined' ? document.activeElement : null;
    ref.current = el instanceof HTMLElement && el !== document.body ? el : null;
  };
  const onCloseAutoFocus = (e: Event) => {
    const el = ref.current;
    if (el && el.isConnected) {
      e.preventDefault();
      el.focus();
    }
  };
  return { capture, onCloseAutoFocus };
};
