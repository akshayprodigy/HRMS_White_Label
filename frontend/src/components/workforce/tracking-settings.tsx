import React, { useCallback, useEffect, useState } from 'react';
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

const RETENTION_KEY = 'tracking.retention_days';
const inputCls =
  'h-9 px-2 rounded-lg border border-slate-200 text-sm text-[#0F172A] bg-white ' +
  'focus:outline-none focus:ring-2 focus:ring-blue-600/30 focus:border-blue-500 disabled:opacity-50';
const th = 'text-left text-[9px] font-black uppercase tracking-widest text-slate-400 py-2 pr-3';
const fmtDate = (s: string | null) => (s ? s.slice(0, 16).replace('T', ' ') + ' UTC' : '—');

export const TrackingSettings: React.FC = () => {
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [drafts, setDrafts] = useState<Record<number, Policy>>({});
  const [overrides, setOverrides] = useState<Override[]>([]);
  const [consents, setConsents] = useState<Consent[]>([]);
  const [status, setStatus] = useState<'all' | 'active' | 'revoked'>('all');
  const [matches, setMatches] = useState<EmpOpt[]>([]);
  const [search, setSearch] = useState('');
  const [retention, setRetention] = useState('');
  const [loadErr, setLoadErr] = useState<string | null>(null);
  const [readOnly, setReadOnly] = useState(false);
  const [busyKey, setBusyKey] = useState<string | null>(null);

  const guard = useCallback((e: any, fallback: string) => {
    if (e?.response?.status === 403) setReadOnly(true);
    toast.error(errMsg(e, fallback));
  }, []);

  const loadAll = useCallback(async () => {
    try {
      const [p, o, r] = await Promise.all([
        client.get<Policy[]>(ENDPOINTS.TRACKING.POLICIES),
        client.get<Override[]>(ENDPOINTS.TRACKING.OVERRIDES),
        client.get(ENDPOINTS.HR.TIME_RULES),
      ]);
      setPolicies(p.data);
      setDrafts(Object.fromEntries(p.data.map((x) => [x.role_id, x])));
      setOverrides(o.data);
      setRetention(String(r.data?.rules?.[RETENTION_KEY] ?? '30'));
      setLoadErr(null);
    } catch (err: any) {
      setLoadErr(errMsg(err, 'Failed to load tracking settings'));
    }
  }, []);

  const loadConsents = useCallback(async () => {
    try {
      const r = await client.get<Consent[]>(`${ENDPOINTS.TRACKING.CONSENTS}?status=${status}`);
      setConsents(r.data);
    } catch (err: any) {
      toast.error(errMsg(err, 'Failed to load consents'));
    }
  }, [status]);

  useEffect(() => { loadAll(); }, [loadAll]);
  useEffect(() => { loadConsents(); }, [loadConsents]);

  const patchDraft = (id: number, patch: Partial<Policy>) =>
    setDrafts((d) => ({ ...d, [id]: { ...d[id], ...patch } }));

  const dirty = (p: Policy) => {
    const d = drafts[p.role_id];
    return !!d && (d.enabled !== p.enabled || d.interval_seconds !== p.interval_seconds ||
      d.distance_filter_m !== p.distance_filter_m);
  };

  const savePolicy = async (p: Policy) => {
    const d = drafts[p.role_id];
    const iv = Number(d.interval_seconds);
    const dist = Number(d.distance_filter_m);
    if (!Number.isInteger(iv) || iv < 60 || iv > 3600) {
      toast.error('Interval must be a whole number of seconds from 60 to 3600');
      return;
    }
    if (!Number.isInteger(dist) || dist < 10 || dist > 2000) {
      toast.error('Distance filter must be a whole number of metres from 10 to 2000');
      return;
    }
    setBusyKey(`p${p.role_id}`);
    try {
      await client.put(ENDPOINTS.TRACKING.POLICY(p.role_id), {
        enabled: d.enabled, interval_seconds: iv, distance_filter_m: dist,
      });
      toast.success(`Saved tracking policy for ${p.role_name}`);
      await loadAll();
    } catch (e: any) {
      guard(e, 'Failed to save policy');
    } finally {
      setBusyKey(null);
    }
  };

  const setOverride = async (userId: number, enabled: boolean) => {
    setBusyKey(`o${userId}`);
    try {
      await client.put(ENDPOINTS.TRACKING.OVERRIDE(userId), { enabled });
      await loadAll();
    } catch (e: any) {
      guard(e, 'Failed to set override');
    } finally {
      setBusyKey(null);
    }
  };

  const removeOverride = async (userId: number) => {
    setBusyKey(`o${userId}`);
    try {
      await client.delete(ENDPOINTS.TRACKING.OVERRIDE(userId));
      await loadAll();
    } catch (e: any) {
      guard(e, 'Failed to remove override');
    } finally {
      setBusyKey(null);
    }
  };

  const saveRetention = async () => {
    if (!/^\d+$/.test(retention.trim()) || Number(retention) < 1 || Number(retention) > 365) {
      toast.error('Retention must be a whole number of days from 1 to 365');
      return;
    }
    setBusyKey('ret');
    try {
      await client.put(ENDPOINTS.HR.TIME_RULES, { rules: { [RETENTION_KEY]: retention.trim() } });
      toast.success('Retention saved');
    } catch (e: any) {
      guard(e, 'Failed to save retention');
    } finally {
      setBusyKey(null);
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
        const r = await client.get(ENDPOINTS.HR.EMPLOYEES, { params: { search: q, size: 8 } });
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
          {readOnly && (
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
                const d = drafts[p.role_id] ?? p;
                return (
                  <tr key={p.role_id} className="border-t border-slate-100">
                    <td className="py-2 pr-3 font-medium text-slate-800">{p.role_name}</td>
                    <td className="py-2 pr-3">
                      <input type="checkbox" className="w-4 h-4 accent-blue-600"
                        aria-label={`Track ${p.role_name}`} disabled={readOnly}
                        checked={d.enabled} onChange={(e) => patchDraft(p.role_id, { enabled: e.target.checked })} />
                    </td>
                    <td className="py-2 pr-3">
                      <input type="number" min={60} max={3600} step={1} className={`${inputCls} w-24`}
                        aria-label={`Interval seconds for ${p.role_name}`} disabled={readOnly}
                        value={d.interval_seconds}
                        onChange={(e) => patchDraft(p.role_id, { interval_seconds: e.target.value as any })} />
                    </td>
                    <td className="py-2 pr-3">
                      <input type="number" min={10} max={2000} step={1} className={`${inputCls} w-24`}
                        aria-label={`Distance metres for ${p.role_name}`} disabled={readOnly}
                        value={d.distance_filter_m}
                        onChange={(e) => patchDraft(p.role_id, { distance_filter_m: e.target.value as any })} />
                    </td>
                    <td className="py-2 text-right">
                      <Button size="sm" onClick={() => savePolicy(p)}
                        disabled={readOnly || !dirty(p)} isLoading={busyKey === `p${p.role_id}`}>
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
        <div className="relative max-w-sm">
          <input type="text" className={`${inputCls} w-full`} placeholder="Search employee by name"
            aria-label="Search employee" disabled={readOnly}
            value={search} onChange={(e) => setSearch(e.target.value)} />
          {matches.length > 0 && (
            <ul className="absolute z-10 mt-1 w-full bg-white border border-slate-200 rounded-lg shadow-md max-h-56 overflow-y-auto">
              {matches.map((m) => (
                <li key={m.user_id} className="flex items-center justify-between gap-2 px-3 py-2 text-sm">
                  <span>{m.name}</span>
                  <span className="flex gap-1">
                    <Button size="sm" variant="outline" onClick={() => { setOverride(m.user_id, true); setSearch(''); }}>
                      Enable
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => { setOverride(m.user_id, false); setSearch(''); }}>
                      Disable
                    </Button>
                  </span>
                </li>
              ))}
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
                  <Button size="sm" variant="outline" disabled={readOnly || busyKey === `o${o.user_id}`}
                    onClick={() => setOverride(o.user_id, !o.enabled)}>
                    {o.enabled ? 'Disable' : 'Enable'}
                  </Button>
                  <Button size="sm" variant="outline" disabled={readOnly || busyKey === `o${o.user_id}`}
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

      <Card className="p-6 border-slate-200 bg-white space-y-3">
        <h3 className="text-sm font-black uppercase tracking-tight text-[#0F172A]">Location retention</h3>
        <div className="flex items-end gap-3 flex-wrap">
          <div className="space-y-1">
            <label htmlFor={RETENTION_KEY} className="text-[9px] font-black uppercase tracking-widest text-slate-400">
              Retention (days)
            </label>
            <input id={RETENTION_KEY} type="number" min={1} max={365} step={1} className={`${inputCls} w-28 block`}
              disabled={readOnly} value={retention} onChange={(e) => setRetention(e.target.value)} />
          </div>
          <Button size="sm" onClick={saveRetention} disabled={readOnly} isLoading={busyKey === 'ret'}>
            Save retention
          </Button>
        </div>
        <p className="text-[9px] font-bold text-slate-400">
          Location pings older than this are deleted daily (range 1–365).
        </p>
      </Card>
    </div>
  );
};
