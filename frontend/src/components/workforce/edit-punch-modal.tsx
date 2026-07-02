import React, { useState } from 'react';
import { toast } from 'sonner';
import { Pencil, CalendarPlus } from 'lucide-react';
import { Button } from '../ui-elements';
import { Dialog, DialogContent, DialogTitle, DialogFooter } from '../ui/dialog';
import { client } from '../../api/client';
import { ENDPOINTS } from '../../api/endpoints';
import type { AttendanceLog } from './workforce-data';

// Section Q: HR/admin direct punch edits. Times are wall-clock strings
// ("YYYY-MM-DDTHH:MM") sent as-is — the backend stores them verbatim,
// matching how every other screen renders punch times.

const errDetail = (e: any, fallback: string) =>
  e?.response?.data?.detail ||
  e?.response?.data?.error?.message ||
  fallback;

const toLocalInput = (iso?: string | null): string =>
  iso ? iso.slice(0, 16) : '';

const Field: React.FC<{ label: string; children: React.ReactNode }> = ({
  label,
  children,
}) => (
  <div className="space-y-1">
    <label className="text-[9px] font-black uppercase tracking-widest text-slate-400">
      {label}
    </label>
    {children}
  </div>
);

const inputCls =
  'w-full h-10 px-3 rounded-lg border border-slate-200 text-sm text-[#0F172A] ' +
  'focus:outline-none focus:ring-2 focus:ring-blue-600/30 focus:border-blue-500 bg-white';

export const EditPunchModal: React.FC<{
  log: AttendanceLog;
  onClose: () => void;
  onSaved: () => void;
}> = ({ log, onClose, onSaved }) => {
  const [punchIn, setPunchIn] = useState(toLocalInput(log.captured_at));
  const [punchOut, setPunchOut] = useState(toLocalInput(log.punch_out_time));
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);

  const save = async () => {
    if (reason.trim().length < 5) {
      toast.error('Please give a reason (at least 5 characters).');
      return;
    }
    setBusy(true);
    try {
      await client.patch(ENDPOINTS.HR.ATTENDANCE_EDIT(log.id), {
        punch_in_time: punchIn || null,
        punch_out_time: punchOut || null,
        reason: reason.trim(),
      });
      toast.success('Punch times updated');
      onSaved();
      onClose();
    } catch (e: any) {
      toast.error(errDetail(e, 'Failed to update punch times'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-md">
        <DialogTitle className="flex items-center gap-2 text-base font-black uppercase tracking-tight text-[#0F172A]">
          <Pencil size={15} className="text-blue-600" /> Edit Punch Times
        </DialogTitle>
        <p className="text-[10px] font-bold text-slate-500 -mt-1">
          {log.user_name || `User #${log.user_id}`} · changes are audit-logged
        </p>
        <div className="space-y-3 pt-1">
          <Field label="Punch In">
            <input
              type="datetime-local"
              className={inputCls}
              value={punchIn}
              onChange={(e) => setPunchIn(e.target.value)}
            />
          </Field>
          <Field label="Punch Out (leave empty for open)">
            <input
              type="datetime-local"
              className={inputCls}
              value={punchOut}
              onChange={(e) => setPunchOut(e.target.value)}
            />
          </Field>
          <Field label="Reason (required)">
            <textarea
              className={inputCls + ' h-20 py-2 resize-none'}
              placeholder="e.g. Employee forgot to punch out — confirmed with manager"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
          </Field>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button onClick={save} isLoading={busy}>
            Save Changes
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export const AddMissedPunchModal: React.FC<{
  userId: number;
  userName: string;
  onClose: () => void;
  onSaved: () => void;
}> = ({ userId, userName, onClose, onSaved }) => {
  const yesterday = new Date(Date.now() - 86400000).toISOString().slice(0, 10);
  const [workDate, setWorkDate] = useState(yesterday);
  const [punchIn, setPunchIn] = useState('09:30');
  const [punchOut, setPunchOut] = useState('18:00');
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);

  const save = async () => {
    if (reason.trim().length < 5) {
      toast.error('Please give a reason (at least 5 characters).');
      return;
    }
    if (!workDate || !punchIn) {
      toast.error('Date and punch-in time are required.');
      return;
    }
    setBusy(true);
    try {
      await client.post(ENDPOINTS.HR.ATTENDANCE_MANUAL, {
        user_id: userId,
        work_date: workDate,
        punch_in_time: `${workDate}T${punchIn}`,
        punch_out_time: punchOut ? `${workDate}T${punchOut}` : null,
        reason: reason.trim(),
      });
      toast.success('Attendance record created');
      onSaved();
      onClose();
    } catch (e: any) {
      toast.error(errDetail(e, 'Failed to create attendance record'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-md">
        <DialogTitle className="flex items-center gap-2 text-base font-black uppercase tracking-tight text-[#0F172A]">
          <CalendarPlus size={15} className="text-blue-600" /> Add Missed Punch
        </DialogTitle>
        <p className="text-[10px] font-bold text-slate-500 -mt-1">
          {userName} · creates a manual attendance record (audit-logged)
        </p>
        <div className="space-y-3 pt-1">
          <Field label="Work Date">
            <input
              type="date"
              className={inputCls}
              value={workDate}
              onChange={(e) => setWorkDate(e.target.value)}
            />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Punch In">
              <input
                type="time"
                className={inputCls}
                value={punchIn}
                onChange={(e) => setPunchIn(e.target.value)}
              />
            </Field>
            <Field label="Punch Out (optional)">
              <input
                type="time"
                className={inputCls}
                value={punchOut}
                onChange={(e) => setPunchOut(e.target.value)}
              />
            </Field>
          </div>
          <Field label="Reason (required)">
            <textarea
              className={inputCls + ' h-20 py-2 resize-none'}
              placeholder="e.g. Employee was on site and forgot to punch in"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
          </Field>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button onClick={save} isLoading={busy}>
            Create Record
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
