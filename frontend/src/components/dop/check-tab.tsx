import React, { useRef, useState } from 'react';
import { Button, Card } from '../ui-elements';
import { client } from '../../api/client';
import { ENDPOINTS } from '../../api/endpoints';
import { orgToday } from '../../lib/org-time';
import { ApproverBuilder, ApproverValue, approverBody, emptyApprover } from './approver-builder';
import { CheckAll, CheckAllResult, CheckOne, CheckOneResult } from './check-result';
import { PersonPicker } from './person-picker';
import { Meta, Notice, Person, dopErr, inputCls, labelCls } from './dop-utils';

const capacity = (via: string, a: ApproverValue, meta: Meta | null): string => {
  if (via === 'hr') return 'As HR';
  switch (a.type) {
    case 'reporting_manager': return 'As their reporting manager';
    case 'dept_head_of_requester': return 'As head of their department';
    case 'specific_user': return 'Named directly';
    case 'role': return `Because they have the ${a.ref ?? ''} role`;
    case 'manager_kind': return `As their ${meta?.kinds.find((k) => k.code === a.ref)?.name.toLowerCase() ?? 'manager'}`;
    default: return 'As approver';
  }
};

/** "Who would approve this?" without changing anything. */
export const CheckTab: React.FC<{ meta: Meta | null }> = ({ meta }) => {
  const [emp, setEmp] = useState<Person | null>(null);
  const [sub, setSub] = useState('leave');
  const [on, setOn] = useState(orgToday);
  const [ap, setAp] = useState<ApproverValue>(emptyApprover());
  const [useFb, setUseFb] = useState(false);
  const [fb, setFb] = useState<ApproverValue>(emptyApprover('role'));
  const [one, setOne] = useState<CheckOne | null>(null);
  const [all, setAll] = useState<CheckAll | null>(null);
  const [busy, setBusy] = useState<'one' | 'all' | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [usedAp, setUsedAp] = useState<ApproverValue>(ap);
  const [usedFb, setUsedFb] = useState<ApproverValue | null>(null);
  const seq = useRef(0);

  const go = async (mode: 'one' | 'all') => {
    if (busy) return;
    setErr(null);
    if (mode === 'one' && !emp) return setErr('Choose an employee to check.');
    const a = approverBody(ap, 'Approver');
    if (typeof a === 'string') return setErr(a);
    const f = useFb ? approverBody(fb, 'Fallback') : undefined;
    if (typeof f === 'string') return setErr(f);
    const n = ++seq.current;
    setUsedAp(ap); setUsedFb(useFb ? fb : null);
    setBusy(mode);
    const body: Record<string, unknown> = { subdomain: sub, on_date: on || null, approver: a, fallback: f ?? null };
    try {
      if (mode === 'one') {
        const r = await client.post<CheckOne>(ENDPOINTS.DOP.CHECK, { ...body, user_id: emp!.id });
        if (n === seq.current) { setOne(r.data); setAll(null); }
      } else {
        const r = await client.post<CheckAll>(ENDPOINTS.DOP.CHECK_ALL, body);
        if (n === seq.current) { setAll(r.data); setOne(null); }
      }
    } catch (e: any) {
      if (n === seq.current) { setErr(dopErr(e, 'The check failed')); setOne(null); setAll(null); }
    } finally {
      if (n === seq.current) setBusy(null);
    }
  };

  return (
    <div className="space-y-4">
      <p className="text-sm text-gray-600">Try a route before you rely on it. This only answers "who would approve?" and changes nothing.</p>
      <Card className="p-4 space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <PersonPicker id="ck-emp" label="Employee making the request" value={emp} onChange={setEmp} />
          <div>
            <label className={labelCls} htmlFor="ck-sub">Kind of request</label>
            <select id="ck-sub" className={`${inputCls} w-full`} value={sub} onChange={(e) => setSub(e.target.value)}>
              {(meta?.subdomains ?? []).map((s) => <option key={s.code} value={s.code}>{s.name}</option>)}
            </select>
          </div>
          <div>
            <label className={labelCls} htmlFor="ck-on">On the date</label>
            <input id="ck-on" type="date" className={`${inputCls} w-full`} value={on} onChange={(e) => setOn(e.target.value)} />
          </div>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <ApproverBuilder idp="ck-ap" label="Who should approve" meta={meta} value={ap} onChange={setAp} />
          <div className="space-y-2">
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={useFb} onChange={(e) => setUseFb(e.target.checked)} />If they cannot, try someone else (fallback)</label>
            {useFb && <ApproverBuilder idp="ck-fb" label="Fallback approver" meta={meta} value={fb} onChange={setFb} />}
          </div>
        </div>
        {err && <Notice>{err}</Notice>}
        <div className="flex gap-2 flex-wrap">
          <Button onClick={() => go('one')} isLoading={busy === 'one'} disabled={busy !== null}>Check this employee</Button>
          <Button variant="outline" onClick={() => go('all')} isLoading={busy === 'all'} disabled={busy !== null}>Check all employees</Button>
        </div>
      </Card>
      {one && <CheckOneResult r={one} capacity={capacity(one.via, one.via === 'fallback' && usedFb ? usedFb : usedAp, meta)} />}
      {all && <CheckAllResult r={all} />}
    </div>
  );
};
