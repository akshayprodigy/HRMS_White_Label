import React, { useState } from 'react';
import { toast } from 'sonner';
import { Button } from '../ui-elements';
import { client } from '../../api/client';
import { ENDPOINTS } from '../../api/endpoints';
import { Modal } from '../assets/modal';
import { PersonPicker } from './person-picker';
import { Meta, NO_TIME, Notice, Person, PostItem, SubdomainPicker, dopErr, inputCls, labelCls, useGuard, useOrgDate } from './dop-utils';

/** Create an acting cover for a person or a post. */
export const ActingDialog: React.FC<{
  meta: Meta | null; prefillPost: PostItem | null; onClose: () => void; onSaved: () => void;
}> = ({ meta, prefillPost, onClose, onSaved }) => {
  const [mode, setMode] = useState<'person' | 'post'>(prefillPost ? 'post' : 'person');
  const [covered, setCovered] = useState<Person | null>(null);
  const [postId, setPostId] = useState(prefillPost ? String(prefillPost.id) : '');
  const [acting, setActing] = useState<Person | null>(null);
  const [subs, setSubs] = useState<string[]>([]);
  const { today, ready } = useOrgDate();
  const [start, setStart] = useState('');
  React.useEffect(() => { if (ready && !start) setStart(today); }, [ready, today, start]);
  const [endOn, setEndOn] = useState('');
  const [onLeave, setOnLeave] = useState(false);
  const [orig, setOrig] = useState(false);
  const [reason, setReason] = useState('');
  const [posts, setPosts] = useState<PostItem[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const { busy, run } = useGuard();

  React.useEffect(() => {
    if (mode !== 'post' || posts) return;
    client.get<PostItem[]>(ENDPOINTS.DOP.POSTS, { params: { include_inactive: false } }).then((r) => setPosts(r.data)).catch((e) => { setPosts([]); setErr(dopErr(e, 'Could not load posts')); });
  }, [mode, posts]);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    run(async () => {
      setErr(null);
      if (!ready) return setErr(NO_TIME);
      if (mode === 'person' && !covered) return setErr('Choose the person being covered.');
      if (mode === 'post' && !postId) return setErr('Choose the post being covered.');
      if (!acting) return setErr('Choose who will act.');
      if (!start) return setErr('Choose a start date.');
      if (endOn && endOn < start) return setErr('The end date is before the start date.');
      const body: Record<string, unknown> = {
        acting_user_id: acting.id, subdomains: subs, starts_on: start, ends_on: endOn || null,
        original_can_act: orig, only_when_on_leave: onLeave, reason: reason.trim() || null,
      };
      if (mode === 'person') body.covers_user_id = covered!.id; else body.covers_post_id = Number(postId);
      try {
        await client.post(ENDPOINTS.DOP.ACTING, body);
        toast.success('Acting cover created');
        onSaved();
      } catch (ex: any) { setErr(dopErr(ex, 'Could not create the cover')); }
    });
  };

  return (
    <Modal title="New acting cover" label="New acting cover" onClose={onClose} busy={busy} wide>
      <form noValidate className="space-y-4" onSubmit={submit}>
        <fieldset className="space-y-2">
          <legend className={labelCls}>Who is being covered</legend>
          <div className="flex gap-4 text-sm">
            <label className="flex items-center gap-1.5"><input type="radio" name="ac-mode" checked={mode === 'person'} onChange={() => setMode('person')} />A person</label>
            <label className="flex items-center gap-1.5"><input type="radio" name="ac-mode" checked={mode === 'post'} onChange={() => setMode('post')} />A post</label>
          </div>
          {mode === 'person'
            ? <PersonPicker id="ac-cov" label="Person being covered" value={covered} onChange={setCovered} required />
            : (
              <div>
                <label className={labelCls} htmlFor="ac-post">Post *</label>
                <select id="ac-post" className={`${inputCls} w-full`} value={postId} onChange={(e) => setPostId(e.target.value)}>
                  <option value="">{posts ? 'Choose…' : 'Loading…'}</option>
                  {prefillPost && !posts?.some((p) => p.id === prefillPost.id) && <option value={prefillPost.id}>{prefillPost.title}</option>}
                  {(posts ?? []).map((p) => <option key={p.id} value={p.id}>{p.title}{p.holder ? ` (${p.holder.user_name})` : ' (vacant)'}</option>)}
                </select>
              </div>
            )}
        </fieldset>
        <PersonPicker id="ac-act" label="Person who will act" value={acting} onChange={setActing} required />
        <SubdomainPicker meta={meta} value={subs} onChange={setSubs} idp="ac-sub" />
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div><label className={labelCls} htmlFor="ac-start">Starts on *</label><input id="ac-start" type="date" className={`${inputCls} w-full`} value={start} onChange={(e) => setStart(e.target.value)} /></div>
          <div><label className={labelCls} htmlFor="ac-end">Ends on (optional)</label><input id="ac-end" type="date" min={start} className={`${inputCls} w-full`} value={endOn} onChange={(e) => setEndOn(e.target.value)} /></div>
        </div>
        <label className="flex items-start gap-2 text-sm"><input type="checkbox" className="mt-1" checked={onLeave} onChange={(e) => setOnLeave(e.target.checked)} />Only act while the person being covered is on approved leave</label>
        <label className="flex items-start gap-2 text-sm"><input type="checkbox" className="mt-1" checked={orig} onChange={(e) => setOrig(e.target.checked)} />The original person can also approve</label>
        <div><label className={labelCls} htmlFor="ac-reason">Reason (optional)</label><input id="ac-reason" maxLength={255} className={`${inputCls} w-full`} value={reason} onChange={(e) => setReason(e.target.value)} /></div>
        {err && <Notice>{err}</Notice>}
        <div className="flex justify-end gap-2">
          <Button variant="outline" type="button" onClick={onClose} disabled={busy}>Cancel</Button>
          <Button type="submit" isLoading={busy}>Create cover</Button>
        </div>
      </form>
    </Modal>
  );
};
