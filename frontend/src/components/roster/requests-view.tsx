import React, { useState } from 'react';
import { toast } from 'sonner';
import { AlertTriangle, ArrowRight, RefreshCw, X } from 'lucide-react';
import { Card, Button, Badge } from '../ui-elements';
import { errMsg } from '../schedule-delegations-utils';
import { fmtDate, inputCls, labelCls } from '../my-schedule/my-schedule-api';
import {
  schedulerApi,
  type ApproverSwap,
  type CoverageGap,
  type SchedDrop,
  type SchedOpenShift,
} from './roster-api';
import { OpenShiftsSchedulerPanel } from './open-shifts-panel';
import { CoverageGapsPanel } from './coverage-gaps-panel';
import type { QueueKey } from './use-requests';

/** warnings are computed server-side for at most this many swaps */
const WARNING_LIMIT = 50;

const person = (name: string | null | undefined, id: number) => name || `User #${id}`;
const cellText = (c: { shift_name: string | null; is_week_off: boolean }) =>
  c.is_week_off ? 'Week off' : c.shift_name || '—';

type Pending = Map<string, 'approve' | 'reject'>;

const NoteField = ({
  id, value, onChange,
}: { id: string; value: string; onChange: (v: string) => void }) => (
  <div className="space-y-1 flex-1 min-w-[200px]">
    <label htmlFor={id} className={labelCls}>Note (optional)</label>
    <input id={id} className={inputCls} maxLength={500} value={value}
      onChange={(e) => onChange(e.target.value)} placeholder="Shown to the employees" />
  </div>
);

const DecideButtons = ({
  pending, onApprove, onReject, approveLabel, rejectLabel,
}: {
  pending?: 'approve' | 'reject';
  onApprove: () => void;
  onReject: () => void;
  approveLabel: string;
  rejectLabel: string;
}) => (
  <>
    <Button size="sm" className="h-10" isLoading={pending === 'approve'} disabled={!!pending}
      aria-label={approveLabel} onClick={onApprove}>
      Approve
    </Button>
    <Button size="sm" variant="outline" className="h-10" isLoading={pending === 'reject'} disabled={!!pending}
      aria-label={rejectLabel} onClick={onReject}>
      Reject
    </Button>
  </>
);

const SwapCard = ({
  swap, index, pending, onDecide,
}: {
  swap: ApproverSwap;
  index: number;
  pending?: 'approve' | 'reject';
  onDecide: (s: ApproverSwap, action: 'approve' | 'reject', note: string) => void;
}) => {
  const [note, setNote] = useState('');
  const a = person(swap.requester_name, swap.requester_id);
  const b = person(swap.counterparty_name, swap.counterparty_id);
  const warns = swap.warnings || [];
  return (
    <li className="border border-slate-100 rounded-xl p-3 space-y-2">
      <div className="flex items-center gap-2 flex-wrap text-[12px] font-black text-[#0F172A]">
        {a}
        <ArrowRight size={12} className="text-slate-400" aria-label="swaps with" />
        {b}
        <Badge variant="warning" className="text-[8px] uppercase">awaiting approval</Badge>
      </div>
      {swap.reason && <p className="text-[10px] text-slate-500 italic">"{swap.reason}"</p>}
      <ul className="text-[11px] text-slate-700 space-y-1" aria-label="Exchanged shifts">
        {swap.cells.map((c, i) => (
          <li key={i}>
            <span className="font-bold">{c.user_id === swap.requester_id ? a : b}</span>
            {` · ${fmtDate(c.work_date)}: `}
            <span className="text-slate-500">{cellText(c.before)}</span>
            {' → '}
            <span className="font-bold">{cellText(c.after)}</span>
          </li>
        ))}
      </ul>
      {index >= WARNING_LIMIT ? (
        <p className="text-[10px] text-slate-400">Rule check not run for this swap (queue is long).</p>
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
        <DecideButtons pending={pending}
          approveLabel={`Approve swap between ${a} and ${b}`}
          rejectLabel={`Reject swap between ${a} and ${b}`}
          onApprove={() => onDecide(swap, 'approve', note)}
          onReject={() => onDecide(swap, 'reject', note)} />
      </div>
    </li>
  );
};

const DropCard = ({
  drop, pending, onDecide,
}: {
  drop: SchedDrop;
  pending?: 'approve' | 'reject';
  onDecide: (d: SchedDrop, action: 'approve' | 'reject', note: string, post: boolean) => void;
}) => {
  const [note, setNote] = useState('');
  const [post, setPost] = useState(true);
  const who = person(drop.user_name, drop.user_id);
  return (
    <li className="border border-slate-100 rounded-xl p-3 space-y-2">
      <div className="flex items-center gap-2 flex-wrap text-[12px] font-black text-[#0F172A]">
        {who} wants to give away {fmtDate(drop.work_date)} · {drop.shift_name || 'shift'}
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
        <DecideButtons pending={pending}
          approveLabel={`Approve give-away by ${who}`}
          rejectLabel={`Reject give-away by ${who}`}
          onApprove={() => onDecide(drop, 'approve', note, post)}
          onReject={() => onDecide(drop, 'reject', note, post)} />
      </div>
    </li>
  );
};

const QueueError = ({ msg, onRetry }: { msg?: string; onRetry: () => void }) =>
  msg ? (
    <div role="alert" className="text-[11px] text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2 mb-3 flex items-center gap-3">
      <span className="flex-1">Couldn't load: {msg}</span>
      <Button size="sm" variant="outline" onClick={onRetry}>Retry</Button>
    </div>
  ) : null;

interface Props {
  swaps: ApproverSwap[];
  drops: SchedDrop[];
  shifts: SchedOpenShift[];
  gaps: CoverageGap[];
  loading: boolean;
  errors: Partial<Record<QueueKey, string>>;
  reload: () => void | Promise<void>;
  /** roster changed (swap/drop/claim approved): refresh planner grid too */
  onRosterChanged: () => void;
  onNewOpenShift: () => void;
  canPostOpenShift?: boolean;
}

interface Result { title: string; lines: string[]; warn: boolean }

export const RequestsView: React.FC<Props> = ({
  swaps, drops, shifts, gaps, loading, errors, reload, onRosterChanged, onNewOpenShift, canPostOpenShift,
}) => {
  const [pending, setPending] = useState<Pending>(new Map());
  // outcome of the latest decision (warnings / skipped reasons stay visible)
  const [result, setResult] = useState<Result | null>(null);
  const mark = (k: string, a?: 'approve' | 'reject') =>
    setPending((p) => { const n = new Map(p); a ? n.set(k, a) : n.delete(k); return n; });

  const decideSwap = async (s: ApproverSwap, action: 'approve' | 'reject', note: string) => {
    const k = `swap-${s.id}`;
    mark(k, action);
    try {
      const r = await schedulerApi.decideSwap(s.id, action, note.trim() || null);
      const t = action === 'approve' ? 'Swap approved — rosters updated' : 'Swap rejected';
      toast.success(t);
      const w = (r.warnings || []).map((x) => x.message);
      setResult({ title: t, lines: w, warn: w.length > 0 });
      onRosterChanged();
    } catch (e: any) {
      toast.error(errMsg(e, `Failed to ${action} swap`));
    } finally {
      mark(k);
      await reload();
    }
  };

  const decideDrop = async (
    d: SchedDrop, action: 'approve' | 'reject', note: string, post: boolean
  ) => {
    const k = `drop-${d.id}`;
    mark(k, action);
    try {
      // untouched default = null so the server may skip posting (with a reason)
      // instead of failing; an explicit "don't post" is false.
      const r = await schedulerApi.decideDrop(
        d.id, action, note.trim() || null, action === 'approve' && !post ? false : null);
      const t = action === 'reject' ? 'Give-away rejected'
        : r.open_shift_id ? 'Give-away approved — open shift posted'
        : 'Give-away approved';
      toast.success(t);
      if (r.open_shift_skipped_reason) toast.warning(r.open_shift_skipped_reason);
      setResult({
        title: t,
        lines: r.open_shift_skipped_reason ? [r.open_shift_skipped_reason] : [],
        warn: !!r.open_shift_skipped_reason,
      });
      if (action === 'approve') onRosterChanged();
    } catch (e: any) {
      toast.error(errMsg(e, `Failed to ${action} give-away`));
    } finally {
      mark(k);
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
      {result && (
        <div role="status" className={
          'rounded-xl border px-4 py-3 text-[11px] flex items-start gap-3 ' +
          (result.warn ? 'bg-amber-50 border-amber-200 text-amber-900' : 'bg-emerald-50 border-emerald-200 text-emerald-800')}>
          <div className="flex-1">
            <p className="font-black">{result.title}</p>
            {result.lines.length > 0 && (
              <ul className="list-disc list-inside mt-0.5">
                {result.lines.map((l, i) => <li key={i}>{l}</li>)}
              </ul>
            )}
          </div>
          <button type="button" onClick={() => setResult(null)} aria-label="Dismiss result" className="opacity-60 hover:opacity-100">
            <X size={14} />
          </button>
        </div>
      )}
      <CoverageGapsPanel
        gaps={gaps}
        canPublish={canPostOpenShift}
        error={errors.gaps}
        onRetry={() => reload()}
        onResult={(title, lines) => setResult({ title, lines, warn: lines.length > 0 })}
        onChanged={async () => { onRosterChanged(); await reload(); }}
      />
      <Card className="p-5 border-slate-200 bg-white" aria-label="Swap approvals">
        <p className="text-[10px] font-black uppercase tracking-widest text-[#0F172A] mb-3">
          Swap approvals <Badge variant="neutral" className="ml-2">{swaps.length}</Badge>
        </p>
        <QueueError msg={errors.swaps} onRetry={() => reload()} />
        {swaps.length === 0 ? (!errors.swaps && empty('No swaps awaiting approval')) : (
          <ul className="space-y-2">
            {swaps.map((s, i) => (
              <SwapCard key={s.id} swap={s} index={i} pending={pending.get(`swap-${s.id}`)} onDecide={decideSwap} />
            ))}
          </ul>
        )}
      </Card>
      <Card className="p-5 border-slate-200 bg-white" aria-label="Give-away approvals">
        <p className="text-[10px] font-black uppercase tracking-widest text-[#0F172A] mb-3">
          Give-away approvals <Badge variant="neutral" className="ml-2">{drops.length}</Badge>
        </p>
        <QueueError msg={errors.drops} onRetry={() => reload()} />
        {drops.length === 0 ? (!errors.drops && empty('No give-aways awaiting approval')) : (
          <ul className="space-y-2">
            {drops.map((d) => (
              <DropCard key={d.id} drop={d} pending={pending.get(`drop-${d.id}`)} onDecide={decideDrop} />
            ))}
          </ul>
        )}
      </Card>
      <OpenShiftsSchedulerPanel
        shifts={shifts}
        error={errors.shifts}
        onRetry={() => reload()}
        onNew={onNewOpenShift}
        canPost={canPostOpenShift}
        onResult={(title, lines) => setResult({ title, lines, warn: lines.length > 0 })}
        onChanged={async () => { onRosterChanged(); await reload(); }}
      />
    </div>
  );
};
