import React, { useState } from 'react';
import { toast } from 'sonner';
import { Plus } from 'lucide-react';
import { Card, Button, Badge } from '../ui-elements';
import { errMsg } from '../schedule-delegations-utils';
import { STATUS_TONE, fmtDate, statusLabel } from '../my-schedule/my-schedule-api';
import { InlineConfirm } from '../my-schedule/inline-confirm';
import { schedulerApi, type SchedOpenShift } from './roster-api';

interface Props {
  shifts: SchedOpenShift[];
  onChanged: () => void | Promise<void>;
  onNew: () => void;
}

/** Scheduler list of open shifts (next 60 days) with claim decisions. */
export const OpenShiftsSchedulerPanel: React.FC<Props> = ({ shifts, onChanged, onNew }) => {
  const [busy, setBusy] = useState<Set<string>>(new Set());
  const [warnings, setWarnings] = useState<Record<number, string[]>>({});

  const run = async (
    key: string, shiftId: number, fn: () => Promise<SchedOpenShift>, ok: string, fail: string
  ) => {
    setBusy((b) => new Set(b).add(key));
    try {
      const r = await fn();
      toast.success(ok);
      const w = r?.warnings || [];
      setWarnings((m) => ({ ...m, [shiftId]: w }));
      w.forEach((x) => toast.warning(x));
      await onChanged();
    } catch (e: any) {
      toast.error(errMsg(e, fail));
      await onChanged();
    } finally {
      setBusy((b) => { const n = new Set(b); n.delete(key); return n; });
    }
  };

  return (
    <Card className="p-5 border-slate-200 bg-white" aria-label="Open shifts">
      <div className="flex items-center justify-between gap-3 flex-wrap mb-3">
        <div>
          <p className="text-[10px] font-black uppercase tracking-widest text-[#0F172A]">Open shifts</p>
          <p className="text-[10px] text-slate-500 mt-0.5">Unfilled shifts in the next 60 days and their claims.</p>
        </div>
        <Button size="sm" onClick={onNew} className="gap-1.5" aria-label="Post a new open shift">
          <Plus size={14} /> Post open shift
        </Button>
      </div>
      {shifts.length === 0 ? (
        <p className="text-[10px] font-black uppercase tracking-widest text-slate-400 py-6 text-center">
          No open shifts
        </p>
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
                  {o.status === 'open' && (
                    <InlineConfirm label="Cancel shift" ariaLabel={`Cancel open shift on ${fmtDate(o.work_date)}`}
                      busy={busy.has(`os-${o.id}`)}
                      onConfirm={() => run(`os-${o.id}`, o.id, () => schedulerApi.cancelOpenShift(o.id),
                        'Open shift cancelled', 'Failed to cancel open shift')} />
                  )}
                </div>
              </div>
              {(warnings[o.id] || []).length > 0 && (
                <ul className="text-[10px] text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-2 py-1 list-disc list-inside">
                  {warnings[o.id].map((w, i) => <li key={i}>{w}</li>)}
                </ul>
              )}
              {o.claims.length > 0 && (
                <ul className="border-t border-slate-100 pt-2 space-y-1.5">
                  {o.claims.map((c) => {
                    const k = `claim-${c.id}`;
                    return (
                      <li key={c.id} className="flex items-center justify-between gap-3 flex-wrap">
                        <div className="min-w-0">
                          <span className="text-[11px] font-bold text-slate-800">
                            {c.user_name || `User #${c.user_id}`}
                          </span>
                          <Badge variant={STATUS_TONE[c.status] || 'neutral'} className="text-[8px] uppercase ml-2">
                            {statusLabel(c.status)}
                          </Badge>
                          {c.status === 'pending' && c.eligibility_reason && (
                            <p className="text-[10px] text-amber-700">Cannot be confirmed now: {c.eligibility_reason}</p>
                          )}
                        </div>
                        {c.status === 'pending' && (
                          <div className="flex items-center gap-2">
                            <Button size="sm" className="h-8" isLoading={busy.has(k)}
                              aria-label={`Approve claim by ${c.user_name || c.user_id}`}
                              onClick={() => run(k, o.id, () => schedulerApi.decideClaim(c.id, 'approve'),
                                'Claim approved', 'Failed to approve claim')}>
                              Approve
                            </Button>
                            <Button size="sm" variant="outline" className="h-8" disabled={busy.has(k)}
                              aria-label={`Reject claim by ${c.user_name || c.user_id}`}
                              onClick={() => run(k, o.id, () => schedulerApi.decideClaim(c.id, 'reject'),
                                'Claim rejected', 'Failed to reject claim')}>
                              Reject
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
