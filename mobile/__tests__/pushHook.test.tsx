import { renderHook } from '@testing-library/react-native';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { usePushLifecycle } from '../src/features/push/usePushLifecycle';

jest.mock('expo-task-manager', () => ({ defineTask: jest.fn() }));
const mockPerform = jest.fn(async () => true);
const mockRegister = jest.fn(async () => null);
const mockClear = jest.fn();
const mockUnregister = jest.fn(async () => undefined);
jest.mock('../src/features/push/actions', () => ({ performNotificationAction: (...a: unknown[]) => (mockPerform as (...x: unknown[]) => unknown)(...a), refreshAfterPush: jest.fn() }));
jest.mock('../src/features/push/backgroundTask', () => ({ registerBackgroundTask: jest.fn(async () => undefined) }));
jest.mock('../src/features/push/registration', () => ({ registerForPush: () => mockRegister(), unregisterPush: () => mockUnregister(), clearNotificationState: () => mockClear() }));
let mockUser: { id: number } | null = { id: 1 };
const mockHooks: (() => unknown)[] = [];
jest.mock('../src/auth/AuthProvider', () => ({
  useAuth: () => ({ user: mockUser }),
  onBeforeLogout: (fn: () => unknown) => { mockHooks.push(fn); return () => undefined; },
}));
const mockNavigate = jest.fn();
let mockNavKey: string | undefined = 'k';
jest.mock('expo-router', () => ({ useRouter: () => ({ navigate: mockNavigate }), useRootNavigationState: () => ({ key: mockNavKey }) }));
let mockLast: unknown = null;
let responseCb: ((r: unknown) => void) | null = null;
const mockN = {
  setNotificationHandler: jest.fn(),
  addPushTokenListener: jest.fn(() => ({ remove: jest.fn() })),
  addNotificationReceivedListener: jest.fn(() => ({ remove: jest.fn() })),
  addNotificationResponseReceivedListener: jest.fn((cb: (r: unknown) => void) => { responseCb = cb; return { remove: jest.fn() }; }),
  getLastNotificationResponse: jest.fn(() => mockLast),
  clearLastNotificationResponse: jest.fn(),
};
jest.mock('expo-notifications', () => {
  const m: Record<string, unknown> = { __esModule: true };
  for (const k of ['setNotificationHandler', 'addPushTokenListener', 'addNotificationReceivedListener', 'addNotificationResponseReceivedListener', 'getLastNotificationResponse', 'clearLastNotificationResponse']) {
    Object.defineProperty(m, k, { enumerable: true, get: () => (mockN as Record<string, unknown>)[k] });
  }
  return m;
});

const response = (data: unknown, actionIdentifier: string, id = 'n1') => ({ actionIdentifier, notification: { date: 1, request: { identifier: id, content: { data } } } });
const DEF = 'expo.modules.notifications.actions.DEFAULT';
const wrap = ({ children }: { children: React.ReactNode }) => <QueryClientProvider client={new QueryClient()}>{children}</QueryClientProvider>;

beforeEach(() => {
  jest.clearAllMocks();
  mockUser = { id: 1 };
  mockNavKey = 'k';
  mockLast = null;
  responseCb = null;
  mockHooks.length = 0;
  mockN.addPushTokenListener.mockImplementation(() => ({ remove: jest.fn() }));
  mockN.addNotificationResponseReceivedListener.mockImplementation((cb: (r: unknown) => void) => { responseCb = cb; return { remove: jest.fn() }; });
  mockN.getLastNotificationResponse.mockImplementation(() => mockLast);
});

describe('usePushLifecycle: cross-user', () => {
  it("does not post or navigate for another user's notification", async () => {
    await renderHook(() => usePushLifecycle(), { wrapper: wrap });
    responseCb!(response({ notification_id: 5, user_id: 2, category: 'approval' }, 'approve', 'a1'));
    expect(mockPerform).not.toHaveBeenCalled();
    responseCb!(response({ notification_id: 6, user_id: 2, category: 'open_shift', resource_type: 'open_shift', resource_id: '3' }, DEF, 'a2'));
    expect(mockNavigate).toHaveBeenCalledTimes(1);
    expect(mockNavigate).toHaveBeenCalledWith('/home');
  });
  it('still acts when user_id matches', async () => {
    await renderHook(() => usePushLifecycle(), { wrapper: wrap });
    responseCb!(response({ notification_id: 5, user_id: 1, category: 'approval' }, 'approve', 'a3'));
    expect(mockPerform).toHaveBeenCalledWith(expect.anything(), 5, 'approve');
  });
});

describe('usePushLifecycle', () => {
  it('registers after login, subscribes to token rotation, and hooks unregister into logout', async () => {
    await renderHook(() => usePushLifecycle(), { wrapper: wrap });
    expect(mockRegister).toHaveBeenCalledTimes(1);
    expect(mockN.addPushTokenListener).toHaveBeenCalled();
    await mockHooks[0]();
    expect(mockUnregister).toHaveBeenCalled();
    expect(mockClear).toHaveBeenCalled();
  });
  it('does not register while signed out', async () => {
    mockUser = null;
    await renderHook(() => usePushLifecycle(), { wrapper: wrap });
    expect(mockRegister).not.toHaveBeenCalled();
    expect(mockN.addNotificationResponseReceivedListener).not.toHaveBeenCalled();
  });
  it('runs a cold-start action button response once the session exists, then clears it', async () => {
    mockLast = response({ notification_id: 5, category: 'approval' }, 'approve');
    await renderHook(() => usePushLifecycle(), { wrapper: wrap });
    expect(mockPerform).toHaveBeenCalledWith(expect.anything(), 5, 'approve');
    expect(mockN.clearLastNotificationResponse).toHaveBeenCalled();
  });
  it('waits for navigation to be ready before handling', async () => {
    mockNavKey = undefined;
    mockLast = response({ notification_id: 5, category: 'approval' }, DEF);
    await renderHook(() => usePushLifecycle(), { wrapper: wrap });
    expect(mockNavigate).not.toHaveBeenCalled();
  });
  it('deep-links on tap and de-duplicates the same response', async () => {
    await renderHook(() => usePushLifecycle(), { wrapper: wrap });
    const r = response({ notification_id: 6, category: 'open_shift', resource_type: 'open_shift', resource_id: '3' }, DEF, 'n6');
    responseCb!(r);
    responseCb!(r);
    expect(mockNavigate).toHaveBeenCalledTimes(1);
    expect(mockNavigate).toHaveBeenCalledWith('/schedule?section=open');
    expect(mockPerform).not.toHaveBeenCalled();
  });
  it('need_help opens the app instead of posting', async () => {
    await renderHook(() => usePushLifecycle(), { wrapper: wrap });
    responseCb!(response({ notification_id: 7, category: 'broadcast_safety', resource_type: 'broadcast', resource_id: '9' }, 'need_help', 'n7'));
    expect(mockPerform).not.toHaveBeenCalled();
    expect(mockNavigate).toHaveBeenCalledWith('/home');
  });
});
