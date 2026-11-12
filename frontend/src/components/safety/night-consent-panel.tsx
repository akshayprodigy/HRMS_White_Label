import { useCallback, useEffect, useState } from 'react';
import { Moon } from 'lucide-react';
import { toast } from 'sonner';
import { client } from '../../api/client';
import { ENDPOINTS } from '../../api/endpoints';
import { Badge, Button, Card } from '../ui-elements';
import { InlineConfirm } from '../my-schedule/inline-confirm';
import { errMsg, todayIso } from '../schedule-delegations-utils';

interface Consent {
  id: number;
  consent_given: boolean;
  valid_from: string;
  valid_to: string | null;
  document_url: string | null;
  note: string | null;
  active: boolean;
}

const field = 'h-10 bg-slate-50 border border-slate-200 rounded-xl px-3 text-sm font-bold outline-none';
const lbl = 'text-[10px] font-black text-slate-600 uppercase tracking-widest';

/** HR-managed night-shift consent records for one employee. */
export const NightConsentPanel = ({ userId, canWrite }: { userId: number; canWrite: boolean }) => {
  const [rows, setRows] = useState<Consent[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [f, setF] = useState({ valid_from: todayIso(), valid_to: '', document_url: '', note: '' });

  const load = useCallback(async () => {
    setErr(null);
    try {
      setRows((await client.get(ENDPOINTS.SAFETY.HR_CONSENTS(userId))).data);
    } catch (e) {
      setErr(errMsg(e, 'Failed to load consents'));
    }
  }, [userId]);
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

  const create = () =>
    run(() => client.post(ENDPOINTS.SAFETY.HR_CONSENTS(userId), {
      consent_given: true,
      valid_from: f.valid_from,
      valid_to: f.valid_to || null,
      document_url: f.document_url || null,
      note: f.note || null,
    }), 'Consent recorded');

  return (
    <Card className="p-6 border-slate-200 bg-white space-y-5" data-testid="night-consent-panel">
      <div className="flex items-center gap-2">
        <Moon size={16} className="text-indigo-600" aria-hidden="true" />
        <h3 className="text-[10px] font-black text-slate-500 uppercase tracking-[0.2em]">Night-shift consent</h3>
      </div>
      <p className="text-xs text-slate-500">
        Women employees need active recorded consent before being scheduled on a night shift
        (overnight or overlapping 22:00-06:00).
      </p>
      {err && <p className="text-sm text-rose-600">{err}</p>}
      {rows && rows.length === 0 && <p className="text-xs text-slate-500">No consent recorded.</p>}
      {(rows || []).map((c) => (
        <div key={c.id} className="flex flex-wrap items-center gap-3 border border-slate-100 rounded-xl p-3">
          <div className="flex-1 min-w-0 text-xs text-slate-700">
            <p className="font-black text-slate-900 tabular-nums">
              {c.valid_from} → {c.valid_to || 'open-ended'}
            </p>
            {c.note && <p>{c.note}</p>}
            {c.document_url && (
              <a href={c.document_url} target="_blank" rel="noreferrer" className="text-indigo-600 hover:underline">
                Document
              </a>
            )}
          </div>
          <Badge variant={c.active ? 'success' : 'neutral'}>
            {!c.consent_given ? 'Not given' : c.active ? 'Active' : 'Not active'}
          </Badge>
          {canWrite && c.consent_given && (!c.valid_to || c.valid_to >= todayIso()) && (
            <InlineConfirm label="End consent" ariaLabel="End this consent" busy={busy}
              onConfirm={() => run(() => client.post(ENDPOINTS.SAFETY.HR_CONSENT_END(userId, c.id), {}), 'Consent ended')} />
          )}
        </div>
      ))}
      {canWrite && (
        <div className="space-y-3">
          <p className={lbl}>Record consent</p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <label className="space-y-1 text-xs text-slate-600">Valid from
              <input type="date" className={`${field} w-full`} value={f.valid_from}
                onChange={(e) => setF({ ...f, valid_from: e.target.value })} />
            </label>
            <label className="space-y-1 text-xs text-slate-600">Valid to (optional)
              <input type="date" className={`${field} w-full`} value={f.valid_to}
                onChange={(e) => setF({ ...f, valid_to: e.target.value })} />
            </label>
            <input aria-label="Document URL" placeholder="Document URL (optional)" className={field}
              value={f.document_url} maxLength={500}
              onChange={(e) => setF({ ...f, document_url: e.target.value })} />
            <input aria-label="Note" placeholder="Note (optional)" className={field}
              value={f.note} maxLength={255} onChange={(e) => setF({ ...f, note: e.target.value })} />
          </div>
          <Button size="sm" onClick={create} disabled={busy || !f.valid_from}>Record consent</Button>
        </div>
      )}
    </Card>
  );
};
