import React, { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Badge, Button, fmtDate } from '../ui-elements';
import { client } from '../../api/client';
import { ENDPOINTS } from '../../api/endpoints';
import { Modal } from '../assets/modal';
import { ConfirmDialog } from './confirm-dialog';
import { PersonPicker } from './person-picker';
import { Holder, NO_TIME, Notice, Person, PostItem, addDays, dopErr, inputCls, labelCls, useGuard, useOrgDate } from './dop-utils';

/** Who holds a post: hand over, end a holding, remove a mistaken one, see the history. */
export const HoldersDialog: React.FC<{
  post: PostItem; onClose: () => void; onChanged: () => void; onActing: (p: PostItem) => void;
}> = ({ post, onClose, onChanged, onActing }) => {
  const [hist, setHist] = useState<Holder[] | null>(null);
  const [person, setPerson] = useState<Person | null>(null);
  const { today, ready } = useOrgDate();
  const [start, setStart] = useState('');
  const [endOn, setEndOn] = useState('');
  const [err, setErr] = useState<string | null>(null);
  const [suggest, setSuggest] = useState(false);
  const [ending, setEnding] = useState<number | null>(null);
  const [endDate, setEndDate] = useState('');
  const [listErr, setListErr] = useState<string | null>(null);
  const [removing, setRemoving] = useState<Holder | null>(null);
  const { busy, run } = useGuard();
  React.useEffect(() => { if (ready && !start) setStart(today); }, [ready, today, start]);

  const load = useCallback(async () => {
    try {
      const r = await client.get(ENDPOINTS.DOP.POST_HOLDERS(post.id));
      setHist([...(r.data.holders as Holder[])].sort((a, b) => (b.starts_on < a.starts_on ? -1 : 1)));
    } catch (e: any) { setListErr(dopErr(e, 'Could not load the history')); setHist((x) => x ?? []); }
  }, [post.id]);
  useEffect(() => { load(); }, [load]);

  const openEnded = !!hist?.some((h) => !h.ends_on && h.starts_on <= start);
  const handover = (e: React.FormEvent) => {
    e.preventDefault();
    run(async () => {
      setErr(null); setSuggest(false);
      if (!ready) return setErr(NO_TIME);
      if (!person) return setErr('Choose who takes over.');
      if (endOn && endOn < start) return setErr('The end date is before the start date.');
      try {
        await client.post(ENDPOINTS.DOP.POST_HOLDERS(post.id), { user_id: person.id, starts_on: start, ends_on: endOn || null });
        toast.success('Handover saved'); setPerson(null); setEndOn(''); onChanged(); await load();
      } catch (ex: any) {
        const m = dopErr(ex, 'Could not save the handover');
        setErr(m);
        if (endOn && ex?.response?.status === 409 && /acting/i.test(m)) setSuggest(true);
      }
    });
  };
  const endHolder = (h: Holder) => run(async () => {
    setListErr(null);
    if (!endDate) return setListErr('Choose the last day.');
    try {
      await client.post(ENDPOINTS.DOP.HOLDER_END(post.id, h.id), { ends_on: endDate });
      toast.success('Holding ended'); setEnding(null); onChanged(); await load();
    } catch (ex: any) { setListErr(dopErr(ex, 'Could not end it')); }
  });
  const remove = async (reopen: boolean) => {
    await client.post(ENDPOINTS.DOP.HOLDER_REMOVE(post.id, removing!.id), { reopen_previous: reopen });
    toast.success('Holder removed'); setRemoving(null); onChanged(); await load();
  };
  const prev = removing ? hist?.find((x) => x.id !== removing.id && x.ends_on === addDays(removing.starts_on, -1)) : undefined;
  const state = (h: Holder) => (h.ends_on && h.ends_on < today ? 'Past' : h.starts_on > today ? 'Starts later' : 'Current');

  return (
    <Modal title={`Holders of ${post.title}`} label={`Holders of ${post.title}`} onClose={onClose} busy={busy} wide>
      <form noValidate onSubmit={handover} className="space-y-3 border border-gray-100 rounded-lg p-3">
        <h4 className="text-sm font-medium text-gray-800">Hand the post over</h4>
        <PersonPicker id="hd-person" label="New holder" value={person} onChange={setPerson} required />
        <div className="grid grid-cols-2 gap-3">
          <div><label className={labelCls} htmlFor="hd-start">Starts on</label><input id="hd-start" type="date" min={today || undefined} className={`${inputCls} w-full`} value={start} onChange={(e) => setStart(e.target.value)} /></div>
          <div><label className={labelCls} htmlFor="hd-end">Ends on (optional)</label><input id="hd-end" type="date" className={`${inputCls} w-full`} value={endOn} onChange={(e) => setEndOn(e.target.value)} /></div>
        </div>
        {endOn && openEnded && (
          <Notice tone="info">The current holder has no end date, so a handover with an end date is refused. For a short stand-in, use an acting cover instead (used for approvals from the next release).</Notice>
        )}
        {err && <Notice>{err}</Notice>}
        {(suggest || (endOn && openEnded && err)) && (
          <Button size="sm" type="button" variant="outline" onClick={() => onActing(post)}>Set up an acting cover for {post.title} (used for approvals from the next release)</Button>
        )}
        <div className="flex justify-end"><Button type="submit" isLoading={busy}>Hand over</Button></div>
      </form>

      <h4 className="text-sm font-medium text-gray-800">History</h4>
      {listErr && <Notice>{listErr}</Notice>}
      {!ready && <p className="text-sm text-gray-500">Waiting for the organisation's time zone…</p>}
      {hist === null && <p className="text-sm text-gray-500">Loading…</p>}
      {hist?.length === 0 && <p className="text-sm text-gray-500">Nobody has held this post yet.</p>}
      <ul className="space-y-2">
        {ready && hist?.map((h) => (
          <li key={h.id} className="border border-gray-100 rounded-lg p-3 text-sm space-y-2">
            <div className="flex items-center justify-between gap-2 flex-wrap">
              <span><span className="font-medium">{h.user_name}</span> <span className="text-xs text-gray-600">{fmtDate(h.starts_on)} to {h.ends_on ? fmtDate(h.ends_on) : 'no end date'}</span></span>
              <span className="flex items-center gap-2">
                <Badge variant={state(h) === 'Current' ? 'success' : state(h) === 'Past' ? 'neutral' : 'info'}>{state(h)}</Badge>
                {h.starts_on <= today && !(h.ends_on && h.ends_on < today) && ending !== h.id && (
                  <Button size="sm" variant="outline" onClick={() => { setEnding(h.id); setListErr(null); setEndDate(today); }}>End</Button>
                )}
                {h.starts_on >= today && <Button size="sm" variant="outline" onClick={() => setRemoving(h)}>Remove</Button>}
              </span>
            </div>
            {ending === h.id && (
              <div className="flex items-end gap-2 flex-wrap">
                <div><label className={labelCls} htmlFor={`hd-e-${h.id}`}>Last day</label><input id={`hd-e-${h.id}`} type="date" min={h.starts_on} className={inputCls} value={endDate} onChange={(e) => setEndDate(e.target.value)} /></div>
                <Button size="sm" variant="danger" isLoading={busy} onClick={() => endHolder(h)}>End holding</Button>
                <Button size="sm" variant="outline" disabled={busy} onClick={() => setEnding(null)}>Cancel</Button>
              </div>
            )}
          </li>
        ))}
      </ul>
      <div className="flex justify-end"><Button variant="outline" onClick={onClose} disabled={busy}>Close</Button></div>

      {removing && (
        <RemoveDialog holder={removing} prev={prev} onClose={() => setRemoving(null)} onRemove={remove} />
      )}
    </Modal>
  );
};

const RemoveDialog: React.FC<{ holder: Holder; prev?: Holder; onClose: () => void; onRemove: (reopen: boolean) => Promise<void> }> = ({ holder, prev, onClose, onRemove }) => {
  const [reopen, setReopen] = useState(!!prev);
  return (
    <ConfirmDialog
      title={`Remove ${holder.user_name} from the post`} confirmText={reopen && prev ? `Give the post back to ${prev.user_name}` : 'Remove and leave vacant'} danger
      onClose={onClose} onConfirm={() => onRemove(reopen)}
      body={(
        <>
          <p>{holder.user_name} has not started yet (starts {fmtDate(holder.starts_on)}).</p>
          {prev ? (
            <div className="space-y-1">
              <label className="flex items-center gap-2"><input type="radio" name="rm" checked={reopen} onChange={() => setReopen(true)} />Give the post back to {prev.user_name}</label>
              <label className="flex items-center gap-2"><input type="radio" name="rm" checked={!reopen} onChange={() => setReopen(false)} />Leave it vacant</label>
            </div>
          ) : null}
          {!reopen && <Notice tone="warn">The post will be vacant from {fmtDate(holder.starts_on)} and anything routed to it will have nobody to go to.</Notice>}
        </>
      )}
    />
  );
};
