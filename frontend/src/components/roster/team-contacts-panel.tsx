import { useEffect, useState } from 'react';
import { Phone } from 'lucide-react';
import { client } from '../../api/client';
import { ENDPOINTS } from '../../api/endpoints';
import { Card } from '../ui-elements';
import { errMsg } from '../schedule-delegations-utils';

interface TeamContact {
  user_id: number;
  name: string | null;
  department: string | null;
  phone: string | null;
  blood_group: string | null;
  contacts: { id: number; name: string; relation: string; phone: string; is_primary: boolean }[];
}

const Tel = ({ phone, label }: { phone: string; label: string }) => (
  <span className="inline-flex items-center gap-1.5 tabular-nums">
    <span>{phone}</span>
    <a href={`tel:${phone.replace(/[^\d+]/g, '')}`} aria-label={label}
      className="inline-flex items-center gap-0.5 text-indigo-600 hover:underline">
      <Phone className="w-3 h-3" aria-hidden="true" /> Call
    </a>
  </span>
);

/** Emergency contacts for the employees the viewer schedules. */
export const TeamContactsPanel = ({ department }: { department: string }) => {
  const [rows, setRows] = useState<TeamContact[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    setRows(null);
    setErr(null);
    client
      .get(ENDPOINTS.ROSTER.TEAM_CONTACTS, { params: department ? { department } : {} })
      .then((r) => live && setRows(r.data))
      .catch((e) => live && setErr(errMsg(e, 'Failed to load team contacts')));
    return () => { live = false; };
  }, [department]);

  return (
    <Card className="p-4 space-y-2" data-testid="team-contacts-panel">
      <h3 className="text-sm font-semibold text-gray-800">
        Team contacts{department ? ` · ${department}` : ''}
      </h3>
      {err && <p className="text-xs text-rose-600">{err}</p>}
      {!rows && !err && <p className="text-xs text-gray-500">Loading…</p>}
      {rows && rows.length === 0 && <p className="text-xs text-gray-500">No employees in scope.</p>}
      {rows && rows.length > 0 && (
        <div className="overflow-x-auto max-h-60 overflow-y-auto">
          <table className="text-xs w-full">
            <thead>
              <tr className="text-left text-gray-500">
                <th className="py-1 pr-3 font-medium">Employee</th>
                <th className="py-1 pr-3 font-medium">Phone</th>
                <th className="py-1 pr-3 font-medium">Blood</th>
                <th className="py-1 font-medium">Emergency contacts</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.user_id} className="border-t border-gray-200 align-top">
                  <td className="py-1.5 pr-3 font-medium text-gray-900">{r.name}</td>
                  <td className="py-1.5 pr-3">
                    {r.phone ? <Tel phone={r.phone} label={`Call ${r.name}`} /> : '—'}
                  </td>
                  <td className="py-1.5 pr-3">{r.blood_group || '—'}</td>
                  <td className="py-1.5">
                    {r.contacts.length === 0 && <span className="text-gray-400">None on file</span>}
                    {r.contacts.map((c) => (
                      <div key={c.id}>
                        {c.name} ({c.relation}){c.is_primary ? ' · primary' : ''} ·{' '}
                        <Tel phone={c.phone} label={`Call ${c.name}`} />
                      </div>
                    ))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
};
