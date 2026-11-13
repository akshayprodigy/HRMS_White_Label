import { parseUtc } from '../../lib/time';
import type { MyStatus } from './api';

export type StopReason = 'unknown' | 'disabled' | 'no_consent' | 'no_window' | 'before_window' | 'after_window';
export type Decision = {
  run: boolean;
  reason: 'in_window' | StopReason;
  /** Epoch ms when the current window ends (only while running); persisted so the headless task can stop itself. */
  windowEnd: number | null;
  /** Epoch ms of the next moment the decision changes (window start / end), or null. */
  changeAt: number | null;
};

export const MAX_CHECK_MS = 10 * 60_000;
export const MIN_CHECK_MS = 5_000;

/**
 * Pure start/stop decision from my-status + the device clock. The server's `in_window` flag is a snapshot from when
 * the status was fetched, so the window bounds are compared against `now` instead. Tracking runs only when HR requires
 * it for this user, the user consented, and `now` is inside [window.start, window.end] (shift +/- 30 min, UTC).
 */
export function decideTracking(status: MyStatus | null | undefined, now: number): Decision {
  const stop = (reason: StopReason, changeAt: number | null = null): Decision => ({ run: false, reason, windowEnd: null, changeAt });
  if (!status) return stop('unknown');
  if (!status.required) return stop('disabled');
  if (!status.consented) return stop('no_consent');
  const w = status.window;
  if (!w) return stop('no_window');
  const start = parseUtc(w.start).getTime();
  const end = parseUtc(w.end).getTime();
  if (Number.isNaN(start) || Number.isNaN(end) || end <= start) return stop('no_window');
  if (now < start) return stop('before_window', start);
  if (now > end) return stop('after_window');
  return { run: true, reason: 'in_window', windowEnd: end, changeAt: end };
}

/** Delay until the next status re-check: the next window boundary, but never longer than MAX_CHECK_MS (policy / consent
 * may change on the server) and never shorter than MIN_CHECK_MS. */
export function nextCheckDelay(d: Decision, now: number): number {
  const until = d.changeAt == null ? MAX_CHECK_MS : d.changeAt - now + 1000;
  return Math.min(MAX_CHECK_MS, Math.max(MIN_CHECK_MS, until));
}
