import React, { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Calendar, MapPin } from 'lucide-react';
import { Card, Button, Badge, errMsg } from '../ui-elements';
import { Dialog, DialogContent, DialogTitle, DialogFooter } from '../ui/dialog';
import { client } from '../../api/client';
import { ENDPOINTS } from '../../api/endpoints';
import { useOrgTime } from '../../lib/org-time';

export interface MyHoliday {
  id: number;
  name: string;
  date: string;
  location: string;
  is_optional: boolean;
  pick: { id: number; status: string } | null;
}

interface MyHolidaysResponse {
  quota: number;
  used: number;
  remaining: number;
  year: number;
  holidays: MyHoliday[];
}

// Pending is NOT a granted holiday: it only becomes one once a person approves.
const PICK_BADGE: Record<string, { label: string; variant: 'success' | 'warning' | 'neutral' }> = {
  pending: { label: 'Pending approval', variant: 'warning' },
  approved: { label: 'Approved', variant: 'success' },
};

const fmtDay = (iso: string) => {
  const [y, m, d] = iso.split('-').map(Number);
  // Pure calendar date: format in UTC so the browser zone cannot shift it.
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString(undefined, {
    weekday: 'short', day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC',
  });
};

export const MyHolidaysPanel: React.FC = () => {
  const { today } = useOrgTime();
  const [yearSel, setYearSel] = useState<number | null>(null);
  const year = yearSel ?? Number(today.slice(0, 4));
  const [data, setData] = useState<MyHolidaysResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [pickFor, setPickFor] = useState<MyHoliday | null>(null);
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [cancelFor, setCancelFor] = useState<MyHoliday | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await client.get<MyHolidaysResponse>(ENDPOINTS.HOLIDAYS.MY, { params: { year } });
      setData(res.data);
    } catch (e) {
      toast.error(errMsg(e, 'Failed to load holidays'));
    } finally {
      setLoading(false);
    }
  }, [year]);

  useEffect(() => { void load(); }, [load]);

  const submitPick = async () => {
    if (!pickFor) return;
    setBusy(true);
    try {
      await client.post(ENDPOINTS.HOLIDAYS.PICKS, {
        holiday_id: pickFor.id,
        reason: reason.trim() || null,
      });
      toast.success('Request sent for approval. The holiday is not yours until it is approved.');
      setPickFor(null);
      setReason('');
      await load();
    } catch (e) {
      toast.error(errMsg(e, 'Could not request this holiday'));
    } finally {
      setBusy(false);
    }
  };

  const doCancel = async () => {
    if (!cancelFor?.pick) return;
    setBusy(true);
    try {
      await client.post(ENDPOINTS.HOLIDAYS.PICK_CANCEL(cancelFor.pick.id));
      toast.success('Pick cancelled');
      setCancelFor(null);
      await load();
    } catch (e) {
      toast.error(errMsg(e, 'Could not cancel'));
    } finally {
      setBusy(false);
    }
  };

  const years = [year - 1, year, year + 1].filter((v, i, a) => a.indexOf(v) === i);
  const mandatory = data?.holidays.filter((h) => !h.is_optional) ?? [];
  const optional = data?.holidays.filter((h) => h.is_optional) ?? [];
  const noQuota = !!data && data.remaining <= 0;

  const row = (h: MyHoliday) => {
    const badge = h.pick ? PICK_BADGE[h.pick.status] : null;
    return (
      <Card key={h.id} className="p-4 border-slate-200 bg-white">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${h.is_optional ? 'bg-amber-50 text-amber-400' : 'bg-blue-50 text-blue-400'}`}>
              <Calendar size={18} />
            </div>
            <div>
              <p className="text-sm font-black text-[#0F172A] uppercase tracking-tight">{h.name}</p>
              <p className="text-xs font-bold text-slate-500">{fmtDay(h.date)}</p>
              <p className="flex items-center gap-1 text-[10px] font-bold text-slate-400 uppercase tracking-widest">
                <MapPin size={10} /> {h.location}
              </p>
            </div>
          </div>
          {h.is_optional && (
            <div className="flex items-center gap-2">
              {badge && <Badge variant={badge.variant}>{badge.label}</Badge>}
              {h.pick ? (
                <Button size="sm" variant="outline" onClick={() => setCancelFor(h)}>Cancel</Button>
              ) : (
                <Button size="sm" disabled={noQuota} onClick={() => { setReason(''); setPickFor(h); }}>
                  Pick
                </Button>
              )}
            </div>
          )}
        </div>
      </Card>
    );
  };

  return (
    <div className="space-y-6" data-testid="my-holidays-panel">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <select
            aria-label="Year"
            value={year}
            onChange={(e) => setYearSel(Number(e.target.value))}
            className="h-9 px-3 rounded-lg border border-slate-200 text-xs font-bold text-slate-700 bg-white"
          >
            {years.map((y) => <option key={y} value={y}>{y}</option>)}
          </select>
          {data && (
            <Badge variant={noQuota ? 'warning' : 'info'} className="text-[10px] font-black uppercase tracking-widest">
              {data.used} of {data.quota} optional used
            </Badge>
          )}
        </div>
        {data && (
          <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">
            Pending picks count toward your quota until a decision
          </p>
        )}
      </div>

      {loading && !data ? (
        <div className="py-10 text-center text-xs font-black uppercase tracking-widest text-slate-400 animate-pulse">Loading holidays...</div>
      ) : (
        <>
          <section className="space-y-3">
            <p className="text-[10px] font-black text-blue-600 uppercase tracking-widest">Company holidays ({mandatory.length})</p>
            {mandatory.length === 0
              ? <p className="text-xs font-bold text-slate-400">No company holidays this year.</p>
              : mandatory.map(row)}
          </section>
          <section className="space-y-3">
            <p className="text-[10px] font-black text-amber-600 uppercase tracking-widest">Optional holidays ({optional.length})</p>
            {optional.length === 0
              ? <p className="text-xs font-bold text-slate-400">No optional holidays this year.</p>
              : optional.map(row)}
          </section>
        </>
      )}

      <Dialog open={!!pickFor} onOpenChange={(o: boolean) => { if (!o) setPickFor(null); }}>
        <DialogContent>
          <DialogTitle>Pick {pickFor?.name}</DialogTitle>
          <p className="mt-2 text-sm text-slate-600">
            {pickFor ? fmtDay(pickFor.date) : ''}. This sends a request to your approver; the day is not
            taken until it is approved.
          </p>
          <div className="mt-3">
            <label className="text-xs text-slate-500">Reason (optional)</label>
            <textarea
              rows={3}
              value={reason}
              maxLength={1000}
              onChange={(e) => setReason(e.target.value)}
              className="w-full px-3 py-2 rounded-lg border border-slate-200 text-sm"
            />
          </div>
          <DialogFooter>
            <Button variant="secondary" onClick={() => setPickFor(null)}>Close</Button>
            <Button onClick={submitPick} disabled={busy}>{busy ? 'Sending...' : 'Request'}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!cancelFor} onOpenChange={(o: boolean) => { if (!o) setCancelFor(null); }}>
        <DialogContent>
          <DialogTitle>Cancel pick</DialogTitle>
          <p className="mt-2 text-sm text-slate-600">
            Cancel your {cancelFor?.pick?.status === 'approved' ? 'approved ' : 'pending '}pick of {cancelFor?.name}?
          </p>
          <DialogFooter>
            <Button variant="secondary" onClick={() => setCancelFor(null)}>Keep</Button>
            <Button variant="danger" onClick={doCancel} disabled={busy}>{busy ? 'Cancelling...' : 'Cancel pick'}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};
