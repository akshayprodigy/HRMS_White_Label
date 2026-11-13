import { act, fireEvent, screen, waitFor } from '@testing-library/react-native';
import type MockAdapter from 'axios-mock-adapter';
import { LeaveScreen } from '../src/features/leave/LeaveScreen';
import { GATE_BODY, renderWithProviders, setupApiMock, teardownApiMock } from '../test-utils';

jest.mock('../src/config/tenant', () => ({
  getTenant: () => ({ ...require('../tenants/dev/tenant.json'), id: 'dev' }),
  getApiBaseUrl: () => 'http://test/api/v1',
}));
jest.mock('../src/auth/AuthProvider', () => ({ useAuth: () => ({ user: { id: 1, email: 'a@x.com' }, unverified: false }) }));
jest.mock('react-native-safe-area-context', () => ({ useSafeAreaInsets: () => ({ top: 0, bottom: 0, left: 0, right: 0 }) }));
jest.mock('expo-router', () => ({ useRouter: () => ({ navigate: jest.fn(), push: jest.fn() }) }));
const mockCamera = jest.fn();
const mockPerm = jest.fn();
const mockDoc = jest.fn();
jest.mock('expo-image-picker', () => ({ requestCameraPermissionsAsync: (...a: unknown[]) => mockPerm(...a), launchCameraAsync: (...a: unknown[]) => mockCamera(...a) }));
jest.mock('expo-document-picker', () => ({ getDocumentAsync: (...a: unknown[]) => mockDoc(...a) }));

const NOW = () => new Date(2026, 10, 13, 10, 0, 0); // 2026-11-13 local
const sick = { id: 2, name: 'Sick', allow_half_day: true, requires_medical_cert_after: 3, unpaid_allowed: false };
const casual = { id: 1, name: 'Casual', allow_half_day: true, requires_medical_cert_after: null, unpaid_allowed: false };
const lr = (o: object) => ({ id: 10, leave_type: casual, start_date: '2026-11-10', end_date: '2026-11-10', is_half_day: false, half_day_session: null, reason: 'x', status: 'submitted', total_days: 1, is_emergency: false, attachment_url: null, proof_due_date: null, proof_submitted_at: null, converted_to_lop_at: null, ...o });

let mock: MockAdapter;
beforeEach(() => {
  mock = setupApiMock();
  mockCamera.mockReset(); mockPerm.mockReset(); mockDoc.mockReset();
  mock.onGet('/leave/balances').reply(200, [{ leave_type: casual, balance: 12, used: 2, total: 12, remaining: 10 }]);
  mock.onGet('/leave/types').reply(200, [casual, sick]);
  mock.onGet('/leave/my').reply(200, []);
});
afterEach(teardownApiMock);

const open = async () => {
  await renderWithProviders(<LeaveScreen now={NOW} />);
  await waitFor(() => expect(screen.getByTestId('apply-leave')).toBeEnabled()); // enabled once leave types load
  await fireEvent.press(screen.getByTestId('apply-leave'));
  await screen.findByTestId('apply-form');
};
const fill = async (o: { type?: number; start?: string; end?: string; reason?: string }) => {
  if (o.type) await fireEvent.press(screen.getByTestId(`type-${o.type}`));
  if (o.start) await fireEvent.changeText(screen.getByTestId('input-start'), o.start);
  if (o.end) await fireEvent.changeText(screen.getByTestId('input-end'), o.end);
  if (o.reason) await fireEvent.changeText(screen.getByTestId('input-reason'), o.reason);
};
const applyPosts = () => mock.history.post.filter((r) => r.url === '/leave/apply');

describe('balances + history', () => {
  it('shows balances and request status badges', async () => {
    mock.onGet('/leave/my').reply(200, [lr({ id: 11, status: 'approved' })]);
    await renderWithProviders(<LeaveScreen now={NOW} />);
    expect(await screen.findByTestId('balance-1')).toHaveTextContent(/10\.0/);
    expect(await screen.findByTestId('leave-status-11')).toHaveTextContent('Approved');
  });
  it('shows the attendance gate notice on ATTENDANCE_REQUIRED', async () => {
    mock.onGet('/leave/balances').reply(403, GATE_BODY);
    mock.onGet('/leave/my').reply(403, GATE_BODY);
    await renderWithProviders(<LeaveScreen now={NOW} />);
    expect(await screen.findByTestId('gate-notice')).toBeTruthy();
  });
});

describe('apply form', () => {
  it('blocks submit with field errors and sends nothing', async () => {
    await open();
    await fireEvent.press(screen.getByTestId('submit-leave'));
    expect(await screen.findByTestId('error-type')).toBeTruthy();
    expect(screen.getByText('Enter a start date.')).toBeTruthy();
    expect(screen.getByText('Enter a reason.')).toBeTruthy();
    expect(applyPosts()).toHaveLength(0);
  });
  it('requires a medical certificate for long sick leave', async () => {
    await open();
    await fill({ type: 2, start: '2026-11-16', end: '2026-11-18', reason: 'Fever' });
    await fireEvent.press(screen.getByTestId('submit-leave'));
    expect(await screen.findByTestId('error-attachment')).toHaveTextContent(/medical certificate/);
    expect(applyPosts()).toHaveLength(0);
  });
  it('submits a valid request with the exact payload and shows a notice', async () => {
    mock.onPost('/leave/apply').reply(200, lr({ id: 20 }));
    await open();
    await fill({ type: 1, start: '2026-11-16', end: '2026-11-17', reason: ' Trip ' });
    await fireEvent.press(screen.getByTestId('submit-leave'));
    expect(await screen.findByTestId('leave-notice')).toHaveTextContent('Leave submitted for approval.');
    expect(JSON.parse(applyPosts()[0].data)).toEqual({
      leave_type_id: 1, start_date: '2026-11-16', end_date: '2026-11-17', reason: 'Trip', emergency_contact: null,
      is_half_day: false, half_day_session: null, attachment_url: null, is_emergency: false,
    });
  });
  it('half day locks end = start and sends the session', async () => {
    mock.onPost('/leave/apply').reply(200, lr({ id: 21, is_half_day: true }));
    await open();
    await fireEvent.press(screen.getByTestId('toggle-half'));
    await fireEvent(screen.getByTestId('toggle-half'), 'valueChange', true);
    await fill({ type: 1, start: '2026-11-16', reason: 'Dentist' });
    await fireEvent.press(screen.getByTestId('session-afternoon'));
    await fireEvent.press(screen.getByTestId('submit-leave'));
    await waitFor(() => expect(applyPosts()).toHaveLength(1));
    expect(JSON.parse(applyPosts()[0].data)).toMatchObject({ is_half_day: true, half_day_session: 'afternoon', start_date: '2026-11-16', end_date: '2026-11-16' });
  });
  it('emergency toggle shows helper text, prefills today, and defers the certificate; server proof_due_date is surfaced', async () => {
    mock.onPost('/leave/apply').reply(200, lr({ id: 22, is_emergency: true, proof_due_date: '2026-11-17' }));
    await open();
    expect(screen.queryByTestId('emergency-help')).toBeNull();
    await fireEvent(screen.getByTestId('toggle-emergency'), 'valueChange', true);
    expect(screen.getByTestId('emergency-help')).toHaveTextContent(/medical certificate/);
    expect(screen.getByTestId('input-start').props.value).toBe('2026-11-13');
    await fill({ type: 2, start: '2026-11-11', end: '2026-11-14', reason: 'Fever' });
    expect(screen.getByTestId('proof-deferred')).toBeTruthy();
    await fireEvent.press(screen.getByTestId('submit-leave'));
    expect(await screen.findByTestId('leave-notice')).toHaveTextContent(/Upload your proof by 17 Nov/);
    expect(JSON.parse(applyPosts()[0].data)).toMatchObject({ is_emergency: true, start_date: '2026-11-11', attachment_url: null });
  });
  it('shows the server back-date window rejection', async () => {
    mock.onPost('/leave/apply').reply(400, { detail: 'Emergency leave can be back-dated at most 3 day(s) (earliest 2026-11-10)' });
    await open();
    await fireEvent(screen.getByTestId('toggle-emergency'), 'valueChange', true);
    await fill({ type: 1, start: '2026-11-01', end: '2026-11-01', reason: 'x' });
    await fireEvent.press(screen.getByTestId('submit-leave'));
    expect(await screen.findByTestId('apply-error')).toHaveTextContent(/back-dated at most 3/);
  });
  it('uploads the attached certificate first, then applies with the stored filename', async () => {
    mockPerm.mockResolvedValue({ granted: true });
    mockCamera.mockResolvedValue({ canceled: false, assets: [{ uri: 'file:///c.jpg', fileName: 'c.jpg', mimeType: 'image/jpeg', fileSize: 2000 }] });
    mock.onPost('/leave/attachments').reply(200, { attachment_url: 'abc123.jpg' });
    mock.onPost('/leave/apply').reply(200, lr({ id: 23 }));
    await open();
    await fill({ type: 2, start: '2026-11-16', end: '2026-11-18', reason: 'Fever' });
    await fireEvent.press(screen.getByTestId('attach-camera'));
    expect(await screen.findByTestId('attachment-name')).toHaveTextContent('c.jpg');
    await fireEvent.press(screen.getByTestId('submit-leave'));
    await waitFor(() => expect(applyPosts()).toHaveLength(1));
    expect(JSON.parse(applyPosts()[0].data).attachment_url).toBe('abc123.jpg');
  });
  it('explains a denied camera permission', async () => {
    mockPerm.mockResolvedValue({ granted: false });
    await open();
    await fill({ type: 2, start: '2026-11-16', end: '2026-11-18', reason: 'Fever' });
    await fireEvent.press(screen.getByTestId('attach-camera'));
    expect(await screen.findByTestId('attach-pick-error')).toHaveTextContent(/Camera access is off/);
  });
});

describe('proof + cancel', () => {
  const owed = lr({ id: 30, leave_type: sick, is_emergency: true, status: 'approved', proof_due_date: '2026-11-16' });
  it('shows the proof-due badge and uploads via /leave/attachments then /leave/{id}/proof', async () => {
    mock.onGet('/leave/my').reply(200, [owed]);
    mockDoc.mockResolvedValue({ canceled: false, assets: [{ uri: 'file:///p.pdf', name: 'p.pdf', mimeType: 'application/pdf', size: 5000 }] });
    mock.onPost('/leave/attachments').reply(200, { attachment_url: 'zzz.pdf' });
    mock.onPost('/leave/30/proof').reply(200, { ...owed, proof_submitted_at: '2026-11-13T00:00:00' });
    await renderWithProviders(<LeaveScreen now={NOW} />);
    expect(await screen.findByTestId('proof-due-30')).toHaveTextContent('Proof due by 16 Nov');
    mock.onGet('/leave/my').reply(200, [{ ...owed, proof_submitted_at: '2026-11-13T00:00:00' }]);
    await fireEvent.press(screen.getByTestId('proof-30-file'));
    await waitFor(() => expect(mock.history.post.some((r) => r.url === '/leave/30/proof')).toBe(true));
    expect(JSON.parse(mock.history.post.find((r) => r.url === '/leave/30/proof')!.data)).toEqual({ attachment_url: 'zzz.pdf' });
    await waitFor(() => expect(screen.queryByTestId('proof-due-30')).toBeNull());
  });
  it('shows no proof prompt once converted to LOP', async () => {
    mock.onGet('/leave/my').reply(200, [{ ...owed, converted_to_lop_at: '2026-11-17T00:00:00' }]);
    await renderWithProviders(<LeaveScreen now={NOW} />);
    expect(await screen.findByTestId('leave-lop-30')).toBeTruthy();
    expect(screen.queryByTestId('proof-due-30')).toBeNull();
  });
  it('cancels a pending request after confirmation, only when submitted', async () => {
    mock.onGet('/leave/my').reply(200, [lr({ id: 40 }), lr({ id: 41, status: 'approved' })]);
    mock.onPost('/leave/40/cancel').reply(200, lr({ id: 40, status: 'cancelled' }));
    await renderWithProviders(<LeaveScreen now={NOW} />);
    expect(await screen.findByTestId('cancel-40')).toBeTruthy();
    expect(screen.queryByTestId('cancel-41')).toBeNull();
    await fireEvent.press(screen.getByTestId('cancel-40'));
    expect(mock.history.post).toHaveLength(0);
    mock.onGet('/leave/my').reply(200, [lr({ id: 40, status: 'cancelled' })]);
    await fireEvent.press(screen.getByTestId('cancel-confirm-40'));
    await waitFor(() => expect(mock.history.post.map((r) => r.url)).toEqual(['/leave/40/cancel']));
    await waitFor(() => expect(screen.getByTestId('leave-status-40')).toHaveTextContent('Cancelled'));
  });
  it('shows a cancel error from the server', async () => {
    mock.onGet('/leave/my').reply(200, [lr({ id: 40 })]);
    mock.onPost('/leave/40/cancel').reply(400, { detail: 'Cannot cancel leave in approved status' });
    await renderWithProviders(<LeaveScreen now={NOW} />);
    await fireEvent.press(await screen.findByTestId('cancel-40'));
    await fireEvent.press(screen.getByTestId('cancel-confirm-40'));
    expect(await screen.findByTestId('leave-error-40')).toHaveTextContent(/Cannot cancel/);
  });
});

describe('guards', () => {
  const uploads = () => mock.history.post.filter((r) => r.url === '/leave/attachments');

  it('drops the attachment when the type changes so a hidden invalid file cannot block or leak into submit', async () => {
    mockDoc.mockResolvedValue({ canceled: false, assets: [{ uri: 'file:///bad.doc', name: 'bad.doc', mimeType: 'application/msword', size: 10 }] });
    mock.onPost('/leave/apply').reply(200, lr({ id: 50 }));
    await open();
    await fill({ type: 2, start: '2026-11-16', end: '2026-11-18', reason: 'Fever' });
    await fireEvent.press(screen.getByTestId('attach-file'));
    expect(await screen.findByTestId('attachment-name')).toHaveTextContent('bad.doc');
    await fireEvent.press(screen.getByTestId('type-1')); // Casual: no certificate rule
    expect(screen.queryByTestId('attachment-name')).toBeNull();
    await fireEvent.press(screen.getByTestId('submit-leave'));
    await waitFor(() => expect(applyPosts()).toHaveLength(1));
    expect(uploads()).toHaveLength(0);
    expect(JSON.parse(applyPosts()[0].data).attachment_url).toBeNull();
  });

  it('a double tap submits once', async () => {
    mock.onPost('/leave/apply').reply(() => new Promise((res) => setTimeout(() => res([200, lr({ id: 51 })]), 20)));
    await open();
    await fill({ type: 1, start: '2026-11-16', end: '2026-11-16', reason: 'x' });
    const btn = screen.getByTestId('submit-leave');
    await act(async () => { void fireEvent.press(btn); void fireEvent.press(btn); }); // both taps land before any re-render can disable the button
    await screen.findByTestId('leave-notice');
    expect(applyPosts()).toHaveLength(1);
  });

  it('retrying after a failed apply reuses the uploaded attachment', async () => {
    mockPerm.mockResolvedValue({ granted: true });
    mockCamera.mockResolvedValue({ canceled: false, assets: [{ uri: 'file:///c.jpg', fileName: 'c.jpg', mimeType: 'image/jpeg', fileSize: 2000 }] });
    mock.onPost('/leave/attachments').reply(200, { attachment_url: 'abc123.jpg' });
    mock.onPost('/leave/apply').replyOnce(400, { detail: 'Insufficient leave balance' }).onPost('/leave/apply').reply(200, lr({ id: 52 }));
    await open();
    await fill({ type: 2, start: '2026-11-16', end: '2026-11-18', reason: 'Fever' });
    await fireEvent.press(screen.getByTestId('attach-camera'));
    await screen.findByTestId('attachment-name');
    await fireEvent.press(screen.getByTestId('submit-leave'));
    expect(await screen.findByTestId('apply-error')).toHaveTextContent(/Insufficient/);
    await fireEvent.press(screen.getByTestId('submit-leave'));
    await screen.findByTestId('leave-notice');
    expect(uploads()).toHaveLength(1);
    expect(applyPosts()).toHaveLength(2);
    expect(JSON.parse(applyPosts()[1].data).attachment_url).toBe('abc123.jpg');
  });
});
