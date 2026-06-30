import React, { useEffect, useMemo, useState } from 'react';
import {
  Plus,
  Trash2,
  Search,
  RefreshCw,
  Users,
  Calendar,
  Building2,
} from 'lucide-react';
import { Card, Button, Badge, cn } from './ui-elements';
import { toast } from 'sonner@2.0.3';
import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';
import { Dialog, DialogContent, DialogTitle, DialogFooter } from './ui/dialog';
import { Input } from './ui/input';
import { AssignShiftDialog } from './assign-shift-dialog';

interface Assignment {
  id: number;
  employee_id: number;
  shift_template_id: number;
  effective_from: string;
  effective_to: string | null;
  note: string | null;
  assigned_by_id: number | null;
  created_at: string;
  updated_at: string;
  employee_name?: string | null;
  employee_email?: string | null;
  employee_department?: string | null;
  shift_template_name?: string | null;
}

interface ShiftTemplate {
  id: number;
  name: string;
  is_active: boolean;
}

const errMsg = (err: any, fallback: string): string => {
  const detail = err?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail))
    return detail.map((d: any) => d?.msg || JSON.stringify(d)).join('; ');
  return err?.message || fallback;
};

const todayISO = () => new Date().toISOString().slice(0, 10);

export const EmployeeShiftAssignmentsView: React.FC = () => {
  const [items, setItems] = useState<Assignment[]>([]);
  const [templates, setTemplates] = useState<ShiftTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [templateFilter, setTemplateFilter] = useState<number | ''>('');
  const [departmentFilter, setDepartmentFilter] = useState('');
  const [onlyOngoing, setOnlyOngoing] = useState(true);
  const [asOfDate, setAsOfDate] = useState<string>('');

  const [singleAssignOpen, setSingleAssignOpen] = useState(false);
  const [singleAssignEmployeeId, setSingleAssignEmployeeId] = useState<
    number | null
  >(null);
  const [singleAssignEmployeeName, setSingleAssignEmployeeName] = useState<
    string | undefined
  >(undefined);

  const [bulkOpen, setBulkOpen] = useState(false);
  const [bulkSubmitting, setBulkSubmitting] = useState(false);
  const [bulkResult, setBulkResult] = useState<{
    assigned: number;
    skipped: number;
    failed: number;
    errors: string[];
  } | null>(null);
  const [bulkForm, setBulkForm] = useState({
    mode: 'department' as 'department' | 'employee_ids',
    department: '',
    employee_ids: '',
    shift_template_id: '' as number | '',
    effective_from: todayISO(),
    effective_to: '',
    note: '',
  });

  const [deleteTarget, setDeleteTarget] = useState<Assignment | null>(null);

  const fetchItems = async () => {
    setLoading(true);
    try {
      const params: any = { include_ended: !onlyOngoing };
      if (templateFilter) params.shift_template_id = templateFilter;
      if (departmentFilter) params.department = departmentFilter;
      if (asOfDate) params.as_of_date = asOfDate;
      const res = await client.get(ENDPOINTS.SHIFTS.ASSIGNMENTS, { params });
      setItems(res.data || []);
    } catch (e: any) {
      toast.error(errMsg(e, 'Failed to load assignments'));
    } finally {
      setLoading(false);
    }
  };

  const fetchTemplates = async () => {
    try {
      const res = await client.get(ENDPOINTS.SHIFTS.TEMPLATES);
      setTemplates(res.data || []);
    } catch {
      /* non-fatal: filter still works without */
    }
  };

  useEffect(() => {
    fetchTemplates();
  }, []);

  useEffect(() => {
    fetchItems();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [templateFilter, departmentFilter, onlyOngoing, asOfDate]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return items;
    return items.filter(
      (a) =>
        (a.employee_name || '').toLowerCase().includes(q) ||
        (a.employee_email || '').toLowerCase().includes(q) ||
        (a.employee_department || '').toLowerCase().includes(q) ||
        (a.shift_template_name || '').toLowerCase().includes(q),
    );
  }, [items, search]);

  const openSingleAssign = (employeeId: number, name?: string) => {
    setSingleAssignEmployeeId(employeeId);
    setSingleAssignEmployeeName(name);
    setSingleAssignOpen(true);
  };

  const openBulk = () => {
    setBulkResult(null);
    setBulkForm({
      mode: 'department',
      department: '',
      employee_ids: '',
      shift_template_id: '',
      effective_from: todayISO(),
      effective_to: '',
      note: '',
    });
    setBulkOpen(true);
  };

  const submitBulk = async () => {
    if (!bulkForm.shift_template_id) {
      toast.error('Pick a shift template');
      return;
    }
    if (!bulkForm.effective_from) {
      toast.error('Effective From is required');
      return;
    }
    const payload: any = {
      shift_template_id: bulkForm.shift_template_id,
      effective_from: bulkForm.effective_from,
      effective_to: bulkForm.effective_to || null,
      note: bulkForm.note || null,
    };
    if (bulkForm.mode === 'department') {
      if (!bulkForm.department.trim()) {
        toast.error('Department is required');
        return;
      }
      payload.department = bulkForm.department.trim();
    } else {
      const ids = bulkForm.employee_ids
        .split(/[,\s]+/)
        .map((s) => s.trim())
        .filter(Boolean)
        .map((s) => Number(s))
        .filter((n) => Number.isFinite(n) && n > 0);
      if (ids.length === 0) {
        toast.error('Provide at least one employee user ID');
        return;
      }
      payload.employee_ids = ids;
    }

    setBulkSubmitting(true);
    try {
      const res = await client.post(
        ENDPOINTS.SHIFTS.ASSIGNMENTS_BULK,
        payload,
        { params: { close_previous: true } },
      );
      setBulkResult(res.data);
      const { assigned, skipped, failed } = res.data || {};
      if (failed > 0) {
        toast.error(
          `Bulk done: ${assigned} assigned, ${skipped} skipped, ${failed} failed`,
        );
      } else {
        toast.success(
          `Bulk done: ${assigned} assigned, ${skipped} skipped`,
        );
      }
      fetchItems();
    } catch (e: any) {
      toast.error(errMsg(e, 'Bulk assignment failed'));
    } finally {
      setBulkSubmitting(false);
    }
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    try {
      await client.delete(ENDPOINTS.SHIFTS.ASSIGNMENT_DETAIL(deleteTarget.id));
      toast.success('Assignment removed');
      setDeleteTarget(null);
      fetchItems();
    } catch (e: any) {
      toast.error(errMsg(e, 'Delete failed'));
    }
  };

  return (
    <div className="p-8 space-y-6 max-w-[1600px] mx-auto animate-in fade-in duration-300">
      <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-4">
        <div>
          <h2 className="text-3xl font-black text-[#0F172A] tracking-tighter uppercase">
            Shift Assignments
          </h2>
          <p className="text-[#64748B] font-bold uppercase tracking-widest text-[10px] mt-1">
            Who Works Which Shift · Reassign &amp; Bulk-Assign
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <button
            type="button"
            onClick={fetchItems}
            className="p-2 text-slate-400 hover:text-blue-600 transition-colors"
            title="Refresh"
            aria-label="Refresh"
          >
            <RefreshCw size={16} className={cn(loading && 'animate-spin')} />
          </button>
          <Button
            onClick={openBulk}
            variant="ghost"
            className="h-10 border border-blue-200 bg-blue-50 text-blue-700 hover:bg-blue-100 font-black uppercase text-[10px] tracking-widest"
          >
            <Users size={14} className="mr-1.5" />
            Bulk Assign
          </Button>
        </div>
      </div>

      <Card className="p-0 border-slate-200 overflow-hidden bg-white">
        <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between bg-slate-50/40 gap-4 flex-wrap">
          <div className="flex items-center gap-3 flex-wrap">
            <h4 className="text-sm font-black text-[#0F172A] tracking-tight uppercase">
              Assignments
              {!loading && (
                <span className="ml-2 text-slate-400 font-bold text-[10px]">
                  ({filtered.length}/{items.length})
                </span>
              )}
            </h4>
            <label className="inline-flex items-center gap-1.5 text-[10px] font-black uppercase tracking-widest text-slate-600 cursor-pointer">
              <input
                type="checkbox"
                checked={onlyOngoing}
                onChange={(e) => setOnlyOngoing(e.target.checked)}
                className="w-3.5 h-3.5 accent-blue-600"
              />
              Ongoing Only
            </label>
            <select
              value={templateFilter}
              onChange={(e) =>
                setTemplateFilter(
                  e.target.value === '' ? '' : Number(e.target.value),
                )
              }
              className="h-9 px-3 bg-white border border-slate-200 rounded-xl text-[10px] font-black uppercase tracking-widest text-slate-700 outline-none"
            >
              <option value="">All Shifts</option>
              {templates.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </select>
            <input
              value={departmentFilter}
              onChange={(e) => setDepartmentFilter(e.target.value)}
              placeholder="Filter dept…"
              className="h-9 px-3 bg-white border border-slate-200 rounded-xl text-[10px] font-black uppercase tracking-widest w-40 outline-none"
            />
            <div className="flex items-center gap-1.5">
              <Calendar size={12} className="text-slate-400" />
              <input
                type="date"
                value={asOfDate}
                onChange={(e) => setAsOfDate(e.target.value)}
                className="h-9 px-2 bg-white border border-slate-200 rounded-xl text-[10px] font-black uppercase tracking-widest outline-none"
                title="Show assignments active on this date"
              />
              {asOfDate && (
                <button
                  type="button"
                  onClick={() => setAsOfDate('')}
                  className="text-[9px] text-slate-400 hover:text-slate-700"
                >
                  clear
                </button>
              )}
            </div>
          </div>
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 pointer-events-none" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search name, email, dept, shift..."
              className="pl-10 pr-4 h-9 bg-white border border-slate-200 rounded-xl text-[10px] font-black uppercase tracking-widest w-72 focus:ring-2 focus:ring-blue-600/10 outline-none"
            />
          </div>
        </div>

        {loading ? (
          <div className="py-16 text-center text-[10px] font-black uppercase tracking-widest text-slate-400 animate-pulse">
            Loading…
          </div>
        ) : filtered.length === 0 ? (
          <div className="py-16 text-center text-[10px] font-black uppercase tracking-widest text-slate-400">
            No assignments match these filters.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead className="bg-white border-b border-slate-100">
                <tr>
                  <th className="px-6 py-3 text-[9px] font-black text-slate-400 uppercase tracking-widest">
                    Employee
                  </th>
                  <th className="px-6 py-3 text-[9px] font-black text-slate-400 uppercase tracking-widest">
                    Department
                  </th>
                  <th className="px-6 py-3 text-[9px] font-black text-slate-400 uppercase tracking-widest">
                    Shift
                  </th>
                  <th className="px-6 py-3 text-[9px] font-black text-slate-400 uppercase tracking-widest">
                    From → To
                  </th>
                  <th className="px-6 py-3 text-[9px] font-black text-slate-400 uppercase tracking-widest w-28">
                    Status
                  </th>
                  <th className="px-6 py-3 text-right text-[9px] font-black text-slate-400 uppercase tracking-widest w-44">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {filtered.map((a) => {
                  const ongoing = !a.effective_to;
                  return (
                    <tr
                      key={a.id}
                      className="hover:bg-slate-50/60 transition-colors"
                    >
                      <td className="px-6 py-3">
                        <div className="text-sm font-black text-[#0F172A]">
                          {a.employee_name || `User #${a.employee_id}`}
                        </div>
                        {a.employee_email && (
                          <div className="text-[10px] font-bold text-slate-400">
                            {a.employee_email}
                          </div>
                        )}
                      </td>
                      <td className="px-6 py-3 text-[11px] font-bold text-slate-600">
                        {a.employee_department || '—'}
                      </td>
                      <td className="px-6 py-3 text-sm font-black text-[#0F172A]">
                        {a.shift_template_name ||
                          `Template #${a.shift_template_id}`}
                      </td>
                      <td className="px-6 py-3 text-xs font-bold text-slate-700 tabular-nums">
                        {a.effective_from} →{' '}
                        {a.effective_to || (
                          <span className="text-emerald-600">ongoing</span>
                        )}
                        {a.note && (
                          <div className="text-[10px] font-bold text-slate-400 mt-0.5 italic">
                            {a.note}
                          </div>
                        )}
                      </td>
                      <td className="px-6 py-3">
                        <Badge
                          variant={ongoing ? 'success' : 'neutral'}
                          className="text-[8px] uppercase"
                        >
                          {ongoing ? 'Active' : 'Ended'}
                        </Badge>
                      </td>
                      <td className="px-6 py-3 text-right space-x-1">
                        <button
                          type="button"
                          onClick={() =>
                            openSingleAssign(
                              a.employee_id,
                              a.employee_name || undefined,
                            )
                          }
                          className="inline-flex items-center px-2.5 py-1.5 rounded-lg text-[9px] font-black uppercase tracking-widest text-blue-700 hover:bg-blue-50"
                        >
                          Reassign
                        </button>
                        <button
                          type="button"
                          onClick={() => setDeleteTarget(a)}
                          className="inline-flex items-center px-2.5 py-1.5 rounded-lg text-[9px] font-black uppercase tracking-widest text-rose-600 hover:bg-rose-50"
                        >
                          <Trash2 size={11} className="mr-1" /> Remove
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* Single assign / reassign */}
      {singleAssignEmployeeId !== null && (
        <AssignShiftDialog
          open={singleAssignOpen}
          onClose={() => setSingleAssignOpen(false)}
          employeeId={singleAssignEmployeeId}
          employeeName={singleAssignEmployeeName}
          onAssigned={fetchItems}
        />
      )}

      {/* Bulk assign dialog */}
      <Dialog
        open={bulkOpen}
        onOpenChange={(o) => (o ? setBulkOpen(true) : setBulkOpen(false))}
      >
        <DialogContent className="max-w-xl p-0 overflow-hidden">
          <div className="bg-blue-600 px-6 py-5 text-white">
            <DialogTitle className="text-lg font-black uppercase tracking-tight flex items-center gap-2">
              <Users size={18} />
              Bulk Assign Shift
            </DialogTitle>
            <p className="text-blue-100 text-[10px] font-bold uppercase tracking-widest mt-1">
              Same Shift · Many Employees · Existing Open-Ended Assignments Auto-Close
            </p>
          </div>
          <div className="p-6 space-y-5 max-h-[70vh] overflow-y-auto">
            <div>
              <label className="text-[10px] font-black uppercase tracking-widest text-[#0F172A]">
                Target
              </label>
              <div className="flex gap-2 mt-1.5">
                <button
                  type="button"
                  onClick={() => setBulkForm({ ...bulkForm, mode: 'department' })}
                  className={cn(
                    'flex-1 px-3 py-2 rounded-xl border text-[10px] font-black uppercase tracking-widest transition-colors',
                    bulkForm.mode === 'department'
                      ? 'bg-blue-600 text-white border-blue-600'
                      : 'bg-white text-slate-600 border-slate-200 hover:border-blue-300',
                  )}
                >
                  <Building2 size={12} className="inline mr-1" />
                  By Department
                </button>
                <button
                  type="button"
                  onClick={() =>
                    setBulkForm({ ...bulkForm, mode: 'employee_ids' })
                  }
                  className={cn(
                    'flex-1 px-3 py-2 rounded-xl border text-[10px] font-black uppercase tracking-widest transition-colors',
                    bulkForm.mode === 'employee_ids'
                      ? 'bg-blue-600 text-white border-blue-600'
                      : 'bg-white text-slate-600 border-slate-200 hover:border-blue-300',
                  )}
                >
                  <Users size={12} className="inline mr-1" />
                  By Employee IDs
                </button>
              </div>
            </div>

            {bulkForm.mode === 'department' ? (
              <div>
                <label className="text-[10px] font-black uppercase tracking-widest text-[#0F172A]">
                  Department Name
                </label>
                <Input
                  value={bulkForm.department}
                  onChange={(e: any) =>
                    setBulkForm({ ...bulkForm, department: e.target.value })
                  }
                  placeholder="e.g. Engineering"
                  className="mt-1.5"
                />
                <p className="text-[9px] font-bold text-slate-400 mt-1">
                  Exact match against each active employee's department field.
                </p>
              </div>
            ) : (
              <div>
                <label className="text-[10px] font-black uppercase tracking-widest text-[#0F172A]">
                  Employee User IDs
                </label>
                <Input
                  value={bulkForm.employee_ids}
                  onChange={(e: any) =>
                    setBulkForm({ ...bulkForm, employee_ids: e.target.value })
                  }
                  placeholder="32, 43, 47"
                  className="mt-1.5"
                />
                <p className="text-[9px] font-bold text-slate-400 mt-1">
                  Comma or space separated.
                </p>
              </div>
            )}

            <div>
              <label className="text-[10px] font-black uppercase tracking-widest text-[#0F172A]">
                Shift Template
              </label>
              <select
                value={bulkForm.shift_template_id}
                onChange={(e) =>
                  setBulkForm({
                    ...bulkForm,
                    shift_template_id:
                      e.target.value === '' ? '' : Number(e.target.value),
                  })
                }
                className="mt-1.5 w-full h-10 px-3 bg-white border border-slate-200 rounded-xl text-sm font-bold text-[#0F172A] outline-none"
              >
                <option value="">— Choose a template —</option>
                {templates
                  .filter((t) => t.is_active)
                  .map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.name}
                    </option>
                  ))}
              </select>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="text-[10px] font-black uppercase tracking-widest text-[#0F172A]">
                  Effective From
                </label>
                <Input
                  type="date"
                  value={bulkForm.effective_from}
                  onChange={(e: any) =>
                    setBulkForm({ ...bulkForm, effective_from: e.target.value })
                  }
                  className="mt-1.5"
                />
              </div>
              <div>
                <label className="text-[10px] font-black uppercase tracking-widest text-[#0F172A]">
                  Effective To
                </label>
                <Input
                  type="date"
                  value={bulkForm.effective_to}
                  onChange={(e: any) =>
                    setBulkForm({ ...bulkForm, effective_to: e.target.value })
                  }
                  className="mt-1.5"
                />
              </div>
            </div>

            <div>
              <label className="text-[10px] font-black uppercase tracking-widest text-[#0F172A]">
                Note
              </label>
              <Input
                value={bulkForm.note}
                onChange={(e: any) =>
                  setBulkForm({ ...bulkForm, note: e.target.value })
                }
                placeholder="optional"
                maxLength={255}
                className="mt-1.5"
              />
            </div>

            {bulkResult && (
              <div className="grid grid-cols-3 gap-2">
                <div className="rounded-xl border border-emerald-100 bg-emerald-50 px-3 py-3 text-center">
                  <div className="text-[9px] font-black uppercase tracking-widest text-emerald-700">
                    Assigned
                  </div>
                  <div className="text-2xl font-black text-emerald-700 tabular-nums">
                    {bulkResult.assigned}
                  </div>
                </div>
                <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-3 text-center">
                  <div className="text-[9px] font-black uppercase tracking-widest text-slate-600">
                    Skipped
                  </div>
                  <div className="text-2xl font-black text-slate-600 tabular-nums">
                    {bulkResult.skipped}
                  </div>
                </div>
                <div className="rounded-xl border border-rose-100 bg-rose-50 px-3 py-3 text-center">
                  <div className="text-[9px] font-black uppercase tracking-widest text-rose-700">
                    Failed
                  </div>
                  <div className="text-2xl font-black text-rose-700 tabular-nums">
                    {bulkResult.failed}
                  </div>
                </div>
                {bulkResult.errors.length > 0 && (
                  <div className="col-span-3 rounded-xl border border-rose-100 bg-rose-50/40 p-3 max-h-40 overflow-y-auto">
                    <ul className="space-y-1">
                      {bulkResult.errors.map((err, i) => (
                        <li
                          key={i}
                          className="text-[11px] text-rose-800 break-all"
                        >
                          • {err}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}
          </div>
          <DialogFooter className="px-6 py-4 bg-slate-50 border-t border-slate-100">
            <Button
              variant="ghost"
              onClick={() => setBulkOpen(false)}
              className="text-[10px] font-black uppercase tracking-widest"
            >
              {bulkResult ? 'Done' : 'Cancel'}
            </Button>
            {!bulkResult && (
              <Button
                onClick={submitBulk}
                isLoading={bulkSubmitting}
                className="bg-blue-600 hover:bg-blue-700 text-white text-[10px] font-black uppercase tracking-widest"
              >
                <Plus size={12} className="mr-1.5" />
                Assign
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={!!deleteTarget}
        onOpenChange={() => setDeleteTarget(null)}
      >
        <DialogContent className="max-w-md p-0 overflow-hidden">
          <div className="bg-rose-600 px-6 py-5 text-white">
            <DialogTitle className="text-lg font-black uppercase tracking-tight">
              Remove Assignment
            </DialogTitle>
          </div>
          <div className="p-6">
            <p className="text-sm text-slate-700">
              Delete the shift assignment for{' '}
              <strong>
                {deleteTarget?.employee_name ||
                  `user #${deleteTarget?.employee_id}`}
              </strong>
              ? This cannot be undone.
            </p>
          </div>
          <DialogFooter className="px-6 py-4 bg-slate-50 border-t border-slate-100">
            <Button
              variant="ghost"
              onClick={() => setDeleteTarget(null)}
              className="text-[10px] font-black uppercase tracking-widest"
            >
              Cancel
            </Button>
            <Button
              onClick={confirmDelete}
              className="bg-rose-600 hover:bg-rose-700 text-white text-[10px] font-black uppercase tracking-widest"
            >
              Remove
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};
