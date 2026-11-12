import React, { useCallback, useEffect, useState } from 'react';
import { Plane, Search, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { Card, Button, Badge } from './ui-elements';
import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';
import { errMsg, todayIso } from './schedule-delegations-utils';

type Candidate = { id: number; name: string; email: string };
type Delegation = {
  id: number;
  user_name?: string | null;
  delegate_id: number;
  delegate_name?: string | null;
  starts_on: string;
  ends_on?: string | null;
  only_when_on_leave: boolean;
  note?: string | null;
  status: string;
};

const fieldCls =
  'w-full h-10 px-3 rounded-lg border border-slate-200 text-sm text-[#0F172A] ' +
  'focus:outline-none focus:ring-2 focus:ring-blue-500';

const STATUS_LABEL: Record<string, string> = {
  active: 'Active now',
  scheduled: 'Scheduled',
  waiting_for_leave: 'Waiting for approved leave',
  expired: 'Expired',
  revoked: 'Revoked',
  inactive: 'Inactive',
};

export const OutOfOfficeCard = () => {
  const [mine, setMine] = useState<Delegation[]>([]);
  const [toMe, setToMe] = useState<Delegation[]>([]);
  const [q, setQ] = useState('');
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [picked, setPicked] = useState<Candidate | null>(null);
  const [startsOn, setStartsOn] = useState(todayIso());
  const [endsOn, setEndsOn] = useState('');
  const [onlyOnLeave, setOnlyOnLeave] = useState(false);
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const res = await client.get(ENDPOINTS.APPROVALS.MY_DELEGATIONS);
      setMine(res.data?.mine ?? []);
      setToMe(res.data?.delegated_to_me ?? []);
    } catch (e) {
      toast.error(errMsg(e, 'Request failed'));
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    if (picked || q.trim().length < 2) { setCandidates([]); return; }
    const t = setTimeout(async () => {
      try {
        const res = await client.get(
          `${ENDPOINTS.APPROVALS.MY_DELEGATIONS}/candidates?q=${encodeURIComponent(q.trim())}`,
        );
        setCandidates(res.data ?? []);
      } catch {
        setCandidates([]);
      }
    }, 250);
    return () => clearTimeout(t);
  }, [q, picked]);

  const create = async () => {
    if (!picked) { toast.error('Pick a delegate'); return; }
    if (endsOn && endsOn < startsOn) { toast.error('End date is before the start date'); return; }
    setBusy(true);
    try {
      await client.post(ENDPOINTS.APPROVALS.MY_DELEGATIONS, {
        delegate_id: picked.id,
        starts_on: startsOn || null,
        ends_on: endsOn || null,
        only_when_on_leave: onlyOnLeave,
        note: note.trim() || null,
      });
      toast.success(`${picked.name} will cover your approvals`);
      setPicked(null); setQ(''); setEndsOn(''); setNote(''); setOnlyOnLeave(false);
      await load();
    } catch (e) {
      toast.error(errMsg(e, 'Request failed'));
    } finally {
      setBusy(false);
    }
  };

  const revoke = async (id: number) => {
    try {
      await client.delete(ENDPOINTS.APPROVALS.MY_DELEGATION(id));
      toast.success('Delegation revoked');
      await load();
    } catch (e) {
      toast.error(errMsg(e, 'Request failed'));
    }
  };

  return (
    <section className="space-y-6" data-testid="out-of-office-card">
      <div>
        <h3 className="text-[10px] font-black text-[#94A3B8] uppercase tracking-[0.2em] flex items-center gap-2">
          <Plane size={14} /> Out of office
        </h3>
        <p className="text-[11px] font-bold text-slate-500 mt-2">
          While you are away, your delegate sees your pending approvals (marked
          &quot;acting for you&quot;) and can approve or reject them. They cannot
          approve their own requests, and delegation does not pass on to anyone
          else.
        </p>
      </div>

      <Card className="p-5 border-slate-200 bg-white space-y-4">
        <div className="space-y-1 relative">
          <label className="text-[9px] font-black uppercase tracking-widest text-slate-400" htmlFor="ooo-delegate">
            Delegate
          </label>
          {picked ? (
            <div className="flex items-center gap-2">
              <Badge variant="info" className="text-[10px] px-3 h-7 font-black">
                {picked.name} ({picked.email})
              </Badge>
              <button
                type="button"
                className="text-[10px] font-black uppercase tracking-widest text-slate-400 hover:text-slate-600"
                onClick={() => { setPicked(null); setQ(''); }}
              >
                Change
              </button>
            </div>
          ) : (
            <>
              <div className="relative">
                <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
                <input
                  id="ooo-delegate"
                  className={fieldCls + ' pl-9'}
                  placeholder="Search colleagues by name or email"
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                />
              </div>
              {candidates.length > 0 && (
                <div className="border border-slate-200 rounded-lg bg-white divide-y divide-slate-100 max-h-40 overflow-y-auto">
                  {candidates.map((c) => (
                    <button
                      key={c.id}
                      type="button"
                      data-testid={`ooo-candidate-${c.id}`}
                      className="w-full text-left px-3 py-2 text-xs font-bold text-slate-700 hover:bg-slate-50"
                      onClick={() => { setPicked(c); setCandidates([]); }}
                    >
                      {c.name} <span className="text-slate-400">{c.email}</span>
                    </button>
                  ))}
                </div>
              )}
            </>
          )}
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div className="space-y-1">
            <label className="text-[9px] font-black uppercase tracking-widest text-slate-400" htmlFor="ooo-from">From</label>
            <input id="ooo-from" type="date" className={fieldCls} value={startsOn} onChange={(e) => setStartsOn(e.target.value)} />
          </div>
          <div className="space-y-1">
            <label className="text-[9px] font-black uppercase tracking-widest text-slate-400" htmlFor="ooo-to">Until (optional)</label>
            <input id="ooo-to" type="date" className={fieldCls} value={endsOn} min={startsOn} onChange={(e) => setEndsOn(e.target.value)} />
          </div>
        </div>

        <label className="flex items-center gap-2 text-xs font-bold text-slate-600">
          <input
            type="checkbox"
            checked={onlyOnLeave}
            onChange={(e) => setOnlyOnLeave(e.target.checked)}
            className="w-4 h-4 accent-blue-600"
          />
          Only on days I have approved leave (standing delegate)
        </label>

        <div className="space-y-1">
          <label className="text-[9px] font-black uppercase tracking-widest text-slate-400" htmlFor="ooo-note">Note (optional)</label>
          <input id="ooo-note" className={fieldCls} maxLength={255} value={note} onChange={(e) => setNote(e.target.value)} />
        </div>

        <div className="flex justify-end">
          <Button onClick={create} isLoading={busy} disabled={!picked}>
            Set delegate
          </Button>
        </div>
      </Card>

      <div className="space-y-2">
        <h4 className="text-[10px] font-black uppercase tracking-widest text-slate-400">My delegations</h4>
        {mine.length === 0 && (
          <p className="text-xs font-bold text-slate-400">No delegate set.</p>
        )}
        {mine.map((d) => (
          <div key={d.id} className="flex items-center justify-between gap-3 border border-slate-200 rounded-xl px-4 py-3" data-testid={`ooo-row-${d.id}`}>
            <div className="min-w-0">
              <p className="text-sm font-black text-[#0F172A] truncate">{d.delegate_name}</p>
              <p className="text-[10px] font-bold text-slate-500">
                {d.starts_on} → {d.ends_on || 'open ended'}
                {d.only_when_on_leave ? ' · only while on approved leave' : ''}
                {d.note ? ` · ${d.note}` : ''}
              </p>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <Badge variant={d.status === 'active' ? 'success' : 'neutral'} className="text-[9px] px-2 h-5 font-black uppercase tracking-widest">
                {STATUS_LABEL[d.status] ?? d.status}
              </Badge>
              <button
                type="button"
                aria-label="Revoke delegation"
                className="p-2 rounded-lg text-red-500 hover:bg-red-50"
                onClick={() => revoke(d.id)}
              >
                <Trash2 size={14} />
              </button>
            </div>
          </div>
        ))}
      </div>

      {toMe.length > 0 && (
        <div className="space-y-2">
          <h4 className="text-[10px] font-black uppercase tracking-widest text-slate-400">Covering for</h4>
          {toMe.map((d) => (
            <div key={d.id} className="border border-slate-200 rounded-xl px-4 py-3">
              <p className="text-sm font-black text-[#0F172A]">{d.user_name}</p>
              <p className="text-[10px] font-bold text-slate-500">
                {d.starts_on} → {d.ends_on || 'open ended'} · {STATUS_LABEL[d.status] ?? d.status}
              </p>
            </div>
          ))}
        </div>
      )}
    </section>
  );
};
