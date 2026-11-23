import React, { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { MapPin } from 'lucide-react';
import { Button, errMsg } from '../ui-elements';
import { Dialog, DialogContent, DialogTitle, DialogFooter } from '../ui/dialog';
import { client } from '../../api/client';
import { ENDPOINTS } from '../../api/endpoints';
import { useOrgTime } from '../../lib/org-time';
import { KIND_LABEL, needsPlace, type WorkLocationKind } from './shared';

const inputCls =
  'w-full h-10 px-3 rounded-lg border border-slate-200 text-sm text-[#0F172A] ' +
  'focus:outline-none focus:ring-2 focus:ring-blue-600/30 focus:border-blue-500 bg-white';
const labelCls = 'text-[9px] font-black uppercase tracking-widest text-slate-400';

export const WorkLocationRequestDialog: React.FC<{
  open: boolean;
  onClose: () => void;
  onCreated?: () => void;
}> = ({ open, onClose, onCreated }) => {
  const { today } = useOrgTime();
  const [kind, setKind] = useState<WorkLocationKind>('wfh');
  const [start, setStart] = useState('');
  const [end, setEnd] = useState('');
  const [portion, setPortion] = useState('full');
  const [place, setPlace] = useState('');
  const [purpose, setPurpose] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setKind('wfh'); setStart(today); setEnd(today); setPortion('full');
      setPlace(''); setPurpose(''); setError(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const single = !!start && start === end;
  // A half day only makes sense for one date.
  useEffect(() => { if (!single) setPortion('full'); }, [single]);

  const submit = async () => {
    if (!start || !end) { setError('Choose the dates'); return; }
    if (end < start) { setError('End date cannot be before the start date'); return; }
    if (needsPlace(kind) && !place.trim()) { setError('Place is required'); return; }
    if (!purpose.trim()) { setError('Please give a purpose'); return; }
    setBusy(true);
    setError(null);
    try {
      await client.post(ENDPOINTS.WORK_LOCATION.LIST, {
        kind, start_date: start, end_date: end,
        day_portion: single ? portion : 'full',
        place: needsPlace(kind) ? place.trim() : (place.trim() || null),
        purpose: purpose.trim(),
      });
      toast.success('Request sent for approval. It is not granted until someone approves it.');
      onCreated?.();
      onClose();
    } catch (e) {
      setError(errMsg(e, 'Failed to submit request'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o: boolean) => !o && onClose()}>
      <DialogContent className="max-w-md">
        <DialogTitle className="flex items-center gap-2 text-base font-black uppercase tracking-tight text-[#0F172A]">
          <MapPin size={15} className="text-blue-600" /> Work location request
        </DialogTitle>
        <p className="text-[10px] font-bold text-slate-500 -mt-1">
          Approved by your manager or HR. Until then it stays pending and nothing changes.
        </p>
        <div className="space-y-3 pt-1">
          <div className="space-y-1">
            <label className={labelCls}>Kind</label>
            <select className={inputCls} value={kind} onChange={(e) => setKind(e.target.value as WorkLocationKind)}>
              {(Object.keys(KIND_LABEL) as WorkLocationKind[]).map((k) => (
                <option key={k} value={k}>{KIND_LABEL[k]}</option>
              ))}
            </select>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <label className={labelCls}>From</label>
              <input type="date" className={inputCls} value={start}
                onChange={(e) => { setStart(e.target.value); if (end < e.target.value) setEnd(e.target.value); }} />
            </div>
            <div className="space-y-1">
              <label className={labelCls}>To</label>
              <input type="date" className={inputCls} value={end} min={start || undefined}
                onChange={(e) => setEnd(e.target.value)} />
            </div>
          </div>
          <div className="space-y-1">
            <label className={labelCls}>Day portion</label>
            <select className={inputCls} value={portion} disabled={!single} onChange={(e) => setPortion(e.target.value)}>
              <option value="full">Full day</option>
              <option value="first_half">First half</option>
              <option value="second_half">Second half</option>
            </select>
            {!single && <p className="text-[10px] text-slate-400">Half days are for a single date.</p>}
          </div>
          <div className="space-y-1">
            <label className={labelCls}>Place{needsPlace(kind) ? ' (required)' : ' (optional)'}</label>
            <input className={inputCls} value={place} maxLength={200} onChange={(e) => setPlace(e.target.value)}
              placeholder={needsPlace(kind) ? 'Client or site name' : ''} />
          </div>
          <div className="space-y-1">
            <label className={labelCls}>Purpose</label>
            <textarea className={inputCls + ' h-20 py-2'} value={purpose} maxLength={1000}
              onChange={(e) => setPurpose(e.target.value)} />
          </div>
          {error && <p className="text-xs font-bold text-red-600" role="alert">{error}</p>}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={busy}>Close</Button>
          <Button onClick={submit} disabled={busy}>{busy ? 'Sending…' : 'Send for approval'}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
