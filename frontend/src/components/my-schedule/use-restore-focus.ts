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
