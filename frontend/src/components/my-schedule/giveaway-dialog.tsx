import React, { useState } from 'react';
import { toast } from 'sonner';
import { Hand } from 'lucide-react';
import { Button } from '../ui-elements';
import {
  Dialog, DialogContent, DialogTitle, DialogDescription, DialogFooter,
} from '../ui/dialog';
import { errMsg } from '../schedule-delegations-utils';
import { fmtDate, inputCls, labelCls, mySchedule } from './my-schedule-api';

interface Props {
  date: string;
  shiftName?: string;
  onClose: () => void;
  onDone: () => void;
}

export const GiveawayDialog: React.FC<Props> = ({ date, shiftName, onClose, onDone }) => {
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    if (reason.trim().length < 3) {
      toast.error('Please give a reason (at least 3 characters).');
      return;
    }
    setBusy(true);
    try {
      await mySchedule.createDrop({ work_date: date, reason: reason.trim() });
      toast.success('Give-away requested — sent to your approver');
      onDone();
    } catch (e: any) {
      toast.error(errMsg(e, 'Failed to request give-away'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open onOpenChange={(o: boolean) => !o && !busy && onClose()}>
      <DialogContent className="max-w-md">
        <DialogTitle className="flex items-center gap-2 text-base font-black uppercase tracking-tight text-[#0F172A]">
          <Hand size={15} className="text-indigo-600" /> Give away shift
        </DialogTitle>
        <DialogDescription className="text-[10px] font-bold text-slate-500 -mt-1">
          Your {shiftName || 'shift'} on {fmtDate(date)} · if approved you are released from it
        </DialogDescription>
        <div className="space-y-1 pt-1">
          <label htmlFor="gv-reason" className={labelCls}>Reason (required)</label>
          <textarea id="gv-reason" className={inputCls + ' h-20 py-2 resize-none'} maxLength={500}
            placeholder="e.g. Unwell, cannot work that day"
            value={reason} onChange={(e) => setReason(e.target.value)} />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={busy}>Cancel</Button>
          <Button onClick={submit} isLoading={busy}>Request give-away</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
