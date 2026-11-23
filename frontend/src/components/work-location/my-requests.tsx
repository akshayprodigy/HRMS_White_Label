import React, { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Send } from 'lucide-react';
import { Card, Button, Badge, errMsg } from '../ui-elements';
import { client } from '../../api/client';
import { ENDPOINTS } from '../../api/endpoints';
import { useOrgTime } from '../../lib/org-time';
import { WorkLocationRequestDialog } from './request-dialog';
import { KIND_LABEL, type WorkLocationRequest } from './shared';

// Pending is NOT granted: it only counts once a person approves it.
const STATUS_BADGE: Record<string, { label: string; variant: 'success' | 'warning' | 'error' | 'neutral' }> = {
  pending: { label: 'Pending approval', variant: 'warning' },
  approved: { label: 'Approved', variant: 'success' },
  rejected: { label: 'Rejected', variant: 'error' },
  cancelled: { label: 'Cancelled', variant: 'neutral' },
};

export const fmtDay = (iso: string) => {
  const [y, m, d] = iso.split('-').map(Number);
  // Pure calendar date: format in UTC so the browser zone cannot shift it.
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString(undefined, {
    day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC',
  });
};

const PORTION: Record<string, string> = { first_half: ' (first half)', second_half: ' (second half)' };

export const fmtRange = (r: WorkLocationRequest) =>
  (r.start_date === r.end_date ? fmtDay(r.start_date) : `${fmtDay(r.start_date)} – ${fmtDay(r.end_date)}`) +
  (PORTION[r.day_portion] || '');

export const MyWorkLocationRequests: React.FC = () => {
  const { today } = useOrgTime();
  const [items, setItems] = useState<WorkLocationRequest[]>([]);
  const [open, setOpen] = useState(false);
  const [busyId, setBusyId] = useState<number | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await client.get<WorkLocationRequest[]>(ENDPOINTS.WORK_LOCATION.MY);
      setItems(res.data || []);
    } catch (e) {
      toast.error(errMsg(e, 'Failed to load work-location requests'));
    }
  }, []);
  useEffect(() => { void load(); }, [load]);

  // Backend: only pending/approved can be cancelled, and not once started.
  const canCancel = (r: WorkLocationRequest) =>
    (r.status === 'pending' || r.status === 'approved') && r.start_date >= today;

  const cancel = async (r: WorkLocationRequest) => {
    setBusyId(r.id);
    try {
      await client.post(ENDPOINTS.WORK_LOCATION.CANCEL(r.id));
      toast.success('Request cancelled');
      await load();
    } catch (e) {
      toast.error(errMsg(e, 'Could not cancel the request'));
      await load();
    } finally {
      setBusyId(null);
    }
  };

  return (
    <Card className="p-5 border-slate-200 bg-white" data-testid="my-work-location">
      <div className="flex items-center justify-between mb-3">
        <p className="text-[10px] font-black uppercase tracking-widest text-[#0F172A]">My Work Location Requests</p>
        <Button onClick={() => setOpen(true)} className="h-8 text-[10px] font-black uppercase">
          <Send size={12} className="mr-1" /> Work location request
        </Button>
      </div>
      {items.length === 0 ? (
        <p className="text-xs text-slate-400 font-bold">No work-location requests yet</p>
      ) : (
        <div className="space-y-3">
          {items.map((r) => {
            const b = STATUS_BADGE[r.status] || STATUS_BADGE.cancelled;
            return (
              <div key={r.id} className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 pt-3">
                <div>
                  <p className="text-sm font-black text-[#0F172A]">
                    {KIND_LABEL[r.kind] || r.kind}{r.place ? ` · ${r.place}` : ''}
                  </p>
                  <p className="text-xs font-bold text-slate-600">{fmtRange(r)}</p>
                  <p className="text-xs text-slate-500">{r.purpose}</p>
                  {r.status === 'rejected' && r.decision_note && (
                    <p className="text-xs text-red-600 font-bold">Note: {r.decision_note}</p>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <Badge variant={b.variant}>{b.label}</Badge>
                  {(r.status === 'pending' || r.status === 'approved') && (
                    <Button size="sm" variant="outline" disabled={busyId === r.id || !canCancel(r)}
                      title={canCancel(r) ? undefined : 'A request that has already started cannot be cancelled. Ask HR.'}
                      onClick={() => cancel(r)}>
                      Cancel
                    </Button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
      <WorkLocationRequestDialog open={open} onClose={() => setOpen(false)} onCreated={load} />
    </Card>
  );
};
