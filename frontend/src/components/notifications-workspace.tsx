/**
 * Notifications workspace (Section L).
 *
 * Four tabs:
 *   1. My Preferences    — per-category channel toggles + quiet hours
 *   2. Providers         — HR: provider status + test-send
 *   3. Templates         — HR: template CRUD + seed
 *   4. Delivery Log      — HR: search + resend + dead-letter
 */
import React, { useEffect, useMemo, useState } from 'react';
import {
  Bell, Radio, FileEdit, ScrollText, RefreshCw, Play,
  Send, ShieldAlert, CheckCircle2, XCircle, AlertTriangle,
} from 'lucide-react';
import { toast } from 'sonner';
import {
  Card, Button, Badge, cn, errMsg, EmptyState, Loading, StatusChip,
} from './ui-elements';
import { Input } from './ui/input';
import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';

const TABS = [
  { id: 'my-prefs',   label: 'My Preferences', icon: Bell },
  { id: 'providers',  label: 'Providers',      icon: Radio },
  { id: 'templates',  label: 'Templates',      icon: FileEdit },
  { id: 'log',        label: 'Delivery Log',   icon: ScrollText },
] as const;
type TabId = typeof TABS[number]['id'];

const CATEGORIES = [
  'approvals', 'leave', 'overtime', 'payroll',
  'performance', 'expense', 'statutory', 'other',
];
const CHANNELS = ['email', 'sms'];

// ---------------------------------------------------------------------------
// Tab 1: My preferences
// ---------------------------------------------------------------------------

const MyPrefsTab: React.FC = () => {
  const [prefs, setPrefs] = useState<any[]>([]);
  const [quiet, setQuiet] = useState<any>({ quiet_from: null, quiet_to: null, hard_opt_out: false });
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  const refresh = async () => {
    setLoading(true);
    try {
      const [p, q] = await Promise.all([
        client.get(ENDPOINTS.NOTIFICATIONS.MY_PREFS),
        client.get(ENDPOINTS.NOTIFICATIONS.MY_QUIET),
      ]);
      setPrefs(p.data || []);
      setQuiet(q.data || { quiet_from: null, quiet_to: null, hard_opt_out: false });
    } catch (e: any) {
      toast.error(errMsg(e, 'Failed to load preferences'));
    } finally { setLoading(false); }
  };
  useEffect(() => { refresh(); }, []);

  const getPref = (category: string, channel: string) => {
    return prefs.find(p => p.category === category && p.channel === channel);
  };
  const enabled = (category: string, channel: string): boolean => {
    const p = getPref(category, channel);
    if (p) return !!p.enabled;
    // Defaults roughly match backend DEFAULT_ENABLED_CHANNELS_BY_CATEGORY.
    const defaults: Record<string, string[]> = {
      approvals: ['email'], leave: ['email'],
      payroll: ['email'], performance: ['email'],
      expense: ['email'], statutory: ['email'],
    };
    return (defaults[category] || []).includes(channel);
  };
  const setEnabled = (category: string, channel: string, value: boolean) => {
    const existing = getPref(category, channel);
    if (existing) {
      setPrefs(prefs.map(p => p === existing ? { ...p, enabled: value } : p));
    } else {
      setPrefs([...prefs, { category, channel, enabled: value, digest_cadence: 'immediate' }]);
    }
  };
  const setDigest = (category: string, channel: string, cadence: string) => {
    const existing = getPref(category, channel);
    if (existing) {
      setPrefs(prefs.map(p => p === existing ? { ...p, digest_cadence: cadence } : p));
    } else {
      setPrefs([...prefs, { category, channel, enabled: enabled(category, channel), digest_cadence: cadence }]);
    }
  };

  const save = async () => {
    setBusy(true);
    try {
      await client.put(ENDPOINTS.NOTIFICATIONS.MY_PREFS,
        prefs.map(p => ({
          category: p.category, channel: p.channel,
          enabled: p.enabled, digest_cadence: p.digest_cadence || 'immediate',
        })),
      );
      await client.put(ENDPOINTS.NOTIFICATIONS.MY_QUIET, {
        quiet_from: quiet.quiet_from || null,
        quiet_to: quiet.quiet_to || null,
        hard_opt_out: !!quiet.hard_opt_out,
      });
      toast.success('Preferences saved');
      await refresh();
    } catch (e: any) {
      toast.error(errMsg(e, 'Save failed'));
    } finally { setBusy(false); }
  };

  if (loading) return <div className="text-slate-400 py-4">Loading…</div>;

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold">My notification preferences</h2>
        <p className="text-sm text-slate-500">
          In-app notifications always fire. Email and SMS opt-in per category.
        </p>
      </div>

      <Card>
        <table className="w-full text-sm">
          <thead className="text-xs uppercase text-slate-500 border-b">
            <tr>
              <th className="text-left px-3 py-2">Category</th>
              <th className="text-center px-3 py-2">Email</th>
              <th className="text-center px-3 py-2">Email digest</th>
              <th className="text-center px-3 py-2">SMS</th>
              <th className="text-center px-3 py-2">SMS digest</th>
            </tr>
          </thead>
          <tbody>
            {CATEGORIES.map(c => (
              <tr key={c} className="border-b">
                <td className="px-3 py-2 capitalize">{c}</td>
                {CHANNELS.flatMap(ch => [
                  <td key={ch + '-en'} className="text-center px-3 py-2">
                    <input type="checkbox"
                      checked={enabled(c, ch)}
                      onChange={e => setEnabled(c, ch, e.target.checked)} />
                  </td>,
                  <td key={ch + '-dg'} className="text-center px-3 py-2">
                    <select className="border border-slate-300 rounded px-1 py-0.5 text-xs"
                      value={getPref(c, ch)?.digest_cadence || 'immediate'}
                      onChange={e => setDigest(c, ch, e.target.value)}>
                      <option value="immediate">immediate</option>
                      <option value="hourly">hourly</option>
                      <option value="daily">daily</option>
                    </select>
                  </td>,
                ])}
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <Card className="p-4 space-y-3">
        <div className="font-medium text-sm">Quiet hours & opt-out</div>
        <div className="grid grid-cols-3 gap-3 items-end">
          <div>
            <label className="text-xs text-slate-500">Quiet from</label>
            <Input type="time" value={quiet.quiet_from || ''}
              onChange={e => setQuiet({ ...quiet, quiet_from: e.target.value })} />
          </div>
          <div>
            <label className="text-xs text-slate-500">Quiet to</label>
            <Input type="time" value={quiet.quiet_to || ''}
              onChange={e => setQuiet({ ...quiet, quiet_to: e.target.value })} />
          </div>
          <label className="text-sm flex items-center gap-2 mt-4">
            <input type="checkbox" checked={!!quiet.hard_opt_out}
              onChange={e => setQuiet({ ...quiet, hard_opt_out: e.target.checked })} />
            Hard opt-out from all email/SMS
          </label>
        </div>
      </Card>

      <div className="flex justify-end">
        <Button onClick={save} disabled={busy}>{busy ? 'Saving…' : 'Save preferences'}</Button>
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// Tab 2: Providers + test-send
// ---------------------------------------------------------------------------

const ProvidersTab: React.FC = () => {
  const [status, setStatus] = useState<any | null>(null);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState({
    channel: 'email', to: '', subject: 'ERP test',
    body: 'Section L test — please ignore.',
    dlt_template_id: '',
  });
  const [busy, setBusy] = useState(false);

  const refresh = async () => {
    setLoading(true);
    try {
      const r = await client.get(ENDPOINTS.NOTIFICATIONS.PROVIDER_STATUS);
      setStatus(r.data);
    } catch (e: any) {
      toast.error(errMsg(e, 'Failed to load providers'));
    } finally { setLoading(false); }
  };
  useEffect(() => { refresh(); }, []);

  const send = async () => {
    if (!form.to.trim()) { toast.error('Recipient required'); return; }
    setBusy(true);
    try {
      const r = await client.post(ENDPOINTS.NOTIFICATIONS.TEST_SEND, {
        channel: form.channel, to: form.to,
        subject: form.subject, body: form.body,
        dlt_template_id: form.dlt_template_id || null,
      });
      if (r.data.ok) toast.success(`Sent — id ${r.data.message_id || 'ok'}`);
      else toast.error(r.data.error || 'Send failed');
    } catch (e: any) {
      toast.error(errMsg(e, 'Send failed'));
    } finally { setBusy(false); }
  };

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-start">
        <div>
          <h2 className="text-lg font-semibold">Provider status</h2>
          <p className="text-sm text-slate-500">
            Boots as log-provider by default. Set env vars to enable real providers.
          </p>
        </div>
        <Button variant="secondary" onClick={refresh}>
          <RefreshCw size={14} className="mr-1" />Refresh
        </Button>
      </div>

      {loading || !status ? (
        <div className="text-slate-400 py-4">Loading…</div>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3">
            {['email', 'sms'].map(ch => {
              const p = status[ch];
              const dev = p.is_dev;
              return (
                <Card key={ch} className="p-4">
                  <div className="flex items-center justify-between">
                    <div className="font-medium capitalize">{ch}</div>
                    <Badge className={cn(
                      'border',
                      dev
                        ? 'bg-amber-100 text-amber-700 border-amber-300'
                        : 'bg-green-100 text-green-700 border-green-300',
                    )}>
                      {dev ? 'log (dev)' : p.provider}
                    </Badge>
                  </div>
                  <div className="text-xs text-slate-500 mt-1">
                    Provider: <span className="font-mono">{p.provider}</span>
                  </div>
                </Card>
              );
            })}
          </div>
          <div className="text-xs text-slate-500 mt-2">{status.hint}</div>
        </>
      )}

      <Card className="p-4 space-y-3">
        <div className="font-medium text-sm">Test send</div>
        <div className="grid grid-cols-4 gap-3">
          <div>
            <label className="text-xs text-slate-500">Channel</label>
            <select className="w-full border border-slate-300 rounded px-2 py-1.5 text-sm"
              value={form.channel} onChange={e => setForm({ ...form, channel: e.target.value })}>
              <option value="email">email</option>
              <option value="sms">sms</option>
            </select>
          </div>
          <div className="col-span-2">
            <label className="text-xs text-slate-500">Recipient ({form.channel === 'sms' ? 'phone' : 'email'})</label>
            <Input value={form.to} onChange={e => setForm({ ...form, to: e.target.value })} />
          </div>
          <div>
            <label className="text-xs text-slate-500">Subject (email)</label>
            <Input value={form.subject} onChange={e => setForm({ ...form, subject: e.target.value })} />
          </div>
          <div className="col-span-3">
            <label className="text-xs text-slate-500">Body</label>
            <Input value={form.body} onChange={e => setForm({ ...form, body: e.target.value })} />
          </div>
          <div>
            <label className="text-xs text-slate-500">DLT template id (SMS)</label>
            <Input value={form.dlt_template_id}
              onChange={e => setForm({ ...form, dlt_template_id: e.target.value })} />
          </div>
        </div>
        <div className="flex justify-end">
          <Button onClick={send} disabled={busy}>
            <Send size={14} className="mr-1" />{busy ? 'Sending…' : 'Test send'}
          </Button>
        </div>
      </Card>
    </div>
  );
};

// ---------------------------------------------------------------------------
// Tab 3: Templates
// ---------------------------------------------------------------------------

const TemplatesTab: React.FC = () => {
  const [rows, setRows] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [edit, setEdit] = useState<any | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = async () => {
    setLoading(true);
    try {
      const r = await client.get(ENDPOINTS.NOTIFICATIONS.TEMPLATES);
      setRows(r.data || []);
    } catch (e: any) {
      toast.error(errMsg(e, 'Failed to load templates'));
    } finally { setLoading(false); }
  };
  useEffect(() => { refresh(); }, []);

  const seed = async () => {
    try {
      const r = await client.post(ENDPOINTS.NOTIFICATIONS.TEMPLATES_SEED);
      toast.success(`Seeded ${r.data.inserted} new templates`);
      await refresh();
    } catch (e: any) {
      toast.error(errMsg(e, 'Seed failed'));
    }
  };

  const save = async () => {
    if (!edit) return;
    setBusy(true);
    try {
      const payload = {
        event_type: edit.event_type,
        channel: edit.channel,
        category: edit.category || 'other',
        subject: edit.subject || null,
        body_html: edit.body_html || null,
        body_text: edit.body_text || '',
        dlt_template_id: edit.dlt_template_id || null,
        is_sensitive: !!edit.is_sensitive,
        is_active: !!edit.is_active,
      };
      if (edit.id) {
        await client.put(ENDPOINTS.NOTIFICATIONS.TEMPLATE_DETAIL(edit.id), payload);
      } else {
        await client.post(ENDPOINTS.NOTIFICATIONS.TEMPLATES, payload);
      }
      toast.success('Saved');
      setEdit(null);
      await refresh();
    } catch (e: any) {
      toast.error(errMsg(e, 'Save failed'));
    } finally { setBusy(false); }
  };

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-start">
        <div>
          <h2 className="text-lg font-semibold">Notification templates</h2>
          <p className="text-sm text-slate-500">
            <code className="bg-slate-100 px-1">{'{name}'}</code> placeholders
            render from context. Sensitive templates strip money keys automatically.
            SMS templates need a DLT template id for real sends.
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="secondary" onClick={seed}>
            Seed starter set
          </Button>
          <Button onClick={() => setEdit({
            event_type: '', channel: 'email', category: 'other',
            body_text: '', is_sensitive: false, is_active: true,
          })}>
            New template
          </Button>
        </div>
      </div>

      {loading ? (
        <div className="text-slate-400 py-4">Loading…</div>
      ) : (
        <Card>
          <table className="w-full text-sm">
            <thead className="text-xs uppercase text-slate-500 border-b">
              <tr>
                <th className="text-left px-3 py-2">Event</th>
                <th className="text-left px-3 py-2">Channel</th>
                <th className="text-left px-3 py-2">Category</th>
                <th className="text-left px-3 py-2">Sensitive</th>
                <th className="text-left px-3 py-2">Active</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {rows.map(r => (
                <tr key={r.id} className="border-b hover:bg-slate-50">
                  <td className="px-3 py-2 font-mono text-xs">{r.event_type}</td>
                  <td className="px-3 py-2">{r.channel}</td>
                  <td className="px-3 py-2 text-slate-500">{r.category}</td>
                  <td className="px-3 py-2">{r.is_sensitive ? '🔒' : ''}</td>
                  <td className="px-3 py-2">{r.is_active ? '✓' : '✗'}</td>
                  <td className="px-3 py-2 text-right">
                    <Button size="sm" variant="secondary" onClick={() => setEdit(r)}>Edit</Button>
                  </td>
                </tr>
              ))}
              {!rows.length && (
                <tr><td colSpan={6} className="text-center text-slate-400 py-6">
                  No templates yet — click "Seed starter set".
                </td></tr>
              )}
            </tbody>
          </table>
        </Card>
      )}

      {edit && (
        <Card className="p-4 space-y-3">
          <div className="font-medium">{edit.id ? 'Edit' : 'New'} template</div>
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="text-xs text-slate-500">Event type</label>
              <Input value={edit.event_type}
                onChange={e => setEdit({ ...edit, event_type: e.target.value })} />
            </div>
            <div>
              <label className="text-xs text-slate-500">Channel</label>
              <select className="w-full border border-slate-300 rounded px-2 py-1.5 text-sm"
                value={edit.channel} onChange={e => setEdit({ ...edit, channel: e.target.value })}>
                <option value="email">email</option>
                <option value="sms">sms</option>
              </select>
            </div>
            <div>
              <label className="text-xs text-slate-500">Category</label>
              <Input value={edit.category}
                onChange={e => setEdit({ ...edit, category: e.target.value })} />
            </div>
            <div className="col-span-3">
              <label className="text-xs text-slate-500">Subject</label>
              <Input value={edit.subject || ''}
                onChange={e => setEdit({ ...edit, subject: e.target.value })} />
            </div>
            <div className="col-span-3">
              <label className="text-xs text-slate-500">Body (plain text)</label>
              <textarea className="w-full border border-slate-300 rounded px-2 py-1.5 text-sm min-h-[80px]"
                value={edit.body_text}
                onChange={e => setEdit({ ...edit, body_text: e.target.value })} />
            </div>
            <div className="col-span-3">
              <label className="text-xs text-slate-500">Body (HTML)</label>
              <textarea className="w-full border border-slate-300 rounded px-2 py-1.5 text-sm min-h-[80px] font-mono text-xs"
                value={edit.body_html || ''}
                onChange={e => setEdit({ ...edit, body_html: e.target.value })} />
            </div>
            <div>
              <label className="text-xs text-slate-500">DLT template id (SMS)</label>
              <Input value={edit.dlt_template_id || ''}
                onChange={e => setEdit({ ...edit, dlt_template_id: e.target.value })} />
            </div>
            <label className="text-xs flex items-center gap-2 mt-4">
              <input type="checkbox" checked={!!edit.is_sensitive}
                onChange={e => setEdit({ ...edit, is_sensitive: e.target.checked })} />
              Sensitive (strip money keys before render)
            </label>
            <label className="text-xs flex items-center gap-2 mt-4">
              <input type="checkbox" checked={edit.is_active !== false}
                onChange={e => setEdit({ ...edit, is_active: e.target.checked })} />
              Active
            </label>
          </div>
          {edit.is_sensitive && (
            <div className="p-2 rounded bg-amber-50 border border-amber-200 text-xs text-amber-800 flex items-start gap-2">
              <ShieldAlert size={14} className="mt-0.5" />
              <div>
                Sensitive templates NEVER carry money figures. The body must
                direct the reader to open the ERP — money keys in the context
                are stripped at render time.
              </div>
            </div>
          )}
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={() => setEdit(null)}>Cancel</Button>
            <Button onClick={save} disabled={busy}>{busy ? 'Saving…' : 'Save'}</Button>
          </div>
        </Card>
      )}
    </div>
  );
};

// ---------------------------------------------------------------------------
// Tab 4: Delivery log + dead-letter + resend
// ---------------------------------------------------------------------------

const LogTab: React.FC = () => {
  const [rows, setRows] = useState<any[]>([]);
  const [dead, setDead] = useState<any[]>([]);
  const [statusFilter, setStatusFilter] = useState('');
  const [eventFilter, setEventFilter] = useState('');
  const [loading, setLoading] = useState(true);
  const [showDead, setShowDead] = useState(false);
  const [busy, setBusy] = useState<number | null>(null);

  const refresh = async () => {
    setLoading(true);
    try {
      const [r, dl] = await Promise.all([
        client.get(ENDPOINTS.NOTIFICATIONS.DELIVERIES, {
          params: {
            status: statusFilter || undefined,
            event_type: eventFilter || undefined,
          },
        }),
        client.get(ENDPOINTS.NOTIFICATIONS.DEAD_LETTER),
      ]);
      setRows(r.data || []);
      setDead(dl.data || []);
    } catch (e: any) {
      toast.error(errMsg(e, 'Failed to load log'));
    } finally { setLoading(false); }
  };
  useEffect(() => { refresh(); }, [statusFilter, eventFilter]);

  const resend = async (id: number) => {
    setBusy(id);
    try {
      const r = await client.post(ENDPOINTS.NOTIFICATIONS.DELIVERY_RESEND(id));
      if (r.data.ok) toast.success('Resent');
      else toast.error(r.data.error || 'Resend failed');
      await refresh();
    } catch (e: any) {
      toast.error(errMsg(e, 'Resend failed'));
    } finally { setBusy(null); }
  };

  const tone = (s: string) => {
    if (s === 'sent') return 'bg-green-100 text-green-700 border-green-300';
    if (s === 'failed' || s === 'dead_letter') return 'bg-red-100 text-red-700 border-red-300';
    if (s === 'queued') return 'bg-blue-100 text-blue-700 border-blue-300';
    return 'bg-slate-100 text-slate-600 border-slate-300';
  };

  const list = showDead ? dead : rows;

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-start">
        <div>
          <h2 className="text-lg font-semibold">Delivery log</h2>
          <p className="text-sm text-slate-500">
            One row per channel-send attempt. Failed sends retry with
            backoff; MAX attempts → dead-letter for admin inspection.
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant={showDead ? 'default' : 'secondary'}
            onClick={() => setShowDead(!showDead)}>
            <AlertTriangle size={14} className="mr-1" />
            {showDead ? 'Show all' : `Dead-letter (${dead.length})`}
          </Button>
          <Button variant="secondary" onClick={refresh}>
            <RefreshCw size={14} className="mr-1" />Refresh
          </Button>
        </div>
      </div>

      {!showDead && (
        <div className="flex gap-2">
          <select className="border border-slate-300 rounded px-2 py-1 text-sm"
            value={statusFilter} onChange={e => setStatusFilter(e.target.value)}>
            <option value="">Any status</option>
            {['queued','sent','failed','skipped_pref','skipped_quiet','dead_letter'].map(s =>
              <option key={s} value={s}>{s}</option>
            )}
          </select>
          <Input placeholder="Event type filter"
            value={eventFilter} onChange={e => setEventFilter(e.target.value)}
            className="max-w-xs" />
        </div>
      )}

      {loading ? (
        <div className="text-slate-400 py-4">Loading…</div>
      ) : (
        <Card>
          <table className="w-full text-sm">
            <thead className="text-xs uppercase text-slate-500 border-b">
              <tr>
                <th className="text-left px-3 py-2">ID</th>
                <th className="text-left px-3 py-2">Event</th>
                <th className="text-left px-3 py-2">Recipient</th>
                <th className="text-left px-3 py-2">Channel</th>
                <th className="text-left px-3 py-2">Status</th>
                <th className="text-right px-3 py-2">Attempts</th>
                <th className="text-left px-3 py-2">Error</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {list.map(d => (
                <tr key={d.id} className="border-b hover:bg-slate-50">
                  <td className="px-3 py-2 font-mono text-xs">#{d.id}</td>
                  <td className="px-3 py-2 text-xs">{d.event_type}</td>
                  <td className="px-3 py-2">#{d.recipient_user_id}</td>
                  <td className="px-3 py-2">{d.channel}</td>
                  <td className="px-3 py-2">
                    <Badge className={cn('border', tone(d.status))}>{d.status}</Badge>
                  </td>
                  <td className="px-3 py-2 text-right">{d.attempts}</td>
                  <td className="px-3 py-2 text-red-700 text-xs truncate max-w-xs">{d.error || ''}</td>
                  <td className="px-3 py-2 text-right">
                    {['failed', 'dead_letter'].includes(d.status) && (
                      <Button size="sm" variant="secondary"
                        onClick={() => resend(d.id)}
                        disabled={busy === d.id}>
                        {busy === d.id ? '…' : 'Resend'}
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
              {!list.length && (
                <tr><td colSpan={8} className="text-center text-slate-400 py-6">
                  Nothing to show.
                </td></tr>
              )}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
};

// ---------------------------------------------------------------------------
// Shell
// ---------------------------------------------------------------------------

export const NotificationsWorkspace: React.FC = () => {
  const [tab, setTab] = useState<TabId>('my-prefs');

  return (
    <div className="p-6 space-y-4">
      <div className="flex gap-1 border-b border-slate-200">
        {TABS.map(t => {
          const Icon = t.icon;
          const active = tab === t.id;
          return (
            <button key={t.id} onClick={() => setTab(t.id)}
              className={cn(
                'px-4 py-2 flex items-center gap-2 text-sm border-b-2 -mb-px transition-colors',
                active
                  ? 'border-blue-600 text-blue-700 font-medium'
                  : 'border-transparent text-slate-500 hover:text-slate-700',
              )}>
              <Icon size={14} />{t.label}
            </button>
          );
        })}
      </div>

      {tab === 'my-prefs' && <MyPrefsTab />}
      {tab === 'providers' && <ProvidersTab />}
      {tab === 'templates' && <TemplatesTab />}
      {tab === 'log' && <LogTab />}
    </div>
  );
};

export default NotificationsWorkspace;
