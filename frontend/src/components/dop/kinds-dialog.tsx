import React, { useState } from 'react';
import { toast } from 'sonner';
import { Badge, Button } from '../ui-elements';
import { client } from '../../api/client';
import { ENDPOINTS } from '../../api/endpoints';
import { Modal } from '../assets/modal';
import { Kind, Notice, dopErr, inputCls, labelCls, useGuard } from './dop-utils';

/** The kinds of manager (Reporting, Functional, ...). Add one, rename, switch on or off. */
export const KindsDialog: React.FC<{ kinds: Kind[]; onClose: () => void; onChanged: () => void }> = ({ kinds, onClose, onChanged }) => {
  const [code, setCode] = useState('');
  const [name, setName] = useState('');
  const [edit, setEdit] = useState<{ id: number; name: string } | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const { busy, run } = useGuard();

  const call = (fn: () => Promise<unknown>, ok: string) => run(async () => {
    setErr(null);
    try { await fn(); toast.success(ok); onChanged(); } catch (e: any) { setErr(dopErr(e, 'Could not save')); }
  });
  const add = (e: React.FormEvent) => {
    e.preventDefault();
    if (!/^[a-z][a-z0-9_]{1,39}$/.test(code)) return setErr('The short code is 2-40 characters: lowercase letters, numbers and underscores, starting with a letter.');
    if (!name.trim()) return setErr('Give the type a name.');
    call(async () => { await client.post(ENDPOINTS.DOP.KINDS, { code, name: name.trim() }); setCode(''); setName(''); }, 'Manager type added');
  };

  return (
    <Modal title="Manager types" label="Manager types" onClose={onClose} busy={busy}>
      <ul className="divide-y divide-gray-100 border border-gray-100 rounded-lg">
        {kinds.map((k) => (
          <li key={k.id} className="flex items-center justify-between gap-2 px-3 py-2 text-sm">
            {edit?.id === k.id ? (
              <form className="flex gap-2 flex-1" onSubmit={(e) => { e.preventDefault(); call(async () => { await client.patch(ENDPOINTS.DOP.KIND(k.id), { name: edit.name.trim() }); setEdit(null); }, 'Renamed'); }}>
                <input aria-label="New name" maxLength={80} className={`${inputCls} flex-1`} value={edit.name} onChange={(e) => setEdit({ id: k.id, name: e.target.value })} />
                <Button size="sm" type="submit" disabled={busy || !edit.name.trim()}>Save</Button>
                <Button size="sm" variant="outline" type="button" onClick={() => setEdit(null)}>Cancel</Button>
              </form>
            ) : (
              <>
                <span>
                  <span className={k.is_active ? 'font-medium' : 'text-gray-400'}>{k.name}</span>
                  {k.is_system && <span className="text-xs text-gray-500"> (built in)</span>}
                  {!k.is_active && <span className="ml-2"><Badge variant="neutral">Off</Badge></span>}
                </span>
                <span className="flex gap-1">
                  <Button size="sm" variant="ghost" onClick={() => setEdit({ id: k.id, name: k.name })}>Rename</Button>
                  {!k.is_system && (
                    <Button size="sm" variant="ghost" disabled={busy} onClick={() => call(() => client.patch(ENDPOINTS.DOP.KIND(k.id), { is_active: !k.is_active }), k.is_active ? 'Switched off' : 'Switched on')}>
                      {k.is_active ? 'Switch off' : 'Switch on'}
                    </Button>
                  )}
                </span>
              </>
            )}
          </li>
        ))}
        {kinds.length === 0 && <li className="px-3 py-3 text-sm text-gray-500">No manager types yet.</li>}
      </ul>
      <form onSubmit={add} className="space-y-2">
        <h4 className="text-sm font-medium text-gray-800">Add a type</h4>
        <div className="flex gap-2 flex-wrap">
          <div><label className={labelCls} htmlFor="kd-name">Name</label><input id="kd-name" maxLength={80} className={inputCls} placeholder="e.g. Project manager" value={name} onChange={(e) => setName(e.target.value)} /></div>
          <div><label className={labelCls} htmlFor="kd-code">Short code</label><input id="kd-code" maxLength={40} className={inputCls} placeholder="e.g. project_mgr" value={code} onChange={(e) => setCode(e.target.value)} /></div>
        </div>
        <Button size="sm" type="submit" isLoading={busy}>Add type</Button>
      </form>
      {err && <Notice>{err}</Notice>}
      <div className="flex justify-end"><Button variant="outline" onClick={onClose} disabled={busy}>Close</Button></div>
    </Modal>
  );
};
