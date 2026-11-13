import { act, fireEvent, screen, waitFor } from '@testing-library/react-native';
import type MockAdapter from 'axios-mock-adapter';
import { PunchScreen } from '../src/features/punch/PunchScreen';
import { PunchQueue } from '../src/features/punch/queue';
import { setPunchQueue } from '../src/features/punch/api';
import { memorySelfieFiles, memoryStore } from '../src/features/punch/store';
import { renderWithProviders, setupApiMock, teardownApiMock } from '../test-utils';

jest.mock('../src/config/tenant', () => ({ getTenant: () => ({ ...require('../tenants/dev/tenant.json'), id: 'dev' }), getApiBaseUrl: () => 'http://test/api/v1' }));
jest.mock('react-native-safe-area-context', () => ({ useSafeAreaInsets: () => ({ top: 0, bottom: 0, left: 0, right: 0 }) }));
jest.mock('expo-router', () => ({ useRouter: () => ({ navigate: jest.fn() }) }));
jest.mock('../src/auth/AuthProvider', () => ({ useAuth: () => ({ user: { id: 1, email: 'e@x.com' } }) }));
jest.mock('expo-file-system', () => ({ File: class {}, Directory: class {}, Paths: {} }));
jest.mock('expo-image-manipulator', () => ({ manipulateAsync: jest.fn(), SaveFormat: { JPEG: 'jpeg' } }));
jest.mock('expo-crypto', () => ({ randomUUID: () => 'uuid-test-0001' }));
jest.mock('expo-camera', () => ({ CameraView: 'CameraView', useCameraPermissions: () => [{ granted: true }, jest.fn()] }));
const mockSelfie = jest.fn();
jest.mock('../src/features/punch/SelfieCapture', () => {
  const { Pressable, Text } = require('react-native');
  return { SelfieCapture: ({ onDone }: { onDone: (s: unknown) => void }) => <Pressable testID="selfie-stub" onPress={() => onDone(mockSelfie())}><Text>selfie</Text></Pressable> };
});
const mockLoc = { granted: true, canAskAgain: true, status: 'granted' };
jest.mock('expo-location', () => ({
  Accuracy: { High: 4 },
  getForegroundPermissionsAsync: jest.fn(async () => mockLoc),
  requestForegroundPermissionsAsync: jest.fn(async () => mockLoc),
  getCurrentPositionAsync: jest.fn(async () => ({ coords: { latitude: 12.97, longitude: 77.59, accuracy: 8 }, mocked: true })),
}));

const mkQ = (...a: ConstructorParameters<typeof PunchQueue>) => { const q = new PunchQueue(...a); q.setUser(1); return q; };
let mock: MockAdapter;
beforeEach(() => {
  mock = setupApiMock();
  setPunchQueue(mkQ(memoryStore(), memorySelfieFiles()));
  mockSelfie.mockReturnValue(null);
  mock.onGet('/dashboard/pending-count').reply(200, { count: 0 });
  mock.onGet('/roster/my/running-late').reply(200, { notice: null, can_post: false });
});
afterEach(async () => { await teardownApiMock(); setPunchQueue(null); });

describe('PunchScreen', () => {
  it('shows position, accuracy and mock warning, punches in and refreshes the gate queries', async () => {
    let marked = false;
    mock.onGet('/attendance/today').reply(() => [200, marked ? { is_marked: true, attendance: { id: 1, captured_at: '2026-11-13T09:00:00Z', punch_out_time: null } } : { is_marked: false, attendance: null }]);
    mock.onPost('/attendance/mark').reply(() => { marked = true; return [200, { id: 1, captured_at: '2026-11-13T09:00:00Z', punch_out_time: null }]; });
    await renderWithProviders(<PunchScreen />);
    await screen.findByTestId('loc-fix');
    expect(screen.getByTestId('loc-accuracy')).toHaveTextContent(/±8 m/);
    expect(screen.getByTestId('mock-warning')).toBeTruthy();
    await waitFor(() => expect(screen.getByTestId('punch-button')).toHaveTextContent('Punch in'));
    await fireEvent.press(screen.getByTestId('punch-button'));
    await fireEvent.press(await screen.findByTestId('selfie-stub'));
    await screen.findByTestId('punch-result');
    await waitFor(() => expect(screen.getByTestId('punch-button')).toHaveTextContent('Punch out'));
    expect(mock.history.get.filter((r) => r.url === '/dashboard/pending-count').length).toBeGreaterThan(1);
    expect(JSON.parse(mock.history.post[0].data)).toMatchObject({ mode: 'mobile', is_mock_location: true });
  });

  it('shows the geofence rejection message and code', async () => {
    mock.onGet('/attendance/today').reply(200, { is_marked: false, attendance: null });
    mock.onPost('/attendance/mark').reply(422, { detail: { error: 'OUTSIDE_GEOFENCE', message: 'You are 420 m from Head Office.' } });
    await renderWithProviders(<PunchScreen />);
    await waitFor(() => expect(screen.getByTestId('punch-button')).not.toBeDisabled());
    await fireEvent.press(screen.getByTestId('punch-button'));
    await fireEvent.press(await screen.findByTestId('selfie-stub'));
    expect(await screen.findByTestId('punch-error-message')).toHaveTextContent('You are 420 m from Head Office.');
    expect(screen.getByTestId('punch-error-code')).toHaveTextContent('OUTSIDE_GEOFENCE');
  });

  it('queues on network failure and shows Pending sync (1)', async () => {
    mock.onGet('/attendance/today').reply(200, { is_marked: false, attendance: null });
    mock.onPost('/attendance/mark').networkError();
    mock.onPost('/attendance/offline-sync').networkError(); // network is down for the sync too, so the punch stays pending
    await renderWithProviders(<PunchScreen />);
    await waitFor(() => expect(screen.getByTestId('punch-button')).not.toBeDisabled());
    await fireEvent.press(screen.getByTestId('punch-button'));
    await fireEvent.press(await screen.findByTestId('selfie-stub'));
    await screen.findByTestId('punch-queued');
    expect(await screen.findByTestId('pending-sync-title')).toHaveTextContent('Pending sync (1)');
  });

  it('offers punch out when already punched in', async () => {
    mock.onGet('/attendance/today').reply(200, { is_marked: true, attendance: { id: 1, captured_at: '2026-11-13T09:00:00Z', punch_out_time: null } });
    await renderWithProviders(<PunchScreen />);
    await waitFor(() => expect(screen.getByTestId('punch-button')).toHaveTextContent('Punch out'));
  });

  it('shows running-late only when postable, and posts minutes_late', async () => {
    mock.onGet('/attendance/today').reply(200, { is_marked: false, attendance: null });
    mock.onGet('/roster/my/running-late').reply(200, { notice: null, can_post: true, shift_start: '2026-11-13T00:00:00+00:00' });
    mock.onPost('/roster/my/running-late').reply(200, {});
    await renderWithProviders(<PunchScreen />);
    await fireEvent.press(await screen.findByTestId('late-30'));
    await fireEvent.press(screen.getByTestId('running-late-submit'));
    await waitFor(() => expect(mock.history.post.length).toBe(1));
    expect(JSON.parse(mock.history.post[0].data)).toEqual({ minutes_late: 30 });
  });

  it('explains a denied location permission', async () => {
    Object.assign(mockLoc, { granted: false, canAskAgain: true, status: 'denied' });
    mock.onGet('/attendance/today').reply(200, { is_marked: false, attendance: null });
    await renderWithProviders(<PunchScreen />);
    expect(await screen.findByTestId('loc-denied')).toBeTruthy();
    Object.assign(mockLoc, { granted: true, status: 'granted' });
  });

  it('shows pending-sync state: a queued in makes the next action Punch out; queued out is done', async () => {
    mock.onGet('/attendance/today').reply(200, { is_marked: false, attendance: null });
    const q = mkQ(memoryStore(), memorySelfieFiles());
    setPunchQueue(q);
    const base = { latitude: null, longitude: null, accuracy: null, is_mock_location: false, liveness_passed: null, liveness_score: null };
    await q.enqueue({ ...base, client_uuid: 'uuid-in-0001', kind: 'in', captured_at: new Date().toISOString() });
    await renderWithProviders(<PunchScreen />);
    await waitFor(() => expect(screen.getByTestId('punch-button')).toHaveTextContent('Punch out'));
    expect(screen.getByTestId('punch-tab-status')).toHaveTextContent('Punched in (pending sync)');
    await act(async () => { await q.enqueue({ ...base, client_uuid: 'uuid-out-001', kind: 'out', captured_at: new Date(Date.now() + 1000).toISOString() }); });
    await screen.findByTestId('punch-done');
    expect(screen.queryByTestId('punch-button')).toBeNull();
  });

  it('warns that a punch without location will be flagged', async () => {
    Object.assign(mockLoc, { granted: false, canAskAgain: true, status: 'denied' });
    mock.onGet('/attendance/today').reply(200, { is_marked: false, attendance: null });
    await renderWithProviders(<PunchScreen />);
    expect(await screen.findByTestId('no-location-warning')).toBeTruthy();
    Object.assign(mockLoc, { granted: true, status: 'granted' });
  });
});
