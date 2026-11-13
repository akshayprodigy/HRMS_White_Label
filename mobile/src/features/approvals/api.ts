import { api, normalizeError } from '../../api/client';
import type { BulkResult, ChainQueueItem, LegacyInboxItem } from '../../api/types';
import { isGateError } from '../attendance/gate';

export type ApprovalSource = 'legacy' | 'chain';

/** Normalised row: both the legacy inbox and the chain queue map onto this. */
export type ApprovalCard = {
  key: string; // `${source}-${refId}`
  source: ApprovalSource;
  refId: number;
  kind: string;
  title: string;
  subtitle: string;
  requester: string | null;
  amountPaise: number | null;
  createdAt: string;
  dueAt: string | null;
  overdue: boolean;
  actingFor: string | null;
  meta?: string;
  steps?: { step_number: number; status: string }[];
};

export type ApprovalsData = { items: ApprovalCard[]; partialError: string | null };

export const APPROVALS_KEY = ['approvals'] as const;

const KIND_LABELS: Record<string, string> = {
  leave: 'Leave request',
  leave_request: 'Leave request',
  comp_off: 'Comp-off request',
  compoff: 'Comp-off request',
  expense: 'Expense claim',
  estimate: 'Estimate',
  estimate_version: 'Estimate',
  timesheet: 'Timesheet',
  overtime: 'Overtime request',
  regularization: 'Attendance regularization',
  attendance_regularization: 'Attendance regularization',
  salary_advance: 'Salary advance',
  travel: 'Travel request',
};

/** "comp_off" -> "Comp-off request"; unknown kinds are title-cased ("some_thing" -> "Some thing"). */
export function kindLabel(kind: string): string {
  const k = kind.trim().toLowerCase();
  if (KIND_LABELS[k]) return KIND_LABELS[k];
  const t = k.replace(/[_-]+/g, ' ').trim();
  return t ? t.charAt(0).toUpperCase() + t.slice(1) : 'Request';
}

function actingName(a: { user_id: number; name: string | null } | null): string | null {
  return a ? a.name || `user #${a.user_id}` : null;
}

export function chainToCard(q: ChainQueueItem): ApprovalCard {
  const kind = q.entity?.kind || q.instance.entity_type || 'item';
  const title =
    q.entity?.title ||
    q.entity?.purpose ||
    (q.entity?.from_city && q.entity?.to_city ? `${q.entity.from_city} → ${q.entity.to_city}` : null) ||
    `${kindLabel(kind)} #${q.instance.id}`;
  const lines = q.entity?.line_count ?? 0;
  return {
    key: `chain-${q.instance.id}`,
    source: 'chain',
    refId: q.instance.id,
    kind: kindLabel(kind),
    title,
    subtitle: [q.step_instance.label, q.entity?.description].filter(Boolean).join(' · '),
    requester: null, // the queue carries only submitter_id, never a name: don't show "user #id"
    amountPaise: q.entity?.amount_paise ?? q.instance.amount_paise ?? null,
    createdAt: q.instance.created_at,
    dueAt: q.due_at,
    overdue: !!q.is_overdue,
    actingFor: actingName(q.acting_for),
    meta: lines > 0 ? `${lines} line item${lines > 1 ? 's' : ''}${q.entity?.out_of_policy_count ? ` · ${q.entity.out_of_policy_count} out-of-policy` : ''}` : undefined,
  };
}

export function legacyToCard(l: LegacyInboxItem): ApprovalCard {
  return {
    key: `legacy-${l.id}`,
    source: 'legacy',
    refId: l.id,
    kind: kindLabel(l.resource_type),
    title: l.requested_by_name ? `${kindLabel(l.resource_type)} · ${l.requested_by_name}` : kindLabel(l.resource_type),
    subtitle: `Step ${l.current_step_number}`,
    requester: l.requested_by_name,
    amountPaise: null,
    createdAt: l.created_at,
    dueAt: l.due_at ?? l.due_date,
    overdue: !!l.is_overdue,
    actingFor: actingName(l.acting_for),
    steps: l.steps?.map((s) => ({ step_number: s.step_number, status: s.status })),
  };
}

/** Overdue first, otherwise chain items before legacy (as on web), original order preserved. */
export function mergeApprovals(chain: ChainQueueItem[], legacy: LegacyInboxItem[]): ApprovalCard[] {
  const all = [...chain.map(chainToCard), ...legacy.map(legacyToCard)];
  return [...all.filter((c) => c.overdue), ...all.filter((c) => !c.overdue)];
}

/**
 * Both sources are fetched in parallel. If one fails the other still renders (with `partialError`);
 * if both fail the (gate-error-preferred) error is thrown so callers can show the gate notice.
 */
export async function fetchApprovals(): Promise<ApprovalsData> {
  const [chainR, legacyR] = await Promise.allSettled([
    api.get<ChainQueueItem[]>('/approval-chains/my-queue'),
    api.get<LegacyInboxItem[]>('/approvals/inbox'),
  ]);
  if (chainR.status === 'rejected' && legacyR.status === 'rejected') {
    throw [chainR.reason, legacyR.reason].find(isGateError) ?? normalizeError(legacyR.reason);
  }
  const failed = chainR.status === 'rejected' ? chainR.reason : legacyR.status === 'rejected' ? legacyR.reason : null;
  return {
    items: mergeApprovals(
      chainR.status === 'fulfilled' && Array.isArray(chainR.value.data) ? chainR.value.data : [],
      legacyR.status === 'fulfilled' && Array.isArray(legacyR.value.data) ? legacyR.value.data : [],
    ),
    partialError: failed ? normalizeError(failed).message : null,
  };
}

export async function actOnApproval(card: ApprovalCard, action: 'approve' | 'reject', comment?: string): Promise<void> {
  const note = comment?.trim() || null;
  if (card.source === 'chain') {
    await api.post(`/approval-chains/instances/${card.refId}/act`, { action, comment: note });
  } else {
    await api.post(`/approvals/${card.refId}/action`, { status: action === 'approve' ? 'approved' : 'rejected', comment: note });
  }
}

/** Legacy items only (like web); chain items are acted on one at a time. */
export async function bulkAction(ids: number[], action: 'approve' | 'reject', comment?: string): Promise<BulkResult> {
  const res = await api.post<BulkResult>('/approvals/bulk-action', {
    items: ids.map((id) => ({ kind: 'legacy', id })),
    action,
    comment: comment?.trim() || null,
  });
  return res.data;
}
