import { fireEvent, screen, waitFor } from '@testing-library/react-native';
import type MockAdapter from 'axios-mock-adapter';
import { ApprovalDetail } from '../src/features/approvals/ApprovalDetail';
import { ApprovalsScreen } from '../src/features/approvals/ApprovalsScreen';
import { mergeApprovals } from '../src/features/approvals/api';
import { hasApproverRole } from '../src/features/approvals/hooks';
import { GATE_BODY, renderWithProviders, setupApiMock, teardownApiMock } from '../test-utils';

jest.mock('../src/config/tenant', () => ({
  getTenant: () => ({ ...require('../tenants/dev/tenant.json'), id: 'dev' }),
  getApiBaseUrl: () => 'http://test/api/v1',
}));
jest.mock('react-native-safe-area-context', () => ({ useSafeAreaInsets: () => ({ top: 0, bottom: 0, left: 0, right: 0 }) }));
const mockPush = jest.fn();
const mockBack = jest.fn();
let mockParams: { key?: string } = {};
jest.mock('expo-router', () => ({
  useRouter: () => ({ navigate: jest.fn(), push: mockPush, back: mockBack, replace: jest.fn() }),
  useLocalSearchParams: () => mockParams,
}));

const chain = [{
  step_instance: { id: 5, step_order: 1, label: 'Manager', approver_type: 'user' },
  instance: { id: 11, entity_type: 'expense', submitter_id: 7, amount_paise: 250000, created_at: '2026-11-10T08:00:00' },
  entity: { kind: 'expense', title: 'Client dinner', line_count: 2, out_of_policy_count: 1 },
  due_at: '2026-11-11T08:00:00', is_overdue: true, acting_for: null,
}];
const legacy = [
  { id: 21, resource_type: 'leave', resource_id: '88', status: 'pending', current_step_number: 1, requested_by_id: 3, requested_by_name: 'Asha', created_at: '2026-11-12T08:00:00', due_date: null, due_at: null, is_overdue: false, acting_for: { user_id: 4, name: 'Ravi' }, steps: [{ step_number: 1, status: 'pending' }] },
  { id: 22, resource_type: 'comp_off', resource_id: '9', status: 'pending', current_step_number: 1, requested_by_id: 3, requested_by_name: 'Asha', created_at: '2026-11-12T09:00:00', due_date: null, due_at: null, is_overdue: false, acting_for: null },
];

let mock: MockAdapter;
beforeEach(() => {
  mock = setupApiMock();
  mockPush.mockClear();
  mockBack.mockClear();
  mock.onGet('/approval-chains/my-queue').reply(200, chain);
  mock.onGet('/approvals/inbox').reply(200, legacy);
});
afterEach(teardownApiMock);

describe('merge + access', () => {
  it('puts overdue first and maps both sources', () => {
    const cards = mergeApprovals(chain as never, legacy as never);
    expect(cards.map((c) => c.key)).toEqual(['chain-11', 'legacy-21', 'legacy-22']);
    expect(cards[0]).toMatchObject({ overdue: true, title: 'Client dinner', kind: 'expense' });
    expect(cards[1]).toMatchObject({ actingFor: 'Ravi', requester: 'Asha' });
  });
  it('detects approvers by superuser, role name or approve permission', () => {
    expect(hasApproverRole({ id: 1, email: 'a', is_superuser: true })).toBe(true);
    expect(hasApproverRole({ id: 1, email: 'a', roles: [{ name: 'PM' }] })).toBe(true);
    expect(hasApproverRole({ id: 1, email: 'a', roles: [{ name: 'Dev', permissions: [{ name: 'leave approve' }] }] })).toBe(true);
    expect(hasApproverRole({ id: 1, email: 'a', roles: [{ name: 'Employee', permissions: [{ name: 'employee leave read' }] }] })).toBe(false);
  });
});

describe('ApprovalsScreen', () => {
  it('lists merged items with overdue and acting-for badges', async () => {
    await renderWithProviders(<ApprovalsScreen />);
    await waitFor(() => expect(screen.getByText('Client dinner')).toBeTruthy());
    expect(screen.getByTestId('overdue-chain-11')).toBeTruthy();
    expect(screen.getByText('Acting for Ravi')).toBeTruthy();
    expect(screen.queryByTestId('overdue-legacy-21')).toBeNull();
    expect(screen.getByText('leave 88')).toBeTruthy();
    await fireEvent.press(screen.getByTestId('open-legacy-21'));
    expect(mockPush).toHaveBeenCalledWith('/approval/legacy-21');
  });

  it('shows the gate notice when both endpoints answer ATTENDANCE_REQUIRED', async () => {
    mock.reset();
    mock.onGet('/approval-chains/my-queue').reply(403, GATE_BODY);
    mock.onGet('/approvals/inbox').reply(403, GATE_BODY);
    await renderWithProviders(<ApprovalsScreen />);
    await waitFor(() => expect(screen.getByText('Punch in to see this')).toBeTruthy());
  });

  it('still lists one source when the other fails', async () => {
    mock.onGet('/approval-chains/my-queue').reply(500, {});
    await renderWithProviders(<ApprovalsScreen />);
    await waitFor(() => expect(screen.getByText('leave 88')).toBeTruthy());
    expect(screen.getByTestId('approvals-partial-error')).toBeTruthy();
  });

  it('bulk approves selected legacy items and shows a result summary with failures', async () => {
    mock.onPost('/approvals/bulk-action').reply(200, {
      results: [{ kind: 'legacy', id: 21, ok: true, error: null }, { kind: 'legacy', id: 22, ok: false, error: 'Not your step' }],
      ok_count: 1, failed_count: 1,
    });
    await renderWithProviders(<ApprovalsScreen />);
    await waitFor(() => expect(screen.getByText('leave 88')).toBeTruthy());
    expect(screen.queryByTestId('select-chain-11')).toBeNull(); // chain items are not bulk-selectable
    await fireEvent.press(screen.getByTestId('select-legacy-21'));
    await fireEvent.press(screen.getByTestId('select-legacy-22'));
    expect(screen.getByTestId('bulk-count').props.children.join('')).toBe('2 selected');
    await fireEvent.press(screen.getByTestId('bulk-approve'));
    await waitFor(() => expect(screen.getByTestId('bulk-summary').props.children).toBe('1 approved, 1 failed'));
    expect(screen.getByText('#22: Not your step')).toBeTruthy();
    expect(JSON.parse(mock.history.post[0].data)).toEqual({ items: [{ kind: 'legacy', id: 21 }, { kind: 'legacy', id: 22 }], action: 'approve', comment: null });
  });

  it('bulk reject requires confirmation', async () => {
    mock.onPost('/approvals/bulk-action').reply(200, { results: [{ kind: 'legacy', id: 21, ok: true, error: null }], ok_count: 1, failed_count: 0 });
    await renderWithProviders(<ApprovalsScreen />);
    await waitFor(() => expect(screen.getByText('leave 88')).toBeTruthy());
    await fireEvent.press(screen.getByTestId('select-legacy-21'));
    await fireEvent.press(screen.getByTestId('bulk-reject'));
    expect(mock.history.post.length).toBe(0);
    expect(screen.getByTestId('bulk-reject-confirm-text')).toBeTruthy();
    await fireEvent.press(screen.getByTestId('bulk-reject-confirm'));
    await waitFor(() => expect(screen.getByTestId('bulk-summary').props.children).toBe('1 rejected'));
    expect(JSON.parse(mock.history.post[0].data).action).toBe('reject');
  });
});

describe('ApprovalDetail', () => {
  it('approves a legacy item via /approvals/{id}/action with status+comment', async () => {
    mockParams = { key: 'legacy-21' };
    mock.onPost('/approvals/21/action').reply(200, {});
    await renderWithProviders(<ApprovalDetail />);
    await waitFor(() => expect(screen.getByTestId('detail-title')).toBeTruthy());
    await fireEvent.changeText(screen.getByLabelText('Comment (optional)'), ' looks good ');
    await fireEvent.press(screen.getByTestId('approve'));
    await waitFor(() => expect(mockBack).toHaveBeenCalled());
    expect(JSON.parse(mock.history.post[0].data)).toEqual({ status: 'approved', comment: 'looks good' });
  });

  it('approves a chain item via /approval-chains/instances/{id}/act', async () => {
    mockParams = { key: 'chain-11' };
    mock.onPost('/approval-chains/instances/11/act').reply(200, {});
    await renderWithProviders(<ApprovalDetail />);
    await waitFor(() => expect(screen.getByTestId('detail-title')).toBeTruthy());
    await fireEvent.press(screen.getByTestId('approve'));
    await waitFor(() => expect(mockBack).toHaveBeenCalled());
    expect(JSON.parse(mock.history.post[0].data)).toEqual({ action: 'approve', comment: null });
  });

  it('reject needs confirmation, then posts the per-kind payload', async () => {
    mockParams = { key: 'chain-11' };
    mock.onPost('/approval-chains/instances/11/act').reply(200, {});
    await renderWithProviders(<ApprovalDetail />);
    await waitFor(() => expect(screen.getByTestId('reject')).toBeTruthy());
    await fireEvent.press(screen.getByTestId('reject'));
    expect(mock.history.post.length).toBe(0);
    expect(screen.getByTestId('reject-confirm-text')).toBeTruthy();
    await fireEvent.press(screen.getByTestId('reject-cancel'));
    expect(mock.history.post.length).toBe(0);
    await fireEvent.press(screen.getByTestId('reject'));
    await fireEvent.press(screen.getByTestId('reject-confirm'));
    await waitFor(() => expect(mockBack).toHaveBeenCalled());
    expect(JSON.parse(mock.history.post[0].data)).toEqual({ action: 'reject', comment: null });
  });

  it('shows the SoD 403 message and keeps the item', async () => {
    mockParams = { key: 'legacy-21' };
    mock.onPost('/approvals/21/action').reply(403, { error: { code: '403', message: 'You cannot approve your own request' } });
    await renderWithProviders(<ApprovalDetail />);
    await waitFor(() => expect(screen.getByTestId('approve')).toBeTruthy());
    await fireEvent.press(screen.getByTestId('approve'));
    await waitFor(() => expect(screen.getByTestId('detail-error').props.children).toBe('You cannot approve your own request'));
    expect(mockBack).not.toHaveBeenCalled();
    await waitFor(() => expect(screen.getByTestId('detail-title')).toBeTruthy());
  });
});
