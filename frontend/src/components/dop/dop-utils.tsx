import React, { useRef, useState } from 'react';
import { inputCls, labelCls } from '../assets/asset-utils';
import { useOrgTime } from '../../lib/org-time';

export { inputCls, labelCls };

export interface Kind { id: number; code: string; name: string; sort_order: number; is_active: boolean; is_system: boolean }
export interface Meta {
  kinds: Kind[];
  subdomains: { code: string; name: string }[];
  scopes: string[];
  departments: { id: number; name: string }[];
  locations: string[];
  roles: string[];
  approver_types: string[];
}
export interface Person { id: number; name: string; email: string }

export interface Cell {
  assignment_id: number;
  source: 'user' | 'department' | 'location' | 'company';
  manager_user_id: number | null;
  manager_name: string | null;
  post_id: number | null;
  post_title: string | null;
  vacant: boolean;
  manager_active?: boolean;
  self_managed?: boolean;
}
export interface ManagerRow {
  user_id: number; name: string; email: string; is_active: boolean;
  department: string | null; location: string | null;
  managers: Record<string, Cell | null>;
}
export interface Assignment {
  id: number; kind_name: string; kind_code: string; scope_type: string;
  scope_user_name: string | null; scope_department_name: string | null; scope_location: string | null;
  manager_user_name: string | null; manager_post_title: string | null;
  subdomains: string[]; starts_on: string; ends_on: string | null; note: string | null;
  status: 'live' | 'scheduled' | 'ended' | 'cancelled';
}
export interface Holder { id: number; user_id: number; user_name: string; starts_on: string; ends_on: string | null }
export interface Cover {
  id: number; key?: string; source: 'acting' | 'out_of_office'; read_only: boolean;
  covers_user_id: number | null; covers_user_name: string | null;
  covers_post_id: number | null; covers_post_title: string | null;
  acting_user_id: number; acting_user_name: string | null;
  subdomains: string[]; starts_on: string; ends_on: string | null;
  original_can_act: boolean; only_when_on_leave: boolean; reason: string | null;
  status: 'live' | 'scheduled' | 'ended' | 'revoked';
}
export interface PostItem {
  id: number; code: string; title: string;
  department_id: number | null; department_name: string | null; location: string | null;
  parent_post_id: number | null; parent_post_title: string | null;
  heads_department_id: number | null; heads_department_name: string | null;
  is_active: boolean; holder: Holder | null; next_holder: Holder | null; acting: Cover[];
}

export const NO_ACCESS = "You need the 'dop manage' permission";

/** Readable text for FastAPI/pydantic 422 arrays, {detail}, {error:{message}} and network failures. */
export const dopErr = (e: any, fallback: string): string => {
  if (e?.response?.status === 403) return NO_ACCESS;
  const data = e?.response?.data;
  const d = data?.detail;
  if (typeof d === 'string' && d.trim()) return d;
  if (Array.isArray(d)) {
    const out = d.map((x: any) => {
      if (typeof x === 'string') return x;
      const msg = String(x?.msg ?? '').replace(/^Value error,\s*/i, '');
      const f = Array.isArray(x?.loc) ? String(x.loc[x.loc.length - 1] ?? '') : '';
      const field = f && !/^\d+$/.test(f) && f !== 'body' ? f.replace(/_/g, ' ') : '';
      if (!msg) return '';
      return field ? `${field[0].toUpperCase()}${field.slice(1)}: ${msg}` : msg;
    }).filter(Boolean);
    if (out.length) return out.join('. ');
  }
  if (d && typeof d === 'object' && typeof d.message === 'string') return d.message;
  if (typeof data?.error?.message === 'string') return data.error.message;
  if (typeof data?.message === 'string') return data.message;
  if (!e?.response) return 'Cannot reach the server. Check your connection and try again.';
  return fallback;
};

export const SOURCE_LABEL: Record<string, string> = {
  user: 'Own', department: 'Department', location: 'Location', company: 'Company',
};

export const APPROVER_LABEL: Record<string, string> = {
  reporting_manager: "The employee's reporting manager",
  dept_head_of_requester: "Head of the employee's department",
  specific_user: 'One named person',
  role: 'Anyone with a role',
  post: 'Whoever holds a post',
  manager_kind: 'A type of manager',
};
export const approverLabel = (t: string) =>
  APPROVER_LABEL[t] ?? (t.charAt(0).toUpperCase() + t.slice(1).replace(/_/g, ' '));

export const subText = (subs: string[] | undefined, meta: Meta | null) =>
  !subs || subs.length === 0
    ? 'Everything'
    : subs.map((c) => meta?.subdomains.find((s) => s.code === c)?.name ?? c).join(', ');

export const addDays = (iso: string, n: number) => {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
};

export const STATUS_VARIANT: Record<string, 'success' | 'info' | 'neutral' | 'warning'> = {
  live: 'success', scheduled: 'info', ended: 'neutral', cancelled: 'neutral', revoked: 'neutral',
};
export const STATUS_TEXT: Record<string, string> = {
  live: 'Active', scheduled: 'Starts later', ended: 'Ended', cancelled: 'Cancelled', revoked: 'Ended early',
};

/** The organisation's date, only once its time zone is known (never the browser's UTC date). */
export const useOrgDate = () => {
  const { today, ready } = useOrgTime();
  return { today: ready ? today : '', ready };
};
export const NO_TIME = "The organisation's time zone has not loaded yet. Wait a moment and try again.";

/** Blocks a second submit before React re-renders (double click, Enter + click). */
export const useGuard = () => {
  const lock = useRef(false);
  const [busy, setBusy] = useState(false);
  const run = async (fn: () => Promise<void>) => {
    if (lock.current) return;
    lock.current = true;
    setBusy(true);
    try { await fn(); } finally { lock.current = false; setBusy(false); }
  };
  return { busy, run };
};

export const Notice: React.FC<{ tone?: 'error' | 'warn' | 'info'; children: React.ReactNode }> = ({ tone = 'error', children }) => {
  const c = tone === 'error' ? 'bg-red-50 text-red-700' : tone === 'warn' ? 'bg-amber-50 text-amber-800' : 'bg-blue-50 text-blue-800';
  return <div role={tone === 'error' ? 'alert' : 'status'} className={`p-3 rounded-lg text-sm ${c}`}>{children}</div>;
};

/** "Everything" or a chosen set of areas. */
export const SubdomainPicker: React.FC<{
  meta: Meta | null; value: string[]; onChange: (v: string[]) => void; idp: string;
}> = ({ meta, value, onChange, idp }) => {
  const all = value.length === 0;
  const toggle = (c: string) => value.length === 1 && value[0] === c ? undefined : onChange(value.includes(c) ? value.filter((x) => x !== c) : [...value, c]);
  return (
    <fieldset>
      <legend className={labelCls}>What it covers</legend>
      <div className="flex gap-4 text-sm mb-2">
        <label className="flex items-center gap-1.5" htmlFor={`${idp}-all`}>
          <input id={`${idp}-all`} type="radio" name={`${idp}-mode`} checked={all} onChange={() => onChange([])} />Everything
        </label>
        <label className="flex items-center gap-1.5" htmlFor={`${idp}-sel`}>
          <input id={`${idp}-sel`} type="radio" name={`${idp}-mode`} checked={!all} onChange={() => meta?.subdomains[0] && onChange([meta.subdomains[0].code])} />Selected areas only
        </label>
      </div>
      {!all && (
        <>
          <div className="grid grid-cols-2 gap-1.5 text-sm">
            {(meta?.subdomains ?? []).map((s) => {
              const last = value.length === 1 && value[0] === s.code;
              return (
                <label key={s.code} className="flex items-center gap-1.5">
                  <input type="checkbox" checked={value.includes(s.code)} disabled={last} onChange={() => toggle(s.code)} />{s.name}
                </label>
              );
            })}
          </div>
          {value.length === 1 && <p className="text-xs text-gray-500 mt-1">At least one area must stay ticked. To cover everything, choose Everything.</p>}
        </>
      )}
    </fieldset>
  );
};
