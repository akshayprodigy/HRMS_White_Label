/**
 * Pure routing of a notification response (tap or action button) into what the app should do.
 * Contract: backend/app/services/push.py `data` payload. No expo imports so it is trivially unit-testable.
 */
export type PushCategory = 'approval' | 'open_shift' | 'broadcast_safety' | 'broadcast_ack' | 'none';
export type PushAction = 'approve' | 'reject' | 'claim' | 'safe' | 'need_help' | 'acknowledge';

export const CATEGORY_ACTIONS: Record<PushCategory, PushAction[]> = {
  approval: ['approve', 'reject'],
  open_shift: ['claim'],
  broadcast_safety: ['safe', 'need_help'],
  broadcast_ack: ['acknowledge'],
  none: [],
};

/** expo-notifications' DEFAULT_ACTION_IDENTIFIER (a plain tap); duplicated so this file stays dependency-free. */
export const DEFAULT_ACTION_ID = 'expo.modules.notifications.actions.DEFAULT';

/** Actions that must open the app instead of acting in the background (the user types a note there). */
const OPEN_APP_ACTIONS: ReadonlySet<string> = new Set(['need_help']);

export type PushData = {
  notification_id: number | null;
  /** Recipient (added by the backend later; null on older servers = no per-user check). */
  user_id: number | null;
  event_type: string | null;
  resource_type: string | null;
  resource_id: string | null;
  category: PushCategory;
};

export type RoutedResponse =
  | { kind: 'action'; notification_id: number; action: PushAction }
  | { kind: 'open'; href: string; refreshBroadcasts: boolean }
  | { kind: 'ignore' };

export type ResponseLike = {
  actionIdentifier?: string;
  notification?: { request?: { content?: { data?: unknown } } };
};

export function parsePushData(raw: unknown): PushData | null {
  if (!raw || typeof raw !== 'object') return null;
  const d = raw as Record<string, unknown>;
  const id = typeof d.notification_id === 'number' ? d.notification_id : typeof d.notification_id === 'string' && /^\d+$/.test(d.notification_id) ? Number(d.notification_id) : null;
  const uid = typeof d.user_id === 'number' ? d.user_id : typeof d.user_id === 'string' && /^\d+$/.test(d.user_id) ? Number(d.user_id) : null;
  const cat = typeof d.category === 'string' && d.category in CATEGORY_ACTIONS ? (d.category as PushCategory) : 'none';
  const str = (v: unknown) => (typeof v === 'string' && v ? v : typeof v === 'number' ? String(v) : null);
  return { notification_id: id, user_id: uid, event_type: str(d.event_type), resource_type: str(d.resource_type), resource_id: str(d.resource_id), category: cat };
}

export function hrefFor(data: PushData | null): string {
  if (!data) return '/home';
  if (data.category === 'approval' || data.resource_type === 'chained_approval_instance') {
    // Only chained instances share an id with the mobile approval key; legacy items (keyed by their own item id) go to the queue.
    if (data.resource_type === 'chained_approval_instance' && data.resource_id && /^\d+$/.test(data.resource_id)) return `/approval/chain-${data.resource_id}`;
    return '/approvals';
  }
  if (data.category === 'open_shift' || data.resource_type === 'open_shift') return '/schedule?section=open';
  return '/home'; // broadcasts surface as the root modal / Home banner
}

/**
 * `currentUserId` = who is signed in now. A notification addressed to someone else (shared device, A's tray entry tapped
 * after B signed in) must never act as B or deep-link into A's resource: taps land on /home, buttons are ignored.
 */
export function routeResponse(res: ResponseLike | null | undefined, currentUserId?: number | null): RoutedResponse {
  if (!res) return { kind: 'ignore' };
  const data = parsePushData(res.notification?.request?.content?.data);
  if (data && data.user_id != null && currentUserId != null && data.user_id !== currentUserId) {
    return (res.actionIdentifier ?? DEFAULT_ACTION_ID) === DEFAULT_ACTION_ID ? { kind: 'open', href: '/home', refreshBroadcasts: false } : { kind: 'ignore' };
  }
  const actionId = res.actionIdentifier ?? DEFAULT_ACTION_ID;
  const isBroadcast = data?.category === 'broadcast_safety' || data?.category === 'broadcast_ack' || data?.resource_type === 'broadcast';

  if (actionId === DEFAULT_ACTION_ID) {
    return { kind: 'open', href: hrefFor(data), refreshBroadcasts: isBroadcast };
  }
  if (!data || data.notification_id == null) return { kind: 'ignore' };
  // Only act on buttons this category actually offers (a stale/forged identifier must never hit the endpoint).
  if (!(CATEGORY_ACTIONS[data.category] as string[]).includes(actionId)) return { kind: 'ignore' };
  if (OPEN_APP_ACTIONS.has(actionId)) return { kind: 'open', href: hrefFor(data), refreshBroadcasts: isBroadcast };
  return { kind: 'action', notification_id: data.notification_id, action: actionId as PushAction };
}
