import React, { useState } from 'react';
import { toast } from 'sonner';
import { Card, Button, Badge } from '../ui-elements';
import { client } from '../../api/client';
import { ENDPOINTS } from '../../api/endpoints';
import { errMsg } from '../schedule-delegations-utils';
import {
  BackfillResp, COMMON_OFFSETS, Device, HEALTH_META, STATUS_VARIANT,
  countsText, offsetLabel, relTime, utcText, localText,
} from './biometric-utils';
import { Th, inputCls, labelCls, useBackfill } from './shared';

type Confirm = { id: number; kind: 'disable' | 'delete' } | null;

export const DevicesTab: React.FC<{
  devices: Device[] | null; reload: () => Promise<void>; backfill: ReturnType<typeof useBackfill>;
}> = ({ devices, reload, backfill }) => {
  const [busyId, setBusyId] = useState<number | null>(null);
  const [confirm, setConfirm] = useState<Confirm>(null);
  const [rowError, setRowError] = useState<{ id: number; msg: string } | null>(null);
  const [editing, setEditing] = useState<Device | null>(null);

  const run = async (id: number, fn: () => Promise<void>, fallback: string) => {
    setBusyId(id);
    setRowError(null);
    try {
      await fn();
      setConfirm(null);
      await reload();
    } catch (err: any) {
      setConfirm(null);
      setRowError({ id, msg: errMsg(err, fallback) });
    } finally {
      setBusyId(null);
    }
  };

  const approve = (d: Device) =>
    run(d.id, async () => {
      const r = await client.post<BackfillResp>(ENDPOINTS.BIOMETRIC.DEVICE_APPROVE(d.id));
      toast.success(`Device approved: ${countsText(r.data.backfill ?? {})}`);
      if ((r.data.remaining ?? 0) > 0) backfill.start(r.data, { device_id: d.id, label: d.name || d.serial });
    }, 'Could not approve the device');

  const disable = (d: Device) =>
    run(d.id, async () => {
      await client.post(ENDPOINTS.BIOMETRIC.DEVICE_DISABLE(d.id));
      toast.success('Device disabled');
    }, 'Could not disable the device');

  const remove = (d: Device) =>
    run(d.id, async () => {
      await client.delete(ENDPOINTS.BIOMETRIC.DEVICE(d.id));
      toast.success('Device deleted');
    }, 'Could not delete the device');

  if (!devices) return <p className="py-12 text-center text-sm text-gray-500">Loading devices…</p>;

  const anyBusy = busyId !== null || backfill.busy;

  return (
    <div className="space-y-4">
      {anyBusy && busyId !== null && (
        <div role="status" className="p-3 rounded-lg bg-indigo-50 text-sm text-indigo-800">
          Working… approving a device with many held taps can take a minute or more. Please keep this page open.
        </div>
      )}

      {devices.length === 0 ? (
        <Card className="p-8 space-y-3">
          <p className="text-sm font-medium text-gray-800">No devices have connected yet</p>
          <p className="text-sm text-gray-600">
            On the device, open <strong>Menu → Comm → Cloud Server / ADMS</strong> and set:
          </p>
          <ul className="text-sm text-gray-700 list-disc pl-6 space-y-1">
            <li>Server address: <code className="px-1 bg-gray-100 rounded">{window.location.host}</code> (port 80 / 443 as per this address)</li>
            <li>Path: <code className="px-1 bg-gray-100 rounded">/iclock</code></li>
          </ul>
          <p className="text-sm text-gray-500">
            The device appears here as Pending within a minute. Its taps are held until you approve it.
          </p>
        </Card>
      ) : (
        <Card className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50">
                <tr>
                  <Th>Device</Th><Th>Status</Th><Th>Health</Th><Th>Last seen</Th><Th>Last IP</Th>
                  <Th>Pending taps</Th><Th>Unmapped PINs</Th><Th>Enrolled</Th><Th className="sticky right-0 bg-gray-50 border-l border-gray-100">Actions</Th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {devices.map((d) => {
                  const h = HEALTH_META[d.health];
                  const rowBusy = busyId === d.id;
                  const conf = confirm?.id === d.id ? confirm.kind : null;
                  return (
                    <React.Fragment key={d.id}>
                      <tr>
                        <td className="px-3 py-2">
                          <div className="font-medium text-gray-900">{d.name || d.serial}</div>
                          <div className="text-xs text-gray-500">
                            {d.name ? `${d.serial} · ` : ''}{offsetLabel(d.utc_offset_minutes)}
                            {d.location_note ? ` · ${d.location_note}` : ''}
                          </div>
                        </td>
                        <td className="px-3 py-2"><Badge variant={STATUS_VARIANT[d.status]}>{d.status}</Badge></td>
                        <td className="px-3 py-2"><Badge variant={h.variant}>{h.label}</Badge></td>
                        <td className="px-3 py-2 whitespace-nowrap">
                          <span title={d.last_seen_at ? `${localText(d.last_seen_at)} (${utcText(d.last_seen_at)})` : 'Never connected'}>
                            {relTime(d.last_seen_at)}
                          </span>
                        </td>
                        <td className="px-3 py-2 text-gray-600">{d.last_ip || '—'}</td>
                        <td className="px-3 py-2">{d.pending_punches}</td>
                        <td className="px-3 py-2">{d.unmapped_pins}</td>
                        <td className="px-3 py-2">{d.enrolled_users}</td>
                        <td className="px-3 py-2 sticky right-0 bg-white border-l border-gray-100">
                          <div className="flex items-center gap-2 flex-wrap">
                            {(d.status === 'pending' || d.status === 'disabled') && (
                              <Button size="sm" onClick={() => approve(d)} isLoading={rowBusy} disabled={anyBusy}>
                                Approve
                              </Button>
                            )}
                            {d.status !== 'disabled' && (
                              <Button size="sm" variant="outline" disabled={anyBusy}
                                onClick={() => { setRowError(null); setConfirm({ id: d.id, kind: 'disable' }); }}>
                                Disable
                              </Button>
                            )}
                            <Button size="sm" variant="outline" disabled={anyBusy} onClick={() => setEditing(d)}>Edit</Button>
                            <Button size="sm" variant="ghost" disabled={anyBusy || d.status === 'active'}
                              title={d.status === 'active' ? 'Disable first' : undefined}
                              onClick={() => { setRowError(null); setConfirm({ id: d.id, kind: 'delete' }); }}>
                              Delete
                            </Button>
                            {d.status === 'active' && <span className="text-xs text-gray-400">Disable first</span>}
                          </div>
                        </td>
                      </tr>
                      {(conf || (rowError?.id === d.id)) && (
                        <tr className="bg-gray-50">
                          <td colSpan={9} className="px-3 py-2">
                            {conf && (
                              <div className="flex items-center gap-3 flex-wrap text-sm">
                                <span>
                                  {conf === 'disable'
                                    ? 'Disable this device? Its traffic will be acknowledged and dropped.'
                                    : 'Delete this device and its held taps? Not possible if taps were already applied.'}
                                </span>
                                <Button size="sm" variant="danger" isLoading={rowBusy}
                                  onClick={() => (conf === 'disable' ? disable(d) : remove(d))}>
                                  {conf === 'disable' ? 'Yes, disable' : 'Yes, delete'}
                                </Button>
                                <Button size="sm" variant="outline" disabled={rowBusy} onClick={() => setConfirm(null)}>Cancel</Button>
                              </div>
                            )}
                            {rowError?.id === d.id && (
                              <p role="alert" className="text-sm text-red-700">{rowError.msg}</p>
                            )}
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {editing && (
        <EditDevice
          device={editing}
          onClose={() => setEditing(null)}
          onSaved={async () => { setEditing(null); await reload(); }}
        />
      )}
    </div>
  );
};

const EditDevice: React.FC<{ device: Device; onClose: () => void; onSaved: () => Promise<void> }> = ({
  device, onClose, onSaved,
}) => {
  const known = COMMON_OFFSETS.some((o) => o.minutes === device.utc_offset_minutes);
  const [name, setName] = useState(device.name ?? '');
  const [offsetSel, setOffsetSel] = useState(known ? String(device.utc_offset_minutes) : 'custom');
  const [custom, setCustom] = useState(String(device.utc_offset_minutes));
  const [ips, setIps] = useState(device.ip_allowlist ?? '');
  const [note, setNote] = useState(device.location_note ?? '');
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  React.useEffect(() => {
    const h = (e: KeyboardEvent) => { if (e.key === 'Escape' && !saving) onClose(); };
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  }, [onClose, saving]);

  const save = async () => {
    const minutes = offsetSel === 'custom' && !custom.trim() ? NaN : offsetSel === 'custom' ? Number(custom) : Number(offsetSel);
    if (!Number.isInteger(minutes) || minutes < -720 || minutes > 840) {
      setErr('UTC offset must be a whole number of minutes between -720 and 840.');
      return;
    }
    setSaving(true);
    setErr(null);
    try {
      await client.patch(ENDPOINTS.BIOMETRIC.DEVICE(device.id), {
        name: name.trim() || null,
        utc_offset_minutes: minutes,
        ip_allowlist: ips.trim(),
        location_note: note.trim() || null,
      });
      toast.success('Device updated');
      await onSaved();
    } catch (e: any) {
      setErr(errMsg(e, 'Could not save the device'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: 'rgba(15,23,42,0.45)' }}
      role="dialog"
      aria-modal="true"
      aria-label="Edit device"
    >
      <Card className="w-full max-w-lg p-5 space-y-4 max-h-full overflow-y-auto">
        <h3 className="text-base font-semibold text-gray-900">Edit device {device.serial}</h3>
        <div>
          <label className={labelCls} htmlFor="bd-name">Name</label>
          <input id="bd-name" maxLength={120} className={`${inputCls} w-full`} value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <div>
          <label className={labelCls} htmlFor="bd-offset">Device clock UTC offset</label>
          <select id="bd-offset" className={`${inputCls} w-full`} value={offsetSel} onChange={(e) => setOffsetSel(e.target.value)}>
            {COMMON_OFFSETS.map((o) => <option key={o.minutes} value={o.minutes}>{o.label}</option>)}
            <option value="custom">Custom (minutes)…</option>
          </select>
          {offsetSel === 'custom' && (
            <input aria-label="Custom UTC offset in minutes" type="number" className={`${inputCls} w-full mt-2`}
              min={-720} max={840} value={custom} onChange={(e) => setCustom(e.target.value)} />
          )}
        </div>
        <div>
          <label className={labelCls} htmlFor="bd-ips">IP allow-list (comma separated, empty = any)</label>
          <input id="bd-ips" className={`${inputCls} w-full`} placeholder="10.0.0.5, 10.0.0.6" value={ips}
            onChange={(e) => setIps(e.target.value)} />
        </div>
        <div>
          <label className={labelCls} htmlFor="bd-note">Location note</label>
          <input id="bd-note" maxLength={200} className={`${inputCls} w-full`} value={note} onChange={(e) => setNote(e.target.value)} />
        </div>
        {err && <p role="alert" className="text-sm text-red-700">{err}</p>}
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={onClose} disabled={saving}>Cancel</Button>
          <Button onClick={save} isLoading={saving}>Save</Button>
        </div>
      </Card>
    </div>
  );
};
