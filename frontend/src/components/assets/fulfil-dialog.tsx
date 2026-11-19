import React, { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Button } from '../ui-elements';
import { client } from '../../api/client';
import { ENDPOINTS } from '../../api/endpoints';
import { errMsg } from '../schedule-delegations-utils';
import { Modal } from './modal';
import { Asset, AssetRequest, inputCls, labelCls, serverSafeToday } from './asset-utils';

export const FulfilDialog: React.FC<{ req: AssetRequest; onClose: () => void; onDone: () => void }> = ({ req, onClose, onDone }) => {
  const [all, setAll] = useState(false);
  const [q, setQ] = useState('');
  const [dq, setDq] = useState('');
  const [items, setItems] = useState<Asset[]>([]);
  const [pick, setPick] = useState<Asset | null>(null);
  const [date, setDate] = useState(serverSafeToday());
  const [dateTouched, setDateTouched] = useState(false);
  const [listErr, setListErr] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [condition, setCondition] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    const t = window.setTimeout(() => setDq(q.trim()), 300);
    return () => window.clearTimeout(t);
  }, [q]);

  useEffect(() => {
    let live = true;
    setLoaded(false);
    const params: Record<string, unknown> = { status: 'in_stock', limit: 50 };
    if (!all) params.category_id = req.category.id;
    if (dq) params.q = dq;
    client.get<{ items: Asset[] }>(ENDPOINTS.ASSETS.LIST, { params })
      .then((r) => { if (live) { setItems(r.data.items); setListErr(null); setLoaded(true); } })
      .catch((e) => { if (live) { setListErr(errMsg(e, 'Could not load assets')); setLoaded(true); } });
    return () => { live = false; };
  }, [all, dq, req.category.id]);

  const submit = async () => {
    if (!pick) return setErr('Choose an asset to issue.');
    setBusy(true);
    setErr(null);
    try {
      await client.post(ENDPOINTS.ASSETS.REQUEST_FULFIL(req.id), {
        asset_id: pick.id, issued_date: dateTouched && date ? date : undefined, condition: condition.trim() || null,
        allow_other_category: pick.category.id !== req.category.id,
      });
      toast.success(`${pick.asset_tag} issued to ${req.employee.name}`);
      onDone();
    } catch (e: any) {
      const m = errMsg(e, 'Could not fulfil the request');
      setErr(m);
      toast.error(m);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal title={`Fulfil request #${req.id}`} label="Fulfil request" onClose={onClose} busy={busy}>
      <p className="text-sm text-gray-600">{req.employee.name} requested {req.category.name}.</p>
      <div className="flex items-end gap-3 flex-wrap">
        <div className="flex-1">
          <label className={labelCls} htmlFor="fl-q">Search in-stock assets</label>
          <input id="fl-q" className={`${inputCls} w-full`} value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
        <label className="flex items-center gap-2 text-sm text-gray-700 pb-2">
          <input type="checkbox" checked={all} onChange={(e) => setAll(e.target.checked)} />Show all categories
        </label>
      </div>
      {listErr && <p role="alert" className="text-sm text-red-700">{listErr}</p>}
      <ul role="radiogroup" aria-label="In-stock assets" className="max-h-56 overflow-y-auto border border-gray-100 rounded-lg divide-y divide-gray-100">
        {loaded && !listErr && items.length === 0 && <li className="p-3 text-sm text-gray-500">No in-stock assets found.</li>}
        {items.map((a) => (
          <li key={a.id}>
            <button type="button" role="radio" aria-checked={pick?.id === a.id} onClick={() => setPick(a)}
              className={`w-full text-left px-3 py-2 text-sm hover:bg-gray-50 ${pick?.id === a.id ? 'bg-indigo-50' : ''}`}>
              <span className="font-medium">{a.asset_tag}</span> {a.name}
              <span className="text-xs text-gray-500"> · {a.category.name}</span>
            </button>
          </li>
        ))}
      </ul>
      {pick && pick.category.id !== req.category.id && (
        <p className="text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded-lg p-2">
          This asset is in a different category ({pick.category.name}) than requested.
        </p>
      )}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div>
          <label className={labelCls} htmlFor="fl-date">Issue date</label>
          <input id="fl-date" type="date" max={serverSafeToday()} className={`${inputCls} w-full`} value={date} onChange={(e) => { setDate(e.target.value); setDateTouched(true); }} />
        </div>
        <div>
          <label className={labelCls} htmlFor="fl-cond">Condition</label>
          <input id="fl-cond" maxLength={50} className={`${inputCls} w-full`} value={condition} onChange={(e) => setCondition(e.target.value)} />
        </div>
      </div>
      {err && <p role="alert" className="text-sm text-red-700">{err}</p>}
      <div className="flex justify-end gap-2">
        <Button variant="outline" onClick={onClose} disabled={busy}>Cancel</Button>
        <Button onClick={submit} isLoading={busy}>Issue asset</Button>
      </div>
    </Modal>
  );
};
