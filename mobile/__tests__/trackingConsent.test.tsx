import { fireEvent, screen, waitFor } from '@testing-library/react-native';
import { Alert } from 'react-native';
import type MockAdapter from 'axios-mock-adapter';
import { ConsentScreen, CONSENT_POINTS } from '../src/features/tracking/ConsentScreen';
import type { MyStatus } from '../src/features/tracking/api';
import { renderWithProviders, setupApiMock, teardownApiMock } from '../test-utils';

jest.mock('../src/config/tenant', () => ({ getTenant: () => ({ ...require('../tenants/dev/tenant.json'), id: 'dev' }), getApiBaseUrl: () => 'http://test/api/v1' }));
jest.mock('react-native-safe-area-context', () => ({ useSafeAreaInsets: () => ({ top: 0, bottom: 0, left: 0, right: 0 }) }));
jest.mock('../src/auth/AuthProvider', () => ({ useAuth: () => ({ user: { id: 1, email: 'a@x.com' }, loading: false }), onBeforeLogout: () => () => undefined, onSessionCleared: () => () => undefined }));
jest.mock('react-native-maps', () => ({ __esModule: true, default: () => null, Marker: () => null, Polyline: () => null }));
const mockTracking: { perm: 'none' | 'foreground' | 'background'; [k: string]: any } = { // eslint-disable-line @typescript-eslint/no-explicit-any
  perm: 'foreground',
  order: [] as string[],
  getPermissionLevel: jest.fn(async () => mockTracking.perm),
  requestPermissions: jest.fn(async () => mockTracking.perm),
  stopTracking: jest.fn(async () => undefined),
  applyStatus: jest.fn(async () => ({ running: false, mode: null, reason: 'unknown' })),
  flushPings: jest.fn(async () => ({ stop: null })),
  getPingQueue: () => ({ setUser: jest.fn() }),
};
jest.mock('../src/features/tracking/tracking', () => ({
  getPermissionLevel: () => mockTracking.getPermissionLevel(),
  requestPermissions: () => mockTracking.requestPermissions(),
  stopTracking: (o: unknown) => mockTracking.stopTracking(o),
  applyStatus: () => mockTracking.applyStatus(),
  flushPings: () => mockTracking.flushPings(),
  getPingQueue: () => mockTracking.getPingQueue(),
  enforceWindowEnd: async () => false,
  beginRevoke: () => mockTracking.order.push('begin'),
  endRevoke: () => mockTracking.order.push('end'),
}));

const iso = (d: Date) => d.toISOString();
const win = () => {
  const now = Date.now();
  return { work_date: '2026-11-13', start: iso(new Date(now - 3_600_000)), end: iso(new Date(now + 3_600_000)), shift_start: iso(new Date(now - 1_800_000)), shift_end: iso(new Date(now + 1_800_000)), in_window: true };
};
const st = (over: Partial<MyStatus> = {}): MyStatus => ({ required: true, consented: false, consented_at: null, active: false, window: win(), interval_seconds: 300, distance_filter_m: 100, ...over });

let mock: MockAdapter;
beforeEach(() => {
  mock = setupApiMock();
  mockTracking.perm = 'foreground';
  mockTracking.order = [];
  jest.clearAllMocks();
});
afterEach(teardownApiMock);

/** Press the button of the last Alert by label. */
function pressAlert(spy: jest.SpyInstance, label: string) {
  const buttons = spy.mock.calls.at(-1)![2] as { text: string; onPress?: () => void }[];
  buttons.find((b) => b.text === label)!.onPress?.(); // cancel buttons have no handler
}

describe('ConsentScreen', () => {
  it('HR has not enabled it: says so, offers no consent and collects nothing', async () => {
    mock.onGet('/tracking/my-trail').reply(200, { user_id: 1, date: 'x', truncated: false, points: [] });
    mock.onGet('/tracking/my-status').reply(200, st({ required: false, window: null }));
    await renderWithProviders(<ConsentScreen />);
    expect(await screen.findByText(/Not turned on for your role/)).toBeTruthy();
    expect(screen.queryByTestId('tracking-agree')).toBeNull();
    expect(screen.queryByTestId('tracking-delete-data')).toBeNull();
  });

  it('shows every required consent point before the OS prompt', async () => {
    mock.onGet('/tracking/my-status').reply(200, st());
    await renderWithProviders(<ConsentScreen />);
    await screen.findByTestId('tracking-explainer');
    expect(CONSENT_POINTS).toHaveLength(5);
    expect(screen.getByText(/Only during your rostered shifts/)).toBeTruthy();
    expect(screen.getByText(/What is collected/)).toBeTruthy();
    expect(screen.getAllByText(/kept for 30 days/).length).toBeGreaterThan(0);
    expect(screen.getByText(/revoke consent at any time/)).toBeTruthy();
    expect(mockTracking.requestPermissions).not.toHaveBeenCalled();
  });

  it('"I agree" POSTs consent once (double tap guarded), then asks for permissions and re-checks', async () => {
    let consented = false;
    mock.onGet('/tracking/my-status').reply(() => [200, st({ consented, active: consented })]);
    mock.onPost('/tracking/consent').reply(() => new Promise((r) => setTimeout(() => { consented = true; r([200, { consented: true, consented_at: iso(new Date()) }]); }, 150)));
    await renderWithProviders(<ConsentScreen />);
    const btn = await screen.findByTestId('tracking-agree');
    await fireEvent.press(btn);
    await fireEvent.press(btn); // the first request is still in flight (slow reply): the second tap must not send another
    await waitFor(() => expect(screen.getByTestId('tracking-status').props.children).toMatch(/Consented/));
    expect(mock.history.post.filter((r) => r.url === '/tracking/consent')).toHaveLength(1);
    expect(mockTracking.requestPermissions).toHaveBeenCalledTimes(1);
    expect(mockTracking.applyStatus).toHaveBeenCalled();
  });

  it('shows a friendly error when consent fails and stays un-consented', async () => {
    mock.onGet('/tracking/my-status').reply(200, st());
    mock.onPost('/tracking/consent').reply(500);
    await renderWithProviders(<ConsentScreen />);
    await fireEvent.press(await screen.findByTestId('tracking-agree'));
    expect(await screen.findByTestId('tracking-msg-error')).toBeTruthy();
    expect(mockTracking.requestPermissions).not.toHaveBeenCalled();
    expect(screen.getByTestId('tracking-agree')).toBeTruthy();
  });

  it('consented + inside the window: sharing now; foreground-only permission is called out', async () => {
    mock.onGet('/tracking/my-status').reply(200, st({ consented: true, active: true }));
    await renderWithProviders(<ConsentScreen />);
    expect(await screen.findByText('Consented · sharing now')).toBeTruthy();
    await screen.findByTestId('tracking-perm-warning');
    expect(screen.getByText(/only while the app is open/)).toBeTruthy();
    expect(screen.getByTestId('tracking-allow-always')).toBeTruthy();
    // shift_start/end are UTC instants: shown as HH:MM wall clock, never a date fragment
    expect(screen.getByText(/^Shift (\d{2}:\d{2}|—) to (\d{2}:\d{2}|—) \(sharing/)).toBeTruthy();
    expect(screen.queryByText(/Shift 20\d\d-/)).toBeNull();
  });

  it('consented but no shift window: idle', async () => {
    mock.onGet('/tracking/my-status').reply(200, st({ consented: true, active: true, window: null }));
    await renderWithProviders(<ConsentScreen />);
    expect(await screen.findByText('Consented · idle')).toBeTruthy();
    expect(screen.getByTestId('tracking-why').props.children).toMatch(/no rostered shift/);
  });

  it('location permission off: warns and offers to allow / open settings', async () => {
    mockTracking.perm = 'none';
    mock.onGet('/tracking/my-status').reply(200, st({ consented: true, active: true }));
    await renderWithProviders(<ConsentScreen />);
    await screen.findByTestId('tracking-perm-warning');
    expect(screen.getByTestId('tracking-allow')).toBeTruthy();
    expect(screen.getByTestId('tracking-open-settings')).toBeTruthy();
    expect(screen.getByText('Consented · idle')).toBeTruthy();
  });

  it('revoke asks for confirmation, stops tracking locally first, then DELETEs consent', async () => {
    const spy = jest.spyOn(Alert, 'alert').mockImplementation(() => undefined);
    let consented = true;
    mock.onGet('/tracking/my-status').reply(() => [200, st({ consented, active: consented })]);
    mock.onDelete('/tracking/consent').reply(() => { consented = false; return [200, { consented: false, revoked: true }]; });
    await renderWithProviders(<ConsentScreen />);
    await fireEvent(await screen.findByTestId('tracking-switch'), 'valueChange', false);
    expect(mock.history.delete).toHaveLength(0); // nothing until confirmed
    pressAlert(spy, 'Revoke consent');
    await waitFor(() => expect(screen.getByTestId('tracking-agree')).toBeTruthy());
    expect(mockTracking.stopTracking).toHaveBeenCalledWith({ clear: true });
    expect(mock.history.delete.filter((r) => r.url === '/tracking/consent')).toHaveLength(1);
    expect(mockTracking.order).toEqual(['begin', 'end']);
    expect(mockTracking.applyStatus).toHaveBeenCalled(); // re-applied after the revoke settles
  });

  it('a failed revoke still ends the revoke window and re-applies the (still consented) status', async () => {
    const spy = jest.spyOn(Alert, 'alert').mockImplementation(() => undefined);
    mock.onGet('/tracking/my-status').reply(200, st({ consented: true, active: true }));
    mock.onDelete('/tracking/consent').reply(500);
    await renderWithProviders(<ConsentScreen />);
    await fireEvent(await screen.findByTestId('tracking-switch'), 'valueChange', false);
    pressAlert(spy, 'Revoke consent');
    expect(await screen.findByTestId('tracking-msg-error')).toBeTruthy();
    expect(mockTracking.order).toEqual(['begin', 'end']);
    expect(mockTracking.applyStatus).toHaveBeenCalled();
  });

  it('cancelling the revoke prompt changes nothing', async () => {
    const spy = jest.spyOn(Alert, 'alert').mockImplementation(() => undefined);
    mock.onGet('/tracking/my-status').reply(200, st({ consented: true, active: true }));
    await renderWithProviders(<ConsentScreen />);
    await fireEvent(await screen.findByTestId('tracking-switch'), 'valueChange', false);
    pressAlert(spy, 'Keep sharing');
    expect(mock.history.delete).toHaveLength(0);
    expect(mockTracking.stopTracking).not.toHaveBeenCalled();
  });

  it('delete my data confirms, calls DELETE /tracking/my-data and reports the count', async () => {
    const spy = jest.spyOn(Alert, 'alert').mockImplementation(() => undefined);
    mock.onGet('/tracking/my-status').reply(200, st({ consented: true, active: true }));
    mock.onDelete('/tracking/my-data').reply(200, { deleted: { pings: 12, alerts: 0 } });
    await renderWithProviders(<ConsentScreen />);
    await fireEvent.press(await screen.findByTestId('tracking-delete-data'));
    expect(mock.history.delete).toHaveLength(0);
    pressAlert(spy, 'Delete');
    expect(await screen.findByText('Deleted 12 location points.')).toBeTruthy();
    expect(mock.history.delete.filter((r) => r.url === '/tracking/my-data')).toHaveLength(1);
  });

  it('a failing status call shows an error with retry', async () => {
    mock.onGet('/tracking/my-status').replyOnce(500).onGet('/tracking/my-status').reply(200, st({ required: false, window: null }));
    await renderWithProviders(<ConsentScreen />);
    expect(await screen.findByTestId('tracking-error')).toBeTruthy();
    await fireEvent.press(screen.getByText('Try again'));
    expect(await screen.findByText(/Not turned on for your role/)).toBeTruthy();
  });
});
