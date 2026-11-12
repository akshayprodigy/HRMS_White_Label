import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { AlertOctagon, ArrowLeft, RefreshCw, Send } from 'lucide-react';
import { Badge, Button, Card } from '../ui-elements';
import { client } from '../../api/client';
import { ENDPOINTS } from '../../api/endpoints';
import { errMsg, parseServerDate } from '../schedule-delegations-utils';
import { InlineConfirm } from '../my-schedule/inline-confirm';
import { useVisiblePoll } from '../../hooks/use-visible-poll';

type Severity = 'info' | 'warning' | 'critical';
type Audience = 'all' | 'location' | 'department' | 'on_shift';

interface Counts {
  total: number; read: number; acked: number; safe: number;
  need_help: number; no_response: number;
}
interface BroadcastSummary {
  id: number; title: string; message: string; severity: Severity;
  audience: Audience; audience_value: string | null;
  requires_ack: boolean; safety_check: boolean;
  created_by_name: string | null; created_at: string | null;
  closed_at: string | null; counts: Counts;
}
interface Recipient {
  user_id: number; name: string; department: string | null;
  location: string | null; read_at: string | null; acked_at: string | null;
  safety_status: 'safe' | 'need_help' | null; safety_note: string | null;
  responded_at: string | null;
}
interface Detail extends BroadcastSummary {
  recipients: Recipient[]; recipients_total: number;
}
interface Options {
  departments: { value: string; count: number }[];
  locations: { value: string; count: number }[];
}

const SEV_VARIANT: Record<Severity, 'info' | 'warning' | 'error'> = {
  info: 'info', warning: 'warning', critical: 'error',
};
const AUD_LABEL: Record<Audience, string> = {
  all: 'All active employees', location: 'Location',
  department: 'Department', on_shift: 'Currently on shift',
};
const fmt = (iso: string | null) =>
  iso ? parseServerDate(iso).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' }) : '—';
const audienceText = (b: BroadcastSummary) =>
  b.audience_value ? `${AUD_LABEL[b.audience]}: ${b.audience_value}` : AUD_LABEL[b.audience];

const FIELD = 'w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900';

// ------------------------------- compose -------------------------------

const Compose: React.FC<{ onSent: (id: number) => void }> = ({ onSent }) => {
  const [opts, setOpts] = useState<Options>({ departments: [], locations: [] });
  const [title, setTitle] = useState('');
  const [message, setMessage] = useState('');
  const [severity, setSeverity] = useState<Severity>('warning');
  const [audience, setAudience] = useState<Audience>('all');
  const [value, setValue] = useState('');
  const [requiresAck, setRequiresAck] = useState(true);
  const [safetyCheck, setSafetyCheck] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    client.get(ENDPOINTS.BROADCASTS.OPTIONS).then((r) => setOpts(r.data)).catch(() => {});
  }, []);

  const list = audience === 'department' ? opts.departments : audience === 'location' ? opts.locations : [];
  const needsValue = audience === 'department' || audience === 'location';
  const valid = title.trim() && message.trim() && (!needsValue || value);
  const target = needsValue
    ? `${value || '…'} (${list.find((x) => x.value === value)?.count ?? '?'} people)`
    : AUD_LABEL[audience].toLowerCase();

  const send = async () => {
    setSending(true);
    setError(null);
    try {
      const res = await client.post(ENDPOINTS.BROADCASTS.BASE, {
        title, message, severity, audience,
        audience_value: needsValue ? value : null,
        requires_ack: requiresAck, safety_check: safetyCheck,
      });
      setTitle(''); setMessage(''); setConfirming(false);
      onSent(res.data.id);
    } catch (err: any) {
      setError(errMsg(err, 'Failed to send broadcast'));
      setConfirming(false);
    } finally {
      setSending(false);
    }
  };

  return (
    <Card className="p-5 space-y-4">
      <div className="flex items-center gap-2 text-red-600">
        <AlertOctagon className="w-5 h-5" />
        <h2 className="text-sm font-black uppercase tracking-widest">New emergency broadcast</h2>
      </div>
      <div>
        <label htmlFor="bc-title" className="text-xs font-bold text-slate-500">Title</label>
        <input id="bc-title" className={FIELD} value={title} maxLength={200}
          onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Fire drill / Severe weather" />
      </div>
      <div>
        <label htmlFor="bc-msg" className="text-xs font-bold text-slate-500">Message</label>
        <textarea id="bc-msg" className={FIELD} rows={3} maxLength={900} value={message}
          onChange={(e) => setMessage(e.target.value)} placeholder="What should people do?" />
      </div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <div>
          <label htmlFor="bc-sev" className="text-xs font-bold text-slate-500">Severity</label>
          <select id="bc-sev" className={FIELD} value={severity}
            onChange={(e) => setSeverity(e.target.value as Severity)}>
            <option value="info">Info (banner)</option>
            <option value="warning">Warning (banner)</option>
            <option value="critical">Critical (blocking modal)</option>
          </select>
        </div>
        <div>
          <label htmlFor="bc-aud" className="text-xs font-bold text-slate-500">Audience</label>
          <select id="bc-aud" className={FIELD} value={audience}
            onChange={(e) => { setAudience(e.target.value as Audience); setValue(''); }}>
            {(Object.keys(AUD_LABEL) as Audience[]).map((a) => (
              <option key={a} value={a}>{AUD_LABEL[a]}</option>
            ))}
          </select>
        </div>
        {needsValue && (
          <div>
            <label htmlFor="bc-val" className="text-xs font-bold text-slate-500">
              {audience === 'department' ? 'Department' : 'Location'}
            </label>
            <select id="bc-val" className={FIELD} value={value} onChange={(e) => setValue(e.target.value)}>
              <option value="">Select…</option>
              {list.map((x) => (
                <option key={x.value} value={x.value}>{x.value} ({x.count})</option>
              ))}
            </select>
          </div>
        )}
      </div>
      <div className="flex flex-wrap gap-6 text-sm text-slate-700">
        <label className="flex items-center gap-2">
          <input type="checkbox" checked={requiresAck} onChange={(e) => setRequiresAck(e.target.checked)} />
          Require acknowledgement
        </label>
        <label className="flex items-center gap-2">
          <input type="checkbox" checked={safetyCheck} onChange={(e) => setSafetyCheck(e.target.checked)} />
          Ask people to mark themselves safe
        </label>
      </div>
      {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
      {!confirming ? (
        <Button variant="danger" disabled={!valid} onClick={() => setConfirming(true)}>
          <Send className="w-4 h-4 mr-2" /> Review &amp; send
        </Button>
      ) : (
        <div className="rounded-lg border border-red-200 bg-red-50 p-3 space-y-2">
          <p className="text-sm text-red-800">
            Send now to <b>{target}</b> by in-app, email and SMS. Quiet hours and notification
            preferences are bypassed. This cannot be recalled.
          </p>
          <div className="flex gap-2">
            <Button variant="danger" isLoading={sending} onClick={send}>Send broadcast</Button>
            <Button variant="outline" onClick={() => setConfirming(false)}>Cancel</Button>
          </div>
        </div>
      )}
    </Card>
  );
};

// ------------------------------- detail -------------------------------

type Filter = '' | 'need_help' | 'no_response' | 'safe';
const FILTERS: { id: Filter; label: string }[] = [
  { id: '', label: 'All' }, { id: 'need_help', label: 'Need help' },
  { id: 'no_response', label: 'No response' }, { id: 'safe', label: 'Safe' },
];
const PAGE_SIZE = 25;

const DetailView: React.FC<{ id: number; onBack: () => void }> = ({ id, onBack }) => {
  const [data, setData] = useState<Detail | null>(null);
  const [filter, setFilter] = useState<Filter>('');
  const [page, setPage] = useState(1);
  const [error, setError] = useState<string | null>(null);
  const [closing, setClosing] = useState(false);

  const load = useCallback(async () => {
    try {
      const res = await client.get(ENDPOINTS.BROADCASTS.DETAIL(id), {
        params: { filter: filter || undefined, page, page_size: PAGE_SIZE },
      });
      setData(res.data);
      setError(null);
    } catch (err: any) {
      setError(errMsg(err, 'Failed to load broadcast'));
    }
  }, [id, filter, page]);
  // live counts: every 15 s while the tab is visible (refetches on filter/page change)
  useVisiblePoll(load, 15_000);

  const close = async () => {
    setClosing(true);
    try {
      await client.post(ENDPOINTS.BROADCASTS.CLOSE(id));
      await load();
    } catch (err: any) {
      setError(errMsg(err, 'Failed to close broadcast'));
    } finally {
      setClosing(false);
    }
  };

  const pages = data ? Math.max(1, Math.ceil(data.recipients_total / PAGE_SIZE)) : 1;
  const tiles = data ? [
    { k: 'Recipients', v: data.counts.total, c: 'text-slate-900' },
    { k: 'Read', v: data.counts.read, c: 'text-slate-900' },
    { k: 'Acknowledged', v: data.counts.acked, c: 'text-blue-700' },
    { k: 'Safe', v: data.counts.safe, c: 'text-green-700' },
    { k: 'Need help', v: data.counts.need_help, c: 'text-red-700' },
    { k: 'No response', v: data.counts.no_response, c: 'text-amber-700' },
  ] : [];

  return (
    <div className="space-y-4">
      <button type="button" onClick={onBack}
        className="flex items-center gap-1 text-sm font-semibold text-slate-600 hover:text-slate-900">
        <ArrowLeft className="w-4 h-4" /> All broadcasts
      </button>
      {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
      {data && (
        <>
          <Card className="p-5">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <Badge variant={SEV_VARIANT[data.severity]}>{data.severity}</Badge>
                  <Badge variant={data.closed_at ? 'neutral' : 'success'}>
                    {data.closed_at ? 'Closed' : 'Active'}
                  </Badge>
                </div>
                <h2 className="text-lg font-black text-slate-900">{data.title}</h2>
                <p className="text-sm text-slate-600 whitespace-pre-wrap break-words">{data.message}</p>
                <p className="text-xs text-slate-400 mt-2">
                  {audienceText(data)} · sent {fmt(data.created_at)} by {data.created_by_name ?? '—'}
                </p>
              </div>
              <div className="flex items-center gap-3">
                <button type="button" onClick={load} aria-label="Refresh"
                  className="text-slate-500 hover:text-slate-900"><RefreshCw className="w-4 h-4" /></button>
                {!data.closed_at && (
                  <InlineConfirm label="Close broadcast" confirmLabel="Close" busy={closing}
                    onConfirm={close} ariaLabel="close broadcast" />
                )}
              </div>
            </div>
          </Card>
          <div className="grid grid-cols-2 md:grid-cols-6 gap-3" data-testid="bc-counts">
            {tiles.map((t) => (
              <Card key={t.k} className="p-3 text-center">
                <p className={`text-2xl font-black ${t.c}`}>{t.v}</p>
                <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400">{t.k}</p>
              </Card>
            ))}
          </div>
          <Card className="p-4">
            <div className="flex flex-wrap gap-2 mb-3">
              {FILTERS.map((f) => (
                <button key={f.id} type="button"
                  onClick={() => { setFilter(f.id); setPage(1); }}
                  className={`px-3 py-1 rounded-full text-xs font-bold border ${
                    filter === f.id ? 'bg-slate-900 text-white border-slate-900'
                      : 'bg-white text-slate-600 border-slate-300'}`}>
                  {f.label}
                </button>
              ))}
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-[10px] uppercase tracking-widest text-slate-400">
                    <th className="py-2 pr-3">Employee</th><th className="pr-3">Dept / location</th>
                    <th className="pr-3">Status</th><th className="pr-3">Ack</th><th>Note</th>
                  </tr>
                </thead>
                <tbody>
                  {data.recipients.map((r) => (
                    <tr key={r.user_id} className="border-t border-slate-100">
                      <td className="py-2 pr-3 font-semibold text-slate-900">{r.name}</td>
                      <td className="pr-3 text-slate-500">{[r.department, r.location].filter(Boolean).join(' / ') || '—'}</td>
                      <td className="pr-3">
                        {r.safety_status === 'need_help' ? <Badge variant="error">Needs help</Badge>
                          : r.safety_status === 'safe' ? <Badge variant="success">Safe</Badge>
                          : r.read_at ? <Badge variant="info">Read</Badge>
                          : <Badge variant="warning">No response</Badge>}
                      </td>
                      <td className="pr-3 text-slate-500">{r.acked_at ? fmt(r.acked_at) : '—'}</td>
                      <td className="text-slate-600">{r.safety_note ?? ''}</td>
                    </tr>
                  ))}
                  {data.recipients.length === 0 && (
                    <tr><td colSpan={5} className="py-6 text-center text-slate-400">No recipients in this view</td></tr>
                  )}
                </tbody>
              </table>
            </div>
            {pages > 1 && (
              <div className="flex items-center justify-end gap-3 mt-3 text-sm text-slate-600">
                <Button size="sm" variant="outline" disabled={page <= 1} onClick={() => setPage(page - 1)}>Prev</Button>
                <span>Page {page} of {pages}</span>
                <Button size="sm" variant="outline" disabled={page >= pages} onClick={() => setPage(page + 1)}>Next</Button>
              </div>
            )}
          </Card>
        </>
      )}
    </div>
  );
};

// -------------------------------- page --------------------------------

export const EmergencyBroadcastPage: React.FC = () => {
  const [selected, setSelected] = useState<number | null>(null);
  const [items, setItems] = useState<BroadcastSummary[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await client.get(ENDPOINTS.BROADCASTS.BASE, { params: { page_size: 50 } });
      setItems(res.data.items);
      setError(null);
    } catch (err: any) {
      setError(errMsg(err, 'Failed to load broadcasts'));
    }
  }, []);
  useVisiblePoll(load, 15_000, selected === null);

  const active = useMemo(() => items.filter((b) => !b.closed_at).length, [items]);

  if (selected !== null) {
    return <div className="p-6 max-w-5xl mx-auto"><DetailView id={selected} onBack={() => setSelected(null)} /></div>;
  }
  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">
      <Compose onSent={(id) => { load(); setSelected(id); }} />
      <Card className="p-5">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-black uppercase tracking-widest text-slate-500">
            History {active > 0 && <span className="text-red-600">· {active} active</span>}
          </h2>
        </div>
        {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
        <div className="divide-y divide-slate-100">
          {items.map((b) => (
            <button key={b.id} type="button" onClick={() => setSelected(b.id)}
              className="w-full text-left py-3 flex flex-wrap items-center justify-between gap-2 hover:bg-slate-50">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <Badge variant={SEV_VARIANT[b.severity]}>{b.severity}</Badge>
                  <span className="font-semibold text-slate-900 truncate">{b.title}</span>
                  {b.closed_at && <Badge variant="neutral">Closed</Badge>}
                </div>
                <p className="text-xs text-slate-400 mt-1">{audienceText(b)} · {fmt(b.created_at)}</p>
              </div>
              <div className="text-xs text-slate-600 flex gap-3">
                <span>{b.counts.total} sent</span>
                <span>{b.counts.acked} acked</span>
                <span className="text-green-700">{b.counts.safe} safe</span>
                <span className={b.counts.need_help ? 'text-red-700 font-bold' : ''}>{b.counts.need_help} need help</span>
                <span className="text-amber-700">{b.counts.no_response} pending</span>
              </div>
            </button>
          ))}
          {items.length === 0 && <p className="py-6 text-center text-sm text-slate-400">No broadcasts yet</p>}
        </div>
      </Card>
    </div>
  );
};
