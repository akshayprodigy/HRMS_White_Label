import React, { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Clock } from 'lucide-react';
import { Button } from '../ui-elements';
import {
  Dialog, DialogContent, DialogTitle, DialogDescription, DialogFooter,
} from '../ui/dialog';
import { client } from '../../api/client';
import { ENDPOINTS } from '../../api/endpoints';
import { errMsg } from '../schedule-delegations-utils';
import { inputCls, labelCls } from './my-schedule-api';
import { useRestoreFocus } from './use-restore-focus';

const MINUTES = [5, 10, 15, 30, 45, 60, 90, 120];

interface LateState {
  can_post: boolean;
  shift_name?: string;
  notice: { eta_hhmm: string; reason: string | null } | null;
}

/** "Running late" strip for the shift that is relevant right now (today's, or
 * an overnight shift from yesterday still running) while not yet punched in. */
export const RunningLateCard: React.FC<{ inline?: boolean }> = ({ inline = false }) => {
  const restoreFocus = useRestoreFocus();
  const [state, setState] = useState<LateState | null>(null);
  const [open, setOpen] = useState(false);
  const [minutes, setMinutes] = useState(15);
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const r = await client.get<LateState>(ENDPOINTS.ROSTER.RUNNING_LATE);
      setState(r.data);
    } catch {
      setState(null);
    }
  }, []);
  useEffect(() => { load(); }, [load]);
  // Re-check when the tab regains focus (e.g. after punching in elsewhere) so
  // the card hides once a punch exists.
  useEffect(() => {
    const onVis = () => { if (document.visibilityState === 'visible') load(); };
    document.addEventListener('visibilitychange', onVis);
    return () => document.removeEventListener('visibilitychange', onVis);
  }, [load]);

  if (!state || (!state.can_post && !state.notice)) return null;

  const send = async () => {
    setBusy(true);
    try {
      await client.post(ENDPOINTS.ROSTER.RUNNING_LATE, {
        minutes_late: minutes,
        reason: reason.trim() || undefined,
      });
      toast.success('Running late notice sent');
      setOpen(false);
      setReason('');
      await load();
    } catch (e: any) {
      toast.error(errMsg(e, 'Failed to send running late notice'));
    } finally {
      setBusy(false);
    }
  };

  const clear = async () => {
    setBusy(true);
    try {
      await client.delete(ENDPOINTS.ROSTER.RUNNING_LATE);
      await load();
    } catch (e: any) {
      toast.error(errMsg(e, 'Failed to clear notice'));
    } finally {
      setBusy(false);
    }
  };

  const formBody = (
    <div className="space-y-3 pt-1">
              <div className="space-y-1">
                <label htmlFor="rl-min" className={labelCls}>I'll be late by</label>
                <select id="rl-min" className={inputCls} value={minutes}
                  onChange={(e) => setMinutes(Number(e.target.value))}>
                  {MINUTES.map((m) => (
                    <option key={m} value={m}>{m} minutes</option>
                  ))}
                </select>
              </div>
              <div className="space-y-1">
                <label htmlFor="rl-reason" className={labelCls}>Reason (optional)</label>
                <input id="rl-reason" className={inputCls} maxLength={255}
                  placeholder="e.g. Stuck in traffic"
                  value={reason} onChange={(e) => setReason(e.target.value)} />
              </div>
            </div>
  );

  return (
    <div className="flex items-center justify-between gap-3 flex-wrap border border-amber-200 bg-amber-50 rounded-xl px-4 py-3">
      <div className="flex items-center gap-2 min-w-0">
        <Clock size={15} className="text-amber-600 shrink-0" />
        {state.notice ? (
          <p className="text-[11px] font-bold text-[#0F172A]">
            Running late notice sent · ETA {state.notice.eta_hhmm} UTC
            {state.notice.reason ? (
              <span className="font-medium text-slate-600"> · {state.notice.reason}</span>
            ) : null}
          </p>
        ) : (
          <p className="text-[11px] font-bold text-[#0F172A]">
            Not at work yet? Let your manager know you are running late.
          </p>
        )}
      </div>
      <div className="flex items-center gap-2">
        {state.notice && (
          <Button variant="outline" size="sm" onClick={clear} disabled={busy}>Clear</Button>
        )}
        {state.can_post && (
          <Button size="sm" onClick={() => setOpen(true)} disabled={busy}>
            {state.notice ? 'Update' : 'Running late'}
          </Button>
        )}
      </div>

      {open && inline && (
        <div className="w-full space-y-3 pt-1">
          {formBody}
          <div className="flex justify-end gap-2">
            <Button variant="outline" size="sm" onClick={() => setOpen(false)} disabled={busy}>Cancel</Button>
            <Button size="sm" onClick={send} isLoading={busy}>Send notice</Button>
          </div>
        </div>
      )}
      {open && !inline && (
        <Dialog open onOpenChange={(o: boolean) => !o && !busy && setOpen(false)}>
          <DialogContent className="max-w-sm" onCloseAutoFocus={restoreFocus}>
            <DialogTitle className="flex items-center gap-2 text-base font-black uppercase tracking-tight text-[#0F172A]">
              <Clock size={15} className="text-amber-600" /> Running late
            </DialogTitle>
            <DialogDescription className="text-[10px] font-bold text-slate-500 -mt-1">
              Your {state.shift_name || 'shift'} schedulers will be notified. No-show alerts
              are held until your ETA plus the grace threshold.
            </DialogDescription>
            {formBody}
            <DialogFooter>
              <Button variant="outline" onClick={() => setOpen(false)} disabled={busy}>Cancel</Button>
              <Button onClick={send} isLoading={busy}>Send notice</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
    </div>
  );
};
