import React, { useState } from 'react';
import { toast } from 'sonner';
import { Button } from '../ui-elements';
import { client } from '../../api/client';
import { ENDPOINTS } from '../../api/endpoints';
import { errMsg } from '../schedule-delegations-utils';
import { Modal } from './modal';
import {
  AssetDetail, KIND_LABEL, MaintKind, fmtDate, fmtInr, inputCls, labelCls, rupeesToPaise, todayIso,
} from './asset-utils';

const LogForm: React.FC<{ asset: AssetDetail; onClose: () => void; onDone: () => void }> = ({ asset, onClose, onDone }) => {
  const [kind, setKind] = useState<MaintKind>('repair');
  const [desc, setDesc] = useState('');
  const [vendor, setVendor] = useState('');
  const [cost, setCost] = useState('');
  const [started, setStarted] = useState(todayIso());
  const [completed, setCompleted] = useState('');
  const [toRepair, setToRepair] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const submit = async () => {
    if (!desc.trim()) return setErr('Description is required.');
    const c = rupeesToPaise(cost);
    if (Number.isNaN(c)) return setErr('Cost must be a non-negative amount.');
    if (!started) return setErr('Start date is required.');
    if (completed && completed < started) return setErr('Completed date cannot be before the start date.');
    setBusy(true);
    setErr(null);
    try {
      await client.post(ENDPOINTS.ASSETS.MAINTENANCE(asset.id), {
        kind, description: desc.trim(), vendor: vendor.trim() || null, cost_paise: c ?? 0,
        started_on: started, completed_on: completed || null, move_to_repair: toRepair && !completed,
      });
      toast.success('Maintenance logged');
      onDone();
    } catch (e: any) {
      setErr(errMsg(e, 'Could not log maintenance'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal title={`Log maintenance — ${asset.asset_tag}`} label="Log maintenance" onClose={onClose} busy={busy}>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div>
          <label className={labelCls} htmlFor="mt-kind">Kind</label>
          <select id="mt-kind" className={`${inputCls} w-full`} value={kind} onChange={(e) => setKind(e.target.value as MaintKind)}>
            {(Object.keys(KIND_LABEL) as MaintKind[]).map((k) => <option key={k} value={k}>{KIND_LABEL[k]}</option>)}
          </select>
        </div>
        <div>
          <label className={labelCls} htmlFor="mt-vendor">Vendor</label>
          <input id="mt-vendor" maxLength={150} className={`${inputCls} w-full`} value={vendor} onChange={(e) => setVendor(e.target.value)} />
        </div>
        <div>
          <label className={labelCls} htmlFor="mt-cost">Cost (₹)</label>
          <input id="mt-cost" type="number" min={0} step="0.01" className={`${inputCls} w-full`} value={cost} onChange={(e) => setCost(e.target.value)} />
        </div>
        <div>
          <label className={labelCls} htmlFor="mt-start">Started on</label>
          <input id="mt-start" type="date" className={`${inputCls} w-full`} value={started} onChange={(e) => setStarted(e.target.value)} />
        </div>
        <div>
          <label className={labelCls} htmlFor="mt-done">Completed on</label>
          <input id="mt-done" type="date" className={`${inputCls} w-full`} value={completed} onChange={(e) => setCompleted(e.target.value)} />
        </div>
      </div>
      <div>
        <label className={labelCls} htmlFor="mt-desc">Description *</label>
        <textarea id="mt-desc" rows={2} className={`${inputCls} w-full h-auto py-2`} value={desc} onChange={(e) => setDesc(e.target.value)} />
      </div>
      {asset.status === 'in_stock' && !completed && (
        <label className="flex items-center gap-2 text-sm text-gray-700">
          <input type="checkbox" checked={toRepair} onChange={(e) => setToRepair(e.target.checked)} />
          Move asset to repair
        </label>
      )}
      {err && <p role="alert" className="text-sm text-red-700">{err}</p>}
      <div className="flex justify-end gap-2">
        <Button variant="outline" onClick={onClose} disabled={busy}>Cancel</Button>
        <Button onClick={submit} isLoading={busy}>Log</Button>
      </div>
    </Modal>
  );
};

export const MaintenanceSection: React.FC<{ asset: AssetDetail; onChanged: () => void }> = ({ asset, onChanged }) => {
  const [logging, setLogging] = useState(false);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [confirmId, setConfirmId] = useState<number | null>(null);

  const act = async (id: number, fn: () => Promise<unknown>, ok: string) => {
    setBusyId(id);
    try {
      await fn();
      toast.success(ok);
      onChanged();
    } catch (e: any) {
      toast.error(errMsg(e, 'Request failed'));
    } finally {
      setBusyId(null);
      setConfirmId(null);
    }
  };

  return (
    <section className="space-y-2">
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-semibold text-gray-900">
          Maintenance <span className="text-xs font-normal text-gray-500">total {fmtInr(asset.maintenance_cost_total_paise)}</span>
        </h4>
        <Button size="sm" variant="outline" onClick={() => setLogging(true)}>Log maintenance</Button>
      </div>
      {asset.maintenance.length === 0 ? (
        <p className="text-sm text-gray-500">No maintenance recorded.</p>
      ) : (
        <ul className="divide-y divide-gray-100 border border-gray-100 rounded-lg">
          {asset.maintenance.map((m) => (
            <li key={m.id} className="p-3 flex items-start justify-between gap-3 flex-wrap">
              <div className="text-sm">
                <div className="font-medium text-gray-900">
                  {KIND_LABEL[m.kind] ?? m.kind} · {fmtInr(m.cost_paise)}
                  {!m.completed_on && <span className="ml-2 text-xs text-amber-700">open</span>}
                </div>
                <div className="text-gray-600">{m.description}</div>
                <div className="text-xs text-gray-500">
                  {m.vendor ? `${m.vendor} · ` : ''}{fmtDate(m.started_on)}{m.completed_on ? ` → ${fmtDate(m.completed_on)}` : ''}
                </div>
              </div>
              <div className="flex gap-2">
                {!m.completed_on && (
                  <Button size="sm" variant="outline" disabled={busyId === m.id}
                    onClick={() => act(m.id, () => client.patch(ENDPOINTS.ASSETS.MAINTENANCE_ITEM(m.id),
                      { complete: true, return_to_stock: asset.status === 'in_repair' }), 'Maintenance completed')}>
                    Complete
                  </Button>
                )}
                {confirmId === m.id ? (
                  <>
                    <Button size="sm" variant="danger" disabled={busyId === m.id}
                      onClick={() => act(m.id, () => client.delete(ENDPOINTS.ASSETS.MAINTENANCE_ITEM(m.id)), 'Maintenance deleted')}>
                      Confirm delete
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => setConfirmId(null)}>Keep</Button>
                  </>
                ) : (
                  <Button size="sm" variant="outline" disabled={busyId === m.id} onClick={() => setConfirmId(m.id)}>Delete</Button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
      {logging && <LogForm asset={asset} onClose={() => setLogging(false)} onDone={() => { setLogging(false); onChanged(); }} />}
    </section>
  );
};
