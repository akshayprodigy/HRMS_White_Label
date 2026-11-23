import { DEFAULT_ACTION_ID, routeResponse } from '../src/features/push/routing';

const tap = (data: unknown) => routeResponse({ actionIdentifier: DEFAULT_ACTION_ID, notification: { request: { content: { data } } } });

describe('phase 6A notification routes', () => {
  it.each([
    ['optional_holiday_decided', 'optional_holiday', '/holidays'],
    ['work_location_decided', 'work_location', '/work-location'],
    ['work_location_cancelled', 'work_location', '/work-location'],
    ['work_location_submitted', 'work_location', '/approvals'],
    ['optional_holiday_submitted', 'optional_holiday', '/approvals'],
  ])('%s opens the matching screen (submitted goes to the Approvals tab)', (event_type, resource_type, href) => {
    expect(tap({ notification_id: 1, event_type, resource_type, resource_id: '4', category: 'none' })).toEqual({ kind: 'open', href, refreshBroadcasts: false });
  });
  it('an actionable approval notification still opens the approvals queue', () => {
    expect(tap({ notification_id: 1, event_type: 'work_location_submitted', resource_type: 'work_location', resource_id: '4', category: 'approval' })).toMatchObject({ href: '/approvals' });
  });
});
