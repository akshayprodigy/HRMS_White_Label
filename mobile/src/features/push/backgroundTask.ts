import { QueryClient } from '@tanstack/react-query';
import * as Notifications from 'expo-notifications';
import * as TaskManager from 'expo-task-manager';
import { Platform } from 'react-native';
import { getTokens, setTokens } from '../../api/client';
import { tokenStorage } from '../../auth/tokenStorage';
import { performNotificationAction } from './actions';
import { parsePushData, routeResponse, type ResponseLike } from './routing';

export const BACKGROUND_NOTIFICATION_TASK = 'hrms-background-notification-task';

/**
 * Headless handler (Android): runs with NO React tree, possibly in a killed app, when an action button with
 * opensAppToForeground:false is tapped. Loads the stored session into the API client (its 401 refresh path then works
 * as usual) and posts the action. Plain pushes (no actionIdentifier) and non-action responses are ignored here.
 * Dedupe against the foreground listener is shared through performNotificationAction's per-(notification, action) set.
 */
export async function handleBackgroundPayload(payload: unknown): Promise<void> {
  if (!payload || typeof payload !== 'object' || !('actionIdentifier' in payload)) return;
  // Pure parse first (no storage); the signed-in user is only needed to reject notifications meant for someone else.
  if (routeResponse(payload as ResponseLike).kind !== 'action') return; // taps / need_help are handled when the app opens
  if (!getTokens()) {
    const stored = await tokenStorage.load().catch(() => null);
    if (!stored) return; // signed out: nothing to act as
    setTokens(stored);
  }
  const me = await tokenStorage.loadMe<{ id?: number }>();
  const myId = typeof me?.id === 'number' ? me.id : null;
  // A user-addressed push with no stored profile cannot be verified: ignore rather than fail open.
  if (myId == null && parsePushData((payload as ResponseLike).notification?.request?.content?.data)?.user_id != null) return;
  const routed = routeResponse(payload as ResponseLike, myId);
  if (routed.kind !== 'action') return; // addressed to a different user
  await performNotificationAction(new QueryClient(), routed.notification_id, routed.action);
}

// Must run at JS startup (imported from index.js), never inside a component.
TaskManager.defineTask(BACKGROUND_NOTIFICATION_TASK, async ({ data, error }) => {
  if (error) return;
  try {
    await handleBackgroundPayload(data);
  } catch (e) {
    console.warn('[push] background action failed', e instanceof Error ? e.message : e);
  }
});

export async function registerBackgroundTask(): Promise<void> {
  if (Platform.OS !== 'android') return; // iOS cannot run JS for a button tap on a killed app (buttons open the app there)
  try {
    await Notifications.registerTaskAsync(BACKGROUND_NOTIFICATION_TASK);
  } catch (e) {
    console.warn('[push] could not register background task', e instanceof Error ? e.message : e);
  }
}
