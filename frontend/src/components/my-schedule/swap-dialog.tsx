import React, { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { ArrowLeftRight } from 'lucide-react';
import { Button } from '../ui-elements';
import {
  Dialog, DialogContent, DialogTitle, DialogDescription, DialogFooter,
} from '../ui/dialog';
import { errMsg, todayIso } from '../schedule-delegations-utils';
import {
  SwapCandidate, fmtDate, inputCls, labelCls, mySchedule,
} from './my-schedule-api';

const addDays = (iso: string, n: number) => {
  const d = new Date(iso + 'T00:00:00Z');
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
};

const candShift = (c?: SwapCandidate) =>
  !c ? '—' : c.is_week_off ? 'Week off' : c.shift_name || 'No shift';

interface Props {
  date: string; // the day of my shift I want to hand over
  shiftName?: string;
  onClose: () => void;
  onDone: () => void;
}

export const SwapDialog: React.FC<Props> = ({ date, shiftName, onClose, onDone }) => {
  const [cands, setCands] = useState<SwapCandidate[]>([]);
  const [returnCands, setReturnCands] = useState<SwapCandidate[]>([]);
  const [loading, setLoading] = useState(true);
  const [pick, setPick] = useState<number | ''>('');
  const [otherDay, setOtherDay] = useState(false);
  const [returnDate, setReturnDate] = useState('');
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let live = true;
    setLoading(true);
    mySchedule.swapCandidates(date)
      .then((c) => live && setCands(c))
      .catch((e) => toast.error(errMsg(e, 'Failed to load colleagues')))
      .finally(() => live && setLoading(false));
    return () => { live = false; };
  }, [date]);

  const maxDate = addDays(todayIso(), 90);
  const rd = otherDay && returnDate && returnDate !== date
    && returnDate >= todayIso() && returnDate <= maxDate ? returnDate : '';
  useEffect(() => {
    if (!rd) { setReturnCands([]); return; }
    let live = true;
    mySchedule.swapCandidates(rd)
      .then((c) => live && setReturnCands(c))
      .catch((e) => { if (live) { setReturnCands([]); toast.error(errMsg(e, 'Failed to load that date')); } });
    return () => { live = false; };
  }, [rd]);

  const chosen = cands.find((c) => c.user_id === pick);

  const submit = async () => {
    if (!pick) { toast.error('Pick a colleague to swap with.'); return; }
    if (otherDay && !rd) {
      toast.error(`Pick a return date between today and ${fmtDate(maxDate)} that differs from ${fmtDate(date)}, or untick the option.`);
      return;
    }
    setBusy(true);
    try {
      await mySchedule.createSwap({
        counterparty_id: pick,
        requester_date: date,
        counterparty_date: rd || null,
        reason: reason.trim() || null,
      });
      toast.success('Swap requested — your colleague has been notified');
      onDone();
    } catch (e: any) {
      toast.error(errMsg(e, 'Failed to request swap'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open onOpenChange={(o: boolean) => !o && !busy && onClose()}>
      <DialogContent className="max-w-lg">
        <DialogTitle className="flex items-center gap-2 text-base font-black uppercase tracking-tight text-[#0F172A]">
          <ArrowLeftRight size={15} className="text-indigo-600" /> Swap shift
        </DialogTitle>
        <DialogDescription className="text-[10px] font-bold text-slate-500 -mt-1">
          Your {shiftName || 'shift'} on {fmtDate(date)} · colleague must accept, then your approver confirms
        </DialogDescription>
        <div className="space-y-3 pt-1">
          <div className="space-y-1">
            <label htmlFor="sw-with" className={labelCls}>Swap with (your department)</label>
            <select id="sw-with" className={inputCls} value={pick} disabled={loading}
              onChange={(e) => setPick(e.target.value ? Number(e.target.value) : '')}>
              <option value="">{loading ? 'Loading…' : 'Select a colleague…'}</option>
              {cands.map((c) => (
                <option key={c.user_id} value={c.user_id}>
                  {c.name} — {candShift(c)} on {fmtDate(date)}
                </option>
              ))}
            </select>
            {!loading && cands.length === 0 && (
              <p className="text-[10px] text-slate-500">No colleagues found in your department.</p>
            )}
          </div>
          <label className="flex items-center gap-2 text-[11px] font-bold text-slate-700">
            <input type="checkbox" checked={otherDay}
              onChange={(e) => setOtherDay(e.target.checked)} />
            Take their shift on a different day in return
          </label>
          {otherDay && (
            <div className="space-y-1">
              <label htmlFor="sw-ret" className={labelCls}>Return date</label>
              <input id="sw-ret" type="date" className={inputCls} min={todayIso()} max={maxDate}
                value={returnDate} onChange={(e) => setReturnDate(e.target.value)} />
              {rd && chosen && (
                <p className="text-[10px] text-slate-600">
                  {chosen.name} works{' '}
                  <b>{candShift(returnCands.find((c) => c.user_id === chosen.user_id))}</b>{' '}
                  on {fmtDate(rd)}.
                </p>
              )}
            </div>
          )}
          <div className="space-y-1">
            <label htmlFor="sw-reason" className={labelCls}>Reason (optional)</label>
            <textarea id="sw-reason" className={inputCls + ' h-20 py-2 resize-none'} maxLength={500}
              placeholder="e.g. Family event that evening"
              value={reason} onChange={(e) => setReason(e.target.value)} />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={busy}>Cancel</Button>
          <Button onClick={submit} isLoading={busy}>Request swap</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
