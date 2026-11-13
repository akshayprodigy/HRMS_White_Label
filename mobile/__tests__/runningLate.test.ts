import { canShowRunningLate, validateRunningLate } from '../src/features/punch/runningLate';
import { normalizeError } from '../src/api/errors';
import { AxiosError } from 'axios';

describe('running late', () => {
  it('validates minutes (5..240, integer) and reason length', () => {
    expect(validateRunningLate(4, '')).toMatch(/between 5 and 240/);
    expect(validateRunningLate(241, '')).toMatch(/between 5 and 240/);
    expect(validateRunningLate(1.5, '')).toMatch(/whole number/);
    expect(validateRunningLate(15, 'x'.repeat(256))).toMatch(/255/);
    expect(validateRunningLate(5, 'traffic')).toBeNull();
    expect(validateRunningLate(240, '')).toBeNull();
  });
  it('shows only when the shift started, can_post and not punched in', () => {
    const s = { notice: null, can_post: true, shift_start: '2026-11-13T09:30:00+00:00' };
    const at = (iso: string) => Date.parse(iso);
    expect(canShowRunningLate(s, false, at('2026-11-13T09:00:00Z'))).toBe(false);
    expect(canShowRunningLate(s, false, at('2026-11-13T09:45:00Z'))).toBe(true);
    expect(canShowRunningLate(s, true, at('2026-11-13T09:45:00Z'))).toBe(false);
    expect(canShowRunningLate({ ...s, can_post: false }, false, at('2026-11-13T09:45:00Z'))).toBe(false);
    expect(canShowRunningLate(undefined, false)).toBe(false);
  });
});

describe('structured geofence 422 detail', () => {
  it('surfaces message and error code', () => {
    const e = new AxiosError('x', 'ERR', undefined, undefined, { status: 422, data: { detail: { error: 'OUTSIDE_GEOFENCE', message: 'You are 420 m from Head Office.', nearest_fence_name: 'Head Office' } }, statusText: '', headers: {}, config: {} as never });
    const n = normalizeError(e);
    expect(n.message).toBe('You are 420 m from Head Office.');
    expect(n.code).toBe('OUTSIDE_GEOFENCE');
    expect(n.status).toBe(422);
  });
});
