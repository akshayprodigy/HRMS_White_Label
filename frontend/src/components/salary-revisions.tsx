/**
 * Salary revisions admin: list, create, edit, submit, action queue,
 * apply-now and apply-due. HR/Super Admin/PM/CEO depending on perms.
 */
import React, { useEffect, useMemo, useState } from 'react';
import {
  Plus, Edit2, Send, Check, X, Play, Download, RefreshCw, Filter,
  AlertTriangle, Calendar, TrendingUp,
} from 'lucide-react';
import { Card, Button, Badge, cn } from './ui-elements';
import { toast } from 'sonner';
import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';
import { Dialog, DialogContent, DialogTitle, DialogFooter } from './ui/dialog';
import { Input } from './ui/input';

interface Revision {
  id: number; employee_id: number;
  employee_full_name: string | null; employee_code: string | null;
  department: string | null; cycle_id: number | null;
  revision_type: 'increment' | 'promotion' | 'correction' | 'demotion';
  effective_from: string; reason: string | null; status: string;
  old_designation_title: string | null; new_designation_title: string | null;
  old_grade_name: string | null; new_grade_name: string | null;
  old_basic: number; old_conveyance: number; old_hra: number;
  old_other_allowance: number; old_ctc: number;
  new_basic: number; new_conveyance: number; new_hra: number;
  new_other_allowance: number; new_ctc: number;
  hike_amount: number; hike_percent: number;
  band_warning: string | null;
  rejected_reason: string | null;
  letter_id: number | null;
  arrears_run_id: number | null; arrears_amount: number; arrears_months: number;
  applied_at: string | null;
}
interface Employee { id: number; employee_id: string; full_name?: string; name?: string }
interface Designation { id: number; title: string; grade_id: number | null }
interface Grade { id: number; name: string; min_salary: number | null; max_salary: number | null }

const errMsg = (err: any, fallback: string): string => {
  const detail = err?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail))
    return detail.map((d: any) => d?.msg || JSON.stringify(d)).join('; ');
  return err?.message || fallback;
};

const today = () => new Date().toISOString().slice(0, 10);

const statusChip = (s: string) => {
  const v = s === 'applied' || s === 'approved' ? 'success'
    : s === 'rejected' || s === 'cancelled' ? 'error'
      : 'info';
  return <Badge variant={v as any}>{s}</Badge>;
};
const typeChip = (t: string) => {
  const cls = t === 'promotion' ? 'bg-purple-100 text-purple-700'
    : t === 'demotion' ? 'bg-red-100 text-red-700'
      : 'bg-blue-100 text-blue-700';
  return <span className={cn('px-2 py-0.5 rounded text-[10px] font-bold uppercase', cls)}>{t}</span>;
};

export const SalaryRevisionsView: React.FC = () => {
  const [rows, setRows] = useState<Revision[]>([]);
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [designations, setDesignations] = useState<Designation[]>([]);
  const [grades, setGrades] = useState<Grade[]>([]);
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState<string>('pending');
  const [createOpen, setCreateOpen] = useState(false);
  const [reviewing, setReviewing] = useState<Revision | null>(null);
  const [action, setAction] = useState<'approve' | 'reject'>('approve');
  const [comment, setComment] = useState('');
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({
    employee_id: 0,
    revision_type: 'increment' as 'increment' | 'promotion' | 'correction' | 'demotion',
    effective_from: today(),
    reason: '',
    new_designation_id: null as number | null,
    new_grade_id: null as number | null,
    new_basic: 0, new_conveyance: 0, new_hra: 0, new_other_allowance: 0,
  });
  const [pickedEmp, setPickedEmp] = useState<{ old_basic: number; old_ctc: number; band: string | null } | null>(null);
  const [pickedRating, setPickedRating] = useState<{ final_rating: number | null; cycle_name: string | null } | null>(null);

  const fetchAll = async () => {
    setLoading(true);
    try {
      const [r, e, d, g] = await Promise.all([
        client.get(ENDPOINTS.REVISIONS.REVISIONS, {
          params: status === 'all' ? {} : { status },
        }),
        client.get(ENDPOINTS.HR.EMPLOYEES, { params: { size: 500 } })
          .catch(() => ({ data: { items: [] } })),
        client.get(ENDPOINTS.REVISIONS.DESIGNATIONS),
        client.get(ENDPOINTS.REVISIONS.GRADES),
      ]);
      setRows(r.data || []);
      // GET /hr/employees returns a paginated { items, total } envelope.
      setEmployees(Array.isArray(e.data?.items) ? e.data.items : []);
      setDesignations(d.data || []);
      setGrades(g.data || []);
    } catch (e: any) {
      toast.error(errMsg(e, 'Failed to load revisions'));
    } finally { setLoading(false); }
  };

  useEffect(() => { fetchAll(); /* eslint-disable-line */ }, [status]);

  const newCtc = form.new_basic + form.new_conveyance + form.new_hra + form.new_other_allowance;
  const hikePct = pickedEmp && pickedEmp.old_ctc > 0
    ? (((newCtc - pickedEmp.old_ctc) / pickedEmp.old_ctc) * 100).toFixed(2) : '0.00';

  // Live band warning
  const targetGrade = grades.find(g => g.id === form.new_grade_id);
  const liveBandWarning = targetGrade && (
    (targetGrade.min_salary != null && newCtc < targetGrade.min_salary)
      ? `New CTC ${newCtc.toLocaleString('en-IN')} is below the grade minimum ${targetGrade.min_salary.toLocaleString('en-IN')}.`
      : (targetGrade.max_salary != null && newCtc > targetGrade.max_salary)
        ? `New CTC ${newCtc.toLocaleString('en-IN')} is above the grade maximum ${targetGrade.max_salary.toLocaleString('en-IN')}.`
        : null
  );

  const submitRevision = async (alsoSubmit: boolean) => {
    setBusy(true);
    try {
      const created = (await client.post(ENDPOINTS.REVISIONS.REVISIONS, {
        ...form,
        new_ctc: newCtc,
      })).data;
      if (alsoSubmit) {
        await client.post(ENDPOINTS.REVISIONS.SUBMIT(created.id));
      }
      toast.success(alsoSubmit ? 'Created and submitted' : 'Saved as draft');
      setCreateOpen(false); fetchAll();
    } catch (e: any) { toast.error(errMsg(e, 'Save failed')); }
    finally { setBusy(false); }
  };

  const actOnReview = async () => {
    if (!reviewing) return;
    setBusy(true);
    try {
      await client.post(ENDPOINTS.REVISIONS.ACTION(reviewing.id), {
        action, comment: comment || undefined,
      });
      toast.success(action === 'approve' ? 'Approved' : 'Rejected');
      setReviewing(null); setComment(''); fetchAll();
    } catch (e: any) { toast.error(errMsg(e, 'Action failed')); }
    finally { setBusy(false); }
  };

  const applyNow = async (r: Revision) => {
    try {
      await client.post(ENDPOINTS.REVISIONS.APPLY(r.id));
      toast.success('Applied');
      fetchAll();
    } catch (e: any) { toast.error(errMsg(e, 'Apply failed')); }
  };

  const applyDue = async () => {
    try {
      const r = await client.post(ENDPOINTS.REVISIONS.APPLY_DUE);
      toast.success(`Applied ${r.data.applied}, skipped ${r.data.skipped}`);
      fetchAll();
    } catch (e: any) { toast.error(errMsg(e, 'Apply-due failed')); }
  };

  const downloadLetter = async (r: Revision) => {
    if (!r.letter_id) { toast.error('No letter yet'); return; }
    try {
      const res = await client.get(ENDPOINTS.REVISIONS.LETTER(r.id), { responseType: 'blob' });
      const blob = new Blob([res.data], { type: 'application/pdf' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `revision_${r.id}.pdf`;
      a.click(); URL.revokeObjectURL(url);
    } catch (e: any) { toast.error(errMsg(e, 'Download failed')); }
  };

  const onEmployeeChange = (id: number) => {
    setForm(f => ({ ...f, employee_id: id }));
    const emp = employees.find((e: any) => e.id === id || e.user_id === id);
    if (!emp) { setPickedEmp(null); setPickedRating(null); return; }
    // Read-only bridge to Performance: fetch the latest RELEASED rating
    // so HR sees it as decision context. Never triggers a hike.
    const userId = (emp as any).user_id || emp.id;
    client.get(`/performance/ratings/${userId}`)
      .then(r => setPickedRating({
        final_rating: r.data?.final_rating ?? null,
        cycle_name: r.data?.cycle_name ?? null,
      }))
      .catch(() => setPickedRating(null));
    // Pull employee detail to get current comp baseline.
    client.get(`${ENDPOINTS.HR.EMPLOYEES}/${emp.id}`).then(r => {
      const e: any = r.data;
      const basic = Number(e.salary || 0);
      const ca = Number(e.conveyance_allowance ?? Math.round(basic * 0.30));
      const hra = Number(e.hra ?? Math.round(basic * 0.50));
      const other = Number(e.other_allowance ?? Math.round(basic * 0.20));
      setPickedEmp({ old_basic: basic, old_ctc: basic + ca + hra + other, band: null });
      // pre-fill the new fields with current values
      setForm(f => ({
        ...f, employee_id: id,
        new_basic: basic, new_conveyance: ca, new_hra: hra, new_other_allowance: other,
        new_designation_id: e.designation_id ?? null, new_grade_id: e.grade_id ?? null,
      }));
    }).catch(() => setPickedEmp({ old_basic: 0, old_ctc: 0, band: null }));
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <TrendingUp className="w-6 h-6 text-blue-600" /> Salary Revisions
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Promotions, hikes, corrections — apply on/after effective date. Back-dated revisions auto-arrear in next payroll.
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={applyDue}><Play className="w-4 h-4 mr-2" /> Apply due</Button>
          <Button onClick={() => { setCreateOpen(true); setPickedEmp(null); setForm({
            employee_id: 0, revision_type: 'increment', effective_from: today(),
            reason: '', new_designation_id: null, new_grade_id: null,
            new_basic: 0, new_conveyance: 0, new_hra: 0, new_other_allowance: 0,
          }); }}><Plus className="w-4 h-4 mr-2" /> New revision</Button>
        </div>
      </div>

      <Card className="p-4">
        <div className="flex items-center gap-3 mb-4">
          <Filter className="w-4 h-4 text-slate-500" />
          <select value={status} onChange={e => setStatus(e.target.value)}
            className="border border-slate-200 rounded-md h-9 px-2 text-sm">
            <option value="pending">Pending</option>
            <option value="approved">Approved (awaiting effective date)</option>
            <option value="applied">Applied</option>
            <option value="rejected">Rejected</option>
            <option value="draft">Draft</option>
            <option value="all">All</option>
          </select>
          <Button variant="outline" onClick={fetchAll}><RefreshCw className="w-4 h-4" /></Button>
        </div>

        {loading ? <div className="py-8 text-center text-slate-500">Loading…</div>
          : rows.length === 0 ? <div className="py-12 text-center text-slate-500">No revisions in this view.</div>
            : (
              <div className="overflow-x-auto">
                <table className="min-w-full text-sm">
                  <thead className="text-left text-xs uppercase text-slate-500 border-b">
                    <tr>
                      <th className="p-3">Employee</th>
                      <th className="p-3">Type</th>
                      <th className="p-3">Effective</th>
                      <th className="p-3">Old → New CTC</th>
                      <th className="p-3">Hike</th>
                      <th className="p-3">Status</th>
                      <th className="p-3">Letter / Arrear</th>
                      <th className="p-3 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map(r => (
                      <tr key={r.id} className="border-b hover:bg-slate-50">
                        <td className="p-3">
                          <div className="font-medium">{r.employee_full_name || `#${r.employee_id}`}</div>
                          <div className="text-[10px] text-slate-400">{r.employee_code} · {r.department}</div>
                        </td>
                        <td className="p-3">{typeChip(r.revision_type)}</td>
                        <td className="p-3"><Calendar className="w-3 h-3 inline mr-1" />{r.effective_from}</td>
                        <td className="p-3 font-mono text-xs">
                          ₹{r.old_ctc.toLocaleString('en-IN')} → ₹{r.new_ctc.toLocaleString('en-IN')}
                        </td>
                        <td className="p-3">
                          <span className={cn('font-bold', r.hike_amount > 0 ? 'text-green-700' : 'text-red-700')}>
                            {r.hike_amount > 0 ? '+' : ''}{r.hike_percent.toFixed(2)}%
                          </span>
                          {r.band_warning && (
                            <div className="text-[10px] text-amber-700 flex items-center gap-1 mt-1">
                              <AlertTriangle className="w-3 h-3" /> Band warning
                            </div>
                          )}
                        </td>
                        <td className="p-3">{statusChip(r.status)}</td>
                        <td className="p-3 text-[10px]">
                          {r.letter_id ? <Badge variant="info">Letter ready</Badge> : '—'}
                          {r.arrears_run_id ? (
                            <div className="text-slate-500 mt-1">
                              Arrear ₹{r.arrears_amount.toLocaleString('en-IN')} ({r.arrears_months}mo) → run #{r.arrears_run_id}
                            </div>
                          ) : null}
                        </td>
                        <td className="p-3 text-right space-x-1">
                          {r.status === 'pending' && (
                            <>
                              <Button size="sm" variant="outline"
                                onClick={() => { setReviewing(r); setAction('approve'); setComment(''); }}>
                                <Check className="w-3 h-3 text-green-600" />
                              </Button>
                              <Button size="sm" variant="outline"
                                onClick={() => { setReviewing(r); setAction('reject'); setComment(''); }}>
                                <X className="w-3 h-3 text-red-600" />
                              </Button>
                            </>
                          )}
                          {r.status === 'approved' && (
                            <Button size="sm" variant="outline" onClick={() => applyNow(r)}>
                              Apply now
                            </Button>
                          )}
                          {r.letter_id && (
                            <Button size="sm" variant="outline" onClick={() => downloadLetter(r)}>
                              <Download className="w-3 h-3" />
                            </Button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
      </Card>

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="max-w-2xl">
          <DialogTitle>New Salary Revision</DialogTitle>
          <div className="space-y-4 mt-4 max-h-[65vh] overflow-y-auto pr-1 grid grid-cols-2 gap-3">
            <div className="col-span-2">
              <label className="text-xs font-semibold text-slate-600">Employee</label>
              <select value={form.employee_id || ''}
                onChange={e => onEmployeeChange(Number(e.target.value))}
                className="w-full border border-slate-200 rounded-md h-9 px-2 text-sm">
                <option value="">— Select —</option>
                {employees.map((e: any) =>
                  <option key={e.id} value={e.id}>
                    {e.full_name || e.name} ({e.employee_id})
                  </option>
                )}
              </select>
            </div>
            <div>
              <label className="text-xs font-semibold text-slate-600">Type</label>
              <select value={form.revision_type}
                onChange={e => setForm({ ...form, revision_type: e.target.value as any })}
                className="w-full border border-slate-200 rounded-md h-9 px-2 text-sm">
                <option value="increment">Increment</option>
                <option value="promotion">Promotion</option>
                <option value="correction">Correction</option>
                <option value="demotion">Demotion</option>
              </select>
            </div>
            <div>
              <label className="text-xs font-semibold text-slate-600">Effective from</label>
              <Input type="date" value={form.effective_from}
                onChange={e => setForm({ ...form, effective_from: e.target.value })} />
            </div>
            <div>
              <label className="text-xs font-semibold text-slate-600">New designation</label>
              <select value={form.new_designation_id ?? ''}
                onChange={e => setForm({ ...form, new_designation_id: e.target.value ? Number(e.target.value) : null })}
                className="w-full border border-slate-200 rounded-md h-9 px-2 text-sm">
                <option value="">— Unchanged —</option>
                {designations.map(d => <option key={d.id} value={d.id}>{d.title}</option>)}
              </select>
            </div>
            <div>
              <label className="text-xs font-semibold text-slate-600">New grade</label>
              <select value={form.new_grade_id ?? ''}
                onChange={e => setForm({ ...form, new_grade_id: e.target.value ? Number(e.target.value) : null })}
                className="w-full border border-slate-200 rounded-md h-9 px-2 text-sm">
                <option value="">— Unchanged —</option>
                {grades.map(g => <option key={g.id} value={g.id}>
                  {g.name}{g.min_salary != null ? ` (₹${g.min_salary}–${g.max_salary})` : ''}
                </option>)}
              </select>
            </div>
            <div>
              <label className="text-xs font-semibold text-slate-600">New Basic</label>
              <Input type="number" min={0} value={form.new_basic}
                onChange={e => setForm({ ...form, new_basic: Number(e.target.value) })} />
            </div>
            <div>
              <label className="text-xs font-semibold text-slate-600">New HRA</label>
              <Input type="number" min={0} value={form.new_hra}
                onChange={e => setForm({ ...form, new_hra: Number(e.target.value) })} />
            </div>
            <div>
              <label className="text-xs font-semibold text-slate-600">New Conveyance</label>
              <Input type="number" min={0} value={form.new_conveyance}
                onChange={e => setForm({ ...form, new_conveyance: Number(e.target.value) })} />
            </div>
            <div>
              <label className="text-xs font-semibold text-slate-600">New Other Allowance</label>
              <Input type="number" min={0} value={form.new_other_allowance}
                onChange={e => setForm({ ...form, new_other_allowance: Number(e.target.value) })} />
            </div>
            <div className="col-span-2">
              <label className="text-xs font-semibold text-slate-600">Reason</label>
              <textarea value={form.reason}
                onChange={e => setForm({ ...form, reason: e.target.value })}
                className="w-full border border-slate-200 rounded-md p-2 text-sm" rows={2} />
            </div>
            {pickedRating && pickedRating.final_rating != null && (
              <div className="col-span-2 p-2 bg-purple-50 border border-purple-200 rounded-lg text-xs flex items-center gap-2">
                <span className="font-semibold uppercase tracking-wide text-purple-700">
                  Latest rating (read-only)
                </span>
                <span className="text-lg font-bold text-purple-800">
                  {pickedRating.final_rating.toFixed(1)}
                </span>
                {pickedRating.cycle_name && (
                  <span className="text-slate-500">from {pickedRating.cycle_name}</span>
                )}
                <span className="ml-auto text-[10px] text-slate-400">
                  Rating is decision context — it does not auto-hike
                </span>
              </div>
            )}
            <div className="col-span-2 p-3 bg-blue-50 border border-blue-200 rounded-lg text-sm grid grid-cols-3 gap-3">
              <div>
                <div className="text-xs text-slate-500">Old CTC</div>
                <div className="font-bold">₹{(pickedEmp?.old_ctc || 0).toLocaleString('en-IN')}</div>
              </div>
              <div>
                <div className="text-xs text-slate-500">New CTC</div>
                <div className="font-bold">₹{newCtc.toLocaleString('en-IN')}</div>
              </div>
              <div>
                <div className="text-xs text-slate-500">Hike</div>
                <div className={cn('font-bold', newCtc > (pickedEmp?.old_ctc || 0) ? 'text-green-700' : 'text-red-700')}>
                  {hikePct}%
                </div>
              </div>
            </div>
            {liveBandWarning && (
              <div className="col-span-2 p-2 bg-amber-50 border border-amber-200 text-amber-800 text-xs rounded flex items-center gap-2">
                <AlertTriangle className="w-3 h-3" /> {liveBandWarning} (saved as warning — not blocked)
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateOpen(false)}>Cancel</Button>
            <Button variant="outline" isLoading={busy} onClick={() => submitRevision(false)}>
              Save draft
            </Button>
            <Button isLoading={busy} onClick={() => submitRevision(true)}>
              <Send className="w-3 h-3 mr-2" /> Save &amp; submit
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!reviewing} onOpenChange={(o: boolean) => { if (!o) setReviewing(null); }}>
        <DialogContent className="max-w-md">
          <DialogTitle>{action === 'approve' ? 'Approve' : 'Reject'} Revision</DialogTitle>
          {reviewing && (
            <div className="mt-4 space-y-2 text-sm">
              <div><span className="text-slate-500">Employee:</span> {reviewing.employee_full_name}</div>
              <div><span className="text-slate-500">Type:</span> {typeChip(reviewing.revision_type)}</div>
              <div><span className="text-slate-500">Effective:</span> {reviewing.effective_from}</div>
              <div>
                <span className="text-slate-500">CTC:</span>{' '}
                ₹{reviewing.old_ctc.toLocaleString('en-IN')} → ₹{reviewing.new_ctc.toLocaleString('en-IN')}{' '}
                <span className="font-bold">({reviewing.hike_percent.toFixed(2)}%)</span>
              </div>
              {reviewing.band_warning && (
                <div className="p-2 bg-amber-50 border border-amber-200 text-amber-800 rounded text-xs flex items-center gap-2">
                  <AlertTriangle className="w-3 h-3" /> {reviewing.band_warning}
                </div>
              )}
              {reviewing.revision_type === 'promotion' && (
                <div className="p-2 bg-purple-50 border border-purple-200 text-purple-800 rounded text-xs">
                  Promotion approval requires HR / CEO authority.
                </div>
              )}
              <div>
                <label className="text-xs font-semibold text-slate-600">
                  Comment {action === 'reject' ? '(recommended)' : '(optional)'}
                </label>
                <textarea value={comment} onChange={e => setComment(e.target.value)}
                  className="w-full border border-slate-200 rounded-md p-2 text-sm" rows={3} />
              </div>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setReviewing(null)}>Cancel</Button>
            <Button isLoading={busy} onClick={actOnReview}>
              {action === 'approve' ? 'Approve' : 'Reject'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};
