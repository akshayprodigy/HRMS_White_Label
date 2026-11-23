import type MockAdapter from 'axios-mock-adapter';
import { fmtShiftTime } from '../src/lib/time';
import { fmtOrgDate, fmtOrgTime, formatOrgTime, loadOrgTime, orgToday, orgTimezone, resetOrgTimeForTests } from '../src/lib/org-time';
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
  it('shows instants in org time/date without a zone label, and leaves date-only strings alone', async () => {
    mock.onGet('/meta/org-time').reply(200, { timezone: 'Asia/Kolkata', utc_offset_minutes: 330, today: '2026-11-20' });
    await loadOrgTime();
    expect(fmtOrgTime('2026-11-20T20:00:00Z')).toBe('01:30');
    expect(fmtOrgTime(null)).toBe('—');
    expect(fmtOrgDate('2026-11-20T20:00:00Z')).toBe('21 Nov'); // already the next day in IST
    expect(fmtOrgDate('2026-11-20')).toBe('20 Nov');
    expect(fmtShiftTime('09:00:00')).toBe('09:00');
    expect(fmtShiftTime(null)).toBe('—');
  });
  it('retries with backoff after a failure', async () => {
    jest.useFakeTimers();
    try {
      mock.onGet('/meta/org-time').replyOnce(500).onGet('/meta/org-time').reply(200, { timezone: 'Asia/Kolkata', utc_offset_minutes: 330, today: '2026-11-20' });
      expect(await loadOrgTime()).toBeNull();
      expect(mock.history.get.length).toBe(1);
      await jest.advanceTimersByTimeAsync(1999);
      expect(mock.history.get.length).toBe(1);
      await jest.advanceTimersByTimeAsync(2);
      expect(mock.history.get.length).toBe(2);
      expect(orgTimezone()).toBe('Asia/Kolkata');
    } finally {
      jest.useRealTimers();
    }
  });
  it('rejects an invalid zone', async () => {
    mock.onGet('/meta/org-time').reply(200, { timezone: 'Not/AZone', utc_offset_minutes: 0, today: '2026-11-20' });
    expect(await loadOrgTime()).toBeNull();
    expect(orgTimezone()).toBe('UTC');
  });
});
