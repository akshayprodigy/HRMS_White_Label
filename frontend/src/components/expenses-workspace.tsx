/**
 * Expenses + Approval Chain workspace.
 *
 * Six tabs:
 *   1. My Expenses  — submit + track claims
 *   2. My Travel    — submit + track travel requests
 *   3. Approvals    — manager/finance queue (any chained-approval instance
 *                     awaiting me)
 *   4. Finance      — approved claims ready for reimbursement / payroll push
 *   5. Categories   — HR admin: expense categories with policy caps
 *   6. Chain Builder — HR admin: visual approval-chain configurator
 *
 * The chain builder + finance queue tabs are gated at the API level too;
 * unauthorized users simply see empty rows.
 */
import React, { useEffect, useMemo, useState } from 'react';
import {
  Receipt, Plane, ClipboardCheck, Banknote, Layers, GitBranch,
  Plus, RefreshCw, Send, CheckCircle2, XCircle, AlertTriangle,
  Eye,
} from 'lucide-react';
import { toast } from 'sonner@2.0.3';
import { Card, Button, Badge, cn } from './ui-elements';
import { Dialog, DialogContent, DialogTitle, DialogFooter } from './ui/dialog';
import { Input } from './ui/input';
import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';

// ---------------------------------------------------------------------------
// Utilities
// ---------------------------------------------------------------------------

const errMsg = (e: any, fb: string) => {
  const d = e?.response?.data?.detail;
  if (typeof d === 'string') return d;
  if (Array.isArray(d)) return d.map((x: any) => x?.msg || JSON.stringify(x)).join('; ');
  if (d && typeof d === 'object') return d.message || JSON.stringify(d);
  return e?.message || fb;
};

const today = () => new Date().toISOString().slice(0, 10);

const fmtInr = (paise?: number | null) => {
  if (paise == null) return '—';
  const rupees = paise / 100;
  return '₹' + rupees.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
};

const statusTone = (s: string) => {
  const key = (s || '').toLowerCase();
  if (['approved', 'reimbursed', 'pushed_to_payroll', 'completed'].includes(key))
    return 'bg-green-100 text-green-700 border-green-300';
  if (['rejected', 'cancelled'].includes(key))
    return 'bg-red-100 text-red-700 border-red-300';
  if (['submitted', 'pending'].includes(key))
    return 'bg-blue-100 text-blue-700 border-blue-300';
  return 'bg-slate-100 text-slate-600 border-slate-300';
};

const TABS = [
  { id: 'my-expenses',   label: 'My Expenses', icon: Receipt },
  { id: 'my-travel',     label: 'My Travel',   icon: Plane },
  { id: 'approvals',     label: 'Approvals',   icon: ClipboardCheck },
  { id: 'finance',       label: 'Finance',     icon: Banknote },
  { id: 'categories',    label: 'Categories',  icon: Layers },
  { id: 'chain-builder', label: 'Chain Builder', icon: GitBranch },
] as const;
type TabId = typeof TABS[number]['id'];

// ===========================================================================
// TAB 1 — My Expenses
// ===========================================================================

const MyExpensesTab: React.FC = () => {
  const [claims, setClaims] = useState<any[]>([]);
  const [cats, setCats] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [createOpen, setCreateOpen] = useState(false);
  const [form, setForm] = useState({
    title: '', description: '', claim_date: today(), cost_center: '',
  });
  const [lines, setLines] = useState<any[]>([
    { category_id: 0, amount_paise: 0, description: '', receipt_url: '', line_date: today() },
  ]);
  const [busy, setBusy] = useState(false);

  const refresh = async () => {
    setLoading(true);
    try {
      const [c, k] = await Promise.all([
        client.get(ENDPOINTS.EXPENSES.CLAIMS),
        client.get(ENDPOINTS.EXPENSES.CATEGORIES),
      ]);
      setClaims(c.data || []);
      setCats(k.data || []);
    } catch (e: any) {
      toast.error(errMsg(e, 'Failed to load claims'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { refresh(); }, []);

  const totalPaise = lines.reduce(
    (sum, l) => sum + (Number(l.amount_paise) || 0), 0,
  );

  const addLine = () => setLines(prev => [...prev, {
    category_id: cats[0]?.id || 0, amount_paise: 0, description: '',
    receipt_url: '', line_date: today(),
  }]);

  const create = async () => {
    if (!form.title.trim()) {
      toast.error('Title is required');
      return;
    }
    if (!lines.length || lines.some(l => !l.category_id)) {
      toast.error('Every line needs a category');
      return;
    }
    setBusy(true);
    try {
      const r = await client.post(ENDPOINTS.EXPENSES.CLAIMS, {
        ...form,
        line_items: lines.map(l => ({
          category_id: Number(l.category_id),
          amount_paise: Number(l.amount_paise),
          description: l.description || null,
          receipt_url: l.receipt_url || null,
          line_date: l.line_date || null,
        })),
      });
      toast.success('Draft saved');
      setCreateOpen(false);
      setForm({ title: '', description: '', claim_date: today(), cost_center: '' });
      setLines([{ category_id: cats[0]?.id || 0, amount_paise: 0, description: '', receipt_url: '', line_date: today() }]);
      await refresh();
    } catch (e: any) {
      toast.error(errMsg(e, 'Failed to save draft'));
    } finally {
      setBusy(false);
    }
  };

  const submit = async (id: number) => {
    if (!confirm('Submit this claim for approval?')) return;
    try {
      await client.post(ENDPOINTS.EXPENSES.CLAIM_SUBMIT(id));
      toast.success('Submitted');
      await refresh();
    } catch (e: any) {
      toast.error(errMsg(e, 'Failed to submit'));
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-lg font-semibold">My Expense Claims</h2>
          <p className="text-sm text-slate-500">
            Multi-line receipts, routed through the configured approval chain.
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="secondary" onClick={refresh}>
            <RefreshCw size={14} className="mr-1" />Refresh
          </Button>
          <Button onClick={() => setCreateOpen(true)}>
            <Plus size={14} className="mr-1" />New Claim
          </Button>
        </div>
      </div>

      {loading ? (
        <div className="text-center text-slate-400 py-8">Loading…</div>
      ) : claims.length === 0 ? (
        <Card className="p-8 text-center text-slate-500">
          No claims yet. Click "New Claim" to file receipts.
        </Card>
      ) : (
        <div className="space-y-2">
          {claims.map(c => (
            <Card key={c.id} className="p-4">
              <div className="flex justify-between items-start">
                <div>
                  <div className="font-medium">{c.title}</div>
                  <div className="text-xs text-slate-500 mt-1">
                    {c.claim_date} · {c.line_items?.length || 0} line{c.line_items?.length === 1 ? '' : 's'}
                    {c.cost_center ? ` · ${c.cost_center}` : ''}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <div className="text-lg font-semibold">{fmtInr(c.total_amount_paise)}</div>
                  <Badge className={cn(statusTone(c.status), 'border')}>
                    {c.status}
                  </Badge>
                </div>
              </div>
              {(c.line_items || []).some((l: any) => l.is_out_of_policy) && (
                <div className="mt-2 p-2 rounded bg-amber-50 border border-amber-200 text-xs text-amber-800 flex items-start gap-2">
                  <AlertTriangle size={14} className="mt-0.5" />
                  <div>
                    Some lines flagged out-of-policy. Approvers will see the reason.
                  </div>
                </div>
              )}
              {c.status === 'draft' && (
                <div className="mt-3 flex justify-end gap-2">
                  <Button size="sm" onClick={() => submit(c.id)}>
                    <Send size={14} className="mr-1" />Submit
                  </Button>
                </div>
              )}
            </Card>
          ))}
        </div>
      )}

      <Dialog open={createOpen} onOpenChange={(o: boolean) => setCreateOpen(o)}>
        <DialogContent className="max-w-2xl">
          <DialogTitle>New Expense Claim</DialogTitle>
          <div className="grid grid-cols-2 gap-3 mt-3">
            <div className="col-span-2">
              <label className="text-xs text-slate-500">Title</label>
              <Input value={form.title} onChange={e => setForm({ ...form, title: e.target.value })} />
            </div>
            <div>
              <label className="text-xs text-slate-500">Claim date</label>
              <Input type="date" value={form.claim_date} onChange={e => setForm({ ...form, claim_date: e.target.value })} />
            </div>
            <div>
              <label className="text-xs text-slate-500">Cost center (optional)</label>
              <Input value={form.cost_center} onChange={e => setForm({ ...form, cost_center: e.target.value })} />
            </div>
            <div className="col-span-2">
              <label className="text-xs text-slate-500">Description (optional)</label>
              <Input value={form.description} onChange={e => setForm({ ...form, description: e.target.value })} />
            </div>
          </div>

          <div className="mt-4">
            <div className="flex justify-between items-center">
              <div className="font-medium text-sm">Line items</div>
              <Button size="sm" variant="secondary" onClick={addLine}>
                <Plus size={12} className="mr-1" />Add line
              </Button>
            </div>
            <div className="mt-2 space-y-2">
              {lines.map((l, idx) => (
                <div key={idx} className="grid grid-cols-12 gap-2 p-2 border border-slate-200 rounded">
                  <div className="col-span-3">
                    <label className="text-[10px] text-slate-500">Category</label>
                    <select className="w-full border border-slate-300 rounded px-2 py-1.5 text-sm"
                      value={l.category_id}
                      onChange={e => {
                        const v = Number(e.target.value);
                        setLines(prev => prev.map((x, i) => i === idx ? { ...x, category_id: v } : x));
                      }}>
                      <option value={0}>—</option>
                      {cats.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
                    </select>
                  </div>
                  <div className="col-span-2">
                    <label className="text-[10px] text-slate-500">Amount (paise)</label>
                    <Input type="number" value={l.amount_paise}
                      onChange={e => setLines(prev => prev.map((x, i) => i === idx ? { ...x, amount_paise: Number(e.target.value) } : x))} />
                  </div>
                  <div className="col-span-2">
                    <label className="text-[10px] text-slate-500">Date</label>
                    <Input type="date" value={l.line_date}
                      onChange={e => setLines(prev => prev.map((x, i) => i === idx ? { ...x, line_date: e.target.value } : x))} />
                  </div>
                  <div className="col-span-3">
                    <label className="text-[10px] text-slate-500">Description</label>
                    <Input value={l.description}
                      onChange={e => setLines(prev => prev.map((x, i) => i === idx ? { ...x, description: e.target.value } : x))} />
                  </div>
                  <div className="col-span-2">
                    <label className="text-[10px] text-slate-500">Receipt URL</label>
                    <Input value={l.receipt_url}
                      onChange={e => setLines(prev => prev.map((x, i) => i === idx ? { ...x, receipt_url: e.target.value } : x))} />
                  </div>
                </div>
              ))}
              <div className="text-right text-sm text-slate-600">
                Total: <span className="font-semibold">{fmtInr(totalPaise)}</span>
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="secondary" onClick={() => setCreateOpen(false)}>Cancel</Button>
            <Button onClick={create} disabled={busy}>{busy ? 'Saving…' : 'Save Draft'}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

// ===========================================================================
// TAB 2 — My Travel
// ===========================================================================

const MyTravelTab: React.FC = () => {
  const [trips, setTrips] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [openNew, setOpenNew] = useState(false);
  const [form, setForm] = useState({
    purpose: '', from_city: '', to_city: '',
    start_date: today(), end_date: today(),
    estimated_cost_paise: 0, advance_requested_paise: 0, notes: '',
  });
  const [busy, setBusy] = useState(false);

  const refresh = async () => {
    setLoading(true);
    try {
      const r = await client.get(ENDPOINTS.EXPENSES.TRAVEL);
      setTrips(r.data || []);
    } catch (e: any) {
      toast.error(errMsg(e, 'Failed to load travel'));
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { refresh(); }, []);

  const create = async () => {
    if (!form.purpose.trim()) { toast.error('Purpose is required'); return; }
    setBusy(true);
    try {
      await client.post(ENDPOINTS.EXPENSES.TRAVEL, form);
      toast.success('Travel request drafted');
      setOpenNew(false);
      await refresh();
    } catch (e: any) {
      toast.error(errMsg(e, 'Failed to create travel'));
    } finally { setBusy(false); }
  };
  const submit = async (id: number) => {
    if (!confirm('Submit this travel request for approval?')) return;
    try {
      await client.post(ENDPOINTS.EXPENSES.TRAVEL_SUBMIT(id));
      toast.success('Submitted');
      await refresh();
    } catch (e: any) {
      toast.error(errMsg(e, 'Failed to submit'));
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-lg font-semibold">My Travel Requests</h2>
          <p className="text-sm text-slate-500">Request pre-approval + optional advance.</p>
        </div>
        <div className="flex gap-2">
          <Button variant="secondary" onClick={refresh}><RefreshCw size={14} className="mr-1" />Refresh</Button>
          <Button onClick={() => setOpenNew(true)}><Plus size={14} className="mr-1" />New Request</Button>
        </div>
      </div>

      {loading ? (
        <div className="text-center text-slate-400 py-8">Loading…</div>
      ) : trips.length === 0 ? (
        <Card className="p-8 text-center text-slate-500">No travel requests yet.</Card>
      ) : (
        <div className="space-y-2">
          {trips.map(t => (
            <Card key={t.id} className="p-4">
              <div className="flex justify-between items-start">
                <div>
                  <div className="font-medium">{t.purpose}</div>
                  <div className="text-xs text-slate-500 mt-1">
                    {t.from_city} → {t.to_city} · {t.start_date} to {t.end_date}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <div className="text-sm text-slate-600">
                    Est. {fmtInr(t.estimated_cost_paise)}
                    {t.advance_requested_paise > 0 && (
                      <span className="ml-2 text-purple-700">+ Adv. {fmtInr(t.advance_requested_paise)}</span>
                    )}
                  </div>
                  <Badge className={cn(statusTone(t.status), 'border')}>{t.status}</Badge>
                </div>
              </div>
              {t.status === 'draft' && (
                <div className="mt-3 flex justify-end">
                  <Button size="sm" onClick={() => submit(t.id)}>
                    <Send size={14} className="mr-1" />Submit
                  </Button>
                </div>
              )}
            </Card>
          ))}
        </div>
      )}

      <Dialog open={openNew} onOpenChange={(o: boolean) => setOpenNew(o)}>
        <DialogContent className="max-w-xl">
          <DialogTitle>New Travel Request</DialogTitle>
          <div className="grid grid-cols-2 gap-3 mt-3">
            <div className="col-span-2">
              <label className="text-xs text-slate-500">Purpose</label>
              <Input value={form.purpose} onChange={e => setForm({ ...form, purpose: e.target.value })} />
            </div>
            <div>
              <label className="text-xs text-slate-500">From</label>
              <Input value={form.from_city} onChange={e => setForm({ ...form, from_city: e.target.value })} />
            </div>
            <div>
              <label className="text-xs text-slate-500">To</label>
              <Input value={form.to_city} onChange={e => setForm({ ...form, to_city: e.target.value })} />
            </div>
            <div>
              <label className="text-xs text-slate-500">Start date</label>
              <Input type="date" value={form.start_date} onChange={e => setForm({ ...form, start_date: e.target.value })} />
            </div>
            <div>
              <label className="text-xs text-slate-500">End date</label>
              <Input type="date" value={form.end_date} onChange={e => setForm({ ...form, end_date: e.target.value })} />
            </div>
            <div>
              <label className="text-xs text-slate-500">Est. cost (paise)</label>
              <Input type="number" value={form.estimated_cost_paise}
                onChange={e => setForm({ ...form, estimated_cost_paise: Number(e.target.value) })} />
            </div>
            <div>
              <label className="text-xs text-slate-500">Advance requested (paise)</label>
              <Input type="number" value={form.advance_requested_paise}
                onChange={e => setForm({ ...form, advance_requested_paise: Number(e.target.value) })} />
            </div>
            <div className="col-span-2">
              <label className="text-xs text-slate-500">Notes</label>
              <Input value={form.notes} onChange={e => setForm({ ...form, notes: e.target.value })} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="secondary" onClick={() => setOpenNew(false)}>Cancel</Button>
            <Button onClick={create} disabled={busy}>{busy ? 'Saving…' : 'Save Draft'}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

// ===========================================================================
// TAB 3 — Approver Queue (manager/finance shared inbox)
// ===========================================================================

const ApproverQueueTab: React.FC = () => {
  const [queue, setQueue] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [actOn, setActOn] = useState<any | null>(null);
  const [comment, setComment] = useState('');
  const [busy, setBusy] = useState(false);

  const refresh = async () => {
    setLoading(true);
    try {
      const r = await client.get(ENDPOINTS.APPROVAL_CHAINS.MY_QUEUE);
      setQueue(r.data || []);
    } catch (e: any) {
      toast.error(errMsg(e, 'Failed to load queue'));
    } finally { setLoading(false); }
  };
  useEffect(() => { refresh(); }, []);

  const act = async (action: 'approve' | 'reject') => {
    if (!actOn) return;
    setBusy(true);
    try {
      await client.post(ENDPOINTS.APPROVAL_CHAINS.INSTANCE_ACT(actOn.instance.id), {
        action, comment: comment || null,
      });
      toast.success(action === 'approve' ? 'Approved' : 'Rejected');
      setActOn(null); setComment('');
      await refresh();
    } catch (e: any) {
      toast.error(errMsg(e, 'Action failed'));
    } finally { setBusy(false); }
  };

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-lg font-semibold">Approvals Queue</h2>
          <p className="text-sm text-slate-500">
            Every chained-approval instance awaiting your action.
          </p>
        </div>
        <Button variant="secondary" onClick={refresh}>
          <RefreshCw size={14} className="mr-1" />Refresh
        </Button>
      </div>

      {loading ? (
        <div className="text-center text-slate-400 py-8">Loading…</div>
      ) : queue.length === 0 ? (
        <Card className="p-8 text-center text-slate-500">
          Nothing awaiting your action. Nice.
        </Card>
      ) : (
        <div className="space-y-2">
          {queue.map((row: any) => (
            <Card key={row.step_instance.id} className="p-4">
              <div className="flex justify-between items-start">
                <div>
                  <div className="flex items-center gap-2">
                    <Badge className="border-slate-300">{row.instance.entity_type}</Badge>
                    <div className="font-medium">
                      {row.entity?.title || row.entity?.purpose || `#${row.entity?.id}`}
                    </div>
                  </div>
                  <div className="text-xs text-slate-500 mt-1">
                    {row.entity?.kind === 'expense' ? (
                      <>
                        {row.entity.line_count} lines · {row.entity.claim_date}
                        {row.entity.out_of_policy_count > 0 && (
                          <span className="ml-2 text-amber-700">
                            ⚠ {row.entity.out_of_policy_count} out-of-policy
                          </span>
                        )}
                      </>
                    ) : row.entity?.kind === 'travel' ? (
                      <>
                        {row.entity.from_city} → {row.entity.to_city} · {row.entity.start_date} to {row.entity.end_date}
                      </>
                    ) : null}
                  </div>
                  <div className="text-xs text-slate-500 mt-1">
                    Step {row.step_instance.step_order} · {row.step_instance.mode}/{row.step_instance.parallel_rule}
                    {row.step_instance.label ? ` · ${row.step_instance.label}` : ''}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <div className="text-lg font-semibold">{fmtInr(row.instance.amount_paise)}</div>
                </div>
              </div>
              <div className="mt-3 flex justify-end gap-2">
                <Button size="sm" variant="secondary" onClick={() => setActOn({ ...row, _action: 'reject' })}>
                  <XCircle size={14} className="mr-1" />Reject
                </Button>
                <Button size="sm" onClick={() => setActOn({ ...row, _action: 'approve' })}>
                  <CheckCircle2 size={14} className="mr-1" />Approve
                </Button>
              </div>
            </Card>
          ))}
        </div>
      )}

      <Dialog open={!!actOn} onOpenChange={(o: boolean) => { if (!o) { setActOn(null); setComment(''); } }}>
        <DialogContent>
          <DialogTitle>
            {actOn?._action === 'approve' ? 'Approve' : 'Reject'}{' '}
            {actOn?.instance?.entity_type}
          </DialogTitle>
          <div className="mt-2 text-sm text-slate-600">
            {actOn?.entity?.title || actOn?.entity?.purpose}
            {' — '}
            <span className="font-semibold">{fmtInr(actOn?.instance?.amount_paise)}</span>
          </div>
          <div className="mt-3">
            <label className="text-xs text-slate-500">
              Comment (optional{actOn?._action === 'reject' ? ' — but useful' : ''})
            </label>
            <Input value={comment} onChange={e => setComment(e.target.value)} />
          </div>
          <DialogFooter>
            <Button variant="secondary" onClick={() => { setActOn(null); setComment(''); }}>Cancel</Button>
            <Button onClick={() => act(actOn._action)} disabled={busy}>
              {busy ? 'Working…' : actOn?._action === 'approve' ? 'Approve' : 'Reject'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

// ===========================================================================
// TAB 4 — Finance Queue
// ===========================================================================

const FinanceQueueTab: React.FC = () => {
  const [rows, setRows] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [reimburseOn, setReimburseOn] = useState<any | null>(null);
  const [rForm, setRForm] = useState({ mode: 'direct', reference: '', payroll_run_id: 0 });
  const [busy, setBusy] = useState(false);

  const refresh = async () => {
    setLoading(true);
    try {
      const r = await client.get(ENDPOINTS.EXPENSES.FINANCE_QUEUE);
      setRows(r.data || []);
    } catch (e: any) {
      toast.error(errMsg(e, 'Failed to load finance queue'));
    } finally { setLoading(false); }
  };
  useEffect(() => { refresh(); }, []);

  const reimburse = async () => {
    if (!reimburseOn) return;
    setBusy(true);
    try {
      await client.post(
        ENDPOINTS.EXPENSES.CLAIM_REIMBURSE(reimburseOn.id),
        {
          mode: rForm.mode,
          reference: rForm.reference || null,
          payroll_run_id: rForm.mode === 'payroll' ? Number(rForm.payroll_run_id) : null,
        },
      );
      toast.success('Reimbursement recorded');
      setReimburseOn(null); setRForm({ mode: 'direct', reference: '', payroll_run_id: 0 });
      await refresh();
    } catch (e: any) {
      toast.error(errMsg(e, 'Reimbursement failed'));
    } finally { setBusy(false); }
  };

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-lg font-semibold">Finance Reimbursement Queue</h2>
          <p className="text-sm text-slate-500">
            Approved claims — mark reimbursed directly, or push to the next payroll draft.
          </p>
        </div>
        <Button variant="secondary" onClick={refresh}>
          <RefreshCw size={14} className="mr-1" />Refresh
        </Button>
      </div>

      {loading ? (
        <div className="text-center text-slate-400 py-8">Loading…</div>
      ) : rows.length === 0 ? (
        <Card className="p-8 text-center text-slate-500">Queue is empty.</Card>
      ) : (
        <div className="space-y-2">
          {rows.map(r => (
            <Card key={r.id} className="p-4">
              <div className="flex justify-between items-start">
                <div>
                  <div className="font-medium">{r.title}</div>
                  <div className="text-xs text-slate-500 mt-1">
                    Claim #{r.id} · Emp {r.employee_id} · {r.claim_date}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <div className="text-lg font-semibold">{fmtInr(r.total_amount_paise)}</div>
                  <Button size="sm" onClick={() => setReimburseOn(r)}>
                    <Banknote size={14} className="mr-1" />Reimburse
                  </Button>
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}

      <Dialog open={!!reimburseOn} onOpenChange={(o: boolean) => { if (!o) setReimburseOn(null); }}>
        <DialogContent>
          <DialogTitle>Reimburse {reimburseOn?.title}</DialogTitle>
          <div className="mt-2 text-sm text-slate-600">
            Amount: <span className="font-semibold">{fmtInr(reimburseOn?.total_amount_paise)}</span>
          </div>
          <div className="mt-3 grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-slate-500">Mode</label>
              <select className="w-full border border-slate-300 rounded px-2 py-1.5 text-sm"
                value={rForm.mode} onChange={e => setRForm({ ...rForm, mode: e.target.value })}>
                <option value="direct">Direct (mark reimbursed)</option>
                <option value="payroll">Push to payroll draft</option>
              </select>
            </div>
            {rForm.mode === 'direct' ? (
              <div>
                <label className="text-xs text-slate-500">Reference (NEFT / txn id)</label>
                <Input value={rForm.reference} onChange={e => setRForm({ ...rForm, reference: e.target.value })} />
              </div>
            ) : (
              <div>
                <label className="text-xs text-slate-500">Payroll run id</label>
                <Input type="number" value={rForm.payroll_run_id}
                  onChange={e => setRForm({ ...rForm, payroll_run_id: Number(e.target.value) })} />
              </div>
            )}
          </div>
          <div className="mt-3 p-2 rounded bg-slate-50 border border-slate-200 text-[11px] text-slate-600">
            Double-pay guard is enforced server-side — a claim already reimbursed
            (direct or payroll) cannot be reimbursed again.
          </div>
          <DialogFooter>
            <Button variant="secondary" onClick={() => setReimburseOn(null)}>Cancel</Button>
            <Button onClick={reimburse} disabled={busy}>
              {busy ? 'Working…' : 'Confirm'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

// ===========================================================================
// TAB 5 — Category master
// ===========================================================================

const CategoriesTab: React.FC = () => {
  const [rows, setRows] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [openNew, setOpenNew] = useState(false);
  const [form, setForm] = useState({
    name: '', code: '', is_active: true,
    per_diem_cap_paise: 0, receipt_required_above_paise: 0,
    policy_mode: 'warn', notes: '',
  });
  const [busy, setBusy] = useState(false);

  const refresh = async () => {
    setLoading(true);
    try {
      const r = await client.get(ENDPOINTS.EXPENSES.CATEGORIES, { params: { include_inactive: true } });
      setRows(r.data || []);
    } catch (e: any) {
      toast.error(errMsg(e, 'Failed to load categories'));
    } finally { setLoading(false); }
  };
  useEffect(() => { refresh(); }, []);

  const create = async () => {
    if (!form.name.trim()) { toast.error('Name required'); return; }
    setBusy(true);
    try {
      await client.post(ENDPOINTS.EXPENSES.CATEGORIES, {
        ...form,
        per_diem_cap_paise: form.per_diem_cap_paise || null,
        receipt_required_above_paise: form.receipt_required_above_paise || null,
      });
      toast.success('Category created');
      setOpenNew(false);
      setForm({ name: '', code: '', is_active: true, per_diem_cap_paise: 0, receipt_required_above_paise: 0, policy_mode: 'warn', notes: '' });
      await refresh();
    } catch (e: any) {
      toast.error(errMsg(e, 'Failed'));
    } finally { setBusy(false); }
  };

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-lg font-semibold">Expense Categories</h2>
          <p className="text-sm text-slate-500">Policy caps + receipt thresholds per category.</p>
        </div>
        <Button onClick={() => setOpenNew(true)}><Plus size={14} className="mr-1" />New Category</Button>
      </div>

      {loading ? (
        <div className="text-center text-slate-400 py-8">Loading…</div>
      ) : rows.length === 0 ? (
        <Card className="p-8 text-center text-slate-500">No categories yet.</Card>
      ) : (
        <Card>
          <table className="w-full text-sm">
            <thead className="text-xs uppercase text-slate-500 border-b">
              <tr>
                <th className="text-left px-3 py-2">Name</th>
                <th className="text-left px-3 py-2">Code</th>
                <th className="text-right px-3 py-2">Per-diem cap</th>
                <th className="text-right px-3 py-2">Receipt above</th>
                <th className="text-left px-3 py-2">Policy</th>
                <th className="text-left px-3 py-2">Active</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(r => (
                <tr key={r.id} className="border-b">
                  <td className="px-3 py-2">{r.name}</td>
                  <td className="px-3 py-2 text-slate-500">{r.code || '—'}</td>
                  <td className="px-3 py-2 text-right">{fmtInr(r.per_diem_cap_paise)}</td>
                  <td className="px-3 py-2 text-right">{fmtInr(r.receipt_required_above_paise)}</td>
                  <td className="px-3 py-2">
                    <Badge className={cn(
                      r.policy_mode === 'block'
                        ? 'bg-red-100 text-red-700 border-red-300'
                        : 'bg-amber-100 text-amber-700 border-amber-300',
                      'border',
                    )}>
                      {r.policy_mode}
                    </Badge>
                  </td>
                  <td className="px-3 py-2">{r.is_active ? '✓' : '✗'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}

      <Dialog open={openNew} onOpenChange={(o: boolean) => setOpenNew(o)}>
        <DialogContent>
          <DialogTitle>New Expense Category</DialogTitle>
          <div className="grid grid-cols-2 gap-3 mt-3">
            <div><label className="text-xs text-slate-500">Name</label>
              <Input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} /></div>
            <div><label className="text-xs text-slate-500">Code</label>
              <Input value={form.code} onChange={e => setForm({ ...form, code: e.target.value })} /></div>
            <div><label className="text-xs text-slate-500">Per-diem cap (paise)</label>
              <Input type="number" value={form.per_diem_cap_paise}
                onChange={e => setForm({ ...form, per_diem_cap_paise: Number(e.target.value) })} /></div>
            <div><label className="text-xs text-slate-500">Receipt required above (paise)</label>
              <Input type="number" value={form.receipt_required_above_paise}
                onChange={e => setForm({ ...form, receipt_required_above_paise: Number(e.target.value) })} /></div>
            <div><label className="text-xs text-slate-500">Policy mode</label>
              <select className="w-full border border-slate-300 rounded px-2 py-1.5 text-sm"
                value={form.policy_mode} onChange={e => setForm({ ...form, policy_mode: e.target.value })}>
                <option value="warn">Warn</option>
                <option value="block">Block</option>
              </select></div>
            <div className="col-span-2"><label className="text-xs text-slate-500">Notes</label>
              <Input value={form.notes} onChange={e => setForm({ ...form, notes: e.target.value })} /></div>
          </div>
          <DialogFooter>
            <Button variant="secondary" onClick={() => setOpenNew(false)}>Cancel</Button>
            <Button onClick={create} disabled={busy}>{busy ? 'Saving…' : 'Create'}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

// ===========================================================================
// TAB 6 — Chain Builder
// ===========================================================================

const emptyStep = (order: number) => ({
  step_order: order,
  approver_type: 'reporting_manager',
  approver_ref: '',
  mode: 'sequential', parallel_rule: 'all',
  min_amount_paise: 0, max_amount_paise: 0,
  skip_if_same_person: false, skip_if_absent_days: 0,
  label: '',
});

const ChainBuilderTab: React.FC = () => {
  const [chains, setChains] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [openNew, setOpenNew] = useState(false);
  const [form, setForm] = useState<any>({
    name: '', entity_type: 'expense', department: '',
    effective_from: today(), effective_to: '',
    is_active: true, auto_approve_below_paise: 0,
    skip_if_same_person: true, notes: '',
    steps: [emptyStep(1)] as any[],
  });
  const [previewOn, setPreviewOn] = useState(false);
  const [previewForm, setPreviewForm] = useState({
    entity_type: 'expense', amount_paise: 100000, department: '',
  });
  const [previewResult, setPreviewResult] = useState<any | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = async () => {
    setLoading(true);
    try {
      const r = await client.get(ENDPOINTS.APPROVAL_CHAINS.LIST, {
        params: { include_inactive: true },
      });
      setChains(r.data || []);
    } catch (e: any) {
      toast.error(errMsg(e, 'Failed to load chains'));
    } finally { setLoading(false); }
  };
  useEffect(() => { refresh(); }, []);

  const setStep = (idx: number, patch: any) => {
    setForm((prev: any) => ({
      ...prev,
      steps: prev.steps.map((s: any, i: number) => i === idx ? { ...s, ...patch } : s),
    }));
  };
  const addStep = () => setForm((prev: any) => ({
    ...prev,
    steps: [...prev.steps, emptyStep(prev.steps.length + 1)],
  }));

  const submit = async () => {
    if (!form.name.trim()) { toast.error('Name required'); return; }
    setBusy(true);
    try {
      const payload = {
        ...form,
        department: form.department || null,
        effective_to: form.effective_to || null,
        auto_approve_below_paise: form.auto_approve_below_paise || null,
        steps: form.steps.map((s: any) => ({
          ...s,
          approver_ref: s.approver_ref || null,
          min_amount_paise: s.min_amount_paise === 0 ? null : Number(s.min_amount_paise),
          max_amount_paise: s.max_amount_paise === 0 ? null : Number(s.max_amount_paise),
          skip_if_absent_days: s.skip_if_absent_days === 0 ? null : Number(s.skip_if_absent_days),
        })),
      };
      await client.post(ENDPOINTS.APPROVAL_CHAINS.LIST, payload);
      toast.success('Chain created');
      setOpenNew(false);
      await refresh();
    } catch (e: any) {
      toast.error(errMsg(e, 'Failed to save chain — bands may not cover the amount range'));
    } finally { setBusy(false); }
  };

  const runPreview = async () => {
    try {
      const r = await client.get(ENDPOINTS.APPROVAL_CHAINS.PREVIEW, {
        params: {
          entity_type: previewForm.entity_type,
          amount_paise: previewForm.amount_paise,
          department: previewForm.department || undefined,
        },
      });
      setPreviewResult(r.data);
    } catch (e: any) {
      toast.error(errMsg(e, 'Preview failed'));
      setPreviewResult(null);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-lg font-semibold">Approval Chain Builder</h2>
          <p className="text-sm text-slate-500">
            Configure ordered approval steps with amount bands, parallel rules,
            and self-approval skips. Preview a routing before rolling out.
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="secondary" onClick={() => setPreviewOn(true)}>
            <Eye size={14} className="mr-1" />Preview Routing
          </Button>
          <Button onClick={() => setOpenNew(true)}>
            <Plus size={14} className="mr-1" />New Chain
          </Button>
        </div>
      </div>

      {loading ? (
        <div className="text-center text-slate-400 py-8">Loading…</div>
      ) : chains.length === 0 ? (
        <Card className="p-8 text-center text-slate-500">
          No chains yet. Create one so Expense/Travel submissions can route.
        </Card>
      ) : (
        <div className="space-y-3">
          {chains.map(c => (
            <Card key={c.id} className="p-4">
              <div className="flex justify-between items-start">
                <div>
                  <div className="font-medium">{c.name}</div>
                  <div className="text-xs text-slate-500 mt-1">
                    Entity: <b>{c.entity_type}</b>
                    {c.department ? ` · Dept: ${c.department}` : ' · Org-wide'}
                    {' · Effective from '}{c.effective_from}
                    {c.auto_approve_below_paise
                      ? ` · Auto-approve below ${fmtInr(c.auto_approve_below_paise)}`
                      : ''}
                  </div>
                </div>
                <Badge className={cn(
                  c.is_active ? 'bg-green-100 text-green-700 border-green-300' : 'bg-slate-100 text-slate-600 border-slate-300',
                  'border',
                )}>
                  {c.is_active ? 'active' : 'disabled'}
                </Badge>
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                {(c.steps || []).map((s: any) => (
                  <div key={s.id} className="text-xs bg-slate-50 border border-slate-200 px-2 py-1 rounded">
                    <span className="font-semibold">#{s.step_order}</span>{' '}
                    {s.approver_type}
                    {s.approver_ref ? ` (${s.approver_ref})` : ''}
                    {' · '}{s.mode}
                    {s.mode === 'parallel' ? `/${s.parallel_rule}` : ''}
                    {(s.min_amount_paise != null || s.max_amount_paise != null) && (
                      <span className="ml-1 text-slate-500">
                        [{fmtInr(s.min_amount_paise || 0)}
                        {'–'}
                        {s.max_amount_paise != null ? fmtInr(s.max_amount_paise) : '∞'}]
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </Card>
          ))}
        </div>
      )}

      <Dialog open={openNew} onOpenChange={(o: boolean) => setOpenNew(o)}>
        <DialogContent className="max-w-3xl">
          <DialogTitle>New Approval Chain</DialogTitle>
          <div className="grid grid-cols-3 gap-3 mt-3">
            <div className="col-span-2">
              <label className="text-xs text-slate-500">Name</label>
              <Input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} />
            </div>
            <div>
              <label className="text-xs text-slate-500">Entity type</label>
              <select className="w-full border border-slate-300 rounded px-2 py-1.5 text-sm"
                value={form.entity_type} onChange={e => setForm({ ...form, entity_type: e.target.value })}>
                <option value="expense">expense</option>
                <option value="travel">travel</option>
              </select>
            </div>
            <div>
              <label className="text-xs text-slate-500">Department (blank = org-wide)</label>
              <Input value={form.department} onChange={e => setForm({ ...form, department: e.target.value })} />
            </div>
            <div>
              <label className="text-xs text-slate-500">Effective from</label>
              <Input type="date" value={form.effective_from} onChange={e => setForm({ ...form, effective_from: e.target.value })} />
            </div>
            <div>
              <label className="text-xs text-slate-500">Auto-approve below (paise)</label>
              <Input type="number" value={form.auto_approve_below_paise}
                onChange={e => setForm({ ...form, auto_approve_below_paise: Number(e.target.value) })} />
            </div>
          </div>

          <div className="mt-4">
            <div className="flex justify-between items-center">
              <div className="font-medium text-sm">Steps</div>
              <Button size="sm" variant="secondary" onClick={addStep}>
                <Plus size={12} className="mr-1" />Add step
              </Button>
            </div>
            <div className="mt-2 space-y-2">
              {form.steps.map((s: any, idx: number) => (
                <div key={idx} className="p-3 border border-slate-200 rounded space-y-2">
                  <div className="grid grid-cols-12 gap-2">
                    <div className="col-span-1">
                      <label className="text-[10px] text-slate-500">Order</label>
                      <Input type="number" value={s.step_order}
                        onChange={e => setStep(idx, { step_order: Number(e.target.value) })} />
                    </div>
                    <div className="col-span-3">
                      <label className="text-[10px] text-slate-500">Approver</label>
                      <select className="w-full border border-slate-300 rounded px-2 py-1.5 text-sm"
                        value={s.approver_type} onChange={e => setStep(idx, { approver_type: e.target.value })}>
                        <option value="reporting_manager">Reporting manager</option>
                        <option value="dept_head">Department head</option>
                        <option value="role">Role</option>
                        <option value="specific_user">Specific user</option>
                        <option value="finance">Finance</option>
                      </select>
                    </div>
                    <div className="col-span-2">
                      <label className="text-[10px] text-slate-500">Ref (role/user)</label>
                      <Input value={s.approver_ref}
                        onChange={e => setStep(idx, { approver_ref: e.target.value })} />
                    </div>
                    <div className="col-span-2">
                      <label className="text-[10px] text-slate-500">Mode</label>
                      <select className="w-full border border-slate-300 rounded px-2 py-1.5 text-sm"
                        value={s.mode} onChange={e => setStep(idx, { mode: e.target.value })}>
                        <option value="sequential">sequential</option>
                        <option value="parallel">parallel</option>
                      </select>
                    </div>
                    <div className="col-span-2">
                      <label className="text-[10px] text-slate-500">Parallel rule</label>
                      <select className="w-full border border-slate-300 rounded px-2 py-1.5 text-sm"
                        value={s.parallel_rule} onChange={e => setStep(idx, { parallel_rule: e.target.value })}>
                        <option value="all">all</option>
                        <option value="any">any</option>
                      </select>
                    </div>
                    <div className="col-span-2">
                      <label className="text-[10px] text-slate-500">Label</label>
                      <Input value={s.label} onChange={e => setStep(idx, { label: e.target.value })} />
                    </div>
                  </div>
                  <div className="grid grid-cols-12 gap-2">
                    <div className="col-span-3">
                      <label className="text-[10px] text-slate-500">Min amount (paise) — blank/0 = 0</label>
                      <Input type="number" value={s.min_amount_paise}
                        onChange={e => setStep(idx, { min_amount_paise: Number(e.target.value) })} />
                    </div>
                    <div className="col-span-3">
                      <label className="text-[10px] text-slate-500">Max amount (paise) — blank/0 = ∞</label>
                      <Input type="number" value={s.max_amount_paise}
                        onChange={e => setStep(idx, { max_amount_paise: Number(e.target.value) })} />
                    </div>
                    <div className="col-span-3 flex items-end">
                      <label className="text-xs flex items-center gap-2">
                        <input type="checkbox" checked={s.skip_if_same_person}
                          onChange={e => setStep(idx, { skip_if_same_person: e.target.checked })} />
                        Skip if same person as submitter
                      </label>
                    </div>
                    <div className="col-span-3">
                      <label className="text-[10px] text-slate-500">Skip if approver absent &gt; N days</label>
                      <Input type="number" value={s.skip_if_absent_days}
                        onChange={e => setStep(idx, { skip_if_absent_days: Number(e.target.value) })} />
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <DialogFooter>
            <Button variant="secondary" onClick={() => setOpenNew(false)}>Cancel</Button>
            <Button onClick={submit} disabled={busy}>{busy ? 'Saving…' : 'Create chain'}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={previewOn} onOpenChange={(o: boolean) => setPreviewOn(o)}>
        <DialogContent>
          <DialogTitle>Preview routing</DialogTitle>
          <div className="grid grid-cols-3 gap-3 mt-3">
            <div>
              <label className="text-xs text-slate-500">Entity type</label>
              <select className="w-full border border-slate-300 rounded px-2 py-1.5 text-sm"
                value={previewForm.entity_type} onChange={e => setPreviewForm({ ...previewForm, entity_type: e.target.value })}>
                <option value="expense">expense</option>
                <option value="travel">travel</option>
              </select>
            </div>
            <div>
              <label className="text-xs text-slate-500">Amount (paise)</label>
              <Input type="number" value={previewForm.amount_paise}
                onChange={e => setPreviewForm({ ...previewForm, amount_paise: Number(e.target.value) })} />
            </div>
            <div>
              <label className="text-xs text-slate-500">Department</label>
              <Input value={previewForm.department}
                onChange={e => setPreviewForm({ ...previewForm, department: e.target.value })} />
            </div>
          </div>
          <div className="mt-3 flex justify-end">
            <Button onClick={runPreview}>Run preview</Button>
          </div>
          {previewResult && (
            <div className="mt-3 p-3 rounded bg-slate-50 border border-slate-200">
              {previewResult.chain ? (
                <>
                  <div className="text-sm">
                    Chain <b>{previewResult.chain.name}</b>{' '}
                    <span className="text-slate-500">({previewResult.chain.department || 'org-wide'})</span>
                  </div>
                  <div className="mt-2 space-y-1">
                    {previewResult.plan.length === 0 ? (
                      <div className="text-sm text-green-700">
                        No steps — routes as AUTO-APPROVED.
                      </div>
                    ) : previewResult.plan.map((p: any, i: number) => (
                      <div key={i} className="text-xs">
                        <span className="font-semibold">#{p.step_order}</span>{' '}
                        {p.approver_type} · {p.mode}
                        {p.mode === 'parallel' ? `/${p.parallel_rule}` : ''}
                        {p.skip_reason && (
                          <span className="ml-2 text-amber-700">⚠ {p.skip_reason}</span>
                        )}
                      </div>
                    ))}
                  </div>
                </>
              ) : (
                <div className="text-sm text-red-700">
                  {previewResult.reason || 'No matching chain'}
                </div>
              )}
            </div>
          )}
          <DialogFooter>
            <Button variant="secondary" onClick={() => { setPreviewOn(false); setPreviewResult(null); }}>Close</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

// ===========================================================================
// Workspace shell
// ===========================================================================

export const ExpensesWorkspace: React.FC = () => {
  const [tab, setTab] = useState<TabId>('my-expenses');

  return (
    <div className="p-6 space-y-4">
      <div className="flex gap-1 border-b border-slate-200">
        {TABS.map(t => {
          const Icon = t.icon;
          const active = tab === t.id;
          return (
            <button key={t.id} onClick={() => setTab(t.id)}
              className={cn(
                'px-4 py-2 flex items-center gap-2 text-sm border-b-2 -mb-px transition-colors',
                active
                  ? 'border-blue-600 text-blue-700 font-medium'
                  : 'border-transparent text-slate-500 hover:text-slate-700',
              )}>
              <Icon size={14} />{t.label}
            </button>
          );
        })}
      </div>

      {tab === 'my-expenses' && <MyExpensesTab />}
      {tab === 'my-travel' && <MyTravelTab />}
      {tab === 'approvals' && <ApproverQueueTab />}
      {tab === 'finance' && <FinanceQueueTab />}
      {tab === 'categories' && <CategoriesTab />}
      {tab === 'chain-builder' && <ChainBuilderTab />}
    </div>
  );
};

export default ExpensesWorkspace;
