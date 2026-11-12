import React, { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { AlertTriangle, ArrowRight, RefreshCw } from 'lucide-react';
import { Card, Button, Badge } from '../ui-elements';
import { errMsg } from '../schedule-delegations-utils';
import { fmtDate, inputCls, labelCls } from '../my-schedule/my-schedule-api';
import {
  schedulerApi,
  type ApproverSwap,
  type SchedDrop,
  type SchedOpenShift,
  type SwapWarning,
} from './roster-api';
import { OpenShiftsSchedulerPanel } from './open-shifts-panel';

const cellText = (c: { shift_name: string | null; is_week_off: boolean }) =>
  c.is_week_off ? 'Week off' : c.shift_name || '—';

const NoteField = ({
  id, value, onChange,
}: { id: string; value: string; onChange: (v: string) => void }) => (
  <div className="space-y-1 flex-1 min-w-[200px]">
    <label htmlFor={id} className={labelCls}>Note (optional)</label>
    <input id={id} className={inputCls} maxLength={500} value={value}
      onChange={(e) => onChange(e.target.value)} placeholder="Shown to the employees" />
  </div>
);

const SwapCard = ({
  swap, busy, onDecide,
}: {
  swap: ApproverSwap;
  busy: boolean;
  onDecide: (s: ApproverSwap, action: 'approve' | 'reject', note: string) => void;
}) => {
  const [note, setNote] = useState('');
  const [warns, setWarns] = useState<SwapWarning[] | null>(null);
  const [checkErr, setCheckErr] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    setWarns(null);
    setCheckErr(null);
    schedulerApi.swapCheck(swap.id)
      .then((w) => live && setWarns(w))
      .catch((e: any) => live && setCheckErr(errMsg(e, 'Could not check scheduling rules')));
    return () => { live = false; };
  }, [swap.id]);

  return (
    <li className="border border-slate-100 rounded-xl p-3 space-y-2">
      <div className="flex items-center gap-2 flex-wrap text-[12px] font-black text-[#0F172A]">
        {swap.requester_name || `User #${swap.requester_id}`}
        <ArrowRight size={12} className="text-slate-400" aria-label="swaps with" />
        {swap.counterparty_name || `User #${swap.counterparty_id}`}
        <Badge variant="warning" className="text-[8px] uppercase">awaiting approval</Badge>
      </div>
      {swap.reason && <p className="text-[10px] text-slate-500 italic">"{swap.reason}"</p>}
      <ul className="text-[11px] text-slate-700 space-y-1" aria-label="Exchanged shifts">
        {swap.cells.map((c, i) => (
          <li key={i}>
            <span className="font-bold">
              {c.user_id === swap.requester_id ? swap.requester_name : swap.counterparty_name}
            </span>
            {` · ${fmtDate(c.work_date)}: `}
            <span className="text-slate-500">{cellText(c.before)}</span>
            {' → '}
            <span className="font-bold">{cellText(c.after)}</span>
          </li>
        ))}
      </ul>
      {checkErr ? (
        <p role="alert" className="text-[10px] text-red-700">{checkErr}</p>
      ) : warns === null ? (
        <p className="text-[10px] text-slate-400">Checking scheduling rules…</p>
      ) : warns.length > 0 ? (
        <div role="alert" className="text-[10px] text-amber-800 bg-amber-50 border border-amber-200 rounded-lg px-2 py-1.5">
          <p className="font-black uppercase tracking-widest flex items-center gap-1">
            <AlertTriangle size={11} /> Rule warnings (advisory)
          </p>
          <ul className="list-disc list-inside mt-0.5">
            {warns.map((w, i) => <li key={i}>{w.message}</li>)}
          </ul>
        </div>
      ) : (
        <p className="text-[10px] text-emerald-700">No rule warnings.</p>
      )}
      <div className="flex items-end gap-2 flex-wrap">
        <NoteField id={`swap-note-${swap.id}`} value={note} onChange={setNote} />
        <Button size="sm" className="h-10" isLoading={busy}
          aria-label={`Approve swap between ${swap.requester_name} and ${swap.counterparty_name}`}
          onClick={() => onDecide(swap, 'approve', note)}>
          Approve
        </Button>
        <Button size="sm" variant="outline" className="h-10" disabled={busy}
          aria-label={`Reject swap between ${swap.requester_name} and ${swap.counterparty_name}`}
          onClick={() => onDecide(swap, 'reject', note)}>
          Reject
        </Button>
      </div>
    </li>
  );
};

const DropCard = ({
  drop, busy, onDecide,
}: {
  drop: SchedDrop;
  busy: boolean;
  onDecide: (d: SchedDrop, action: 'approve' | 'reject', note: string, post: boolean) => void;
}) => {
  const [note, setNote] = useState('');
  const [post, setPost] = useState(true);
  return (
    <li className="border border-slate-100 rounded-xl p-3 space-y-2">
      <div className="flex items-center gap-2 flex-wrap text-[12px] font-black text-[#0F172A]">
        {drop.user_name || `User #${drop.user_id}`} wants to give away{' '}
        {fmtDate(drop.work_date)} · {drop.shift_name || 'shift'}
        {drop.shift_start && (
          <span className="text-[10px] font-bold text-slate-500 tabular-nums">
            {drop.shift_start.slice(0, 5)}–{(drop.shift_end || '').slice(0, 5)}
          </span>
        )}
      </div>
      <p className="text-[10px] text-slate-500 italic">"{drop.reason}"</p>
      <label className="flex items-center gap-2 text-[11px] font-bold text-slate-700">
        <input type="checkbox" checked={post} onChange={(e) => setPost(e.target.checked)} />
        Post as open shift when approved
      </label>
      <div className="flex items-end gap-2 flex-wrap">
        <NoteField id={`drop-note-${drop.id}`} value={note} onChange={setNote} />
        <Button size="sm" className="h-10" isLoading={busy}
          aria-label={`Approve give-away by ${drop.user_name}`}
          onClick={() => onDecide(drop, 'approve', note, post)}>
          Approve
        </Button>
        <Button size="sm" variant="outline" className="h-10" disabled={busy}
          aria-label={`Reject give-away by ${drop.user_name}`}
          onClick={() => onDecide(drop, 'reject', note, post)}>
          Reject
        </Button>
      </div>
    </li>
  );
};

interface Props {
  swaps: ApproverSwap[];
  drops: SchedDrop[];
  shifts: SchedOpenShift[];
  loading: boolean;
  /** reload the queues */
  reload: () => void | Promise<void>;
  /** roster changed (swap/drop/claim approved): refresh planner grid too */
  onRosterChanged: () => void;
  onNewOpenShift: () => void;
}

export const RequestsView: React.FC<Props> = ({
  swaps, drops, shifts, loading, reload, onRosterChanged, onNewOpenShift,
}) => {
  const [busy, setBusy] = useState<Set<string>>(new Set());
  const mark = (k: string, on: boolean) =>
    setBusy((b) => { const n = new Set(b); on ? n.add(k) : n.delete(k); return n; });

  const decideSwap = async (s: ApproverSwap, action: 'approve' | 'reject', note: string) => {
    const k = `swap-${s.id}`;
    mark(k, true);
    try {
      const r = await schedulerApi.decideSwap(s.id, action, note.trim() || null);
      toast.success(action === 'approve' ? 'Swap approved — rosters updated' : 'Swap rejected');
      (r.warnings || []).forEach((w) => toast.warning(w.message));
      onRosterChanged();
    } catch (e: any) {
      toast.error(errMsg(e, `Failed to ${action} swap`));
    } finally {
      mark(k, false);
      await reload();
    }
  };

  const decideDrop = async (
    d: SchedDrop, action: 'approve' | 'reject', note: string, post: boolean
  ) => {
    const k = `drop-${d.id}`;
    mark(k, true);
    try {
      const r = await schedulerApi.decideDrop(
        d.id, action, note.trim() || null, action === 'approve' ? post : null);
      toast.success(
        action === 'reject' ? 'Give-away rejected'
          : r.open_shift_id ? 'Give-away approved — open shift posted'
          : 'Give-away approved');
      if (r.open_shift_skipped_reason) toast.warning(r.open_shift_skipped_reason);
      if (action === 'approve') onRosterChanged();
    } catch (e: any) {
      toast.error(errMsg(e, `Failed to ${action} give-away`));
    } finally {
      mark(k, false);
      await reload();
    }
  };

  const empty = (t: string) => (
    <p className="text-[10px] font-black uppercase tracking-widest text-slate-400 py-5 text-center">{t}</p>
  );

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-end">
        <Button size="sm" variant="outline" onClick={() => reload()} className="gap-1.5" aria-label="Refresh requests">
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} /> Refresh
        </Button>
      </div>
      <Card className="p-5 border-slate-200 bg-white" aria-label="Swap approvals">
        <p className="text-[10px] font-black uppercase tracking-widest text-[#0F172A] mb-3">
          Swap approvals <Badge variant="neutral" className="ml-2">{swaps.length}</Badge>
        </p>
        {swaps.length === 0 ? empty('No swaps awaiting approval') : (
          <ul className="space-y-2">
            {swaps.map((s) => (
              <SwapCard key={s.id} swap={s} busy={busy.has(`swap-${s.id}`)} onDecide={decideSwap} />
            ))}
          </ul>
        )}
      </Card>
      <Card className="p-5 border-slate-200 bg-white" aria-label="Give-away approvals">
        <p className="text-[10px] font-black uppercase tracking-widest text-[#0F172A] mb-3">
          Give-away approvals <Badge variant="neutral" className="ml-2">{drops.length}</Badge>
        </p>
        {drops.length === 0 ? empty('No give-aways awaiting approval') : (
          <ul className="space-y-2">
            {drops.map((d) => (
              <DropCard key={d.id} drop={d} busy={busy.has(`drop-${d.id}`)} onDecide={decideDrop} />
            ))}
          </ul>
        )}
      </Card>
      <OpenShiftsSchedulerPanel
        shifts={shifts}
        onNew={onNewOpenShift}
        onChanged={async () => { onRosterChanged(); await reload(); }}
      />
    </div>
  );
};
