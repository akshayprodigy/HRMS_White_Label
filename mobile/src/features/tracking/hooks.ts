import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useRef } from 'react';
import { AppState } from 'react-native';
import { onBeforeLogout, useAuth } from '../../auth/AuthProvider';
import { fetchMyStatus, MY_STATUS_KEY, type MyStatus } from './api';
import { applyStatus, flushPings, getPingQueue, stopTracking, type ApplyResult } from './tracking';
import { decideTracking, nextCheckDelay } from './window';

export function useMyTrackingStatus() {
  const { user } = useAuth();
  return useQuery({ queryKey: MY_STATUS_KEY, queryFn: fetchMyStatus, enabled: !!user, staleTime: 60_000 });
}

/** Refetch my-status, apply start/stop for the current moment and upload anything queued. Single-flight per caller set. */
export function useRecheckTracking() {
  const { user } = useAuth();
  const qc = useQueryClient();
  const uid = user?.id ?? null;
  return useCallback(async (): Promise<ApplyResult | null> => {
    if (uid == null) return null;
    let status: MyStatus | undefined;
    try {
      status = await qc.fetchQuery({ queryKey: MY_STATUS_KEY, queryFn: fetchMyStatus, staleTime: 0 });
    } catch {
      // Offline / server trouble: decide from the last known status so a window that has ended still stops tracking.
      status = qc.getQueryData<MyStatus>(MY_STATUS_KEY);
      if (!status) return null;
    }
    const r = await applyStatus(status, uid);
    const q = getPingQueue();
    q.setUser(uid);
    const out = await flushPings().catch(() => null);
    if (out?.stop) void qc.invalidateQueries({ queryKey: MY_STATUS_KEY });
    return r;
  }, [qc, uid]);
}

/**
 * KNOWN LIMITATION: there is no OS-level background start at window start. If the app is not running when a shift window
 * opens, tracking begins only once the app is opened (or foregrounded) during or before the window. Once started, the
 * Android foreground service / iOS background location keep it going and the headless task stops it at the window end.
 * Follow-up: schedule the start with expo-background-task.
 *
 * Mounted ONCE inside the root layout: on sign-in, on foreground, and on a timer aimed at the next window boundary
 * (capped at 10 minutes so policy/consent changes are noticed). Also tears everything down on logout. */
export function useTrackingLifecycle() {
  const { user, loading } = useAuth();
  const qc = useQueryClient();
  const recheck = useRecheckTracking();
  const uid = user?.id ?? null;
  const running = useRef(false);

  // Logout: stop and erase BEFORE the tokens go (hook order is registration order; nothing here needs the network).
  useEffect(() => onBeforeLogout(async () => { await stopTracking({ clear: true }); }), []);

  useEffect(() => {
    if (uid == null) {
      if (loading) return; // the stored session is still being restored: not a sign-out
      // Forced logout / signed out: nothing may keep collecting.
      void stopTracking({ clear: true }).catch(() => undefined);
      return;
    }
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const run = async () => {
      if (running.current) return;
      running.current = true;
      try { await recheck(); } catch (e) { console.warn('[tracking] recheck failed', e instanceof Error ? e.message : e); } finally { running.current = false; }
      if (!alive) return;
      clearTimeout(timer);
      const now = Date.now();
      timer = setTimeout(() => void run(), nextCheckDelay(decideTracking(qc.getQueryData<MyStatus>(MY_STATUS_KEY), now), now));
    };
    void run();
    const sub = AppState.addEventListener('change', (s) => { if (s === 'active') void run(); });
    return () => { alive = false; clearTimeout(timer); sub.remove(); };
  }, [uid, loading, qc, recheck]);
}
