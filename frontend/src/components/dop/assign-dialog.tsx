import React, { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Button, fmtDate } from '../ui-elements';
import { client } from '../../api/client';
import { ENDPOINTS } from '../../api/endpoints';
import { Modal } from '../assets/modal';
import { orgToday } from '../../lib/org-time';
import { PersonPicker } from './person-picker';
import { Meta, Notice, Person, PostItem, SubdomainPicker, dopErr, inputCls, labelCls, useGuard } from './dop-utils';

type Target = 'selected' | 'department' | 'location' | 'company';

/** Give employees (selected, or a whole department/location/company) a manager of one type. */
export const AssignDialog: React.FC<{
  meta: Meta | null; picked: Map<number, string>; onClose: () => void; onDone: () => void;
}> = ({ meta, picked, onClose, onDone }) => {
  const kinds = (meta?.kinds ?? []).filter((k) => k.is_active);
  const [kindId, setKindId] = useState('');
  const [target, setTarget] = useState<Target>(picked.size > 0 ? 'selected' : 'department');
  const [deptId, setDeptId] = useState('');
  const [loc, setLoc] = useState('');
  const [sure, setSure] = useState(false);
  const [mode, setMode] = useState<'person' | 'post'>('person');
  const [person, setPerson] = useState<Person | null>(null);
  const [postId, setPostId] = useState('');
  const [posts, setPosts] = useState<PostItem[]>([]);
  const [subs, setSubs] = useState<string[]>([]);
  const [start, setStart] = useState(orgToday);
  const [endOn, setEndOn] = useState('');
  const [note, setNote] = useState('');
  const [err, setErr] = useState<string | null>(null);
  const [conflict, setConflict] = useState(false);
  const { busy, run } = useGuard();

  useEffect(() => { if (!kindId && kinds[0]) setKindId(String((kinds.find((k) => k.code === 'reporting') ?? kinds[0]).id)); }, [kinds, kindId]);
  useEffect(() => {
    client.get<PostItem[]>(ENDPOINTS.DOP.POSTS, { params: { include_inactive: false } }).then((r) => setPosts(r.data)).catch(() => setPosts([]));
  }, []);

  const kind = kinds.find((k) => String(k.id) === kindId);
  const submit = (replace: boolean) => run(async () => {
    setErr(null); setConflict(false);
    if (!kind) return setErr('Choose a manager type.');
    if (mode === 'person' && !person) return setErr('Choose the manager.');
    if (mode === 'post' && !postId) return setErr('Choose the post.');
    if (target === 'department' && !deptId) return setErr('Choose a department.');
    if (target === 'location' && !loc) return setErr('Choose a location.');
    if (target === 'company' && !sure) return setErr('Tick the box to confirm this applies to the whole company.');
    if (!start) return setErr('Choose a start date.');
    if (endOn && endOn < start) return setErr('The end date is before the start date.');
    const body: Record<string, unknown> = {
      kind_id: kind.id, subdomains: subs, starts_on: start, ends_on: endOn || null, note: note.trim() || null, replace,
    };
    if (mode === 'person') body.manager_user_id = person!.id; else body.manager_post_id = Number(postId);
    if (target === 'selected') body.user_ids = [...picked.keys()];
    else {
      body.scope_type = target;
      if (target === 'department') body.scope_department_id = Number(deptId);
      if (target === 'location') body.scope_location = loc;
    }
    try {
      const r = await client.post(ENDPOINTS.DOP.ASSIGNMENTS_BULK, body);
      const d = r.data;
      toast.success(`Manager set${target === 'selected' ? ` for ${d.created} ${d.created === 1 ? 'employee' : 'employees'}` : ''}${d.replaced ? `, ${d.replaced} replaced` : ''}${d.continued ? `, ${d.continued} earlier ${d.continued === 1 ? 'manager resumes' : 'managers resume'} afterwards` : ''}`);
      onDone();
    } catch (e: any) {
      const m = dopErr(e, 'Could not save the assignment');
      if (e?.response?.status === 409) setConflict(true);
      if (!(e?.response?.status === 409 && /^Overlaps/.test(m))) setErr(m);
    }
  });

  return (
    <Modal title="Assign managers" label="Assign managers" onClose={onClose} busy={busy} wide>
      <form noValidate className="space-y-4" onSubmit={(e) => { e.preventDefault(); submit(false); }}>
        {kind?.code === 'reporting' && <Notice tone="warn">Reporting managers take effect straight away for live approvals.</Notice>}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className={labelCls} htmlFor="ad-kind">Type of manager *</label>
            <select id="ad-kind" className={`${inputCls} w-full`} value={kindId} onChange={(e) => setKindId(e.target.value)}>
              {kinds.map((k) => <option key={k.id} value={k.id}>{k.name}</option>)}
            </select>
          </div>
          <div>
            <label className={labelCls} htmlFor="ad-target">Who gets this manager *</label>
            <select id="ad-target" className={`${inputCls} w-full`} value={target} onChange={(e) => { setTarget(e.target.value as Target); setSure(false); }}>
              <option value="selected" disabled={picked.size === 0}>The {picked.size} selected {picked.size === 1 ? 'employee' : 'employees'}</option>
              <option value="department">Everyone in a department</option>
              <option value="location">Everyone at a location</option>
              <option value="company">Everyone in the company</option>
            </select>
          </div>
        </div>
        {target === 'department' && (
          <div>
            <label className={labelCls} htmlFor="ad-dept">Department *</label>
            <select id="ad-dept" className={`${inputCls} w-full`} value={deptId} onChange={(e) => setDeptId(e.target.value)}>
              <option value="">Choose…</option>
              {(meta?.departments ?? []).map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
            </select>
          </div>
        )}
        {target === 'location' && (
          <div>
            <label className={labelCls} htmlFor="ad-loc">Location *</label>
            <select id="ad-loc" className={`${inputCls} w-full`} value={loc} onChange={(e) => setLoc(e.target.value)}>
              <option value="">Choose…</option>
              {(meta?.locations ?? []).map((l) => <option key={l} value={l}>{l}</option>)}
            </select>
          </div>
        )}
        {target === 'company' && (
          <label className="flex items-start gap-2 text-sm"><input type="checkbox" className="mt-1" checked={sure} onChange={(e) => setSure(e.target.checked)} />
            I understand this applies to every employee who has no more specific manager of this type.</label>
        )}
        {target === 'selected' && picked.size > 0 && (
          <p className="text-xs text-gray-500">{[...picked.values()].slice(0, 6).join(', ')}{picked.size > 6 ? ` and ${picked.size - 6} more` : ''}</p>
        )}

        <fieldset className="space-y-2">
          <legend className={labelCls}>The manager is</legend>
          <div className="flex gap-4 text-sm">
            <label className="flex items-center gap-1.5"><input type="radio" name="ad-mode" checked={mode === 'person'} onChange={() => setMode('person')} />A person</label>
            <label className="flex items-center gap-1.5"><input type="radio" name="ad-mode" checked={mode === 'post'} onChange={() => setMode('post')} />Whoever holds a post</label>
          </div>
          {mode === 'person' ? (
            <PersonPicker id="ad-person" label="Manager" value={person} onChange={setPerson} required />
          ) : (
            <div>
              <label className={labelCls} htmlFor="ad-post">Post *</label>
              <select id="ad-post" className={`${inputCls} w-full`} value={postId} onChange={(e) => setPostId(e.target.value)}>
                <option value="">Choose…</option>
                {posts.map((p) => <option key={p.id} value={p.id}>{p.title}{p.holder ? ` (${p.holder.user_name})` : ' (vacant)'}</option>)}
              </select>
            </div>
          )}
        </fieldset>

        <SubdomainPicker meta={meta} value={subs} onChange={setSubs} idp="ad-sub" />

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className={labelCls} htmlFor="ad-start">Starts on *</label>
            <input id="ad-start" type="date" className={`${inputCls} w-full`} value={start} onChange={(e) => setStart(e.target.value)} />
          </div>
          <div>
            <label className={labelCls} htmlFor="ad-end">Ends on (optional)</label>
            <input id="ad-end" type="date" className={`${inputCls} w-full`} value={endOn} min={start} onChange={(e) => setEndOn(e.target.value)} />
          </div>
        </div>
        <div>
          <label className={labelCls} htmlFor="ad-note">Note (optional)</label>
          <input id="ad-note" maxLength={255} className={`${inputCls} w-full`} value={note} onChange={(e) => setNote(e.target.value)} />
        </div>

        {err && <Notice>{err}</Notice>}
        {conflict && (
          <Notice tone="warn">
            Some of these employees already have a manager of this type for those dates. You can replace the existing one: it will end the day before the new one starts.
            {endOn && <p className="mt-1">Because you set an end date ({fmtDate(endOn)}), the previous manager comes back the day after it.</p>}
            <div className="mt-2"><Button size="sm" variant="danger" type="button" disabled={busy} onClick={() => submit(true)}>Replace existing</Button></div>
          </Notice>
        )}
        <div className="flex justify-end gap-2">
          <Button variant="outline" type="button" onClick={onClose} disabled={busy}>Cancel</Button>
          <Button type="submit" isLoading={busy}>Assign</Button>
        </div>
      </form>
    </Modal>
  );
};
