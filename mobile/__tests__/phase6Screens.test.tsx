import { fireEvent, screen, waitFor } from '@testing-library/react-native';
import type MockAdapter from 'axios-mock-adapter';
import { HolidaysScreen } from '../src/features/holidays/HolidaysScreen';
import { ApprovedBanner } from '../src/features/work-location/ApprovedBanner';
import { WorkLocationScreen } from '../src/features/work-location/WorkLocationScreen';
import { renderWithProviders, setupApiMock, teardownApiMock } from '../test-utils';

jest.mock('../src/config/tenant', () => ({ getTenant: () => ({ ...require('../tenants/dev/tenant.json'), id: 'dev' }), getApiBaseUrl: () => 'http://test/api/v1' }));
jest.mock('../src/auth/AuthProvider', () => ({ useAuth: () => ({ user: { id: 1, email: 'a@x.com' } }) }));
jest.mock('react-native-safe-area-context', () => ({ useSafeAreaInsets: () => ({ top: 0, bottom: 0, left: 0, right: 0 }) }));
jest.mock('../src/lib/org-time', () => ({ useOrgTime: () => ({ today: '2026-11-20', timezone: 'Asia/Kolkata', ready: true }) }));

const hol = (o: object) => ({ id: 1, name: 'Holi', date: '2026-11-25', location: 'All', is_optional: true, pick: null, ...o });
const wl = (o: object) => ({ id: 5, kind: 'wfh', start_date: '2026-11-20', end_date: '2026-11-20', day_portion: 'full', place: null, purpose: 'Plumber', status: 'pending', decision_note: null, ...o });
const posts = (url: string) => mock.history.post.filter((r) => r.url === url);

let mock: MockAdapter;
beforeEach(() => { mock = setupApiMock(); });
afterEach(teardownApiMock);

describe('HolidaysScreen', () => {
  const load = (holidays: object[], remaining = 1) => mock.onGet('/holidays/my').reply(200, { quota: 2, used: 2 - remaining, remaining, year: 2026, holidays });

  it('shows the quota chip and Pending approval (never "granted"), with Cancel', async () => {
    load([hol({ pick: { id: 9, status: 'pending' } })], 1);
    await renderWithProviders(<HolidaysScreen />);
    expect(await screen.findByTestId('quota-chip')).toHaveTextContent('1 of 2 optional used');
    expect(screen.getByTestId('pick-status-1')).toHaveTextContent('Pending approval');
    expect(screen.getByTestId('cancel-1')).toBeEnabled();
  });
  it('picks with the reason and says it is not taken until approved', async () => {
    load([hol({})]);
    mock.onPost('/holidays/picks').reply(201, {});
    await renderWithProviders(<HolidaysScreen />);
    await fireEvent.press(await screen.findByTestId('pick-1'));
    await fireEvent.changeText(screen.getByTestId('pick-reason-1'), ' family ');
    await fireEvent.press(screen.getByTestId('pick-confirm-1'));
    await waitFor(() => expect(posts('/holidays/picks').length).toBe(1));
    expect(JSON.parse(posts('/holidays/picks')[0].data)).toEqual({ holiday_id: 1, reason: 'family' });
    expect(await screen.findByTestId('pick-msg-1')).toHaveTextContent(/not yours until it is approved/);
  });
  it('surfaces a backend error on pick', async () => {
    load([hol({})]);
    mock.onPost('/holidays/picks').reply(409, { detail: 'Optional holiday quota used up' });
    await renderWithProviders(<HolidaysScreen />);
    await fireEvent.press(await screen.findByTestId('pick-1'));
    await fireEvent.press(screen.getByTestId('pick-confirm-1'));
    expect(await screen.findByTestId('holiday-error-1')).toHaveTextContent('Optional holiday quota used up');
  });
  it('rejected shows the note and offers Pick again; cancel hits the cancel endpoint', async () => {
    load([hol({ id: 1, pick: { id: 9, status: 'rejected', decision_note: 'Team busy' } }), hol({ id: 2, name: 'Diwali', pick: { id: 10, status: 'approved' } })]);
    mock.onPost('/holidays/picks/10/cancel').reply(200, {});
    await renderWithProviders(<HolidaysScreen />);
    expect(await screen.findByTestId('pick-note-1')).toHaveTextContent(/Team busy/);
    expect(screen.getByTestId('pick-1')).toHaveTextContent('Pick again');
    await fireEvent.press(screen.getByTestId('cancel-2'));
    await fireEvent.press(screen.getByTestId('cancel-confirm-2'));
    await waitFor(() => expect(posts('/holidays/picks/10/cancel').length).toBe(1));
  });
  it('disables Pick and Cancel for past holidays', async () => {
    load([hol({ id: 1, date: '2026-11-19' }), hol({ id: 2, date: '2026-11-19', pick: { id: 3, status: 'pending' } })]);
    await renderWithProviders(<HolidaysScreen />);
    expect(await screen.findByTestId('pick-1')).toBeDisabled();
    expect(screen.getByTestId('cancel-2')).toBeDisabled();
  });
});

describe('WorkLocationScreen', () => {
  it('lists requests, shows Pending approval, and disables cancel once started', async () => {
    mock.onGet('/work-location-requests/my').reply(200, [wl({ id: 5 }), wl({ id: 6, start_date: '2026-11-18', end_date: '2026-11-22', status: 'approved' })]);
    await renderWithProviders(<WorkLocationScreen />);
    expect(await screen.findByTestId('wl-status-5')).toHaveTextContent('Pending approval');
    expect(screen.getByTestId('wl-cancel-5')).toBeEnabled();
    expect(screen.getByTestId('wl-cancel-6')).toBeDisabled();
  });
  it('blocks an invalid form without calling the server', async () => {
    mock.onGet('/work-location-requests/my').reply(200, []);
    await renderWithProviders(<WorkLocationScreen />);
    await fireEvent.press(await screen.findByTestId('wl-new'));
    await fireEvent.press(screen.getByTestId('wl-submit'));
    expect(await screen.findByText('Please give a purpose.')).toBeTruthy();
    expect(posts('/work-location-requests').length).toBe(0);
  });
  it('submits the exact payload and shows the pending notice', async () => {
    mock.onGet('/work-location-requests/my').reply(200, []);
    mock.onPost('/work-location-requests').reply(201, {});
    await renderWithProviders(<WorkLocationScreen />);
    await fireEvent.press(await screen.findByTestId('wl-new'));
    await fireEvent.press(screen.getByTestId('kind-client_visit'));
    await fireEvent.changeText(screen.getByTestId('wl-place'), 'Acme');
    await fireEvent.changeText(screen.getByTestId('wl-purpose'), 'Demo');
    await fireEvent.press(screen.getByTestId('wl-submit'));
    await waitFor(() => expect(posts('/work-location-requests').length).toBe(1));
    expect(JSON.parse(posts('/work-location-requests')[0].data)).toEqual({ kind: 'client_visit', start_date: '2026-11-20', end_date: '2026-11-20', day_portion: 'full', place: 'Acme', purpose: 'Demo' });
    expect(await screen.findByTestId('wl-notice')).toHaveTextContent(/not granted until someone approves/);
  });
  it('shows the backend 409 for overlapping approved leave', async () => {
    mock.onGet('/work-location-requests/my').reply(200, []);
    mock.onPost('/work-location-requests').reply(409, { detail: 'You have approved leave on these dates' });
    await renderWithProviders(<WorkLocationScreen />);
    await fireEvent.press(await screen.findByTestId('wl-new'));
    await fireEvent.changeText(screen.getByTestId('wl-purpose'), 'Home');
    await fireEvent.press(screen.getByTestId('wl-submit'));
    expect(await screen.findByTestId('wl-server-error')).toHaveTextContent('You have approved leave on these dates');
  });
});

describe('ApprovedBanner', () => {
  it('shows only for an approved request covering today', async () => {
    mock.onGet('/work-location-requests/my').reply(200, [wl({ status: 'pending' })]);
    await renderWithProviders(<ApprovedBanner />);
    await waitFor(() => expect(mock.history.get.length).toBe(1));
    expect(screen.queryByTestId('wl-approved-banner')).toBeNull();
  });
  it('uses the right kind label', async () => {
    mock.onGet('/work-location-requests/my').reply(200, [wl({ status: 'approved' })]);
    await renderWithProviders(<ApprovedBanner />);
    expect(await screen.findByTestId('wl-approved-banner')).toHaveTextContent('Approved Work from home today — location check relaxed');
  });
});
