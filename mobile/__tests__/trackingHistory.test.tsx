import { fireEvent, screen } from '@testing-library/react-native';
import type MockAdapter from 'axios-mock-adapter';
import { MyHistory } from '../src/features/tracking/MyHistory';
import { renderWithProviders, setupApiMock, teardownApiMock } from '../test-utils';

jest.mock('../src/config/tenant', () => ({ getTenant: () => ({ ...require('../tenants/dev/tenant.json'), id: 'dev' }), getApiBaseUrl: () => 'http://test/api/v1' }));
jest.mock('react-native-maps', () => {
  const React = require('react');
  const { View } = require('react-native');
  const MapView = React.forwardRef((p: { children?: unknown }, _r: unknown) => React.createElement(View, { testID: 'field-map' }, p.children));
  return { __esModule: true, default: MapView, Marker: () => null, Polyline: (p: { coordinates: unknown[] }) => React.createElement(View, { testID: 'field-polyline', accessibilityLabel: String(p.coordinates.length) }) };
});
const mockMaps = { on: true };
jest.mock('../src/features/tracking/maps', () => ({ mapsAvailable: () => mockMaps.on }));

const pt = (iso: string) => ({ captured_at: iso, lat: 12.9, lng: 77.6, accuracy: 10, speed: 0, battery: null });
const day = (off: number) => new Date(Date.now() - off * 86_400_000).toISOString().slice(0, 10);
let mock: MockAdapter;
beforeEach(() => { mock = setupApiMock(); mockMaps.on = true; });
afterEach(teardownApiMock);

describe('MyHistory', () => {
  it('requests my-trail for today and draws a polyline when maps are available', async () => {
    mock.onGet('/tracking/my-trail').reply((c) => [200, { user_id: 1, date: c.params.date, truncated: false, points: [pt('2026-11-13T09:00:00Z'), pt('2026-11-13T09:05:00Z')] }]);
    await renderWithProviders(<MyHistory />);
    expect(await screen.findByTestId('field-polyline')).toBeTruthy();
    expect(mock.history.get[0].params).toEqual({ date: day(0) });
  });
  it('falls back to a time-ordered list without maps; Yesterday refetches that date', async () => {
    mockMaps.on = false;
    mock.onGet('/tracking/my-trail').reply((c) => [200, { user_id: 1, date: c.params.date, truncated: false, points: c.params.date === day(0) ? [pt('2026-11-13T09:00:00Z')] : [] }]);
    await renderWithProviders(<MyHistory />);
    expect(await screen.findByTestId('history-list')).toBeTruthy();
    expect(screen.getByText(/09:00 UTC/)).toBeTruthy();
    await fireEvent.press(screen.getByTestId('history-yesterday'));
    expect(await screen.findByTestId('history-empty')).toBeTruthy();
    expect(mock.history.get.some((r) => r.params.date === day(1))).toBe(true);
  });
  it('shows an error message when the request fails', async () => {
    mock.onGet('/tracking/my-trail').reply(500);
    await renderWithProviders(<MyHistory />);
    expect(await screen.findByTestId('history-error', {}, { timeout: 3000 })).toBeTruthy();
  });
});
