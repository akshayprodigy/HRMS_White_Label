import { useEffect, useState } from 'react';

const QUERY = '(max-width: 767px)';

// Force flag: `?mobile=1` in the URL pins mobile shell (for QA on desktop).
// `?desktop=1` pins the desktop shell even on a phone (escape hatch).
function forcedMode(): 'mobile' | 'desktop' | null {
  if (typeof window === 'undefined') return null;
  const p = new URLSearchParams(window.location.search);
  if (p.get('mobile') === '1') return 'mobile';
  if (p.get('desktop') === '1') return 'desktop';
  return null;
}

export function useIsMobile(): boolean {
  const [isMobile, setIsMobile] = useState<boolean>(() => {
    if (typeof window === 'undefined') return false;
    const forced = forcedMode();
    if (forced) return forced === 'mobile';
    return window.matchMedia(QUERY).matches;
  });

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const forced = forcedMode();
    if (forced) return; // forced modes don't react to resize
    const mql = window.matchMedia(QUERY);
    const onChange = (e: MediaQueryListEvent) => setIsMobile(e.matches);
    // Safari <14 uses addListener; modern browsers use addEventListener.
    if (mql.addEventListener) mql.addEventListener('change', onChange);
    else mql.addListener(onChange);
    return () => {
      if (mql.removeEventListener) mql.removeEventListener('change', onChange);
      else mql.removeListener(onChange);
    };
  }, []);

  return isMobile;
}
