import { DEFAULT_ACTION_ID, hrefFor, parsePushData, routeResponse } from '../src/features/push/routing';

const resp = (data: unknown, actionIdentifier = DEFAULT_ACTION_ID) => ({ actionIdentifier, notification: { request: { content: { data } } } });
const approval = { notification_id: 5, event_type: 'leave_request', resource_type: 'leave', resource_id: '12', category: 'approval' };
const chain = { ...approval, resource_type: 'chained_approval_instance', resource_id: '77' };
const shift = { notification_id: 6, resource_type: 'open_shift', resource_id: '3', category: 'open_shift' };
const safety = { notification_id: 7, resource_type: 'broadcast', resource_id: '9', category: 'broadcast_safety' };
const ack = { ...safety, category: 'broadcast_ack' };

describe('routeResponse: buttons', () => {
  it.each([
    ['approve', approval], ['reject', approval], ['claim', shift], ['safe', safety], ['acknowledge', ack],
  ])('%s runs in the background via the actions endpoint', (action, data) => {
    expect(routeResponse(resp(data, action))).toEqual({ kind: 'action', notification_id: data.notification_id, action });
  });
  it('need_help opens the app (note entry) instead of acting', () => {
    expect(routeResponse(resp(safety, 'need_help'))).toEqual({ kind: 'open', href: '/home', refreshBroadcasts: true });
  });
  it('accepts a stringified notification_id', () => {
    expect(routeResponse(resp({ ...approval, notification_id: '5' }, 'approve'))).toMatchObject({ kind: 'action', notification_id: 5 });
  });
  it('ignores buttons the category does not offer, unknown ids and missing/invalid ids', () => {
    expect(routeResponse(resp(approval, 'claim'))).toEqual({ kind: 'ignore' });
    expect(routeResponse(resp(safety, 'approve'))).toEqual({ kind: 'ignore' });
    expect(routeResponse(resp({ ...approval, category: 'none' }, 'approve'))).toEqual({ kind: 'ignore' });
    expect(routeResponse(resp(approval, 'expo.modules.notifications.actions.DISMISS'))).toEqual({ kind: 'ignore' });
    expect(routeResponse(resp({ ...approval, notification_id: undefined }, 'approve'))).toEqual({ kind: 'ignore' });
    expect(routeResponse(resp({ ...approval, notification_id: 'abc' }, 'approve'))).toEqual({ kind: 'ignore' });
    expect(routeResponse(resp({ ...approval, category: 'bogus' }, 'approve'))).toEqual({ kind: 'ignore' });
  });
  it('ignores null / empty responses and non-object data on buttons', () => {
    expect(routeResponse(null)).toEqual({ kind: 'ignore' });
    expect(routeResponse(undefined)).toEqual({ kind: 'ignore' });
    expect(routeResponse(resp('junk', 'approve'))).toEqual({ kind: 'ignore' });
    expect(routeResponse({ actionIdentifier: 'approve' })).toEqual({ kind: 'ignore' });
  });
});

describe('routeResponse: taps (deep links)', () => {
  it('chained approval -> detail route', () => {
    expect(routeResponse(resp(chain))).toEqual({ kind: 'open', href: '/approval/chain-77', refreshBroadcasts: false });
  });
  it('legacy approval -> approvals queue (its id is not the item key)', () => {
    expect(routeResponse(resp(approval))).toMatchObject({ href: '/approvals' });
  });
  it('open shift -> Schedule Open sub-view', () => {
    expect(routeResponse(resp(shift))).toMatchObject({ href: '/schedule?section=open' });
  });
  it('broadcast -> home, forcing a broadcast refresh', () => {
    expect(routeResponse(resp(safety))).toEqual({ kind: 'open', href: '/home', refreshBroadcasts: true });
    expect(routeResponse(resp(ack))).toMatchObject({ refreshBroadcasts: true });
  });
  it('anything else, or garbage data, -> home', () => {
    expect(routeResponse(resp({ category: 'none', resource_type: 'payslip', resource_id: '1' }))).toMatchObject({ href: '/home', refreshBroadcasts: false });
    expect(routeResponse(resp(null))).toMatchObject({ kind: 'open', href: '/home' });
    expect(routeResponse({})).toMatchObject({ kind: 'open', href: '/home' });
  });
  it('rejects a non-numeric chained id (no route injection)', () => {
    expect(hrefFor(parsePushData({ ...chain, resource_id: '../x' }))).toBe('/approvals');
  });
});

describe('routeResponse: per-user binding', () => {
  const mine = { ...approval, user_id: 1 };
  it('acts / deep-links when the recipient matches or the push has no user_id (older backend)', () => {
    expect(routeResponse(resp(mine, 'approve'), 1)).toMatchObject({ kind: 'action' });
    expect(routeResponse(resp(approval, 'approve'), 1)).toMatchObject({ kind: 'action' });
    expect(routeResponse(resp(chain), 1)).toMatchObject({ href: '/approval/chain-77' });
    expect(routeResponse(resp({ ...mine, user_id: '1' }, 'approve'), 1)).toMatchObject({ kind: 'action' });
  });
  it("ignores another user's buttons and sends their taps to /home", () => {
    expect(routeResponse(resp(mine, 'approve'), 2)).toEqual({ kind: 'ignore' });
    expect(routeResponse(resp({ ...chain, user_id: 1 }), 2)).toEqual({ kind: 'open', href: '/home', refreshBroadcasts: false });
  });
});
