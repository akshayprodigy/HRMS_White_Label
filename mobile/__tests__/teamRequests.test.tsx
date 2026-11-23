import { fireEvent, screen, waitFor } from '@testing-library/react-native';
import type MockAdapter from 'axios-mock-adapter';
import { decidable } from '../src/features/team-requests/api';
import { TeamRequests } from '../src/features/team-requests/TeamRequests';
import { renderWithProviders, setupApiMock, teardownApiMock } from '../test-utils';

jest.mock('../src/config/tenant', () => ({ getTenant: () => ({ ...require('../tenants/dev/tenant.json'), id: 'dev' }), getApiBaseUrl: () => 'http://test/api/v1' }));
jest.mock('../src/auth/AuthProvider', () => ({ useAuth: () => ({ user: { id: 1, email: 'm@x.com' } }) }));
jest.mock('react-native-safe-area-context', () => ({ useSafeAreaInsets: () => ({ top: 0, bottom: 0, left: 0, right: 0 }) }));
jest.mock('../src/features/attendance/gate', () => ({ ...jest.requireActual('../src/features/attendance/gate'), useAttendanceGate: () => ({ gated: false, ready: true }) }));

const wl = (o: object) => ({ id: 5, user_name: 'Asha', kind: 'wfh', start_date: '2026-11-20', end_date: '2026-11-20', day_portion: 'full', place: null, purpose: 'Plumber', can_decide: true, ...o });
const pk = (o: object) => ({ id: 7, user_name: 'Ravi', holiday: { id: 1, name: 'Holi', date: '2026-11-25', location: 'All' }, reason: 'family', can_decide: true, ...o });

let mock: MockAdapter;
beforeEach(() => { mock = setupApiMock(); });
afterEach(teardownApiMock);
const posts = (u: string) => mock.history.post.filter((r) => r.url === u);

describe('decidable', () => {
  it('keeps only can_decide rows', () => {
    expect(decidable([{ id: 1, can_decide: true }, { id: 2, can_decide: false }, { id: 3 }])).toEqual([{ id: 1, can_decide: true }]);
    expect(decidable('nope')).toEqual([]);
  });
});

describe('TeamRequests', () => {
  it('lists only rows the viewer can decide', async () => {
    mock.onGet('/work-location-requests').reply(200, [wl({}), wl({ id: 6, can_decide: false })]);
    mock.onGet('/holidays/picks').reply(200, [pk({ can_decide: false })]);
    await renderWithProviders(<TeamRequests />);
    expect(await screen.findByTestId('team-wl-5')).toBeTruthy();
    expect(screen.queryByTestId('team-wl-6')).toBeNull();
    expect(screen.queryByTestId('team-pick-7')).toBeNull();
    expect(mock.history.get.every((r) => r.params?.status === 'pending')).toBe(true);
  });
  it('approves a work-location request with an optional note', async () => {
    mock.onGet('/work-location-requests').reply(200, [wl({})]);
    mock.onGet('/holidays/picks').reply(200, []);
    mock.onPost('/work-location-requests/5/decide').reply(200, {});
    await renderWithProviders(<TeamRequests />);
    await fireEvent.press(await screen.findByTestId('team-approve-wl-5'));
    await fireEvent.changeText(screen.getByTestId('team-note-wl-5'), ' ok ');
    await fireEvent.press(screen.getByTestId('team-confirm-wl-5'));
    await waitFor(() => expect(posts('/work-location-requests/5/decide').length).toBe(1));
    expect(JSON.parse(posts('/work-location-requests/5/decide')[0].data)).toEqual({ approve: true, note: 'ok' });
  });
  it('rejects a pick with a null note and surfaces a 409', async () => {
    mock.onGet('/work-location-requests').reply(200, []);
    mock.onGet('/holidays/picks').reply(200, [pk({})]);
    mock.onPost('/holidays/picks/7/decide').reply(409, { detail: 'decide via approvals' });
    await renderWithProviders(<TeamRequests />);
    await fireEvent.press(await screen.findByTestId('team-reject-pick-7'));
    await fireEvent.press(screen.getByTestId('team-confirm-pick-7'));
    expect(await screen.findByTestId('team-error-pick-7')).toHaveTextContent('decide via approvals');
    expect(JSON.parse(posts('/holidays/picks/7/decide')[0].data)).toEqual({ approve: false, note: null });
  });
  it('hides quietly on 403 and shows other errors', async () => {
    mock.onGet('/work-location-requests').reply(403, { detail: 'Not allowed' });
    mock.onGet('/holidays/picks').reply(403, { detail: 'Not allowed' });
    const r = await renderWithProviders(<TeamRequests />);
    await waitFor(() => expect(mock.history.get.length).toBe(2));
    expect(screen.queryByTestId('team-requests-title')).toBeNull();
    expect(screen.queryByTestId('team-requests-error')).toBeNull();
    r.unmount();
    mock.reset();
    mock.onGet('/work-location-requests').reply(500, { detail: 'Boom' });
    mock.onGet('/holidays/picks').reply(200, []);
    await renderWithProviders(<TeamRequests />);
    expect(await screen.findByTestId('team-requests-error')).toBeTruthy();
  });
});
