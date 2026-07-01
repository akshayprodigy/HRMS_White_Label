/**
 * Section K plumbing admin — three tabs:
 *   1. My Bank Details  (any user; HR-verify chip if verified)
 *   2. Data Quality     (HR: fleet-wide scan + readiness gate)
 *   3. Scheduled Jobs   (HR: list, run-now, toggle)
 */
import React, { useEffect, useState } from 'react';
import {
  Banknote, Bug, Play, Pause, ShieldCheck, ShieldAlert,
  Clock, RefreshCw, CheckCircle2, XCircle, Wrench,
} from 'lucide-react';
import { toast } from 'sonner';
import {
  Card, Button, Badge, cn, errMsg, EmptyState, Loading, StatusChip,
} from './ui-elements';
import { Input } from './ui/input';
import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';

const TABS = [
  { id: 'my-bank',   label: 'My Bank Details', icon: Banknote },
  { id: 'dq',        label: 'Data Quality',    icon: Bug },
  { id: 'jobs',      label: 'Scheduled Jobs',  icon: Wrench },
] as const;
type TabId = typeof TABS[number]['id'];

// ---------------------------------------------------------------------------
// Tab 1: My Bank Details
// ---------------------------------------------------------------------------

const MyBankTab: React.FC = () => {
  const [data, setData] = useState<any | null>(null);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState({
    bank_account: '', bank_ifsc_code: '',
    bank_account_holder_name: '', bank_name: '',
  });
  const [busy, setBusy] = useState(false);

  const refresh = async () => {
    setLoading(true);
    try {
      const r = await client.get(ENDPOINTS.PLUMBING.MY_BANK);
      setData(r.data);
      setForm({
        bank_account: r.data.bank_account || '',
        bank_ifsc_code: r.data.bank_ifsc_code || '',
        bank_account_holder_name: r.data.bank_account_holder_name || '',
        bank_name: r.data.bank_name || '',
      });
    } catch (e: any) {
      toast.error(errMsg(e, 'Failed to load bank details'));
    } finally { setLoading(false); }
  };
  useEffect(() => { refresh(); }, []);

  const save = async () => {
    setBusy(true);
    try {
      const r = await client.put(ENDPOINTS.PLUMBING.MY_BANK, form);
      setData(r.data);
      toast.success('Bank details saved — HR will re-verify');
    } catch (e: any) {
      toast.error(errMsg(e, 'Save failed'));
    } finally { setBusy(false); }
  };

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold">My Bank Details</h2>
        <p className="text-sm text-slate-500">
          Used by the NEFT salary run. Editing any field clears the HR
          verification stamp — you'll need HR to reverify.
        </p>
      </div>

      {loading ? (
        <div className="text-slate-400 py-4">Loading…</div>
      ) : (
        <Card className="p-4 space-y-3">
          <div className="flex items-center gap-2">
            {data?.bank_verified_at ? (
              <Badge className="border bg-green-100 text-green-700 border-green-300 flex items-center gap-1">
                <ShieldCheck size={12} />HR-verified
              </Badge>
            ) : (
              <Badge className="border bg-amber-100 text-amber-700 border-amber-300 flex items-center gap-1">
                <ShieldAlert size={12} />Pending HR verification
              </Badge>
            )}
            {!data?.is_shape_valid && (
              <Badge className="border bg-red-100 text-red-700 border-red-300">
                Shape check failed
              </Badge>
            )}
          </div>
          {data?.validation_warnings?.length > 0 && (
            <div className="p-2 rounded bg-amber-50 border border-amber-200 text-xs text-amber-800">
              {data.validation_warnings.map((w: string, i: number) => (
                <div key={i}>• {w}</div>
              ))}
              <div className="mt-1 text-[10px] text-slate-500">
                These are warnings, not blockers. Confirm with your cancelled cheque.
              </div>
            </div>
          )}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-slate-500">Account number</label>
              <Input value={form.bank_account}
                onChange={e => setForm({ ...form, bank_account: e.target.value })} />
            </div>
            <div>
              <label className="text-xs text-slate-500">IFSC code</label>
              <Input value={form.bank_ifsc_code}
                onChange={e => setForm({ ...form, bank_ifsc_code: e.target.value.toUpperCase() })} />
            </div>
            <div>
              <label className="text-xs text-slate-500">Account holder name</label>
              <Input value={form.bank_account_holder_name}
                onChange={e => setForm({ ...form, bank_account_holder_name: e.target.value })} />
            </div>
            <div>
              <label className="text-xs text-slate-500">Bank name</label>
              <Input value={form.bank_name}
                onChange={e => setForm({ ...form, bank_name: e.target.value })} />
            </div>
          </div>
          <div className="flex justify-end">
            <Button onClick={save} disabled={busy}>
              {busy ? 'Saving…' : 'Save'}
            </Button>
          </div>
        </Card>
      )}
    </div>
  );
};

// ---------------------------------------------------------------------------
// Tab 2: Data Quality
// ---------------------------------------------------------------------------

const DQTab: React.FC = () => {
  const [scan, setScan] = useState<any | null>(null);
  const [readiness, setReadiness] = useState<any | null>(null);
  const [loading, setLoading] = useState(true);
  const [severityFilter, setSeverityFilter] = useState<string>('');

  const refresh = async () => {
    setLoading(true);
    try {
      const [s, r] = await Promise.all([
        client.get(ENDPOINTS.PLUMBING.DQ_SCAN, {
          params: severityFilter ? { severity: severityFilter } : {},
        }),
        client.get(ENDPOINTS.PLUMBING.DQ_READINESS),
      ]);
      setScan(s.data);
      setReadiness(r.data);
    } catch (e: any) {
      toast.error(errMsg(e, 'Scan failed'));
    } finally { setLoading(false); }
  };
  useEffect(() => { refresh(); }, [severityFilter]);

  const sevTone = (s: string) => {
    if (s.startsWith('BLOCKS_')) return 'bg-red-100 text-red-700 border-red-300';
    return 'bg-amber-100 text-amber-700 border-amber-300';
  };

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-start">
        <div>
          <h2 className="text-lg font-semibold">Data-Quality Scan</h2>
          <p className="text-sm text-slate-500">
            Advisory — HR fixes flagged rows before payroll/statutory export.
            Nothing here auto-blocks payroll.
          </p>
        </div>
        <Button variant="secondary" onClick={refresh}>
          <RefreshCw size={14} className="mr-1" />Rescan
        </Button>
      </div>

      {readiness && (
        <Card className={cn(
          "p-3 border",
          readiness.ready
            ? "bg-green-50 border-green-300"
            : "bg-red-50 border-red-300",
        )}>
          <div className="flex items-center gap-2">
            {readiness.ready
              ? <CheckCircle2 size={16} className="text-green-700" />
              : <XCircle size={16} className="text-red-700" />}
            <div className="font-medium">
              {readiness.ready
                ? 'Ready — no payroll/statutory blockers'
                : `${readiness.blocker_count} blocker(s) present`}
            </div>
          </div>
        </Card>
      )}

      {loading || !scan ? (
        <div className="text-slate-400 py-4">Loading…</div>
      ) : (
        <>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
            {Object.entries(scan.summary?.by_severity || {}).map(([k, v]) => (
              <button key={k}
                onClick={() => setSeverityFilter(severityFilter === k ? '' : k)}
                className={cn(
                  'p-2 rounded border text-left',
                  severityFilter === k ? 'ring-2 ring-blue-400' : '',
                  sevTone(k),
                )}>
                <div className="text-lg font-semibold">{String(v)}</div>
                <div className="text-[10px] uppercase tracking-wide">{k}</div>
              </button>
            ))}
          </div>

          <Card>
            <table className="w-full text-sm">
              <thead className="text-xs uppercase text-slate-500 border-b">
                <tr>
                  <th className="text-left px-3 py-2">Emp</th>
                  <th className="text-left px-3 py-2">Name</th>
                  <th className="text-left px-3 py-2">Field</th>
                  <th className="text-left px-3 py-2">Severity</th>
                  <th className="text-left px-3 py-2">Reason</th>
                </tr>
              </thead>
              <tbody>
                {(scan.findings || []).map((f: any, i: number) => (
                  <tr key={i} className="border-b hover:bg-slate-50">
                    <td className="px-3 py-2">{f.employee_code}</td>
                    <td className="px-3 py-2">{f.full_name}</td>
                    <td className="px-3 py-2 text-slate-600">{f.field}</td>
                    <td className="px-3 py-2">
                      <Badge className={cn('border', sevTone(f.severity))}>
                        {f.severity}
                      </Badge>
                    </td>
                    <td className="px-3 py-2 text-slate-600">{f.reason}</td>
                  </tr>
                ))}
                {!(scan.findings || []).length && (
                  <tr><td colSpan={5} className="text-center text-slate-400 py-6">
                    No findings — data quality is clean.
                  </td></tr>
                )}
              </tbody>
            </table>
          </Card>
        </>
      )}
    </div>
  );
};

// ---------------------------------------------------------------------------
// Tab 3: Scheduled Jobs
// ---------------------------------------------------------------------------

const JobsTab: React.FC = () => {
  const [data, setData] = useState<any | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);

  const refresh = async () => {
    setLoading(true);
    try {
      const r = await client.get(ENDPOINTS.PLUMBING.JOBS);
      setData(r.data);
    } catch (e: any) {
      toast.error(errMsg(e, 'Failed to load jobs'));
    } finally { setLoading(false); }
  };
  useEffect(() => { refresh(); }, []);

  const seed = async () => {
    try {
      await client.post(ENDPOINTS.PLUMBING.JOBS_SEED);
      toast.success('Seeded');
      await refresh();
    } catch (e: any) {
      toast.error(errMsg(e, 'Seed failed'));
    }
  };
  const runNow = async (name: string) => {
    setBusy(name);
    try {
      const r = await client.post(ENDPOINTS.PLUMBING.JOB_RUN_NOW(name));
      const s = r.data;
      if (s.ok) toast.success(`${name} succeeded in ${s.duration_ms}ms`);
      else toast.error(`${name} failed: ${s.error || 'see admin log'}`);
      await refresh();
    } catch (e: any) {
      toast.error(errMsg(e, 'Run failed'));
    } finally { setBusy(null); }
  };
  const toggle = async (name: string) => {
    try {
      await client.post(ENDPOINTS.PLUMBING.JOB_TOGGLE(name));
      await refresh();
    } catch (e: any) {
      toast.error(errMsg(e, 'Toggle failed'));
    }
  };

  const statusTone = (s: string) => {
    if (s === 'success') return 'bg-green-100 text-green-700 border-green-300';
    if (s === 'failed')  return 'bg-red-100 text-red-700 border-red-300';
    if (s === 'running') return 'bg-blue-100 text-blue-700 border-blue-300';
    return 'bg-slate-100 text-slate-600 border-slate-300';
  };

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-start">
        <div>
          <h2 className="text-lg font-semibold">Scheduled Jobs</h2>
          <p className="text-sm text-slate-500">
            APScheduler in-process. Every job is idempotent + safe to
            re-run. "Run now" forces execution regardless of enabled state.
          </p>
        </div>
        <div className="flex gap-2">
          {data?.unregistered?.length > 0 && (
            <Button variant="secondary" onClick={seed}>
              Seed {data.unregistered.length} job(s)
            </Button>
          )}
          <Button variant="secondary" onClick={refresh}>
            <RefreshCw size={14} className="mr-1" />Refresh
          </Button>
        </div>
      </div>

      {loading ? (
        <div className="text-slate-400 py-4">Loading…</div>
      ) : (
        <div className="space-y-2">
          {(data?.jobs || []).map((j: any) => (
            <Card key={j.id} className="p-4">
              <div className="flex justify-between items-start">
                <div>
                  <div className="flex items-center gap-2">
                    <div className="font-medium">{j.display_name}</div>
                    <Badge className={cn('border', statusTone(j.last_status))}>
                      {j.last_status}
                    </Badge>
                    {!j.enabled && (
                      <Badge className="border bg-slate-100 text-slate-600 border-slate-300">
                        disabled
                      </Badge>
                    )}
                    {j.is_running && (
                      <Badge className="border bg-blue-100 text-blue-700 border-blue-300 flex items-center gap-1">
                        <Clock size={10} />running
                      </Badge>
                    )}
                  </div>
                  <div className="text-xs text-slate-500 mt-1">
                    {j.description}
                  </div>
                  <div className="text-xs text-slate-500 mt-1 font-mono">
                    Cron: {j.cadence_cron}
                    {j.last_run_at && (
                      <span className="ml-3">Last: {new Date(j.last_run_at).toLocaleString()}</span>
                    )}
                    {j.last_duration_ms != null && (
                      <span className="ml-3">Took: {j.last_duration_ms}ms</span>
                    )}
                  </div>
                  {j.last_error && (
                    <div className="mt-2 p-2 rounded bg-red-50 border border-red-200 text-xs text-red-700">
                      {j.last_error}
                    </div>
                  )}
                  {j.last_summary && !j.last_error && (
                    <div className="mt-2 p-2 rounded bg-slate-50 border border-slate-200 text-xs text-slate-600 font-mono truncate">
                      {j.last_summary}
                    </div>
                  )}
                </div>
                <div className="flex gap-2">
                  <Button size="sm" variant="secondary" onClick={() => toggle(j.name)}>
                    {j.enabled ? <><Pause size={12} className="mr-1" />Disable</> : <><Play size={12} className="mr-1" />Enable</>}
                  </Button>
                  <Button size="sm" onClick={() => runNow(j.name)} disabled={busy === j.name}>
                    <Play size={12} className="mr-1" />{busy === j.name ? 'Running…' : 'Run now'}
                  </Button>
                </div>
              </div>
            </Card>
          ))}
          {!(data?.jobs || []).length && (
            <Card className="p-8 text-center text-slate-500">
              No jobs seeded yet. Click "Seed" above to register the default
              catalog.
            </Card>
          )}
        </div>
      )}
    </div>
  );
};

// ---------------------------------------------------------------------------
// Shell
// ---------------------------------------------------------------------------

export const PlumbingAdmin: React.FC = () => {
  const [tab, setTab] = useState<TabId>('my-bank');

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

      {tab === 'my-bank' && <MyBankTab />}
      {tab === 'dq' && <DQTab />}
      {tab === 'jobs' && <JobsTab />}
    </div>
  );
};

export default PlumbingAdmin;
