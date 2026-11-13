import { fireEvent, screen, waitFor } from '@testing-library/react-native';
import type MockAdapter from 'axios-mock-adapter';
import { OpenShiftsPanel } from '../src/features/schedule/OpenShiftsPanel';
import { SwapDialog } from '../src/features/schedule/SwapDialog';
import { SwapsPanel } from '../src/features/schedule/SwapsPanel';
import { AcksBanner } from '../src/features/schedule/AcksBanner';
import { ScheduleScreen } from '../src/features/schedule/ScheduleScreen';
import { GATE_BODY, renderWithProviders, setupApiMock, teardownApiMock } from '../test-utils';

jest.mock('../src/config/tenant', () => ({
  getTenant: () => ({ ...require('../tenants/dev/tenant.json'), id: 'dev' }),
  getApiBaseUrl: () => 'http://test/api/v1',
}));
jest.mock('../src/auth/AuthProvider', () => ({ useAuth: () => ({ user: { id: 1, email: 'a@x.com' }, unverified: false }) }));
jest.mock('react-native-safe-area-context', () => ({ useSafeAreaInsets: () => ({ top: 0, bottom: 0, left: 0, right: 0 }) }));
jest.mock('expo-router', () => ({ useRouter: () => ({ navigate: jest.fn(), push: jest.fn() }) }));

const TODAY = '2026-11-13';
const cand = (o: object) => ({ user_id: 5, name: 'Asha', shift_template_id: 4, shift_name: 'Evening', is_week_off: false, ...o });
const open = (o: object) => ({ id: 7, work_date: '2026-11-20', shift_name: 'Night', shift_start: '22:00:00', shift_end: '06:00:00', department: 'Ops', location: null, note: null, slots: 2, filled: 1, my_claim_id: null, my_claim_status: null, warnings: [], ...o });

let mock: MockAdapter;
beforeEach(() => {
  mock = setupApiMock();
  mock.onGet('/attendance/today').reply(200, { is_marked: true, attendance: null });
  mock.onGet('/dashboard/pending-count').reply(200, { count: 0 });
});
afterEach(teardownApiMock);
const posts = (url: string) => mock.history.post.filter((r) => r.url === url);

describe('SwapDialog', () => {
  const day = { date: '2026-11-16', shiftName: 'Morning', shiftTemplateId: 3, isWeekOff: false };
  const renderIt = (onDone = jest.fn(), onClose = jest.fn()) => renderWithProviders(<SwapDialog day={day} today={TODAY} onClose={onClose} onDone={onDone} />);
  beforeEach(() => {
    mock.onGet('/roster/swaps/candidates', { params: { date: '2026-11-16' } }).reply(200, [cand({}), cand({ user_id: 6, name: 'Ben', shift_template_id: 3, shift_name: 'Morning' })]);
  });

  it('lists same-department colleagues and disables one already on my shift', async () => {
    await renderIt();
    expect(await screen.findByTestId('cand-5')).toBeEnabled();
    expect(screen.getByTestId('cand-6')).toBeDisabled();
  });

  it('requires a colleague before posting', async () => {
    await renderIt();
    await screen.findByTestId('cand-5');
    await fireEvent.press(screen.getByTestId('swap-submit'));
    expect(await screen.findByTestId('swap-error')).toHaveTextContent(/colleague/i);
    expect(posts('/roster/swaps')).toHaveLength(0);
  });

  it('posts the swap (with return date + reason) and reports done', async () => {
    mock.onGet('/roster/swaps/candidates', { params: { date: '2026-11-18' } }).reply(200, [cand({ shift_name: 'Late' })]);
    mock.onPost('/roster/swaps').reply(200, { id: 1 });
    const onDone = jest.fn();
    await renderIt(onDone);
    await fireEvent.press(await screen.findByTestId('cand-5'));
    await fireEvent(screen.getByTestId('swap-other-day'), 'valueChange', true);
    await fireEvent.changeText(screen.getByTestId('swap-return-date'), '2026-11-18');
    await waitFor(() => expect(screen.getByTestId('swap-return-hint')).toHaveTextContent(/Asha works Late on 18 Nov/));
    await fireEvent.changeText(screen.getByTestId('swap-reason'), '  family event ');
    await fireEvent.press(screen.getByTestId('swap-submit'));
    await waitFor(() => expect(onDone).toHaveBeenCalledTimes(1));
    expect(JSON.parse(posts('/roster/swaps')[0].data)).toEqual({ counterparty_id: 5, requester_date: '2026-11-16', counterparty_date: '2026-11-18', reason: 'family event' });
  });

  it('blocks an invalid return date client-side', async () => {
    await renderIt();
    await fireEvent.press(await screen.findByTestId('cand-5'));
    await fireEvent(screen.getByTestId('swap-other-day'), 'valueChange', true);
    await fireEvent.changeText(screen.getByTestId('swap-return-date'), '2026-12-20');
    await fireEvent.press(screen.getByTestId('swap-submit'));
    expect(await screen.findByTestId('swap-error')).toHaveTextContent(/within 14 days/i);
    await fireEvent.changeText(screen.getByTestId('swap-return-date'), '2026-11-16');
    await fireEvent.press(screen.getByTestId('swap-submit'));
    expect(await screen.findByTestId('swap-error')).toHaveTextContent(/return date/i);
    expect(posts('/roster/swaps')).toHaveLength(0);
  });

  it('shows the backend reason on failure and does not double-post on rapid taps', async () => {
    mock.onPost('/roster/swaps').reply(() => new Promise((r) => setTimeout(() => r([409, { detail: 'A pending swap already involves one of these employees on these dates' }]), 20)));
    const onDone = jest.fn();
    await renderIt(onDone);
    await fireEvent.press(await screen.findByTestId('cand-5'));
    await fireEvent.press(screen.getByTestId('swap-submit'));
    await fireEvent.press(screen.getByTestId('swap-submit'));
    expect(await screen.findByTestId('swap-error')).toHaveTextContent(/pending swap already/i);
    expect(posts('/roster/swaps')).toHaveLength(1);
    expect(onDone).not.toHaveBeenCalled();
  });
});

describe('OpenShiftsPanel', () => {
  it('shows UTC-labelled open shifts and claims one, refreshing the list', async () => {
    let claimed = false;
    mock.onGet('/roster/open-shifts/available').reply(() => [200, [open(claimed ? { my_claim_id: 31, my_claim_status: 'pending' } : {})]]);
    mock.onPost('/roster/open-shifts/7/claim').reply(() => { claimed = true; return [200, open({ my_claim_id: 31, my_claim_status: 'pending' })]; });
    await renderWithProviders(<OpenShiftsPanel />);
    expect(await screen.findByText(/22:00–06:00 UTC/)).toBeTruthy();
    expect(screen.getByText(/1\/2 filled/)).toBeTruthy();
    await fireEvent.press(screen.getByTestId('claim-7'));
    expect(await screen.findByTestId('open-status-7')).toBeTruthy();
    expect(screen.getByTestId('open-notice')).toHaveTextContent(/awaiting confirmation/i);
    expect(screen.queryByTestId('claim-7')).toBeNull();
    expect(screen.getByTestId('withdraw-7')).toBeTruthy();
    expect(posts('/roster/open-shifts/7/claim')).toHaveLength(1);
  });

  it('claim is double-tap safe and surfaces the backend refusal', async () => {
    mock.onGet('/roster/open-shifts/available').reply(200, [open({})]);
    mock.onPost('/roster/open-shifts/7/claim').reply(() => new Promise((r) => setTimeout(() => r([400, { detail: 'You are not eligible: already rostered that day' }]), 20)));
    await renderWithProviders(<OpenShiftsPanel />);
    await fireEvent.press(await screen.findByTestId('claim-7'));
    await fireEvent.press(screen.getByTestId('claim-7'));
    expect(await screen.findByTestId('open-error')).toHaveTextContent(/not eligible/i);
    expect(posts('/roster/open-shifts/7/claim')).toHaveLength(1);
  });

  it('auto-confirmed claims and warnings are announced', async () => {
    mock.onGet('/roster/open-shifts/available').reply(200, [open({})]);
    mock.onPost('/roster/open-shifts/7/claim').reply(200, open({ my_claim_id: 9, my_claim_status: 'approved', warnings: ['Less than 11h rest'] }));
    await renderWithProviders(<OpenShiftsPanel />);
    await fireEvent.press(await screen.findByTestId('claim-7'));
    expect(await screen.findByTestId('open-notice')).toHaveTextContent(/the shift is yours/i);
    expect(screen.getByText('Less than 11h rest')).toBeTruthy();
  });

  it('withdraws a pending claim after confirmation', async () => {
    mock.onGet('/roster/open-shifts/available').reply(200, [open({ my_claim_id: 31, my_claim_status: 'pending' })]);
    mock.onPost('/roster/open-shifts/claims/31/withdraw').reply(200, open({}));
    await renderWithProviders(<OpenShiftsPanel />);
    expect(screen.queryByTestId('claim-7')).toBeNull();
    await fireEvent.press(await screen.findByTestId('withdraw-7'));
    await fireEvent.press(screen.getByTestId('withdraw-7-confirm'));
    await waitFor(() => expect(posts('/roster/open-shifts/claims/31/withdraw')).toHaveLength(1));
  });

  it('a withdrawn claim can be claimed again; the gate shows the punch-in notice', async () => {
    mock.onGet('/roster/open-shifts/available').reply(200, [open({ my_claim_id: 31, my_claim_status: 'withdrawn' })]);
    await renderWithProviders(<OpenShiftsPanel />);
    expect(await screen.findByTestId('claim-7')).toBeTruthy();
  });

  it('gate 403 shows the attendance notice', async () => {
    mock.onGet('/roster/open-shifts/available').reply(403, GATE_BODY);
    await renderWithProviders(<OpenShiftsPanel />);
    expect(await screen.findByTestId('gate-notice')).toBeTruthy();
  });
});

describe('SwapsPanel', () => {
  const swap = (o: object) => ({ id: 1, requester_id: 9, requester_name: 'Ravi', counterparty_id: 1, counterparty_name: 'Me', requester_date: '2026-11-16', counterparty_date: '2026-11-16', reason: null, status: 'pending_peer', requester_cell: { shift_template_id: 3, shift_name: 'Morning', is_week_off: false }, counterparty_cell: { shift_template_id: null, shift_name: null, is_week_off: true }, decision_note: null, created_at: null, direction: 'incoming', ...o });
  beforeEach(() => mock.onGet('/roster/drops/my').reply(200, []));

  it('accepts an incoming swap once and refreshes', async () => {
    let status = 'pending_peer';
    mock.onGet('/roster/swaps/my').reply(() => [200, [swap({ status })]]);
    mock.onPost('/roster/swaps/1/accept').reply(() => new Promise((r) => setTimeout(() => { status = 'pending_approval'; r([200, swap({ status })]); }, 20)));
    await renderWithProviders(<SwapsPanel />);
    await fireEvent.press(await screen.findByTestId('swap-accept-1'));
    await fireEvent.press(screen.getByTestId('swap-accept-1'));
    await waitFor(() => expect(screen.queryByTestId('swap-accept-1')).toBeNull());
    expect(screen.getByTestId('swap-status-1')).toBeTruthy();
    expect(posts('/roster/swaps/1/accept')).toHaveLength(1);
  });

  it('declines incoming and cancels outgoing (after confirmation)', async () => {
    mock.onGet('/roster/swaps/my').reply(200, [swap({}), swap({ id: 2, direction: 'outgoing', requester_name: 'Me', counterparty_name: 'Ravi', status: 'pending_approval' })]);
    mock.onPost('/roster/swaps/1/decline').reply(200, swap({ status: 'declined' }));
    mock.onPost('/roster/swaps/2/cancel').reply(200, swap({ id: 2, status: 'cancelled' }));
    await renderWithProviders(<SwapsPanel />);
    await fireEvent.press(await screen.findByTestId('swap-decline-1'));
    await waitFor(() => expect(posts('/roster/swaps/1/decline')).toHaveLength(1));
    expect(screen.queryByTestId('swap-accept-2')).toBeNull();
    await fireEvent.press(screen.getByTestId('swap-cancel-2'));
    expect(posts('/roster/swaps/2/cancel')).toHaveLength(0); // needs the confirm step
    await fireEvent.press(screen.getByTestId('swap-cancel-2-confirm'));
    await waitFor(() => expect(posts('/roster/swaps/2/cancel')).toHaveLength(1));
  });

  it('lists give-aways and cancels a pending one', async () => {
    mock.onGet('/roster/swaps/my').reply(200, []);
    mock.onGet('/roster/drops/my').reply(200, [{ id: 4, work_date: '2026-11-17', shift_name: 'Morning', shift_start: null, shift_end: null, reason: 'unwell', status: 'pending', decision_note: null }]);
    mock.onPost('/roster/drops/4/cancel').reply(200, {});
    await renderWithProviders(<SwapsPanel />);
    await fireEvent.press(await screen.findByTestId('drop-cancel-4'));
    await fireEvent.press(screen.getByTestId('drop-cancel-4-confirm'));
    await waitFor(() => expect(posts('/roster/drops/4/cancel')).toHaveLength(1));
  });
});

describe('AcksBanner', () => {
  it('shows emergency changes and acknowledges them; hidden when none', async () => {
    let acks = [{ id: 3, work_date: '2026-11-14', old_shift_name: 'Morning', old_is_week_off: false, new_shift_name: null, new_is_week_off: true, reason: 'Cover' }];
    mock.onGet('/roster/my/acks').reply(() => [200, acks]);
    mock.onPost('/roster/my/acks/3').reply(() => { acks = []; return [200, {}]; });
    await renderWithProviders(<AcksBanner />);
    expect(await screen.findByTestId('ack-3')).toHaveTextContent(/Morning → Week off/);
    await fireEvent.press(screen.getByTestId('ack-btn-3'));
    await waitFor(() => expect(screen.queryByTestId('acks-banner')).toBeNull());
    expect(posts('/roster/my/acks/3')).toHaveLength(1);
  });
});

describe('ScheduleScreen', () => {
  const NOW = new Date('2026-11-13T10:00:00Z'); // a Friday
  beforeEach(() => { jest.spyOn(Date, 'now').mockReturnValue(NOW.getTime()); });
  afterEach(() => jest.restoreAllMocks());
  const mon = (() => { const d = new Date(NOW); const dow = (d.getUTCDay() + 6) % 7; d.setUTCDate(d.getUTCDate() - dow); return d.toISOString().slice(0, 10); })();
  const week = (start: string) => ({ start, days: Array.from({ length: 7 }, (_, i) => { const d = new Date(`${start}T00:00:00Z`); d.setUTCDate(d.getUTCDate() + i); const date = d.toISOString().slice(0, 10); return { date, is_today: date === NOW.toISOString().slice(0, 10), is_weekend: i === 6, holiday_name: null, on_leave: false, leave_type: null, shift: i === 6 ? { name: 'Week off', start_time: null, end_time: null, is_overnight: false, source: 'roster' } : { name: 'Morning', start_time: '09:00', end_time: '17:00', is_overnight: false, source: 'roster', shift_template_id: 3, transport_required: i === 0 } }; }) });
  beforeEach(() => {
    mock.onGet('/roster/my/week').reply((c) => [200, week(c.params?.start ?? mon)]);
    mock.onGet('/roster/my/acks').reply(200, []);
    mock.onGet('/roster/my/on-call').reply(200, [{ id: 1, work_date: mon, start_time: '18:00', end_time: '23:00', is_overnight: false, note: null }]);
    mock.onGet('/roster/my/running-late').reply(200, { notice: null, can_post: false });
    mock.onGet('/roster/my/calendar-feed').reply(200, { active: false, created_at: null });
    mock.onGet('/roster/swaps/my').reply(200, []);
    mock.onGet('/roster/drops/my').reply(200, []);
    mock.onGet('/roster/open-shifts/available').reply(200, []);
    mock.onGet('/roster/availability/my').reply(200, []);
    mock.onGet('/shifts/templates').reply(200, [{ id: 3, name: 'Morning' }]);
  });

  it('shows the week strip with UTC times, transport flag and on-call; sub-tabs switch', async () => {
    await renderWithProviders(<ScheduleScreen />);
    expect(await screen.findByTestId(`strip-${mon}`)).toBeTruthy();
    expect(await screen.findByTestId('on-call-1')).toHaveTextContent(/18:00–23:00 UTC/);
    await fireEvent.press(screen.getByTestId(`strip-${mon}`));
    expect(await screen.findByTestId(`day-times-${mon}`)).toHaveTextContent('09:00–17:00 UTC');
    expect(screen.getByTestId(`day-transport-${mon}`)).toBeTruthy();
    expect(screen.queryByTestId(`swap-${mon}`)).toBeNull(); // past day: no swap / give-away
    await fireEvent.press(screen.getByTestId('strip-2026-11-13'));
    expect(await screen.findByTestId('swap-2026-11-13')).toBeTruthy(); // today: can swap / give away
    expect(screen.getByTestId('give-2026-11-13')).toBeTruthy();
    await fireEvent.press(screen.getByTestId('sched-tab-swaps'));
    expect(await screen.findByTestId('swaps-incoming-empty')).toBeTruthy();
    await fireEvent.press(screen.getByTestId('sched-tab-open'));
    expect(await screen.findByTestId('open-empty')).toBeTruthy();
    await fireEvent.press(screen.getByTestId('sched-tab-availability'));
    expect(await screen.findByTestId('avail-empty')).toBeTruthy();
  });

  it('offers swap on a published future day and moves to Swaps after requesting', async () => {
    const tomorrow = '2026-11-14';
    mock.onGet('/roster/swaps/candidates').reply(200, [cand({})]);
    mock.onPost('/roster/swaps').reply(200, { id: 1 });
    await renderWithProviders(<ScheduleScreen />);
    await fireEvent.press(await screen.findByTestId(`strip-${tomorrow}`));
    await fireEvent.press(screen.getByTestId(`swap-${tomorrow}`));
    await fireEvent.press(await screen.findByTestId('cand-5'));
    await fireEvent.press(screen.getByTestId('swap-submit'));
    expect(await screen.findByTestId('sched-notice')).toHaveTextContent(/Swap requested/);
    expect(await screen.findByTestId('swaps-incoming-empty')).toBeTruthy();
  });

  it('creates a calendar link and exposes it once', async () => {
    mock.onPost('/roster/my/calendar-feed').reply(200, { url: 'http://test/api/v1/calendar/abc.ics' });
    await renderWithProviders(<ScheduleScreen />);
    await screen.findByTestId('feed-status');
    await fireEvent.press(screen.getByTestId('feed-create'));
    expect(await screen.findByTestId('feed-url')).toHaveTextContent('http://test/api/v1/calendar/abc.ics');
    expect(screen.getByTestId('feed-warning')).toBeTruthy();
  });
});

import { GiveawayDialog } from '../src/features/schedule/GiveawayDialog';
describe('GiveawayDialog', () => {
  it('requires a reason of 3+ chars, posts once', async () => {
    mock.onPost('/roster/drops').reply(() => new Promise((r) => setTimeout(() => r([200, { id: 1 }]), 20)));
    const onDone = jest.fn();
    await renderWithProviders(<GiveawayDialog date="2026-11-16" shiftName="Morning" onClose={jest.fn()} onDone={onDone} />);
    await fireEvent.changeText(screen.getByTestId('giveaway-reason'), 'ab');
    await fireEvent.press(screen.getByTestId('giveaway-submit'));
    expect(await screen.findByTestId('giveaway-error')).toBeTruthy();
    expect(posts('/roster/drops')).toHaveLength(0);
    await fireEvent.changeText(screen.getByTestId('giveaway-reason'), ' unwell ');
    await fireEvent.press(screen.getByTestId('giveaway-submit'));
    await fireEvent.press(screen.getByTestId('giveaway-submit'));
    await waitFor(() => expect(onDone).toHaveBeenCalledTimes(1));
    expect(posts('/roster/drops')).toHaveLength(1);
    expect(JSON.parse(posts('/roster/drops')[0].data)).toEqual({ work_date: '2026-11-16', reason: 'unwell' });
  });
});
