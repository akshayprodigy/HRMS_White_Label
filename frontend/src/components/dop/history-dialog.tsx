import React, { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Badge, Button, fmtDate } from '../ui-elements';
import { client } from '../../api/client';
import { ENDPOINTS } from '../../api/endpoints';
import { Modal } from '../assets/modal';
import { Assignment, ManagerRow, Meta, Notice, STATUS_TEXT, STATUS_VARIANT, dopErr, inputCls, subText, useGuard, useOrgDate } from './dop-utils';

const who = (a: Assignment) =>
  a.scope_type === 'user' ? 'This employee'
    : a.scope_type === 'department' ? `Everyone in ${a.scope_department_name ?? 'a department'}`
      : a.scope_type === 'location' ? `Everyone at ${a.scope_location}` : 'Everyone in the company';

/** Every manager assignment that applies to one employee, with End. */
export const HistoryDialog: React.FC<{ meta: Meta | null; user: ManagerRow; onClose: () => void; onChanged: () => void }> = ({ meta, user, onClose, onChanged }) => {
  const [rows, setRows] = useState<Assignment[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [ending, setEnding] = useState<number | null>(null);
  const { today, ready } = useOrgDate();
  const [endDate, setEndDate] = useState('');
  const { busy, run } = useGuard();

  const load = useCallback(async () => {
    try {
      const r = await client.get(ENDPOINTS.DOP.ASSIGNMENTS, { params: { user_id: user.user_id, history: true, limit: 200 } });
      setRows(r.data.items); setErr(null);
    } catch (e: any) { setErr(dopErr(e, 'Could not load the history')); setRows((x) => x ?? []); }
  }, [user.user_id]);
  useEffect(() => { load(); }, [load]);

  const end = (a: Assignment) => run(async () => {
    setErr(null);
    if (!endDate) return setErr('Choose the last day.');
    try {
      await client.post(ENDPOINTS.DOP.ASSIGNMENT_END(a.id), { ends_on: endDate });
      toast.success('Assignment ended'); setEnding(null); onChanged(); await load();
    } catch (e: any) { setErr(dopErr(e, 'Could not end it')); }
  });

  return (
    <Modal title={`Managers of ${user.name}`} label={`Manager history for ${user.name}`} onClose={onClose} busy={busy} wide>
      {err && <Notice>{err}</Notice>}
      {rows === null && <p className="text-sm text-gray-500">Loading…</p>}
      {rows?.length === 0 && !err && <p className="text-sm text-gray-500">No manager has ever been set for this employee.</p>}
      <ul className="space-y-2">
        {rows?.map((a) => {
          const open = a.status === 'live' || a.status === 'scheduled';
          return (
            <li key={a.id} className="border border-gray-100 rounded-lg p-3 text-sm space-y-1">
              <div className="flex items-center justify-between gap-2 flex-wrap">
                <span className="font-medium">{a.kind_name}: {a.manager_user_name ?? `post ${a.manager_post_title}`}</span>
                <Badge variant={STATUS_VARIANT[a.status] ?? 'neutral'}>{STATUS_TEXT[a.status] ?? a.status}</Badge>
              </div>
              <p className="text-xs text-gray-600">{who(a)} · {subText(a.subdomains, meta)} · {fmtDate(a.starts_on)} to {a.ends_on ? fmtDate(a.ends_on) : 'no end date'}{a.note ? ` · ${a.note}` : ''}</p>
              {open && ending !== a.id && <Button size="sm" variant="outline" disabled={!ready} onClick={() => { setEnding(a.id); setEndDate(today); }}>End</Button>}
              {ending === a.id && (
                <div className="space-y-2 pt-1">
                  {a.scope_type !== 'user' && <Notice tone="warn">This one is shared. Ending it ends it for everyone it covers, not only {user.name}.</Notice>}
                  <div className="flex items-end gap-2 flex-wrap">
                    <div>
                      <label className="block text-xs font-medium text-gray-600 mb-1" htmlFor={`hd-end-${a.id}`}>Last day</label>
                      <input id={`hd-end-${a.id}`} type="date" min={a.status === 'scheduled' ? undefined : a.starts_on} className={inputCls} value={endDate} onChange={(e) => setEndDate(e.target.value)} />
                    </div>
                    <Button size="sm" variant="danger" isLoading={busy} onClick={() => end(a)}>End it</Button>
                    <Button size="sm" variant="outline" disabled={busy} onClick={() => setEnding(null)}>Cancel</Button>
                  </div>
                </div>
              )}
            </li>
          );
        })}
      </ul>
      <div className="flex justify-end"><Button variant="outline" onClick={onClose} disabled={busy}>Close</Button></div>
    </Modal>
  );
};
