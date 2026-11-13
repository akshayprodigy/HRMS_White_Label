import type { QueryClient } from '@tanstack/react-query';
import * as Notifications from 'expo-notifications';
import { api, normalizeError } from '../../api/client';
import { APPROVALS_KEY } from '../approvals/api';
import { isGateError, PENDING_COUNT_KEY } from '../attendance/gate';
import { BROADCASTS_KEY } from '../broadcast/api';
import type { PushAction } from './routing';

const seen = new Set<string>();

export function refreshAfterPush(qc: QueryClient) {
  for (const key of [APPROVALS_KEY, PENDING_COUNT_KEY, ['schedule'], BROADCASTS_KEY]) void qc.invalidateQueries({ queryKey: key });
}

/** POST /notifications/actions. Idempotent per (notification, action) within a session: a re-delivered response is a no-op. */
export async function performNotificationAction(qc: QueryClient, notificationId: number, action: PushAction): Promise<boolean> {
  const k = `${notificationId}:${action}`;
  if (seen.has(k)) return true;
  seen.add(k);
  try {
    await api.post('/notifications/actions', { notification_id: notificationId, action });
    return true;
  } catch (e) {
    seen.delete(k); // allow a retry from a fresh tap
    const err = normalizeError(e);
    const body = isGateError(err) ? 'Punch in first, then try again from the app.' : err.status === 0 ? 'No connection. Open the app to try again.' : err.status === 404 ? 'This notification is no longer available.' : err.message;
    // Nothing visible happened in the background, so tell the user the action did not go through.
    await Notifications.scheduleNotificationAsync({ content: { title: "Couldn't complete that action", body, data: { category: 'none' } }, trigger: null }).catch(() => undefined);
    return false;
  } finally {
    refreshAfterPush(qc);
  }
}

export function resetActionsForTests() {
  seen.clear();
}
