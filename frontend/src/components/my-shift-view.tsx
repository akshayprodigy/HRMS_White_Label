import React, { useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';
import {
  CalendarClock,
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  Clock3,
  Moon,
  RefreshCw,
  Send,
  XCircle,
} from 'lucide-react';
import { Card, Button, Badge, cn } from './ui-elements';
import { Dialog, DialogContent, DialogTitle, DialogDescription, DialogFooter } from './ui/dialog';
import { MyRegularizations, TeamRegularizations } from './regularization-requests';
import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';
import { todayIso } from './schedule-delegations-utils';
import { AvailabilityPanel } from './my-schedule/availability-panel';
import { SwapPanel } from './my-schedule/swap-panel';
import { SwapDialog } from './my-schedule/swap-dialog';
import { GiveawayDialog } from './my-schedule/giveaway-dialog';
import { OpenShiftsPanel } from './my-schedule/open-shifts-panel';
import { RunningLateCard } from './my-schedule/running-late-card';
import { MyOnCallCard } from './my-schedule/my-on-call-card';
import { MyAcksBanner } from './my-schedule/my-acks-banner';
import { CalendarFeedCard } from './my-schedule/calendar-feed-card';
import { STATUS_TONE, inputCls } from './my-schedule/my-schedule-api';

type MyTab = 'week' | 'availability' | 'swaps' | 'open' | 'calendar';
const TABS: { id: MyTab; label: string }[] = [
  { id: 'week', label: 'Week' },
  { id: 'availability', label: 'Availability' },
  { id: 'swaps', label: 'Swaps & give-aways' },
  { id: 'open', label: 'Open shifts' },
  { id: 'calendar', label: 'Calendar' },
];

const addDays = (iso: string, n: number) => {
  const d = new Date(iso + 'T00:00:00Z');
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
};

// Section R: employee self-service — current shift, assignment history,
// and shift-change requests (approved Manager -> HR via the chain
// engine; progress shows in the requester's list below).

const errMsg = (e: any, fallback: string) =>
  e?.response?.data?.detail ||
  e?.response?.data?.error?.message ||
  fallback;

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

  // W7: roster week + per-day change requests
  const [rosterWeek, setRosterWeek] = useState<any | null>(null);
  const [weekStart, setWeekStart] = useState<string | null>(null); // null = current week
  const [tab, setTab] = useState<MyTab>('week');
  const [swapDay, setSwapDay] = useState<any | null>(null);
  const [giveDay, setGiveDay] = useState<any | null>(null);
  const [selfReload, setSelfReload] = useState(0);
  const [rosterReqs, setRosterReqs] = useState<any[]>([]);
  const [rosterReqOpen, setRosterReqOpen] = useState(false);
  const [rosterBusy, setRosterBusy] = useState(false);
  const [rosterForm, setRosterForm] = useState({
    work_date: '',
    requested_shift_template_id: '' as number | '',
    requested_week_off: false,
    reason: '',
  });

  const weekSeq = useRef(0);
  const [weekLoading, setWeekLoading] = useState(false);
  // Keeps the previous week on failure; stale responses are ignored.
  const loadWeek = async (start: string | null) => {
    const my = ++weekSeq.current;
    setWeekLoading(true);
    try {
      const r = await client.get(ENDPOINTS.ROSTER.MY_WEEK, {
        params: start ? { start } : undefined,
      });
      if (my === weekSeq.current) {
        setRosterWeek(r.data);
        setWeekStart(start);
      }
    } catch (e: any) {
      if (my === weekSeq.current) toast.error(errMsg(e, 'Failed to load roster week'));
    } finally {
      if (my === weekSeq.current) setWeekLoading(false);
    }
  };

  const refresh = async () => {
    setLoading(true);
    try {
      const weekP = loadWeek(weekStart);
      const [cur, hist, reqs, tpls, rReqs] = await Promise.all([
        client.get(ENDPOINTS.SHIFTS.MY_CURRENT).catch(() => ({ data: null })),
        client.get(ENDPOINTS.SHIFTS.MY_HISTORY).catch(() => ({ data: [] })),
        client.get(ENDPOINTS.SHIFTS.CHANGE_REQUESTS_MY).catch(() => ({ data: [] })),
        client.get(ENDPOINTS.SHIFTS.TEMPLATES).catch(() => ({ data: [] })),
        client.get(ENDPOINTS.ROSTER.CHANGE_REQUESTS_MY).catch(() => ({ data: [] })),
      ]);
      setCurrent(cur.data);
      setHistory(hist.data || []);
      setRequests(reqs.data || []);
      setTemplates((tpls.data || []).filter((t: any) => t.is_active));
      await weekP;
      setRosterReqs(rReqs.data || []);
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { refresh(); }, []);

  const openRosterReq = (workDate: string) => {
    setRosterForm({
      work_date: workDate,
      requested_shift_template_id: '',
      requested_week_off: false,
      reason: '',
    });
    setRosterReqOpen(true);
  };

  const submitRosterReq = async () => {
    if (!rosterForm.requested_week_off && !rosterForm.requested_shift_template_id) {
      toast.error('Pick a shift or choose week-off.');
      return;
    }
    if (rosterForm.reason.trim().length < 5) {
      toast.error('Please give a reason (at least 5 characters).');
      return;
    }
    setRosterBusy(true);
    try {
      await client.post(ENDPOINTS.ROSTER.CHANGE_REQUESTS, {
        work_date: rosterForm.work_date,
        requested_shift_template_id: rosterForm.requested_week_off
          ? null
          : rosterForm.requested_shift_template_id,
        requested_week_off: rosterForm.requested_week_off,
        reason: rosterForm.reason.trim(),
      });
      toast.success('Roster change requested — sent to your team head');
      setRosterReqOpen(false);
      await refresh();
    } catch (e: any) {
      toast.error(errMsg(e, 'Failed to submit roster request'));
    } finally {
      setRosterBusy(false);
    }
  };

  const cancelRosterReq = async (id: number) => {
    try {
      await client.post(ENDPOINTS.ROSTER.CHANGE_REQUEST_CANCEL(id));
      toast.success('Roster request cancelled');
      await refresh();
    } catch (e: any) {
      toast.error(errMsg(e, 'Failed to cancel request'));
    }
  };

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
              {rosterWeek?.days?.some((x: any) => x.is_today && x.shift?.transport_required) && (
                <p className="text-[10px] font-black text-indigo-600 uppercase tracking-widest mt-1">
                  Cab/transport arranged
                </p>
              )}
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

      <MyAcksBanner />
      <RunningLateCard />
      <MyOnCallCard />

      {/* W7: My Roster — this week */}
      {rosterWeek?.days?.length ? (
        <Card className="p-5 border-slate-200 bg-white">
          <div className="flex items-center justify-between mb-3">
            <p className="text-[10px] font-black uppercase tracking-widest text-[#0F172A] flex items-center gap-1.5">
              <CalendarDays size={13} className="text-indigo-600" /> My Roster ·{' '}
              {rosterWeek.days.some((x: any) => x.is_today) ? 'This Week' : `Week of ${rosterWeek.start}`}
            </p>
            <div className="flex items-center gap-2">
              <span className="hidden sm:block text-[9px] font-bold text-slate-400 uppercase tracking-widest">
                tap a day to request a change
              </span>
              {!rosterWeek.days.some((x: any) => x.is_today) && (
                <button type="button" disabled={weekLoading} onClick={() => loadWeek(null)}
                  className="text-[9px] font-black uppercase tracking-widest text-indigo-600 hover:underline px-1">
                  This week
                </button>
              )}
              <button type="button" aria-label="Previous week" disabled={weekLoading}
                onClick={() => loadWeek(addDays(rosterWeek.start, -7))}
                className="p-1 rounded-md text-slate-500 hover:bg-slate-100 disabled:opacity-50">
                <ChevronLeft size={14} />
              </button>
              <button type="button" aria-label="Next week" disabled={weekLoading}
                onClick={() => loadWeek(addDays(rosterWeek.start, 7))}
                className="p-1 rounded-md text-slate-500 hover:bg-slate-100 disabled:opacity-50">
                <ChevronRight size={14} />
              </button>
            </div>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-2">
            {rosterWeek.days.map((d: any) => {
              // Weekly-off day with only an assigned/default shift behaves
              // like the My Workspace widget; a published roster shift wins.
              const weekOff =
                d.shift?.name === 'Week off' ||
                (!!d.is_weekend && d.shift?.source !== 'roster');
              // A published roster shift (not a default/assigned one) can be
              // swapped or given away while it is today or later.
              const published =
                d.shift?.source === 'roster' && !!d.shift?.start_time && !d.on_leave;
              const canAct = published && d.date >= todayIso();
              return (
              <div
                key={d.date}
                className={cn(
                  'border rounded-xl transition-colors hover:border-indigo-300 hover:bg-indigo-50/40 flex flex-col',
                  d.is_today ? 'border-indigo-300 bg-indigo-50/50' : 'border-slate-100',
                )}
              >
              <button
                type="button"
                onClick={() => openRosterReq(d.date)}
                className="text-left p-2.5 flex-1"
              >
                <p className="text-[9px] font-black uppercase tracking-widest text-slate-400">
                  {new Date(d.date + 'T00:00:00').toLocaleDateString('en-IN', { weekday: 'short', day: '2-digit' })}
                </p>
                <p className="text-[11px] font-black text-[#0F172A] mt-1 truncate">
                  {d.on_leave ? 'On leave' : weekOff ? 'Week off' : d.shift?.name}
                </p>
                {d.shift?.start_time && !d.on_leave && !weekOff && (
                  <p className="text-[9px] font-bold text-slate-500 tabular-nums">
                    {d.shift.start_time}–{d.shift.end_time}
                  </p>
                )}
                {d.shift?.transport_required && !d.on_leave && !weekOff && (
                  <p className="text-[8px] font-bold text-indigo-600 uppercase tracking-widest mt-0.5">
                    Cab/transport arranged
                  </p>
                )}
                {d.holiday_name && (
                  <p className="text-[8px] font-bold text-rose-500 uppercase tracking-widest mt-0.5 truncate">
                    {d.holiday_name}
                  </p>
                )}
              </button>
              {canAct && (
                <div className="flex gap-2 px-2.5 pb-2">
                  <button type="button"
                    aria-label={`Swap shift on ${d.date}`}
                    onClick={() => setSwapDay(d)}
                    className="text-[9px] font-black uppercase tracking-widest text-indigo-600 hover:text-indigo-600">
                    Swap
                  </button>
                  <button type="button"
                    aria-label={`Give away shift on ${d.date}`}
                    onClick={() => setGiveDay(d)}
                    className="text-[9px] font-black uppercase tracking-widest text-indigo-600 hover:text-indigo-600">
                    Give away
                  </button>
                </div>
              )}
              </div>
              );
            })}
          </div>

          {rosterReqs.length > 0 && (
            <div className="mt-4 space-y-2">
              <p className="text-[9px] font-black uppercase tracking-widest text-slate-400">
                My Roster Requests
              </p>
              {rosterReqs.map((r) => (
                <div key={r.id} className="flex items-center justify-between border border-slate-100 rounded-xl p-2.5">
                  <div className="min-w-0">
                    <p className="text-[11px] font-black text-[#0F172A]">
                      {r.work_date} →{' '}
                      {r.requested_week_off ? 'Week off' : r.requested_shift_name || 'Shift'}
                    </p>
                    <p className="text-[10px] text-slate-600 italic truncate">"{r.reason}"</p>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <Badge variant={STATUS_TONE[r.status] || 'neutral'} className="text-[8px] uppercase">
                      {r.status}
                    </Badge>
                    {r.status === 'pending' && (
                      <button
                        type="button"
                        onClick={() => cancelRosterReq(r.id)}
                        className="text-rose-500 hover:text-rose-700"
                        title="Cancel"
                      >
                        <XCircle size={13} />
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>
      ) : null}

      <div role="tablist" aria-label="My schedule sections"
        className="flex gap-1 border-b border-slate-200 overflow-x-auto">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            id={`myshift-tab-${t.id}`}
            aria-selected={tab === t.id}
            aria-controls="myshift-tabpanel"
            onClick={() => {
              setTab(t.id);
              if (t.id === 'swaps' || t.id === 'open') setSelfReload((n) => n + 1);
            }}
            className={cn(
              'px-4 py-2.5 text-[10px] font-black uppercase tracking-widest whitespace-nowrap border-b-2',
              tab === t.id
                ? 'border-indigo-600 text-indigo-700'
                : 'border-transparent text-slate-400 hover:text-slate-600',
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div id="myshift-tabpanel" role="tabpanel" aria-labelledby={`myshift-tab-${tab}`} className="space-y-6">
      {/* Panels stay mounted (hidden) so in-progress state survives tab switches. */}
      <div hidden={tab !== 'availability'}>
        <AvailabilityPanel shifts={templates.map((t: any) => ({ id: t.id, name: t.name }))} />
      </div>
      <div hidden={tab !== 'swaps'}><SwapPanel reloadKey={selfReload} /></div>
      <div hidden={tab !== 'open'}><OpenShiftsPanel reloadKey={selfReload} /></div>
      <div hidden={tab !== 'calendar'}><CalendarFeedCard /></div>
      <div hidden={tab !== 'week'} className="space-y-6">
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

      <MyRegularizations />
      <TeamRegularizations />
      </div>
      </div>

      {swapDay && (
        <SwapDialog
          date={swapDay.date}
          shiftName={swapDay.shift?.name}
          shiftTemplateId={swapDay.shift?.shift_template_id ?? null}
          isWeekOff={swapDay.shift?.name === 'Week off'}
          onClose={() => setSwapDay(null)}
          onDone={() => { setSwapDay(null); setSelfReload((n) => n + 1); setTab('swaps'); }}
        />
      )}
      {giveDay && (
        <GiveawayDialog
          date={giveDay.date}
          shiftName={giveDay.shift?.name}
          onClose={() => setGiveDay(null)}
          onDone={() => { setGiveDay(null); setSelfReload((n) => n + 1); setTab('swaps'); }}
        />
      )}

      {/* Request dialog */}
      {reqOpen && (
        <Dialog open onOpenChange={(o: boolean) => !o && setReqOpen(false)}>
          <DialogContent className="max-w-md">
            <DialogTitle className="flex items-center gap-2 text-base font-black uppercase tracking-tight text-[#0F172A]">
              <Send size={15} className="text-blue-600" /> Request Shift Change
            </DialogTitle>
            <DialogDescription className="text-[10px] font-bold text-slate-500 -mt-1">
              Approved by your manager, then HR
            </DialogDescription>
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

      {/* Roster change dialog (W7) */}
      {rosterReqOpen && (
        <Dialog open onOpenChange={(o: boolean) => !o && setRosterReqOpen(false)}>
          <DialogContent className="max-w-md">
            <DialogTitle className="flex items-center gap-2 text-base font-black uppercase tracking-tight text-[#0F172A]">
              <CalendarDays size={15} className="text-indigo-600" /> Request Roster Change
            </DialogTitle>
            <DialogDescription className="text-[10px] font-bold text-slate-500 -mt-1">
              For {rosterForm.work_date} · approved by your team head
            </DialogDescription>
            <div className="space-y-3 pt-1">
              <label className="flex items-center gap-2 text-[11px] font-bold text-slate-700">
                <input
                  type="checkbox"
                  checked={rosterForm.requested_week_off}
                  onChange={(e) =>
                    setRosterForm({ ...rosterForm, requested_week_off: e.target.checked })
                  }
                />
                Request this day as a week-off
              </label>
              {!rosterForm.requested_week_off && (
                <div className="space-y-1">
                  <label className="text-[9px] font-black uppercase tracking-widest text-slate-400">
                    Preferred shift
                  </label>
                  <select
                    className={inputCls}
                    value={rosterForm.requested_shift_template_id}
                    onChange={(e) =>
                      setRosterForm({
                        ...rosterForm,
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
              )}
              <div className="space-y-1">
                <label className="text-[9px] font-black uppercase tracking-widest text-slate-400">
                  Reason (required)
                </label>
                <textarea
                  className={inputCls + ' h-20 py-2 resize-none'}
                  placeholder="e.g. Doctor's appointment that morning"
                  value={rosterForm.reason}
                  onChange={(e) => setRosterForm({ ...rosterForm, reason: e.target.value })}
                />
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setRosterReqOpen(false)} disabled={rosterBusy}>
                Cancel
              </Button>
              <Button onClick={submitRosterReq} isLoading={rosterBusy}>
                Submit Request
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
    </div>
  );
};
