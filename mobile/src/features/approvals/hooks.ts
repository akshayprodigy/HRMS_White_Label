import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '../../auth/AuthProvider';
import { PENDING_COUNT_KEY, retryUnlessGate, useAttendanceGate } from '../attendance/gate';
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

/** Runs only once the gate answer is known and open (no 403 spam before punch-in). */
export function useApprovals(enabled = true) {
  const { user } = useAuth();
  const { gated, ready } = useAttendanceGate();
  return useQuery({ queryKey: APPROVALS_KEY, queryFn: fetchApprovals, enabled: enabled && !!user && ready && !gated, retry: retryUnlessGate });
}

/**
 * Approvals tab visibility ("show") is separate from fetching ("run"): the queue is always fetched once the gate is
 * open (so Home's awaiting count is right for role approvers too); the tab shows for role/permission approvers
 * (static check from /auth/me) or whenever the queue is non-empty.
 */
export function useApprovalsAccess() {
  const { user } = useAuth();
  const approver = hasApproverRole(user);
  const q = useApprovals();
  const queueCount = q.data?.items.length ?? 0;
  return { show: approver || queueCount > 0, approver, queueCount };
}

export function useApprovalAction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { card: ApprovalCard; action: 'approve' | 'reject'; comment?: string }) =>
      actOnApproval(v.card, v.action, v.comment),
    onMutate: async (v) => {
      await qc.cancelQueries({ queryKey: APPROVALS_KEY });
      const prev = qc.getQueryData<ApprovalsData>(APPROVALS_KEY);
      const index = prev ? prev.items.findIndex((c) => c.key === v.card.key) : -1;
      if (prev) qc.setQueryData<ApprovalsData>(APPROVALS_KEY, { ...prev, items: prev.items.filter((c) => c.key !== v.card.key) });
      return { index };
    },
    onError: (_e, v, ctx) => {
      // Re-insert only the failed card (other cards may have changed meanwhile).
      qc.setQueryData<ApprovalsData>(APPROVALS_KEY, (cur) => {
        if (!cur || cur.items.some((c) => c.key === v.card.key)) return cur;
        const items = [...cur.items];
        items.splice(Math.min(Math.max(ctx?.index ?? 0, 0), items.length), 0, v.card);
        return { ...cur, items };
      });
    },
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: APPROVALS_KEY });
      void qc.invalidateQueries({ queryKey: PENDING_COUNT_KEY });
    },
  });
}

export function useBulkAction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { ids: number[]; action: 'approve' | 'reject'; comment?: string }) => bulkAction(v.ids, v.action, v.comment),
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: APPROVALS_KEY });
      void qc.invalidateQueries({ queryKey: PENDING_COUNT_KEY });
    },
  });
}
