import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '../../auth/AuthProvider';
import type { MyBroadcast } from '../../api/types';
import { acknowledge, BROADCASTS_KEY, fetchMyBroadcasts, markRead, markSafety } from './api';

export const BROADCAST_POLL_MS = 60_000;

/** Polls while the app is foregrounded (focusManager pauses it in the background) and refetches on every focus. */
export function useMyBroadcasts() {
  const { user } = useAuth();
  return useQuery({
    queryKey: BROADCASTS_KEY,
    queryFn: fetchMyBroadcasts,
    enabled: !!user,
    staleTime: 0,
    refetchInterval: BROADCAST_POLL_MS,
  });
}

export type BroadcastResponseInput = { id: number } & ({ kind: 'safety'; status: 'safe' | 'need_help'; note?: string } | { kind: 'ack' } | { kind: 'read' });

export function useBroadcastRespond() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: BroadcastResponseInput) =>
      v.kind === 'safety' ? markSafety(v.id, v.status, v.note) : v.kind === 'ack' ? acknowledge(v.id) : markRead(v.id),
    onSuccess: (row, v) => {
      // Resolve the row immediately so the modal closes without waiting for the refetch.
      qc.setQueryData<MyBroadcast[]>(BROADCASTS_KEY, (cur) => cur?.map((b) => (b.id === v.id ? { ...b, ...row, pending: false } : b)));
    },
    onSettled: () => void qc.invalidateQueries({ queryKey: BROADCASTS_KEY }),
  });
}
