import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query';
import { useRef, useState } from 'react';
import { normalizeError } from '../../api/client';
import { useAuth } from '../../auth/AuthProvider';
import { retryUnlessGate, useAttendanceGate } from '../attendance/gate';
import {
  ackChange, cancelDrop, claimOpenShift, createAvailability, createDrop, createSwap, deleteAvailability, deleteFeed,
  fetchAcks, fetchAvailability, fetchDrops, fetchFeedStatus, fetchOnCall, fetchOpenShifts, fetchShiftOptions, fetchSwapCandidates,
  fetchSwaps, fetchWeek, rotateFeed, SCHEDULE_KEYS, swapAction, withdrawClaim, type SwapAction,
} from './api';

/** Roster routes are attendance-gated: only run once the gate answer is known and open. */
function useGated<T>(key: readonly unknown[], fn: () => Promise<T>, enabled = true) {
  const { user } = useAuth();
  const { gated, ready } = useAttendanceGate();
  return useQuery({ queryKey: key, queryFn: fn, enabled: enabled && !!user && ready && !gated, retry: retryUnlessGate });
}

export const useWeek = (start: string) => useGated([...SCHEDULE_KEYS.week, start], () => fetchWeek(start));
export function useMonthWeeks(starts: string[], enabled: boolean) {
  const { user } = useAuth();
  const { gated, ready } = useAttendanceGate();
  return useQueries({
    queries: starts.map((s) => ({ queryKey: [...SCHEDULE_KEYS.week, s], queryFn: () => fetchWeek(s), enabled: enabled && !!user && ready && !gated, retry: retryUnlessGate })),
  });
}
export const useOnCall = () => useGated(SCHEDULE_KEYS.onCall, fetchOnCall);
export const useAcks = () => useGated(SCHEDULE_KEYS.acks, fetchAcks);
export const useSwaps = () => useGated(SCHEDULE_KEYS.swaps, fetchSwaps);
export const useDrops = () => useGated(SCHEDULE_KEYS.drops, fetchDrops);
export const useOpenShifts = () => useGated(SCHEDULE_KEYS.openShifts, fetchOpenShifts);
export const useAvailability = () => useGated(SCHEDULE_KEYS.availability, fetchAvailability);
export const useShiftOptions = () => useGated(SCHEDULE_KEYS.templates, fetchShiftOptions);
export const useFeedStatus = () => useGated(SCHEDULE_KEYS.feed, fetchFeedStatus);
export const useSwapCandidates = (date: string | null) => useGated([...SCHEDULE_KEYS.candidates, date], () => fetchSwapCandidates(date as string), !!date);

/** Invalidate the given schedule key groups (prefix match) after a mutation settles. */
function useInvalidate(...keys: (readonly string[])[]) {
  const qc = useQueryClient();
  return () => Promise.all(keys.map((k) => qc.invalidateQueries({ queryKey: k })));
}

export function useAckChange() {
  const inv = useInvalidate(SCHEDULE_KEYS.acks, SCHEDULE_KEYS.week);
  return useMutation({ mutationFn: ackChange, onSettled: inv });
}
export function useCreateSwap() {
  const inv = useInvalidate(SCHEDULE_KEYS.swaps, SCHEDULE_KEYS.week, SCHEDULE_KEYS.candidates);
  return useMutation({ mutationFn: createSwap, onSettled: inv });
}
export function useSwapAction() {
  const inv = useInvalidate(SCHEDULE_KEYS.swaps, SCHEDULE_KEYS.week);
  return useMutation({ mutationFn: (v: { id: number; action: SwapAction }) => swapAction(v.id, v.action), onSettled: inv });
}
export function useCreateDrop() {
  const inv = useInvalidate(SCHEDULE_KEYS.drops, SCHEDULE_KEYS.week);
  return useMutation({ mutationFn: createDrop, onSettled: inv });
}
export function useCancelDrop() {
  const inv = useInvalidate(SCHEDULE_KEYS.drops, SCHEDULE_KEYS.week);
  return useMutation({ mutationFn: cancelDrop, onSettled: inv });
}
/** Settled (not only success): a failed claim usually means the list is stale (shift filled / no longer open). */
export function useClaim() {
  const inv = useInvalidate(SCHEDULE_KEYS.openShifts, SCHEDULE_KEYS.week);
  return useMutation({ mutationFn: claimOpenShift, onSettled: inv });
}
export function useWithdraw() {
  const inv = useInvalidate(SCHEDULE_KEYS.openShifts, SCHEDULE_KEYS.week);
  return useMutation({ mutationFn: withdrawClaim, onSettled: inv });
}
export function useAddAvailability() {
  const inv = useInvalidate(SCHEDULE_KEYS.availability);
  return useMutation({ mutationFn: createAvailability, onSettled: inv });
}
export function useDeleteAvailability() {
  const inv = useInvalidate(SCHEDULE_KEYS.availability);
  return useMutation({ mutationFn: deleteAvailability, onSettled: inv });
}
export function useRotateFeed() {
  const inv = useInvalidate(SCHEDULE_KEYS.feed);
  return useMutation({ mutationFn: rotateFeed, onSettled: inv });
}
export function useDeleteFeed() {
  const inv = useInvalidate(SCHEDULE_KEYS.feed);
  return useMutation({ mutationFn: deleteFeed, onSettled: inv });
}

/**
 * Per-key double-tap guard for row actions: a second press while the first is in flight is ignored
 * (the ref flips synchronously, before React re-renders the disabled button). Failures surface as `error`.
 */
export function useGuardedRun() {
  const inflight = useRef(new Set<string>());
  const [busy, setBusy] = useState<ReadonlySet<string>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const run = async (key: string, fn: () => Promise<unknown>): Promise<boolean> => {
    if (inflight.current.has(key)) return false;
    inflight.current.add(key);
    setBusy(new Set(inflight.current));
    setError(null);
    try {
      await fn();
      return true;
    } catch (e) {
      setError(normalizeError(e).message);
      return false;
    } finally {
      inflight.current.delete(key);
      setBusy(new Set(inflight.current));
    }
  };
  return { run, error, clearError: () => setError(null), isBusy: (key: string) => busy.has(key), anyBusy: busy.size > 0 };
}
