import React, { useEffect, useState } from 'react';
import { client } from '../../api/client';
import { ENDPOINTS } from '../../api/endpoints';
import { PersonPicker } from './person-picker';
import { Meta, Person, PostItem, approverLabel, inputCls, labelCls } from './dop-utils';

export interface ApproverValue { type: string; ref: string | null; person: Person | null }
export const emptyApprover = (type = 'reporting_manager'): ApproverValue => ({ type, ref: null, person: null });
export const needsRef = (t: string) => !['reporting_manager', 'dept_head_of_requester'].includes(t);

/** Valid body for the API, or the reason it is not ready yet. */
export const approverBody = (a: ApproverValue, what: string): { type: string; ref?: string } | string => {
  if (!needsRef(a.type)) return { type: a.type };
  if (a.type === 'specific_user') return a.person ? { type: a.type, ref: String(a.person.id) } : `${what}: choose the person.`;
  if (!a.ref) return `${what}: choose ${a.type === 'role' ? 'a role' : a.type === 'post' ? 'a post' : 'a manager type'}.`;
  return { type: a.type, ref: a.ref };
};

/** Pick who should approve: a rule type plus, where it needs one, the person, role, post or manager type. */
export const ApproverBuilder: React.FC<{
  idp: string; label: string; meta: Meta | null; value: ApproverValue; onChange: (v: ApproverValue) => void;
}> = ({ idp, label, meta, value, onChange }) => {
  const [posts, setPosts] = useState<PostItem[]>([]);
  useEffect(() => {
    if (value.type !== 'post' || posts.length) return;
    client.get<PostItem[]>(ENDPOINTS.DOP.POSTS, { params: { include_inactive: false } }).then((r) => setPosts(r.data)).catch(() => setPosts([]));
  }, [value.type, posts.length]);
  const types = meta?.approver_types ?? [];
  return (
    <div className="space-y-2">
      <label className={labelCls} htmlFor={`${idp}-type`}>{label}</label>
      <select id={`${idp}-type`} className={`${inputCls} w-full`} value={value.type} onChange={(e) => onChange(emptyApprover(e.target.value))}>
        {types.map((t) => <option key={t} value={t}>{approverLabel(t)}</option>)}
      </select>
      {value.type === 'specific_user' && (
        <PersonPicker id={`${idp}-person`} label="Person" value={value.person} onChange={(p) => onChange({ ...value, person: p })} required />
      )}
      {value.type === 'role' && (
        <select aria-label="Role" className={`${inputCls} w-full`} value={value.ref ?? ''} onChange={(e) => onChange({ ...value, ref: e.target.value || null })}>
          <option value="">Choose a role…</option>{(meta?.roles ?? []).map((r) => <option key={r} value={r}>{r}</option>)}
        </select>
      )}
      {value.type === 'post' && (
        <select aria-label="Post" className={`${inputCls} w-full`} value={value.ref ?? ''} onChange={(e) => onChange({ ...value, ref: e.target.value || null })}>
          <option value="">Choose a post…</option>{posts.map((p) => <option key={p.id} value={p.id}>{p.title}</option>)}
        </select>
      )}
      {value.type === 'manager_kind' && (
        <select aria-label="Type of manager" className={`${inputCls} w-full`} value={value.ref ?? ''} onChange={(e) => onChange({ ...value, ref: e.target.value || null })}>
          <option value="">Choose a type of manager…</option>{(meta?.kinds ?? []).filter((k) => k.is_active).map((k) => <option key={k.id} value={k.code}>{k.name}</option>)}
        </select>
      )}
    </div>
  );
};
