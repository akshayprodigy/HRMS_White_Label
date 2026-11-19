import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Plus, Tags } from 'lucide-react';
import { Badge, Button, Card } from '../ui-elements';
import { client } from '../../api/client';
import { ENDPOINTS } from '../../api/endpoints';
import { errMsg } from '../schedule-delegations-utils';
import { Th } from '../biometric/shared';
import {
  Asset, AssetCategory, AssetStatus, STATUS_BADGE, STATUS_LABEL, expiringSoon, fmtDate, fmtInr, holderText, inputCls,
} from './asset-utils';

const LIMIT = 50;

export const RegisterTab: React.FC<{
  refreshKey: number;
  onOpen: (id: number) => void;
  onAdd: () => void;
  onCategories: () => void;
}> = ({ refreshKey, onOpen, onAdd, onCategories }) => {
  const [items, setItems] = useState<Asset[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [status, setStatus] = useState('');
  const [categoryId, setCategoryId] = useState('');
  const [q, setQ] = useState('');
  const [dq, setDq] = useState('');
  const [cats, setCats] = useState<AssetCategory[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const reqRef = useRef(0);

  useEffect(() => {
    const t = window.setTimeout(() => { setDq(q.trim()); setOffset(0); }, 300);
    return () => window.clearTimeout(t);
  }, [q]);

  useEffect(() => {
    client.get<AssetCategory[]>(ENDPOINTS.ASSETS.CATEGORIES).then((r) => setCats(r.data)).catch(() => setCats([]));
  }, [refreshKey]);

  const load = useCallback(async () => {
    const id = ++reqRef.current;
    setLoading(true);
    try {
      const params: Record<string, unknown> = { limit: LIMIT, offset };
      if (status) params.status = status;
      if (categoryId) params.category_id = Number(categoryId);
      if (dq) params.q = dq;
      const r = await client.get<{ items: Asset[]; total: number }>(ENDPOINTS.ASSETS.LIST, { params });
      if (id !== reqRef.current) return;
      setItems(r.data.items);
      setTotal(r.data.total);
      setError(null);
    } catch (e: any) {
      if (id === reqRef.current) setError(errMsg(e, 'Failed to load assets'));
    } finally {
      if (id === reqRef.current) setLoading(false);
    }
  }, [status, categoryId, dq, offset]);

  useEffect(() => { load(); }, [load, refreshKey]);

  const end = Math.min(offset + LIMIT, total);
  return (
    <div className="space-y-4">
      <div className="flex items-end gap-3 flex-wrap">
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1" htmlFor="ar-status">Status</label>
          <select id="ar-status" className={inputCls} value={status} onChange={(e) => { setStatus(e.target.value); setOffset(0); }}>
            <option value="">All</option>
            {(Object.keys(STATUS_LABEL) as AssetStatus[]).map((s) => <option key={s} value={s}>{STATUS_LABEL[s]}</option>)}
          </select>
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1" htmlFor="ar-cat">Category</label>
          <select id="ar-cat" className={inputCls} value={categoryId} onChange={(e) => { setCategoryId(e.target.value); setOffset(0); }}>
            <option value="">All</option>
            {cats.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </div>
        <div className="flex-1">
          <label className="block text-xs font-medium text-gray-600 mb-1" htmlFor="ar-q">Search</label>
          <input id="ar-q" className={`${inputCls} w-full`} placeholder="Tag, name, serial or holder" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
        <Button variant="outline" size="sm" onClick={onCategories}><Tags className="w-4 h-4 mr-1" />Categories</Button>
        <Button size="sm" onClick={onAdd}><Plus className="w-4 h-4 mr-1" />Add asset</Button>
      </div>

      {error && <div role="alert" className="p-3 rounded-lg bg-red-50 text-sm text-red-700">{error}</div>}

      <Card className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-100">
              <Th>Tag</Th><Th>Name</Th><Th>Category</Th><Th>Status</Th><Th>Holder</Th><Th>Warranty</Th><Th className="text-right">Book value</Th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {items.map((a) => (
              <tr key={a.id} className="cursor-pointer hover:bg-gray-50" onClick={() => onOpen(a.id)}>
                <td className="px-3 py-2 font-medium text-gray-900 whitespace-nowrap">{a.asset_tag}</td>
                <td className="px-3 py-2">{a.name}{a.model ? <span className="text-xs text-gray-500"> {a.model}</span> : null}</td>
                <td className="px-3 py-2">{a.category.name}</td>
                <td className="px-3 py-2"><Badge variant={STATUS_BADGE[a.status]}>{STATUS_LABEL[a.status]}</Badge></td>
                <td className="px-3 py-2">{holderText(a.holder)}</td>
                <td className={`px-3 py-2 whitespace-nowrap ${expiringSoon(a.warranty_expiry) ? 'text-amber-700 font-medium' : ''}`}>
                  {fmtDate(a.warranty_expiry)}
                </td>
                <td className="px-3 py-2 text-right whitespace-nowrap">{fmtInr(a.book_value_paise)}</td>
              </tr>
            ))}
            {!loading && !error && items.length === 0 && (
              <tr><td colSpan={7} className="px-3 py-8 text-center text-gray-500">No assets match these filters.</td></tr>
            )}
            {loading && items.length === 0 && (
              <tr><td colSpan={7} className="px-3 py-8 text-center text-gray-500">Loading…</td></tr>
            )}
          </tbody>
        </table>
      </Card>

      <div className="flex items-center justify-between text-sm text-gray-600">
        <span>{total === 0 ? '0 assets' : `${offset + 1}–${end} of ${total}`}</span>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" disabled={offset === 0 || loading} onClick={() => setOffset(Math.max(0, offset - LIMIT))}>Previous</Button>
          <Button size="sm" variant="outline" disabled={end >= total || loading} onClick={() => setOffset(offset + LIMIT)}>Next</Button>
        </div>
      </div>
    </div>
  );
};
