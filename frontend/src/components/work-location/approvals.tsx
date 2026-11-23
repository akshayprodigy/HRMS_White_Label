import React, { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { CheckCircle2, XCircle } from 'lucide-react';
import { Card, Button, Badge, errMsg } from '../ui-elements';
import { client } from '../../api/client';
import { ENDPOINTS } from '../../api/endpoints';
import { KIND_LABEL, fmtRange, type WorkLocationRequest } from './shared';

/** Direct-path pending requests the viewer can decide (server `can_decide`).
 *  Chain-routed requests are decided in the chained-approval queue. */
export const WorkLocationApprovals: React.FC<{ refreshKey?: number }> = ({ refreshKey = 0 }) => {
  const [rows, setRows] = useState<WorkLocationRequest[]>([]);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [notes, setNotes] = useState<Record<number, string>>({});

  const load = useCallback(async () => {
    try {
      const res = await client.get<WorkLocationRequest[]>(ENDPOINTS.WORK_LOCATION.LIST, { params: { status: 'pending' } });
      setRows((res.data || []).filter((r) => r.can_decide && r.status === 'pending'));
    } catch (e: any) {
      setRows([]);
      // 403 = no reports and no HR/leave permission: nothing to decide
      if (e?.response?.status !== 403) toast.error(errMsg(e, 'Failed to load work-location requests'));
    }
  }, []);
  useEffect(() => { void load(); }, [load, refreshKey]);

  const decide = async (r: WorkLocationRequest, approve: boolean) => {
    setBusyId(r.id);
    try {
      await client.post(ENDPOINTS.WORK_LOCATION.DECIDE(r.id), {
        approve, note: (notes[r.id] || '').trim() || null,
      });
      toast.success(approve ? 'Request approved' : 'Request rejected');
      await load();
    } catch (e) {
      // e.g. 409 "You have approved leave on these dates"
      toast.error(errMsg(e, 'Could not record the decision'));
      await load();
    } finally {
      setBusyId(null);
    }
  };

  if (rows.length === 0) return null;

  return (
    <Card className="p-5 border-slate-200 bg-white" data-testid="work-location-approvals">
      <p className="text-[10px] font-black uppercase tracking-widest text-[#0F172A] mb-3">
        Work location <Badge variant="warning" className="ml-2">{rows.length}</Badge>
      </p>
      <div className="space-y-3">
        {rows.map((r) => (
          <div key={r.id} className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 pt-3">
            <div>
              <p className="text-sm font-black text-[#0F172A]">{r.user_name || `User #${r.user_id}`}</p>
              <p className="text-xs font-bold text-slate-600">
                {KIND_LABEL[r.kind] || r.kind}{r.place ? ` · ${r.place}` : ''} · {fmtRange(r)}
              </p>
              <p className="text-xs text-slate-500 italic">"{r.purpose}"</p>
            </div>
            <div className="flex items-center gap-2">
              <input value={notes[r.id] || ''} maxLength={500}
                onChange={(e) => setNotes((n) => ({ ...n, [r.id]: e.target.value }))}
                placeholder="Note (optional)"
                className="h-9 px-3 rounded-lg border border-slate-200 text-xs" />
              <Button size="sm" variant="outline" disabled={busyId === r.id} onClick={() => decide(r, false)}>
                <XCircle size={14} className="mr-1" />Reject
              </Button>
              <Button size="sm" disabled={busyId === r.id} onClick={() => decide(r, true)}>
                <CheckCircle2 size={14} className="mr-1" />Approve
              </Button>
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
};
