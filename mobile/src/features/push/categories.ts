import * as Notifications from 'expo-notifications';
// Lint's import/namespace cannot see these enums through expo-notifications' re-exports (tsc can).
/* eslint-disable import/namespace */
import { Platform } from 'react-native';
import { CATEGORY_ACTIONS, type PushAction, type PushCategory } from './routing';

/** Must match backend push.py: emergency pushes are sent with channelId "emergency". */
export const EMERGENCY_CHANNEL_ID = 'emergency';
export const DEFAULT_CHANNEL_ID = 'default';

type Button = { title: string; opensAppToForeground: boolean; isDestructive?: boolean; isAuthenticationRequired?: boolean };
export const BUTTONS: Record<PushAction, Button> = {
  approve: { title: 'Approve', opensAppToForeground: false, isAuthenticationRequired: true },
  reject: { title: 'Reject', opensAppToForeground: false, isDestructive: true, isAuthenticationRequired: true },
  claim: { title: 'Claim shift', opensAppToForeground: false, isAuthenticationRequired: true },
  safe: { title: "I'm safe", opensAppToForeground: false },
  // Opens the app so the user can add a note in the broadcast screen (see routing.ts).
  need_help: { title: 'I need help', opensAppToForeground: true },
  acknowledge: { title: 'Acknowledge', opensAppToForeground: false },
};

export async function setupChannels(): Promise<void> {
  if (Platform.OS !== 'android') return;
  await Notifications.setNotificationChannelAsync(DEFAULT_CHANNEL_ID, { name: 'General', importance: Notifications.AndroidImportance.HIGH });
  await Notifications.setNotificationChannelAsync(EMERGENCY_CHANNEL_ID, {
    name: 'Emergency alerts',
    importance: Notifications.AndroidImportance.MAX,
    vibrationPattern: [0, 500, 250, 500],
    lockscreenVisibility: Notifications.AndroidNotificationVisibility.PUBLIC,
  });
}

export async function setupCategories(): Promise<void> {
  const cats = (Object.keys(CATEGORY_ACTIONS) as PushCategory[]).filter((c) => CATEGORY_ACTIONS[c].length > 0);
  await Promise.all(
    cats.map((c) =>
      Notifications.setNotificationCategoryAsync(
        c,
        CATEGORY_ACTIONS[c].map((a) => ({ identifier: a, buttonTitle: BUTTONS[a].title, options: {
          opensAppToForeground: BUTTONS[a].opensAppToForeground,
          isDestructive: BUTTONS[a].isDestructive,
          isAuthenticationRequired: BUTTONS[a].isAuthenticationRequired,
        } })),
      ),
    ),
  );
}
