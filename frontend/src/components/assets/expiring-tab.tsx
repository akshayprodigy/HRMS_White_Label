import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Card } from '../ui-elements';
import { client } from '../../api/client';
import { ENDPOINTS } from '../../api/endpoints';
import { errMsg } from '../schedule-delegations-utils';
import { Th } from '../biometric/shared';
import { Asset, daysUntil, fmtDate, holderText, inputCls, labelCls } from './asset-utils';

const nearest = (a: Asset): number | null => {
  const ds = [daysUntil(a.warranty_expiry), daysUntil(a.amc_expiry)].filter((d): d is number => d != null && d >= 0);
  return ds.length ? Math.min(...ds) : null;
};

export const ExpiringTab: React.FC<{ refreshKey: number; onOpen: (id: number) => void }> = ({ refreshKey, onOpen }) => {
  const [days, setDays] = useState('30');
  const [items, setItems] = useState<Asset[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const seq = useRef(0);
  const load = useCallback(async () => {
    const id = ++seq.current;
    setLoading(true);
    try {
      const r = await client.get<{ items: Asset[]; total: number }>(ENDPOINTS.ASSETS.LIST, {
        params: { expiring_within_days: Number(days), limit: 200 },
      });
      if (id !== seq.current) return;
      const items = [...r.data.items].sort((a, b) => (nearest(a) ?? 9999) - (nearest(b) ?? 9999));
      setItems(items);
      setTotal(r.data.total);
      setError(null);
    } catch (e: any) {
      if (id === seq.current) setError(errMsg(e, 'Failed to load expiring assets'));
    } finally {
      if (id === seq.current) setLoading(false);
    }
  }, [days]);
  useEffect(() => { load(); }, [load, refreshKey]);

  return (
    <div className="space-y-4">
      <div>
        <label className={labelCls} htmlFor="ex-days">Expiring within</label>
        <select id="ex-days" className={inputCls} value={days} onChange={(e) => setDays(e.target.value)}>
          <option value="30">30 days</option><option value="60">60 days</option><option value="90">90 days</option>
        </select>
      </div>
      {error && <div role="alert" className="p-3 rounded-lg bg-red-50 text-sm text-red-700">{error}</div>}
      {total > items.length && <p className="text-sm text-amber-800">Showing the first {items.length} of {total}.</p>}
      <Card className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-100">
              <Th>Tag</Th><Th>Name</Th><Th>Holder</Th><Th>Warranty expiry</Th><Th>AMC</Th><Th className="text-right">Days left</Th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {items.map((a) => {
              const d = nearest(a);
              return (
                <tr key={a.id} className="cursor-pointer hover:bg-gray-50" onClick={() => onOpen(a.id)}>
                  <td className="px-3 py-2 font-medium text-gray-900 whitespace-nowrap">{a.asset_tag}</td>
                  <td className="px-3 py-2">{a.name}</td>
                  <td className="px-3 py-2">{holderText(a.holder)}</td>
                  <td className="px-3 py-2 whitespace-nowrap">{fmtDate(a.warranty_expiry)}</td>
                  <td className="px-3 py-2 whitespace-nowrap">{a.amc_vendor ? `${a.amc_vendor} · ` : ''}{fmtDate(a.amc_expiry)}</td>
                  <td className={`px-3 py-2 text-right ${d != null && d <= 7 ? 'text-red-700 font-semibold' : ''}`}>{d ?? '—'}</td>
                </tr>
              );
            })}
            {!loading && !error && items.length === 0 && (
              <tr><td colSpan={6} className="px-3 py-8 text-center text-gray-500">Nothing expires in this window.</td></tr>
            )}
          </tbody>
        </table>
      </Card>
    </div>
  );
};
