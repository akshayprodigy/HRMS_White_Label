import React, { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Button } from '../ui-elements';
import { client } from '../../api/client';
import { ENDPOINTS } from '../../api/endpoints';
import { errMsg } from '../schedule-delegations-utils';
import { Modal } from './modal';
import { Asset, inputCls, labelCls } from './asset-utils';
import { orgToday } from '../../lib/org-time';

/** Allocate an in-stock register asset to one employee (Employee primary key). */
export const AllocateFromRegisterDialog: React.FC<{
  empId: number | string;
  onClose: () => void;
  onDone: () => void;
}> = ({ empId, onClose, onDone }) => {
  const [q, setQ] = useState('');
  const [dq, setDq] = useState('');
  const [items, setItems] = useState<Asset[]>([]);
  const [pick, setPick] = useState<Asset | null>(null);
  const [date, setDate] = useState(orgToday());
  const [dateTouched, setDateTouched] = useState(false);
  const [condition, setCondition] = useState('');
  const [remarks, setRemarks] = useState('');
  const [listErr, setListErr] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
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
    if (dq) params.q = dq;
    client.get<{ items: Asset[] }>(ENDPOINTS.ASSETS.LIST, { params })
      .then((r) => { if (live) { setItems(r.data.items); setListErr(null); setLoaded(true); } })
      .catch((e) => { if (live) { setListErr(errMsg(e, 'Could not load assets')); setLoaded(true); } });
    return () => { live = false; };
  }, [dq]);

  // The selection may not be in the new result list: clear it.
  useEffect(() => { setPick(null); }, [dq]);

  const submit = async () => {
    if (!pick) return setErr('Choose an asset to allocate.');
    setBusy(true);
    setErr(null);
    try {
      await client.post(ENDPOINTS.ASSETS.ALLOCATE(pick.id), {
        employee_id: Number(empId),
        issued_date: dateTouched && date ? date : undefined,
        condition: condition.trim() || null,
        remarks: remarks.trim() || null,
      });
      toast.success(`${pick.asset_tag} allocated`);
      onDone();
    } catch (e: any) {
      const m = errMsg(e, 'Could not allocate the asset');
      setErr(m);
      toast.error(m);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal title="Allocate from register" label="Allocate from register" onClose={onClose} busy={busy}>
      <div>
        <label className={labelCls} htmlFor="ea-q">Search in-stock assets</label>
        <input id="ea-q" className={`${inputCls} w-full`} value={q} onChange={(e) => setQ(e.target.value)} />
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
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div>
          <label className={labelCls} htmlFor="ea-date">Issue date</label>
          <input id="ea-date" type="date" max={orgToday()} className={`${inputCls} w-full`} value={date} onChange={(e) => { setDate(e.target.value); setDateTouched(true); }} />
        </div>
        <div>
          <label className={labelCls} htmlFor="ea-cond">Condition</label>
          <input id="ea-cond" maxLength={50} className={`${inputCls} w-full`} value={condition} onChange={(e) => setCondition(e.target.value)} />
        </div>
      </div>
      <div>
        <label className={labelCls} htmlFor="ea-rem">Remarks</label>
        <textarea id="ea-rem" rows={2} className={`${inputCls} w-full h-auto py-2`} value={remarks} onChange={(e) => setRemarks(e.target.value)} />
      </div>
      {err && <p role="alert" className="text-sm text-red-700">{err}</p>}
      <div className="flex justify-end gap-2">
        <Button variant="outline" onClick={onClose} disabled={busy}>Cancel</Button>
        <Button onClick={submit} isLoading={busy}>Allocate</Button>
      </div>
    </Modal>
  );
};

/** Return / mark-lost for a register-backed allocation row. */
export const RowActionDialog: React.FC<{
  kind: 'return' | 'lost';
  assetId: number;
  label: string;
  onClose: () => void;
  onDone: () => void;
}> = ({ kind, assetId, label, onClose, onDone }) => {
  const [toStatus, setToStatus] = useState('in_stock');
  const [date, setDate] = useState(orgToday());
  const [dateTouched, setDateTouched] = useState(false);
  const [condition, setCondition] = useState('');
  const [remarks, setRemarks] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const submit = async () => {
    if (kind === 'lost' && remarks.trim().length < 3) return setErr('Remarks are required (at least 3 characters).');
    setBusy(true);
    setErr(null);
    try {
      if (kind === 'return') {
        await client.post(ENDPOINTS.ASSETS.RETURN(assetId), {
          returned_date: dateTouched && date ? date : undefined,
          condition: condition.trim() || null,
          remarks: remarks.trim() || null,
          to_status: toStatus,
        });
        toast.success('Asset returned');
      } else {
        await client.post(ENDPOINTS.ASSETS.LOST(assetId), { remarks: remarks.trim() });
        toast.success('Asset marked as lost');
      }
      onDone();
    } catch (e: any) {
      const m = errMsg(e, 'Action failed');
      setErr(m);
      toast.error(m);
    } finally {
      setBusy(false);
    }
  };

  const title = kind === 'return' ? `Return asset — ${label}` : `Mark as lost — ${label}`;
  return (
    <Modal title={title} label={kind === 'return' ? 'Return asset' : 'Mark asset as lost'} onClose={onClose} busy={busy}>
      {kind === 'return' && (
        <>
          <div>
            <label className={labelCls} htmlFor="er-to">Return to</label>
            <select id="er-to" className={`${inputCls} w-full`} value={toStatus} onChange={(e) => setToStatus(e.target.value)}>
              <option value="in_stock">In stock</option>
              <option value="in_repair">In repair</option>
              <option value="retired">Retired</option>
            </select>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <label className={labelCls} htmlFor="er-date">Return date</label>
              <input id="er-date" type="date" max={orgToday()} className={`${inputCls} w-full`} value={date} onChange={(e) => { setDate(e.target.value); setDateTouched(true); }} />
            </div>
            <div>
              <label className={labelCls} htmlFor="er-cond">Condition</label>
              <input id="er-cond" maxLength={50} className={`${inputCls} w-full`} value={condition} onChange={(e) => setCondition(e.target.value)} />
            </div>
          </div>
        </>
      )}
      <div>
        <label className={labelCls} htmlFor="er-rem">Remarks{kind === 'lost' ? ' *' : ''}</label>
        <textarea id="er-rem" rows={2} className={`${inputCls} w-full h-auto py-2`} value={remarks} onChange={(e) => setRemarks(e.target.value)} />
      </div>
      {err && <p role="alert" className="text-sm text-red-700">{err}</p>}
      <div className="flex justify-end gap-2">
        <Button variant="outline" onClick={onClose} disabled={busy}>Cancel</Button>
        <Button variant={kind === 'lost' ? 'danger' : 'primary'} onClick={submit} isLoading={busy}>Confirm</Button>
      </div>
    </Modal>
  );
};
