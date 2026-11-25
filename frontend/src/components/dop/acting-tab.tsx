import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Plus } from 'lucide-react';
import { toast } from 'sonner';
import { Badge, Button, Card, fmtDate } from '../ui-elements';
import { client } from '../../api/client';
import { ENDPOINTS } from '../../api/endpoints';
import { Th } from '../biometric/shared';
import { ActingDialog } from './acting-dialog';
import { ConfirmDialog } from './confirm-dialog';
import { Cover, Meta, Notice, PostItem, STATUS_TEXT, STATUS_VARIANT, dopErr, subText } from './dop-utils';

export const ActingTab: React.FC<{
  meta: Meta | null; refreshKey: number; prefillPost: PostItem | null; onPrefillUsed: () => void; onChanged: () => void;
}> = ({ meta, refreshKey, prefillPost, onPrefillUsed, onChanged }) => {
  const [items, setItems] = useState<Cover[]>([]);
  const [ended, setEnded] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [flip, setFlip] = useState<Cover | null>(null);
  const [stop, setStop] = useState<Cover | null>(null);
  const [bump, setBump] = useState(0);
  const seq = useRef(0);

  useEffect(() => { if (prefillPost) setCreating(true); }, [prefillPost]);

  const load = useCallback(async () => {
    const n = ++seq.current;
    setLoading(true);
    try {
      const r = await client.get<Cover[]>(ENDPOINTS.DOP.ACTING, { params: { include_ended: ended } });
      if (n !== seq.current) return;
      setItems(r.data); setError(null);
    } catch (e: any) {
      if (n === seq.current) { setItems([]); setError(dopErr(e, 'Could not load acting covers')); }
    } finally {
      if (n === seq.current) setLoading(false);
    }
  }, [ended]);
  useEffect(() => { load(); }, [load, refreshKey, bump]);

  const done = () => { setBump((b) => b + 1); onChanged(); };
  const closeCreate = () => { setCreating(false); onPrefillUsed(); };
  const who = (c: Cover) => c.covers_post_title ? `the holder of ${c.covers_post_title}` : c.covers_user_name ?? 'them';
  const covers = (c: Cover) => c.covers_post_title ? `Post: ${c.covers_post_title}` : c.covers_user_name ?? '—';

  return (
    <div className="space-y-4">
      <p className="text-sm text-gray-600">An acting cover records who will approve in place of a person or post for a while. It is saved now and starts being used for approvals in the next release.</p>
      <Notice tone="info">Out-of-office covers set by employees are the only covers used for approvals today. They are listed for reference and can only be changed by them. Once acting covers are in use, they take priority.</Notice>
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <label className="flex items-center gap-1.5 text-sm"><input type="checkbox" checked={ended} onChange={(e) => setEnded(e.target.checked)} />Show ended covers</label>
        <Button size="sm" onClick={() => setCreating(true)}><Plus className="w-4 h-4 mr-1" />New acting cover</Button>
      </div>
      {error && <Notice>{error}</Notice>}
      <Card className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-100"><Th>Covering for</Th><Th>Acting person</Th><Th>Areas</Th><Th>Dates</Th><Th>Original can also act</Th><Th>Status</Th><Th className="text-right">Actions</Th></tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {items.map((c) => {
              const open = c.status === 'live' || c.status === 'scheduled';
              return (
                <tr key={c.key ?? `${c.source}-${c.id}`} className={c.read_only ? 'bg-gray-50' : 'hover:bg-gray-50'}>
                  <td className="px-3 py-2">{covers(c)}{c.read_only && <span className="block"><Badge variant="neutral">Out of office (read-only)</Badge></span>}
                    {c.only_when_on_leave && <span className="block text-xs text-gray-500">Only while on leave</span>}</td>
                  <td className="px-3 py-2">{c.acting_user_name}</td>
                  <td className="px-3 py-2">{c.read_only ? 'Everything' : subText(c.subdomains, meta)}</td>
                  <td className="px-3 py-2 whitespace-nowrap">{fmtDate(c.starts_on)} to {c.ends_on ? fmtDate(c.ends_on) : 'no end date'}</td>
                  <td className="px-3 py-2">
                    {c.read_only ? <span className="text-gray-500">Yes</span> : (
                      <button
                        type="button" role="switch" aria-checked={c.original_can_act} disabled={!open}
                        aria-label={`Original can also act for ${covers(c)}`} onClick={() => setFlip(c)}
                        className={`inline-flex h-5 w-9 items-center px-1 rounded-full ${c.original_can_act ? 'bg-indigo-600 justify-end' : 'bg-slate-300'} ${open ? '' : 'opacity-50'}`}
                      >
                        <span className="inline-block h-3.5 w-3.5 rounded-full bg-white" />
                      </button>
                    )}
                  </td>
                  <td className="px-3 py-2">
                    {c.status === 'live' && !c.read_only
                      ? <><Badge variant="neutral">In place</Badge><span className="block text-xs text-gray-500">Not used for approvals yet</span></>
                      : <Badge variant={STATUS_VARIANT[c.status] ?? 'neutral'}>{STATUS_TEXT[c.status] ?? c.status}</Badge>}
                  </td>
                  <td className="px-3 py-2 text-right">
                    {!c.read_only && open && <Button size="sm" variant="outline" onClick={() => setStop(c)}>End</Button>}
                  </td>
                </tr>
              );
            })}
            {loading && items.length === 0 && <tr><td colSpan={7} className="px-3 py-8 text-center text-gray-500">Loading…</td></tr>}
            {!loading && !error && items.length === 0 && <tr><td colSpan={7} className="px-3 py-8 text-center text-gray-500">No acting covers.</td></tr>}
          </tbody>
        </table>
      </Card>
      {creating && <ActingDialog meta={meta} prefillPost={prefillPost} onClose={closeCreate} onSaved={() => { closeCreate(); done(); }} />}
      {flip && (
        <ConfirmDialog
          title="Change who can approve" confirmText={flip.original_can_act ? 'Stop the original approving' : 'Let the original also approve'}
          onClose={() => setFlip(null)}
          onConfirm={async () => { await client.patch(ENDPOINTS.DOP.ACTING_ITEM(flip.id), { original_can_act: !flip.original_can_act }); toast.success('Saved'); setFlip(null); done(); }}
          body={flip.original_can_act
            ? <p>{flip.acting_user_name} will be the only one who can approve for {who(flip)} once acting covers are used. Nothing changes in live approvals today.</p>
            : <p>{who(flip)} will be able to approve as well as {flip.acting_user_name}, once acting covers are used. Nothing changes in live approvals today.</p>}
        />
      )}
      {stop && (
        <ConfirmDialog
          title="End this acting cover" confirmText="End cover" danger onClose={() => setStop(null)}
          onConfirm={async () => { await client.post(ENDPOINTS.DOP.ACTING_REVOKE(stop.id)); toast.success('Cover ended'); setStop(null); done(); }}
          body={<p>{stop.acting_user_name} will stop acting for {who(stop)} once acting covers are used. Nothing changes in live approvals today.</p>}
        />
      )}
    </div>
  );
};
