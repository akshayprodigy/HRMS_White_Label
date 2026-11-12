import React, { useState } from 'react';
import { toast } from 'sonner';
import { Plus } from 'lucide-react';
import { Card, Button, Badge } from '../ui-elements';
import { errMsg } from '../schedule-delegations-utils';
import { STATUS_TONE, fmtDate, statusLabel } from '../my-schedule/my-schedule-api';
import { InlineConfirm } from '../my-schedule/inline-confirm';
import { schedulerApi, type SchedOpenShift } from './roster-api';
import { OPEN_SHIFT_HORIZON_DAYS } from './use-requests';

interface Props {
  shifts: SchedOpenShift[];
  error?: string;
  onRetry: () => void;
  onChanged: () => void | Promise<void>;
  onNew: () => void;
  /** viewer may publish (planner grid can_publish); gates posting */
  canPost?: boolean;
  /** report a decision outcome (and any warnings) to the result area */
  onResult: (title: string, lines: string[]) => void;
}

/** Scheduler list of open shifts with claim decisions. */
export const OpenShiftsSchedulerPanel: React.FC<Props> = ({
  shifts, error, onRetry, onChanged, onNew, onResult, canPost = true,
}) => {
  // key -> pending action, so only the clicked button spins
  const [busy, setBusy] = useState<Map<string, string>>(new Map());

  const run = async (
    key: string, action: string, fn: () => Promise<SchedOpenShift>, ok: string, fail: string
  ) => {
    setBusy((b) => new Map(b).set(key, action));
    try {
      const r = await fn();
      toast.success(ok);
      onResult(ok, r?.warnings || []);
    } catch (e: any) {
      toast.error(errMsg(e, fail));
    } finally {
      setBusy((b) => { const n = new Map(b); n.delete(key); return n; });
      await onChanged();
    }
  };

  return (
    <Card className="p-5 border-slate-200 bg-white" aria-label="Open shifts">
      <div className="flex items-center justify-between gap-3 flex-wrap mb-3">
        <div>
          <p className="text-[10px] font-black uppercase tracking-widest text-[#0F172A]">Open shifts</p>
          <p className="text-[10px] text-slate-500 mt-0.5">
            Unfilled shifts in the next {OPEN_SHIFT_HORIZON_DAYS} days and their claims.
          </p>
        </div>
        {canPost ? (
          <Button size="sm" onClick={onNew} className="gap-1.5" aria-label="Post a new open shift">
            <Plus size={14} /> Post open shift
          </Button>
        ) : (
          <span className="text-[10px] text-slate-500">
            You can't post open shifts (publish permission required).
          </span>
        )}
      </div>
      {error && (
        <div role="alert" className="text-[11px] text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2 mb-3 flex items-center gap-3">
          <span className="flex-1">Couldn't load: {error}</span>
          <Button size="sm" variant="outline" onClick={onRetry}>Retry</Button>
        </div>
      )}
      {shifts.length === 0 ? (
        !error && (
          <p className="text-[10px] font-black uppercase tracking-widest text-slate-400 py-6 text-center">
            No open shifts in the next {OPEN_SHIFT_HORIZON_DAYS} days
          </p>
        )
      ) : (
        <ul className="space-y-2">
          {shifts.map((o) => (
            <li key={o.id} className="border border-slate-100 rounded-xl p-3 space-y-2">
              <div className="flex items-start justify-between gap-3 flex-wrap">
                <div className="min-w-0">
                  <p className="text-[12px] font-black text-[#0F172A]">
                    {fmtDate(o.work_date)} · {o.shift_name || 'Shift'}
                    {o.shift_start && (
                      <span className="text-[10px] font-bold text-slate-500 tabular-nums">
                        {' '}{o.shift_start.slice(0, 5)}–{(o.shift_end || '').slice(0, 5)}
                      </span>
                    )}
                  </p>
                  <p className="text-[10px] text-slate-500">
                    {[o.department, o.location].filter(Boolean).join(' · ') || 'Any department'}
                    {` · ${o.filled}/${o.slots} filled`}
                    {o.auto_confirm ? ' · auto-confirm' : ''}
                    {o.created_by_name ? ` · posted by ${o.created_by_name}` : ''}
                  </p>
                  {o.note && <p className="text-[10px] text-slate-500 italic">"{o.note}"</p>}
                </div>
                <div className="flex items-center gap-3 shrink-0">
                  <Badge variant={STATUS_TONE[o.status] || 'neutral'} className="text-[8px] uppercase">
                    {statusLabel(o.status)}
                  </Badge>
                  {o.status === 'open' && o.can_cancel && (
                    <InlineConfirm label="Cancel shift" ariaLabel={`Cancel open shift on ${fmtDate(o.work_date)}`}
                      busy={busy.has(`os-${o.id}`)}
                      onConfirm={() => run(`os-${o.id}`, 'cancel', () => schedulerApi.cancelOpenShift(o.id),
                        'Open shift cancelled', 'Failed to cancel open shift')} />
                  )}
                </div>
              </div>
              {o.claims.length > 0 && (
                <ul className="border-t border-slate-100 pt-2 space-y-1.5">
                  {o.claims.map((c) => {
                    const k = `claim-${c.id}`;
                    const who = c.user_name || `User #${c.user_id}`;
                    const pending = busy.get(k);
                    return (
                      <li key={c.id} className="flex items-center justify-between gap-3 flex-wrap">
                        <div className="min-w-0">
                          <span className="text-[11px] font-bold text-slate-800">{who}</span>
                          {c.can_decide === false && c.status === 'pending' && (
                            <span className="text-[10px] text-slate-500 ml-2">(your claim, another approver decides)</span>
                          )}
                          <Badge variant={STATUS_TONE[c.status] || 'neutral'} className="text-[8px] uppercase ml-2">
                            {statusLabel(c.status)}
                          </Badge>
                          {c.status === 'pending' && c.eligibility_reason && (
                            <p className="text-[10px] text-amber-700">Cannot be confirmed now: {c.eligibility_reason}</p>
                          )}
                        </div>
                        {c.status === 'pending' && c.can_decide !== false && (
                          <div className="flex items-center gap-2">
                            <Button size="sm" className="h-8" isLoading={pending === 'approve'} disabled={!!pending}
                              aria-label={`Approve claim by ${who}`}
                              onClick={() => run(k, 'approve', () => schedulerApi.decideClaim(c.id, 'approve'),
                                'Claim approved', 'Failed to approve claim')}>
                              Approve
                            </Button>
                            <Button size="sm" variant="outline" className="h-8" disabled={!!pending}
                              aria-label={`Reject claim by ${who}`}
                              onClick={() => run(k, 'reject', () => schedulerApi.decideClaim(c.id, 'reject'),
                                'Claim rejected', 'Failed to reject claim')}>
                              {pending === 'reject' ? '…' : 'Reject'}
                            </Button>
                          </div>
                        )}
                      </li>
                    );
                  })}
                </ul>
              )}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
};
