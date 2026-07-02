import React, { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { CheckCircle, RefreshCw, XCircle } from 'lucide-react';
import { Card, Button, Badge } from './ui-elements';
import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';

// Section R: HR oversight of shift-change requests. Approve/Reject act
// on the chain instance — the backend enforces whose turn it is, so an
// HR click during the manager step returns a clear error.

const errMsg = (e: any, fallback: string) =>
  e?.response?.data?.detail ||
  e?.response?.data?.error?.message ||
  fallback;

const STATUS_TONE: Record<string, 'success' | 'error' | 'warning' | 'neutral'> = {
  approved: 'success',
  rejected: 'error',
  pending: 'warning',
  cancelled: 'neutral',
};

const FILTERS = ['pending', 'approved', 'rejected', 'cancelled', 'all'] as const;

export const ShiftChangeRequestsTab: React.FC = () => {
  const [rows, setRows] = useState<any[]>([]);
  const [filter, setFilter] = useState<(typeof FILTERS)[number]>('pending');
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<number | null>(null);

  const refresh = async (f = filter) => {
    setLoading(true);
    try {
      const res = await client.get(ENDPOINTS.SHIFTS.CHANGE_REQUESTS, {
        params: f === 'all' ? {} : { status: f },
      });
      setRows(res.data || []);
    } catch (e: any) {
      toast.error(errMsg(e, 'Failed to load change requests'));
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { refresh(filter); /* eslint-disable-line */ }, [filter]);

  const act = async (r: any, action: 'approve' | 'reject') => {
    if (!r.approval_instance_id) {
      toast.error('No approval instance linked to this request');
      return;
    }
    setBusyId(r.id);
    try {
      await client.post(
        ENDPOINTS.APPROVAL_CHAINS.INSTANCE_ACT(r.approval_instance_id),
        { action, comment: null },
      );
      toast.success(action === 'approve' ? 'Approved' : 'Rejected');
      await refresh();
    } catch (e: any) {
      toast.error(errMsg(e, 'Action failed — it may not be your step yet'));
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="p-6 space-y-4 max-w-[1100px]">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex gap-1.5">
          {FILTERS.map((f) => (
            <button
              key={f}
              type="button"
              onClick={() => setFilter(f)}
              className={
                'px-3 py-1.5 rounded-lg border text-[9px] font-black uppercase tracking-widest transition-colors ' +
                (filter === f
                  ? 'border-blue-600 bg-blue-50 text-blue-700'
                  : 'border-slate-200 text-slate-500 hover:text-blue-600')
              }
            >
              {f}
            </button>
          ))}
        </div>
        <Button variant="outline" onClick={() => refresh()} className="h-9">
          <RefreshCw size={13} className="mr-1.5" /> Refresh
        </Button>
      </div>

      {loading ? (
        <p className="text-[10px] font-black uppercase tracking-widest text-slate-400 py-10 text-center">
          Loading…
        </p>
      ) : rows.length === 0 ? (
        <Card className="p-10 text-center border-slate-200 bg-white">
          <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">
            No {filter === 'all' ? '' : filter + ' '}shift change requests
          </p>
        </Card>
      ) : (
        <div className="space-y-2">
          {rows.map((r) => (
            <Card key={r.id} className="p-4 border-slate-200 bg-white">
              <div className="flex items-start justify-between gap-3 flex-wrap">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <p className="text-sm font-black text-[#0F172A]">
                      {r.user_name || `User #${r.user_id}`}
                    </p>
                    <Badge variant={STATUS_TONE[r.status] || 'neutral'} className="text-[8px] uppercase">
                      {r.status}
                    </Badge>
                  </div>
                  <p className="text-[10px] font-bold text-slate-600 mt-1">
                    {r.current_shift_name || 'No shift'} → {r.requested_shift_name}
                    <span className="text-slate-400 tabular-nums"> · from {r.effective_from}</span>
                  </p>
                  <p className="text-[10px] text-slate-500 italic mt-1">"{r.reason}"</p>
                </div>
                {r.status === 'pending' && (
                  <div className="flex gap-2 shrink-0">
                    <Button
                      onClick={() => act(r, 'approve')}
                      isLoading={busyId === r.id}
                      className="h-8 bg-emerald-600 hover:bg-emerald-700 text-white text-[9px] font-black uppercase tracking-widest"
                    >
                      <CheckCircle size={11} className="mr-1" /> Approve
                    </Button>
                    <Button
                      variant="outline"
                      onClick={() => act(r, 'reject')}
                      disabled={busyId === r.id}
                      className="h-8 border-rose-200 text-rose-600 hover:bg-rose-50 text-[9px] font-black uppercase tracking-widest"
                    >
                      <XCircle size={11} className="mr-1" /> Reject
                    </Button>
                  </div>
                )}
              </div>
            </Card>
          ))}
        </div>
      )}
      <p className="text-[9px] font-bold text-slate-400 uppercase tracking-widest">
        Requests route Manager → HR. Approvers can also act from the
        Approvals queue in Expenses &amp; Travel.
      </p>
    </div>
  );
};
