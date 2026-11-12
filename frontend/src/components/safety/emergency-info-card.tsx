import { useCallback, useEffect, useState } from 'react';
import { HeartPulse, Phone } from 'lucide-react';
import { toast } from 'sonner';
import { client } from '../../api/client';
import { ENDPOINTS } from '../../api/endpoints';
import { Button, Card, cn } from '../ui-elements';
import { InlineConfirm } from '../my-schedule/inline-confirm';
import { errMsg } from '../schedule-delegations-utils';

export const GENDERS = ['female', 'male', 'other', 'undisclosed'];
export const BLOOD_GROUPS = ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-'];
const MAX_CONTACTS = 3;

interface Contact { id: number; name: string; relation: string; phone: string; is_primary: boolean }
interface Profile { gender: string | null; blood_group: string | null; contacts: Contact[] }

const field = 'w-full h-10 bg-slate-50 border border-slate-200 rounded-xl px-3 text-sm font-bold outline-none';
const lbl = 'text-[10px] font-black text-slate-600 uppercase tracking-widest';

/** Gender, blood group and up to 3 emergency contacts. `userId` undefined =
 *  the signed-in employee (/me/*); a number = HR editing that employee. */
export const EmergencyInfoCard = ({
  self = false, userId, canEdit = true, onLoaded,
}: {
  /** true = the signed-in employee's own data (/me/*). Never inferred. */
  self?: boolean;
  /** HR mode: the employee's user id. Ignored when `self`. */
  userId?: number;
  canEdit?: boolean;
  onLoaded?: (p: { can_write?: boolean }) => void;
}) => {
  const api = self
    ? {
        profile: ENDPOINTS.SAFETY.ME_PROFILE,
        contacts: ENDPOINTS.SAFETY.ME_CONTACTS,
        contact: (id: number) => ENDPOINTS.SAFETY.ME_CONTACT(id),
      }
    : {
        profile: ENDPOINTS.SAFETY.HR_PROFILE(userId as number),
        contacts: ENDPOINTS.SAFETY.HR_CONTACTS(userId as number),
        contact: (id: number) => ENDPOINTS.SAFETY.HR_CONTACT(userId as number, id),
      };
  if (!self && userId == null) {
    return <Card className="p-6 text-sm text-slate-500">This employee has no linked user account, so emergency info is unavailable.</Card>;
  }
  const [data, setData] = useState<Profile | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [gender, setGender] = useState('');
  const [blood, setBlood] = useState('');
  const [busy, setBusy] = useState(false);
  const [nc, setNc] = useState({ name: '', relation: '', phone: '', is_primary: false });

  const load = useCallback(async () => {
    setErr(null);
    try {
      const r = await client.get(api.profile);
      setData(r.data);
      setGender(r.data.gender || '');
      setBlood(r.data.blood_group || '');
      onLoaded?.(r.data);
    } catch (e) {
      setErr(errMsg(e, 'Failed to load emergency info'));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api.profile]); // eslint-disable-line
  useEffect(() => { load(); }, [load]);

  const run = async (fn: () => Promise<unknown>, ok: string) => {
    setBusy(true);
    try {
      await fn();
      toast.success(ok);
      await load();
    } catch (e) {
      toast.error(errMsg(e, 'Action failed'));
    } finally {
      setBusy(false);
    }
  };

  const saveProfile = () =>
    run(() => client.put(api.profile, { gender: gender || null, blood_group: blood || null }), 'Saved');
  const addContact = () =>
    run(async () => {
      await client.post(api.contacts, nc);
      setNc({ name: '', relation: '', phone: '', is_primary: false });
    }, 'Contact added');

  if (err) return <Card className="p-6 text-sm text-rose-600">{err}</Card>;
  if (!data) return <Card className="p-6 text-xs text-slate-500">Loading…</Card>;
  const full = data.contacts.length >= MAX_CONTACTS;

  return (
    <Card className="p-6 border-slate-200 bg-white space-y-6" data-testid="emergency-info-card">
      <div className="flex items-center gap-2">
        <HeartPulse size={16} className="text-rose-500" aria-hidden="true" />
        <h3 className="text-[10px] font-black text-slate-500 uppercase tracking-[0.2em]">Emergency info</h3>
      </div>
      <p className="text-xs text-slate-500">
        Visible only to you, HR and the managers who schedule you. Used for safety and night-shift compliance.
      </p>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="space-y-1.5">
          <label htmlFor="ei-gender" className={lbl}>Gender</label>
          <select id="ei-gender" className={field} value={gender} disabled={!canEdit || busy}
            onChange={(e) => setGender(e.target.value)}>
            <option value="">Not set</option>
            {GENDERS.map((g) => <option key={g} value={g}>{g[0].toUpperCase() + g.slice(1)}</option>)}
          </select>
        </div>
        <div className="space-y-1.5">
          <label htmlFor="ei-blood" className={lbl}>Blood group</label>
          <select id="ei-blood" className={field} value={blood} disabled={!canEdit || busy}
            onChange={(e) => setBlood(e.target.value)}>
            <option value="">Not set</option>
            {BLOOD_GROUPS.map((b) => <option key={b} value={b}>{b}</option>)}
          </select>
        </div>
      </div>
      {canEdit && (
        <Button size="sm" onClick={saveProfile} disabled={busy}>Save</Button>
      )}

      <div className="space-y-3">
        <p className={lbl}>Emergency contacts ({data.contacts.length}/{MAX_CONTACTS})</p>
        {data.contacts.length === 0 && <p className="text-xs text-slate-500">No contacts yet.</p>}
        {data.contacts.map((c) => (
          <div key={c.id} className="flex flex-wrap items-center gap-3 border border-slate-100 rounded-xl p-3">
            <div className="flex-1 min-w-0">
              <p className="text-sm font-black text-slate-900 truncate">
                {c.name} <span className="text-xs font-bold text-slate-500">({c.relation})</span>
                {c.is_primary && (
                  <span className="ml-2 text-[9px] font-black uppercase tracking-widest text-emerald-600">Primary</span>
                )}
              </p>
              <p className="text-xs text-slate-600 tabular-nums flex items-center gap-2">
                <span>{c.phone}</span>
                <a href={`tel:${c.phone.replace(/[^\d+]/g, '')}`} aria-label={`Call ${c.name}`}
                  className="inline-flex items-center gap-1 text-indigo-600 hover:underline">
                  <Phone size={12} aria-hidden="true" /> Call
                </a>
              </p>
            </div>
            {canEdit && (
              <div className="flex items-center gap-3">
                {!c.is_primary && (
                  <button type="button" disabled={busy}
                    onClick={() => run(() => client.put(api.contact(c.id), { is_primary: true }), 'Primary updated')}
                    className="text-[9px] font-black uppercase tracking-widest text-indigo-600">
                    Make primary
                  </button>
                )}
                <InlineConfirm label="Remove" ariaLabel={`Remove contact ${c.name}`} busy={busy}
                  onConfirm={() => run(() => client.delete(api.contact(c.id)), 'Contact removed')} />
              </div>
            )}
          </div>
        ))}
      </div>

      {canEdit && (
        <div className={cn('space-y-3', full && 'opacity-60')}>
          <p className={lbl}>Add contact</p>
          {full ? (
            <p className="text-xs text-slate-500">
              Maximum of {MAX_CONTACTS} contacts reached. Remove one to add another.
            </p>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <input aria-label="Contact name" placeholder="Name" className={field} value={nc.name}
                onChange={(e) => setNc({ ...nc, name: e.target.value })} maxLength={120} />
              <input aria-label="Relation" placeholder="Relation" className={field} value={nc.relation}
                onChange={(e) => setNc({ ...nc, relation: e.target.value })} maxLength={50} />
              <input aria-label="Contact phone" placeholder="Phone" className={field} value={nc.phone}
                onChange={(e) => setNc({ ...nc, phone: e.target.value })} maxLength={20} inputMode="tel" />
              <label className="flex items-center gap-2 text-xs text-slate-600 md:col-span-2">
                <input type="checkbox" checked={nc.is_primary}
                  onChange={(e) => setNc({ ...nc, is_primary: e.target.checked })} />
                Primary contact
              </label>
              <div>
                <Button size="sm" onClick={addContact}
                  disabled={busy || !nc.name.trim() || !nc.relation.trim() || !nc.phone.trim()}>
                  Add contact
                </Button>
              </div>
            </div>
          )}
        </div>
      )}
    </Card>
  );
};
