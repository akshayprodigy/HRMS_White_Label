import React, { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Button, Card } from '../ui-elements';
import { client } from '../../api/client';
import { ENDPOINTS } from '../../api/endpoints';
import { errMsg } from '../schedule-delegations-utils';
import { Asset, KIND_LABEL, Maintenance, fmtDate, fmtInr } from './asset-utils';

const CAP = 50;
interface Row { asset: Asset; open: Maintenance[] }

export const MaintenanceTab: React.FC<{
  refreshKey: number; onOpen: (id: number) => void; onChanged: () => void;
}> = ({ refreshKey, onOpen, onChanged }) => {
  const [rows, setRows] = useState<Row[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await client.get<{ items: Asset[]; total: number }>(ENDPOINTS.ASSETS.LIST, { params: { status: 'in_repair', limit: CAP } });
      const full = await Promise.all(r.data.items.map(async (asset) => {
        const m = await client.get<Maintenance[]>(ENDPOINTS.ASSETS.MAINTENANCE(asset.id));
        return { asset, open: m.data.filter((x) => !x.completed_on) };
      }));
      setRows(full);
      setTotal(r.data.total);
      setError(null);
    } catch (e: any) {
      setError(errMsg(e, 'Failed to load maintenance'));
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => { load(); }, [load, refreshKey]);

  const complete = async (m: Maintenance) => {
    setBusyId(m.id);
    try {
      await client.patch(ENDPOINTS.ASSETS.MAINTENANCE_ITEM(m.id), { complete: true, return_to_stock: true });
      toast.success('Maintenance completed');
      await load();
      onChanged();
    } catch (e: any) {
      toast.error(errMsg(e, 'Could not complete maintenance'));
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="space-y-4">
      {error && <div role="alert" className="p-3 rounded-lg bg-red-50 text-sm text-red-700">{error}</div>}
      {total > CAP && <p className="text-sm text-amber-800">Showing the first {CAP} of {total} assets in repair.</p>}
      {!loading && !error && rows.length === 0 && <Card className="p-8 text-center text-sm text-gray-500">No assets are in repair.</Card>}
      {rows.map(({ asset, open }) => (
        <Card key={asset.id} className="p-4 space-y-2">
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <div className="text-sm">
              <span className="font-medium text-gray-900">{asset.asset_tag}</span> {asset.name}
              <span className="text-xs text-gray-500"> · {asset.category.name}</span>
            </div>
            <Button size="sm" variant="outline" onClick={() => onOpen(asset.id)}>Open asset</Button>
          </div>
          {open.length === 0 ? (
            <p className="text-sm text-gray-500">No open maintenance entries.</p>
          ) : (
            <ul className="divide-y divide-gray-100 border border-gray-100 rounded-lg">
              {open.map((m) => (
                <li key={m.id} className="p-3 flex items-start justify-between gap-3 flex-wrap">
                  <div className="text-sm">
                    <div className="font-medium text-gray-900">{KIND_LABEL[m.kind] ?? m.kind} · {fmtInr(m.cost_paise)}</div>
                    <div className="text-gray-600">{m.description}</div>
                    <div className="text-xs text-gray-500">{m.vendor ? `${m.vendor} · ` : ''}since {fmtDate(m.started_on)}</div>
                  </div>
                  <Button size="sm" disabled={busyId === m.id} onClick={() => complete(m)}>Complete</Button>
                </li>
              ))}
            </ul>
          )}
        </Card>
      ))}
    </div>
  );
};
