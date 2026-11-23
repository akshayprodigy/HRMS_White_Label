import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '../../auth/AuthProvider';
import { retryUnlessGate } from '../attendance/gate';
import { cancelPick, fetchMyHolidays, HOLIDAY_KEYS, pickHoliday } from './api';

export function useMyHolidays(year: number | null) {
  const { user } = useAuth();
  return useQuery({ queryKey: [...HOLIDAY_KEYS.my, year ?? 'current'], queryFn: () => fetchMyHolidays(year), enabled: !!user, retry: retryUnlessGate });
}
function useInvalidateHolidays() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: HOLIDAY_KEYS.my });
}
export function usePickHoliday() {
  const invalidate = useInvalidateHolidays();
  return useMutation({ mutationFn: pickHoliday, onSuccess: invalidate });
}
export function useCancelPick() {
  const invalidate = useInvalidateHolidays();
  return useMutation({ mutationFn: cancelPick, onSuccess: invalidate, onError: invalidate });
}
