import { addDays, canActOnDay, isWeekOffDay, monthWeekStarts, sameShift, validateSwap, weekStartOf } from '../src/features/schedule/dates';
import type { RosterDay, SwapCandidate } from '../src/api/types';

const day = (o: Omit<Partial<RosterDay>, 'shift'> & { shift?: Partial<RosterDay['shift']> } = {}): RosterDay => ({
  date: '2026-11-16', is_today: false, holiday_name: null, on_leave: false, leave_type: null,
  ...o,
  shift: { name: 'Morning', start_time: '09:00', end_time: '17:00', is_overnight: false, source: 'roster', shift_template_id: 3, ...o.shift },
});
const cand = (o: Partial<SwapCandidate> = {}): SwapCandidate => ({ user_id: 5, name: 'Asha', shift_template_id: 4, shift_name: 'Evening', is_week_off: false, ...o });

describe('date windows', () => {
  it('addDays crosses month/year boundaries', () => {
    expect(addDays('2026-12-30', 3)).toBe('2027-01-02');
    expect(addDays('2026-03-01', -1)).toBe('2026-02-28');
  });
  it('weekStartOf returns the Monday', () => {
    expect(weekStartOf('2026-11-16')).toBe('2026-11-16'); // Monday
    expect(weekStartOf('2026-11-22')).toBe('2026-11-16'); // Sunday
    expect(weekStartOf('2026-11-13')).toBe('2026-11-09'); // Friday
  });
  it('monthWeekStarts covers every day of the month', () => {
    // Nov 2026: 1st is a Sunday, 30th a Monday -> weeks starting Oct 26 .. Nov 30
    expect(monthWeekStarts('2026-11')).toEqual(['2026-10-26', '2026-11-02', '2026-11-09', '2026-11-16', '2026-11-23', '2026-11-30']);
    expect(monthWeekStarts('2027-02')).toEqual(['2027-02-01', '2027-02-08', '2027-02-15', '2027-02-22']);
  });
});

describe('day actions', () => {
  it('only a published roster shift today or later can be swapped / given away', () => {
    expect(canActOnDay(day(), '2026-11-16')).toBe(true);
    expect(canActOnDay(day(), '2026-11-17')).toBe(false); // past
    expect(canActOnDay(day({ shift: { source: 'assigned' } }), '2026-11-16')).toBe(false);
    expect(canActOnDay(day({ shift: { source: 'default' } }), '2026-11-16')).toBe(false);
    expect(canActOnDay(day({ on_leave: true }), '2026-11-16')).toBe(false);
    expect(canActOnDay(day({ shift: { name: 'Week off', start_time: null, end_time: null } }), '2026-11-16')).toBe(false);
  });
  it('week off: explicit roster week off, or a Sunday without a published shift', () => {
    expect(isWeekOffDay(day({ shift: { name: 'Week off', start_time: null } }))).toBe(true);
    expect(isWeekOffDay(day({ is_weekend: true, shift: { source: 'assigned' } }))).toBe(true);
    expect(isWeekOffDay(day({ is_weekend: true }))).toBe(false); // roster shift wins
  });
});

describe('swap validation', () => {
  const today = '2026-11-13';
  const base = { date: '2026-11-16', today, pick: 5, cands: [cand()], mine: { shiftTemplateId: 3, shiftName: 'Morning', isWeekOff: false }, otherDay: false, returnDate: '' };
  it('requires a colleague', () => {
    expect(validateSwap({ ...base, pick: null })).toMatch(/colleague/i);
    expect(validateSwap(base)).toBeNull();
  });
  it('rejects a colleague on the same shift', () => {
    expect(validateSwap({ ...base, cands: [cand({ shift_template_id: 3, shift_name: 'Morning' })] })).toMatch(/colleague/i);
    expect(sameShift(cand({ shift_template_id: 3 }), base.mine)).toBe(true);
    expect(sameShift(cand({ is_week_off: true, shift_template_id: null, shift_name: null }), base.mine)).toBe(false);
    expect(sameShift(cand({ is_week_off: true }), { ...base.mine, isWeekOff: true })).toBe(true);
  });
  it('return date must be in [today, today+90], differ from the date and be within 14 days of it', () => {
    const v = (returnDate: string) => validateSwap({ ...base, otherDay: true, returnDate });
    expect(v('')).toMatch(/return date/i);
    expect(v('2026-11-16')).toMatch(/return date/i); // same day
    expect(v('2026-11-12')).toMatch(/return date/i); // past
    expect(v('2027-02-20')).toMatch(/return date/i); // > 90 days
    expect(v('2026-12-01')).toMatch(/14 days/); // 15 days from 16 Nov
    expect(v('2026-11-20')).toBeNull();
    expect(v('not-a-date')).toMatch(/return date/i);
  });
});

import { ruleText, toAvailabilityInput, validateAvailability, EMPTY_AVAILABILITY } from '../src/features/schedule/availability';
describe('availability rules', () => {
  const T = '2026-11-13';
  it('validates like the backend', () => {
    expect(validateAvailability({ ...EMPTY_AVAILABILITY, kind: 'preferred' }, T)).toMatch(/shift you prefer/);
    expect(validateAvailability({ ...EMPTY_AVAILABILITY, mode: 'date', specificDate: '' }, T)).toMatch(/YYYY-MM-DD/);
    expect(validateAvailability({ ...EMPTY_AVAILABILITY, mode: 'date', specificDate: '2026-11-12' }, T)).toMatch(/past/);
    expect(validateAvailability({ ...EMPTY_AVAILABILITY, validFrom: '2026-12-02', validTo: '2026-12-01' }, T)).toMatch(/on or before/);
    expect(validateAvailability({ ...EMPTY_AVAILABILITY, weekday: 2 }, T)).toBeNull();
  });
  it('sends exactly one of weekday / specific_date and drops bounds on date rules', () => {
    expect(toAvailabilityInput({ ...EMPTY_AVAILABILITY, weekday: 2, validFrom: '2026-12-01', note: ' x ' })).toEqual({ kind: 'unavailable', weekday: 2, specific_date: null, shift_template_id: null, valid_from: '2026-12-01', valid_to: null, note: 'x' });
    expect(toAvailabilityInput({ ...EMPTY_AVAILABILITY, mode: 'date', specificDate: '2026-11-20', validFrom: '2026-12-01' })).toMatchObject({ weekday: null, specific_date: '2026-11-20', valid_from: null });
  });
  it('describes rules', () => {
    const r = { id: 1, kind: 'preferred' as const, weekday: 0, specific_date: null, shift_template_id: 3, valid_from: null, valid_to: null, note: null };
    expect(ruleText(r, [{ id: 3, name: 'Morning' }])).toBe('Prefers Morning on Mon');
    expect(ruleText({ ...r, kind: 'unavailable', shift_template_id: null }, [])).toBe('Unavailable every Mon');
  });
});

import { monthName } from '../src/features/schedule/dates';
it('monthName', () => { expect(monthName('2026-11')).toBe('November 2026'); expect(monthName('2027-01')).toBe('January 2027'); });
