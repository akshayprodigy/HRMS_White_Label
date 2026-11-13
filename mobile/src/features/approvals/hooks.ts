import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '../../auth/AuthProvider';
import { useAttendanceGate } from '../attendance/gate';
import { actOnApproval, APPROVALS_KEY, bulkAction, fetchApprovals, type ApprovalCard, type ApprovalsData } from './api';
import type { Me } from '../../api/client';

const APPROVER_ROLES = new Set(['hr', 'pm', 'admin', 'super admin']);

type RoleLike = { name?: string; permissions?: { name?: string }[] };

/** Cheap static check from /auth/me: superuser, approver-ish role names, or any *approv* / admin permission. */
export function hasApproverRole(user: Me | null): boolean {
  if (!user) return false;
  if (user.is_superuser) return true;
  const roles = (Array.isArray(user.roles) ? user.roles : []) as RoleLike[];
  return roles.some(
    (r) =>
      APPROVER_ROLES.has((r.name ?? '').trim().toLowerCase()) ||
      (r.permissions ?? []).some((p) => /approv|^admin access$/i.test(p.name ?? '')),
  );
}

export function useApprovals(enabled = true) {
  return useQuery({ queryKey: APPROVALS_KEY, queryFn: fetchApprovals, enabled });
}

/**
 * Approvals tab visibility: (1) static role/permission check; otherwise (2) the merged queue itself,
 * fetched only once the attendance gate is open (the endpoints 403 before punch-in) - the tab appears
 * when the queue is non-empty. Same query key as the screen, so it costs no extra requests there.
 */
export function useApprovalsAccess() {
  const { user } = useAuth();
  const { gated, ready } = useAttendanceGate();
  const approver = hasApproverRole(user);
  const q = useApprovals(!!user && ready && !gated && !approver);
  const queued = (q.data?.items.length ?? 0) > 0;
  return { show: approver || queued, approver, queueCount: q.data?.items.length ?? 0 };
}

export function useApprovalAction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { card: ApprovalCard; action: 'approve' | 'reject'; comment?: string }) =>
      actOnApproval(v.card, v.action, v.comment),
    onMutate: async (v) => {
      await qc.cancelQueries({ queryKey: APPROVALS_KEY });
      const prev = qc.getQueryData<ApprovalsData>(APPROVALS_KEY);
      if (prev) qc.setQueryData<ApprovalsData>(APPROVALS_KEY, { ...prev, items: prev.items.filter((c) => c.key !== v.card.key) });
      return { prev };
    },
    onError: (_e, _v, ctx) => {
      if (ctx?.prev) qc.setQueryData(APPROVALS_KEY, ctx.prev);
    },
    onSettled: () => void qc.invalidateQueries({ queryKey: APPROVALS_KEY }),
  });
}

export function useBulkAction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { ids: number[]; action: 'approve' | 'reject'; comment?: string }) => bulkAction(v.ids, v.action, v.comment),
    onSettled: () => void qc.invalidateQueries({ queryKey: APPROVALS_KEY }),
  });
}
