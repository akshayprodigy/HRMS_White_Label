import React, { useState } from 'react';
import { toast } from 'sonner';
import { Pencil, CalendarPlus } from 'lucide-react';
import { Button } from '../ui-elements';
import { Dialog, DialogContent, DialogTitle, DialogFooter } from '../ui/dialog';
import { client } from '../../api/client';
import { ENDPOINTS } from '../../api/endpoints';
import type { AttendanceLog } from './workforce-data';
import { orgToday, toOrgInput, useOrgTime } from '../../lib/org-time';

// Section Q: HR/admin direct punch edits. Times are org-local wall-clock
// strings ("YYYY-MM-DDTHH:MM") sent as-is — the backend reads naive input as
// org-local and stores UTC.

const errDetail = (e: any, fallback: string) =>
  e?.response?.data?.detail ||
  e?.response?.data?.error?.message ||
  fallback;

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
  const { ready } = useOrgTime();
  // Pre-fill only once org time is known; before that the zone is a UTC
  // placeholder and the backend would read the edited value as org-local.
  const origIn = ready ? toOrgInput(log.captured_at) : '';
  const origOut = ready ? toOrgInput(log.punch_out_time) : '';
  const [edits, setEdits] = useState<{ in?: string; out?: string }>({});
  const punchIn = edits.in ?? origIn;
  const punchOut = edits.out ?? origOut;
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);

  const save = async () => {
    if (reason.trim().length < 5) {
      toast.error('Please give a reason (at least 5 characters).');
      return;
    }
    // Send only changed fields (the backend leaves an omitted/null one as is).
    const body: Record<string, string> = { reason: reason.trim() };
    if (punchIn && punchIn !== origIn) body.punch_in_time = punchIn;
    if (punchOut && punchOut !== origOut) body.punch_out_time = punchOut;
    if (!body.punch_in_time && !body.punch_out_time) {
      toast.error('Change a punch time first.');
      return;
    }
    setBusy(true);
    try {
      await client.patch(ENDPOINTS.HR.ATTENDANCE_EDIT(log.id), body);
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
        {!ready && <p className="text-[10px] font-bold text-slate-500">Loading org time…</p>}
        <div className="space-y-3 pt-1">
          <Field label="Punch In">
            <input
              type="datetime-local"
              className={inputCls}
              value={punchIn}
              onChange={(e) => setEdits((s) => ({ ...s, in: e.target.value }))}
            />
          </Field>
          <Field label="Punch Out (leave empty for open)">
            <input
              type="datetime-local"
              className={inputCls}
              value={punchOut}
              onChange={(e) => setEdits((s) => ({ ...s, out: e.target.value }))}
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
          <Button onClick={save} isLoading={busy} disabled={!ready}>
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
  const yesterday = new Date(Date.parse(`${orgToday()}T00:00:00Z`) - 86400000).toISOString().slice(0, 10);
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
