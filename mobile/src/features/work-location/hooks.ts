import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '../../auth/AuthProvider';
import { cancelRequest, createRequest, fetchMyRequests, WL_KEYS } from './api';

export function useMyRequests(staleTime?: number) {
  const { user } = useAuth();
  return useQuery({ queryKey: WL_KEYS.my, queryFn: fetchMyRequests, enabled: !!user, retry: 1, ...(staleTime != null ? { staleTime } : {}) });
}
function useInvalidate() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: WL_KEYS.my });
}
export function useCreateRequest() {
  const invalidate = useInvalidate();
  return useMutation({ mutationFn: createRequest, onSuccess: invalidate });
}
export function useCancelRequest() {
  const invalidate = useInvalidate();
  return useMutation({ mutationFn: cancelRequest, onSuccess: invalidate, onError: invalidate });
}
