import { useEffect, useRef } from 'react';

/** Calls `fn` immediately, then every `ms` while the tab is visible, and once
 * more whenever the tab becomes visible again. Pass a memoised (useCallback)
 * `fn`: when its identity changes (filter / page / id changed) it is refetched
 * immediately instead of waiting for the next tick. */
export function useVisiblePoll(fn: () => void, ms: number, enabled = true) {
  const ref = useRef(fn);
  ref.current = fn;
  const prevFn = useRef(fn);
  useEffect(() => {
    if (!enabled) return;
    const tick = () => {
      if (document.visibilityState === 'visible') ref.current();
    };
    tick();
    const id = window.setInterval(tick, ms);
    document.addEventListener('visibilitychange', tick);
    return () => {
      window.clearInterval(id);
      document.removeEventListener('visibilitychange', tick);
    };
  }, [ms, enabled]);
  useEffect(() => {
    if (prevFn.current === fn) return;
    prevFn.current = fn;
    if (enabled && document.visibilityState === 'visible') fn();
  }, [fn, enabled]);
}
