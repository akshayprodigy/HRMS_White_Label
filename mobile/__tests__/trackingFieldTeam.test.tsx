import { fireEvent, screen, waitFor } from '@testing-library/react-native';
import type MockAdapter from 'axios-mock-adapter';
import { FieldTeamScreen } from '../src/features/tracking/FieldTeamScreen';
import type { FieldNow, FieldRow } from '../src/features/tracking/api';
import { renderWithProviders, setupApiMock, teardownApiMock } from '../test-utils';

jest.mock('../src/config/tenant', () => ({ getTenant: () => ({ ...require('../tenants/dev/tenant.json'), id: 'dev' }), getApiBaseUrl: () => 'http://test/api/v1' }));
jest.mock('react-native-safe-area-context', () => ({ useSafeAreaInsets: () => ({ top: 0, bottom: 0, left: 0, right: 0 }) }));
jest.mock('react-native-maps', () => {
  const React = require('react');
  const { View } = require('react-native');
  const MapView = React.forwardRef((p: { children?: unknown }, _r: unknown) => React.createElement(View, { testID: 'field-map' }, p.children));
  return { __esModule: true, default: MapView, Marker: (p: { testID: string }) => React.createElement(View, { testID: p.testID }), Polyline: (p: { coordinates: unknown[] }) => React.createElement(View, { testID: 'field-polyline', accessibilityLabel: String(p.coordinates.length) }) };
});
const mockMaps = { on: true };
jest.mock('../src/features/tracking/maps', () => ({ mapsAvailable: () => mockMaps.on }));

const ping = (min: number) => ({ captured_at: new Date(Date.now() - min * 60_000).toISOString(), lat: 12.9, lng: 77.6, accuracy: 10, speed: 0, battery: 80 });
const row = (id: number, over: Partial<FieldRow> = {}): FieldRow => ({ user_id: id, name: `Person ${id}`, department: 'Ops', status: 'on_shift', late_minutes: 0, shift_name: 'Day', start_hhmm: '09:00', end_hhmm: '18:00', ping: ping(2), ...over });
const board = (rows: FieldRow[]): FieldNow => ({ now: new Date().toISOString(), tracked: rows.length, with_location: rows.filter((r) => r.ping).length, rows });

let mock: MockAdapter;
beforeEach(() => { mock = setupApiMock(); mockMaps.on = true; });
afterEach(teardownApiMock);

describe('FieldTeamScreen', () => {
  it('403 (no roster scope) shows the not-available notice', async () => {
    mock.onGet('/tracking/field-now').reply(403, { detail: 'You have no roster scope.' });
    await renderWithProviders(<FieldTeamScreen />);
    expect(await screen.findByTestId('field-no-scope')).toBeTruthy();
    expect(mock.history.get.filter((r) => r.url !== '/meta/org-time')).toHaveLength(1); // not retried
  });

  it('lists tracked people (located first), shows markers and counts', async () => {
    mock.onGet('/tracking/field-now').reply(200, board([row(2, { name: 'Zed', ping: null }), row(1, { name: 'Amy' })]));
    await renderWithProviders(<FieldTeamScreen />);
    expect(await screen.findByTestId('field-counts')).toBeTruthy();
    expect(screen.getByText('2 tracked · 1 with recent location')).toBeTruthy();
    expect(screen.getByTestId('field-map')).toBeTruthy();
    expect(screen.getByTestId('field-marker-1')).toBeTruthy();
    expect(screen.queryByTestId('field-marker-2')).toBeNull();
    expect(screen.getByText('No recent location')).toBeTruthy();
    expect(screen.getByText(/Last seen 2 min ago · 80% battery/)).toBeTruthy();
  });

  it('falls back to the list (no crash) when the map is not available in this build', async () => {
    mockMaps.on = false;
    mock.onGet('/tracking/field-now').reply(200, board([row(1)]));
    await renderWithProviders(<FieldTeamScreen />);
    expect(await screen.findByTestId('field-no-map')).toBeTruthy();
    expect(screen.queryByTestId('field-map')).toBeNull();
    expect(screen.getByTestId('field-row-1')).toBeTruthy();
  });

  it('nobody tracked: explains that tracking is off by default', async () => {
    mock.onGet('/tracking/field-now').reply(200, board([]));
    await renderWithProviders(<FieldTeamScreen />);
    expect(await screen.findByTestId('field-empty')).toBeTruthy();
  });

  it('tapping a person loads their trail for today and draws a polyline', async () => {
    mock.onGet('/tracking/field-now').reply(200, board([row(1)]));
    mock.onGet('/tracking/trail').reply((cfg) => [200, { user_id: cfg.params.user_id, date: cfg.params.date, truncated: false, points: [ping(30), ping(20), ping(10)] }]);
    await renderWithProviders(<FieldTeamScreen />);
    await fireEvent.press(await screen.findByTestId('field-row-1'));
    expect(await screen.findByTestId('field-trail-summary')).toBeTruthy();
    expect(screen.getByText(/3 points from/)).toBeTruthy();
    expect(screen.getByTestId('field-polyline').props.accessibilityLabel).toBe('3');
    const req = mock.history.get.find((r) => r.url === '/tracking/trail')!;
    expect(req.params).toMatchObject({ user_id: 1, date: new Date().toISOString().slice(0, 10) });
  });

  it('shows the server message when a trail is refused (403) and an empty state for no points', async () => {
    mock.onGet('/tracking/field-now').reply(200, board([row(1), row(2)]));
    mock.onGet('/tracking/trail').reply((cfg) => cfg.params.user_id === 1
      ? [403, { detail: 'Location tracking is not active for this employee.' }]
      : [200, { user_id: 2, date: cfg.params.date, truncated: false, points: [] }]);
    await renderWithProviders(<FieldTeamScreen />);
    await fireEvent.press(await screen.findByTestId('field-row-1'));
    expect(await screen.findByText('Location tracking is not active for this employee.')).toBeTruthy();
    await fireEvent.press(screen.getByTestId('field-row-2'));
    expect(await screen.findByTestId('field-trail-empty')).toBeTruthy();
  });

  it('department chips refetch with the filter', async () => {
    mock.onGet('/tracking/field-now').reply((cfg) => [200, board(cfg.params?.department === 'Ops' ? [row(1)] : [row(1), row(3, { department: 'HR' })])]);
    await renderWithProviders(<FieldTeamScreen />);
    await fireEvent.press(await screen.findByTestId('field-dept-Ops'));
    await waitFor(() => expect(mock.history.get.some((r) => r.params?.department === 'Ops')).toBe(true));
    await waitFor(() => expect(screen.queryByTestId('field-row-3')).toBeNull());
  });
});

describe('useFieldTeamAccess', () => {
  const { QueryClient, QueryClientProvider } = require('@tanstack/react-query');
  const { render, cleanup } = require('@testing-library/react-native');
  const { Text } = require('react-native');
  const { useFieldTeamAccess } = require('../src/features/tracking/FieldTeamScreen');
  function Probe() { const { allowed } = useFieldTeamAccess(); return <Text testID="probe">{String(allowed)}</Text>; }
  const mount = async (client: unknown) => render(<QueryClientProvider client={client}><Probe /></QueryClientProvider>);

  it('remembers a 403 for the session: remounting does not ask again', async () => {
    mock.onGet('/tracking/field-now').reply(403, { detail: 'You have no roster scope.' });
    const client = new QueryClient({ defaultOptions: { queries: { gcTime: Infinity } } });
    await mount(client);
    await waitFor(() => expect(mock.history.get).toHaveLength(1));
    expect(screen.getByTestId('probe').props.children).toBe('false');
    await cleanup();
    await mount(client);
    await new Promise((r) => setTimeout(r, 30));
    expect(mock.history.get.filter((r) => r.url !== '/meta/org-time')).toHaveLength(1);
    await cleanup(); // unmount first: an observer leaving a cleared client re-arms a gc timer that keeps the worker alive
    client.clear();
  });
  it('granted users are allowed', async () => {
    mock.onGet('/tracking/field-now').reply(200, board([]));
    const client = new QueryClient();
    await mount(client);
    await waitFor(() => expect(screen.getByTestId('probe').props.children).toBe('true'));
    await cleanup(); // unmount first: an observer leaving a cleared client re-arms a gc timer that keeps the worker alive
    client.clear();
  });
});
