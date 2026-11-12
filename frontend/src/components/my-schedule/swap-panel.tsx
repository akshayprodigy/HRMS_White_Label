import React, { useCallback, useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';
import { Card, Button, Badge } from '../ui-elements';
import { errMsg } from '../schedule-delegations-utils';
import {
  Drop, Swap, STATUS_TONE, fmtDate, mySchedule, statusLabel,
} from './my-schedule-api';
import { InlineConfirm } from './inline-confirm';

const cellText = (c: { shift_name: string | null; is_week_off: boolean } | null) =>
  !c ? '—' : c.is_week_off ? 'Week off' : c.shift_name || 'Shift';

const StatusBadge = ({ s }: { s: string }) => (
  <Badge variant={STATUS_TONE[s] || 'neutral'} className="text-[8px] uppercase">
    {statusLabel(s)}
  </Badge>
);

/** Swap requests (incoming/outgoing) and give-away requests of the user. */
export const SwapPanel: React.FC<{ reloadKey?: number }> = ({ reloadKey = 0 }) => {
  const [swaps, setSwaps] = useState<Swap[]>([]);
  const [drops, setDrops] = useState<Drop[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<Set<string>>(new Set());
  const seq = useRef(0);

  const load = useCallback(async () => {
    const my = ++seq.current;
    try {
      const [s, d] = await Promise.all([mySchedule.mySwaps(), mySchedule.myDrops()]);
      if (my !== seq.current) return;
      setSwaps(s);
      setDrops(d);
    } catch (e: any) {
      if (my === seq.current) toast.error(errMsg(e, 'Failed to load swaps'));
    } finally {
      if (my === seq.current) setLoading(false);
    }
  }, []);
  useEffect(() => { load(); }, [load, reloadKey]);

  const act = async (key: string, fn: () => Promise<unknown>, ok: string, fail: string) => {
    setBusy((b) => new Set(b).add(key));
    try {
      await fn();
      toast.success(ok);
      await load();
    } catch (e: any) {
      toast.error(errMsg(e, fail));
    } finally {
      setBusy((b) => { const n = new Set(b); n.delete(key); return n; });
    }
  };

  const incoming = swaps.filter((s) => s.direction === 'incoming');
  const outgoing = swaps.filter((s) => s.direction === 'outgoing');

  const swapRow = (s: Swap, mine: boolean) => {
    const other = mine ? s.counterparty_name : s.requester_name;
    const myCell = mine ? s.requester_cell : s.counterparty_cell;
    const theirCell = mine ? s.counterparty_cell : s.requester_cell;
    const myDate = mine ? s.requester_date : s.counterparty_date;
    const theirDate = mine ? s.counterparty_date : s.requester_date;
    return (
      <li key={s.id} className="border border-slate-100 rounded-xl p-3">
        <div className="flex items-center justify-between gap-2">
          <p className="text-[12px] font-black text-[#0F172A]">
            {mine ? 'You ⇄ ' : ''}{other || 'Colleague'}{!mine ? ' ⇄ You' : ''}
          </p>
          <StatusBadge s={s.status} />
        </div>
        <p className="text-[10px] font-bold text-slate-600 mt-1">
          You give {cellText(myCell)} on {fmtDate(myDate)} · you get {cellText(theirCell)} on {fmtDate(theirDate)}
        </p>
        {s.reason && <p className="text-[10px] text-slate-500 italic mt-1 truncate">"{s.reason}"</p>}
        {s.decision_note && <p className="text-[10px] text-slate-500 mt-1">Note: {s.decision_note}</p>}
        <div className="mt-2 flex items-center gap-3 flex-wrap">
          {!mine && s.status === 'pending_peer' && (
            <>
              <Button size="sm" className="h-8"
                aria-label={`Accept swap from ${other || 'colleague'}`}
                isLoading={busy.has(`a${s.id}`)}
                onClick={() => act(`a${s.id}`, () => mySchedule.swapAction(s.id, 'accept'),
                  'Swap accepted — sent for approval', 'Failed to accept swap')}>
                Accept
              </Button>
              <Button size="sm" variant="outline" className="h-8"
                aria-label={`Decline swap from ${other || 'colleague'}`}
                isLoading={busy.has(`d${s.id}`)}
                onClick={() => act(`d${s.id}`, () => mySchedule.swapAction(s.id, 'decline'),
                  'Swap declined', 'Failed to decline swap')}>
                Decline
              </Button>
            </>
          )}
          {mine && (s.status === 'pending_peer' || s.status === 'pending_approval') && (
            <InlineConfirm label="Cancel request" ariaLabel={`Cancel swap with ${other || 'colleague'}`}
              busy={busy.has(`c${s.id}`)}
              onConfirm={() => act(`c${s.id}`, () => mySchedule.swapAction(s.id, 'cancel'),
                'Swap cancelled', 'Failed to cancel swap')} />
          )}
        </div>
      </li>
    );
  };

  const head = 'text-[9px] font-black uppercase tracking-widest text-slate-400 mb-2';
  const empty = (t: string) => (
    <p className="text-[10px] font-black uppercase tracking-widest text-slate-400 py-3 text-center">{t}</p>
  );

  return (
    <div className="space-y-4">
      <Card className="p-5 border-slate-200 bg-white">
        <p className="text-[10px] font-black uppercase tracking-widest text-[#0F172A] mb-1">Shift swaps</p>
        <p className="text-[10px] text-slate-500 mb-3">
          Start a swap from a day in the week strip on the Week tab.
        </p>
        {loading ? empty('Loading…') : (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <div>
              <p className={head}>Incoming ({incoming.length})</p>
              {incoming.length ? <ul className="space-y-2">{incoming.map((s) => swapRow(s, false))}</ul>
                : empty('No incoming requests')}
            </div>
            <div>
              <p className={head}>Outgoing ({outgoing.length})</p>
              {outgoing.length ? <ul className="space-y-2">{outgoing.map((s) => swapRow(s, true))}</ul>
                : empty('No outgoing requests')}
            </div>
          </div>
        )}
      </Card>

      <Card className="p-5 border-slate-200 bg-white">
        <p className="text-[10px] font-black uppercase tracking-widest text-[#0F172A] mb-3">
          My give-away requests
        </p>
        {loading ? empty('Loading…') : drops.length === 0 ? empty('No give-away requests') : (
          <ul className="space-y-2">
            {drops.map((d) => (
              <li key={d.id} className="border border-slate-100 rounded-xl p-3">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-[12px] font-black text-[#0F172A]">
                    {d.shift_name || 'Shift'} · {fmtDate(d.work_date)}
                  </p>
                  <StatusBadge s={d.status} />
                </div>
                <p className="text-[10px] text-slate-500 italic mt-1 truncate">"{d.reason}"</p>
                {d.decision_note && <p className="text-[10px] text-slate-500 mt-1">Note: {d.decision_note}</p>}
                {d.status === 'pending' && (
                  <div className="mt-2">
                    <InlineConfirm label="Cancel request" ariaLabel={`Cancel give-away for ${fmtDate(d.work_date)}`}
                      busy={busy.has(`x${d.id}`)}
                      onConfirm={() => act(`x${d.id}`, () => mySchedule.cancelDrop(d.id),
                        'Give-away cancelled', 'Failed to cancel give-away')} />
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
};
