import React, { useCallback, useEffect, useState } from 'react';
import { Network, RefreshCw } from 'lucide-react';
import { Button } from '../ui-elements';
import { client } from '../../api/client';
import { ENDPOINTS } from '../../api/endpoints';
import { ActingTab } from './acting-tab';
import { CheckTab } from './check-tab';
import { ManagersTab } from './managers-tab';
import { PostsTab } from './posts-tab';
import { Meta, NO_ACCESS, Notice, PostItem, dopErr } from './dop-utils';

type Tab = 'managers' | 'posts' | 'acting' | 'check';
const TABS: { id: Tab; label: string }[] = [
  { id: 'managers', label: 'Managers' },
  { id: 'posts', label: 'Posts' },
  { id: 'acting', label: 'Acting' },
  { id: 'check', label: 'Check' },
];

export const DopAdmin: React.FC = () => {
  const [tab, setTab] = useState<Tab>('managers');
  const [meta, setMeta] = useState<Meta | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [prefill, setPrefill] = useState<PostItem | null>(null);

  const loadMeta = useCallback(async () => {
    try {
      const r = await client.get<Meta>(ENDPOINTS.DOP.META);
      setMeta(r.data); setError(null);
    } catch (e: any) { setError(dopErr(e, 'Could not load Delegation of Powers')); }
  }, []);
  useEffect(() => { loadMeta(); }, [loadMeta]);
  const denied = error === NO_ACCESS;
  const bump = useCallback(() => { setRefreshKey((k) => k + 1); loadMeta(); }, [loadMeta]);

  return (
    <div className="p-8 space-y-5">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2">
          <Network className="w-5 h-5 text-indigo-600" />
          <div>
            <h2 className="text-lg font-semibold text-gray-900">Delegation of Powers</h2>
            <p className="text-sm text-gray-500 mt-0.5">Decide who manages each employee, who holds which post, and who can act in their place.</p>
          </div>
        </div>
        <Button variant="outline" size="sm" onClick={bump}><RefreshCw className="w-4 h-4 mr-1" />Refresh</Button>
      </div>

      <Notice tone="info">
        Other manager types and acting covers are setup only until the next release: live approvals keep their current routes.
        Changing a reporting manager takes effect immediately.
      </Notice>

      {!denied && (
      <div role="tablist" aria-label="Delegation of Powers sections" className="flex gap-1 border-b border-gray-200 overflow-x-auto">
        {TABS.map((t) => (
          <button
            key={t.id} type="button" role="tab" aria-selected={tab === t.id} onClick={() => setTab(t.id)}
            className={`px-4 py-2 text-sm font-medium whitespace-nowrap border-b-2 -mb-px ${
              tab === t.id ? 'border-indigo-600 text-indigo-700' : 'border-transparent text-gray-500 hover:text-gray-800'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>
      )}

      {error && <Notice>{error}</Notice>}

      {!denied && tab === 'managers' && <ManagersTab meta={meta} refreshKey={refreshKey} onMetaChanged={loadMeta} />}
      {!denied && tab === 'posts' && <PostsTab meta={meta} refreshKey={refreshKey} onActing={(p) => { setPrefill(p); setTab('acting'); }} />}
      {!denied && tab === 'acting' && <ActingTab meta={meta} refreshKey={refreshKey} prefillPost={prefill} onPrefillUsed={() => setPrefill(null)} onChanged={() => setRefreshKey((k) => k + 1)} />}
      {!denied && tab === 'check' && <CheckTab meta={meta} />}
    </div>
  );
};
