/**
 * Revision-cycle workspace: create cycle, bulk-draft per department or
 * list, edit hike per row (in the per-revision view), bulk-submit.
 */
import React, { useEffect, useState } from 'react';
import {
  Plus, Send, Calendar, RefreshCw, Layers, TrendingUp,
} from 'lucide-react';
import { Card, Button, Badge, cn } from './ui-elements';
import { toast } from 'sonner';
import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';
import { Dialog, DialogContent, DialogTitle, DialogFooter } from './ui/dialog';
import { Input } from './ui/input';

interface Cycle {
  id: number; name: string; effective_from: string; status: string;
  budget_hike_amount: number | null; notes: string | null;
  total_revisions: number; total_hike_amount: number;
  avg_hike_percent: number; by_status: Record<string, number>;
}

const errMsg = (err: any, fallback: string): string => {
  const detail = err?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail))
    return detail.map((d: any) => d?.msg || JSON.stringify(d)).join('; ');
  return err?.message || fallback;
};

export const RevisionCyclesView: React.FC = () => {
  const [cycles, setCycles] = useState<Cycle[]>([]);
  const [loading, setLoading] = useState(true);
  const [createOpen, setCreateOpen] = useState(false);
  const [bulkOpen, setBulkOpen] = useState<Cycle | null>(null);
  const [form, setForm] = useState({
    name: '', effective_from: new Date().toISOString().slice(0, 10),
    budget_hike_amount: '' as number | '', notes: '',
  });
  const [bulkForm, setBulkForm] = useState({
    department: '',
    revision_type: 'increment' as 'increment' | 'promotion' | 'correction' | 'demotion',
    blanket_hike_percent: 8,
    reason: '',
  });
  const [busy, setBusy] = useState(false);

  const fetch = async () => {
    setLoading(true);
    try {
      const r = await client.get(ENDPOINTS.REVISIONS.CYCLES);
      setCycles(r.data || []);
    } catch (e: any) { toast.error(errMsg(e, 'Failed to load')); }
    finally { setLoading(false); }
  };
  useEffect(() => { fetch(); }, []);

  const createCycle = async () => {
    setBusy(true);
    try {
      await client.post(ENDPOINTS.REVISIONS.CYCLES, {
        name: form.name,
        effective_from: form.effective_from,
        budget_hike_amount: form.budget_hike_amount === '' ? null : Number(form.budget_hike_amount),
        notes: form.notes || null,
      });
      toast.success('Cycle created'); setCreateOpen(false); fetch();
    } catch (e: any) { toast.error(errMsg(e, 'Failed')); }
    finally { setBusy(false); }
  };

  const bulkDraft = async () => {
    if (!bulkOpen) return;
    setBusy(true);
    try {
      const r = await client.post(ENDPOINTS.REVISIONS.CYCLE_BULK_DRAFT(bulkOpen.id), {
        department: bulkForm.department,
        revision_type: bulkForm.revision_type,
        blanket_hike_percent: bulkForm.blanket_hike_percent,
        reason: bulkForm.reason || null,
      });
      toast.success(`Drafted ${r.data.affected}, skipped ${r.data.skipped}`);
      setBulkOpen(null); fetch();
    } catch (e: any) { toast.error(errMsg(e, 'Bulk draft failed')); }
    finally { setBusy(false); }
  };

  const bulkSubmit = async (c: Cycle) => {
    try {
      const r = await client.post(ENDPOINTS.REVISIONS.CYCLE_BULK_SUBMIT(c.id), {});
      toast.success(`Submitted ${r.data.affected} for approval`);
      fetch();
    } catch (e: any) { toast.error(errMsg(e, 'Bulk submit failed')); }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Layers className="w-6 h-6 text-blue-600" /> Revision Cycles
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Annual / bulk hike workspaces. Drafts can be edited per-employee before bulk submission.
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={fetch}><RefreshCw className="w-4 h-4" /></Button>
          <Button onClick={() => setCreateOpen(true)}><Plus className="w-4 h-4 mr-2" /> New cycle</Button>
        </div>
      </div>

      {loading ? <div className="py-8 text-center text-slate-500">Loading…</div>
        : cycles.length === 0 ? <Card className="p-12 text-center text-slate-500">No revision cycles yet.</Card>
          : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {cycles.map(c => (
                <Card key={c.id} className="p-4 space-y-3">
                  <div className="flex items-start justify-between">
                    <div>
                      <h2 className="text-lg font-bold">{c.name}</h2>
                      <div className="text-xs text-slate-500 flex items-center gap-1 mt-1">
                        <Calendar className="w-3 h-3" /> Effective {c.effective_from}
                      </div>
                    </div>
                    <Badge variant={c.status === 'completed' ? 'success' : 'info'}>{c.status}</Badge>
                  </div>
                  <div className="grid grid-cols-3 gap-2 text-sm">
                    <div>
                      <div className="text-[10px] uppercase text-slate-500">Revisions</div>
                      <div className="font-bold">{c.total_revisions}</div>
                    </div>
                    <div>
                      <div className="text-[10px] uppercase text-slate-500">Total hike</div>
                      <div className="font-bold text-green-700">₹{c.total_hike_amount.toLocaleString('en-IN')}</div>
                    </div>
                    <div>
                      <div className="text-[10px] uppercase text-slate-500">Avg %</div>
                      <div className="font-bold flex items-center gap-1"><TrendingUp className="w-3 h-3" />{c.avg_hike_percent.toFixed(2)}%</div>
                    </div>
                  </div>
                  {c.budget_hike_amount && (
                    <div className="text-xs text-slate-500">
                      Budget: ₹{c.budget_hike_amount.toLocaleString('en-IN')} ·{' '}
                      <span className={cn('font-bold',
                        c.total_hike_amount > c.budget_hike_amount ? 'text-red-700' : 'text-green-700')}>
                        {c.total_hike_amount > c.budget_hike_amount ? 'Over' : 'Under'} budget
                      </span>
                    </div>
                  )}
                  <div className="flex flex-wrap gap-1">
                    {Object.entries(c.by_status).map(([s, n]) => (
                      <span key={s} className="text-[10px] px-2 py-0.5 bg-slate-100 rounded">
                        {s}: {n}
                      </span>
                    ))}
                  </div>
                  <div className="flex gap-2 pt-2 border-t border-slate-100">
                    <Button size="sm" variant="outline"
                      onClick={() => { setBulkOpen(c); setBulkForm({ ...bulkForm, department: '' }); }}>
                      <Plus className="w-3 h-3 mr-1" /> Bulk-draft
                    </Button>
                    <Button size="sm" onClick={() => bulkSubmit(c)}>
                      <Send className="w-3 h-3 mr-1" /> Submit all drafts
                    </Button>
                  </div>
                </Card>
              ))}
            </div>
          )}

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="max-w-md">
          <DialogTitle>New Revision Cycle</DialogTitle>
          <div className="space-y-3 mt-4">
            <div>
              <label className="text-xs font-semibold text-slate-600">Name</label>
              <Input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })}
                placeholder="FY25-26 Annual Increment" />
            </div>
            <div>
              <label className="text-xs font-semibold text-slate-600">Effective from</label>
              <Input type="date" value={form.effective_from}
                onChange={e => setForm({ ...form, effective_from: e.target.value })} />
            </div>
            <div>
              <label className="text-xs font-semibold text-slate-600">Budget (₹, optional)</label>
              <Input type="number" min={0} value={form.budget_hike_amount}
                onChange={e => setForm({ ...form, budget_hike_amount: e.target.value === '' ? '' : Number(e.target.value) })} />
            </div>
            <div>
              <label className="text-xs font-semibold text-slate-600">Notes</label>
              <textarea value={form.notes} onChange={e => setForm({ ...form, notes: e.target.value })}
                className="w-full border border-slate-200 rounded-md p-2 text-sm" rows={2} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateOpen(false)}>Cancel</Button>
            <Button isLoading={busy} onClick={createCycle}>Create</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!bulkOpen} onOpenChange={(o: boolean) => { if (!o) setBulkOpen(null); }}>
        <DialogContent className="max-w-md">
          <DialogTitle>Bulk draft for {bulkOpen?.name}</DialogTitle>
          <div className="space-y-3 mt-4">
            <div>
              <label className="text-xs font-semibold text-slate-600">Department</label>
              <Input value={bulkForm.department}
                onChange={e => setBulkForm({ ...bulkForm, department: e.target.value })}
                placeholder="e.g. Engineering" />
              <div className="text-[10px] text-slate-400 mt-1">
                One DRAFT per active employee in that department. Existing open revisions in this cycle are skipped.
              </div>
            </div>
            <div>
              <label className="text-xs font-semibold text-slate-600">Type</label>
              <select value={bulkForm.revision_type}
                onChange={e => setBulkForm({ ...bulkForm, revision_type: e.target.value as any })}
                className="w-full border border-slate-200 rounded-md h-9 px-2 text-sm">
                <option value="increment">Increment</option>
                <option value="promotion">Promotion</option>
                <option value="correction">Correction</option>
              </select>
            </div>
            <div>
              <label className="text-xs font-semibold text-slate-600">Blanket hike %</label>
              <Input type="number" min={-50} max={200} step={0.5}
                value={bulkForm.blanket_hike_percent}
                onChange={e => setBulkForm({ ...bulkForm, blanket_hike_percent: Number(e.target.value) })} />
            </div>
            <div>
              <label className="text-xs font-semibold text-slate-600">Reason</label>
              <textarea value={bulkForm.reason}
                onChange={e => setBulkForm({ ...bulkForm, reason: e.target.value })}
                className="w-full border border-slate-200 rounded-md p-2 text-sm" rows={2} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setBulkOpen(null)}>Cancel</Button>
            <Button isLoading={busy} onClick={bulkDraft}>Draft</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};
