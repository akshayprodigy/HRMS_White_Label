import React, { useEffect, useMemo, useState } from 'react';
import {
  Plus, Edit2, Power, Search, RefreshCw, Layers, AlertCircle,
} from 'lucide-react';
import { Card, Button, Badge, cn } from './ui-elements';
import { toast } from 'sonner';
import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';
import { Dialog, DialogContent, DialogTitle, DialogFooter } from './ui/dialog';
import { Input } from './ui/input';

interface Grade {
  id: number; name: string; rank: number;
  min_salary: number | null; max_salary: number | null;
  is_active: boolean;
}
interface Designation {
  id: number; title: string; grade_id: number | null;
  grade_name: string | null; is_active: boolean;
}
interface Unmatched {
  employee_id: string; user_id: number; name: string | null;
  department: string; designation_text: string;
}

const errMsg = (err: any, fallback: string): string => {
  const detail = err?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail))
    return detail.map((d: any) => d?.msg || JSON.stringify(d)).join('; ');
  return err?.message || fallback;
};

export const DesignationGradeAdmin: React.FC = () => {
  const [tab, setTab] = useState<'designations' | 'grades' | 'cleanup'>('designations');
  const [grades, setGrades] = useState<Grade[]>([]);
  const [desigs, setDesigs] = useState<Designation[]>([]);
  const [unmatched, setUnmatched] = useState<Unmatched[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');

  // modals
  const [gradeModal, setGradeModal] = useState(false);
  const [editingGrade, setEditingGrade] = useState<Grade | null>(null);
  const [gradeForm, setGradeForm] = useState({
    name: '', rank: 0, min_salary: '' as number | '', max_salary: '' as number | '', is_active: true,
  });
  const [desigModal, setDesigModal] = useState(false);
  const [editingDesig, setEditingDesig] = useState<Designation | null>(null);
  const [desigForm, setDesigForm] = useState({
    title: '', grade_id: null as number | null, is_active: true,
  });
  const [submitting, setSubmitting] = useState(false);

  const fetchAll = async () => {
    setLoading(true);
    try {
      const [g, d, u] = await Promise.all([
        client.get(ENDPOINTS.REVISIONS.GRADES, { params: { include_inactive: true } }),
        client.get(ENDPOINTS.REVISIONS.DESIGNATIONS, { params: { include_inactive: true } }),
        client.get(ENDPOINTS.REVISIONS.UNMATCHED).catch(() => ({ data: [] })),
      ]);
      setGrades(g.data || []); setDesigs(d.data || []); setUnmatched(u.data || []);
    } catch (e: any) {
      toast.error(errMsg(e, 'Failed to load'));
    } finally { setLoading(false); }
  };

  useEffect(() => { fetchAll(); }, []);

  const filteredDesigs = useMemo(() => {
    const q = search.trim().toLowerCase();
    return desigs.filter(d =>
      !q || d.title.toLowerCase().includes(q) || (d.grade_name || '').toLowerCase().includes(q)
    );
  }, [desigs, search]);
  const filteredGrades = useMemo(() => {
    const q = search.trim().toLowerCase();
    return grades.filter(g => !q || g.name.toLowerCase().includes(q));
  }, [grades, search]);
  const filteredUnmatched = useMemo(() => {
    const q = search.trim().toLowerCase();
    return unmatched.filter(u =>
      !q || (u.name || '').toLowerCase().includes(q)
      || u.designation_text.toLowerCase().includes(q)
    );
  }, [unmatched, search]);

  // Grade actions
  const openCreateGrade = () => {
    setEditingGrade(null);
    setGradeForm({ name: '', rank: 0, min_salary: '', max_salary: '', is_active: true });
    setGradeModal(true);
  };
  const openEditGrade = (g: Grade) => {
    setEditingGrade(g);
    setGradeForm({
      name: g.name, rank: g.rank,
      min_salary: g.min_salary ?? '', max_salary: g.max_salary ?? '',
      is_active: g.is_active,
    });
    setGradeModal(true);
  };
  const submitGrade = async () => {
    setSubmitting(true);
    try {
      const payload = {
        name: gradeForm.name, rank: Number(gradeForm.rank),
        min_salary: gradeForm.min_salary === '' ? null : Number(gradeForm.min_salary),
        max_salary: gradeForm.max_salary === '' ? null : Number(gradeForm.max_salary),
        is_active: gradeForm.is_active,
      };
      if (editingGrade) {
        await client.patch(ENDPOINTS.REVISIONS.GRADE_DETAIL(editingGrade.id), payload);
      } else {
        await client.post(ENDPOINTS.REVISIONS.GRADES, payload);
      }
      toast.success('Saved'); setGradeModal(false); fetchAll();
    } catch (e: any) { toast.error(errMsg(e, 'Failed')); }
    finally { setSubmitting(false); }
  };
  const toggleGrade = async (g: Grade) => {
    try {
      if (g.is_active) await client.delete(ENDPOINTS.REVISIONS.GRADE_DETAIL(g.id));
      else await client.patch(ENDPOINTS.REVISIONS.GRADE_DETAIL(g.id), { is_active: true });
      fetchAll();
    } catch (e: any) { toast.error(errMsg(e, 'Failed')); }
  };

  // Designation actions
  const openCreateDesig = () => {
    setEditingDesig(null);
    setDesigForm({ title: '', grade_id: null, is_active: true });
    setDesigModal(true);
  };
  const openEditDesig = (d: Designation) => {
    setEditingDesig(d);
    setDesigForm({ title: d.title, grade_id: d.grade_id, is_active: d.is_active });
    setDesigModal(true);
  };
  const submitDesig = async () => {
    setSubmitting(true);
    try {
      if (editingDesig) {
        await client.patch(ENDPOINTS.REVISIONS.DESIGNATION_DETAIL(editingDesig.id), desigForm);
      } else {
        await client.post(ENDPOINTS.REVISIONS.DESIGNATIONS, desigForm);
      }
      toast.success('Saved'); setDesigModal(false); fetchAll();
    } catch (e: any) { toast.error(errMsg(e, 'Failed')); }
    finally { setSubmitting(false); }
  };
  const toggleDesig = async (d: Designation) => {
    try {
      if (d.is_active) await client.delete(ENDPOINTS.REVISIONS.DESIGNATION_DETAIL(d.id));
      else await client.patch(ENDPOINTS.REVISIONS.DESIGNATION_DETAIL(d.id), { is_active: true });
      fetchAll();
    } catch (e: any) { toast.error(errMsg(e, 'Failed')); }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Layers className="w-6 h-6 text-blue-600" /> Designations &amp; Grades
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Master of titles + salary bands. Free-text legacy values are migrated; unmatched flagged for cleanup.
          </p>
        </div>
        <div className="flex gap-2">
          {tab === 'designations' && (
            <Button onClick={openCreateDesig}><Plus className="w-4 h-4 mr-2" /> New Designation</Button>
          )}
          {tab === 'grades' && (
            <Button onClick={openCreateGrade}><Plus className="w-4 h-4 mr-2" /> New Grade</Button>
          )}
        </div>
      </div>

      <Card className="p-4">
        <div className="flex items-center gap-3 mb-3">
          {(['designations', 'grades', 'cleanup'] as const).map(t => (
            <button key={t}
              onClick={() => setTab(t)}
              className={cn(
                'px-3 py-1.5 text-sm rounded-md font-medium',
                tab === t ? 'bg-blue-600 text-white' : 'bg-slate-100 text-slate-700',
              )}>
              {t === 'cleanup'
                ? <>Cleanup {unmatched.length > 0 && <span className="ml-1 bg-red-500 text-white text-[10px] px-1.5 rounded-full">{unmatched.length}</span>}</>
                : t.charAt(0).toUpperCase() + t.slice(1)}
            </button>
          ))}
          <div className="relative flex-1 max-w-sm ml-auto">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <Input placeholder="Search…" value={search}
              onChange={e => setSearch(e.target.value)} className="pl-9" />
          </div>
          <Button variant="outline" onClick={fetchAll}><RefreshCw className="w-4 h-4" /></Button>
        </div>

        {loading ? (
          <div className="py-8 text-center text-slate-500">Loading…</div>
        ) : tab === 'designations' ? (
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead className="text-left text-xs uppercase text-slate-500 border-b">
                <tr>
                  <th className="p-3">Title</th>
                  <th className="p-3">Grade</th>
                  <th className="p-3">Status</th>
                  <th className="p-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredDesigs.map(d => (
                  <tr key={d.id} className="border-b hover:bg-slate-50">
                    <td className="p-3 font-medium">{d.title}</td>
                    <td className="p-3">{d.grade_name || '—'}</td>
                    <td className="p-3">
                      <Badge variant={d.is_active ? 'success' : 'error'}>
                        {d.is_active ? 'Active' : 'Inactive'}
                      </Badge>
                    </td>
                    <td className="p-3 text-right space-x-1">
                      <Button size="sm" variant="outline" onClick={() => openEditDesig(d)}>
                        <Edit2 className="w-3 h-3" />
                      </Button>
                      <Button size="sm" variant="outline" onClick={() => toggleDesig(d)}>
                        <Power className={cn('w-3 h-3',
                          d.is_active ? 'text-red-600' : 'text-green-600')} />
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : tab === 'grades' ? (
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead className="text-left text-xs uppercase text-slate-500 border-b">
                <tr>
                  <th className="p-3">Name</th>
                  <th className="p-3">Rank</th>
                  <th className="p-3">Band</th>
                  <th className="p-3">Status</th>
                  <th className="p-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredGrades.map(g => (
                  <tr key={g.id} className="border-b hover:bg-slate-50">
                    <td className="p-3 font-medium">{g.name}</td>
                    <td className="p-3">{g.rank}</td>
                    <td className="p-3 text-xs">
                      {g.min_salary != null || g.max_salary != null
                        ? <>₹{(g.min_salary ?? 0).toLocaleString('en-IN')} – ₹{(g.max_salary ?? 0).toLocaleString('en-IN')}</>
                        : <span className="text-slate-400">No band</span>}
                    </td>
                    <td className="p-3">
                      <Badge variant={g.is_active ? 'success' : 'error'}>
                        {g.is_active ? 'Active' : 'Inactive'}
                      </Badge>
                    </td>
                    <td className="p-3 text-right space-x-1">
                      <Button size="sm" variant="outline" onClick={() => openEditGrade(g)}>
                        <Edit2 className="w-3 h-3" />
                      </Button>
                      <Button size="sm" variant="outline" onClick={() => toggleGrade(g)}>
                        <Power className={cn('w-3 h-3',
                          g.is_active ? 'text-red-600' : 'text-green-600')} />
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div>
            {filteredUnmatched.length === 0 ? (
              <div className="py-8 text-center text-slate-500">No unmatched designations — all employees mapped.</div>
            ) : (
              <>
                <div className="mb-3 p-3 bg-amber-50 border border-amber-200 rounded-lg text-sm flex items-start gap-2">
                  <AlertCircle className="w-4 h-4 text-amber-600 mt-0.5 flex-shrink-0" />
                  <span>
                    These employees have a legacy designation string that no master row matches. Create the matching designation, then re-edit the employee's designation in the directory to wire the FK.
                  </span>
                </div>
                <table className="min-w-full text-sm">
                  <thead className="text-left text-xs uppercase text-slate-500 border-b">
                    <tr>
                      <th className="p-3">Employee</th>
                      <th className="p-3">Code</th>
                      <th className="p-3">Department</th>
                      <th className="p-3">Designation (text)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredUnmatched.map(u => (
                      <tr key={u.user_id} className="border-b">
                        <td className="p-3 font-medium">{u.name || `#${u.user_id}`}</td>
                        <td className="p-3 text-xs">{u.employee_id}</td>
                        <td className="p-3 text-xs">{u.department}</td>
                        <td className="p-3 text-xs text-red-600">{u.designation_text}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </>
            )}
          </div>
        )}
      </Card>

      <Dialog open={gradeModal} onOpenChange={setGradeModal}>
        <DialogContent className="max-w-md">
          <DialogTitle>{editingGrade ? 'Edit' : 'New'} Grade</DialogTitle>
          <div className="space-y-3 mt-4">
            <div>
              <label className="text-xs font-semibold text-slate-600">Name</label>
              <Input value={gradeForm.name}
                onChange={e => setGradeForm({ ...gradeForm, name: e.target.value })} />
            </div>
            <div>
              <label className="text-xs font-semibold text-slate-600">Rank (low → high)</label>
              <Input type="number" min={0} value={gradeForm.rank}
                onChange={e => setGradeForm({ ...gradeForm, rank: Number(e.target.value) })} />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs font-semibold text-slate-600">Band min (₹)</label>
                <Input type="number" min={0} value={gradeForm.min_salary}
                  onChange={e => setGradeForm({ ...gradeForm, min_salary: e.target.value === '' ? '' : Number(e.target.value) })} />
              </div>
              <div>
                <label className="text-xs font-semibold text-slate-600">Band max (₹)</label>
                <Input type="number" min={0} value={gradeForm.max_salary}
                  onChange={e => setGradeForm({ ...gradeForm, max_salary: e.target.value === '' ? '' : Number(e.target.value) })} />
              </div>
            </div>
            <label className="text-sm flex items-center gap-2">
              <input type="checkbox" checked={gradeForm.is_active}
                onChange={e => setGradeForm({ ...gradeForm, is_active: e.target.checked })} />
              Active
            </label>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setGradeModal(false)}>Cancel</Button>
            <Button isLoading={submitting} onClick={submitGrade}>Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={desigModal} onOpenChange={setDesigModal}>
        <DialogContent className="max-w-md">
          <DialogTitle>{editingDesig ? 'Edit' : 'New'} Designation</DialogTitle>
          <div className="space-y-3 mt-4">
            <div>
              <label className="text-xs font-semibold text-slate-600">Title</label>
              <Input value={desigForm.title}
                onChange={e => setDesigForm({ ...desigForm, title: e.target.value })} />
            </div>
            <div>
              <label className="text-xs font-semibold text-slate-600">Grade (optional)</label>
              <select value={desigForm.grade_id ?? ''}
                onChange={e => setDesigForm({ ...desigForm, grade_id: e.target.value ? Number(e.target.value) : null })}
                className="w-full border border-slate-200 rounded-md h-9 px-2 text-sm">
                <option value="">— None —</option>
                {grades.filter(g => g.is_active).map(g =>
                  <option key={g.id} value={g.id}>{g.name}</option>
                )}
              </select>
            </div>
            <label className="text-sm flex items-center gap-2">
              <input type="checkbox" checked={desigForm.is_active}
                onChange={e => setDesigForm({ ...desigForm, is_active: e.target.checked })} />
              Active
            </label>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDesigModal(false)}>Cancel</Button>
            <Button isLoading={submitting} onClick={submitDesig}>Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};
