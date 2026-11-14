import React, { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Card, Button, Badge } from '../ui-elements';
import { client } from '../../api/client';
import { ENDPOINTS } from '../../api/endpoints';
import { errMsg } from '../schedule-delegations-utils';
import {
  BackfillResp, Device, PUNCH_STATES, PUNCH_STATE_VARIANT, Punch, REPROCESS_STATES,
  countsText, dayStartIso, localText, utcText,
} from './biometric-utils';
import { EmpOpt, EmployeePicker, Th, inputCls, labelCls, useBackfill } from './shared';

const PAGE = 50;

export const PunchLogTab: React.FC<{
  devices: Device[]; backfill: ReturnType<typeof useBackfill>; tick: number;
}> = ({ devices, backfill, tick }) => {
  const [state, setState] = useState('');
  const [deviceId, setDeviceId] = useState('');
  const [source, setSource] = useState('');
  const [pin, setPin] = useState('');
  const [emp, setEmp] = useState<EmpOpt | null>(null);
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const [offset, setOffset] = useState(0);
  const [items, setItems] = useState<Punch[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [rState, setRState] = useState<string>('error');
  const [reprocessing, setReprocessing] = useState(false);
  const reqRef = React.useRef(0);

  const load = useCallback(async () => {
    const id = ++reqRef.current;
    setLoading(true);
    try {
      const params: Record<string, string | number> = { limit: PAGE, offset };
      if (state) params.state = state;
      if (deviceId) params.device_id = Number(deviceId);
      if (source) params.source = source;
      if (pin.trim()) params.pin = pin.trim();
      if (emp) params.user_id = emp.user_id;
      if (from) params.from = dayStartIso(from);
      if (to) params.to = dayStartIso(to, 1);
      const r = await client.get<{ items: Punch[]; total: number }>(ENDPOINTS.BIOMETRIC.PUNCHES, { params });
      if (id !== reqRef.current) return;
      setItems(r.data.items);
      setTotal(r.data.total);
      if (r.data.items.length === 0 && r.data.total > 0 && offset > 0) {
        setOffset(Math.max(0, (Math.ceil(r.data.total / PAGE) - 1) * PAGE));
      }
      setError(null);
    } catch (err: any) {
      if (id === reqRef.current) setError(errMsg(err, 'Failed to load the punch log'));
    } finally {
      if (id === reqRef.current) setLoading(false);
    }
  }, [state, deviceId, source, pin, emp, from, to, offset, tick]);

  useEffect(() => {
    const t = window.setTimeout(load, 200);
    return () => window.clearTimeout(t);
  }, [load]);


  const filt = <T,>(set: (v: T) => void) => (v: T) => { set(v); setOffset(0); };

  const reprocess = async () => {
    setReprocessing(true);
    try {
      const body: Record<string, unknown> = { state: rState };
      if (deviceId) body.device_id = Number(deviceId);
      if (pin.trim()) body.pin = pin.trim();
      const r = await client.post<BackfillResp>(ENDPOINTS.BIOMETRIC.REPROCESS, body);
      toast.success(`Reprocessed: ${countsText(r.data.backfill ?? {})}`);
      if ((r.data.remaining ?? 0) > 0) {
        backfill.start(r.data, { state: rState, device_id: deviceId ? Number(deviceId) : null, label: devices.find((d) => String(d.id) === deviceId)?.name || devices.find((d) => String(d.id) === deviceId)?.serial, pin: pin.trim() || undefined });
      }
      await load();
    } catch (err: any) {
      toast.error(errMsg(err, 'Reprocess failed'));
    } finally {
      setReprocessing(false);
    }
  };

  const lastPage = Math.max(0, Math.ceil(total / PAGE) - 1);
  const page = Math.floor(offset / PAGE);

  return (
    <div className="space-y-4">
      <Card className="p-4">
        <div className="flex items-end gap-3 flex-wrap">
          <div>
            <label htmlFor="pl-state" className={labelCls}>State</label>
            <select id="pl-state" className={inputCls} value={state} onChange={(e) => filt(setState)(e.target.value)}>
              <option value="">All states</option>
              {PUNCH_STATES.map((s) => <option key={s} value={s}>{s.replace('_', ' ')}</option>)}
            </select>
          </div>
          <div>
            <label htmlFor="pl-device" className={labelCls}>Device</label>
            <select id="pl-device" className={inputCls} value={deviceId} onChange={(e) => filt(setDeviceId)(e.target.value)}>
              <option value="">All devices</option>
              {devices.map((d) => <option key={d.id} value={d.id}>{d.name || d.serial}</option>)}
            </select>
          </div>
          <div>
            <label htmlFor="pl-source" className={labelCls}>Source</label>
            <select id="pl-source" className={inputCls} value={source} onChange={(e) => filt(setSource)(e.target.value)}>
              <option value="">All sources</option>
              <option value="device">Device</option>
              <option value="import">Import (all)</option>
              <option value="import_code">Import by code</option>
              <option value="import_pin">Import by PIN</option>
            </select>
          </div>
          <div>
            <label htmlFor="pl-pin" className={labelCls}>PIN</label>
            <input id="pl-pin" className={`${inputCls} w-24`} value={pin} onChange={(e) => filt(setPin)(e.target.value)} />
          </div>
          <div className="w-64">
            <label className={labelCls}>Employee</label>
            {emp ? (
              <div className="flex items-center gap-2 text-sm h-9">
                <span className="truncate">{emp.name}</span>
                <button type="button" className="text-xs text-indigo-600" onClick={() => filt(setEmp)(null)}>clear</button>
              </div>
            ) : (
              <EmployeePicker label="Filter by employee" onPick={filt(setEmp)} />
            )}
          </div>
          <div>
            <label htmlFor="pl-from" className={labelCls}>From</label>
            <input id="pl-from" type="date" className={inputCls} value={from} onChange={(e) => filt(setFrom)(e.target.value)} />
          </div>
          <div>
            <label htmlFor="pl-to" className={labelCls}>To</label>
            <input id="pl-to" type="date" className={inputCls} value={to} onChange={(e) => filt(setTo)(e.target.value)} />
          </div>
        </div>
        <div className="flex items-end gap-2 flex-wrap mt-3 pt-3 border-t border-gray-100">
          <div>
            <label htmlFor="pl-rstate" className={labelCls}>Reprocess taps in state</label>
            <select id="pl-rstate" className={inputCls} value={rState} onChange={(e) => setRState(e.target.value)}>
              {REPROCESS_STATES.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
          <Button variant="outline" onClick={reprocess} isLoading={reprocessing} disabled={backfill.busy || reprocessing}>Reprocess</Button>
          <span className="text-xs text-gray-500">Uses the device and PIN filters above.</span>
        </div>
      </Card>

      {error && <div role="alert" className="p-3 rounded-lg bg-red-50 text-sm text-red-700">{error}</div>}

      <Card className="p-0">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-50">
              <tr><Th>Time</Th><Th>Source</Th><Th>PIN</Th><Th>Employee</Th><Th>State</Th><Th>Error</Th></tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {items.length === 0 && (
                <tr><td colSpan={6} className="px-3 py-8 text-center text-gray-500">
                  {loading ? 'Loading…' : 'No taps match these filters.'}
                </td></tr>
              )}
              {items.map((p) => (
                <tr key={p.id}>
                  <td className="px-3 py-2 whitespace-nowrap">
                    <span title={utcText(p.punch_time)}>{localText(p.punch_time)}</span>
                  </td>
                  <td className="px-3 py-2 whitespace-nowrap text-gray-600">
                    {(p.device_id != null ? (devices.find((d) => d.id === p.device_id)?.name || p.device_serial) : null) ?? (p.import_batch ? `Import ${p.import_batch.slice(0, 8)}` : p.source)}
                  </td>
                  <td className="px-3 py-2 font-mono whitespace-nowrap">{p.pin}</td>
                  <td className="px-3 py-2 whitespace-nowrap">
                    {p.user_name ? <>{p.user_name} <span className="text-xs text-gray-500">{p.employee_code}</span></> : <span className="text-gray-400">—</span>}
                  </td>
                  <td className="px-3 py-2">
                    <Badge variant={PUNCH_STATE_VARIANT[p.state] ?? 'neutral'}>{p.state.replace('_', ' ')}</Badge>
                  </td>
                  <td className="px-3 py-2 text-xs text-red-700">{p.error || ''}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <div className="flex items-center justify-between gap-3 flex-wrap text-sm text-gray-600">
        <span>{total} tap{total === 1 ? '' : 's'}{total > 0 ? ` · page ${page + 1} of ${lastPage + 1}` : ''}</span>
        <span className="flex gap-2">
          <Button size="sm" variant="outline" disabled={offset === 0 || loading} onClick={() => setOffset(Math.max(0, offset - PAGE))}>Previous</Button>
          <Button size="sm" variant="outline" disabled={page >= lastPage || loading} onClick={() => setOffset(offset + PAGE)}>Next</Button>
        </span>
      </div>
    </div>
  );
};
