import React, { useCallback, useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';
import { Card, Button, Badge } from '../ui-elements';
import { errMsg } from '../schedule-delegations-utils';
import { OpenShift, STATUS_TONE, fmtDate, mySchedule, statusLabel } from './my-schedule-api';
import { InlineConfirm } from './inline-confirm';

export const OpenShiftsPanel: React.FC<{ reloadKey?: number }> = ({ reloadKey = 0 }) => {
  const [rows, setRows] = useState<OpenShift[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<Set<number>>(new Set());
  const seq = useRef(0);

  const load = useCallback(async () => {
    const my = ++seq.current;
    try {
      const r = await mySchedule.availableOpenShifts();
      if (my === seq.current) setRows(r);
    } catch (e: any) {
      if (my === seq.current) toast.error(errMsg(e, 'Failed to load open shifts'));
    } finally {
      if (my === seq.current) setLoading(false);
    }
  }, []);
  useEffect(() => { load(); }, [load, reloadKey]);

  const run = async (id: number, fn: () => Promise<OpenShift>, ok: string, fail: string) => {
    setBusy((b) => new Set(b).add(id));
    try {
      const r = await fn();
      toast.success(r?.my_claim_status === 'approved' ? 'Claim confirmed — the shift is yours' : ok);
      (r?.warnings || []).forEach((w) => toast.warning(w));
      await load();
    } catch (e: any) {
      toast.error(errMsg(e, fail));
      await load();
    } finally {
      setBusy((b) => { const n = new Set(b); n.delete(id); return n; });
    }
  };

  return (
    <Card className="p-5 border-slate-200 bg-white">
      <p className="text-[10px] font-black uppercase tracking-widest text-[#0F172A]">Open shifts</p>
      <p className="text-[10px] text-slate-500 mt-0.5 mb-3">
        Unfilled shifts in the next 60 days that you are eligible for. Your scheduler confirms claims.
      </p>
      {loading ? (
        <p className="text-[10px] font-black uppercase tracking-widest text-slate-400 py-6 text-center">Loading…</p>
      ) : rows.length === 0 ? (
        <p className="text-[10px] font-black uppercase tracking-widest text-slate-400 py-6 text-center">
          No open shifts right now
        </p>
      ) : (
        <ul className="space-y-2">
          {rows.map((o) => (
            <li key={o.id} className="border border-slate-100 rounded-xl p-3 flex items-center justify-between gap-3 flex-wrap">
              <div className="min-w-0">
                <p className="text-[12px] font-black text-[#0F172A]">
                  {fmtDate(o.work_date)} · {o.shift_name || 'Shift'}
                  {o.shift_start ? (
                    <span className="text-[10px] font-bold text-slate-500 tabular-nums">
                      {' '}{o.shift_start.slice(0, 5)}–{(o.shift_end || '').slice(0, 5)}
                    </span>
                  ) : null}
                </p>
                <p className="text-[10px] text-slate-500">
                  {[o.department, o.location].filter(Boolean).join(' · ') || 'Any department'}
                  {` · ${o.filled}/${o.slots} filled`}
                </p>
                {o.note && <p className="text-[10px] text-slate-500 italic truncate">"{o.note}"</p>}
              </div>
              <div className="flex items-center gap-3 shrink-0">
                {o.my_claim_status && (
                  <Badge variant={STATUS_TONE[o.my_claim_status] || 'neutral'} className="text-[8px] uppercase">
                    {statusLabel(o.my_claim_status)}
                  </Badge>
                )}
                {o.my_claim_status === 'pending' && o.my_claim_id ? (
                  <InlineConfirm label="Withdraw" tone="neutral" ariaLabel={`Withdraw claim for ${fmtDate(o.work_date)}`} busy={busy.has(o.id)}
                    onConfirm={() => run(o.id, () => mySchedule.withdraw(o.my_claim_id as number),
                      'Claim withdrawn', 'Failed to withdraw claim')} />
                ) : !o.my_claim_status || o.my_claim_status === 'withdrawn' ? (
                  <Button size="sm" className="h-8" isLoading={busy.has(o.id)}
                    aria-label={`Claim open shift on ${fmtDate(o.work_date)}`}
                    onClick={() => run(o.id, () => mySchedule.claim(o.id),
                      'Claim submitted — awaiting confirmation', 'Failed to claim shift')}>
                    Claim
                  </Button>
                ) : null}
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
};
