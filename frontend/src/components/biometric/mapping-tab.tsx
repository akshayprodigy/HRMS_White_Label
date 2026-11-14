import React, { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Card, Button, Badge } from '../ui-elements';
import { client } from '../../api/client';
import { ENDPOINTS } from '../../api/endpoints';
import { errMsg } from '../schedule-delegations-utils';
import { BackfillResp, Device, DeviceUser, MappingInfo, countsText } from './biometric-utils';
import { BackfillNotice, EmpOpt, EmployeePicker, Th, inputCls, labelCls, useBackfill } from './shared';

interface Pending409 { pin: string; emp: EmpOpt; msg: string }

export const MappingTab: React.FC<{ devices: Device[]; reloadDevices: () => Promise<void> }> = ({
  devices, reloadDevices,
}) => {
  const [deviceId, setDeviceId] = useState<string>(''); // '' = global
  const [users, setUsers] = useState<DeviceUser[]>([]);
  const [maps, setMaps] = useState<MappingInfo[]>([]);
  const [q, setQ] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [pickingPin, setPickingPin] = useState<string | null>(null);
  const [replace, setReplace] = useState<Pending409 | null>(null);
  const [unmapId, setUnmapId] = useState<number | null>(null);
  const [newPin, setNewPin] = useState('');
  const [newEmp, setNewEmp] = useState<EmpOpt | null>(null);
  const devId = deviceId === '' ? null : Number(deviceId);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      if (devId != null) {
        const r = await client.get<DeviceUser[]>(ENDPOINTS.BIOMETRIC.DEVICE_USERS(devId));
        setUsers(r.data);
      } else {
        const r = await client.get<MappingInfo[]>(ENDPOINTS.BIOMETRIC.MAPPINGS, {
          params: q.trim() ? { q: q.trim() } : {},
        });
        setMaps(r.data);
      }
      setError(null);
    } catch (err: any) {
      setError(errMsg(err, 'Failed to load mappings'));
    } finally {
      setLoading(false);
    }
  }, [devId, q]);

  const refreshAll = useCallback(async () => { await load(); await reloadDevices(); }, [load, reloadDevices]);
  const backfill = useBackfill(refreshAll);

  useEffect(() => {
    const t = window.setTimeout(load, devId == null ? 250 : 0);
    return () => window.clearTimeout(t);
  }, [load, devId]);

  useEffect(() => { setPickingPin(null); setReplace(null); setUnmapId(null); backfill.dismiss(); }, [deviceId]); // eslint-disable-line

  const putMap = async (pin: string, emp: EmpOpt, doReplace: boolean) => {
    setBusy(true);
    setError(null);
    try {
      const r = await client.put<BackfillResp>(ENDPOINTS.BIOMETRIC.MAPPINGS, {
        device_id: devId, pin, user_id: emp.user_id, replace: doReplace,
      });
      toast.success(`PIN ${pin} mapped to ${emp.name}: ${countsText(r.data.backfill ?? {})}`);
      if ((r.data.remaining ?? 0) > 0) backfill.start(r.data, { device_id: devId, pin });
      setPickingPin(null);
      setReplace(null);
      setNewPin('');
      setNewEmp(null);
      await refreshAll();
    } catch (err: any) {
      if (err?.response?.status === 409 && !doReplace) {
        setReplace({ pin, emp, msg: errMsg(err, 'This PIN is already mapped to another employee.') });
      } else {
        setError(errMsg(err, 'Could not map the PIN'));
      }
    } finally {
      setBusy(false);
    }
  };

  const unmap = async (id: number) => {
    setBusy(true);
    setError(null);
    try {
      await client.delete(ENDPOINTS.BIOMETRIC.MAPPING(id));
      toast.success('Mapping removed');
      setUnmapId(null);
      await refreshAll();
    } catch (err: any) {
      setError(errMsg(err, 'Could not remove the mapping'));
    } finally {
      setBusy(false);
    }
  };

  const autoMap = async () => {
    if (devId == null) return;
    setBusy(true);
    setError(null);
    try {
      const r = await client.post<BackfillResp & { created: number }>(ENDPOINTS.BIOMETRIC.MAPPINGS_AUTO, { device_id: devId });
      toast.success(`Auto-mapped ${r.data.created} PIN(s): ${countsText(r.data.backfill ?? {})}`);
      if ((r.data.remaining ?? 0) > 0) backfill.start(r.data, { device_id: devId });
      await refreshAll();
    } catch (err: any) {
      setError(errMsg(err, 'Auto-map failed'));
    } finally {
      setBusy(false);
    }
  };

  const disabled = busy || backfill.busy;
  const unmapNote = 'This does not revert attendance that was already applied from this PIN.';

  const unmapCell = (m: MappingInfo) =>
    unmapId === m.id ? (
      <div className="space-y-1">
        <p className="text-xs text-gray-600 max-w-xs">
          Remove this mapping? {unmapNote}
          {(m.scope === 'global' || m.device_id == null) ? ' This is a global mapping and applies to every device.' : ''}
        </p>
        <div className="flex gap-2">
          <Button size="sm" variant="danger" disabled={disabled} onClick={() => unmap(m.id)}>Yes, unmap</Button>
          <Button size="sm" variant="outline" disabled={disabled} onClick={() => setUnmapId(null)}>Cancel</Button>
        </div>
      </div>
    ) : (
      <Button size="sm" variant="outline" disabled={disabled} onClick={() => setUnmapId(m.id)}>Unmap</Button>
    );

  const replaceBox = (pin: string) =>
    replace && replace.pin === pin ? (
      <div className="mt-2 p-2 rounded-lg bg-amber-50 text-sm text-amber-900 space-y-2">
        <p>{replace.msg} Replace it with {replace.emp.name}?</p>
        <div className="flex gap-2">
          <Button size="sm" disabled={disabled} onClick={() => putMap(pin, replace.emp, true)}>Yes, replace</Button>
          <Button size="sm" variant="outline" disabled={disabled} onClick={() => setReplace(null)}>Cancel</Button>
        </div>
      </div>
    ) : null;

  return (
    <div className="space-y-4">
      <div className="flex items-end gap-3 flex-wrap">
        <div>
          <label htmlFor="map-device" className={labelCls}>Device</label>
          <select id="map-device" className={inputCls} value={deviceId} onChange={(e) => setDeviceId(e.target.value)}>
            <option value="">All devices (global)</option>
            {devices.map((d) => <option key={d.id} value={d.id}>{d.name || d.serial}</option>)}
          </select>
        </div>
        {devId != null ? (
          <Button onClick={autoMap} disabled={disabled} isLoading={busy}>Auto-map suggestions</Button>
        ) : (
          <div>
            <label htmlFor="map-q" className={labelCls}>Filter PIN / employee</label>
            <input id="map-q" className={inputCls} value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
        )}
      </div>

      <p className="text-xs text-gray-500">
        Mapping a PIN applies its held taps to attendance. Removing a mapping does not undo attendance already applied.
      </p>

      <BackfillNotice ctl={backfill} />
      {error && <div role="alert" className="p-3 rounded-lg bg-red-50 text-sm text-red-700">{error}</div>}

      {devId != null ? (
        <Card className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50">
                <tr><Th>PIN</Th><Th>Name on device</Th><Th>Employee</Th><Th>Actions</Th></tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {users.length === 0 && (
                  <tr><td colSpan={4} className="px-3 py-8 text-center text-gray-500">
                    {loading ? 'Loading…' : 'This device has not reported any enrolled users yet.'}
                  </td></tr>
                )}
                {users.map((u) => (
                  <tr key={u.pin} className="align-top">
                    <td className="px-3 py-2 font-mono">{u.pin}</td>
                    <td className="px-3 py-2">{u.name || '—'}</td>
                    <td className="px-3 py-2">
                      {u.mapping ? (
                        <span>
                          {u.mapping.user_name} <span className="text-xs text-gray-500">{u.mapping.employee_code}</span>{' '}
                          {u.mapping.scope === 'global' && <Badge variant="neutral">global</Badge>}
                        </span>
                      ) : u.suggested_user_id ? (
                        <span className="text-gray-600">
                          Suggested: {u.suggested_user_name}{' '}
                          <span className="text-xs text-gray-500">{u.suggested_employee_code}</span>
                        </span>
                      ) : (
                        <span className="text-gray-400">Unmapped</span>
                      )}
                      {pickingPin === u.pin && (
                        <div className="mt-2 max-w-xs">
                          <EmployeePicker label={`Employee for PIN ${u.pin}`} onPick={(e) => putMap(u.pin, e, false)} />
                        </div>
                      )}
                      {replaceBox(u.pin)}
                    </td>
                    <td className="px-3 py-2">
                      <div className="flex gap-2 flex-wrap">
                        {!u.mapping && u.suggested_user_id && (
                          <Button size="sm" disabled={disabled}
                            onClick={() => putMap(u.pin, {
                              user_id: u.suggested_user_id!, name: u.suggested_user_name || '', code: u.suggested_employee_code || '',
                            }, false)}>
                            Accept
                          </Button>
                        )}
                        <Button size="sm" variant="outline" disabled={disabled}
                          onClick={() => { setPickingPin(pickingPin === u.pin ? null : u.pin); setReplace(null); }}>
                          {pickingPin === u.pin ? 'Close' : u.mapping ? 'Change' : 'Map'}
                        </Button>
                        {u.mapping && unmapCell(u.mapping)}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      ) : (
        <>
          <Card className="p-4">
            <p className="text-sm font-medium text-gray-800 mb-2">Add mapping (applies to every device)</p>
            <div className="flex items-end gap-3 flex-wrap">
              <div>
                <label htmlFor="map-newpin" className={labelCls}>PIN</label>
                <input id="map-newpin" className={`${inputCls} w-32`} value={newPin} onChange={(e) => setNewPin(e.target.value)} />
              </div>
              <div className="w-64">
                <label className={labelCls}>Employee</label>
                {newEmp ? (
                  <div className="flex items-center gap-2 text-sm">
                    <span>{newEmp.name} <span className="text-xs text-gray-500">{newEmp.code}</span></span>
                    <button type="button" className="text-xs text-indigo-600" onClick={() => setNewEmp(null)}>change</button>
                  </div>
                ) : (
                  <EmployeePicker label="Employee for new mapping" onPick={setNewEmp} />
                )}
              </div>
              <Button disabled={disabled || !newPin.trim() || !newEmp} onClick={() => putMap(newPin.trim(), newEmp!, false)}>
                Add mapping
              </Button>
            </div>
            {replaceBox(newPin.trim())}
          </Card>
          <Card className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-gray-50">
                  <tr><Th>Scope</Th><Th>PIN</Th><Th>Employee</Th><Th>Created</Th><Th>Actions</Th></tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {maps.length === 0 && (
                    <tr><td colSpan={5} className="px-3 py-8 text-center text-gray-500">{loading ? 'Loading…' : 'No mappings yet.'}</td></tr>
                  )}
                  {maps.map((m) => {
                    const dev = devices.find((d) => d.id === m.device_id);
                    return (
                      <tr key={m.id} className="align-top">
                        <td className="px-3 py-2">
                          {m.device_id == null ? <Badge variant="info">global</Badge> : (dev?.name || dev?.serial || `device ${m.device_id}`)}
                        </td>
                        <td className="px-3 py-2 font-mono">{m.pin}</td>
                        <td className="px-3 py-2">{m.user_name} <span className="text-xs text-gray-500">{m.employee_code}</span></td>
                        <td className="px-3 py-2 whitespace-nowrap text-gray-600">{m.created_at.slice(0, 10)}</td>
                        <td className="px-3 py-2">{unmapCell(m)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </Card>
        </>
      )}
    </div>
  );
};
