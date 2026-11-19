import React, { useCallback, useEffect, useState } from 'react';
import { Package, RefreshCw } from 'lucide-react';
import { Button, Card } from '../ui-elements';
import { client } from '../../api/client';
import { ENDPOINTS } from '../../api/endpoints';
import { errMsg } from '../schedule-delegations-utils';
import { RegisterTab } from './register-tab';
import { AssetDetailDialog } from './asset-detail-dialog';
import { AssetFormDialog } from './asset-form-dialog';
import { CategoriesDialog } from './categories-dialog';
import { Summary, fmtInr } from './asset-utils';
import { NavDetail, takeNav } from '../../lib/pending-nav';

type Tab = 'register' | 'requests' | 'maintenance' | 'expiring';
const TABS: { id: Tab; label: string }[] = [
  { id: 'register', label: 'Register' },
  { id: 'requests', label: 'Requests' },
  { id: 'maintenance', label: 'Maintenance' },
  { id: 'expiring', label: 'Expiring' },
];

const ComingSoon: React.FC<{ name: string }> = ({ name }) => (
  <Card className="p-8 text-center text-sm text-gray-500">{name} is coming soon.</Card>
);

const Tile: React.FC<{ label: string; value: React.ReactNode }> = ({ label, value }) => (
  <Card className="p-4">
    <div className="text-xs text-gray-500">{label}</div>
    <div className="text-xl font-semibold text-gray-900 mt-1">{value}</div>
  </Card>
);

export const AssetManagement: React.FC = () => {
  const [tab, setTab] = useState<Tab>('register');
  const [summary, setSummary] = useState<Summary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [openId, setOpenId] = useState<number | null>(null);
  const [adding, setAdding] = useState(false);
  const [cats, setCats] = useState(false);

  const loadSummary = useCallback(async () => {
    try {
      const r = await client.get<Summary>(ENDPOINTS.ASSETS.SUMMARY);
      setSummary(r.data);
      setError(null);
    } catch (e: any) {
      setError(errMsg(e, 'Failed to load summary'));
    }
  }, []);
  useEffect(() => { loadSummary(); }, [loadSummary, refreshKey]);

  const bump = useCallback(() => setRefreshKey((k) => k + 1), []);

  useEffect(() => {
    const apply = (d: NavDetail | null) => {
      if (d?.tab !== 'asset-management' || d?.resourceType !== 'asset') return;
      const id = Number(d.resourceId);
      if (Number.isInteger(id) && id > 0) { setTab('register'); setOpenId(id); }
    };
    apply(takeNav('asset-management')); // arrived before this page mounted
    // App's listener stashes before this one runs; take so the stash clears.
    const h = (ev: Event) => {
      const d = (ev as CustomEvent).detail as NavDetail | undefined;
      if (d?.tab !== 'asset-management') return;
      takeNav('asset-management');
      apply(d);
    };
    window.addEventListener('erp:navigate', h);
    return () => window.removeEventListener('erp:navigate', h);
  }, []);

  const s = summary?.by_status;
  return (
    <div className="p-8 space-y-5">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2">
          <Package className="w-5 h-5 text-indigo-600" />
          <div>
            <h2 className="text-lg font-semibold text-gray-900">Asset Management</h2>
            <p className="text-sm text-gray-500 mt-0.5">Register, allocate and maintain company assets.</p>
          </div>
        </div>
        <Button variant="outline" size="sm" onClick={bump}><RefreshCw className="w-4 h-4 mr-1" />Refresh</Button>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <Tile label="In stock" value={s?.in_stock ?? '—'} />
        <Tile label="Allocated" value={s?.allocated ?? '—'} />
        <Tile label="In repair" value={s?.in_repair ?? '—'} />
        <Tile label="Expiring (30d)" value={summary?.expiring_30d ?? '—'} />
        <Tile label="Book value" value={summary ? fmtInr(summary.total_book_value_paise) : '—'} />
      </div>

      <div role="tablist" aria-label="Asset sections" className="flex gap-1 border-b border-gray-200 overflow-x-auto">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            aria-selected={tab === t.id}
            onClick={() => setTab(t.id)}
            className={`px-4 py-2 text-sm font-medium whitespace-nowrap border-b-2 -mb-px ${
              tab === t.id ? 'border-indigo-600 text-indigo-700' : 'border-transparent text-gray-500 hover:text-gray-800'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {error && <div role="alert" className="p-3 rounded-lg bg-red-50 text-sm text-red-700">{error}</div>}

      {tab === 'register' && (
        <RegisterTab refreshKey={refreshKey} onOpen={setOpenId} onAdd={() => setAdding(true)} onCategories={() => setCats(true)} />
      )}
      {tab === 'requests' && <ComingSoon name="Requests" />}
      {tab === 'maintenance' && <ComingSoon name="Maintenance" />}
      {tab === 'expiring' && <ComingSoon name="Expiring" />}

      {openId != null && <AssetDetailDialog key={openId} assetId={openId} onClose={() => setOpenId(null)} onChanged={bump} />}
      {adding && <AssetFormDialog onClose={() => setAdding(false)} onSaved={(a) => { setAdding(false); bump(); setOpenId(a.id); }} />}
      {cats && <CategoriesDialog onClose={() => setCats(false)} onChanged={bump} />}
    </div>
  );
};
