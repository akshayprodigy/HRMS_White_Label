import React, { useState } from 'react';
import { toast } from 'sonner';
import { Radio, UserCheck } from 'lucide-react';
import { Card, Button, Badge } from '../ui-elements';
import { errMsg } from '../schedule-delegations-utils';
import { fmtDate, inputCls } from '../my-schedule/my-schedule-api';
import { InlineConfirm } from '../my-schedule/inline-confirm';
import { schedulerApi, addDays, type CoverageGap, type GapSuggestion } from './roster-api';
import { OPEN_SHIFT_HORIZON_DAYS } from './use-requests';
import { todayIso } from '../schedule-delegations-utils';

const SOURCE_LABEL: Record<CoverageGap['source'], string> = {
  emergency_leave: 'Emergency leave',
  no_show: 'No-show',
  drop: 'Give-away',
  sick_call: 'Sick call',
  manual: 'Manual',
};

interface Props {
  gaps: CoverageGap[];
  error?: string;
  onRetry: () => void;
  onChanged: () => void | Promise<void>;
  onResult: (title: string, lines: string[]) => void;
  /** viewer may publish schedules; gates Assign / Broadcast */
  canPublish?: boolean;
}

const GapCard = ({
  gap, onChanged, onResult, canPublish,
}: {
  gap: CoverageGap;
  canPublish: boolean;
  onChanged: () => void | Promise<void>;
  onResult: (title: string, lines: string[]) => void;
}) => {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [sugs, setSugs] = useState<GapSuggestion[] | null>(null);
  const [sugErr, setSugErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [auto, setAuto] = useState(false);
  const [note, setNote] = useState('');

  const loadSuggestions = async () => {
    setLoading(true);
    setSugErr(null);
    try {
      setSugs((await schedulerApi.gapSuggestions(gap.id)).suggestions);
    } catch (e: any) {
      setSugErr(errMsg(e, "Couldn't load suggestions"));
    } finally {
      setLoading(false);
    }
  };
  const toggle = () => {
    const next = !open;
    setOpen(next);
    if (next && sugs === null) loadSuggestions();
  };

  const run = async (key: string, fn: () => Promise<CoverageGap>, done: (g: CoverageGap) => [string, string[]]) => {
    setBusy(key);
    try {
      const g = await fn();
      const [t, lines] = done(g);
      toast.success(t);
      onResult(t, lines);
      await onChanged();
    } catch (e: any) {
      toast.error(errMsg(e, 'Action failed'));
      // a stale gap (someone else acted): refresh the list
      await onChanged();
    } finally {
      setBusy(null);
    }
  };

  const who = gap.absent_name || (gap.absent_user_id ? `User #${gap.absent_user_id}` : null);
  const broadcast = gap.open_shift_id != null && gap.open_shift_status === 'open';
  return (
    <li className="border border-slate-100 rounded-xl p-3 space-y-2" data-testid={`gap-${gap.id}`}>
      <div className="flex items-center gap-2 flex-wrap text-[12px] font-black text-[#0F172A]">
        {fmtDate(gap.work_date)} · {gap.shift_name || 'Shift'}
        {gap.shift_start && (
          <span className="text-[10px] font-bold text-slate-500 tabular-nums">
            {gap.shift_start}–{gap.shift_end}
          </span>
        )}
        <Badge variant="error" className="text-[8px] uppercase">{SOURCE_LABEL[gap.source]}</Badge>
        {broadcast && <Badge variant="info" className="text-[8px] uppercase">broadcast to open shifts</Badge>}
      </div>
      <p className="text-[10px] text-slate-500">
        {who ? `${who} is absent` : 'No absent employee recorded'}
        {[gap.department, gap.location].filter(Boolean).length > 0 &&
          ` · ${[gap.department, gap.location].filter(Boolean).join(' · ')}`}
        {gap.note ? ` · ${gap.note}` : ''}
      </p>
      <div className="flex items-center gap-3 flex-wrap">
        <Button size="sm" variant="outline" className="h-10" onClick={toggle} aria-expanded={open}
          aria-label={`Find replacement for ${fmtDate(gap.work_date)} ${gap.shift_name || 'shift'}`}>
          <UserCheck size={14} className="mr-1.5" /> {open ? 'Hide suggestions' : 'Find replacement'}
        </Button>
        {canPublish && (
          <>
        <Button size="sm" variant="outline" className="h-10" disabled={!!busy || broadcast}
          isLoading={busy === 'broadcast'}
          aria-label={`Broadcast gap ${gap.id} as open shift`}
          onClick={() => run('broadcast', async () => {
            const g = await schedulerApi.broadcastGap(gap.id, auto);
            if (g.work_date > addDays(todayIso(), OPEN_SHIFT_HORIZON_DAYS)) {
              toast.info(`The open shift is on ${fmtDate(g.work_date)}, beyond the ${OPEN_SHIFT_HORIZON_DAYS}-day Open shifts list below. It is live but not listed here yet.`);
            }
            return g;
          },
            () => [auto ? 'Broadcast as open shift — first claim is auto-confirmed' : 'Broadcast as open shift — claims need your approval', []])}>
          <Radio size={14} className="mr-1.5" /> Broadcast
        </Button>
        <label className="flex items-center gap-1.5 text-[10px] font-bold text-slate-600">
          <input type="checkbox" checked={auto} onChange={(e) => setAuto(e.target.checked)} />
          Auto-confirm first claim
        </label>
          </>
        )}
        <input aria-label={`Dismiss note for gap ${gap.id}`} className={inputCls + ' h-10 max-w-xs'}
          maxLength={255} value={note} onChange={(e) => setNote(e.target.value)}
          placeholder="Dismiss note (optional)" />
        <InlineConfirm label="Dismiss" ariaLabel={`Dismiss gap ${gap.id}`} busy={!!busy}
          onConfirm={() => run('dismiss', () => schedulerApi.dismissGap(gap.id, note.trim() || null),
            () => ['Coverage gap dismissed', []])} />
      </div>
      {open && (
        <div className="rounded-lg bg-slate-50 border border-slate-100 p-3 space-y-2" aria-label="Suggested replacements">
          <p className="text-[10px] font-black uppercase tracking-widest text-slate-500">Suggested replacements</p>
          {loading && <p className="text-[11px] text-slate-400">Loading…</p>}
          {sugErr && (
            <div role="alert" className="text-[11px] text-red-700 flex items-center gap-3">
              <span className="flex-1">{sugErr}</span>
              <Button size="sm" variant="outline" onClick={loadSuggestions}>Retry</Button>
            </div>
          )}
          {sugs && sugs.length === 0 && !loading && (
            <p className="text-[11px] text-slate-500">
              No eligible replacement in your scope. Broadcast it as an open shift instead.
            </p>
          )}
          {sugs && sugs.length > 0 && (
            <ol className="space-y-2">
              {sugs.map((s, i) => (
                <li key={s.user_id} className="bg-white border border-slate-100 rounded-lg p-2 flex items-start gap-3">
                  <span className="text-[10px] font-black text-slate-400 w-4 pt-1">{i + 1}</span>
                  <div className="flex-1 min-w-0">
                    <p className="text-[12px] font-black text-[#0F172A]">
                      {s.name}
                      <span className="ml-2 text-[10px] font-bold text-slate-500 tabular-nums">
                        score {s.score}
                      </span>
                    </p>
                    <ul className="text-[10px] text-slate-600 list-disc list-inside">
                      {s.reasons.map((r, j) => <li key={j}>{r}</li>)}
                    </ul>
                  </div>
                  {canPublish && <Button size="sm" className="h-10" disabled={!!busy}
                    isLoading={busy === `assign-${s.user_id}`}
                    aria-label={`Assign ${s.name}`}
                    onClick={() => run(`assign-${s.user_id}`, () => schedulerApi.assignGap(gap.id, s.user_id),
                      (g) => [`${s.name} assigned — schedule published`, g.warnings || []])}>
                    Assign
                  </Button>}
                </li>
              ))}
            </ol>
          )}
        </div>
      )}
    </li>
  );
};

/** Open coverage gaps with ranked replacement suggestions. */
export const CoverageGapsPanel: React.FC<Props> = ({
  gaps, error, onRetry, onChanged, onResult, canPublish = true,
}) => (
  <Card className="p-5 border-slate-200 bg-white" aria-label="Coverage gaps">
    <p className="text-[10px] font-black uppercase tracking-widest text-[#0F172A] mb-3">
      Coverage gaps <Badge variant="neutral" className="ml-2">{gaps.length}</Badge>
    </p>
    {error && (
      <div role="alert" className="text-[11px] text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2 mb-3 flex items-center gap-3">
        <span className="flex-1">Couldn't load: {error}</span>
        <Button size="sm" variant="outline" onClick={onRetry}>Retry</Button>
      </div>
    )}
    {gaps.length === 0 ? (!error && (
      <p className="text-[10px] font-black uppercase tracking-widest text-slate-400 py-5 text-center">
        No open coverage gaps
      </p>
    )) : (
      <ul className="space-y-2">
        {gaps.map((g) => <GapCard key={g.id} gap={g} onChanged={onChanged} onResult={onResult} canPublish={canPublish} />)}
      </ul>
    )}
  </Card>
);
