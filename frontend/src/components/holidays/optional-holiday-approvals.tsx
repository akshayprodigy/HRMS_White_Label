import React, { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { CheckCircle2, XCircle } from 'lucide-react';
import { Card, Button, Badge, errMsg } from '../ui-elements';
import { client } from '../../api/client';
import { ENDPOINTS } from '../../api/endpoints';

interface Pick {
  id: number;
  status: string;
  can_decide: boolean;
  routed_via: 'direct' | 'chain';
  user_id: number;
  user_name: string | null;
  reason: string | null;
  holiday: { id: number; name: string; date: string; location: string } | null;
}

/** Direct-path pending picks the viewer can decide. Chain-routed picks are
 *  decided in the chained-approval queue instead, so they are excluded. */
export const OptionalHolidayApprovals: React.FC<{ refreshKey?: number }> = ({ refreshKey = 0 }) => {
  const [picks, setPicks] = useState<Pick[]>([]);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [notes, setNotes] = useState<Record<number, string>>({});

  const load = useCallback(async () => {
    try {
      const res = await client.get<Pick[]>(ENDPOINTS.HOLIDAYS.PICKS, { params: { status: 'pending' } });
      // The server computes can_decide with the same rule as the decide endpoint
      setPicks((res.data || []).filter((p) => p.can_decide && p.status === 'pending'));
    } catch (e: any) {
      setPicks([]);
      // 403 = no reports and no HR/leave permission: nothing to decide
      if (e?.response?.status !== 403) toast.error(errMsg(e, 'Failed to load optional holiday requests'));
    }
  }, []);

  useEffect(() => { void load(); }, [load, refreshKey]);

  const decide = async (p: Pick, approve: boolean) => {
    setBusyId(p.id);
    try {
      await client.post(ENDPOINTS.HOLIDAYS.PICK_DECIDE(p.id), {
        approve, note: (notes[p.id] || '').trim() || null,
      });
      toast.success(approve ? 'Optional holiday approved' : 'Optional holiday rejected');
      await load();
    } catch (e) {
      toast.error(errMsg(e, 'Could not record the decision'));
      await load();
    } finally {
      setBusyId(null);
    }
  };

  if (picks.length === 0) return null;

  return (
    <Card className="p-5 border-slate-200 bg-white" data-testid="optional-holiday-approvals">
      <p className="text-[10px] font-black uppercase tracking-widest text-[#0F172A] mb-3">
        Optional holidays <Badge variant="warning" className="ml-2">{picks.length}</Badge>
      </p>
      <div className="space-y-3">
        {picks.map((p) => (
          <div key={p.id} className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 pt-3">
            <div>
              <p className="text-sm font-black text-[#0F172A]">{p.user_name || `User #${p.user_id}`}</p>
              <p className="text-xs font-bold text-slate-600">
                {p.holiday ? `${p.holiday.name} · ${p.holiday.date}` : 'Holiday removed'}
              </p>
              {p.reason && <p className="text-xs text-slate-500 italic">"{p.reason}"</p>}
            </div>
            <div className="flex items-center gap-2">
              <input
                value={notes[p.id] || ''}
                maxLength={500}
                onChange={(e) => setNotes({ ...notes, [p.id]: e.target.value })}
                placeholder="Note (optional)"
                className="h-9 px-3 rounded-lg border border-slate-200 text-xs"
              />
              <Button size="sm" variant="outline" disabled={busyId === p.id} onClick={() => decide(p, false)}>
                <XCircle size={14} className="mr-1" />Reject
              </Button>
              <Button size="sm" disabled={busyId === p.id} onClick={() => decide(p, true)}>
                <CheckCircle2 size={14} className="mr-1" />Approve
              </Button>
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
};
