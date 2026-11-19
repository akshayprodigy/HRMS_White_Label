import React, { useState } from 'react';
import { toast } from 'sonner';
import { Button } from '../ui-elements';
import { client } from '../../api/client';
import { ENDPOINTS } from '../../api/endpoints';
import { errMsg } from '../schedule-delegations-utils';
import { EmpOpt, EmployeePicker } from '../biometric/shared';
import { Modal } from './modal';
import { AssetDetail, inputCls, labelCls, serverSafeToday } from './asset-utils';

export type ActionKind = 'allocate' | 'return' | 'lost' | 'to_in_stock' | 'to_in_repair' | 'to_retired';

const TITLES: Record<ActionKind, string> = {
  allocate: 'Allocate asset',
  return: 'Return asset',
  lost: 'Mark asset as lost',
  to_in_stock: 'Move back to stock',
  to_in_repair: 'Send to repair',
  to_retired: 'Retire asset',
};

interface Props {
  asset: AssetDetail;
  kind: ActionKind;
  onClose: () => void;
  onDone: () => void;
}

export const AssetActionDialog: React.FC<Props> = ({ asset, kind, onClose, onDone }) => {
  const [emp, setEmp] = useState<EmpOpt | null>(null);
  const [date, setDate] = useState(serverSafeToday());
  const [dateTouched, setDateTouched] = useState(false);
  const [condition, setCondition] = useState('');
  const [remarks, setRemarks] = useState('');
  const [toStatus, setToStatus] = useState('in_stock');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const submit = async () => {
    let url = '';
    let body: Record<string, unknown> = {};
    if (kind === 'allocate') {
      if (!emp?.id) return setErr('Pick an employee.');
      url = ENDPOINTS.ASSETS.ALLOCATE(asset.id);
      body = { employee_id: emp.id, issued_date: dateTouched && date ? date : undefined, condition: condition.trim() || null, remarks: remarks.trim() || null };
    } else if (kind === 'return') {
      url = ENDPOINTS.ASSETS.RETURN(asset.id);
      body = { returned_date: dateTouched && date ? date : undefined, condition: condition.trim() || null, remarks: remarks.trim() || null, to_status: toStatus };
    } else if (kind === 'lost') {
      if (remarks.trim().length < 3) return setErr('Remarks are required (at least 3 characters).');
      url = ENDPOINTS.ASSETS.LOST(asset.id);
      body = { remarks: remarks.trim() };
    } else {
      url = ENDPOINTS.ASSETS.STATUS(asset.id);
      body = { to_status: kind.replace('to_', ''), remarks: remarks.trim() || null };
    }
    setBusy(true);
    setErr(null);
    try {
      await client.post(url, body);
      toast.success(`${TITLES[kind]}: done`);
      onDone();
    } catch (e: any) {
      const m = errMsg(e, 'Action failed');
      setErr(m);
      toast.error(m);
    } finally {
      setBusy(false);
    }
  };

  const showDate = kind === 'allocate' || kind === 'return';
  return (
    <Modal title={`${TITLES[kind]} — ${asset.asset_tag}`} label={TITLES[kind]} onClose={onClose} busy={busy}>
      {kind === 'allocate' && (
        <div>
          <label className={labelCls}>Employee *</label>
          {emp ? (
            <div className="flex items-center justify-between text-sm border border-gray-200 rounded-lg px-3 py-2">
              <span>{emp.name} <span className="text-xs text-gray-500">{emp.code}</span></span>
              <button type="button" className="text-xs text-indigo-600" onClick={() => setEmp(null)}>Change</button>
            </div>
          ) : (
            <EmployeePicker onPick={setEmp} label="Search employee to allocate to" />
          )}
        </div>
      )}
      {kind === 'return' && (
        <div>
          <label className={labelCls} htmlFor="aa-to">Return to</label>
          <select id="aa-to" className={`${inputCls} w-full`} value={toStatus} onChange={(e) => setToStatus(e.target.value)}>
            <option value="in_stock">In stock</option>
            <option value="in_repair">In repair</option>
            <option value="retired">Retired</option>
          </select>
        </div>
      )}
      {showDate && (
        <div>
          <label className={labelCls} htmlFor="aa-date">{kind === 'allocate' ? 'Issue date' : 'Return date'}</label>
          <input id="aa-date" type="date" max={serverSafeToday()} className={`${inputCls} w-full`} value={date} onChange={(e) => { setDate(e.target.value); setDateTouched(true); }} />
        </div>
      )}
      {showDate && (
        <div>
          <label className={labelCls} htmlFor="aa-cond">Condition</label>
          <input id="aa-cond" maxLength={50} className={`${inputCls} w-full`} value={condition} onChange={(e) => setCondition(e.target.value)} />
        </div>
      )}
      <div>
        <label className={labelCls} htmlFor="aa-rem">Remarks{kind === 'lost' ? ' *' : ''}</label>
        <textarea id="aa-rem" rows={2} className={`${inputCls} w-full h-auto py-2`} value={remarks} onChange={(e) => setRemarks(e.target.value)} />
      </div>
      {err && <p role="alert" className="text-sm text-red-700">{err}</p>}
      <div className="flex justify-end gap-2">
        <Button variant="outline" onClick={onClose} disabled={busy}>Cancel</Button>
        <Button variant={kind === 'lost' ? 'danger' : 'primary'} onClick={submit} isLoading={busy}>Confirm</Button>
      </div>
    </Modal>
  );
};
