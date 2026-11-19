import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { toast } from 'sonner';
import { Badge, Button, Card } from '../ui-elements';
import { client } from '../../api/client';
import { ENDPOINTS } from '../../api/endpoints';
import { errMsg } from '../schedule-delegations-utils';
import { Th } from '../biometric/shared';
import { Modal } from './modal';
import { FulfilDialog } from './fulfil-dialog';
import { AssetRequest, REQ_BADGE, fmtDate, inputCls, labelCls } from './asset-utils';

const STATUSES = ['pending', 'approved', 'rejected', 'fulfilled', 'cancelled'] as const;

const DecideDialog: React.FC<{
  req: AssetRequest; action: 'approve' | 'reject'; onClose: () => void; onDone: () => void;
}> = ({ req, action, onClose, onDone }) => {
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const submit = async () => {
    setBusy(true);
    setErr(null);
    try {
      await client.post(ENDPOINTS.ASSETS.REQUEST_DECIDE(req.id), { action, note: note.trim() || null });
      toast.success(action === 'approve' ? 'Request approved' : 'Request rejected');
      onDone();
    } catch (e: any) {
      const m = errMsg(e, 'Could not record the decision');
      setErr(m);
      toast.error(m);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal title={`${action === 'approve' ? 'Approve' : 'Reject'} request #${req.id}`} label="Decide request" onClose={onClose} busy={busy}>
      <p className="text-sm text-gray-600">{req.employee.name} · {req.category.name}</p>
      <div>
        <label className={labelCls} htmlFor="rq-note">Note (optional)</label>
        <textarea id="rq-note" rows={2} maxLength={500} className={`${inputCls} w-full h-auto py-2`} value={note} onChange={(e) => setNote(e.target.value)} />
      </div>
      {err && <p role="alert" className="text-sm text-red-700">{err}</p>}
      <div className="flex justify-end gap-2">
        <Button variant="outline" onClick={onClose} disabled={busy}>Cancel</Button>
        <Button variant={action === 'reject' ? 'danger' : 'primary'} onClick={submit} isLoading={busy}>
          {action === 'approve' ? 'Approve' : 'Reject'}
        </Button>
      </div>
    </Modal>
  );
};

export const RequestsTab: React.FC<{ refreshKey: number; onChanged: () => void }> = ({ refreshKey, onChanged }) => {
  const [filter, setFilter] = useState('open');
  const [rows, setRows] = useState<AssetRequest[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [decide, setDecide] = useState<{ req: AssetRequest; action: 'approve' | 'reject' } | null>(null);
  const [fulfil, setFulfil] = useState<AssetRequest | null>(null);

  const sel = useMemo(
    () => (filter === 'open' ? ['pending', 'approved'] : filter === 'all' ? [...STATUSES] : [filter]),
    [filter],
  );
  const seq = useRef(0);

  const load = useCallback(async () => {
    const id = ++seq.current;
    setLoading(true);
    try {
      const r = await client.get<AssetRequest[]>(ENDPOINTS.ASSETS.REQUESTS, {
        params: { status: sel }, paramsSerializer: { indexes: null },
      });
      if (id !== seq.current) return;
      setRows(r.data);
      setError(null);
    } catch (e: any) {
      if (id === seq.current) setError(errMsg(e, 'Failed to load requests'));
    } finally {
      if (id === seq.current) setLoading(false);
    }
  }, [sel]);
  useEffect(() => { load(); }, [load, refreshKey]);

  const done = () => { setDecide(null); setFulfil(null); onChanged(); }; // bump -> refreshKey reloads

  return (
    <div className="space-y-4">
      <div>
        <label className={labelCls} htmlFor="rq-filter">Status</label>
        <select id="rq-filter" className={inputCls} value={filter} onChange={(e) => setFilter(e.target.value)}>
          <option value="open">Pending + approved</option>
          <option value="all">All</option>
          {STATUSES.map((s) => <option key={s} value={s}>{s[0].toUpperCase() + s.slice(1)}</option>)}
        </select>
      </div>
      {error && <div role="alert" className="p-3 rounded-lg bg-red-50 text-sm text-red-700">{error}</div>}
      <Card className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-100">
              <Th>Employee</Th><Th>Category</Th><Th>Reason</Th><Th>Needed by</Th><Th>Status</Th><Th>Routed via</Th><Th>Created</Th><Th>Action</Th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {rows.map((r) => (
              <tr key={r.id}>
                <td className="px-3 py-2">
                  <div className="font-medium text-gray-900">{r.employee.name}</div>
                  <div className="text-xs text-gray-500">{r.employee.emp_code}{r.employee.department ? ` · ${r.employee.department}` : ''}</div>
                </td>
                <td className="px-3 py-2">{r.category.name}</td>
                <td className="px-3 py-2"><div className="max-w-xs truncate" title={r.reason}>{r.reason}</div></td>
                <td className="px-3 py-2 whitespace-nowrap">{fmtDate(r.needed_by)}</td>
                <td className="px-3 py-2">
                  <Badge variant={REQ_BADGE[r.status]}>{r.status}</Badge>
                  {r.fulfilled_asset && <div className="text-xs text-gray-500 mt-1">{r.fulfilled_asset.asset_tag}</div>}
                </td>
                <td className="px-3 py-2">{r.routed_via === 'chain' ? 'Approval chain' : 'Direct'}</td>
                <td className="px-3 py-2 whitespace-nowrap">{fmtDate(r.created_at)}</td>
                <td className="px-3 py-2">
                  {r.status === 'pending' && r.routed_via === 'direct' && (
                    <div className="flex gap-2">
                      <Button size="sm" onClick={() => setDecide({ req: r, action: 'approve' })}>Approve</Button>
                      <Button size="sm" variant="outline" onClick={() => setDecide({ req: r, action: 'reject' })}>Reject</Button>
                    </div>
                  )}
                  {r.status === 'pending' && r.routed_via === 'chain' && <span className="text-xs text-gray-500">In approval queue</span>}
                  {r.status === 'approved' && <Button size="sm" onClick={() => setFulfil(r)}>Fulfil</Button>}
                </td>
              </tr>
            ))}
            {!loading && !error && rows.length === 0 && (
              <tr><td colSpan={8} className="px-3 py-8 text-center text-gray-500">No requests.</td></tr>
            )}
            {loading && rows.length === 0 && <tr><td colSpan={8} className="px-3 py-8 text-center text-gray-500">Loading…</td></tr>}
          </tbody>
        </table>
      </Card>
      {decide && <DecideDialog {...decide} onClose={() => setDecide(null)} onDone={done} />}
      {fulfil && <FulfilDialog req={fulfil} onClose={() => setFulfil(null)} onDone={done} />}
    </div>
  );
};
