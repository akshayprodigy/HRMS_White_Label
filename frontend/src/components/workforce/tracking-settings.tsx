import React, { useCallback, useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';
import { MapPin } from 'lucide-react';
import { Card, Button, Badge } from '../ui-elements';
import { client } from '../../api/client';
import { ENDPOINTS } from '../../api/endpoints';
import { errMsg } from '../schedule-delegations-utils';

// HR settings for live location tracking (off by default). Per-role policy,
// per-employee overrides, consent list and the ping retention time rule.

interface Policy {
  role_id: number;
  role_name: string;
  enabled: boolean;
  interval_seconds: number;
  distance_filter_m: number;
  configured: boolean;
}
interface Override { user_id: number; name: string; email: string; enabled: boolean }
interface Consent {
  user_id: number;
  name: string;
  email: string;
  status: 'active' | 'revoked';
  consented_at: string | null;
  revoked_at: string | null;
  app_version: string | null;
}
interface EmpOpt { user_id: number; name: string }
// Numeric inputs are edited as strings and compared with Number().
interface Draft { enabled: boolean; interval: string; distance: string }
const toDraft = (p: Policy): Draft => ({
  enabled: p.enabled,
  interval: String(p.interval_seconds),
  distance: String(p.distance_filter_m),
});
const SEARCH_LIMIT = 8;
const CONSENT_MAX = 500;

const RETENTION_KEY = 'tracking.retention_days';
const inputCls =
  'h-9 px-2 rounded-lg border border-slate-200 text-sm text-[#0F172A] bg-white ' +
  'focus:outline-none focus:ring-2 focus:ring-blue-600/30 focus:border-blue-500 disabled:opacity-50';
const th = 'text-left text-[9px] font-black uppercase tracking-widest text-slate-400 py-2 pr-3';
const fmtDate = (s: string | null) => (s ? s.slice(0, 16).replace('T', ' ') + ' UTC' : '—');

export const TrackingSettings: React.FC = () => {
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [drafts, setDrafts] = useState<Record<number, Draft>>({});
  const [overrides, setOverrides] = useState<Override[]>([]);
  const [consents, setConsents] = useState<Consent[]>([]);
  const [status, setStatus] = useState<'all' | 'active' | 'revoked'>('all');
  const [matches, setMatches] = useState<EmpOpt[]>([]);
  const [search, setSearch] = useState('');
  const [retention, setRetention] = useState('');
  const [retentionAvailable, setRetentionAvailable] = useState(true);
  const [loadErr, setLoadErr] = useState<string | null>(null);
  // Write permission is tracked per section: policies/overrides need
  // "hr employee write"; the retention rule needs the time-rules permission.
  const [policyReadOnly, setPolicyReadOnly] = useState(false);
  const [retentionReadOnly, setRetentionReadOnly] = useState(false);
  const [busy, setBusy] = useState<Set<string>>(new Set());
  const consentReq = useRef(0);

  const setBusyKey = (k: string, on: boolean) =>
    setBusy((prev) => {
      const next = new Set(prev);
      if (on) next.add(k);
      else next.delete(k);
      return next;
    });

  const denied = (e: any, setter: (v: boolean) => void, fallback: string) => {
    if (e?.response?.status === 403) setter(true);
    toast.error(errMsg(e, fallback));
  };

  const loadPolicies = useCallback(async () => {
    try {
      const r = await client.get<Policy[]>(ENDPOINTS.TRACKING.POLICIES);
      setPolicies(r.data);
      setDrafts(Object.fromEntries(r.data.map((x) => [x.role_id, toDraft(x)])));
      setLoadErr(null);
    } catch (err: any) {
      if (err?.response?.status === 403) setPolicyReadOnly(true);
      setLoadErr(errMsg(err, 'Failed to load tracking settings'));
    }
  }, []);

  const loadOverrides = useCallback(async () => {
    try {
      const r = await client.get<Override[]>(ENDPOINTS.TRACKING.OVERRIDES);
      setOverrides(r.data);
    } catch (err: any) {
      if (err?.response?.status === 403) setPolicyReadOnly(true);
      toast.error(errMsg(err, 'Failed to load overrides'));
    }
  }, []);

  const loadRetention = useCallback(async () => {
    try {
      const r = await client.get(ENDPOINTS.HR.TIME_RULES);
      setRetention(String(r.data?.rules?.[RETENTION_KEY] ?? '30'));
      setRetentionAvailable(true);
    } catch (err: any) {
      // No time-rules permission: hide only the retention card.
      if (err?.response?.status === 403) setRetentionAvailable(false);
      else setRetentionReadOnly(true);
    }
  }, []);

  const loadConsents = useCallback(async () => {
    const id = ++consentReq.current;
    try {
      const r = await client.get<Consent[]>(`${ENDPOINTS.TRACKING.CONSENTS}?status=${status}&limit=${CONSENT_MAX}`);
      if (id === consentReq.current) setConsents(r.data);
    } catch (err: any) {
      if (id === consentReq.current) toast.error(errMsg(err, 'Failed to load consents'));
    }
  }, [status]);

  useEffect(() => { loadPolicies(); loadOverrides(); loadRetention(); }, [loadPolicies, loadOverrides, loadRetention]);
  useEffect(() => { loadConsents(); }, [loadConsents]);

  const patchDraft = (id: number, patch: Partial<Draft>) =>
    setDrafts((d) => ({ ...d, [id]: { ...d[id], ...patch } }));

  const dirty = (p: Policy) => {
    const d = drafts[p.role_id];
    return !!d && (d.enabled !== p.enabled || Number(d.interval) !== p.interval_seconds ||
      Number(d.distance) !== p.distance_filter_m);
  };

  const savePolicy = async (p: Policy) => {
    const d = drafts[p.role_id];
    const iv = Number(d.interval);
    const dist = Number(d.distance);
    if (d.interval.trim() === '' || !Number.isInteger(iv) || iv < 60 || iv > 3600) {
      toast.error('Interval must be a whole number of seconds from 60 to 3600');
      return;
    }
    if (d.distance.trim() === '' || !Number.isInteger(dist) || dist < 10 || dist > 2000) {
      toast.error('Distance filter must be a whole number of metres from 10 to 2000');
      return;
    }
    const key = `p${p.role_id}`;
    setBusyKey(key, true);
    try {
      const r = await client.put(ENDPOINTS.TRACKING.POLICY(p.role_id), {
        enabled: d.enabled, interval_seconds: iv, distance_filter_m: dist,
      });
      // Update only this row; other rows' unsaved edits are untouched.
      const saved: Policy = { ...p, enabled: r.data.enabled, interval_seconds: r.data.interval_seconds,
        distance_filter_m: r.data.distance_filter_m, configured: true };
      setPolicies((ps) => ps.map((x) => (x.role_id === p.role_id ? saved : x)));
      patchDraft(p.role_id, toDraft(saved));
      toast.success(`Saved tracking policy for ${p.role_name}`);
    } catch (e: any) {
      denied(e, setPolicyReadOnly, 'Failed to save policy');
    } finally {
      setBusyKey(key, false);
    }
  };

  const setOverride = async (userId: number, enabled: boolean) => {
    const key = `o${userId}`;
    setBusyKey(key, true);
    try {
      await client.put(ENDPOINTS.TRACKING.OVERRIDE(userId), { enabled });
      await loadOverrides();
    } catch (e: any) {
      denied(e, setPolicyReadOnly, 'Failed to set override');
    } finally {
      setBusyKey(key, false);
    }
  };

  const removeOverride = async (userId: number) => {
    const key = `o${userId}`;
    setBusyKey(key, true);
    try {
      await client.delete(ENDPOINTS.TRACKING.OVERRIDE(userId));
      await loadOverrides();
    } catch (e: any) {
      denied(e, setPolicyReadOnly, 'Failed to remove override');
    } finally {
      setBusyKey(key, false);
    }
  };

  const saveRetention = async () => {
    if (!/^\d+$/.test(retention.trim()) || Number(retention) < 1 || Number(retention) > 365) {
      toast.error('Retention must be a whole number of days from 1 to 365');
      return;
    }
    setBusyKey('ret', true);
    try {
      await client.put(ENDPOINTS.HR.TIME_RULES, { rules: { [RETENTION_KEY]: retention.trim() } });
      toast.success('Retention saved');
    } catch (e: any) {
      denied(e, setRetentionReadOnly, 'Failed to save retention');
    } finally {
      setBusyKey('ret', false);
    }
  };

  // Server-side employee search, debounced.
  useEffect(() => {
    const q = search.trim();
    if (q.length < 2) {
      setMatches([]);
      return;
    }
    let live = true;
    const t = window.setTimeout(async () => {
      try {
        const r = await client.get(ENDPOINTS.HR.EMPLOYEES, { params: { search: q, size: SEARCH_LIMIT } });
        if (!live) return;
        setMatches(
          (r.data?.items ?? [])
            .map((x: any) => ({ user_id: x.user_id ?? x.user?.id, name: x.user?.full_name || x.user?.email || '' }))
            .filter((x: EmpOpt) => x.user_id && x.name)
        );
      } catch {
        if (live) setMatches([]);
      }
    }, 250);
    return () => {
      live = false;
      window.clearTimeout(t);
    };
  }, [search]);

  const pickOverride = async (userId: number, enabled: boolean) => {
    await setOverride(userId, enabled);
    setSearch('');
  };

  return (
    <div className="space-y-4 mt-4" data-testid="tracking-settings">
      <Card className="p-6 border-slate-200 bg-white space-y-5">
        <div>
          <h3 className="text-sm font-black uppercase tracking-tight text-[#0F172A] inline-flex items-center gap-2">
            <MapPin size={15} className="text-blue-600" /> Location tracking
          </h3>
          <p className="text-[10px] font-bold text-slate-500 mt-1">
            Off by default. Employees share location from the mobile app only during their rostered
            shift and only after they consent (revocable). Enable it per role below; a per-employee
            override beats the role setting.
          </p>
          {policyReadOnly && (
            <p role="alert" className="text-[10px] font-bold text-amber-700 mt-2">
              You don't have permission to change tracking settings (read-only).
            </p>
          )}
          {loadErr && <p role="alert" className="text-[10px] font-bold text-red-600 mt-2">{loadErr}</p>}
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr><th className={th}>Role</th><th className={th}>Enabled</th>
                <th className={th}>Interval (s)</th><th className={th}>Distance (m)</th><th /></tr>
            </thead>
            <tbody>
              {policies.map((p) => {
                const d = drafts[p.role_id] ?? toDraft(p);
                return (
                  <tr key={p.role_id} className="border-t border-slate-100">
                    <td className="py-2 pr-3 font-medium text-slate-800">{p.role_name}</td>
                    <td className="py-2 pr-3">
                      <input type="checkbox" className="w-4 h-4 accent-blue-600"
                        aria-label={`Track ${p.role_name}`} disabled={policyReadOnly}
                        checked={d.enabled} onChange={(e) => patchDraft(p.role_id, { enabled: e.target.checked })} />
                    </td>
                    <td className="py-2 pr-3">
                      <input type="number" min={60} max={3600} step={1} className={`${inputCls} w-24`}
                        aria-label={`Interval seconds for ${p.role_name}`} disabled={policyReadOnly}
                        value={d.interval}
                        onChange={(e) => patchDraft(p.role_id, { interval: e.target.value })} />
                    </td>
                    <td className="py-2 pr-3">
                      <input type="number" min={10} max={2000} step={1} className={`${inputCls} w-24`}
                        aria-label={`Distance metres for ${p.role_name}`} disabled={policyReadOnly}
                        value={d.distance}
                        onChange={(e) => patchDraft(p.role_id, { distance: e.target.value })} />
                    </td>
                    <td className="py-2 text-right">
                      <Button size="sm" onClick={() => savePolicy(p)}
                        disabled={policyReadOnly || !dirty(p)} isLoading={busy.has(`p${p.role_id}`)}>
                        Save
                      </Button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <p className="text-[9px] font-bold text-slate-400">
          Interval 60–3600 seconds; distance filter 10–2000 metres.
        </p>
      </Card>

      <Card className="p-6 border-slate-200 bg-white space-y-4">
        <h3 className="text-sm font-black uppercase tracking-tight text-[#0F172A]">Per-employee overrides</h3>
        <div
          className="relative max-w-sm"
          onBlur={(e) => {
            if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setSearch('');
          }}
          onKeyDown={(e) => { if (e.key === 'Escape') setSearch(''); }}
        >
          <label htmlFor="tracking-emp-search" className="text-[9px] font-black uppercase tracking-widest text-slate-400">
            Add an override for an employee
          </label>
          <input id="tracking-emp-search" type="text" className={`${inputCls} w-full block`}
            placeholder="Search employee by name" disabled={policyReadOnly}
            value={search} onChange={(e) => setSearch(e.target.value)} />
          {matches.length > 0 && (
            <ul className="absolute z-10 mt-1 w-full bg-white border border-slate-200 rounded-lg shadow-md max-h-56 overflow-y-auto">
              {matches.map((m) => {
                const b = busy.has(`o${m.user_id}`);
                return (
                  <li key={m.user_id} className="flex items-center justify-between gap-2 px-3 py-2 text-sm">
                    <span>{m.name}</span>
                    <span className="flex gap-1">
                      <Button size="sm" variant="outline" disabled={b} onClick={() => pickOverride(m.user_id, true)}>
                        Enable
                      </Button>
                      <Button size="sm" variant="outline" disabled={b} onClick={() => pickOverride(m.user_id, false)}>
                        Disable
                      </Button>
                    </span>
                  </li>
                );
              })}
              {matches.length >= SEARCH_LIMIT && (
                <li className="px-3 py-1 text-[10px] text-slate-400">Showing first {SEARCH_LIMIT} — refine your search</li>
              )}
            </ul>
          )}
        </div>
        {overrides.length === 0 ? (
          <p className="text-sm text-slate-500">No overrides. Roles' settings apply to everyone.</p>
        ) : (
          <ul className="divide-y divide-gray-100">
            {overrides.map((o) => (
              <li key={o.user_id} className="flex items-center justify-between gap-3 py-2 text-sm">
                <span>
                  <span className="font-medium text-slate-800">{o.name}</span>{' '}
                  <span className="text-slate-400">{o.email}</span>{' '}
                  <Badge variant={o.enabled ? 'success' : 'neutral'}>{o.enabled ? 'Always tracked' : 'Never tracked'}</Badge>
                </span>
                <span className="flex gap-1">
                  <Button size="sm" variant="outline" disabled={policyReadOnly || busy.has(`o${o.user_id}`)}
                    onClick={() => setOverride(o.user_id, !o.enabled)}>
                    {o.enabled ? 'Disable' : 'Enable'}
                  </Button>
                  <Button size="sm" variant="outline" disabled={policyReadOnly || busy.has(`o${o.user_id}`)}
                    onClick={() => removeOverride(o.user_id)}>
                    Remove
                  </Button>
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card className="p-6 border-slate-200 bg-white space-y-4">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <h3 className="text-sm font-black uppercase tracking-tight text-[#0F172A]">Consents</h3>
          <select aria-label="Consent status" className={inputCls} value={status}
            onChange={(e) => setStatus(e.target.value as any)}>
            <option value="all">All</option>
            <option value="active">Active</option>
            <option value="revoked">Revoked</option>
          </select>
        </div>
        {consents.length >= CONSENT_MAX && (
          <p className="text-[10px] font-bold text-amber-700">
            Showing the {CONSENT_MAX} most recent consents (maximum).
          </p>
        )}
        {consents.length === 0 ? (
          <p className="text-sm text-slate-500">No consents recorded.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr><th className={th}>Employee</th><th className={th}>Status</th>
                  <th className={th}>Consented</th><th className={th}>Revoked</th><th className={th}>App</th></tr>
              </thead>
              <tbody>
                {consents.map((c) => (
                  <tr key={c.user_id} className="border-t border-slate-100">
                    <td className="py-2 pr-3 font-medium text-slate-800">{c.name}</td>
                    <td className="py-2 pr-3">
                      <Badge variant={c.status === 'active' ? 'success' : 'neutral'}>{c.status}</Badge>
                    </td>
                    <td className="py-2 pr-3 text-slate-600">{fmtDate(c.consented_at)}</td>
                    <td className="py-2 pr-3 text-slate-600">{fmtDate(c.revoked_at)}</td>
                    <td className="py-2 text-slate-600">{c.app_version ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {retentionAvailable && (
      <Card className="p-6 border-slate-200 bg-white space-y-3">
        <h3 className="text-sm font-black uppercase tracking-tight text-[#0F172A]">Location retention</h3>
        {retentionReadOnly && (
          <p role="alert" className="text-[10px] font-bold text-amber-700">You don't have permission to change time rules (read-only).</p>
        )}
        <div className="flex items-end gap-3 flex-wrap">
          <div className="space-y-1">
            <label htmlFor={RETENTION_KEY} className="text-[9px] font-black uppercase tracking-widest text-slate-400">
              Retention (days)
            </label>
            <input id={RETENTION_KEY} type="number" min={1} max={365} step={1} className={`${inputCls} w-28 block`}
              disabled={retentionReadOnly} value={retention} onChange={(e) => setRetention(e.target.value)} />
          </div>
          <Button size="sm" onClick={saveRetention} disabled={retentionReadOnly} isLoading={busy.has('ret')}>
            Save retention
          </Button>
        </div>
        <p className="text-[9px] font-bold text-slate-400">
          Location pings older than this are deleted daily (range 1–365).
        </p>
      </Card>
      )}
    </div>
  );
};
