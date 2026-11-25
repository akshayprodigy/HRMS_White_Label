import React, { useState } from 'react';
import { Badge, fmtDate } from '../ui-elements';

export interface CheckOne {
  user_name: string; subdomain: string; on_date: string; via: 'primary' | 'fallback' | 'hr' | 'blocked';
  approvers: { user_id: number; name: string }[];
  acting_for: { user_id: number; name: string; covers: { name: string }[] }[];
  via_post: { id: number; title: string } | null;
  explanation: string[];
}
export interface CheckAll {
  checked: number; on_date: string; blocked_count: number; via_hr_count: number; truncated: boolean;
  blocked: { user_id: number; name: string; department: string | null; reason: string }[];
  via_hr: { user_id: number; name: string; department: string | null; reason: string }[];
}

const HEAD: Record<CheckOne['via'], { cls: string; title: string; note: string }> = {
  primary: { cls: 'bg-green-50 border-green-200 text-green-700', title: 'Goes to the chosen approver', note: '' },
  fallback: { cls: 'bg-blue-50 border-blue-200 text-blue-900', title: 'Uses the fallback approver', note: 'The first choice could not act.' },
  hr: { cls: 'bg-amber-100 border-amber-400 text-amber-900', title: 'Goes to HR', note: 'Nobody else could be found, so HR would decide.' },
  blocked: { cls: 'bg-red-50 border-red-300 text-red-900', title: 'Blocked: nobody can approve', note: 'This request would get stuck. Fix the setup before relying on this route.' },
};

export const CheckOneResult: React.FC<{ r: CheckOne; capacity: string }> = ({ r, capacity }) => {
  const h = HEAD[r.via];
  const actingFor = (id: number) => r.acting_for.find((a) => a.user_id === id);
  return (
    <section aria-label="Check result" className={`border rounded-lg p-4 space-y-3 ${h.cls}`}>
      <div>
        <h3 className="text-base font-semibold">{h.title}</h3>
        <p className="text-sm">For {r.user_name}, {fmtDate(r.on_date)}. {h.note}</p>
      </div>
      {r.approvers.length > 0 && (
        <ul className="space-y-1 text-sm">
          {r.approvers.map((a) => {
            const af = actingFor(a.user_id);
            return (
              <li key={a.user_id} className="flex items-center gap-2 flex-wrap">
                <span className="font-semibold">{a.name}</span>
                {af ? <Badge variant="info">Acting for {af.covers.map((c) => c.name).join(', ')}</Badge>
                  : r.via_post ? <Badge variant="neutral">As holder of {r.via_post.title}</Badge>
                    : <Badge variant="neutral">{capacity}</Badge>}
              </li>
            );
          })}
        </ul>
      )}
      {r.explanation.length > 0 && (
        <div>
          <h4 className="text-xs font-semibold uppercase tracking-wide opacity-80 mb-1">How this was decided</h4>
          <ol className="text-sm space-y-1">{r.explanation.map((x, i) => <li key={i} className="flex gap-2"><span className="font-semibold">{i + 1}.</span><span>{x}</span></li>)}</ol>
        </div>
      )}
    </section>
  );
};

const SHOW = 8;
const List: React.FC<{ title: string; tone: string; rows: CheckAll['blocked']; total: number }> = ({ title, tone, rows, total }) => {
  const [more, setMore] = useState(false);
  const shown = more ? rows : rows.slice(0, SHOW);
  return (
    <div className={`border rounded-lg p-3 ${tone}`}>
      <h4 className="text-sm font-semibold mb-2">{title} ({total})</h4>
      {rows.length === 0 ? <p className="text-sm">Nobody.</p> : (
        <ul className="divide-y divide-[#E5E7EB] text-sm">
          {shown.map((x) => (
            <li key={x.user_id} className="py-1.5"><span className="font-medium">{x.name}</span>{x.department ? <span className="text-xs"> · {x.department}</span> : null}
              <span className="block text-xs">{x.reason}</span></li>
          ))}
        </ul>
      )}
      {rows.length > SHOW && <button type="button" className="mt-2 text-xs underline" onClick={() => setMore(!more)}>{more ? 'Show fewer' : `Show all ${rows.length}`}</button>}
    </div>
  );
};

export const CheckAllResult: React.FC<{ r: CheckAll }> = ({ r }) => (
  <section aria-label="Check all result" className="space-y-3">
    <p className="text-sm text-gray-700">Checked <strong>{r.checked}</strong> active employees for {fmtDate(r.on_date)}: <strong>{r.blocked_count}</strong> blocked, <strong>{r.via_hr_count}</strong> going to HR, <strong>{r.checked - r.blocked_count - r.via_hr_count}</strong> fine.</p>
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
      <List title="Blocked: nobody can approve" tone="bg-red-50 border-red-300 text-red-900" rows={r.blocked} total={r.blocked_count} />
      <List title="Going to HR" tone="bg-amber-100 border-amber-400 text-amber-900" rows={r.via_hr} total={r.via_hr_count} />
    </div>
    {r.truncated && <p className="text-xs text-gray-500">Only the first 200 of each list are shown.</p>}
  </section>
);
