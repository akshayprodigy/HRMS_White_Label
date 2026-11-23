import { isPast, pickAction } from '../src/features/holidays/logic';
import type { MyHoliday } from '../src/features/holidays/api';

const h = (o: Partial<MyHoliday> = {}): MyHoliday => ({ id: 1, name: 'Holi', date: '2026-11-25', location: 'All', is_optional: true, pick: null, ...o });

describe('pickAction', () => {
  it('offers Pick for an unpicked optional holiday and nothing for a mandatory one', () => {
    expect(pickAction(h(), '2026-11-20', 2)).toEqual({ kind: 'pick', disabled: false });
    expect(pickAction(h({ is_optional: false }), '2026-11-20', 2).kind).toBeNull();
  });
  it('disables Pick with no quota left or for a past holiday (org-local today)', () => {
    expect(pickAction(h(), '2026-11-20', 0).disabled).toBe(true);
    expect(pickAction(h({ date: '2026-11-19' }), '2026-11-20', 2).disabled).toBe(true);
    expect(isPast(h({ date: '2026-11-20' }), '2026-11-20')).toBe(false);
  });
  it('Cancel for pending/approved is disabled once past, regardless of quota', () => {
    expect(pickAction(h({ pick: { id: 3, status: 'pending' } }), '2026-11-20', 0)).toEqual({ kind: 'cancel', disabled: false });
    expect(pickAction(h({ date: '2026-11-19', pick: { id: 3, status: 'approved' } }), '2026-11-20', 1)).toEqual({ kind: 'cancel', disabled: true });
  });
  it('a rejected pick can be picked again; a cancelled one is a plain Pick', () => {
    expect(pickAction(h({ pick: { id: 3, status: 'rejected', decision_note: 'busy' } }), '2026-11-20', 1)).toEqual({ kind: 'pick_again', disabled: false });
    expect(pickAction(h({ pick: { id: 3, status: 'cancelled' } }), '2026-11-20', 1).kind).toBe('pick');
  });
});
