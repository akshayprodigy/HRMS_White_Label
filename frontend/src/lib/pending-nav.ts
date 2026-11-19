/**
 * Pending deep-link stash. Lazy-loaded pages are not mounted yet when an
 * `erp:navigate` event fires, so App stashes the detail and the target page
 * takes it on mount (or from its own listener when already mounted).
 */
export interface NavDetail {
  tab?: string;
  resourceType?: string;
  resourceId?: string | number;
  [k: string]: unknown;
}

const TTL_MS = 5000;
let pending: { detail: NavDetail; at: number } | null = null;

export const stashNav = (detail: NavDetail | undefined | null): void => {
  pending = detail && detail.tab ? { detail, at: Date.now() } : null;
};

/** Returns and clears the stash if it targets `tab` and has not expired. */
export const takeNav = (tab: string): NavDetail | null => {
  const p = pending;
  if (!p || p.detail.tab !== tab) return null;
  pending = null;
  return Date.now() - p.at <= TTL_MS ? p.detail : null;
};
