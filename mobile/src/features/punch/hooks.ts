import { useQueryClient } from '@tanstack/react-query';
import * as Network from 'expo-network';
import { useCallback, useEffect, useSyncExternalStore } from 'react';
import { AppState } from 'react-native';
import { useAuth } from '../../auth/AuthProvider';
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
  const { user } = useAuth();
  const q = getPunchQueue();
  const uid = user?.id ?? null;
  const snap = useSyncExternalStore(
    (cb) => q.subscribe(cb),
    () => q.getSnapshot(),
  );
  useEffect(() => {
    q.setUser(uid);
    void q.ready();
  }, [q, uid]);
  return { queue: q, ...snap };
}

/** Manual / post-punch sync trigger (no timers). */
export function useSyncNow() {
  const invalidate = useInvalidateAfterPunch();
  return useCallback(async (force = false) => {
    const q = getPunchQueue();
    await q.ready();
    const out = await q.sync(syncDeps, { force });
    if (out.created + out.duplicate + out.rejected > 0) await invalidate();
    return out;
  }, [invalidate]);
}

/** Mounted ONCE at the root layout: sync on mount, foreground, network regain and a 60s tick (backoff throttles retries). */
export function usePunchQueueSyncLoop() {
  const { user } = useAuth();
  const uid = user?.id ?? null;
  const run = useSyncNow();
  useEffect(() => {
    const q = getPunchQueue();
    q.setUser(uid);
    if (uid == null) return;
    void run().catch(() => undefined);
    const app = AppState.addEventListener('change', (s) => { if (s === 'active') void run().catch(() => undefined); });
    let net: { remove?: () => void } | undefined;
    try {
      net = Network.addNetworkStateListener((s) => { if (s.isConnected) void run(true).catch(() => undefined); });
    } catch { /* native module missing: foreground + tick still work */ }
    const tick = setInterval(() => void run().catch(() => undefined), 60_000);
    return () => { app.remove(); net?.remove?.(); clearInterval(tick); };
  }, [run, uid]);
}
