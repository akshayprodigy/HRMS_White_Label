import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '../../auth/AuthProvider';
import { retryUnlessGate } from '../attendance/gate';
import { applyLeave, cancelLeave, fetchBalances, fetchLeaveTypes, fetchMyLeaves, LEAVE_KEYS, submitProof, type ApplyPayload, type PickedFile } from './api';

function useLeaveQuery<T>(key: readonly string[], fn: () => Promise<T>) {
  const { user } = useAuth();
  return useQuery({ queryKey: key, queryFn: fn, enabled: !!user, retry: retryUnlessGate });
}
export const useBalances = () => useLeaveQuery(LEAVE_KEYS.balances, fetchBalances);
export const useLeaveTypes = () => useLeaveQuery(LEAVE_KEYS.types, fetchLeaveTypes);
export const useMyLeaves = () => useLeaveQuery(LEAVE_KEYS.my, fetchMyLeaves);

function useInvalidateLeave() {
  const qc = useQueryClient();
  return () => Promise.all([LEAVE_KEYS.balances, LEAVE_KEYS.my].map((k) => qc.invalidateQueries({ queryKey: k })));
}

export function useApplyLeave() {
  const invalidate = useInvalidateLeave();
  return useMutation({ mutationFn: (v: { payload: ApplyPayload; file: PickedFile | null }) => applyLeave(v.payload, v.file), onSuccess: invalidate });
}
export function useSubmitProof() {
  const invalidate = useInvalidateLeave();
  return useMutation({ mutationFn: (v: { id: number; file: PickedFile }) => submitProof(v.id, v.file), onSuccess: invalidate });
}
export function useCancelLeave() {
  const invalidate = useInvalidateLeave();
  return useMutation({ mutationFn: (id: number) => cancelLeave(id), onSuccess: invalidate });
}
