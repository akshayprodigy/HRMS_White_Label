/**
 * PerformanceTab — legacy stub replaced with the real Performance
 * Management workspace. The workspace lives in
 * `components/performance-workspace.tsx` and covers Goals, Reviews,
 * Team Reviews, Cycles, Calibration and 1:1s.
 *
 * We keep the original prop signature so callers that pass placeholder
 * reviews/trend/skills arrays still compile — the workspace ignores
 * them and pulls live data from the backend.
 */
import React from 'react';
import { PerformanceWorkspace } from '../performance-workspace';

interface PerformanceTabProps {
  reviews?: unknown[];
  performanceTrend?: unknown[];
  skillsData?: unknown[];
}

export function PerformanceTab(_props: PerformanceTabProps) {
  return <PerformanceWorkspace />;
}
