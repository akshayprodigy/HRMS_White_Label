import { fireEvent, screen, waitFor } from '@testing-library/react-native';
import { AccessibilityInfo } from 'react-native';
import type MockAdapter from 'axios-mock-adapter';
import { BroadcastBanner } from '../src/features/broadcast/BroadcastBanner';
import { BroadcastModal } from '../src/features/broadcast/BroadcastModal';
import { requiredResponse } from '../src/features/broadcast/api';
import { renderWithProviders, setupApiMock, teardownApiMock } from '../test-utils';

jest.mock('../src/config/tenant', () => ({ getTenant: () => ({ ...require('../tenants/dev/tenant.json'), id: 'dev' }), getApiBaseUrl: () => 'http://test/api/v1' }));
jest.mock('react-native-safe-area-context', () => ({ useSafeAreaInsets: () => ({ top: 0, bottom: 0, left: 0, right: 0 }) }));
jest.mock('../src/auth/AuthProvider', () => ({ useAuth: () => ({ user: { id: 1, email: 'a@x.com' } }) }));

const row = (over: object = {}) => ({ id: 9, title: 'Fire in block B', message: 'Evacuate now', severity: 'critical', requires_ack: false, safety_check: true, created_at: null, pending: true, ...over });
type Json = { props?: Record<string, any>; children?: (Json | string)[] | null }; // eslint-disable-line @typescript-eslint/no-explicit-any
function findNode(n: unknown, pred: (j: Json) => boolean): Json | null {
  if (!n || typeof n === 'string') return null;
  if (Array.isArray(n)) return n.map((c) => findNode(c, pred)).find(Boolean) ?? null;
  const j = n as Json;
  return pred(j) ? j : (j.children ?? []).map((c) => findNode(c, pred)).find(Boolean) ?? null;
}
let mock: MockAdapter;
beforeEach(() => {
  mock = setupApiMock();
});
afterEach(teardownApiMock);

describe('requiredResponse (mirrors backend _my_row.pending)', () => {
  it('safety beats ack beats read', () => {
    expect(requiredResponse({ safety_check: true, requires_ack: true })).toBe('safety');
    expect(requiredResponse({ safety_check: false, requires_ack: true })).toBe('ack');
    expect(requiredResponse({ safety_check: false, requires_ack: false })).toBe('read');
  });
});

describe('BroadcastModal', () => {
  it('renders nothing when there is no pending critical broadcast', async () => {
    mock.onGet('/broadcasts/my').reply(200, [row({ pending: false }), row({ id: 2, severity: 'warning' })]);
    await renderWithProviders(<BroadcastModal />);
    await waitFor(() => expect(mock.history.get.length).toBeGreaterThan(0));
    expect(screen.queryByTestId('broadcast-modal')).toBeNull();
  });

  it('cannot be dismissed: Android back is swallowed and there is no close control', async () => {
    mock.onGet('/broadcasts/my').reply(200, [row()]);
    await renderWithProviders(<BroadcastModal />);
    await screen.findByTestId('broadcast-modal');
    const modal = findNode(screen.toJSON(), (n) => typeof n.props?.onRequestClose === 'function');
    expect(modal).toBeTruthy();
    expect(modal?.props?.onRequestClose?.()).toBeUndefined(); // hardware back does nothing
    expect(screen.getByTestId('broadcast-modal')).toBeTruthy(); // still up
    expect(screen.queryByText(/close|dismiss/i)).toBeNull();
    expect(screen.getByText('Fire in block B')).toBeTruthy();
  });

  it('is an accessibility modal and announces a new critical alert', async () => {
    const spy = jest.spyOn(AccessibilityInfo, 'announceForAccessibility').mockImplementation(() => undefined);
    mock.onGet('/broadcasts/my').reply(200, [row()]);
    await renderWithProviders(<BroadcastModal />);
    const el = await screen.findByTestId('broadcast-modal');
    expect(el.props.accessibilityViewIsModal).toBe(true);
    expect(spy).toHaveBeenCalledWith('Emergency alert: Fire in block B');
  });

  it('safe: posts /safety with the note, then the modal closes', async () => {
    mock.onGet('/broadcasts/my').replyOnce(200, [row()]).onGet('/broadcasts/my').reply(200, [row({ pending: false })]);
    mock.onPost('/broadcasts/9/safety').reply(200, row({ pending: false, safety_status: 'safe' }));
    await renderWithProviders(<BroadcastModal />);
    await screen.findByTestId('broadcast-modal');
    await fireEvent.changeText(screen.getByTestId('bc-note-9'), '  at the gate ');
    await fireEvent.press(screen.getByTestId('bc-safe-9'));
    await waitFor(() => expect(screen.queryByTestId('broadcast-modal')).toBeNull());
    expect(JSON.parse(mock.history.post[0].data)).toEqual({ status: 'safe', note: 'at the gate' });
  });

  it('need help without a note sends no note', async () => {
    mock.onGet('/broadcasts/my').reply(200, [row()]);
    mock.onPost('/broadcasts/9/safety').reply(200, row({ pending: false }));
    await renderWithProviders(<BroadcastModal />);
    await screen.findByTestId('broadcast-modal');
    await fireEvent.press(screen.getByTestId('bc-help-9'));
    await waitFor(() => expect(mock.history.post).toHaveLength(1));
    expect(JSON.parse(mock.history.post[0].data)).toEqual({ status: 'need_help' });
  });

  it('stays up and shows the error when the response fails', async () => {
    mock.onGet('/broadcasts/my').reply(200, [row()]);
    mock.onPost('/broadcasts/9/safety').reply(400, { detail: 'Broadcast is closed' });
    await renderWithProviders(<BroadcastModal />);
    await screen.findByTestId('broadcast-modal');
    await fireEvent.press(screen.getByTestId('bc-safe-9'));
    expect(await screen.findByTestId('bc-error-9')).toBeTruthy();
    expect(screen.getByTestId('broadcast-modal')).toBeTruthy();
  });

  it('acknowledge uses /ack; plain critical uses /read', async () => {
    mock.onGet('/broadcasts/my').reply(200, [row({ safety_check: false, requires_ack: true })]);
    mock.onPost('/broadcasts/9/ack').reply(200, row({ pending: false }));
    await renderWithProviders(<BroadcastModal />);
    await fireEvent.press(await screen.findByTestId('bc-ack-9'));
    await waitFor(() => expect(mock.history.post[0].url).toBe('/broadcasts/9/ack'));
  });

  it('read-only critical broadcast offers "Got it" -> /read', async () => {
    mock.onGet('/broadcasts/my').reply(200, [row({ safety_check: false, requires_ack: false })]);
    mock.onPost('/broadcasts/9/read').reply(200, row({ pending: false }));
    await renderWithProviders(<BroadcastModal />);
    await fireEvent.press(await screen.findByTestId('bc-read-9'));
    await waitFor(() => expect(mock.history.post[0].url).toBe('/broadcasts/9/read'));
  });

  it('a double tap sends one request', async () => {
    mock.onGet('/broadcasts/my').replyOnce(200, [row()]).onGet('/broadcasts/my').reply(200, [row({ pending: false })]);
    mock.onPost('/broadcasts/9/safety').reply(() => new Promise((r) => setTimeout(() => r([200, row({ pending: false })]), 30)));
    await renderWithProviders(<BroadcastModal />);
    await screen.findByTestId('broadcast-modal');
    await fireEvent.press(screen.getByTestId('bc-safe-9'));
    await fireEvent.press(screen.getByTestId('bc-safe-9'));
    await fireEvent.press(screen.getByTestId('bc-help-9'));
    await waitFor(() => expect(screen.queryByTestId('broadcast-modal')).toBeNull());
    expect(mock.history.post).toHaveLength(1);
  });

  it('queues several critical broadcasts, one at a time', async () => {
    mock.onGet('/broadcasts/my').reply(200, [row({ id: 9 }), row({ id: 8, title: 'Second' })]);
    await renderWithProviders(<BroadcastModal />);
    await screen.findByTestId('broadcast-modal');
    expect(screen.getByText('1 more alert after this one')).toBeTruthy();
  });
});

describe('BroadcastBanner', () => {
  it('shows a non-critical broadcast with its response controls', async () => {
    mock.onPost('/broadcasts/4/ack').reply(200, row({ id: 4, pending: false }));
    await renderWithProviders(<BroadcastBanner broadcasts={[row({ id: 4, severity: 'warning', safety_check: false, requires_ack: true, title: 'Drill' })]} />);
    expect(screen.getByText('Drill')).toBeTruthy();
    await fireEvent.press(screen.getByTestId('bc-ack-4'));
    await waitFor(() => expect(mock.history.post[0].url).toBe('/broadcasts/4/ack'));
  });
});
