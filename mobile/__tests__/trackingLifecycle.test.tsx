import { act } from '@testing-library/react-native';
import type MockAdapter from 'axios-mock-adapter';
import type { MyStatus } from '../src/features/tracking/api';
import { useTrackingLifecycle } from '../src/features/tracking/hooks';
import { renderWithProviders, setupApiMock, teardownApiMock } from '../test-utils';

jest.mock('../src/config/tenant', () => ({ getTenant: () => ({ ...require('../tenants/dev/tenant.json'), id: 'dev' }), getApiBaseUrl: () => 'http://test/api/v1' }));
const mockAuth: { user: { id: number } | null; loading: boolean } = { user: { id: 1 }, loading: false };
const logoutHooks: (() => Promise<void> | void)[] = [];
jest.mock('../src/auth/AuthProvider', () => ({
  useAuth: () => mockAuth,
  onBeforeLogout: (fn: () => Promise<void> | void) => { logoutHooks.push(fn); return () => undefined; },
}));
const mockT = { applyStatus: jest.fn(async () => ({ running: true })), stopTracking: jest.fn(async () => undefined), flushPings: jest.fn(async () => ({ stop: null })), setUser: jest.fn() };
jest.mock('../src/features/tracking/tracking', () => ({
  applyStatus: (...a: unknown[]) => mockT.applyStatus(...(a as [])),
  stopTracking: (o: unknown) => (mockT.stopTracking as (o: unknown) => Promise<void>)(o),
  flushPings: () => mockT.flushPings(),
  getPingQueue: () => ({ setUser: mockT.setUser }),
}));

const status: MyStatus = { required: true, consented: true, consented_at: null, active: true, window: null, interval_seconds: 300, distance_filter_m: 100 };
let mock: MockAdapter;
function Harness() { useTrackingLifecycle(); return null; }
beforeEach(() => { mock = setupApiMock(); jest.clearAllMocks(); logoutHooks.length = 0; mockAuth.user = { id: 1 }; mockAuth.loading = false; });
afterEach(teardownApiMock);

describe('useTrackingLifecycle', () => {
  it('on sign-in fetches my-status, applies it for that user and flushes the queue', async () => {
    mock.onGet('/tracking/my-status').reply(200, status);
    await renderWithProviders(<Harness />);
    await act(async () => { await new Promise((r) => setTimeout(r, 20)); });
    expect(mockT.applyStatus).toHaveBeenCalledWith(expect.objectContaining({ required: true }), 1);
    expect(mockT.setUser).toHaveBeenCalledWith(1);
    expect(mockT.flushPings).toHaveBeenCalled();
  });
  it('does not treat the session-restore phase as a sign-out', async () => {
    mockAuth.user = null;
    mockAuth.loading = true;
    await renderWithProviders(<Harness />);
    expect(mockT.stopTracking).not.toHaveBeenCalled();
    expect(mockT.applyStatus).not.toHaveBeenCalled();
  });
  it('signed out: stops tracking and erases queued locations', async () => {
    mockAuth.user = null;
    await renderWithProviders(<Harness />);
    expect(mockT.stopTracking).toHaveBeenCalledWith({ clear: true });
  });
  it('registers a before-logout hook that stops and erases', async () => {
    mock.onGet('/tracking/my-status').reply(200, status);
    await renderWithProviders(<Harness />);
    expect(logoutHooks).toHaveLength(1);
    await logoutHooks[0]();
    expect(mockT.stopTracking).toHaveBeenCalledWith({ clear: true });
  });
  it('offline with no cached status: leaves tracking as it is', async () => {
    mock.onGet('/tracking/my-status').networkError();
    await renderWithProviders(<Harness />);
    await act(async () => { await new Promise((r) => setTimeout(r, 20)); });
    expect(mockT.applyStatus).not.toHaveBeenCalled();
  });
});
