import axios from 'axios';
import MockAdapter from 'axios-mock-adapter';
import { QueryClient } from '@tanstack/react-query';
import { getTokens, setAdapter, setTokens } from '../src/api/client';
import { tokenStorage } from '../src/auth/tokenStorage';
import { performNotificationAction, resetActionsForTests } from '../src/features/push/actions';
import { BACKGROUND_NOTIFICATION_TASK, handleBackgroundPayload, registerBackgroundTask } from '../src/features/push/backgroundTask';
import { buttonOptions } from '../src/features/push/categories';
import { GATE_BODY } from '../test-utils';

jest.mock('../src/config/tenant', () => ({ getTenant: () => ({ id: 'dev' }), getApiBaseUrl: () => 'http://test/api/v1' }));
// defineTask runs at import time, before module-level consts exist: record on globalThis.
jest.mock('expo-task-manager', () => ({ defineTask: (...a: unknown[]) => ((globalThis as { __tasks?: unknown[][] }).__tasks ??= []).push(a) }));
const mockSchedule = jest.fn(async () => 'id');
const mockRegisterTask = jest.fn(async () => null);
jest.mock('expo-notifications', () => ({
  __esModule: true,
  scheduleNotificationAsync: (...a: unknown[]) => mockSchedule(...(a as [])),
  registerTaskAsync: (...a: unknown[]) => mockRegisterTask(...(a as [])),
}));
let mockOS = 'android';
jest.mock('react-native/Libraries/Utilities/Platform', () => ({ __esModule: true, default: { get OS() { return mockOS; }, select: (o: Record<string, unknown>) => o[mockOS] } }));

const DEF = 'expo.modules.notifications.actions.DEFAULT';
const resp = (data: unknown, actionIdentifier: string) => ({ actionIdentifier, notification: { request: { identifier: 'x', content: { data } } } });
const approval = { notification_id: 5, category: 'approval', resource_type: 'leave', resource_id: '1' };

let mock: MockAdapter;
const taskDefinedAtImport = (globalThis as { __tasks?: unknown[][] }).__tasks ?? [];
beforeEach(async () => {
  mock = new MockAdapter(axios);
  setAdapter(mock.adapter());
  setTokens(null);
  await tokenStorage.save({ accessToken: 'stored-a', refreshToken: 'stored-r' });
  await tokenStorage.saveMe({ id: 1 });
  resetActionsForTests();
  mockSchedule.mockClear();
  mockRegisterTask.mockClear();
  mockOS = 'android';
  mock.onPost('/notifications/actions').reply(200, {});
  jest.spyOn(console, 'warn').mockImplementation(() => undefined);
});
afterEach(() => {
  setAdapter(undefined);
  setTokens(null);
});

describe('headless task', () => {
  it('defines the task at module load (JS startup)', () => {
    expect(taskDefinedAtImport[0]?.[0]).toBe(BACKGROUND_NOTIFICATION_TASK);
  });
  it('action button: loads the stored session and POSTs with its token (no AuthProvider)', async () => {
    expect(getTokens()).toBeNull();
    await handleBackgroundPayload(resp(approval, 'approve'));
    const req = mock.history.post.find((r) => r.url === '/notifications/actions')!;
    expect(JSON.parse(req.data)).toEqual({ notification_id: 5, action: 'approve' });
    expect(req.headers?.Authorization).toBe('Bearer stored-a');
  });
  it('ignores plain pushes, taps, need_help and forged buttons', async () => {
    await handleBackgroundPayload({ notification: null, data: { dataString: '{}' } });
    await handleBackgroundPayload(resp(approval, DEF));
    await handleBackgroundPayload(resp({ notification_id: 7, category: 'broadcast_safety' }, 'need_help'));
    await handleBackgroundPayload(resp(approval, 'claim'));
    await handleBackgroundPayload(null);
    expect(mock.history.post).toHaveLength(0);
  });
  it("skips a notification addressed to a different user than the stored session", async () => {
    await handleBackgroundPayload(resp({ ...approval, user_id: 2 }, 'approve'));
    expect(mock.history.post).toHaveLength(0);
    await handleBackgroundPayload(resp({ ...approval, user_id: 1 }, 'approve'));
    expect(mock.history.post).toHaveLength(1);
  });
  it('ignores a user-addressed push when the stored profile is missing (no fail-open)', async () => {
    await tokenStorage.clear();
    await tokenStorage.save({ accessToken: 'a', refreshToken: 'r' }); // tokens without "me"
    await handleBackgroundPayload(resp({ ...approval, user_id: 1 }, 'approve'));
    expect(mock.history.post).toHaveLength(0);
    await handleBackgroundPayload(resp(approval, 'approve')); // older backend, no user_id: still acts
    expect(mock.history.post).toHaveLength(1);
  });
  it('does nothing when signed out (no stored session)', async () => {
    await tokenStorage.clear();
    await handleBackgroundPayload(resp(approval, 'approve'));
    expect(mock.history.post).toHaveLength(0);
  });
  it('failure surfaces a local notification (gate 403)', async () => {
    mock.onPost('/notifications/actions').reply(403, GATE_BODY);
    await handleBackgroundPayload(resp(approval, 'approve'));
    expect(mockSchedule).toHaveBeenCalledWith(expect.objectContaining({ content: expect.objectContaining({ body: expect.stringMatching(/Punch in/) }) }));
  });
  it('is deduped with the foreground listener path (same notification + action runs once)', async () => {
    await Promise.all([handleBackgroundPayload(resp(approval, 'approve')), performNotificationAction(new QueryClient(), 5, 'approve')]);
    await handleBackgroundPayload(resp(approval, 'approve'));
    expect(mock.history.post.filter((r) => r.url === '/notifications/actions')).toHaveLength(1);
  });
  it('registers the task on Android only', async () => {
    await registerBackgroundTask();
    expect(mockRegisterTask).toHaveBeenCalledWith(BACKGROUND_NOTIFICATION_TASK);
    mockRegisterTask.mockClear();
    mockOS = 'ios';
    await registerBackgroundTask();
    expect(mockRegisterTask).not.toHaveBeenCalled();
  });
});

describe('category button options per platform', () => {
  it('iOS: every button opens the app (killed-app taps cannot reach JS otherwise)', () => {
    for (const a of ['approve', 'reject', 'claim', 'safe', 'need_help', 'acknowledge'] as const) {
      expect(buttonOptions(a, 'ios').opensAppToForeground).toBe(true);
    }
  });
  it('Android: background except need_help', () => {
    for (const a of ['approve', 'reject', 'claim', 'safe', 'acknowledge'] as const) {
      expect(buttonOptions(a, 'android').opensAppToForeground).toBe(false);
    }
    expect(buttonOptions('need_help', 'android').opensAppToForeground).toBe(true);
  });
});
