import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Plus } from 'lucide-react';
import { Badge, Button, Card, fmtDate } from '../ui-elements';
import { client } from '../../api/client';
import { ENDPOINTS } from '../../api/endpoints';
import { Th } from '../biometric/shared';
import { PostDialog } from './post-dialog';
import { HoldersDialog } from './holders-dialog';
import { Meta, Notice, PostItem, dopErr, inputCls, labelCls } from './dop-utils';

/** Depth-first order so children sit under their parent. Loops and missing parents fall back to the top level. */
const tree = (posts: PostItem[]): { p: PostItem; depth: number }[] => {
  const ids = new Set(posts.map((p) => p.id));
  const kids = new Map<number | null, PostItem[]>();
  posts.forEach((p) => {
    const k = p.parent_post_id && ids.has(p.parent_post_id) && p.parent_post_id !== p.id ? p.parent_post_id : null;
    kids.set(k, [...(kids.get(k) ?? []), p]);
  });
  const out: { p: PostItem; depth: number }[] = [];
  const seen = new Set<number>();
  const walk = (k: number | null, depth: number) => (kids.get(k) ?? []).forEach((p) => {
    if (seen.has(p.id)) return;
    seen.add(p.id); out.push({ p, depth }); walk(p.id, depth + 1);
  });
  walk(null, 0);
  posts.forEach((p) => { if (!seen.has(p.id)) { seen.add(p.id); out.push({ p, depth: 0 }); walk(p.id, 1); } });
  return out;
};

export const PostsTab: React.FC<{
  meta: Meta | null; refreshKey: number; onActing: (post: PostItem) => void;
}> = ({ meta, refreshKey, onActing }) => {
  const [items, setItems] = useState<PostItem[]>([]);
  const [showOff, setShowOff] = useState(false);
  const [q, setQ] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState<PostItem | 'new' | null>(null);
  const [holdersFor, setHoldersFor] = useState<number | null>(null);
  const [bump, setBump] = useState(0);
  const seq = useRef(0);

  const load = useCallback(async () => {
    const n = ++seq.current;
    setLoading(true);
    try {
      const r = await client.get<PostItem[]>(ENDPOINTS.DOP.POSTS, { params: { include_inactive: showOff } });
      if (n !== seq.current) return;
      setItems(r.data); setError(null);
    } catch (e: any) {
      if (n === seq.current) { setItems([]); setError(dopErr(e, 'Could not load posts')); }
    } finally {
      if (n === seq.current) setLoading(false);
    }
  }, [showOff]);
  useEffect(() => { load(); }, [load, refreshKey, bump]);

  const shown = useMemo(() => {
    const t = tree(items);
    const s = q.trim().toLowerCase();
    if (!s) return t;
    return t.filter(({ p }) => `${p.title} ${p.code} ${p.holder?.user_name ?? ''} ${p.department_name ?? ''}`.toLowerCase().includes(s));
  }, [items, q]);
  const holdersPost = items.find((p) => p.id === holdersFor) ?? null;

  return (
    <div className="space-y-4">
      <p className="text-sm text-gray-600">A post is a seat such as "Head of Finance". People come and go, but a reporting manager set to a post reaches whoever holds it, and live approvals follow that. Other manager types and acting covers use posts from the next release.</p>
      <div className="flex items-end gap-3 flex-wrap">
        <div className="flex-1">
          <label className={labelCls} htmlFor="dp-q">Search posts</label>
          <input id="dp-q" className={`${inputCls} w-full`} placeholder="Post, code, person or department" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
        <label className="flex items-center gap-1.5 text-sm pb-2"><input type="checkbox" checked={showOff} onChange={(e) => setShowOff(e.target.checked)} />Show switched-off posts</label>
        <Button size="sm" onClick={() => setForm('new')}><Plus className="w-4 h-4 mr-1" />New post</Button>
      </div>
      {error && <Notice>{error}</Notice>}
      <Card className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead><tr className="border-b border-gray-100"><Th>Post</Th><Th>Held by</Th><Th>Status</Th><Th className="text-right">Actions</Th></tr></thead>
          <tbody className="divide-y divide-gray-100">
            {shown.map(({ p, depth }) => (
              <tr key={p.id} className="hover:bg-gray-50">
                <td className="px-3 py-2" style={{ paddingLeft: 12 + depth * 20 }}>
                  <span className="font-medium text-gray-900">{depth > 0 ? '↳ ' : ''}{p.title}</span>
                  <span className="block text-xs text-gray-500">{p.code}{p.department_name ? ` · ${p.department_name}` : ''}{p.location ? ` · ${p.location}` : ''}{p.heads_department_name ? ` · heads ${p.heads_department_name}` : ''}</span>
                </td>
                <td className="px-3 py-2">
                  {p.holder ? <span>{p.holder.user_name}{p.holder.ends_on && <span className="block text-xs text-gray-500">until {fmtDate(p.holder.ends_on)}</span>}</span> : <span className="text-gray-400">Nobody</span>}
                  {p.next_holder && <span className="block text-xs text-indigo-700">{p.next_holder.user_name} from {fmtDate(p.next_holder.starts_on)}</span>}
                </td>
                <td className="px-3 py-2"><div className="flex items-center gap-1 flex-wrap">
                  {!p.is_active && <Badge variant="neutral">Switched off</Badge>}
                  {p.is_active && !p.holder && <Badge variant="warning">Vacant</Badge>}
                  {p.acting.length > 0 && <Badge variant="info">{p.acting.length} acting {p.acting.length === 1 ? 'cover' : 'covers'}</Badge>}
                  {p.is_active && p.holder && p.acting.length === 0 && <Badge variant="success">Filled</Badge>}
                </div></td>
                <td className="px-3 py-2"><div className="flex items-center justify-end gap-1">
                  <Button size="sm" variant="outline" onClick={() => setHoldersFor(p.id)}>Holders</Button>
                  <Button size="sm" variant="outline" onClick={() => setForm(p)}>Edit</Button>
                </div></td>
              </tr>
            ))}
            {loading && items.length === 0 && <tr><td colSpan={4} className="px-3 py-8 text-center text-gray-500">Loading…</td></tr>}
            {!loading && !error && shown.length === 0 && <tr><td colSpan={4} className="px-3 py-8 text-center text-gray-500">{items.length === 0 ? 'No posts yet. Create the first one.' : 'No posts match your search.'}</td></tr>}
          </tbody>
        </table>
      </Card>
      {form && <PostDialog meta={meta} post={form === 'new' ? null : form} posts={items} onClose={() => setForm(null)} onSaved={() => { setForm(null); setBump((b) => b + 1); }} />}
      {holdersPost && <HoldersDialog post={holdersPost} onClose={() => setHoldersFor(null)} onChanged={() => setBump((b) => b + 1)} onActing={(p) => { setHoldersFor(null); onActing(p); }} />}
    </div>
  );
};
