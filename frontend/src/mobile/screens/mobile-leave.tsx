import React, { useEffect, useMemo, useState } from 'react';
import { Plus, Loader2, XCircle, CalendarDays, Paperclip } from 'lucide-react';
import { toast } from 'sonner';
import { cn, errMsg, fmtDate, StatusChip, EmptyState } from '../../components/ui-elements';
import { client } from '../../api/client';
import { ENDPOINTS } from '../../api/endpoints';
import type { LeaveBalance, LeaveRequest } from '../../types/erp';

interface LeaveType {
  id: number;
  name: string;
  is_paid?: boolean;
}

export const MobileLeave: React.FC = () => {
  const [balances, setBalances] = useState<LeaveBalance[]>([]);
  const [types, setTypes] = useState<LeaveType[]>([]);
  const [history, setHistory] = useState<LeaveRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [showApply, setShowApply] = useState(false);

  useEffect(() => {
    void load();
  }, []);

  const load = async () => {
    setLoading(true);
    try {
      const [bal, ty, his] = await Promise.all([
        client.get<LeaveBalance[]>(ENDPOINTS.LEAVE.BALANCES),
        client.get<LeaveType[]>(ENDPOINTS.LEAVE.TYPES),
        client.get<LeaveRequest[]>(ENDPOINTS.LEAVE.MY),
      ]);
      setBalances(bal.data || []);
      setTypes(ty.data || []);
      setHistory(his.data || []);
    } catch (e) {
      toast.error(errMsg(e, 'Failed to load leave data'));
    } finally {
      setLoading(false);
    }
  };

  const cancel = async (id: number) => {
    if (!confirm('Cancel this leave request?')) return;
    try {
      await client.post(ENDPOINTS.LEAVE.CANCEL(id));
      toast.success('Leave request cancelled');
      void load();
    } catch (e) {
      toast.error(errMsg(e, 'Cancel failed'));
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 size={22} className="animate-spin text-slate-400" />
      </div>
    );
  }

  return (
    <div className="p-4 space-y-4">
      <BalanceStrip balances={balances} />

      <div className="flex items-center justify-between px-1">
        <h2 className="text-[13px] font-black uppercase tracking-widest text-slate-500">
          My requests
        </h2>
        <button
          type="button"
          onClick={() => setShowApply(true)}
          className="text-[12px] font-bold text-[#2563EB] flex items-center gap-1"
        >
          <Plus size={14} /> Apply
        </button>
      </div>

      {history.length === 0 ? (
        <EmptyState title="No leave yet" hint="Tap Apply to submit a leave request." />
      ) : (
        <ul className="space-y-3">
          {history.map((r) => (
            <li
              key={r.id}
              className="bg-white border border-slate-200 rounded-2xl p-4"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-sm font-black text-[#0F172A] truncate">
                    {r.leave_type?.name || 'Leave'}
                  </p>
                  <p className="text-[12px] text-slate-500 mt-0.5">
                    {fmtDate(r.start_date)} → {fmtDate(r.end_date)}
                    {r.is_half_day && ' · Half-day'}
                    {' · '}
                    <span className="font-bold">{r.total_days}d</span>
                  </p>
                  {r.reason && (
                    <p className="text-[12px] text-slate-500 mt-1 line-clamp-2">
                      {r.reason}
                    </p>
                  )}
                </div>
                <StatusChip status={r.status} />
              </div>
              {r.status === 'submitted' && (
                <button
                  type="button"
                  onClick={() => cancel(r.id)}
                  className="mt-3 h-9 w-full rounded-lg border border-slate-200 text-[12px] font-bold text-slate-700 active:bg-slate-50 flex items-center justify-center gap-1"
                >
                  <XCircle size={14} /> Cancel request
                </button>
              )}
            </li>
          ))}
        </ul>
      )}

      {showApply && (
        <ApplyLeaveSheet
          types={types}
          onClose={() => setShowApply(false)}
          onSubmitted={() => {
            setShowApply(false);
            void load();
          }}
        />
      )}
    </div>
  );
};

const BalanceStrip: React.FC<{ balances: LeaveBalance[] }> = ({ balances }) => {
  if (balances.length === 0) {
    return (
      <div className="rounded-2xl bg-white border border-slate-200 p-4 flex items-center gap-3">
        <CalendarDays size={18} className="text-slate-400" />
        <p className="text-sm text-slate-500">No leave balance assigned.</p>
      </div>
    );
  }
  return (
    <div>
      <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400 mb-2 px-1">
        Balance
      </p>
      <div
        className="grid grid-flow-col auto-cols-[minmax(140px,1fr)] gap-3 overflow-x-auto pb-1 -mx-1 px-1 scroll-smooth snap-x"
        style={{ scrollPaddingInline: 4 }}
      >
        {balances.map((b) => (
          <div
            key={b.id}
            className="bg-white border border-slate-200 rounded-2xl p-4 snap-start"
          >
            <p className="text-[11px] font-bold text-slate-500 truncate">
              {b.leave_type?.name || 'Leave'}
            </p>
            <p className="text-2xl font-black text-[#0F172A] tabular-nums mt-1">
              {b.remaining.toFixed(1)}
            </p>
            <p className="text-[11px] text-slate-400">
              of {b.total.toFixed(1)} days
            </p>
          </div>
        ))}
      </div>
    </div>
  );
};

const ApplyLeaveSheet: React.FC<{
  types: LeaveType[];
  onClose: () => void;
  onSubmitted: () => void;
}> = ({ types, onClose, onSubmitted }) => {
  const [typeId, setTypeId] = useState<string>(
    types[0] ? String(types[0].id) : ''
  );
  const [start, setStart] = useState('');
  const [end, setEnd] = useState('');
  const [halfDay, setHalfDay] = useState(false);
  const [session, setSession] = useState<'morning' | 'afternoon'>('morning');
  const [reason, setReason] = useState('');
  const [emergency, setEmergency] = useState('');
  const [attach, setAttach] = useState<File | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const totalDays = useMemo(() => {
    if (!start || !end) return 0;
    if (halfDay) return 0.5;
    const a = new Date(start);
    const b = new Date(end);
    const diff = Math.floor((b.getTime() - a.getTime()) / 86400000) + 1;
    return Math.max(1, diff);
  }, [start, end, halfDay]);

  const submit = async () => {
    if (!typeId || !start || !end || !reason.trim()) {
      toast.error('Please fill all required fields');
      return;
    }
    setSubmitting(true);
    try {
      let attachmentUrl: string | null = null;
      if (attach) {
        const form = new FormData();
        form.append('file', attach);
        const up = await client.post(
          ENDPOINTS.LEAVE.ATTACHMENT_UPLOAD,
          form
        );
        attachmentUrl = (up.data as any)?.attachment_url || null;
      }
      await client.post(ENDPOINTS.LEAVE.APPLY, {
        leave_type_id: parseInt(typeId, 10),
        start_date: start,
        end_date: end,
        reason,
        emergency_contact: emergency,
        is_half_day: halfDay,
        half_day_session: halfDay ? session : null,
        attachment_url: attachmentUrl,
      });
      toast.success('Leave request submitted');
      onSubmitted();
    } catch (e) {
      toast.error(errMsg(e, 'Submit failed'));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 bg-slate-900/50 flex items-end"
      role="dialog"
      aria-modal="true"
      onClick={onClose}
    >
      <div
        className="w-full max-h-[90dvh] overflow-y-auto bg-white rounded-t-3xl p-5 space-y-4"
        onClick={(e) => e.stopPropagation()}
        style={{ paddingBottom: 'calc(env(safe-area-inset-bottom) + 20px)' }}
      >
        <div className="w-10 h-1 bg-slate-200 rounded-full mx-auto" />
        <h2 className="text-lg font-black text-[#0F172A]">Apply for leave</h2>

        <Field label="Leave type">
          <select
            value={typeId}
            onChange={(e) => setTypeId(e.target.value)}
            className="w-full h-11 rounded-xl border border-slate-200 px-3 text-sm bg-white"
          >
            {types.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>
        </Field>

        <div className="grid grid-cols-2 gap-3">
          <Field label="Start">
            <input
              type="date"
              value={start}
              onChange={(e) => {
                setStart(e.target.value);
                if (!end || new Date(e.target.value) > new Date(end)) {
                  setEnd(e.target.value);
                }
              }}
              className="w-full h-11 rounded-xl border border-slate-200 px-3 text-sm"
            />
          </Field>
          <Field label="End">
            <input
              type="date"
              value={end}
              min={start}
              disabled={halfDay}
              onChange={(e) => setEnd(e.target.value)}
              className="w-full h-11 rounded-xl border border-slate-200 px-3 text-sm disabled:bg-slate-50 disabled:text-slate-400"
            />
          </Field>
        </div>

        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={halfDay}
            onChange={(e) => {
              setHalfDay(e.target.checked);
              if (e.target.checked && start) setEnd(start);
            }}
          />
          Half-day
        </label>
        {halfDay && (
          <div className="flex gap-2">
            {(['morning', 'afternoon'] as const).map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => setSession(s)}
                className={cn(
                  'flex-1 h-10 rounded-xl text-sm font-bold border',
                  session === s
                    ? 'bg-[#2563EB] border-[#2563EB] text-white'
                    : 'bg-white border-slate-200 text-slate-700'
                )}
              >
                {s === 'morning' ? 'Morning' : 'Afternoon'}
              </button>
            ))}
          </div>
        )}

        <Field label="Reason">
          <textarea
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            className="w-full min-h-20 rounded-xl border border-slate-200 p-3 text-sm"
            placeholder="Why do you need this leave?"
          />
        </Field>

        <Field label="Emergency contact (optional)">
          <input
            value={emergency}
            onChange={(e) => setEmergency(e.target.value)}
            className="w-full h-11 rounded-xl border border-slate-200 px-3 text-sm"
            placeholder="Name / number"
          />
        </Field>

        <div>
          <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400 mb-1">
            Attachment (optional)
          </p>
          <label className="w-full h-11 rounded-xl border border-slate-200 bg-slate-50 flex items-center justify-center gap-2 text-sm font-bold text-slate-700 cursor-pointer">
            <Paperclip size={14} />
            {attach ? attach.name : 'Add file'}
            <input
              type="file"
              className="hidden"
              onChange={(e) => setAttach(e.target.files?.[0] ?? null)}
            />
          </label>
        </div>

        <div className="flex items-center justify-between bg-slate-50 border border-slate-200 rounded-xl px-4 py-3">
          <span className="text-[12px] font-bold text-slate-500 uppercase tracking-widest">
            Days
          </span>
          <span className="text-lg font-black text-[#0F172A] tabular-nums">
            {totalDays.toFixed(1)}
          </span>
        </div>

        <div className="flex gap-3 pt-2">
          <button
            type="button"
            onClick={onClose}
            className="flex-1 h-12 rounded-xl border border-slate-200 font-bold text-slate-700"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={submit}
            disabled={submitting}
            className="flex-1 h-12 rounded-xl bg-[#2563EB] text-white font-bold disabled:opacity-50 flex items-center justify-center gap-2"
          >
            {submitting && <Loader2 size={16} className="animate-spin" />}
            Submit
          </button>
        </div>
      </div>
    </div>
  );
};

const Field: React.FC<{ label: string; children: React.ReactNode }> = ({
  label,
  children,
}) => (
  <div>
    <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400 mb-1">
      {label}
    </p>
    {children}
  </div>
);
