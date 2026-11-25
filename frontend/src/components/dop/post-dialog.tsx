import React, { useState } from 'react';
import { toast } from 'sonner';
import { Button } from '../ui-elements';
import { client } from '../../api/client';
import { ENDPOINTS } from '../../api/endpoints';
import { Modal } from '../assets/modal';
import { Meta, Notice, PostItem, dopErr, inputCls, labelCls, useGuard } from './dop-utils';

/** Create or edit a post. */
export const PostDialog: React.FC<{
  meta: Meta | null; post: PostItem | null; posts: PostItem[]; onClose: () => void; onSaved: () => void;
}> = ({ meta, post, posts, onClose, onSaved }) => {
  const [code, setCode] = useState(post?.code ?? '');
  const [title, setTitle] = useState(post?.title ?? '');
  const [dept, setDept] = useState(post?.department_id ? String(post.department_id) : '');
  const [loc, setLoc] = useState(post?.location ?? '');
  const [parent, setParent] = useState(post?.parent_post_id ? String(post.parent_post_id) : '');
  const [heads, setHeads] = useState(post?.heads_department_id ? String(post.heads_department_id) : '');
  const [active, setActive] = useState(post?.is_active ?? true);
  const [err, setErr] = useState<string | null>(null);
  const { busy, run } = useGuard();

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    run(async () => {
      setErr(null);
      if (!code.trim()) return setErr('Give the post a short code.');
      if (!title.trim()) return setErr('Give the post a title.');
      const body = {
        code: code.trim(), title: title.trim(), department_id: dept ? Number(dept) : null, location: loc.trim() || null,
        parent_post_id: parent ? Number(parent) : null, heads_department_id: heads ? Number(heads) : null, is_active: active,
      };
      try {
        if (post) await client.patch(ENDPOINTS.DOP.POST(post.id), body); else await client.post(ENDPOINTS.DOP.POSTS, body);
        toast.success(post ? 'Post saved' : 'Post created');
        onSaved();
      } catch (ex: any) { setErr(dopErr(ex, 'Could not save the post')); }
    });
  };
  const depts = meta?.departments ?? [];
  return (
    <Modal title={post ? `Edit ${post.title}` : 'New post'} label={post ? 'Edit post' : 'New post'} onClose={onClose} busy={busy}>
      <form className="space-y-3" onSubmit={submit}>
        <div className="grid grid-cols-2 gap-3">
          <div><label className={labelCls} htmlFor="pd-title">Title *</label><input id="pd-title" maxLength={120} className={`${inputCls} w-full`} value={title} onChange={(e) => setTitle(e.target.value)} /></div>
          <div><label className={labelCls} htmlFor="pd-code">Short code *</label><input id="pd-code" maxLength={40} className={`${inputCls} w-full`} value={code} onChange={(e) => setCode(e.target.value)} /></div>
          <div>
            <label className={labelCls} htmlFor="pd-dept">Department</label>
            <select id="pd-dept" className={`${inputCls} w-full`} value={dept} onChange={(e) => setDept(e.target.value)}>
              <option value="">None</option>{depts.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
            </select>
          </div>
          <div>
            <label className={labelCls} htmlFor="pd-loc">Location</label>
            <select id="pd-loc" className={`${inputCls} w-full`} value={loc} onChange={(e) => setLoc(e.target.value)}>
              <option value="">None</option>{(meta?.locations ?? []).map((l) => <option key={l} value={l}>{l}</option>)}
            </select>
          </div>
          <div>
            <label className={labelCls} htmlFor="pd-parent">Reports to (post)</label>
            <select id="pd-parent" className={`${inputCls} w-full`} value={parent} onChange={(e) => setParent(e.target.value)}>
              <option value="">Top of the chart</option>
              {posts.filter((p) => p.id !== post?.id).map((p) => <option key={p.id} value={p.id}>{p.title}</option>)}
            </select>
          </div>
          <div>
            <label className={labelCls} htmlFor="pd-heads">Is the head of department</label>
            <select id="pd-heads" className={`${inputCls} w-full`} value={heads} onChange={(e) => setHeads(e.target.value)}>
              <option value="">No</option>{depts.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
            </select>
          </div>
        </div>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} />Post is in use</label>
        {err && <Notice>{err}</Notice>}
        <div className="flex justify-end gap-2">
          <Button variant="outline" type="button" onClick={onClose} disabled={busy}>Cancel</Button>
          <Button type="submit" isLoading={busy}>{post ? 'Save' : 'Create post'}</Button>
        </div>
      </form>
    </Modal>
  );
};
