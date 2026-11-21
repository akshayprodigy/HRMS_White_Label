import { statusMeta, STATUS_META } from '../src/features/tracking/fieldFormat';

describe('fieldFormat statusMeta', () => {
  it('knows the remote status', () => {
    expect(STATUS_META.remote.label).toBe('Remote');
    expect(statusMeta('remote')).toBe(STATUS_META.remote);
  });
  it('falls back to off for an unknown status instead of crashing', () => {
    expect(statusMeta('something_new')).toBe(STATUS_META.off);
  });
});
