import React, { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { CheckCircle, XCircle, RefreshCw, Wrench, Send } from 'lucide-react';
import { Card, Button, Badge } from './ui-elements';
import { Dialog, DialogContent, DialogTitle, DialogFooter } from './ui/dialog';
import {
  regularizationApi,
  regularizationErrMsg,
  type Regularization,
  type RegularizationStatus,
} from '../api/regularization';

// Attendance regularization UI: employee request dialog + "my requests" list,
// and the approver list/queue (shared by the Workforce drill-over and the
// Approvals Center).

const inputCls =
  'w-full h-10 px-3 rounded-lg border border-slate-200 text-sm text-[#0F172A] ' +
  'focus:outline-none focus:ring-2 focus:ring-blue-600/30 focus:border-blue-500 bg-white';

const STATUS_TONE: Record<string, 'success' | 'error' | 'warning' | 'neutral'> = {
  approved: 'success',
  rejected: 'error',
  pending: 'warning',
  cancelled: 'neutral',
};

// List endpoints return naive UTC datetimes (no offset); treat them as UTC.
const parseServerDate = (iso: string) =>
  new Date(/(Z|[+-]\d{2}:?\d{2})$/.test(iso) ? iso : `${iso}Z`);

const fmtDateTime = (iso?: string | null) =>
  iso
    ? parseServerDate(iso).toLocaleString([], {
        day: '2-digit',
        month: 'short',
        hour: '2-digit',
        minute: '2-digit',
      })
    : '—';

const pad = (n: number) => String(n).padStart(2, '0');
const localIsoDate = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;

// ---------------------------------------------------------------------------
// Presentational list with Approve / Reject (reject requires a note)
// ---------------------------------------------------------------------------

const RequestRow: React.FC<{
  r: Regularization;
  showRequester: boolean;
  onDecided?: () => void;
  onCancel?: (id: number) => void;
}> = ({ r, showRequester, onDecided, onCancel }) => {
  const [rejecting, setRejecting] = useState(false);
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);

  const decide = async (approve: boolean) => {
    if (!approve && !note.trim()) {
      toast.error('A note is required to reject a request');
      return;
    }
    setBusy(true);
    try {
      await regularizationApi.decide(r.id, approve, note);
      toast.success(approve ? 'Correction approved' : 'Correction rejected');
      setRejecting(false);
      setNote('');
      onDecided?.();
    } catch (e) {
      toast.error(regularizationErrMsg(e, 'Failed to record decision'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="p-3 rounded-xl border border-slate-200 bg-white space-y-2">
      <div className="flex items-center justify-between gap-2">
        <div>
          <p className="text-[11px] font-black text-[#0F172A] tabular-nums">{r.work_date}</p>
          {showRequester && (
            <p className="text-[10px] font-bold text-slate-500">
              {r.requester_name || `User #${r.user_id}`}
              {r.requester_employee_code ? ` · ${r.requester_employee_code}` : ''}
            </p>
          )}
        </div>
        <Badge variant={STATUS_TONE[r.status] || 'neutral'} className="text-[8px] uppercase">
          {r.status}
        </Badge>
      </div>
      <p className="text-[10px] font-bold text-slate-600 tabular-nums">
        In {fmtDateTime(r.requested_punch_in)} · Out {fmtDateTime(r.requested_punch_out)}
      </p>
      {r.reason && <p className="text-[10px] italic text-slate-500">"{r.reason}"</p>}
      {r.decision_note && (
        <p className="text-[10px] font-bold text-slate-500">Decision note: {r.decision_note}</p>
      )}
      {r.status === 'pending' && onCancel && (
        <button
          type="button"
          onClick={() => onCancel(r.id)}
          className="inline-flex items-center gap-1 text-[9px] font-black uppercase tracking-widest text-rose-500 hover:text-rose-700"
        >
          <XCircle size={10} /> Cancel request
        </button>
      )}
      {r.status === 'pending' && onDecided && (
        <div className="space-y-2 pt-1">
          {rejecting && (
            <textarea
              className={inputCls + ' h-16 py-2 resize-none'}
              placeholder="Reason for rejection (required)"
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
          )}
          <div className="flex gap-2">
            {!rejecting && (
              <Button
                onClick={() => decide(true)}
                disabled={busy}
                className="flex-1 h-8 bg-emerald-600 hover:bg-emerald-700 text-white font-black uppercase text-[9px] tracking-wider"
              >
                <CheckCircle size={11} className="mr-1" /> Approve
              </Button>
            )}
            {rejecting ? (
              <>
                <Button
                  onClick={() => decide(false)}
                  disabled={busy}
                  className="flex-1 h-8 bg-rose-600 hover:bg-rose-700 text-white font-black uppercase text-[9px] tracking-wider"
                >
                  <XCircle size={11} className="mr-1" /> Confirm reject
                </Button>
                <Button
                  onClick={() => {
                    setRejecting(false);
                    setNote('');
                  }}
                  variant="outline"
                  className="h-8 font-black uppercase text-[9px] tracking-wider"
                >
                  Back
                </Button>
              </>
            ) : (
              <Button
                onClick={() => setRejecting(true)}
                disabled={busy}
                variant="outline"
                className="flex-1 h-8 border-rose-200 text-rose-600 hover:bg-rose-50 font-black uppercase text-[9px] tracking-wider"
              >
                <XCircle size={11} className="mr-1" /> Reject
              </Button>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export const RegularizationList: React.FC<{
  items: Regularization[];
  showRequester?: boolean;
  /** Provide to show Approve/Reject on pending rows. */
  onDecided?: () => void;
  /** Provide to show Cancel on pending rows (requester view). */
  onCancel?: (id: number) => void;
  emptyText?: string;
}> = ({ items, showRequester = false, onDecided, onCancel, emptyText = 'No correction requests' }) => {
  if (items.length === 0) {
    return (
      <p className="text-[10px] font-black uppercase tracking-widest text-slate-400 py-6 text-center">
        {emptyText}
      </p>
    );
  }
  return (
    <div className="space-y-2">
      {items.map((r) => (
        <RequestRow
          key={r.id}
          r={r}
          showRequester={showRequester}
          onDecided={onDecided}
          onCancel={onCancel}
        />
      ))}
    </div>
  );
};

// ---------------------------------------------------------------------------
// Approver queue (Approvals Center tab)
// ---------------------------------------------------------------------------

export const RegularizationQueue: React.FC<{ title?: string }> = ({
  title = 'Attendance Correction Requests',
}) => {
  const [status, setStatus] = useState<RegularizationStatus | 'all'>('pending');
  const [items, setItems] = useState<Regularization[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await regularizationApi.listQueue(status);
      setItems(res.data || []);
    } catch (e) {
      toast.error(regularizationErrMsg(e, 'Failed to load correction requests'));
    } finally {
      setLoading(false);
    }
  }, [status]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <Card className="p-5 border-slate-200 bg-white">
      <div className="flex items-center justify-between gap-2 mb-3">
        <p className="text-[10px] font-black uppercase tracking-widest text-[#0F172A]">
          {title}
        </p>
        <div className="flex items-center gap-2">
          <select
            aria-label="Status filter"
            value={status}
            onChange={(e) => setStatus(e.target.value as RegularizationStatus | 'all')}
            className="h-8 px-2 rounded-lg border border-slate-200 text-xs font-bold text-slate-700 bg-white"
          >
            <option value="pending">Pending</option>
            <option value="approved">Approved</option>
            <option value="rejected">Rejected</option>
            <option value="cancelled">Cancelled</option>
            <option value="all">All</option>
          </select>
          <Button onClick={load} variant="outline" className="h-8 text-[10px] font-black uppercase">
            <RefreshCw size={12} className="mr-1" /> Refresh
          </Button>
        </div>
      </div>
      {loading ? (
        <p className="text-[10px] font-black uppercase tracking-widest text-slate-400 py-6 text-center">
          Loading…
        </p>
      ) : (
        <RegularizationList
          items={items}
          showRequester
          onDecided={load}
          emptyText="No correction requests"
        />
      )}
    </Card>
  );
};

// ---------------------------------------------------------------------------
// Employee side: request dialog + my requests
// ---------------------------------------------------------------------------

export const RegularizationRequestDialog: React.FC<{
  open: boolean;
  onClose: () => void;
  onCreated?: () => void;
}> = ({ open, onClose, onCreated }) => {
  const yesterday = () => {
    const d = new Date();
    d.setDate(d.getDate() - 1);
    return localIsoDate(d);
  };
  const [date, setDate] = useState(yesterday());
  const [punchIn, setPunchIn] = useState('');
  const [punchOut, setPunchOut] = useState('');
  const [nextDay, setNextDay] = useState(false);
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setDate(yesterday());
      setPunchIn('');
      setPunchOut('');
      setNextDay(false);
      setReason('');
      setError(null);
    }
  }, [open]);

  const submit = async () => {
    if (!date || !punchIn) {
      setError('Date and punch-in time are required');
      return;
    }
    if (!reason.trim()) {
      setError('Please give a reason');
      return;
    }
    // Local wall-clock -> absolute instant (with the browser's UTC offset).
    const inIso = new Date(`${date}T${punchIn}`).toISOString();
    let outIso: string | null = null;
    if (punchOut) {
      const outDate = new Date(`${date}T${punchOut}`);
      if (nextDay) outDate.setDate(outDate.getDate() + 1);
      outIso = outDate.toISOString();
    }
    setBusy(true);
    setError(null);
    try {
      await regularizationApi.create({
        work_date: date,
        requested_punch_in: inIso,
        requested_punch_out: outIso,
        reason: reason.trim(),
      });
      toast.success('Correction request submitted');
      onCreated?.();
      onClose();
    } catch (e) {
      setError(regularizationErrMsg(e, 'Failed to submit request'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o: boolean) => !o && onClose()}>
      <DialogContent className="max-w-md">
        <DialogTitle className="flex items-center gap-2 text-base font-black uppercase tracking-tight text-[#0F172A]">
          <Wrench size={15} className="text-blue-600" /> Request Attendance Correction
        </DialogTitle>
        <p className="text-[10px] font-bold text-slate-500 -mt-1">
          Approved by your manager or HR; punch times are then updated
        </p>
        <div className="space-y-3 pt-1">
          <div className="space-y-1">
            <label className="text-[9px] font-black uppercase tracking-widest text-slate-400">
              Work date
            </label>
            <input
              type="date"
              className={inputCls}
              value={date}
              onChange={(e) => setDate(e.target.value)}
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <label className="text-[9px] font-black uppercase tracking-widest text-slate-400">
                Punch-in
              </label>
              <input
                type="time"
                aria-label="Punch-in time"
                className={inputCls}
                value={punchIn}
                onChange={(e) => setPunchIn(e.target.value)}
              />
            </div>
            <div className="space-y-1">
              <label className="text-[9px] font-black uppercase tracking-widest text-slate-400">
                Punch-out (optional)
              </label>
              <input
                type="time"
                aria-label="Punch-out time"
                className={inputCls}
                value={punchOut}
                onChange={(e) => setPunchOut(e.target.value)}
              />
            </div>
          </div>
          <label className="flex items-center gap-2 text-[10px] font-bold text-slate-600">
            <input
              type="checkbox"
              checked={nextDay}
              onChange={(e) => setNextDay(e.target.checked)}
            />
            Punch-out is on the next day (overnight shift)
          </label>
          <div className="space-y-1">
            <label className="text-[9px] font-black uppercase tracking-widest text-slate-400">
              Reason (required)
            </label>
            <textarea
              className={inputCls + ' h-20 py-2 resize-none'}
              placeholder="e.g. Forgot to punch in; was on site from 9:30"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
          </div>
          {error && (
            <div className="p-3 bg-red-50 border border-red-100 rounded-xl text-red-600 text-xs font-bold">
              {error}
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button onClick={submit} isLoading={busy}>
            Submit Request
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

/** Request button + the user's own requests (with Cancel on pending). */
export const MyRegularizations: React.FC = () => {
  const [items, setItems] = useState<Regularization[]>([]);
  const [open, setOpen] = useState(false);

  const load = useCallback(async () => {
    try {
      const res = await regularizationApi.listMine();
      setItems(res.data || []);
    } catch (e) {
      toast.error(regularizationErrMsg(e, 'Failed to load correction requests'));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const cancel = async (id: number) => {
    try {
      await regularizationApi.cancel(id);
      toast.success('Request cancelled');
      void load();
    } catch (e) {
      toast.error(regularizationErrMsg(e, 'Failed to cancel request'));
    }
  };

  return (
    <Card className="p-5 border-slate-200 bg-white">
      <div className="flex items-center justify-between mb-3">
        <p className="text-[10px] font-black uppercase tracking-widest text-[#0F172A]">
          My Correction Requests
        </p>
        <Button onClick={() => setOpen(true)} className="h-8 text-[10px] font-black uppercase">
          <Send size={12} className="mr-1" /> Request correction
        </Button>
      </div>
      <RegularizationList items={items} onCancel={cancel} emptyText="No correction requests yet" />
      <RegularizationRequestDialog open={open} onClose={() => setOpen(false)} onCreated={load} />
    </Card>
  );
};

/** Shown only to users who have something to approve (direct reports / HR). */
export const TeamRegularizations: React.FC = () => {
  const [show, setShow] = useState(false);
  useEffect(() => {
    let cancelled = false;
    regularizationApi
      .listQueue('all')
      .then((res) => {
        if (!cancelled) setShow((res.data || []).length > 0);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);
  return show ? <RegularizationQueue title="Team Correction Requests" /> : null;
};
