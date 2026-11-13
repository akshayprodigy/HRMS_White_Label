import { focusManager } from '@tanstack/react-query';
import { useEffect } from 'react';
import { AppState, type AppStateStatus } from 'react-native';

/**
 * react-query has no window focus in React Native: wire AppState so stale queries (attendance gate, lists, Home)
 * refetch when the app returns to the foreground. onlineManager is intentionally not wired: @react-native-community/netinfo
 * is not a dependency (the default always-online behaviour keeps requests flowing; ApiError status 0 drives the offline banner).
 */
export function useAppStateFocus() {
  useEffect(() => {
    const onChange = (s: AppStateStatus) => focusManager.setFocused(s === 'active');
    focusManager.setFocused(AppState.currentState === 'active');
    const sub = AppState.addEventListener('change', onChange);
    return () => sub.remove();
  }, []);
}
