import React, { useCallback, useEffect, useRef, useState } from 'react';
import { History, Settings2, UserPlus } from 'lucide-react';
import { Badge, Button, Card } from '../ui-elements';
import { client } from '../../api/client';
import { ENDPOINTS } from '../../api/endpoints';
import { Th } from '../biometric/shared';
import { AssignDialog } from './assign-dialog';
import { HistoryDialog } from './history-dialog';
import { KindsDialog } from './kinds-dialog';
import { Cell, ManagerRow, Meta, Notice, SOURCE_LABEL, dopErr, inputCls, labelCls } from './dop-utils';

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
      const r = await client.get(ENDPOINTS.DOP.MANAGERS, { params });
      if (n !== seq.current) return;
      setRows(r.data.items); setTotal(r.data.total); setKinds(r.data.kinds); setError(null);
    } catch (e: any) {
      if (n === seq.current) { setRows([]); setError(dopErr(e, 'Could not load managers')); }
    } finally {
      if (n === seq.current) setLoading(false);
    }
  }, [dq, dept, missing, offset]);
  useEffect(() => { load(); }, [load, refreshKey, bump]);

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
        <Button variant="outline" size="sm" onClick={() => setKindsOpen(true)}><Settings2 className="w-4 h-4 mr-1" />Manager types</Button>
        <Button size="sm" onClick={() => setAssigning(true)}><UserPlus className="w-4 h-4 mr-1" />Assign managers</Button>
      </div>

      <p className="text-xs text-gray-500">This grid shows managers who cover everything. A manager limited to certain areas is listed under History (the clock icon).</p>
      {picked.size > 0 && (
        <div className="flex items-center gap-3 flex-wrap text-sm bg-indigo-50 text-indigo-800 rounded-lg px-3 py-2" role="status">
          <span><strong>{picked.size}</strong> {picked.size === 1 ? 'employee' : 'employees'} selected (up to {MAX_PICK})</span>
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
        <AssignDialog meta={meta} picked={picked} onClose={() => setAssigning(false)}
          onDone={() => { setAssigning(false); setPicked(new Map()); setBump((b) => b + 1); }} />
      )}
      {hist && <HistoryDialog meta={meta} user={hist} onClose={() => setHist(null)} onChanged={() => setBump((b) => b + 1)} />}
      {kindsOpen && <KindsDialog kinds={meta?.kinds ?? []} onClose={() => setKindsOpen(false)} onChanged={() => { onMetaChanged(); setBump((b) => b + 1); }} />}
    </div>
  );
};
