import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '../../auth/AuthProvider';
import { retryUnlessGate, useAttendanceGate } from '../attendance/gate';
import { decidePick, decideWorkLocation, fetchTeamPicks, fetchTeamWorkLocation, TEAM_KEYS } from './api';

function useTeamQuery<T>(key: readonly string[], fn: () => Promise<T>) {
  const { user } = useAuth();
  const { gated, ready } = useAttendanceGate();
  return useQuery({ queryKey: key, queryFn: fn, enabled: !!user && ready && !gated, retry: retryUnlessGate });
}
export const useTeamWorkLocation = () => useTeamQuery(TEAM_KEYS.workLocation, fetchTeamWorkLocation);
export const useTeamPicks = () => useTeamQuery(TEAM_KEYS.picks, fetchTeamPicks);

// Refetch on success AND on error: a 409/404 usually means the row was already decided elsewhere.
export function useDecideWorkLocation() {
  const qc = useQueryClient();
  const inv = () => qc.invalidateQueries({ queryKey: TEAM_KEYS.workLocation });
  return useMutation({ mutationFn: decideWorkLocation, onSuccess: inv, onError: inv });
}
export function useDecidePick() {
  const qc = useQueryClient();
  const inv = () => qc.invalidateQueries({ queryKey: TEAM_KEYS.picks });
  return useMutation({ mutationFn: decidePick, onSuccess: inv, onError: inv });
}
