import { approvedBannerText, approvedToday, canCancel, fmtRange } from '../src/features/work-location/logic';
import { buildRequestPayload, isIsoDate, validateRequest, type RequestFormValues } from '../src/features/work-location/validation';
import type { WorkLocationRequest } from '../src/features/work-location/api';

const base: RequestFormValues = { kind: 'wfh', start: '2026-11-20', end: '2026-11-20', portion: 'full', place: '', purpose: 'Plumber visit' };
const req = (o: Partial<WorkLocationRequest>): WorkLocationRequest => ({ id: 1, kind: 'wfh', start_date: '2026-11-20', end_date: '2026-11-20', day_portion: 'full', place: null, purpose: 'x', status: 'pending', decision_note: null, ...o });

describe('validateRequest', () => {
  it('accepts a valid WFH request without a place', () => expect(validateRequest(base)).toEqual({}));
  it('requires dates in order and in format', () => {
    expect(validateRequest({ ...base, start: '' }).start).toBeTruthy();
    expect(validateRequest({ ...base, start: '2026-02-30' }).start).toMatch(/YYYY-MM-DD/);
    expect(validateRequest({ ...base, end: '2026-11-19' }).end).toMatch(/before/);
  });
  it('requires a place for on duty and client visit only', () => {
    expect(validateRequest({ ...base, kind: 'on_duty' }).place).toBeTruthy();
    expect(validateRequest({ ...base, kind: 'client_visit', place: '  ' }).place).toBeTruthy();
    expect(validateRequest({ ...base, kind: 'client_visit', place: 'Acme' })).toEqual({});
  });
  it('requires a purpose', () => expect(validateRequest({ ...base, purpose: ' ' }).purpose).toBeTruthy());
  it('allows a half day only for a single date', () => {
    expect(validateRequest({ ...base, portion: 'first_half' })).toEqual({});
    expect(validateRequest({ ...base, end: '2026-11-21', portion: 'first_half' }).portion).toBeTruthy();
  });
  it('isIsoDate is strict', () => { expect(isIsoDate('2026-11-20')).toBe(true); expect(isIsoDate('2026-13-01')).toBe(false); expect(isIsoDate('20-11-2026')).toBe(false); });
});

describe('buildRequestPayload', () => {
  it('sends only the fields the backend accepts', () => {
    expect(buildRequestPayload({ ...base, kind: 'on_duty', place: ' Acme ', purpose: ' Audit ' })).toEqual({ kind: 'on_duty', start_date: '2026-11-20', end_date: '2026-11-20', day_portion: 'full', place: 'Acme', purpose: 'Audit' });
  });
  it('forces a full day for a range and nulls an empty optional place', () => {
    expect(buildRequestPayload({ ...base, end: '2026-11-22', portion: 'second_half' })).toMatchObject({ day_portion: 'full', place: null });
  });
});

describe('request logic (org-local today, date-only strings)', () => {
  it('cancel is disabled once the start date has passed, and for finished statuses', () => {
    expect(canCancel(req({ start_date: '2026-11-20' }), '2026-11-20')).toBe(true);
    expect(canCancel(req({ start_date: '2026-11-19', end_date: '2026-11-25' }), '2026-11-20')).toBe(false);
    expect(canCancel(req({ status: 'rejected' }), '2026-11-01')).toBe(false);
    expect(canCancel(req({ status: 'approved' }), '2026-11-01')).toBe(true);
  });
  it('the banner needs an APPROVED request covering today; pending never relaxes anything', () => {
    const range = { start_date: '2026-11-19', end_date: '2026-11-21' };
    expect(approvedToday([req({ ...range, status: 'pending' })], '2026-11-20')).toBeNull();
    expect(approvedToday([req({ ...range, status: 'rejected' })], '2026-11-20')).toBeNull();
    expect(approvedToday([req({ ...range, status: 'approved' })], '2026-11-22')).toBeNull();
    const hit = approvedToday([req({ ...range, status: 'approved', kind: 'client_visit' })], '2026-11-20');
    expect(hit && approvedBannerText(hit)).toBe('Approved Client visit today — location check relaxed');
    expect(approvedBannerText(req({ kind: 'wfh' }))).toBe('Approved Work from home today — location check relaxed');
  });
  it('formats date-only ranges without a zone shift', () => {
    expect(fmtRange(req({ start_date: '2026-11-20', end_date: '2026-11-22' }))).toBe('20 Nov – 22 Nov');
    expect(fmtRange(req({ day_portion: 'first_half' }))).toBe('20 Nov (first half)');
  });
});
