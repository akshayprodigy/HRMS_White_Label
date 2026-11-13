import { screen, waitFor, fireEvent } from '@testing-library/react-native';
import type MockAdapter from 'axios-mock-adapter';
import { HomeScreen } from '../src/features/home/HomeScreen';
import { GATE_BODY, renderWithProviders, setupApiMock, teardownApiMock } from '../test-utils';

jest.mock('../src/config/tenant', () => ({
  getTenant: () => ({ ...require('../tenants/dev/tenant.json'), id: 'dev' }),
  getApiBaseUrl: () => 'http://test/api/v1',
}));
jest.mock('react-native-safe-area-context', () => ({ useSafeAreaInsets: () => ({ top: 0, bottom: 0, left: 0, right: 0 }) }));
const mockNavigate = jest.fn();
jest.mock('expo-router', () => ({ useRouter: () => ({ navigate: mockNavigate, push: jest.fn(), back: jest.fn(), replace: jest.fn() }) }));
let mockAuth: { user: object | null; unverified: boolean } = { user: { id: 1, email: 'e@x.com', full_name: 'Emp One' }, unverified: false };
jest.mock('../src/auth/AuthProvider', () => ({ useAuth: () => mockAuth }));

let mock: MockAdapter;
beforeEach(() => {
  mock = setupApiMock();
  mockAuth = { user: { id: 1, email: 'e@x.com', full_name: 'Emp One' }, unverified: false };
  mockNavigate.mockClear();
  mock.onGet('/broadcasts/my').reply(200, []);
  mock.onGet('/approval-chains/my-queue').reply(200, []);
  mock.onGet('/approvals/inbox').reply(200, []);
});
afterEach(teardownApiMock);

const week = { start: '2026-11-09', days: [
  { date: '2026-11-12', is_today: false, holiday_name: null, on_leave: false, leave_type: null, shift: { name: 'Early', start_time: '03:00', end_time: '11:00', is_overnight: false, source: 'roster' } },
  { date: '2026-11-13', is_today: true, holiday_name: null, on_leave: false, leave_type: null, shift: { name: 'Morning', start_time: '09:30', end_time: '18:00', is_overnight: false, source: 'roster', transport_required: true } },
] };

describe('HomeScreen', () => {
  it('renders today shift (UTC labelled), punch status, pending count and broadcast banner', async () => {
    mock.onGet('/attendance/today').reply(200, { is_marked: true, attendance: { id: 1, captured_at: '2026-11-13T09:41:00', punch_out_time: null } });
    mock.onGet('/roster/my/week').reply(200, week);
    mock.onGet('/dashboard/pending-count').reply(200, { count: 3 });
    mock.onGet('/broadcasts/my').reply(200, [{ id: 9, title: 'Fire drill', message: 'Assemble at gate', severity: 'warning', requires_ack: true, safety_check: false, created_at: null, pending: true }]);
    await renderWithProviders(<HomeScreen />);
    await waitFor(() => expect(screen.getByTestId('shift-name').props.children).toBe('Morning'));
    expect(screen.getByText('09:30 UTC – 18:00 UTC')).toBeTruthy();
    expect(screen.getByTestId('punch-status').props.children.join('')).toBe('Punched in at 09:41 UTC');
    await waitFor(() => expect(screen.getByText('3 pending requests')).toBeTruthy());
    expect(screen.getByTestId('broadcast-banner')).toBeTruthy();
    expect(screen.getByText('Fire drill')).toBeTruthy();
    expect(screen.queryByTestId('gate-notice')).toBeNull();
  });

  it('shows the punch-in gate notice (and does not call gated endpoints) when not punched in', async () => {
    mock.onGet('/attendance/today').reply(200, { is_marked: false, attendance: null });
    await renderWithProviders(<HomeScreen />);
    await waitFor(() => expect(screen.getByTestId('gate-notice')).toBeTruthy());
    expect(screen.getByText('Punch in to see this')).toBeTruthy();
    await fireEvent.press(screen.getByTestId('gate-notice-punch'));
    expect(mockNavigate).toHaveBeenCalledWith('/punch');
    expect(mock.history.get.some((r) => r.url === '/roster/my/week')).toBe(false);
  });

  it('handles a 403 ATTENDANCE_REQUIRED from a gated endpoint (superuser-looking state, server disagrees)', async () => {
    mock.onGet('/attendance/today').reply(200, { is_marked: true, attendance: null });
    mock.onGet('/roster/my/week').reply(403, GATE_BODY);
    mock.onGet('/dashboard/pending-count').reply(403, GATE_BODY);
    await renderWithProviders(<HomeScreen />);
    await waitFor(() => expect(screen.getByTestId('gate-notice')).toBeTruthy());
  });

  it('shows an offline banner for an unverified session', async () => {
    mockAuth = { ...mockAuth, unverified: true };
    mock.onGet('/attendance/today').networkError();
    mock.onGet('/roster/my/week').networkError();
    mock.onGet('/dashboard/pending-count').networkError();
    await renderWithProviders(<HomeScreen />);
    expect(screen.getByTestId('offline-banner')).toBeTruthy();
  });
});
