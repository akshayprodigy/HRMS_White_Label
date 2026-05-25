import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { timesheetApi } from '../api/timesheet';

export type UnifiedTimerStatus = {
  isActive: boolean;
  isPaused: boolean;
  seconds: number;
  projectId?: number;
  taskId?: number | null;
  subtaskId?: number | null;
  notes?: string | null;
};

type TimerContextValue = {
  status: UnifiedTimerStatus;
  isRefreshing: boolean;
  refresh: () => Promise<void>;
  start: (
    projectId: number,
    taskId?: number | null,
    subtaskId?: number | null,
    notes?: string,
  ) => Promise<void>;
  pause: () => Promise<void>;
  resume: () => Promise<void>;
  stop: () => Promise<any>;
};

const TimerContext = createContext<TimerContextValue | undefined>(undefined);

const REFRESH_MS = 30_000;

export const TimerProvider = ({ children }: { children: React.ReactNode }) => {
  const [status, setStatus] = useState<UnifiedTimerStatus>({
    isActive: false,
    isPaused: false,
    seconds: 0,
    projectId: undefined,
    taskId: null,
    subtaskId: null,
    notes: null,
  });
  const [isRefreshing, setIsRefreshing] = useState(false);

  const tickIntervalRef = useRef<number | null>(null);

  const refresh = useCallback(async () => {
    setIsRefreshing(true);
    try {
      const res = await timesheetApi.getTimerStatus();
      const data = res.data;

      if (!data?.is_active) {
        setStatus({
          isActive: false,
          isPaused: false,
          seconds: 0,
          projectId: undefined,
          taskId: null,
          subtaskId: null,
          notes: null,
        });
        return;
      }

      const session = data.session;
      setStatus({
        isActive: true,
        isPaused: session?.status === 'paused',
        seconds: data.current_duration_seconds ?? 0,
        projectId: session?.project_id,
        taskId: session?.task_id ?? null,
        subtaskId: session?.subtask_id ?? null,
        notes: session?.notes ?? null,
      });
    } finally {
      setIsRefreshing(false);
    }
  }, []);

  useEffect(() => {
    // Initial load; ignore errors to avoid noisy toasts during app boot.
    refresh().catch(() => undefined);

    const id = window.setInterval(() => {
      refresh().catch(() => undefined);
    }, REFRESH_MS);

    return () => window.clearInterval(id);
  }, [refresh]);

  useEffect(() => {
    if (tickIntervalRef.current) {
      window.clearInterval(tickIntervalRef.current);
      tickIntervalRef.current = null;
    }

    if (status.isActive && !status.isPaused) {
      tickIntervalRef.current = window.setInterval(() => {
        setStatus((prev: UnifiedTimerStatus) => {
          if (!prev.isActive || prev.isPaused) return prev;
          return { ...prev, seconds: prev.seconds + 1 };
        });
      }, 1000);
    }

    return () => {
      if (tickIntervalRef.current) {
        window.clearInterval(tickIntervalRef.current);
        tickIntervalRef.current = null;
      }
    };
  }, [status.isActive, status.isPaused]);

  const start = useCallback(async (
    projectId: number,
    taskId?: number | null,
    subtaskId?: number | null,
    notes?: string,
  ) => {
    await timesheetApi.startTimer(
      projectId,
      taskId ?? undefined,
      subtaskId ?? undefined,
      notes,
    );
    // Optimistic update; a refresh will reconcile in the background.
    setStatus({
      isActive: true,
      isPaused: false,
      seconds: 0,
      projectId,
      taskId: taskId ?? null,
      subtaskId: subtaskId ?? null,
      notes: notes ?? null,
    });
  }, []);

  const pause = useCallback(async () => {
    await timesheetApi.pauseTimer();
    setStatus((prev: UnifiedTimerStatus) => ({ ...prev, isPaused: true }));
  }, []);

  const resume = useCallback(async () => {
    await timesheetApi.resumeTimer();
    setStatus((prev: UnifiedTimerStatus) => ({ ...prev, isPaused: false }));
  }, []);

  const stop = useCallback(async () => {
    const res = await timesheetApi.stopTimer();
    setStatus({
      isActive: false,
      isPaused: false,
      seconds: 0,
      projectId: undefined,
      taskId: null,
      subtaskId: null,
      notes: null,
    });
    return res.data;
  }, []);

  const value = useMemo(
    () => ({ status, isRefreshing, refresh, start, pause, resume, stop }),
    [status, isRefreshing, refresh, start, pause, resume, stop]
  );

  return <TimerContext.Provider value={value}>{children}</TimerContext.Provider>;
};

export const useTimer = (): TimerContextValue => {
  const ctx = useContext(TimerContext);
  if (!ctx) throw new Error('useTimer must be used within a TimerProvider');
  return ctx;
};
