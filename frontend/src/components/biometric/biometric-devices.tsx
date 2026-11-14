import React, { useCallback, useEffect, useState } from 'react';
import { Fingerprint, RefreshCw } from 'lucide-react';
import { Button } from '../ui-elements';
import { client } from '../../api/client';
import { ENDPOINTS } from '../../api/endpoints';
import { errMsg } from '../schedule-delegations-utils';
import { Device } from './biometric-utils';
import { DevicesTab } from './devices-tab';
import { MappingTab } from './mapping-tab';
import { PunchLogTab } from './punch-log-tab';
import { ImportTab } from './import-tab';

type Tab = 'devices' | 'mapping' | 'punches' | 'import';
const TABS: { id: Tab; label: string }[] = [
  { id: 'devices', label: 'Devices' },
  { id: 'mapping', label: 'Mapping' },
  { id: 'punches', label: 'Punch log' },
  { id: 'import', label: 'Import' },
];

export const BiometricDevices: React.FC = () => {
  const [tab, setTab] = useState<Tab>('devices');
  const [devices, setDevices] = useState<Device[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const r = await client.get<Device[]>(ENDPOINTS.BIOMETRIC.DEVICES);
      setDevices(r.data);
      setError(null);
    } catch (err: any) {
      setError(errMsg(err, 'Failed to load devices'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { reload(); }, [reload]);

  return (
    <div className="p-8 space-y-5">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2">
          <Fingerprint className="w-5 h-5 text-indigo-600" />
          <div>
            <h2 className="text-lg font-semibold text-gray-900">Biometric Devices</h2>
            <p className="text-sm text-gray-500 mt-0.5">
              Attendance from ZKTeco / eSSL devices and imported punch files. Times show in your local time; hover for UTC.
            </p>
          </div>
        </div>
        <Button variant="outline" size="sm" onClick={reload} disabled={loading}>
          <RefreshCw className={`w-4 h-4 mr-1 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </Button>
      </div>

      <div role="tablist" aria-label="Biometric sections" className="flex gap-1 border-b border-gray-200 overflow-x-auto">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            aria-selected={tab === t.id}
            onClick={() => setTab(t.id)}
            className={`px-4 py-2 text-sm font-medium whitespace-nowrap border-b-2 -mb-px ${
              tab === t.id
                ? 'border-indigo-600 text-indigo-700'
                : 'border-transparent text-gray-500 hover:text-gray-800'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {error && <div role="alert" className="p-3 rounded-lg bg-red-50 text-sm text-red-700">{error}</div>}

      {tab === 'devices' && <DevicesTab devices={devices} reload={reload} />}
      {tab === 'mapping' && <MappingTab devices={devices ?? []} reloadDevices={reload} />}
      {tab === 'punches' && <PunchLogTab devices={devices ?? []} />}
      {tab === 'import' && <ImportTab />}
    </div>
  );
};
