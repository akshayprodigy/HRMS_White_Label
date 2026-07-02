import React, { useEffect, useState } from 'react';
import { toast } from 'sonner';
import {
  CalendarClock,
  Clock3,
  Moon,
  RefreshCw,
  Send,
  XCircle,
} from 'lucide-react';
import { Card, Button, Badge, cn } from './ui-elements';
import { Dialog, DialogContent, DialogTitle, DialogFooter } from './ui/dialog';
import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';

// Section R: employee self-service — current shift, assignment history,
// and shift-change requests (approved Manager -> HR via the chain
// engine; progress shows in the requester's list below).

const errMsg = (e: any, fallback: string) =>
  e?.response?.data?.detail ||
  e?.response?.data?.error?.message ||
  fallback;

const inputCls =
  'w-full h-10 px-3 rounded-lg border border-slate-200 text-sm text-[#0F172A] ' +
  'focus:outline-none focus:ring-2 focus:ring-blue-600/30 focus:border-blue-500 bg-white';

const STATUS_TONE: Record<string, 'success' | 'error' | 'warning' | 'neutral'> = {
  approved: 'success',
  rejected: 'error',
  pending: 'warning',
  cancelled: 'neutral',
};

const fmtShiftWindow = (s: any) =>
  s ? `${(s.start_time || '').slice(0, 5)} – ${(s.end_time || '').slice(0, 5)}` : '';

export const MyShiftView: React.FC = () => {
  const [current, setCurrent] = useState<any | null>(null);
  const [history, setHistory] = useState<any[]>([]);
  const [requests, setRequests] = useState<any[]>([]);
  const [templates, setTemplates] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [reqOpen, setReqOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({
    requested_shift_template_id: '' as number | '',
    effective_from: '',
    reason: '',
  });

  const refresh = async () => {
    setLoading(true);
    try {
      const [cur, hist, reqs, tpls] = await Promise.all([
        client.get(ENDPOINTS.SHIFTS.MY_CURRENT).catch(() => ({ data: null })),
        client.get(ENDPOINTS.SHIFTS.MY_HISTORY).catch(() => ({ data: [] })),
        client.get(ENDPOINTS.SHIFTS.CHANGE_REQUESTS_MY).catch(() => ({ data: [] })),
        client.get(ENDPOINTS.SHIFTS.TEMPLATES).catch(() => ({ data: [] })),
      ]);
      setCurrent(cur.data);
      setHistory(hist.data || []);
      setRequests(reqs.data || []);
      setTemplates((tpls.data || []).filter((t: any) => t.is_active));
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { refresh(); }, []);

  const hasPending = requests.some((r) => r.status === 'pending');

  const submit = async () => {
    if (!form.requested_shift_template_id) {
      toast.error('Pick the shift you want to move to.');
      return;
    }
    if (!form.effective_from) {
      toast.error('Pick the date the change should start.');
      return;
    }
    if (form.reason.trim().length < 5) {
      toast.error('Please give a reason (at least 5 characters).');
      return;
    }
    setBusy(true);
    try {
      await client.post(ENDPOINTS.SHIFTS.CHANGE_REQUESTS, {
        requested_shift_template_id: form.requested_shift_template_id,
        effective_from: form.effective_from,
        reason: form.reason.trim(),
      });
      toast.success('Shift change requested — sent to your manager');
      setReqOpen(false);
      setForm({ requested_shift_template_id: '', effective_from: '', reason: '' });
      await refresh();
    } catch (e: any) {
      toast.error(errMsg(e, 'Failed to submit request'));
    } finally {
      setBusy(false);
    }
  };

  const cancel = async (id: number) => {
    try {
      await client.post(ENDPOINTS.SHIFTS.CHANGE_REQUEST_CANCEL(id));
      toast.success('Request cancelled');
      await refresh();
    } catch (e: any) {
      toast.error(errMsg(e, 'Failed to cancel request'));
    }
  };

  const shift = current?.shift;

  return (
    <div className="p-8 max-w-[1100px] mx-auto space-y-6 animate-in fade-in duration-300">
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <h2 className="text-3xl font-black text-[#0F172A] tracking-tighter uppercase">
            My Shift
          </h2>
          <p className="text-[#64748B] font-bold uppercase tracking-widest text-[10px] mt-1">
            Current schedule, history & change requests
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={refresh} className="h-10">
            <RefreshCw size={14} className="mr-1.5" /> Refresh
          </Button>
          <Button
            onClick={() => setReqOpen(true)}
            disabled={hasPending}
            className="h-10"
            title={hasPending ? 'You already have a pending request' : undefined}
          >
            <Send size={14} className="mr-1.5" /> Request Shift Change
          </Button>
        </div>
      </div>

      {/* Current shift */}
      <Card className="p-6 border-slate-200 bg-white">
        {loading ? (
          <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">Loading…</p>
        ) : shift ? (
          <div className="flex items-center gap-4">
            <div className={cn(
              'w-12 h-12 rounded-2xl flex items-center justify-center',
              shift.is_overnight ? 'bg-indigo-50 text-indigo-600' : 'bg-blue-50 text-blue-600',
            )}>
              {shift.is_overnight ? <Moon size={20} /> : <Clock3 size={20} />}
            </div>
            <div>
              <p className="text-lg font-black text-[#0F172A] tracking-tight">{shift.name}</p>
              <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest tabular-nums">
                {fmtShiftWindow(shift)}
                {shift.is_overnight ? ' · overnight' : ''}
                {` · grace in ${shift.grace_in_minutes}m / out ${shift.grace_out_minutes}m`}
              </p>
            </div>
          </div>
        ) : (
          <div className="flex items-center gap-4">
            <div className="w-12 h-12 rounded-2xl bg-slate-100 text-slate-400 flex items-center justify-center">
              <CalendarClock size={20} />
            </div>
            <div>
              <p className="text-lg font-black text-[#0F172A] tracking-tight">No shift assigned</p>
              <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">
                Org default hours apply — ask HR or request a shift below
              </p>
            </div>
          </div>
        )}
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* My requests */}
        <Card className="p-5 border-slate-200 bg-white">
          <p className="text-[10px] font-black uppercase tracking-widest text-[#0F172A] mb-3">
            My Change Requests
          </p>
          {requests.length === 0 ? (
            <p className="text-[10px] font-black uppercase tracking-widest text-slate-400 py-6 text-center">
              No requests yet
            </p>
          ) : (
            <div className="space-y-2">
              {requests.map((r) => (
                <div key={r.id} className="border border-slate-100 rounded-xl p-3">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-[11px] font-black text-[#0F172A]">
                      {r.current_shift_name || 'No shift'} → {r.requested_shift_name}
                    </p>
                    <Badge variant={STATUS_TONE[r.status] || 'neutral'} className="text-[8px] uppercase">
                      {r.status}
                    </Badge>
                  </div>
                  <p className="text-[9px] font-bold text-slate-500 mt-1 tabular-nums">
                    from {r.effective_from} · requested {String(r.created_at).slice(0, 10)}
                  </p>
                  <p className="text-[10px] text-slate-600 italic mt-1 truncate">"{r.reason}"</p>
                  {r.status === 'pending' && (
                    <button
                      type="button"
                      onClick={() => cancel(r.id)}
                      className="mt-2 inline-flex items-center gap-1 text-[9px] font-black uppercase tracking-widest text-rose-500 hover:text-rose-700"
                    >
                      <XCircle size={10} /> Cancel request
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}
        </Card>

        {/* Assignment history */}
        <Card className="p-5 border-slate-200 bg-white">
          <p className="text-[10px] font-black uppercase tracking-widest text-[#0F172A] mb-3">
            Assignment History
          </p>
          {history.length === 0 ? (
            <p className="text-[10px] font-black uppercase tracking-widest text-slate-400 py-6 text-center">
              No assignments on record
            </p>
          ) : (
            <div className="space-y-2">
              {history.map((a: any) => (
                <div key={a.id} className="flex items-center justify-between border border-slate-100 rounded-xl p-3">
                  <div>
                    <p className="text-[11px] font-black text-[#0F172A]">
                      {a.shift_template_name || a.shift_template?.name || `Shift #${a.shift_template_id}`}
                    </p>
                    <p className="text-[9px] font-bold text-slate-500 tabular-nums mt-0.5">
                      {a.effective_from} → {a.effective_to || 'ongoing'}
                    </p>
                  </div>
                  {!a.effective_to && (
                    <Badge variant="success" className="text-[8px] uppercase">Active</Badge>
                  )}
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      {/* Request dialog */}
      {reqOpen && (
        <Dialog open onOpenChange={(o) => !o && setReqOpen(false)}>
          <DialogContent className="max-w-md">
            <DialogTitle className="flex items-center gap-2 text-base font-black uppercase tracking-tight text-[#0F172A]">
              <Send size={15} className="text-blue-600" /> Request Shift Change
            </DialogTitle>
            <p className="text-[10px] font-bold text-slate-500 -mt-1">
              Approved by your manager, then HR
            </p>
            <div className="space-y-3 pt-1">
              <div className="space-y-1">
                <label className="text-[9px] font-black uppercase tracking-widest text-slate-400">
                  Move to shift
                </label>
                <select
                  className={inputCls}
                  value={form.requested_shift_template_id}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      requested_shift_template_id: e.target.value ? Number(e.target.value) : '',
                    })
                  }
                >
                  <option value="">Select a shift…</option>
                  {templates.map((t: any) => (
                    <option key={t.id} value={t.id}>
                      {t.name}
                    </option>
                  ))}
                </select>
              </div>
              <div className="space-y-1">
                <label className="text-[9px] font-black uppercase tracking-widest text-slate-400">
                  Effective from
                </label>
                <input
                  type="date"
                  className={inputCls}
                  value={form.effective_from}
                  onChange={(e) => setForm({ ...form, effective_from: e.target.value })}
                />
              </div>
              <div className="space-y-1">
                <label className="text-[9px] font-black uppercase tracking-widest text-slate-400">
                  Reason (required)
                </label>
                <textarea
                  className={inputCls + ' h-20 py-2 resize-none'}
                  placeholder="e.g. College classes moved to mornings from next month"
                  value={form.reason}
                  onChange={(e) => setForm({ ...form, reason: e.target.value })}
                />
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setReqOpen(false)} disabled={busy}>
                Cancel
              </Button>
              <Button onClick={submit} isLoading={busy}>
                Submit Request
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
    </div>
  );
};
