import React, { useEffect, useState } from 'react';
import { Check, X, Loader2, MessageSquare, Inbox } from 'lucide-react';
import { toast } from 'sonner';
import { cn, errMsg, fmtInr, fmtDate, EmptyState } from '../../components/ui-elements';
import { client } from '../../api/client';
import { ENDPOINTS } from '../../api/endpoints';

// ---- Types ------------------------------------------------------------

interface ChainInstance {
  id: number;
  entity_type: string;
  submitter_id: number;
  amount_paise: number | null;
  created_at: string;
}

interface ChainQueueItem {
  step_instance: {
    id: number;
    step_order: number;
    label: string | null;
    approver_type: string;
  };
  instance: ChainInstance;
  entity: {
    kind: string;
    title?: string;
    purpose?: string;
    amount_paise?: number | null;
    description?: string;
    from_city?: string;
    to_city?: string;
    line_count?: number;
    out_of_policy_count?: number;
  } | null;
}

interface LegacyInboxItem {
  id: number;
  resource_type: string;
  resource_id: string;
  status: string;
  current_step_number: number;
  requested_by_id: number | null;
  requested_by_name: string | null;
  created_at: string;
  due_date: string | null;
}

// Normalised card model — both sources feed into this.
interface Card {
  key: string;
  source: 'chain' | 'legacy';
  refId: number;
  kind: string;
  title: string;
  subtitle: string;
  amountPaise: number | null;
  createdAt: string;
  meta?: string;
}

// ---- Screen -----------------------------------------------------------

export const MobileApprovals: React.FC = () => {
  const [items, setItems] = useState<Card[]>([]);
  const [loading, setLoading] = useState(true);
  const [acting, setActing] = useState<string | null>(null);
  const [commentFor, setCommentFor] = useState<Card | null>(null);

  useEffect(() => {
    void load();
  }, []);

  const load = async () => {
    setLoading(true);
    try {
      const [chainR, legacyR] = await Promise.all([
        client
          .get<ChainQueueItem[]>(ENDPOINTS.APPROVAL_CHAINS.MY_QUEUE)
          .catch(() => ({ data: [] })),
        client
          .get<LegacyInboxItem[]>(ENDPOINTS.APPROVALS.INBOX)
          .catch(() => ({ data: [] })),
      ]);
      const chainCards: Card[] = (chainR.data || []).map((q) => {
        const kind = q.entity?.kind || q.instance.entity_type || 'item';
        const title =
          q.entity?.title ||
          q.entity?.purpose ||
          (q.entity?.from_city && q.entity?.to_city
            ? `${q.entity.from_city} → ${q.entity.to_city}`
            : null) ||
          `${kind} #${q.instance.id}`;
        const subtitle = [
          q.step_instance.label,
          q.entity?.description,
        ]
          .filter(Boolean)
          .join(' · ');
        return {
          key: `chain-${q.instance.id}`,
          source: 'chain',
          refId: q.instance.id,
          kind,
          title,
          subtitle,
          amountPaise: q.entity?.amount_paise ?? q.instance.amount_paise ?? null,
          createdAt: q.instance.created_at,
          meta:
            q.entity?.line_count && q.entity.line_count > 0
              ? `${q.entity.line_count} line item${q.entity.line_count > 1 ? 's' : ''}` +
                (q.entity.out_of_policy_count
                  ? ` · ${q.entity.out_of_policy_count} out-of-policy`
                  : '')
              : undefined,
        };
      });
      const legacyCards: Card[] = (legacyR.data || []).map((l) => ({
        key: `legacy-${l.id}`,
        source: 'legacy',
        refId: l.id,
        kind: l.resource_type,
        title: `${l.resource_type} ${l.resource_id}`,
        subtitle: l.requested_by_name
          ? `Requested by ${l.requested_by_name}`
          : `Step ${l.current_step_number}`,
        amountPaise: null,
        createdAt: l.created_at,
      }));
      setItems([...chainCards, ...legacyCards]);
    } catch (e) {
      toast.error(errMsg(e, 'Failed to load approvals'));
    } finally {
      setLoading(false);
    }
  };

  const act = async (card: Card, action: 'approve' | 'reject', comment?: string) => {
    setActing(card.key);
    try {
      if (card.source === 'chain') {
        await client.post(ENDPOINTS.APPROVAL_CHAINS.INSTANCE_ACT(card.refId), {
          action,
          comment: comment || null,
        });
      } else {
        await client.post(ENDPOINTS.APPROVALS.ACTION(card.refId), {
          status: action === 'approve' ? 'APPROVED' : 'REJECTED',
          comment: comment || null,
        });
      }
      toast.success(action === 'approve' ? 'Approved.' : 'Rejected.');
      setItems((prev) => prev.filter((c) => c.key !== card.key));
    } catch (e) {
      toast.error(errMsg(e, 'Action failed'));
    } finally {
      setActing(null);
      setCommentFor(null);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 size={22} className="animate-spin text-slate-400" />
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div className="p-4">
        <EmptyState
          title="Nothing to approve"
          hint="Requests waiting for your call will appear here."
        />
      </div>
    );
  }

  return (
    <div className="p-4 space-y-3">
      <div className="flex items-center justify-between px-1">
        <h2 className="text-[13px] font-black uppercase tracking-widest text-slate-500 flex items-center gap-2">
          <Inbox size={14} /> Pending · {items.length}
        </h2>
        <button
          type="button"
          onClick={load}
          className="text-[12px] font-bold text-[#2563EB]"
        >
          Refresh
        </button>
      </div>
      <ul className="space-y-3">
        {items.map((c) => (
          <li
            key={c.key}
            className="bg-white border border-slate-200 rounded-2xl p-4 space-y-3"
          >
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0 flex-1">
                <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400">
                  {c.kind}
                </p>
                <p className="text-sm font-black text-[#0F172A] mt-0.5 truncate">
                  {c.title}
                </p>
                {c.subtitle && (
                  <p className="text-[12px] text-slate-500 mt-0.5 line-clamp-2">
                    {c.subtitle}
                  </p>
                )}
                <p className="text-[11px] text-slate-400 mt-1">
                  Submitted {fmtDate(c.createdAt)}
                  {c.meta && ` · ${c.meta}`}
                </p>
              </div>
              {c.amountPaise != null && (
                <div className="text-right flex-shrink-0">
                  <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400">
                    Amount
                  </p>
                  <p className="text-base font-black text-[#0F172A] tabular-nums">
                    {fmtInr(c.amountPaise)}
                  </p>
                </div>
              )}
            </div>
            <div className="grid grid-cols-3 gap-2">
              <button
                type="button"
                onClick={() => act(c, 'approve')}
                disabled={acting === c.key}
                className={cn(
                  'h-11 rounded-xl bg-emerald-600 text-white font-bold active:bg-emerald-700 flex items-center justify-center gap-1',
                  acting === c.key && 'opacity-70'
                )}
              >
                {acting === c.key ? (
                  <Loader2 size={16} className="animate-spin" />
                ) : (
                  <Check size={16} />
                )}
                Approve
              </button>
              <button
                type="button"
                onClick={() => setCommentFor({ ...c, key: c.key + ':comment' })}
                disabled={acting === c.key}
                className="h-11 rounded-xl border border-slate-200 font-bold text-slate-700 active:bg-slate-50 flex items-center justify-center gap-1"
                aria-label="Comment"
              >
                <MessageSquare size={16} />
              </button>
              <button
                type="button"
                onClick={() => act(c, 'reject')}
                disabled={acting === c.key}
                className={cn(
                  'h-11 rounded-xl bg-red-600 text-white font-bold active:bg-red-700 flex items-center justify-center gap-1',
                  acting === c.key && 'opacity-70'
                )}
              >
                {acting === c.key ? (
                  <Loader2 size={16} className="animate-spin" />
                ) : (
                  <X size={16} />
                )}
                Reject
              </button>
            </div>
          </li>
        ))}
      </ul>
      {commentFor && (
        <CommentSheet
          card={commentFor}
          onCancel={() => setCommentFor(null)}
          onSubmit={(action, comment) => {
            const orig = items.find((i) => commentFor.key.startsWith(i.key));
            if (!orig) {
              setCommentFor(null);
              return;
            }
            void act(orig, action, comment);
          }}
        />
      )}
    </div>
  );
};

const CommentSheet: React.FC<{
  card: Card;
  onCancel: () => void;
  onSubmit: (action: 'approve' | 'reject', comment: string) => void;
}> = ({ card, onCancel, onSubmit }) => {
  const [comment, setComment] = useState('');
  return (
    <div
      className="fixed inset-0 z-50 bg-slate-900/50 flex items-end"
      role="dialog"
      aria-modal="true"
      onClick={onCancel}
    >
      <div
        className="w-full bg-white rounded-t-3xl p-5 space-y-4"
        onClick={(e) => e.stopPropagation()}
        style={{ paddingBottom: 'calc(env(safe-area-inset-bottom) + 20px)' }}
      >
        <div className="w-10 h-1 bg-slate-200 rounded-full mx-auto" />
        <h2 className="text-lg font-black text-[#0F172A]">Comment (optional)</h2>
        <p className="text-[12px] text-slate-500 -mt-2 truncate">{card.title}</p>
        <textarea
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          placeholder="Add a note the submitter will see…"
          className="w-full min-h-24 rounded-xl border border-slate-200 p-3 text-sm"
          autoFocus
        />
        <div className="grid grid-cols-2 gap-3">
          <button
            type="button"
            onClick={() => onSubmit('reject', comment)}
            className="h-12 rounded-xl bg-red-600 text-white font-bold active:bg-red-700"
          >
            Reject
          </button>
          <button
            type="button"
            onClick={() => onSubmit('approve', comment)}
            className="h-12 rounded-xl bg-emerald-600 text-white font-bold active:bg-emerald-700"
          >
            Approve
          </button>
        </div>
        <button
          type="button"
          onClick={onCancel}
          className="w-full h-11 rounded-xl border border-slate-200 font-bold text-slate-700"
        >
          Back
        </button>
      </div>
    </div>
  );
};
