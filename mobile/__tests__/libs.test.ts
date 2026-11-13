import { focusManager } from '@tanstack/react-query';
import { renderHook } from '@testing-library/react-native';
import { AppState } from 'react-native';
import { useAppStateFocus } from '../src/lib/appFocus';
import { fmtUtcDate, fmtUtcTime, parseUtc } from '../src/lib/time';

describe('time', () => {
  it('treats zone-less timestamps as UTC and date-only strings as UTC midnight', () => {
    expect(fmtUtcTime('2026-11-13T09:05:00')).toBe('09:05 UTC');
    expect(fmtUtcTime('2026-11-13T09:05:00+05:30')).toBe('03:35 UTC');
    expect(parseUtc('2026-11-13').toISOString()).toBe('2026-11-13T00:00:00.000Z');
    expect(fmtUtcDate('2026-11-13')).toBe('13 Nov');
    expect(fmtUtcTime('garbage')).toBe('—');
  });
});

describe('useAppStateFocus', () => {
  it('feeds AppState changes into react-query focusManager', async () => {
    let handler: (s: string) => void = () => undefined;
    const remove = jest.fn();
    const spy = jest.spyOn(AppState, 'addEventListener').mockImplementation(((_: string, h: (s: string) => void) => {
      handler = h;
      return { remove };
    }) as never);
    const { unmount } = await renderHook(() => useAppStateFocus());
    handler('background');
    expect(focusManager.isFocused()).toBe(false);
    handler('active');
    expect(focusManager.isFocused()).toBe(true);
    await unmount();
    expect(remove).toHaveBeenCalled();
    spy.mockRestore();
  });
});
