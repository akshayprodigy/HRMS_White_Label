import React, { useCallback, useEffect, useRef, useState } from 'react';
import { History, Settings2, UserPlus } from 'lucide-react';
import { Badge, Button, Card } from '../ui-elements';
import { client } from '../../api/client';
import { ENDPOINTS } from '../../api/endpoints';
import { Th } from '../biometric/shared';
import { AssignDialog } from './assign-dialog';
import { HistoryDialog } from './history-dialog';
import { KindsDialog } from './kinds-dialog';
import { Assignment, Cell, ManagerRow, Meta, Notice, Person, SOURCE_LABEL, dopErr, inputCls, labelCls } from './dop-utils';
import { PersonPicker } from './person-picker';

const LIMIT = 50;
const MAX_PICK = 200;

const CellView: React.FC<{ c: Cell | null | undefined }> = ({ c }) => {
  if (!c) return <span className="text-gray-400">Not assigned</span>;
  if (c.self_managed) {
    return <span><span className="text-amber-700 font-medium">Own post, needs another manager</span>{c.post_title && <span className="block text-xs text-gray-500">{c.post_title}</span>}</span>;
  }
  if (c.vacant) {
    return <span><span className="text-amber-700 font-medium">Vacant post</span>{c.post_title && <span className="block text-xs text-gray-500">{c.post_title}</span>}</span>;
  }
  if (!c.manager_name) return <span className="text-gray-400">Not assigned</span>;
  return (
    <span>
      {c.manager_name}{c.manager_active === false && <span className="ml-1"><Badge variant="error">Inactive</Badge></span>}
      <span className="block text-xs text-gray-500">{c.manager_active === false ? 'Needs a new manager · ' : ''}{SOURCE_LABEL[c.source] ?? c.source}{c.post_title ? ` · ${c.post_title}` : ''}</span>
    </span>
  );
};

export const ManagersTab: React.FC<{ meta: Meta | null; refreshKey: number; onMetaChanged: () => void }> = ({ meta, refreshKey, onMetaChanged }) => {
  const [q, setQ] = useState('');
  const [dq, setDq] = useState('');
  const [dept, setDept] = useState('');
  const [missing, setMissing] = useState('');
  const [managedBy, setManagedBy] = useState<Person | null>(null);
  const [shared, setShared] = useState<Assignment[]>([]);
  const [offset, setOffset] = useState(0);
  const [rows, setRows] = useState<ManagerRow[]>([]);
  const [kinds, setKinds] = useState<{ id: number; code: string; name: string }[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [picked, setPicked] = useState<Map<number, string>>(new Map());
  const [limitMsg, setLimitMsg] = useState(false);
  const [assigning, setAssigning] = useState(false);
  const [kindsOpen, setKindsOpen] = useState(false);
  const [hist, setHist] = useState<ManagerRow | null>(null);
  const [bump, setBump] = useState(0);
  const seq = useRef(0);
  const onPage = new Set(rows.map((r) => r.user_id));
  const hidden = loading || error ? [] : [...picked.keys()].filter((id) => !onPage.has(id));

  useEffect(() => {
    const t = window.setTimeout(() => { setDq(q.trim()); setOffset(0); }, 300);
    return () => window.clearTimeout(t);
  }, [q]);

  const load = useCallback(async () => {
    const n = ++seq.current;
    setLoading(true);
    try {
      const params: Record<string, unknown> = { limit: LIMIT, offset };
      if (dq) params.q = dq;
      if (dept) params.department = dept;
      if (missing) params.missing = missing;
      if (managedBy) params.managed_by = managedBy.id;
      const r = await client.get(ENDPOINTS.DOP.MANAGERS, { params });
      if (n !== seq.current) return;
      setRows(r.data.items); setTotal(r.data.total); setKinds(r.data.kinds); setError(null);
    } catch (e: any) {
      if (n === seq.current) { setRows([]); setTotal(0); setError(dopErr(e, 'Could not load managers')); }
    } finally {
      if (n === seq.current) setLoading(false);
    }
  }, [dq, dept, missing, managedBy, offset]);
  useEffect(() => { load(); }, [load, refreshKey, bump]);

  // Department / location / company rows naming the filtered manager are
  // shared: they are not removed by Replace on individuals.
  useEffect(() => {
    if (!managedBy) { setShared([]); return; }
    let live = true;
    client.get(ENDPOINTS.DOP.ASSIGNMENTS, { params: { manager_user_id: managedBy.id, limit: 200 } })
      .then((r) => { if (live) setShared((r.data.items as Assignment[]).filter((a) => a.scope_type !== 'user')); })
      .catch(() => { if (live) setShared([]); });
    return () => { live = false; };
  }, [managedBy, refreshKey, bump]);

  useEffect(() => {
    if (!loading && total > 0 && offset >= total) setOffset(Math.floor((total - 1) / LIMIT) * LIMIT);
  }, [total, offset, loading]);

  const toggle = (r: ManagerRow) => {
    setLimitMsg(false);
    setPicked((m) => {
      const next = new Map(m);
      if (next.has(r.user_id)) next.delete(r.user_id);
      else if (next.size >= MAX_PICK) { setLimitMsg(true); return m; }
      else next.set(r.user_id, r.name);
      return next;
    });
  };
  const allOnPage = rows.length > 0 && rows.every((r) => picked.has(r.user_id));
  const togglePage = () => {
    setLimitMsg(false);
    setPicked((m) => {
      const next = new Map(m);
      if (allOnPage) rows.forEach((r) => next.delete(r.user_id));
      else {
        for (const r of rows) {
          if (next.size >= MAX_PICK && !next.has(r.user_id)) { setLimitMsg(true); break; }
          next.set(r.user_id, r.name);
        }
      }
      return next;
    });
  };
  const end = Math.min(offset + LIMIT, total);
  const colSpan = 3 + kinds.length;

  return (
    <div className="space-y-4">
      <div className="flex items-end gap-3 flex-wrap">
        <div className="flex-1">
          <label className={labelCls} htmlFor="dm-q">Search employee</label>
          <input id="dm-q" className={`${inputCls} w-full`} placeholder="Name or email" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
        <div>
          <label className={labelCls} htmlFor="dm-dept">Department</label>
          <select id="dm-dept" className={inputCls} value={dept} onChange={(e) => { setDept(e.target.value); setOffset(0); }}>
            <option value="">All departments</option>
            {(meta?.departments ?? []).map((d) => <option key={d.id} value={d.name}>{d.name}</option>)}
          </select>
        </div>
        <div>
          <label className={labelCls} htmlFor="dm-miss">Show people without</label>
          <select id="dm-miss" className={inputCls} value={missing} onChange={(e) => { setMissing(e.target.value); setOffset(0); }}>
            <option value="">(everyone)</option>
            {kinds.map((k) => <option key={k.code} value={k.code}>{k.name}</option>)}
          </select>
        </div>
        <div className="flex items-end gap-2">
          <PersonPicker id="dm-by" label="Managed by" value={managedBy} onChange={(p) => { setManagedBy(p); setOffset(0); }} />
          {managedBy && <button type="button" className="text-xs text-indigo-600 pb-2" onClick={() => { setManagedBy(null); setOffset(0); }}>Clear</button>}
        </div>
        <Button variant="outline" size="sm" onClick={() => setKindsOpen(true)}><Settings2 className="w-4 h-4 mr-1" />Manager types</Button>
        <Button size="sm" onClick={() => setAssigning(true)}><UserPlus className="w-4 h-4 mr-1" />Assign managers</Button>
      </div>

      <p className="text-xs text-gray-500">Someone leaving? Filter by them, select their people and assign a new manager with Replace.</p>
      {managedBy && shared.length > 0 && (
        <div className="text-xs text-gray-700 space-y-1" role="status">
          <p className="font-medium">{managedBy.name} also manages whole groups. End these under History:</p>
          <ul className="list-disc pl-6">
            {shared.map((a) => (
              <li key={a.id}>
                {a.kind_name}: {a.scope_type === 'department' ? `everyone in ${a.scope_department_name ?? 'a department'}` : a.scope_type === 'location' ? `everyone at ${a.scope_location}` : 'everyone in the company'}
                {' '}<span className="text-gray-500">(End under History)</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      <p className="text-xs text-gray-500">This grid shows managers who cover everything. A manager limited to certain areas is listed under History (the clock icon).</p>
      {picked.size > 0 && (
        <div className="flex items-center gap-3 flex-wrap text-sm bg-indigo-50 text-indigo-800 rounded-lg px-3 py-2" role="status">
          <span><strong>{picked.size}</strong> selected{hidden.length > 0 ? `, ${hidden.length} not on this page` : ''} (up to {MAX_PICK})</span>
          {hidden.length > 0 && <button type="button" className="underline" onClick={() => setPicked((m) => { const n = new Map(m); hidden.forEach((id) => n.delete(id)); return n; })}>Keep only this page</button>}
          <button type="button" className="underline" onClick={() => { setPicked(new Map()); setLimitMsg(false); }}>Clear selection</button>
          <Button size="sm" onClick={() => setAssigning(true)}>Assign a manager to them</Button>
        </div>
      )}
      {limitMsg && <Notice tone="warn">You can select up to {MAX_PICK} employees at a time. Assign these first, then select more.</Notice>}
      {error && <Notice>{error}</Notice>}

      <Card className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-100">
              <th className="px-3 py-2 w-8"><input type="checkbox" aria-label="Select everyone on this page" checked={allOnPage} onChange={togglePage} disabled={rows.length === 0} /></th>
              <Th>Employee</Th>
              {kinds.map((k) => <Th key={k.code}>{k.name}</Th>)}
              <Th>History</Th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {rows.map((r) => (
              <tr key={r.user_id} className={picked.has(r.user_id) ? 'bg-indigo-50' : 'hover:bg-gray-50'}>
                <td className="px-3 py-2"><input type="checkbox" aria-label={`Select ${r.name}`} checked={picked.has(r.user_id)} onChange={() => toggle(r)} /></td>
                <td className="px-3 py-2">
                  <span className="font-medium text-gray-900">{r.name}</span>
                  {!r.is_active && <span className="text-xs text-gray-500"> (inactive)</span>}
                  <span className="block text-xs text-gray-500">{[r.department, r.location].filter(Boolean).join(' · ') || r.email}</span>
                </td>
                {kinds.map((k) => <td key={k.code} className="px-3 py-2"><CellView c={r.managers[k.code]} /></td>)}
                <td className="px-3 py-2">
                  <Button size="sm" variant="ghost" aria-label={`History for ${r.name}`} onClick={() => setHist(r)}><History className="w-4 h-4" /></Button>
                </td>
              </tr>
            ))}
            {loading && rows.length === 0 && <tr><td colSpan={colSpan} className="px-3 py-8 text-center text-gray-500">Loading…</td></tr>}
            {!loading && !error && rows.length === 0 && <tr><td colSpan={colSpan} className="px-3 py-8 text-center text-gray-500">No employees match these filters.</td></tr>}
          </tbody>
        </table>
      </Card>

      <div className="flex items-center justify-between text-sm text-gray-600">
        <span>{total === 0 ? '0 employees' : `${offset + 1}–${end} of ${total}`}</span>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" disabled={offset === 0 || loading} onClick={() => setOffset(Math.max(0, offset - LIMIT))}>Previous</Button>
          <Button size="sm" variant="outline" disabled={end >= total || loading} onClick={() => setOffset(offset + LIMIT)}>Next</Button>
        </div>
      </div>

      {assigning && (
        <AssignDialog meta={meta} picked={picked} onDrop={(ids) => setPicked((m) => { const n = new Map(m); ids.forEach((id) => n.delete(id)); return n; })} onClose={() => setAssigning(false)}
          onDone={() => { setAssigning(false); setPicked(new Map()); setBump((b) => b + 1); }} />
      )}
      {hist && <HistoryDialog meta={meta} user={hist} onClose={() => setHist(null)} onChanged={() => setBump((b) => b + 1)} />}
      {kindsOpen && <KindsDialog kinds={meta?.kinds ?? []} onClose={() => setKindsOpen(false)} onChanged={() => { onMetaChanged(); setBump((b) => b + 1); }} />}
    </div>
  );
};
