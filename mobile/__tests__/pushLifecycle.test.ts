import axios from 'axios';
import MockAdapter from 'axios-mock-adapter';
import { QueryClient } from '@tanstack/react-query';
import { setAdapter, setTokens } from '../src/api/client';
import { performNotificationAction, resetActionsForTests } from '../src/features/push/actions';
import { setupCategories, setupChannels } from '../src/features/push/categories';
import { getRegisteredToken, registerForPush, resetRegistrationForTests, unregisterPush } from '../src/features/push/registration';
import { GATE_BODY } from '../test-utils';

jest.mock('../src/config/tenant', () => ({ getTenant: () => ({ id: 'dev' }), getApiBaseUrl: () => 'http://test/api/v1' }));
let mockProjectId: string | undefined = 'proj-1';
jest.mock('expo-constants', () => ({ __esModule: true, default: { get expoConfig() { return { version: '1.2.3', extra: { eas: { projectId: mockProjectId } } }; } } }));
let mockIsDevice = true;
jest.mock('expo-device', () => ({ get isDevice() { return mockIsDevice; } }));
let mockOS = 'android';
jest.mock('react-native/Libraries/Utilities/Platform', () => ({ __esModule: true, default: { get OS() { return mockOS; }, select: (o: Record<string, unknown>) => o[mockOS] } }));
const mockN = {
  getPermissionsAsync: jest.fn(),
  requestPermissionsAsync: jest.fn(),
  getExpoPushTokenAsync: jest.fn(),
  setNotificationChannelAsync: jest.fn(async () => null),
  setNotificationCategoryAsync: jest.fn(async () => ({})),
  scheduleNotificationAsync: jest.fn(async () => 'id'),
  AndroidImportance: { HIGH: 4, MAX: 5 },
  AndroidNotificationVisibility: { PUBLIC: 1 },
};
jest.mock('expo-notifications', () => {
  // Lazy getters: the import is evaluated before `mockN` is initialised.
  const m: Record<string, unknown> = { __esModule: true };
  for (const k of ['getPermissionsAsync', 'requestPermissionsAsync', 'getExpoPushTokenAsync', 'setNotificationChannelAsync', 'setNotificationCategoryAsync', 'scheduleNotificationAsync', 'AndroidImportance', 'AndroidNotificationVisibility']) {
    Object.defineProperty(m, k, { enumerable: true, get: () => (mockN as Record<string, unknown>)[k] });
  }
  return m;
});
const mockAlert = jest.spyOn(require('react-native').Alert, 'alert');

const TOKEN = 'ExponentPushToken[abcdef123]';
let mock: MockAdapter;
beforeEach(() => {
  mock = new MockAdapter(axios);
  setAdapter(mock.adapter());
  setTokens({ accessToken: 't', refreshToken: 'r' });
  resetRegistrationForTests();
  resetActionsForTests();
  jest.clearAllMocks();
  mockProjectId = 'proj-1';
  mockIsDevice = true;
  mockOS = 'android';
  mockN.getPermissionsAsync.mockResolvedValue({ granted: true, canAskAgain: true });
  mockN.getExpoPushTokenAsync.mockResolvedValue({ data: TOKEN });
  mock.onPost('/devices').reply(200, {});
  jest.spyOn(console, 'warn').mockImplementation(() => undefined);
});
afterEach(() => {
  setAdapter(undefined);
  setTokens(null);
});

describe('registerForPush', () => {
  it('posts token, platform, version and tenant to /devices', async () => {
    expect(await registerForPush()).toBe(TOKEN);
    const req = mock.history.post.find((r) => r.url === '/devices')!;
    expect(JSON.parse(req.data)).toEqual({ token: TOKEN, platform: 'android', app_version: '1.2.3', tenant: 'dev' });
    expect(mockN.getExpoPushTokenAsync).toHaveBeenCalledWith({ projectId: 'proj-1' });
    expect(getRegisteredToken()).toBe(TOKEN);
  });
  it('creates the emergency channel at MAX importance and every action category before asking', async () => {
    await registerForPush();
    expect(mockN.setNotificationChannelAsync).toHaveBeenCalledWith('emergency', expect.objectContaining({ importance: 5 }));
    const ids = mockN.setNotificationCategoryAsync.mock.calls.map((c) => (c as unknown[])[0]).sort();
    expect(ids).toEqual(['approval', 'broadcast_ack', 'broadcast_safety', 'open_shift']);
  });
  it('skips gracefully without an EAS projectId (dev) and on simulators', async () => {
    mockProjectId = undefined;
    expect(await registerForPush()).toBeNull();
    mockProjectId = 'p';
    mockIsDevice = false;
    expect(await registerForPush()).toBeNull();
    expect(mock.history.post).toHaveLength(0);
  });
  it('shows the rationale before the OS prompt and respects "Not now"', async () => {
    mockN.getPermissionsAsync.mockResolvedValue({ granted: false, canAskAgain: true });
    mockAlert.mockImplementationOnce((_t, _m, buttons) => (buttons as { onPress?: () => void }[])[0].onPress?.());
    expect(await registerForPush()).toBeNull();
    expect(mockN.requestPermissionsAsync).not.toHaveBeenCalled();
    mockAlert.mockImplementationOnce((_t, _m, buttons) => (buttons as { onPress?: () => void }[])[1].onPress?.());
    mockN.requestPermissionsAsync.mockResolvedValue({ granted: true });
    expect(await registerForPush()).toBe(TOKEN);
  });
  it('does not prompt when permission was permanently denied', async () => {
    mockN.getPermissionsAsync.mockResolvedValue({ granted: false, canAskAgain: false });
    expect(await registerForPush()).toBeNull();
    expect(mockAlert).not.toHaveBeenCalled();
  });
  it('never throws when the server or token fetch fails', async () => {
    mock.onPost('/devices').reply(500);
    expect(await registerForPush()).toBeNull();
    expect(getRegisteredToken()).toBeNull();
  });
  it('is single-flight', async () => {
    await Promise.all([registerForPush(), registerForPush()]);
    expect(mock.history.post.filter((r) => r.url === '/devices')).toHaveLength(1);
  });
});

describe('unregisterPush', () => {
  it('DELETEs the encoded token with the session still attached, then forgets it', async () => {
    await registerForPush();
    mock.onDelete(`/devices/${encodeURIComponent(TOKEN)}`).reply(200, { revoked: true });
    await unregisterPush();
    expect(mock.history.delete).toHaveLength(1);
    expect(mock.history.delete[0].headers?.Authorization).toBe('Bearer t');
    expect(getRegisteredToken()).toBeNull();
  });
  it('is best-effort: a failing DELETE never throws; no token means no call', async () => {
    await unregisterPush();
    expect(mock.history.delete).toHaveLength(0);
    await registerForPush();
    mock.onDelete().networkError();
    await expect(unregisterPush()).resolves.toBeUndefined();
    expect(getRegisteredToken()).toBeNull();
  });
});

describe('categories', () => {
  it('registers background-capable buttons; need_help opens the app', async () => {
    await setupCategories();
    const call = (id: string) => (mockN.setNotificationCategoryAsync.mock.calls.find((c) => (c as unknown[])[0] === id) as unknown as [string, { identifier: string; options: { opensAppToForeground: boolean } }[]])[1];
    expect(call('approval').map((a) => a.identifier)).toEqual(['approve', 'reject']);
    expect(call('broadcast_safety').find((a) => a.identifier === 'need_help')!.options.opensAppToForeground).toBe(true);
    expect(call('broadcast_safety').find((a) => a.identifier === 'safe')!.options.opensAppToForeground).toBe(false);
  });
  it('channels are Android-only', async () => {
    mockOS = 'ios';
    await setupChannels();
    expect(mockN.setNotificationChannelAsync).not.toHaveBeenCalled();
  });
});

describe('performNotificationAction', () => {
  const qc = () => new QueryClient();
  it('POSTs /notifications/actions and refreshes related queries', async () => {
    mock.onPost('/notifications/actions').reply(200, { ok: 1 });
    const c = qc();
    const spy = jest.spyOn(c, 'invalidateQueries');
    expect(await performNotificationAction(c, 5, 'approve')).toBe(true);
    expect(JSON.parse(mock.history.post.find((r) => r.url === '/notifications/actions')!.data)).toEqual({ notification_id: 5, action: 'approve' });
    expect(spy).toHaveBeenCalled();
  });
  it('de-duplicates a re-delivered response', async () => {
    mock.onPost('/notifications/actions').reply(200, {});
    await performNotificationAction(qc(), 5, 'approve');
    await performNotificationAction(qc(), 5, 'approve');
    expect(mock.history.post.filter((r) => r.url === '/notifications/actions')).toHaveLength(1);
  });
  it('tells the user via a local notification when the attendance gate blocks it, and allows retry', async () => {
    mock.onPost('/notifications/actions').replyOnce(403, GATE_BODY).onPost('/notifications/actions').reply(200, {});
    expect(await performNotificationAction(qc(), 5, 'claim')).toBe(false);
    expect(mockN.scheduleNotificationAsync).toHaveBeenCalledWith(expect.objectContaining({ content: expect.objectContaining({ body: expect.stringMatching(/Punch in/) }) }));
    expect(await performNotificationAction(qc(), 5, 'claim')).toBe(true);
  });
});
