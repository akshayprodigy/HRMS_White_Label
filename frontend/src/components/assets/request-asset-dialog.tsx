import React, { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Button } from '../ui-elements';
import { client } from '../../api/client';
import { ENDPOINTS } from '../../api/endpoints';
import { errMsg } from '../schedule-delegations-utils';
import { Modal } from './modal';
import { inputCls, labelCls, clientSafeMinToday } from './asset-utils';

interface Cat { id: number; name: string; code: string }

export const RequestAssetDialog: React.FC<{ onClose: () => void; onDone: () => void }> = ({ onClose, onDone }) => {
  const [cats, setCats] = useState<Cat[]>([]);
  const [catsErr, setCatsErr] = useState<string | null>(null);
  const [cat, setCat] = useState('');
  const [reason, setReason] = useState('');
  const [needed, setNeeded] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    client.get<Cat[]>(ENDPOINTS.ASSETS.REQUEST_CATEGORIES)
      .then((r) => { if (live) setCats(r.data); })
      .catch((e) => { if (live) setCatsErr(errMsg(e, 'Could not load categories')); });
    return () => { live = false; };
  }, []);

  const submit = async () => {
    const rs = reason.trim();
    if (!cat) return setErr('Choose a category.');
    if (rs.length < 5) return setErr('Reason must be at least 5 characters.');
    if (rs.length > 1000) return setErr('Reason must be at most 1000 characters.');
    setBusy(true);
    setErr(null);
    try {
      await client.post(ENDPOINTS.ASSETS.REQUESTS, {
        category_id: Number(cat), reason: rs, needed_by: needed || undefined,
      });
      toast.success('Asset request submitted');
      onDone();
    } catch (e: any) {
      const m = errMsg(e, 'Could not submit the request');
      setErr(m);
      toast.error(m);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal title="Request an asset" label="Request an asset" onClose={onClose} busy={busy}>
      <div>
        <label className={labelCls} htmlFor="ra-cat">Category *</label>
        <select id="ra-cat" className={`${inputCls} w-full`} value={cat} onChange={(e) => setCat(e.target.value)}>
          <option value="">Select a category</option>
          {cats.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
        {catsErr && <p role="alert" className="text-sm text-red-700 mt-1">{catsErr}</p>}
      </div>
      <div>
        <label className={labelCls} htmlFor="ra-reason">Reason * (5–1000 characters)</label>
        <textarea id="ra-reason" rows={3} maxLength={1000} className={`${inputCls} w-full h-auto py-2`} value={reason} onChange={(e) => setReason(e.target.value)} />
      </div>
      <div>
        <label className={labelCls} htmlFor="ra-needed">Needed by (optional)</label>
        <input id="ra-needed" type="date" min={clientSafeMinToday()} className={`${inputCls} w-full`} value={needed} onChange={(e) => setNeeded(e.target.value)} />
      </div>
      {err && <p role="alert" className="text-sm text-red-700">{err}</p>}
      <div className="flex justify-end gap-2">
        <Button variant="outline" onClick={onClose} disabled={busy}>Cancel</Button>
        <Button onClick={submit} isLoading={busy}>Submit request</Button>
      </div>
    </Modal>
  );
};
