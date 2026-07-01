/**
 * Performance workspace: tabbed hub covering
 *   My Goals · My Review · Team Reviews · Cycles/Forms · Calibration · 1:1s
 *
 * Replaces the PerformanceTab.tsx stub. Each sub-view is a focused
 * component below; the workspace only handles tab routing.
 */
import React, { useEffect, useMemo, useState } from 'react';
import {
  Target, ClipboardCheck, Users, Layers, Sliders, MessageSquare,
  Plus, RefreshCw, Send, Play, CheckCircle2, AlertTriangle,
  ChevronRight, TrendingUp, TrendingDown, Award,
} from 'lucide-react';
import {
  Card, Button, Badge, cn, errMsg, EmptyState, Loading, StatusChip,
} from './ui-elements';
import { toast } from 'sonner';
import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';
import { Dialog, DialogContent, DialogTitle, DialogFooter } from './ui/dialog';
import { Input } from './ui/input';

const today = () => new Date().toISOString().slice(0, 10);

const ragTone = (rag?: string) => {
  if (rag === 'red') return 'bg-red-100 text-red-700 border-red-300';
  if (rag === 'amber') return 'bg-amber-100 text-amber-700 border-amber-300';
  if (rag === 'green') return 'bg-green-100 text-green-700 border-green-300';
  return 'bg-slate-100 text-slate-600 border-slate-300';
};

// ==============================================================
// Section M B2 — Live 1:1 employee picker.
// Loads the employee list once, filters client-side by name. Falls
// back to a plain user-id input if the fetch fails so a broken
// employees endpoint doesn't block scheduling a 1:1.
// ==============================================================

const EmployeePicker: React.FC<{
  selectedUserId?: number | null;
  onSelect: (userId: number) => void;
  placeholder?: string;
}> = ({ selectedUserId, onSelect, placeholder = 'Search by name…' }) => {
  const [employees, setEmployees] = useState<any[]>([]);
  const [q, setQ] = useState('');
  const [loadFailed, setLoadFailed] = useState(false);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const r = await client.get(ENDPOINTS.HR.EMPLOYEES_WITH_USER);
        setEmployees(r.data || []);
      } catch {
        setLoadFailed(true);
      }
    })();
  }, []);

  const selected = employees.find(
    (e: any) => (e.user_id ?? e.user?.id) === selectedUserId,
  );

  const filtered = q
    ? employees.filter((e: any) => {
        const name = String(
          e.user?.full_name || e.full_name || e.name || '',
        ).toLowerCase();
        const code = String(e.employee_id || '').toLowerCase();
        const dep = String(e.department || '').toLowerCase();
        const term = q.toLowerCase();
        return name.includes(term) || code.includes(term) || dep.includes(term);
      }).slice(0, 20)
    : employees.slice(0, 20);

  if (loadFailed) {
    return (
      <div>
        <Input
          type="number"
          value={selectedUserId || ''}
          onChange={e => onSelect(Number(e.target.value))}
          placeholder="User ID (picker unavailable)"
        />
        <div className="text-[10px] text-amber-700 mt-1">
          Employee list unavailable — enter the user id directly.
        </div>
      </div>
    );
  }

  return (
    <div className="relative">
      <Input
        value={
          open
            ? q
            : selected
              ? `${selected.user?.full_name || selected.full_name} · ${selected.employee_id}`
              : q
        }
        onChange={e => { setQ(e.target.value); setOpen(true); }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        placeholder={placeholder}
        aria-label="Employee picker"
      />
      {open && (
        <div className="absolute z-20 mt-1 w-full max-h-64 overflow-auto rounded-lg border border-slate-200 bg-white shadow-lg">
          {filtered.length === 0 ? (
            <div className="p-3 text-xs text-slate-400">No matches.</div>
          ) : (
            filtered.map((e: any) => {
              const uid = e.user_id ?? e.user?.id;
              const name = e.user?.full_name || e.full_name || 'Unnamed';
              return (
                <button
                  key={uid}
                  type="button"
                  onMouseDown={ev => ev.preventDefault()}
                  onClick={() => {
                    onSelect(uid);
                    setQ('');
                    setOpen(false);
                  }}
                  className="w-full text-left px-3 py-2 text-sm hover:bg-slate-50 border-b last:border-b-0"
                >
                  <div className="font-medium text-slate-700">{name}</div>
                  <div className="text-[11px] text-slate-500">
                    {e.employee_id}
                    {e.department ? ` · ${e.department}` : ''}
                  </div>
                </button>
              );
            })
          )}
        </div>
      )}
    </div>
  );
};

// ==============================================================
// TAB 1 — My Goals + Check-ins
// ==============================================================

const MyGoalsTab: React.FC = () => {
  const [goals, setGoals] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [warning, setWarning] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [form, setForm] = useState({
    title: '', description: '', goal_type: 'okr',
    weight: 0, target: '', unit: '',
    start_date: today(), due_date: today(),
  });
  const [checkInFor, setCheckInFor] = useState<any | null>(null);
  const [ciForm, setCiForm] = useState({
    progress_percent: 0, confidence: 'green', note: '',
  });
  const [busy, setBusy] = useState(false);

  const fetchAll = async () => {
    setLoading(true);
    try {
      const r = await client.get(ENDPOINTS.PERFORMANCE.MY_GOALS);
      setGoals(r.data || []);
      const w = (r.data || []).find((g: any) => g.weight_warning);
      setWarning(w?.weight_warning || null);
    } catch (e: any) { toast.error(errMsg(e, 'Failed to load goals')); }
    finally { setLoading(false); }
  };
  useEffect(() => { fetchAll(); }, []);

  const create = async () => {
    if (!form.title) { toast.error('Title required'); return; }
    setBusy(true);
    try {
      await client.post(ENDPOINTS.PERFORMANCE.GOALS, form);
      toast.success('Goal created');
      setCreateOpen(false); fetchAll();
    } catch (e: any) { toast.error(errMsg(e, 'Create failed')); }
    finally { setBusy(false); }
  };

  const activate = async (g: any) => {
    try {
      await client.patch(ENDPOINTS.PERFORMANCE.GOAL_DETAIL(g.id), { status: 'active' });
      fetchAll();
    } catch (e: any) { toast.error(errMsg(e, 'Failed')); }
  };

  const submitCheckIn = async () => {
    if (!checkInFor) return;
    setBusy(true);
    try {
      await client.post(ENDPOINTS.PERFORMANCE.CHECKINS(checkInFor.id), ciForm);
      toast.success('Check-in logged');
      setCheckInFor(null); setCiForm({ progress_percent: 0, confidence: 'green', note: '' });
      fetchAll();
    } catch (e: any) { toast.error(errMsg(e, 'Check-in failed')); }
    finally { setBusy(false); }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">My Goals</h2>
          <p className="text-xs text-slate-500 mt-1">
            Weight-sum warns at ±5pp — never blocks. Check-ins are a history, not a single number.
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={fetchAll}><RefreshCw className="w-4 h-4" /></Button>
          <Button onClick={() => setCreateOpen(true)}><Plus className="w-4 h-4 mr-2" /> New goal</Button>
        </div>
      </div>

      {warning && (
        <Card className="p-3 flex items-start gap-2 bg-amber-50 border-amber-200 text-amber-900 text-xs">
          <AlertTriangle className="w-4 h-4 mt-0.5 flex-shrink-0" /> {warning}
        </Card>
      )}

      {loading ? <div className="py-8 text-center text-slate-500">Loading…</div>
        : goals.length === 0 ? <Card className="p-12 text-center text-slate-500">
            No goals yet. Create one to start tracking objectives.
          </Card>
        : (
          <div className="space-y-3">
            {goals.map(g => (
              <Card key={g.id} className="p-4">
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold">{g.title}</span>
                      <Badge variant={g.status === 'at_risk' ? 'error' : g.status === 'completed' ? 'success' : 'info'}>
                        {g.status}
                      </Badge>
                      <span className="text-[10px] uppercase text-slate-400">{g.goal_type}</span>
                    </div>
                    {g.description && (
                      <p className="text-xs text-slate-600 mt-1">{g.description}</p>
                    )}
                    <div className="flex items-center gap-4 mt-2 text-xs text-slate-500">
                      <span>Due {g.due_date}</span>
                      <span>Weight {g.weight}%</span>
                      {g.target && <span>Target {g.target} {g.unit || ''}</span>}
                    </div>
                    <div className="mt-3 flex items-center gap-2">
                      <div className="flex-1 h-2 bg-slate-100 rounded overflow-hidden">
                        <div className={cn('h-full',
                          g.latest_progress >= 80 ? 'bg-green-500'
                            : g.latest_progress >= 40 ? 'bg-amber-500'
                              : 'bg-slate-400')}
                          style={{ width: `${Math.min(100, g.latest_progress || 0)}%` }} />
                      </div>
                      <span className="text-xs font-mono font-semibold">
                        {g.latest_progress?.toFixed(0) || 0}%
                      </span>
                      {g.latest_confidence && (
                        <span className={cn('px-2 py-0.5 rounded text-[10px] font-semibold uppercase border', ragTone(g.latest_confidence))}>
                          {g.latest_confidence}
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="flex flex-col gap-2 ml-4">
                    <Button size="sm" variant="outline"
                      onClick={() => { setCheckInFor(g); setCiForm({ progress_percent: g.latest_progress || 0, confidence: g.latest_confidence || 'green', note: '' }); }}>
                      Check-in
                    </Button>
                    {g.status === 'draft' && (
                      <Button size="sm" variant="outline" onClick={() => activate(g)}>
                        Activate
                      </Button>
                    )}
                  </div>
                </div>
              </Card>
            ))}
          </div>
        )}

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="max-w-lg">
          <DialogTitle>New goal</DialogTitle>
          <div className="space-y-3 mt-4">
            <div>
              <label className="text-xs font-semibold text-slate-600">Title</label>
              <Input value={form.title} onChange={e => setForm({ ...form, title: e.target.value })} />
            </div>
            <div>
              <label className="text-xs font-semibold text-slate-600">Description</label>
              <textarea value={form.description}
                onChange={e => setForm({ ...form, description: e.target.value })}
                className="w-full border border-slate-200 rounded-md p-2 text-sm" rows={2} />
            </div>
            <div className="grid grid-cols-3 gap-3">
              <div>
                <label className="text-xs font-semibold text-slate-600">Type</label>
                <select value={form.goal_type}
                  onChange={e => setForm({ ...form, goal_type: e.target.value })}
                  className="w-full border border-slate-200 rounded-md h-9 px-2 text-sm">
                  <option value="okr">OKR</option>
                  <option value="kra">KRA</option>
                  <option value="kpi">KPI</option>
                  <option value="project">Project</option>
                </select>
              </div>
              <div>
                <label className="text-xs font-semibold text-slate-600">Weight %</label>
                <Input type="number" min={0} max={100} value={form.weight}
                  onChange={e => setForm({ ...form, weight: Number(e.target.value) })} />
              </div>
              <div>
                <label className="text-xs font-semibold text-slate-600">Unit</label>
                <Input value={form.unit} onChange={e => setForm({ ...form, unit: e.target.value })} />
              </div>
              <div>
                <label className="text-xs font-semibold text-slate-600">Target</label>
                <Input value={form.target} onChange={e => setForm({ ...form, target: e.target.value })} />
              </div>
              <div>
                <label className="text-xs font-semibold text-slate-600">Start</label>
                <Input type="date" value={form.start_date}
                  onChange={e => setForm({ ...form, start_date: e.target.value })} />
              </div>
              <div>
                <label className="text-xs font-semibold text-slate-600">Due</label>
                <Input type="date" value={form.due_date}
                  onChange={e => setForm({ ...form, due_date: e.target.value })} />
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateOpen(false)}>Cancel</Button>
            <Button isLoading={busy} onClick={create}>Create</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!checkInFor} onOpenChange={(o: boolean) => { if (!o) setCheckInFor(null); }}>
        <DialogContent className="max-w-md">
          <DialogTitle>Check-in: {checkInFor?.title}</DialogTitle>
          <div className="space-y-3 mt-4">
            <div>
              <label className="text-xs font-semibold text-slate-600">Progress %</label>
              <Input type="number" min={0} max={100} value={ciForm.progress_percent}
                onChange={e => setCiForm({ ...ciForm, progress_percent: Number(e.target.value) })} />
            </div>
            <div>
              <label className="text-xs font-semibold text-slate-600">Confidence</label>
              <div className="flex gap-2 mt-1">
                {(['green', 'amber', 'red'] as const).map(c => (
                  <button key={c}
                    onClick={() => setCiForm({ ...ciForm, confidence: c })}
                    className={cn(
                      'px-4 py-1.5 rounded-md text-sm font-semibold uppercase border',
                      ciForm.confidence === c ? ragTone(c) : 'bg-white text-slate-400 border-slate-200',
                    )}>
                    {c}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <label className="text-xs font-semibold text-slate-600">Note</label>
              <textarea value={ciForm.note}
                onChange={e => setCiForm({ ...ciForm, note: e.target.value })}
                className="w-full border border-slate-200 rounded-md p-2 text-sm" rows={2} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCheckInFor(null)}>Cancel</Button>
            <Button isLoading={busy} onClick={submitCheckIn}>Log check-in</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

// ==============================================================
// TAB 2 — My Review
// ==============================================================

const MyReviewTab: React.FC = () => {
  const [review, setReview] = useState<any | null>(null);
  const [responses, setResponses] = useState<Record<number, any>>({});
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  const fetch = async () => {
    setLoading(true);
    try {
      const r = await client.get(ENDPOINTS.PERFORMANCE.MY_REVIEW);
      setReview(r.data);
      const map: Record<number, any> = {};
      for (const rp of r.data?.responses || []) {
        map[rp.question_id] = {
          self_rating: rp.self_rating,
          self_comment: rp.self_comment,
        };
      }
      setResponses(map);
    } catch (e: any) { toast.error(errMsg(e, 'Failed to load review')); }
    finally { setLoading(false); }
  };
  useEffect(() => { fetch(); }, []);

  const submit = async () => {
    if (!review?.instance) return;
    setBusy(true);
    try {
      const payload = {
        responses: Object.entries(responses).map(([qid, v]) => ({
          question_id: Number(qid),
          self_rating: (v as any).self_rating,
          self_comment: (v as any).self_comment,
        })),
      };
      await client.post(ENDPOINTS.PERFORMANCE.INSTANCE_SELF(review.instance.id), payload);
      toast.success('Self-review submitted');
      fetch();
    } catch (e: any) { toast.error(errMsg(e, 'Submit failed')); }
    finally { setBusy(false); }
  };

  if (loading) return <div className="py-8 text-center text-slate-500">Loading…</div>;
  if (!review?.instance) return (
    <Card className="p-12 text-center text-slate-500">
      No active review cycle. Your review will appear here when HR launches one.
    </Card>
  );

  const inst = review.instance;
  const cycle = review.cycle;
  const isReleased = inst.is_released;
  const canEdit = inst.current_phase === 'self' || inst.current_phase === 'not_started';

  return (
    <div className="space-y-4">
      <Card className="p-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold">{cycle?.name || 'Review'}</h2>
            <div className="text-xs text-slate-500 mt-1 flex items-center gap-2">
              <span>Phase: <span className="font-semibold">{inst.current_phase}</span></span>
              {isReleased ? <Badge variant="success">Released</Badge> : <Badge variant="info">In progress</Badge>}
            </div>
          </div>
          {isReleased && inst.final_rating != null && (
            <div className="text-right">
              <div className="text-[10px] uppercase text-slate-500">Final rating</div>
              <div className="text-3xl font-bold text-blue-700">{inst.final_rating.toFixed(1)}</div>
            </div>
          )}
        </div>
        {isReleased && inst.manager_override_reason && (
          <div className="mt-3 p-2 bg-purple-50 border border-purple-200 rounded text-xs">
            <span className="font-semibold">Manager note:</span> {inst.manager_override_reason}
          </div>
        )}
      </Card>

      {(review.sections || []).map((s: any) => (
        <Card key={s.id} className="p-4">
          <h3 className="font-semibold text-sm mb-3">{s.title} <span className="text-[10px] text-slate-400">(weight {s.weight}%)</span></h3>
          <div className="space-y-4">
            {(s.questions || []).map((q: any) => (
              <div key={q.id} className="border-b border-slate-100 pb-3">
                <div className="text-sm font-medium">{q.prompt}
                  {q.is_required && <span className="text-red-500 ml-1">*</span>}
                </div>
                {q.question_type === 'rating' ? (
                  <div className="mt-2 flex items-center gap-2">
                    {[1, 2, 3, 4, 5].map(v => (
                      <button key={v}
                        disabled={!canEdit}
                        onClick={() => setResponses({
                          ...responses,
                          [q.id]: { ...(responses[q.id] || {}), self_rating: v },
                        })}
                        className={cn(
                          'w-9 h-9 rounded-md border font-semibold',
                          responses[q.id]?.self_rating === v
                            ? 'bg-blue-600 text-white border-blue-600'
                            : 'bg-white text-slate-600 border-slate-200 hover:border-blue-400',
                          !canEdit && 'opacity-60 cursor-not-allowed',
                        )}>
                        {v}
                      </button>
                    ))}
                    {isReleased && (
                      <div className="ml-auto text-xs">
                        <span className="text-slate-500">Manager: </span>
                        <span className="font-semibold">
                          {(review.responses || []).find((r: any) => r.question_id === q.id)?.manager_rating ?? '—'}
                        </span>
                      </div>
                    )}
                  </div>
                ) : null}
                <textarea
                  disabled={!canEdit}
                  placeholder="Comment"
                  value={responses[q.id]?.self_comment || ''}
                  onChange={e => setResponses({
                    ...responses,
                    [q.id]: { ...(responses[q.id] || {}), self_comment: e.target.value },
                  })}
                  className="w-full mt-2 border border-slate-200 rounded-md p-2 text-sm disabled:bg-slate-50"
                  rows={2}
                />
                {isReleased && (review.responses || []).find((r: any) => r.question_id === q.id)?.manager_comment && (
                  <div className="mt-2 p-2 bg-blue-50 rounded text-xs">
                    <span className="font-semibold">Manager: </span>
                    {(review.responses || []).find((r: any) => r.question_id === q.id).manager_comment}
                  </div>
                )}
              </div>
            ))}
          </div>
        </Card>
      ))}

      {canEdit && (
        <div className="flex justify-end">
          <Button onClick={submit} isLoading={busy}>
            <Send className="w-4 h-4 mr-2" /> Submit self-review
          </Button>
        </div>
      )}
    </div>
  );
};

// ==============================================================
// TAB 3 — Team Reviews (Manager)
// ==============================================================

const TeamReviewsTab: React.FC = () => {
  const [rows, setRows] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [reviewing, setReviewing] = useState<any | null>(null);
  const [detail, setDetail] = useState<any | null>(null);
  const [mgrResponses, setMgrResponses] = useState<Record<number, any>>({});
  const [override, setOverride] = useState<{ value?: number; reason: string }>({ reason: '' });
  const [busy, setBusy] = useState(false);

  const fetch = async () => {
    setLoading(true);
    try {
      const r = await client.get(ENDPOINTS.PERFORMANCE.TEAM_REVIEWS);
      setRows(r.data || []);
    } catch (e: any) { toast.error(errMsg(e, 'Failed to load team')); }
    finally { setLoading(false); }
  };
  useEffect(() => { fetch(); }, []);

  const openReview = async (r: any) => {
    setReviewing(r);
    try {
      // Load the review shape by pulling the employee's my-review-shaped payload
      // via a small workaround: we call MY_REVIEW while acting on their behalf
      // isn't available here — HR endpoint would be cleaner. For now the
      // manager submits ratings against the same question IDs. In a hardened
      // release we'd expose GET /performance/instances/{id}. Placeholder:
      const empDetail = await client.get(ENDPOINTS.PERFORMANCE.MY_REVIEW, {
        params: { cycle_id: r.cycle_id },
        headers: { 'X-Impersonate-User': String(r.employee_id) },
      }).catch(() => null);
      setDetail(empDetail?.data || null);
    } catch (e: any) { /* silent — form still submittable */ }
  };

  const submitMgr = async () => {
    if (!reviewing) return;
    setBusy(true);
    try {
      const payload: any = {
        responses: Object.entries(mgrResponses).map(([qid, v]) => ({
          question_id: Number(qid),
          manager_rating: (v as any).manager_rating,
          manager_comment: (v as any).manager_comment,
        })),
      };
      if (override.value != null) {
        payload.manager_override_rating = override.value;
        payload.manager_override_reason = override.reason;
      }
      await client.post(ENDPOINTS.PERFORMANCE.INSTANCE_MGR(reviewing.id), payload);
      toast.success('Manager review submitted');
      setReviewing(null); setDetail(null); setMgrResponses({}); setOverride({ reason: '' });
      fetch();
    } catch (e: any) { toast.error(errMsg(e, 'Submit failed')); }
    finally { setBusy(false); }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">Team Reviews</h2>
          <p className="text-xs text-slate-500 mt-1">
            Your reportees, grouped by phase. Manager override requires a ≥10-char reason.
          </p>
        </div>
        <Button variant="outline" onClick={fetch}><RefreshCw className="w-4 h-4" /></Button>
      </div>

      {loading ? <div className="py-8 text-center text-slate-500">Loading…</div>
        : rows.length === 0 ? <Card className="p-12 text-center text-slate-500">No active team reviews.</Card>
        : (
          <Card className="p-0">
            <table className="min-w-full text-sm">
              <thead className="text-left text-xs uppercase text-slate-500 border-b bg-slate-50">
                <tr>
                  <th className="p-3">Employee</th>
                  <th className="p-3">Phase</th>
                  <th className="p-3">Self submitted</th>
                  <th className="p-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {rows.map(r => (
                  <tr key={r.id} className="border-b hover:bg-slate-50">
                    <td className="p-3 font-medium">{r.employee_name || `#${r.employee_id}`}</td>
                    <td className="p-3">
                      <Badge variant={r.current_phase === 'manager' ? 'warning' : 'info'}>
                        {r.current_phase}
                      </Badge>
                    </td>
                    <td className="p-3 text-xs">
                      {r.self_submitted_at ? new Date(r.self_submitted_at).toLocaleDateString() : '—'}
                    </td>
                    <td className="p-3 text-right">
                      {r.current_phase === 'manager' && (
                        <Button size="sm" onClick={() => openReview(r)}>
                          Review <ChevronRight className="w-3 h-3 ml-1" />
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        )}

      <Dialog open={!!reviewing} onOpenChange={(o: boolean) => { if (!o) { setReviewing(null); setDetail(null); } }}>
        <DialogContent className="max-w-2xl">
          <DialogTitle>Review — {reviewing?.employee_name}</DialogTitle>
          <div className="mt-4 max-h-[60vh] overflow-y-auto pr-1 space-y-4">
            {!detail ? (
              <div className="text-xs text-slate-500">
                Review form loading… If it doesn't appear you can still submit
                the overall override with a reason.
              </div>
            ) : (detail.sections || []).map((s: any) => (
              <div key={s.id}>
                <h3 className="font-semibold text-sm mb-2">
                  {s.title} <span className="text-[10px] text-slate-400">(weight {s.weight}%)</span>
                </h3>
                {(s.questions || []).map((q: any) => (
                  <div key={q.id} className="mb-3 border-b border-slate-100 pb-2">
                    <div className="text-sm">{q.prompt}</div>
                    <div className="mt-1 text-[10px] text-slate-500">
                      Self: {(detail.responses || []).find((r: any) => r.question_id === q.id)?.self_rating ?? '—'}
                      {' · '}
                      {(detail.responses || []).find((r: any) => r.question_id === q.id)?.self_comment}
                    </div>
                    {q.question_type === 'rating' && (
                      <div className="mt-2 flex items-center gap-2">
                        {[1, 2, 3, 4, 5].map(v => (
                          <button key={v}
                            onClick={() => setMgrResponses({
                              ...mgrResponses,
                              [q.id]: { ...(mgrResponses[q.id] || {}), manager_rating: v },
                            })}
                            className={cn(
                              'w-8 h-8 rounded-md border font-semibold text-sm',
                              mgrResponses[q.id]?.manager_rating === v
                                ? 'bg-blue-600 text-white border-blue-600'
                                : 'bg-white text-slate-600 border-slate-200',
                            )}>
                            {v}
                          </button>
                        ))}
                      </div>
                    )}
                    <Input
                      placeholder="Manager comment"
                      value={mgrResponses[q.id]?.manager_comment || ''}
                      onChange={e => setMgrResponses({
                        ...mgrResponses,
                        [q.id]: { ...(mgrResponses[q.id] || {}), manager_comment: e.target.value },
                      })}
                      className="mt-2"
                    />
                  </div>
                ))}
              </div>
            ))}

            <Card className="p-3 bg-slate-50">
              <div className="text-xs font-semibold uppercase text-slate-600 mb-2">Overall rating override (optional)</div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs text-slate-600">Override rating</label>
                  <Input type="number" min={0} max={5} step={0.1}
                    value={override.value ?? ''}
                    onChange={e => setOverride({
                      ...override,
                      value: e.target.value === '' ? undefined : Number(e.target.value),
                    })} />
                </div>
                <div>
                  <label className="text-xs text-slate-600">Reason (≥10 chars)</label>
                  <Input value={override.reason}
                    onChange={e => setOverride({ ...override, reason: e.target.value })} />
                </div>
              </div>
            </Card>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => { setReviewing(null); setDetail(null); }}>Cancel</Button>
            <Button isLoading={busy} onClick={submitMgr}>Submit review</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

// ==============================================================
// TAB 4 — Cycles Admin (HR)
// ==============================================================

const CyclesAdminTab: React.FC = () => {
  const [cycles, setCycles] = useState<any[]>([]);
  const [forms, setForms] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [createOpen, setCreateOpen] = useState(false);
  const [form, setForm] = useState({
    name: '', cycle_type: 'annual',
    start_date: today(), end_date: today(),
    departments: '',
  });
  const [assignFor, setAssignFor] = useState<any | null>(null);
  const [assignForm, setAssignForm] = useState({ form_id: 0, departments: '', priority: 0 });
  const [busy, setBusy] = useState(false);

  const fetch = async () => {
    setLoading(true);
    try {
      const [c, f] = await Promise.all([
        client.get(ENDPOINTS.PERFORMANCE.CYCLES),
        client.get(ENDPOINTS.PERFORMANCE.FORMS),
      ]);
      setCycles(c.data || []); setForms(f.data || []);
    } catch (e: any) { toast.error(errMsg(e, 'Failed to load')); }
    finally { setLoading(false); }
  };
  useEffect(() => { fetch(); }, []);

  const createCycle = async () => {
    if (!form.name) { toast.error('Name required'); return; }
    setBusy(true);
    try {
      const payload: any = {
        name: form.name, cycle_type: form.cycle_type,
        start_date: form.start_date, end_date: form.end_date,
        population_json: form.departments
          ? { departments: form.departments.split(',').map(s => s.trim()).filter(Boolean) }
          : { all: true },
      };
      await client.post(ENDPOINTS.PERFORMANCE.CYCLES, payload);
      toast.success('Cycle created');
      setCreateOpen(false); fetch();
    } catch (e: any) { toast.error(errMsg(e, 'Failed')); }
    finally { setBusy(false); }
  };

  const launch = async (c: any) => {
    if (!confirm(`Launch ${c.name}? This will create review instances for the entire population.`)) return;
    try {
      const r = await client.post(ENDPOINTS.PERFORMANCE.CYCLE_LAUNCH(c.id));
      toast.success(`Launched — ${r.data?.instances_created} instances`);
      fetch();
    } catch (e: any) { toast.error(errMsg(e, 'Launch failed')); }
  };

  const release = async (c: any) => {
    if (!confirm(`Release ${c.name}? Ratings become visible to employees.`)) return;
    try {
      await client.post(ENDPOINTS.PERFORMANCE.CYCLE_RELEASE(c.id));
      toast.success('Released');
      fetch();
    } catch (e: any) { toast.error(errMsg(e, 'Release failed')); }
  };

  const submitAssign = async () => {
    if (!assignFor || !assignForm.form_id) return;
    try {
      await client.post(ENDPOINTS.PERFORMANCE.CYCLE_ASSIGN(assignFor.id), {
        form_id: assignForm.form_id,
        filter_json: assignForm.departments
          ? { departments: assignForm.departments.split(',').map(s => s.trim()).filter(Boolean) }
          : {},
        priority: assignForm.priority,
      });
      toast.success('Template assigned'); setAssignFor(null); fetch();
    } catch (e: any) { toast.error(errMsg(e, 'Failed')); }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">Review Cycles</h2>
          <p className="text-xs text-slate-500 mt-1">
            Draft → Active (self+manager+calibration) → Released.
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={fetch}><RefreshCw className="w-4 h-4" /></Button>
          <Button onClick={() => setCreateOpen(true)}><Plus className="w-4 h-4 mr-2" /> New cycle</Button>
        </div>
      </div>

      {loading ? <div className="py-8 text-center text-slate-500">Loading…</div>
        : cycles.length === 0 ? <Card className="p-12 text-center text-slate-500">No cycles yet.</Card>
        : (
          <div className="space-y-3">
            {cycles.map(c => (
              <Card key={c.id} className="p-4">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-semibold">{c.name}</span>
                      <Badge variant={
                        c.status === 'released' ? 'success'
                          : c.status === 'active' ? 'info'
                            : c.status === 'draft' ? 'warning' : 'error'
                      }>{c.status}</Badge>
                    </div>
                    <div className="text-xs text-slate-500 mt-1">
                      {c.cycle_type} · {c.start_date} → {c.end_date}
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <Button size="sm" variant="outline" onClick={() => { setAssignFor(c); setAssignForm({ form_id: 0, departments: '', priority: 0 }); }}>
                      Assign form
                    </Button>
                    {c.status === 'draft' && (
                      <Button size="sm" onClick={() => launch(c)}>
                        <Play className="w-3 h-3 mr-1" /> Launch
                      </Button>
                    )}
                    {(c.status === 'active' || c.status === 'calibration') && (
                      <Button size="sm" variant="outline" onClick={() => release(c)}>
                        <CheckCircle2 className="w-3 h-3 mr-1" /> Release
                      </Button>
                    )}
                  </div>
                </div>
              </Card>
            ))}
          </div>
        )}

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="max-w-md">
          <DialogTitle>New cycle</DialogTitle>
          <div className="space-y-3 mt-4">
            <div>
              <label className="text-xs font-semibold text-slate-600">Name</label>
              <Input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} />
            </div>
            <div className="grid grid-cols-3 gap-3">
              <div>
                <label className="text-xs font-semibold text-slate-600">Type</label>
                <select value={form.cycle_type}
                  onChange={e => setForm({ ...form, cycle_type: e.target.value })}
                  className="w-full border border-slate-200 rounded-md h-9 px-2 text-sm">
                  <option value="annual">Annual</option>
                  <option value="half_yearly">Half-yearly</option>
                  <option value="quarterly">Quarterly</option>
                  <option value="probation">Probation</option>
                </select>
              </div>
              <div>
                <label className="text-xs font-semibold text-slate-600">Start</label>
                <Input type="date" value={form.start_date}
                  onChange={e => setForm({ ...form, start_date: e.target.value })} />
              </div>
              <div>
                <label className="text-xs font-semibold text-slate-600">End</label>
                <Input type="date" value={form.end_date}
                  onChange={e => setForm({ ...form, end_date: e.target.value })} />
              </div>
            </div>
            <div>
              <label className="text-xs font-semibold text-slate-600">Departments (comma-sep, blank = all)</label>
              <Input value={form.departments}
                onChange={e => setForm({ ...form, departments: e.target.value })} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateOpen(false)}>Cancel</Button>
            <Button isLoading={busy} onClick={createCycle}>Create</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!assignFor} onOpenChange={(o: boolean) => { if (!o) setAssignFor(null); }}>
        <DialogContent className="max-w-md">
          <DialogTitle>Assign form to {assignFor?.name}</DialogTitle>
          <div className="space-y-3 mt-4">
            <div>
              <label className="text-xs font-semibold text-slate-600">Form</label>
              <select value={assignForm.form_id || ''}
                onChange={e => setAssignForm({ ...assignForm, form_id: Number(e.target.value) })}
                className="w-full border border-slate-200 rounded-md h-9 px-2 text-sm">
                <option value="">— Select —</option>
                {forms.map(f => <option key={f.id} value={f.id}>{f.name}</option>)}
              </select>
            </div>
            <div>
              <label className="text-xs font-semibold text-slate-600">Restrict to departments (comma-sep, blank = all)</label>
              <Input value={assignForm.departments}
                onChange={e => setAssignForm({ ...assignForm, departments: e.target.value })} />
            </div>
            <div>
              <label className="text-xs font-semibold text-slate-600">Priority (higher wins first)</label>
              <Input type="number" value={assignForm.priority}
                onChange={e => setAssignForm({ ...assignForm, priority: Number(e.target.value) })} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setAssignFor(null)}>Cancel</Button>
            <Button onClick={submitAssign}>Assign</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

// ==============================================================
// TAB 5 — Calibration board
// ==============================================================

const CalibrationTab: React.FC = () => {
  const [cycles, setCycles] = useState<any[]>([]);
  const [session, setSession] = useState<any | null>(null);
  const [data, setData] = useState<any | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [form, setForm] = useState({ cycle_id: 0, department: '', name: '' });
  const [adjust, setAdjust] = useState<{ instance?: any; new_rating?: number; reason: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const fetchCycles = async () => {
    try {
      const r = await client.get(ENDPOINTS.PERFORMANCE.CYCLES);
      setCycles(r.data || []);
    } catch (e: any) { /* silent */ }
  };
  useEffect(() => { fetchCycles(); }, []);

  const startSession = async () => {
    if (!form.cycle_id) { toast.error('Pick a cycle'); return; }
    setBusy(true);
    try {
      const r = await client.post(ENDPOINTS.PERFORMANCE.CALIBRATION_SESSIONS, {
        cycle_id: form.cycle_id,
        department: form.department || null,
        name: form.name || null,
        target_curve_json: { "5": 0.10, "4": 0.30, "3": 0.40, "2": 0.15, "1": 0.05 },
      });
      setSession(r.data);
      setCreateOpen(false);
      const d = await client.get(ENDPOINTS.PERFORMANCE.CALIBRATION_DATA(r.data.id));
      setData(d.data);
    } catch (e: any) { toast.error(errMsg(e, 'Failed')); }
    finally { setBusy(false); }
  };

  const submitAdjust = async () => {
    if (!session || !adjust?.instance || adjust.new_rating == null || (adjust.reason || '').length < 10) {
      toast.error('Rating + reason (≥10 chars) required'); return;
    }
    try {
      await client.post(ENDPOINTS.PERFORMANCE.CALIBRATION_ADJUST(session.id), {
        instance_id: adjust.instance.instance_id,
        new_rating: adjust.new_rating, reason: adjust.reason,
      });
      toast.success('Adjusted');
      const d = await client.get(ENDPOINTS.PERFORMANCE.CALIBRATION_DATA(session.id));
      setData(d.data);
      setAdjust(null);
    } catch (e: any) { toast.error(errMsg(e, 'Adjust failed')); }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">Calibration</h2>
          <p className="text-xs text-slate-500 mt-1">
            Rating distribution vs target curve. Adjustments require a reason and are audit-logged.
          </p>
        </div>
        <Button onClick={() => setCreateOpen(true)}><Plus className="w-4 h-4 mr-2" /> Start session</Button>
      </div>

      {!session && (
        <Card className="p-12 text-center text-slate-500">
          Start a session for a cycle+department to see the distribution grid.
        </Card>
      )}

      {session && data && (
        <>
          <Card className="p-4">
            <div className="flex items-center justify-between mb-3">
              <div>
                <div className="font-semibold text-sm">{session.name || `Session #${session.id}`}</div>
                <div className="text-xs text-slate-500">
                  {session.department || 'All'} · cycle {session.cycle_id}
                </div>
              </div>
              <div className="text-xs">
                mean {data.distribution.mean} · stdev {data.distribution.stdev}
              </div>
            </div>
            <div className="grid grid-cols-5 gap-2">
              {(data.distribution.buckets || []).slice().reverse().map((b: any) => (
                <div key={b.label} className={cn(
                  'rounded-lg p-3 border-2',
                  b.is_skewed ? 'border-amber-400 bg-amber-50' : 'border-slate-200 bg-white',
                )}>
                  <div className="text-[10px] uppercase text-slate-500">Rating {b.label}</div>
                  <div className="text-2xl font-bold">{b.count}</div>
                  <div className="text-xs text-slate-600">{b.percent}%</div>
                  {b.target_percent != null && (
                    <div className="text-[10px] text-slate-400 mt-1">
                      target {b.target_percent}% ({b.skew_percent > 0 ? '+' : ''}{b.skew_percent}pp)
                    </div>
                  )}
                </div>
              ))}
            </div>
            {(data.distribution.skew_warnings || []).length > 0 && (
              <div className="mt-3 p-2 bg-amber-50 border border-amber-200 rounded text-xs text-amber-900">
                <AlertTriangle className="w-3 h-3 inline mr-1" />
                {data.distribution.skew_warnings.join(' · ')}
              </div>
            )}
          </Card>

          <Card className="p-0">
            <table className="min-w-full text-sm">
              <thead className="text-left text-xs uppercase text-slate-500 border-b bg-slate-50">
                <tr>
                  <th className="p-3">Employee</th>
                  <th className="p-3">Computed</th>
                  <th className="p-3">Manager override</th>
                  <th className="p-3">Calibrated</th>
                  <th className="p-3">Final</th>
                  <th className="p-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {(data.rows || []).map((r: any) => (
                  <tr key={r.instance_id} className="border-b">
                    <td className="p-3">
                      <div className="font-medium">{r.employee_name}</div>
                      <div className="text-[10px] text-slate-400">{r.department}</div>
                    </td>
                    <td className="p-3 font-mono">{r.computed_overall_rating?.toFixed(1) ?? '—'}</td>
                    <td className="p-3 font-mono">{r.manager_override_rating?.toFixed(1) ?? '—'}</td>
                    <td className="p-3 font-mono">{r.calibrated_rating?.toFixed(1) ?? '—'}</td>
                    <td className="p-3 font-bold">{r.final_rating?.toFixed(1) ?? '—'}</td>
                    <td className="p-3 text-right">
                      <Button size="sm" variant="outline"
                        onClick={() => setAdjust({ instance: r, new_rating: r.final_rating || undefined, reason: '' })}>
                        Adjust
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        </>
      )}

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="max-w-md">
          <DialogTitle>Start calibration session</DialogTitle>
          <div className="space-y-3 mt-4">
            <div>
              <label className="text-xs font-semibold text-slate-600">Cycle</label>
              <select value={form.cycle_id || ''}
                onChange={e => setForm({ ...form, cycle_id: Number(e.target.value) })}
                className="w-full border border-slate-200 rounded-md h-9 px-2 text-sm">
                <option value="">— Select —</option>
                {cycles.filter(c => c.status !== 'released').map(c =>
                  <option key={c.id} value={c.id}>{c.name} ({c.status})</option>)}
              </select>
            </div>
            <div>
              <label className="text-xs font-semibold text-slate-600">Department (blank = all)</label>
              <Input value={form.department}
                onChange={e => setForm({ ...form, department: e.target.value })} />
            </div>
            <div>
              <label className="text-xs font-semibold text-slate-600">Session name</label>
              <Input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateOpen(false)}>Cancel</Button>
            <Button isLoading={busy} onClick={startSession}>Start</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!adjust} onOpenChange={(o: boolean) => { if (!o) setAdjust(null); }}>
        <DialogContent className="max-w-md">
          <DialogTitle>Adjust rating — {adjust?.instance?.employee_name}</DialogTitle>
          <div className="space-y-3 mt-4">
            <div>
              <label className="text-xs font-semibold text-slate-600">New rating</label>
              <Input type="number" min={0} max={5} step={0.1}
                value={adjust?.new_rating ?? ''}
                onChange={e => setAdjust({
                  ...(adjust || { reason: '' }),
                  new_rating: e.target.value === '' ? undefined : Number(e.target.value),
                })} />
            </div>
            <div>
              <label className="text-xs font-semibold text-slate-600">Reason (min 10 chars)</label>
              <textarea value={adjust?.reason || ''}
                onChange={e => setAdjust({ ...(adjust || { reason: '' }), reason: e.target.value })}
                className="w-full border border-slate-200 rounded-md p-2 text-sm" rows={3} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setAdjust(null)}>Cancel</Button>
            <Button onClick={submitAdjust}>Adjust</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

// ==============================================================
// TAB 6 — 1:1 s
// ==============================================================

const OneOnOnesTab: React.FC = () => {
  const [meetings, setMeetings] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [current, setCurrent] = useState<any | null>(null);
  const [actions, setActions] = useState<any[]>([]);
  const [createOpen, setCreateOpen] = useState(false);
  const [form, setForm] = useState({
    reportee_id: 0, scheduled_at: new Date().toISOString().slice(0, 16),
    cadence: 'weekly', duration_minutes: 30,
  });
  const [newAction, setNewAction] = useState({ title: '', due_date: '' });
  const [busy, setBusy] = useState(false);

  const fetch = async () => {
    setLoading(true);
    try {
      const r = await client.get(ENDPOINTS.PERFORMANCE.ONE_ON_ONES);
      setMeetings(r.data || []);
    } catch (e: any) { toast.error(errMsg(e, 'Failed to load')); }
    finally { setLoading(false); }
  };
  useEffect(() => { fetch(); }, []);

  const openMeeting = async (m: any) => {
    setCurrent(m);
    try {
      const r = await client.get(ENDPOINTS.PERFORMANCE.ONE_ON_ONE_ACTIONS(m.id));
      setActions(r.data || []);
    } catch { setActions([]); }
  };

  const createMeeting = async () => {
    if (!form.reportee_id) { toast.error('Reportee ID required'); return; }
    setBusy(true);
    try {
      await client.post(ENDPOINTS.PERFORMANCE.ONE_ON_ONES, {
        reportee_id: form.reportee_id,
        scheduled_at: form.scheduled_at + ':00',
        cadence: form.cadence,
        duration_minutes: form.duration_minutes,
      });
      toast.success('Scheduled');
      setCreateOpen(false); fetch();
    } catch (e: any) { toast.error(errMsg(e, 'Failed')); }
    finally { setBusy(false); }
  };

  const addAction = async () => {
    if (!current || !newAction.title) return;
    try {
      await client.post(ENDPOINTS.PERFORMANCE.ONE_ON_ONE_ACTIONS(current.id), {
        title: newAction.title,
        due_date: newAction.due_date || undefined,
      });
      setNewAction({ title: '', due_date: '' });
      const r = await client.get(ENDPOINTS.PERFORMANCE.ONE_ON_ONE_ACTIONS(current.id));
      setActions(r.data || []);
    } catch (e: any) { toast.error(errMsg(e, 'Failed')); }
  };

  const toggleActionDone = async (a: any) => {
    try {
      const next = a.status === 'done' ? 'open' : 'done';
      await client.patch(ENDPOINTS.PERFORMANCE.ACTION_ITEM(a.id), { status: next });
      const r = await client.get(ENDPOINTS.PERFORMANCE.ONE_ON_ONE_ACTIONS(current!.id));
      setActions(r.data || []);
    } catch (e: any) { toast.error(errMsg(e, 'Failed')); }
  };

  const openActions = useMemo(
    () => actions.filter(a => a.status !== 'done' && a.status !== 'cancelled'),
    [actions],
  );

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">1:1 Meetings</h2>
          <p className="text-xs text-slate-500 mt-1">
            Action items surface for both parties until closed. Optionally link items to goals.
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={fetch}><RefreshCw className="w-4 h-4" /></Button>
          <Button onClick={() => setCreateOpen(true)}><Plus className="w-4 h-4 mr-2" /> Schedule</Button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card className="p-4 md:col-span-1 max-h-[70vh] overflow-y-auto">
          <h3 className="font-semibold text-sm mb-2">Meetings</h3>
          {loading ? <div className="text-xs text-slate-500 py-4">Loading…</div>
            : meetings.length === 0 ? <div className="text-xs text-slate-500 py-4">None yet.</div>
            : meetings.map(m => (
              <button key={m.id} onClick={() => openMeeting(m)}
                className={cn(
                  'w-full text-left border rounded-md p-2 mb-2 hover:border-blue-400',
                  current?.id === m.id ? 'border-blue-500 bg-blue-50' : 'border-slate-200',
                )}>
                <div className="text-xs font-semibold">
                  {new Date(m.scheduled_at).toLocaleString()}
                </div>
                <div className="text-[10px] text-slate-500">
                  {m.cadence} · {m.duration_minutes}min
                </div>
                <div className="text-[10px] text-slate-500">status: {m.status}</div>
              </button>
            ))}
        </Card>

        <Card className="p-4 md:col-span-2">
          {current ? (
            <div className="space-y-3">
              <div>
                <div className="text-xs text-slate-500">
                  Scheduled {new Date(current.scheduled_at).toLocaleString()} · {current.cadence}
                </div>
              </div>
              <div>
                <h3 className="font-semibold text-sm mb-2">Shared notes</h3>
                <textarea defaultValue={current.shared_notes || ''}
                  onBlur={async e => {
                    try {
                      await client.patch(ENDPOINTS.PERFORMANCE.ONE_ON_ONE_DETAIL(current.id), {
                        shared_notes: e.target.value,
                      });
                    } catch { /* silent */ }
                  }}
                  className="w-full border border-slate-200 rounded-md p-2 text-sm"
                  rows={4} />
              </div>
              <div>
                <h3 className="font-semibold text-sm mb-2">
                  Action items ({openActions.length} open)
                </h3>
                <div className="flex gap-2 mb-2">
                  <Input placeholder="New action…" value={newAction.title}
                    onChange={e => setNewAction({ ...newAction, title: e.target.value })} />
                  <Input type="date" value={newAction.due_date}
                    onChange={e => setNewAction({ ...newAction, due_date: e.target.value })} />
                  <Button onClick={addAction}><Plus className="w-4 h-4" /></Button>
                </div>
                <div className="space-y-1">
                  {actions.map(a => (
                    <div key={a.id} className="flex items-center gap-2 border-b border-slate-100 py-1">
                      <input type="checkbox"
                        checked={a.status === 'done'}
                        onChange={() => toggleActionDone(a)} />
                      <span className={cn('flex-1 text-sm',
                        a.status === 'done' && 'line-through text-slate-400')}>
                        {a.title}
                      </span>
                      {a.due_date && <span className="text-[10px] text-slate-500">due {a.due_date}</span>}
                    </div>
                  ))}
                  {actions.length === 0 && (
                    <div className="text-xs text-slate-500 py-2">No action items.</div>
                  )}
                </div>
              </div>
            </div>
          ) : (
            <div className="text-center text-slate-500 py-16 text-sm">
              Pick a meeting from the left, or schedule a new one.
            </div>
          )}
        </Card>
      </div>

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="max-w-md">
          <DialogTitle>Schedule 1:1</DialogTitle>
          <div className="space-y-3 mt-4">
            <div>
              <label className="text-xs font-semibold text-slate-600">Reportee</label>
              <EmployeePicker
                selectedUserId={form.reportee_id}
                onSelect={(uid: number) => setForm({ ...form, reportee_id: uid })}
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs font-semibold text-slate-600">When</label>
                <Input type="datetime-local" value={form.scheduled_at}
                  onChange={e => setForm({ ...form, scheduled_at: e.target.value })} />
              </div>
              <div>
                <label className="text-xs font-semibold text-slate-600">Cadence</label>
                <select value={form.cadence}
                  onChange={e => setForm({ ...form, cadence: e.target.value })}
                  className="w-full border border-slate-200 rounded-md h-9 px-2 text-sm">
                  <option value="once">Once</option>
                  <option value="weekly">Weekly</option>
                  <option value="biweekly">Bi-weekly</option>
                  <option value="monthly">Monthly</option>
                </select>
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateOpen(false)}>Cancel</Button>
            <Button isLoading={busy} onClick={createMeeting}>Schedule</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

// ==============================================================
// Workspace shell
// ==============================================================

export const PerformanceWorkspace: React.FC = () => {
  const [tab, setTab] = useState<'goals' | 'my-review' | 'team' | 'cycles' | 'calibration' | '1:1'>('goals');
  const tabs: { key: typeof tab; label: string; icon: any }[] = [
    { key: 'goals', label: 'My Goals', icon: Target },
    { key: 'my-review', label: 'My Review', icon: ClipboardCheck },
    { key: 'team', label: 'Team Reviews', icon: Users },
    { key: 'cycles', label: 'Cycles', icon: Layers },
    { key: 'calibration', label: 'Calibration', icon: Sliders },
    { key: '1:1', label: '1:1s', icon: MessageSquare },
  ];

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Award className="w-6 h-6 text-blue-600" /> Performance Management
        </h1>
        <p className="text-sm text-slate-500 mt-1">
          Goals, reviews, calibration, and 1:1s in one place. Ratings feed the revision workspace read-only.
        </p>
      </div>

      <div className="flex items-center gap-2 flex-wrap border-b border-slate-200">
        {tabs.map(t => {
          const Icon = t.icon;
          return (
            <button key={t.key} onClick={() => setTab(t.key)}
              className={cn(
                'px-4 py-2 text-sm font-medium flex items-center gap-2 border-b-2 -mb-px',
                tab === t.key
                  ? 'border-blue-600 text-blue-700'
                  : 'border-transparent text-slate-600 hover:text-slate-900',
              )}>
              <Icon className="w-4 h-4" /> {t.label}
            </button>
          );
        })}
      </div>

      {tab === 'goals' && <MyGoalsTab />}
      {tab === 'my-review' && <MyReviewTab />}
      {tab === 'team' && <TeamReviewsTab />}
      {tab === 'cycles' && <CyclesAdminTab />}
      {tab === 'calibration' && <CalibrationTab />}
      {tab === '1:1' && <OneOnOnesTab />}
    </div>
  );
};
