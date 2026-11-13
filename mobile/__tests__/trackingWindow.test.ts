import type { MyStatus } from '../src/features/tracking/api';
import { decideTracking, MAX_CHECK_MS, MIN_CHECK_MS, nextCheckDelay } from '../src/features/tracking/window';

const T = (s: string) => Date.parse(`2026-11-13T${s}:00Z`);
const status = (over: Partial<MyStatus> = {}): MyStatus => ({
  required: true, consented: true, consented_at: '2026-11-01T00:00:00+00:00', active: true,
  window: { work_date: '2026-11-13', start: '2026-11-13T08:30:00+00:00', end: '2026-11-13T18:30:00+00:00', shift_start: '2026-11-13T09:00:00+00:00', shift_end: '2026-11-13T18:00:00+00:00', in_window: true },
  interval_seconds: 300, distance_filter_m: 100, ...over,
});

describe('decideTracking (mocked clock)', () => {
  it('runs inside the window and reports its end', () => {
    const d = decideTracking(status(), T('12:00'));
    expect(d).toMatchObject({ run: true, reason: 'in_window', windowEnd: T('18:30') });
  });
  it('is inclusive at both window boundaries', () => {
    expect(decideTracking(status(), T('08:30')).run).toBe(true);
    expect(decideTracking(status(), T('18:30')).run).toBe(true);
  });
  it('waits before the window and points at its start', () => {
    expect(decideTracking(status(), T('08:29'))).toMatchObject({ run: false, reason: 'before_window', changeAt: T('08:30') });
  });
  it('stops after the window ends, regardless of the stale in_window flag from the server', () => {
    expect(decideTracking(status(), T('18:31'))).toMatchObject({ run: false, reason: 'after_window' });
  });
  it('never runs when HR has not enabled it, even if consented', () => {
    expect(decideTracking(status({ required: false }), T('12:00'))).toMatchObject({ run: false, reason: 'disabled' });
  });
  it('never runs without consent', () => {
    expect(decideTracking(status({ consented: false }), T('12:00'))).toMatchObject({ run: false, reason: 'no_consent' });
  });
  it('does not run on days without a rostered shift or with a bad window', () => {
    expect(decideTracking(status({ window: null }), T('12:00')).reason).toBe('no_window');
    const w = status().window!;
    expect(decideTracking(status({ window: { ...w, end: w.start } }), T('12:00')).reason).toBe('no_window');
    expect(decideTracking(status({ window: { ...w, start: 'garbage' } }), T('12:00')).reason).toBe('no_window');
  });
  it('handles an overnight window that ends the next calendar day', () => {
    const s = status({ window: { ...status().window!, start: '2026-11-13T21:30:00+00:00', end: '2026-11-14T06:30:00+00:00' } });
    expect(decideTracking(s, Date.parse('2026-11-14T03:00:00Z')).run).toBe(true);
    expect(decideTracking(s, Date.parse('2026-11-14T06:31:00Z')).run).toBe(false);
  });
  it('treats a missing status as stopped', () => {
    expect(decideTracking(null, T('12:00'))).toMatchObject({ run: false, reason: 'unknown' });
  });
  it('accepts timestamps without a zone suffix as UTC', () => {
    const w = status().window!;
    expect(decideTracking(status({ window: { ...w, start: '2026-11-13T08:30:00', end: '2026-11-13T18:30:00' } }), T('12:00')).run).toBe(true);
  });
});

describe('nextCheckDelay', () => {
  it('re-checks right after the window end, clamped to the periodic maximum', () => {
    const d = decideTracking(status(), T('18:29'));
    expect(nextCheckDelay(d, T('18:29'))).toBe(61_000);
    expect(nextCheckDelay(decideTracking(status(), T('10:00')), T('10:00'))).toBe(MAX_CHECK_MS);
  });
  it('uses the periodic interval when there is no boundary and a floor otherwise', () => {
    expect(nextCheckDelay(decideTracking(status({ required: false }), T('10:00')), T('10:00'))).toBe(MAX_CHECK_MS);
    expect(nextCheckDelay({ run: true, reason: 'in_window', windowEnd: 1, changeAt: 1 }, 1_000_000)).toBe(MIN_CHECK_MS);
  });
});
