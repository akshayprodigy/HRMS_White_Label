import { useQueryClient } from '@tanstack/react-query';
import * as Notifications from 'expo-notifications';
import { useRootNavigationState, useRouter } from 'expo-router';
import { useEffect, useRef } from 'react';
import { onBeforeLogout, useAuth } from '../../auth/AuthProvider';
import { BROADCASTS_KEY } from '../broadcast/api';
import { performNotificationAction, refreshAfterPush } from './actions';
import { registerBackgroundTask } from './backgroundTask';
import { registerForPush, unregisterPush } from './registration';
import { parsePushData, routeResponse } from './routing';

/** Mounted once inside AuthProvider + QueryClientProvider: registration, token refresh, logout unregister, taps and actions. */
export function usePushLifecycle() {
  const { user } = useAuth();
  const qc = useQueryClient();
  const router = useRouter();
  const navReady = !!useRootNavigationState()?.key;
  const handled = useRef(new Set<string>());
  const userId = user?.id ?? null;

  // Foreground pushes show as a banner; the broadcast poll + modal handle the in-app side.
  useEffect(() => {
    Notifications.setNotificationHandler({
      handleNotification: async () => ({ shouldShowBanner: true, shouldShowList: true, shouldPlaySound: true, shouldSetBadge: false }),
    });
  }, []);

  useEffect(() => {
    void registerBackgroundTask();
  }, []);

  // Unregister BEFORE the tokens are cleared (AuthProvider runs these hooks first).
  useEffect(() => onBeforeLogout(unregisterPush), []);

  useEffect(() => {
    if (userId == null) return;
    void registerForPush();
    // The native token rotates occasionally; re-resolve the Expo token and re-post it.
    const sub = Notifications.addPushTokenListener(() => void registerForPush());
    return () => sub.remove();
  }, [userId]);

  // Pushes arriving in the foreground: pull broadcasts right away instead of waiting for the next poll.
  useEffect(() => {
    if (userId == null) return;
    const sub = Notifications.addNotificationReceivedListener((n) => {
      const d = parsePushData(n.request.content.data);
      if (d?.category === 'broadcast_safety' || d?.category === 'broadcast_ack' || d?.resource_type === 'broadcast') {
        void qc.invalidateQueries({ queryKey: BROADCASTS_KEY });
      }
    });
    return () => sub.remove();
  }, [userId, qc]);

  // Taps and action buttons. Gated on a signed-in user + ready navigation, so a cold-start response (delivered by
  // getLastNotificationResponse) waits until the session is restored and the router exists.
  useEffect(() => {
    if (userId == null || !navReady) return;
    const handle = (res: Notifications.NotificationResponse) => {
      const id = `${res.notification.request.identifier}:${res.actionIdentifier}:${res.notification.date}`;
      if (handled.current.has(id)) return;
      handled.current.add(id);
      const routed = routeResponse(res);
      if (routed.kind === 'action') {
        void performNotificationAction(qc, routed.notification_id, routed.action);
      } else if (routed.kind === 'open') {
        if (routed.refreshBroadcasts) void qc.invalidateQueries({ queryKey: BROADCASTS_KEY });
        refreshAfterPush(qc);
        router.navigate(routed.href as never);
      }
    };
    const sub = Notifications.addNotificationResponseReceivedListener(handle);
    const last = Notifications.getLastNotificationResponse();
    if (last) {
      handle(last);
      Notifications.clearLastNotificationResponse();
    }
    return () => sub.remove();
  }, [userId, navReady, qc, router]);
}
