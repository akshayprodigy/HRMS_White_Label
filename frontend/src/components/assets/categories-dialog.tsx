import React, { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Button } from '../ui-elements';
import { client } from '../../api/client';
import { ENDPOINTS } from '../../api/endpoints';
import { errMsg } from '../schedule-delegations-utils';
import { Modal } from './modal';
import { AssetCategory, inputCls, labelCls } from './asset-utils';

const lifeOk = (s: string) => !s.trim() || (/^\d+$/.test(s.trim()) && Number(s) > 0);

export const CategoriesDialog: React.FC<{ onClose: () => void; onChanged: () => void }> = ({ onClose, onChanged }) => {
  const [cats, setCats] = useState<AssetCategory[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [name, setName] = useState('');
  const [code, setCode] = useState('');
  const [life, setLife] = useState('');
  const [editId, setEditId] = useState<number | null>(null);
  const [eName, setEName] = useState('');
  const [eLife, setELife] = useState('');

  const load = useCallback(async () => {
    try {
      const r = await client.get<AssetCategory[]>(ENDPOINTS.ASSETS.CATEGORIES);
      setCats(r.data);
    } catch (e: any) {
      setErr(errMsg(e, 'Could not load categories'));
    }
  }, []);
  useEffect(() => { load(); }, [load]);

  const run = async (fn: () => Promise<unknown>, ok: string) => {
    setBusy(true);
    setErr(null);
    try {
      await fn();
      toast.success(ok);
      await load();
      onChanged();
      return true;
    } catch (e: any) {
      const m = errMsg(e, 'Request failed');
      setErr(m);
      toast.error(m);
      return false;
    } finally {
      setBusy(false);
    }
  };

  const add = async () => {
    if (!name.trim()) return setErr('Name is required.');
    if (!/^[A-Z0-9]{2,10}$/.test(code)) return setErr('Code must be 2-10 characters of A-Z and 0-9.');
    if (!lifeOk(life)) return setErr('Default life must be a whole number of months greater than 0.');
    const ok = await run(() => client.post(ENDPOINTS.ASSETS.CATEGORIES, {
      name: name.trim(), code, default_useful_life_months: life.trim() ? Number(life) : null,
    }), 'Category added');
    if (ok) { setName(''); setCode(''); setLife(''); }
  };

  const saveEdit = async (c: AssetCategory) => {
    if (!eName.trim()) return setErr('Name is required.');
    if (!lifeOk(eLife)) return setErr('Default life must be a whole number of months greater than 0.');
    const body: Record<string, unknown> = { name: eName.trim() };
    if (eLife.trim()) body.default_useful_life_months = Number(eLife);
    if (await run(() => client.patch(ENDPOINTS.ASSETS.CATEGORY(c.id), body), 'Category updated')) setEditId(null);
  };

  return (
    <Modal title="Asset categories" label="Asset categories" onClose={onClose} busy={busy}>
      <div className="grid grid-cols-1 md:grid-cols-4 gap-2 items-end">
        <div className="md:col-span-2">
          <label className={labelCls} htmlFor="ac-name">Name</label>
          <input id="ac-name" maxLength={80} className={`${inputCls} w-full`} value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <div>
          <label className={labelCls} htmlFor="ac-code">Code</label>
          <input id="ac-code" maxLength={10} placeholder="LAP" className={`${inputCls} w-full`} value={code}
            onChange={(e) => setCode(e.target.value.toUpperCase())} />
        </div>
        <div>
          <label className={labelCls} htmlFor="ac-life">Default life (months)</label>
          <input id="ac-life" type="number" min={1} className={`${inputCls} w-full`} value={life} onChange={(e) => setLife(e.target.value)} />
        </div>
      </div>
      <div className="flex justify-end">
        <Button size="sm" onClick={add} disabled={busy}>Add category</Button>
      </div>
      {err && <p role="alert" className="text-sm text-red-700">{err}</p>}
      <ul className="divide-y divide-gray-100 border border-gray-100 rounded-lg">
        {cats.length === 0 && <li className="p-3 text-sm text-gray-500">No categories yet.</li>}
        {cats.map((c) => (
          <li key={c.id} className="p-3 flex items-center justify-between gap-3 flex-wrap">
            {editId === c.id ? (
              <div className="flex items-center gap-2 flex-wrap">
                <input aria-label="Category name" className={inputCls} value={eName} onChange={(e) => setEName(e.target.value)} />
                <input aria-label="Default life in months" type="number" min={1} className={`${inputCls} w-24`} value={eLife}
                  onChange={(e) => setELife(e.target.value)} />
                <Button size="sm" onClick={() => saveEdit(c)} disabled={busy}>Save</Button>
                <Button size="sm" variant="outline" onClick={() => setEditId(null)}>Cancel</Button>
              </div>
            ) : (
              <>
                <div className="text-sm">
                  <span className={c.is_active ? 'font-medium text-gray-900' : 'font-medium text-gray-400'}>{c.name}</span>{' '}
                  <span className="text-xs text-gray-500">{c.code}</span>
                  <span className="text-xs text-gray-500">
                    {' '}· {c.default_useful_life_months ? `${c.default_useful_life_months} mo` : 'no default life'}
                    {c.is_active ? '' : ' · inactive'}
                  </span>
                </div>
                <div className="flex gap-2">
                  <Button size="sm" variant="outline" disabled={busy}
                    onClick={() => { setEditId(c.id); setEName(c.name); setELife(c.default_useful_life_months ? String(c.default_useful_life_months) : ''); }}>
                    Edit
                  </Button>
                  <Button size="sm" variant="outline" disabled={busy}
                    onClick={() => run(() => client.patch(ENDPOINTS.ASSETS.CATEGORY(c.id), { is_active: !c.is_active }),
                      c.is_active ? 'Category deactivated' : 'Category activated')}>
                    {c.is_active ? 'Deactivate' : 'Activate'}
                  </Button>
                </div>
              </>
            )}
          </li>
        ))}
      </ul>
      <div className="flex justify-end">
        <Button variant="outline" onClick={onClose} disabled={busy}>Close</Button>
      </div>
    </Modal>
  );
};
