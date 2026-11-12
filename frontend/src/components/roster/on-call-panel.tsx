import React, { useCallback, useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';
import { PhoneCall, Settings2 } from 'lucide-react';
import { Card, Button, Badge } from '../ui-elements';
import { errMsg } from '../schedule-delegations-utils';
import { fmtDate, inputCls, labelCls } from '../my-schedule/my-schedule-api';
import { InlineConfirm } from '../my-schedule/inline-confirm';
import { onCallApi, type OnCallDay, type OnCallRule } from './on-call-api';
import { OnCallRulesDialog } from './on-call-rules-dialog';

interface Props {
  start: string;
  end: string;
  department: string;
  employees: { id: number; name: string }[];
  isAdmin: boolean;
}

/** On-call / standby assignments for the planner window. */
export const OnCallPanel = ({ start, end, department, employees, isAdmin }: Props) => {
  const [rows, setRows] = useState<OnCallDay[]>([]);
  const [rules, setRules] = useState<OnCallRule[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<number | 'add' | null>(null);
  const [rulesOpen, setRulesOpen] = useState(false);
  const [userId, setUserId] = useState('');
  const [date, setDate] = useState(start);
  const [from, setFrom] = useState('18:00');
  const [to, setTo] = useState('08:00');
  const [ruleId, setRuleId] = useState('');
  const [note, setNote] = useState('');
  const req = useRef(0);

  const load = useCallback(async () => {
    const id = ++req.current;
    setError(null);
    try {
      const [list, rs] = await Promise.all([
        onCallApi.list(start, end, department || undefined),
        onCallApi.rules(),
      ]);
      if (id !== req.current) return;
      setRows(list);
      setRules(rs);
    } catch (e: any) {
      if (id === req.current) setError(errMsg(e, "Couldn't load on-call days"));
    }
  }, [start, end, department]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { setDate((d) => (d < start || d > end ? start : d)); }, [start, end]);

  const active = rules.filter((r) => r.is_active);
  const add = async () => {
    if (!userId) return toast.error('Choose an employee');
    if (!ruleId) return toast.error('Choose a pay rule');
    setBusy('add');
    try {
      await onCallApi.create({
        user_id: Number(userId), work_date: date, start_time: from, end_time: to,
        rule_id: Number(ruleId), note: note.trim() || null,
      });
      toast.success('On-call assigned — employee notified');
      setNote('');
      await load();
    } catch (e: any) {
      toast.error(errMsg(e, 'Could not assign on-call'));
    } finally {
      setBusy(null);
    }
  };
  const remove = async (d: OnCallDay) => {
    setBusy(d.id);
    try {
      await onCallApi.remove(d.id);
      toast.success('On-call removed');
      await load();
    } catch (e: any) {
      toast.error(errMsg(e, 'Could not remove on-call'));
    } finally {
      setBusy(null);
    }
  };

  return (
    <Card className="p-5 border-slate-200 bg-white space-y-4" data-testid="on-call-panel">
      <div className="flex items-center gap-2 flex-wrap">
        <p className="text-[10px] font-black uppercase tracking-widest text-[#0F172A] flex items-center gap-1.5">
          <PhoneCall size={13} className="text-indigo-600" /> On-call · {fmtDate(start)} – {fmtDate(end)}
        </p>
        <span className="flex-1" />
        {isAdmin && (
          <Button size="sm" variant="outline" onClick={() => setRulesOpen(true)} className="gap-1.5">
            <Settings2 className="w-4 h-4" /> Pay rules
          </Button>
        )}
      </div>

      {error && (
        <div role="alert" className="text-sm text-red-700 flex items-center gap-3">
          <span className="flex-1">{error}</span>
          <Button size="sm" variant="outline" onClick={load}>Retry</Button>
        </div>
      )}

      <div className="grid grid-cols-2 md:grid-cols-6 gap-3 items-end">
        <div className="col-span-2 space-y-1">
          <label htmlFor="oc-emp" className={labelCls}>Employee</label>
          <select id="oc-emp" className={inputCls} value={userId} onChange={(e) => setUserId(e.target.value)}>
            <option value="">Select…</option>
            {employees.map((e) => <option key={e.id} value={e.id}>{e.name}</option>)}
          </select>
        </div>
        <div className="space-y-1">
          <label htmlFor="oc-date" className={labelCls}>Date</label>
          <input id="oc-date" type="date" className={inputCls} value={date} min={undefined}
            onChange={(e) => setDate(e.target.value)} />
        </div>
        <div className="space-y-1">
          <label htmlFor="oc-from" className={labelCls}>From</label>
          <input id="oc-from" type="time" className={inputCls} value={from} onChange={(e) => setFrom(e.target.value)} />
        </div>
        <div className="space-y-1">
          <label htmlFor="oc-to" className={labelCls}>To</label>
          <input id="oc-to" type="time" className={inputCls} value={to} onChange={(e) => setTo(e.target.value)} />
        </div>
        <div className="space-y-1">
          <label htmlFor="oc-rule" className={labelCls}>Pay rule</label>
          <select id="oc-rule" className={inputCls} value={ruleId} onChange={(e) => setRuleId(e.target.value)}>
            <option value="">Select…</option>
            {active.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
          </select>
        </div>
        <div className="col-span-2 md:col-span-4 space-y-1">
          <label htmlFor="oc-note" className={labelCls}>Note (optional)</label>
          <input id="oc-note" className={inputCls} maxLength={255} value={note} onChange={(e) => setNote(e.target.value)} />
        </div>
        <div className="col-span-2">
          <Button size="sm" className="h-10 w-full bg-indigo-600 hover:bg-indigo-700 text-white"
            disabled={busy !== null} isLoading={busy === 'add'} onClick={add}>
            Assign on-call
          </Button>
        </div>
      </div>
      {to <= from && (
        <p className="text-[10px] text-slate-500">Ends the next morning (overnight on-call).</p>
      )}
      {isAdmin && active.length === 0 && (
        <p className="text-[11px] text-amber-700">Create a pay rule first (Pay rules).</p>
      )}

      {rows.length === 0 && !error ? (
        <p className="text-[12px] text-slate-500">No one is on call in this period.</p>
      ) : (
        <ul className="divide-y divide-slate-100">
          {rows.map((d) => (
            <li key={d.id} className="py-2 flex items-center gap-3 flex-wrap text-[12px]" data-testid={`on-call-${d.id}`}>
              <span className="font-black text-[#0F172A]">{d.user_name || `User #${d.user_id}`}</span>
              <span className="text-slate-600">{fmtDate(d.work_date)}</span>
              <span className="tabular-nums text-slate-500">
                {d.start_time}–{d.end_time}{d.is_overnight ? ' (+1)' : ''}
              </span>
              {d.rule_name && <Badge variant="info" className="text-[8px] uppercase">{d.rule_name}</Badge>}
              {d.amount != null && <span className="text-slate-500 tabular-nums">₹{d.amount}</span>}
              {d.paid && <Badge variant="success" className="text-[8px] uppercase">paid</Badge>}
              {d.note && <span className="text-slate-400">{d.note}</span>}
              <span className="flex-1" />
              {!d.paid && (
                <InlineConfirm label="Remove" ariaLabel={`Remove on-call ${d.user_name || d.user_id} ${d.work_date}`}
                  busy={busy !== null} onConfirm={() => remove(d)} />
              )}
            </li>
          ))}
        </ul>
      )}
      {isAdmin && <OnCallRulesDialog open={rulesOpen} onClose={() => setRulesOpen(false)} onChanged={load} />}
    </Card>
  );
};
