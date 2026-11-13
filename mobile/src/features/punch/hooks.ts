import { useQueryClient } from '@tanstack/react-query';
import * as Network from 'expo-network';
import { useCallback, useEffect, useSyncExternalStore } from 'react';
import { AppState } from 'react-native';
import { ATTENDANCE_TODAY_KEY, PENDING_COUNT_KEY } from '../attendance/gate';
import { getPunchQueue, syncDeps } from './api';

/** Refetch everything a punch can change, including the attendance gate probe. */
export function useInvalidateAfterPunch() {
  const qc = useQueryClient();
  return useCallback(async () => {
    await Promise.all([
      qc.invalidateQueries({ queryKey: ATTENDANCE_TODAY_KEY }),
      qc.invalidateQueries({ queryKey: PENDING_COUNT_KEY }),
      qc.invalidateQueries({ queryKey: ['roster-week'] }),
      qc.invalidateQueries({ queryKey: ['running-late'] }),
    ]);
  }, [qc]);
}

export function usePunchQueue() {
  const q = getPunchQueue();
  const snap = useSyncExternalStore(
    (cb) => q.subscribe(cb),
    () => q.getSnapshot(),
  );
  useEffect(() => { void q.ready().then(() => undefined); }, [q]);
  return { queue: q, ...snap };
}

/** Sync on mount, foreground, network regain and a 60s tick (the queue's own backoff throttles retries). */
export function usePunchQueueSync() {
  const invalidate = useInvalidateAfterPunch();
  const run = useCallback(async (force = false) => {
    const q = getPunchQueue();
    await q.ready();
    const out = await q.sync(syncDeps, { force });
    if (out.created + out.duplicate + out.rejected > 0) await invalidate();
    return out;
  }, [invalidate]);

  useEffect(() => {
    void run().catch(() => undefined);
    const app = AppState.addEventListener('change', (s) => { if (s === 'active') void run().catch(() => undefined); });
    let net: { remove(): void } | undefined;
    try {
      net = Network.addNetworkStateListener((s) => { if (s.isConnected) void run(true).catch(() => undefined); });
    } catch { /* native module missing: foreground + tick still work */ }
    const tick = setInterval(() => void run().catch(() => undefined), 60_000);
    return () => { app.remove(); net?.remove?.(); clearInterval(tick); };
  }, [run]);
  return run;
}
