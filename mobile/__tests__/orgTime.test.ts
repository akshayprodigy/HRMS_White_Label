import type MockAdapter from 'axios-mock-adapter';
import { formatOrgTime, loadOrgTime, orgToday, orgTimezone, resetOrgTimeForTests } from '../src/lib/org-time';
import { setupApiMock, teardownApiMock } from '../test-utils';

jest.mock('../src/config/tenant', () => ({ getTenant: () => ({ ...require('../tenants/dev/tenant.json'), id: 'dev' }), getApiBaseUrl: () => 'http://test/api/v1' }));

let mock: MockAdapter;
beforeEach(() => { resetOrgTimeForTests(); mock = setupApiMock(); });
afterEach(async () => { resetOrgTimeForTests(); await teardownApiMock(); });

describe('org time', () => {
  it('falls back to UTC before load', () => {
    mock.onGet('/meta/org-time').reply(500);
    expect(orgTimezone()).toBe('UTC');
  });
  it('loads once, then computes org-local today and time (not the device zone)', async () => {
    mock.onGet('/meta/org-time').reply(200, { timezone: 'Asia/Kolkata', utc_offset_minutes: 330, today: '2026-11-20' });
    await loadOrgTime();
    await loadOrgTime();
    expect(mock.history.get.length).toBe(1);
    expect(orgTimezone()).toBe('Asia/Kolkata');
    // 20:00Z on the 20th is already the 21st in IST.
    expect(orgToday(new Date('2026-11-20T20:00:00Z'))).toBe('2026-11-21');
    expect(formatOrgTime('2026-11-20T20:00:00Z')).toBe('01:30');
    expect(formatOrgTime('2026-11-20T20:00:00')).toBe('01:30'); // zone-less server timestamps are UTC
    expect(formatOrgTime('garbage')).toBe('');
  });
  it('rejects an invalid zone', async () => {
    mock.onGet('/meta/org-time').reply(200, { timezone: 'Not/AZone', utc_offset_minutes: 0, today: '2026-11-20' });
    expect(await loadOrgTime()).toBeNull();
    expect(orgTimezone()).toBe('UTC');
  });
});
