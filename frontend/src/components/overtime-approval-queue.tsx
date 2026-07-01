import React, { useEffect, useMemo, useState } from 'react';
import {
  Check, X, RefreshCw, Calendar, Filter, Play, Users as UsersIcon,
} from 'lucide-react';
import { Card, Button, Badge, cn } from './ui-elements';
import { toast } from 'sonner';
import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';
import { Dialog, DialogContent, DialogTitle, DialogFooter } from './ui/dialog';
import { Input } from './ui/input';

interface OTEntry {
  id: number;
  user_id: number;
  user_full_name?: string;
  work_date: string;
  attendance_id: number | null;
  shift_template_name?: string;
  ot_minutes: number;
  ot_amount: number;
  hourly_rate_used: number;
  multiplier_used: number;
  day_type: 'weekday' | 'weekly_off' | 'holiday';
  status: 'pending' | 'approved' | 'rejected' | 'auto_approved';
  approver_id: number | null;
  approved_at: string | null;
  rejection_reason: string | null;
  payroll_run_id: number | null;
  worked_hours: number | null;
}

const fmtMin = (m: number) => {
  const h = Math.floor(m / 60); const r = m % 60;
  return r ? `${h}h ${r}m` : `${h}h`;
};

const errMsg = (err: any, fallback: string): string => {
  const detail = err?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail))
    return detail.map((d: any) => d?.msg || JSON.stringify(d)).join('; ');
  return err?.message || fallback;
};

const today = () => new Date().toISOString().slice(0, 10);
const monthStart = () => {
  const d = new Date(); d.setDate(1);
  return d.toISOString().slice(0, 10);
};

export const OvertimeApprovalQueue: React.FC = () => {
  const [items, setItems] = useState<OTEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [start, setStart] = useState(monthStart());
  const [end, setEnd] = useState(today());
  const [status, setStatus] = useState<string>('pending');
  const [reviewing, setReviewing] = useState<OTEntry | null>(null);
  const [action, setAction] = useState<'approve' | 'reject'>('approve');
  const [comment, setComment] = useState('');
  const [busy, setBusy] = useState(false);
  const [recomputing, setRecomputing] = useState(false);

  const fetchItems = async () => {
    setLoading(true);
    try {
      const res = await client.get(ENDPOINTS.OVERTIME.ENTRIES, {
        params: {
          start, end,
          ...(status !== 'all' ? { status } : {}),
        },
      });
      setItems(res.data || []);
    } catch (e: any) {
      toast.error(errMsg(e, 'Failed to load OT entries'));
    } finally { setLoading(false); }
  };

  useEffect(() => { fetchItems(); /* eslint-disable-line */ }, [start, end, status]);

  const totals = useMemo(() => {
    const m = items.reduce((s, e) => s + e.ot_minutes, 0);
    const a = items.reduce((s, e) => s + e.ot_amount, 0);
    return { m, a };
  }, [items]);

  const submitAction = async () => {
    if (!reviewing) return;
    setBusy(true);
    try {
      await client.post(ENDPOINTS.OVERTIME.ENTRY_ACTION(reviewing.id), {
        action, comment: comment || undefined,
      });
      toast.success(action === 'approve' ? 'Approved' : 'Rejected');
      setReviewing(null); setComment(''); fetchItems();
    } catch (e: any) {
      toast.error(errMsg(e, 'Action failed'));
    } finally { setBusy(false); }
  };

  const recompute = async () => {
    setRecomputing(true);
    try {
      const r = await client.post(ENDPOINTS.OVERTIME.RECOMPUTE, {
        start_date: start, end_date: end,
      });
      const { ot_entries_created, ot_entries_updated, ot_entries_skipped_finalized,
        night_entries_created, night_entries_updated, night_entries_skipped_finalized,
      } = r.data;
      toast.success(
        `OT: +${ot_entries_created} new, ${ot_entries_updated} updated, ${ot_entries_skipped_finalized} skipped (finalized). ` +
        `Night: +${night_entries_created} new, ${night_entries_updated} updated, ${night_entries_skipped_finalized} skipped.`
      );
      fetchItems();
    } catch (e: any) {
      toast.error(errMsg(e, 'Recompute failed'));
    } finally { setRecomputing(false); }
  };

  const dayChip = (t: string) => {
    const cls = t === 'holiday' ? 'bg-red-100 text-red-700'
      : t === 'weekly_off' ? 'bg-amber-100 text-amber-700'
        : 'bg-slate-100 text-slate-700';
    return <span className={cn('px-2 py-0.5 rounded text-[10px] font-bold', cls)}>{t}</span>;
  };

  const statusChip = (s: string) => {
    const v = s === 'approved' || s === 'auto_approved' ? 'success'
      : s === 'rejected' ? 'error' : 'info';
    return <Badge variant={v as any}>{s}</Badge>;
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <UsersIcon className="w-6 h-6 text-blue-600" /> Overtime Approvals
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Review computed OT before it feeds payroll. Already-finalized entries cannot be edited.
          </p>
        </div>
        <Button onClick={recompute} isLoading={recomputing} variant="outline">
          <Play className="w-4 h-4 mr-2" /> Recompute window
        </Button>
      </div>

      <Card className="p-4">
        <div className="flex flex-wrap items-end gap-3 mb-4">
          <div>
            <label className="text-xs font-semibold text-slate-600 flex items-center gap-1">
              <Calendar className="w-3 h-3" /> Start
            </label>
            <Input type="date" value={start} onChange={e => setStart(e.target.value)} />
          </div>
          <div>
            <label className="text-xs font-semibold text-slate-600">End</label>
            <Input type="date" value={end} onChange={e => setEnd(e.target.value)} />
          </div>
          <div>
            <label className="text-xs font-semibold text-slate-600 flex items-center gap-1">
              <Filter className="w-3 h-3" /> Status
            </label>
            <select value={status} onChange={e => setStatus(e.target.value)}
              className="border border-slate-200 rounded-md h-9 px-2 text-sm">
              <option value="pending">Pending</option>
              <option value="approved">Approved</option>
              <option value="auto_approved">Auto-approved</option>
              <option value="rejected">Rejected</option>
              <option value="all">All</option>
            </select>
          </div>
          <div className="ml-auto flex gap-3 text-xs">
            <span className="px-3 py-1 rounded bg-blue-50 text-blue-700 font-bold">
              {items.length} entries · {fmtMin(totals.m)} · ₹{totals.a.toFixed(2)}
            </span>
            <Button variant="outline" onClick={fetchItems}><RefreshCw className="w-4 h-4" /></Button>
          </div>
        </div>

        {loading ? (
          <div className="py-8 text-center text-slate-500">Loading…</div>
        ) : items.length === 0 ? (
          <div className="py-12 text-center text-slate-500">No OT entries in this window.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead className="text-left text-xs uppercase text-slate-500 border-b">
                <tr>
                  <th className="p-3">Employee</th>
                  <th className="p-3">Work date</th>
                  <th className="p-3">Day</th>
                  <th className="p-3">Shift</th>
                  <th className="p-3">Worked</th>
                  <th className="p-3">OT</th>
                  <th className="p-3">Amount</th>
                  <th className="p-3">Status</th>
                  <th className="p-3">Payroll</th>
                  <th className="p-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {items.map(e => (
                  <tr key={e.id} className="border-b hover:bg-slate-50">
                    <td className="p-3 font-medium">{e.user_full_name || `User #${e.user_id}`}</td>
                    <td className="p-3">{e.work_date}</td>
                    <td className="p-3">{dayChip(e.day_type)}</td>
                    <td className="p-3 text-xs">{e.shift_template_name || '—'}</td>
                    <td className="p-3 text-xs">{e.worked_hours != null ? `${e.worked_hours}h` : '—'}</td>
                    <td className="p-3 font-mono">{fmtMin(e.ot_minutes)} · {e.multiplier_used}×</td>
                    <td className="p-3 font-mono">₹{e.ot_amount.toFixed(2)}</td>
                    <td className="p-3">{statusChip(e.status)}</td>
                    <td className="p-3 text-xs">
                      {e.payroll_run_id ? <Badge variant="info">#{e.payroll_run_id}</Badge> : '—'}
                    </td>
                    <td className="p-3 text-right space-x-1">
                      {(e.status === 'pending' && !e.payroll_run_id) && (
                        <>
                          <Button size="sm" variant="outline"
                            onClick={() => { setReviewing(e); setAction('approve'); setComment(''); }}>
                            <Check className="w-3 h-3 text-green-600" />
                          </Button>
                          <Button size="sm" variant="outline"
                            onClick={() => { setReviewing(e); setAction('reject'); setComment(''); }}>
                            <X className="w-3 h-3 text-red-600" />
                          </Button>
                        </>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Dialog open={!!reviewing} onOpenChange={(o: boolean) => { if (!o) setReviewing(null); }}>
        <DialogContent className="max-w-md">
          <DialogTitle>{action === 'approve' ? 'Approve' : 'Reject'} Overtime</DialogTitle>
          {reviewing && (
            <div className="mt-4 space-y-3 text-sm">
              <div>
                <span className="text-slate-500">Employee:</span> {reviewing.user_full_name}
              </div>
              <div>
                <span className="text-slate-500">Work date:</span> {reviewing.work_date}{' '}
                {dayChip(reviewing.day_type)}
              </div>
              <div>
                <span className="text-slate-500">OT:</span>{' '}
                {fmtMin(reviewing.ot_minutes)} × {reviewing.multiplier_used}× ·{' '}
                ₹{reviewing.ot_amount.toFixed(2)}
              </div>
              <div>
                <span className="text-slate-500">Hourly basis:</span>{' '}
                ₹{reviewing.hourly_rate_used.toFixed(2)}/hr
              </div>
              <div>
                <label className="text-xs font-semibold text-slate-600">
                  Comment {action === 'reject' ? '(recommended)' : '(optional)'}
                </label>
                <textarea value={comment} onChange={e => setComment(e.target.value)}
                  className="w-full border border-slate-200 rounded-md p-2 text-sm"
                  rows={3} />
              </div>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setReviewing(null)}>Cancel</Button>
            <Button isLoading={busy} onClick={submitAction}>
              {action === 'approve' ? 'Approve' : 'Reject'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};
