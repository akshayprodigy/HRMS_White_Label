import { buildApplyPayload, certRequired, leaveDays, validateLeaveForm, type LeaveFormValues } from '../src/features/leave/validation';
import type { LeaveType } from '../src/features/leave/api';

const TODAY = '2026-11-13';
const sick: LeaveType = { id: 2, name: 'Sick', allow_half_day: true, requires_medical_cert_after: 3, unpaid_allowed: false };
const noHalf: LeaveType = { id: 3, name: 'Privilege', allow_half_day: false, requires_medical_cert_after: null, unpaid_allowed: false };
const base: LeaveFormValues = { typeId: 2, start: '2026-11-16', end: '2026-11-16', halfDay: false, session: 'morning', reason: 'Fever', emergency: false, emergencyContact: '', attachment: null };
const v = (o: Partial<LeaveFormValues>): LeaveFormValues => ({ ...base, ...o });

describe('leaveDays', () => {
  it('counts inclusive days, half day is 0.5, invalid is 0', () => {
    expect(leaveDays('2026-11-16', '2026-11-18', false)).toBe(3);
    expect(leaveDays('2026-11-16', '2026-11-16', true)).toBe(0.5);
    expect(leaveDays('2026-11-18', '2026-11-16', false)).toBe(0);
    expect(leaveDays('', '2026-11-16', false)).toBe(0);
    expect(leaveDays('2026-02-30', '2026-03-02', false)).toBe(0);
  });
});

describe('certRequired', () => {
  it('only when the type rule applies and the leave is not emergency (emergency defers proof)', () => {
    expect(certRequired(sick, 3, false)).toBe(true);
    expect(certRequired(sick, 2, false)).toBe(false);
    expect(certRequired(sick, 5, true)).toBe(false);
    expect(certRequired(noHalf, 30, false)).toBe(false);
    expect(certRequired(undefined, 5, false)).toBe(false);
  });
});

describe('validateLeaveForm', () => {
  it('accepts a valid single-day request', () => {
    expect(validateLeaveForm(v({}), sick, TODAY)).toEqual({});
  });
  it('requires type, dates and reason', () => {
    const e = validateLeaveForm(v({ typeId: null, start: '', end: '', reason: '  ' }), undefined, TODAY);
    expect(e).toMatchObject({ type: expect.any(String), start: expect.any(String), end: expect.any(String), reason: expect.any(String) });
  });
  it('rejects malformed dates and end before start', () => {
    expect(validateLeaveForm(v({ start: '16/11/2026' }), sick, TODAY).start).toMatch(/YYYY-MM-DD/);
    expect(validateLeaveForm(v({ start: '2026-11-17', end: '2026-11-16' }), sick, TODAY).end).toMatch(/before/);
  });
  it('half day must be a single day and the type must allow it', () => {
    expect(validateLeaveForm(v({ halfDay: true, end: '2026-11-17' }), sick, TODAY).half).toMatch(/single day/);
    expect(validateLeaveForm(v({ halfDay: true }), noHalf, TODAY).half).toMatch(/does not allow half-day/);
    expect(validateLeaveForm(v({ halfDay: true }), sick, TODAY)).toEqual({});
  });
  it('requires a certificate for long sick leave, but not when emergency', () => {
    const long = { end: '2026-11-18' };
    expect(validateLeaveForm(v(long), sick, TODAY).attachment).toMatch(/medical certificate/);
    expect(validateLeaveForm(v({ ...long, emergency: true }), sick, TODAY).attachment).toBeUndefined();
    expect(validateLeaveForm(v({ ...long, attachment: { uri: 'file:///a.pdf', name: 'a.pdf', mimeType: 'application/pdf', size: 1000 } }), sick, TODAY)).toEqual({});
  });
  it('rejects unsupported or oversized attachments', () => {
    const bad = validateLeaveForm(v({ attachment: { uri: 'x', name: 'a.doc', mimeType: 'application/msword', size: 10 } }), sick, TODAY);
    expect(bad.attachment).toMatch(/PDF, JPEG/);
    const big = validateLeaveForm(v({ attachment: { uri: 'x', name: 'a.pdf', mimeType: 'application/pdf', size: 11 * 1024 * 1024 } }), sick, TODAY);
    expect(big.attachment).toMatch(/10 MB/);
  });
  it('emergency leave may start today or in the past, capped at the 31-day server maximum', () => {
    expect(validateLeaveForm(v({ emergency: true, start: TODAY, end: TODAY }), sick, TODAY)).toEqual({});
    expect(validateLeaveForm(v({ emergency: true, start: '2026-11-11', end: '2026-11-11' }), sick, TODAY)).toEqual({});
    expect(validateLeaveForm(v({ emergency: true, start: '2026-10-01', end: '2026-10-01' }), sick, TODAY).start).toMatch(/31 days/);
  });
});

describe('buildApplyPayload', () => {
  it('maps to the /leave/apply body', () => {
    expect(buildApplyPayload(v({ emergency: true, emergencyContact: ' 99 ', reason: ' Fever ' }), 'abc.pdf')).toEqual({
      leave_type_id: 2, start_date: '2026-11-16', end_date: '2026-11-16', reason: 'Fever', emergency_contact: '99',
      is_half_day: false, half_day_session: null, attachment_url: 'abc.pdf', is_emergency: true,
    });
  });
  it('sends session only for half day and forces end = start', () => {
    expect(buildApplyPayload(v({ halfDay: true, session: 'afternoon', end: '2026-11-20' }), null)).toMatchObject({
      is_half_day: true, half_day_session: 'afternoon', end_date: '2026-11-16', attachment_url: null, emergency_contact: null,
    });
  });
});
