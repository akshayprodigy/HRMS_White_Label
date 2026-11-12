import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Users, Pencil, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '../ui-elements';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../ui/dialog';
import { client } from '../../api/client';
import { ENDPOINTS } from '../../api/endpoints';
import { errMsg } from '../schedule-delegations-utils';
import type { CoverageRequirement, ShiftTemplateLite } from './roster-api';

const WD = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const fieldCls =
  'w-full px-3 py-1.5 border rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500';

interface Form {
  department: string;
  location: string;
  shift: string;
  weekday: string;
  min: string;
  max: string;
}
const EMPTY: Form = { department: '', location: '', shift: '', weekday: '', min: '1', max: '' };

interface Props {
  open: boolean;
  templates: ShiftTemplateLite[];
  onClose: () => void;
  onChanged: () => void;
}

export const CoverageRequirementsDialog = ({ open, templates, onClose, onChanged }: Props) => {
  const [items, setItems] = useState<CoverageRequirement[]>([]);
  const [depts, setDepts] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadErr, setLoadErr] = useState<string | null>(null);
  const [editId, setEditId] = useState<number | 'new' | null>(null);
  const [form, setForm] = useState<Form>(EMPTY);
  const [formErr, setFormErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirmDel, setConfirmDel] = useState<number | null>(null);
  const req = useRef(0);

  const load = useCallback(async () => {
    const id = ++req.current;
    setLoading(true);
    setLoadErr(null);
    try {
      const res = await client.get<CoverageRequirement[]>(ENDPOINTS.ROSTER.COVERAGE_REQUIREMENTS);
      if (id !== req.current) return;
      setItems(res.data || []);
    } catch (err: any) {
      if (id !== req.current) return;
      setLoadErr(errMsg(err, 'Failed to load coverage requirements'));
    } finally {
      if (id === req.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!open) return;
    setEditId(null);
    setConfirmDel(null);
    setFormErr(null);
    load();
    client
      .get(ENDPOINTS.HR.DEPARTMENTS)
      .then((r) => setDepts(((r.data as any[]) || []).map((d) => d.name).filter(Boolean)))
      .catch(() => setDepts([])); // falls back to free text
  }, [open, load]);

  const shiftName = (id: number) => templates.find((t) => t.id === id)?.name || `Shift #${id}`;

  const startEdit = (r: CoverageRequirement | null) => {
    setConfirmDel(null);
    setFormErr(null);
    setEditId(r ? r.id : 'new');
    setForm(
      r
        ? {
            department: r.department || '',
            location: r.location || '',
            shift: String(r.shift_template_id),
            weekday: r.weekday == null ? '' : String(r.weekday),
            min: String(r.min_headcount),
            max: r.max_headcount == null ? '' : String(r.max_headcount),
          }
        : { ...EMPTY, shift: templates[0] ? String(templates[0].id) : '' }
    );
  };

  const save = async () => {
    const min = +form.min;
    const max = form.max.trim() === '' ? null : +form.max;
    if (!form.shift) return setFormErr('Choose a shift');
    if (form.min.trim() === '' || !Number.isInteger(min) || min < 0)
      return setFormErr('Minimum must be a whole number, 0 or more');
    if (max !== null && (!Number.isInteger(max) || max < min))
      return setFormErr('Maximum must be a whole number, not below the minimum');
    const body = {
      department: form.department.trim() || null,
      location: form.location.trim() || null,
      shift_template_id: Number(form.shift),
      weekday: form.weekday === '' ? null : Number(form.weekday),
      min_headcount: min,
      max_headcount: max,
    };
    setBusy(true);
    setFormErr(null);
    try {
      if (editId === 'new') await client.post(ENDPOINTS.ROSTER.COVERAGE_REQUIREMENTS, body);
      else if (editId != null)
        await client.patch(ENDPOINTS.ROSTER.COVERAGE_REQUIREMENT(editId), body);
      toast.success('Coverage requirement saved');
      setEditId(null);
      await load();
      onChanged();
    } catch (err: any) {
      setFormErr(errMsg(err, 'Failed to save requirement'));
    } finally {
      setBusy(false);
    }
  };

  const remove = async (id: number) => {
    setBusy(true);
    try {
      await client.delete(ENDPOINTS.ROSTER.COVERAGE_REQUIREMENT(id));
      toast.success('Requirement deleted');
      setConfirmDel(null);
      await load();
      onChanged();
    } catch (err: any) {
      toast.error(errMsg(err, 'Failed to delete requirement'));
    } finally {
      setBusy(false);
    }
  };

  const set = (k: keyof Form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }));

  return (
    <Dialog open={open} onOpenChange={(o: boolean) => !o && !busy && onClose()}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Users className="w-5 h-5 text-indigo-600" />
            Coverage requirements
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-3 py-2 max-h-[70vh] overflow-y-auto">
          {loadErr && (
            <div className="p-2 bg-red-50 border border-red-200 rounded text-sm text-red-700">
              {loadErr}
            </div>
          )}
          {loading && <p className="text-sm text-gray-400">Loading…</p>}
          {!loading && !loadErr && items.length === 0 && (
            <p className="text-sm text-gray-500">No requirements yet.</p>
          )}
          <ul className="space-y-1.5">
            {items.map((r) => (
              <li
                key={r.id}
                className="flex items-center gap-2 border rounded-lg px-3 py-2 text-sm"
              >
                <div className="flex-1 min-w-0">
                  <div className="font-medium text-gray-900">
                    {shiftName(r.shift_template_id)} &middot;{' '}
                    {r.weekday == null ? 'Every day' : WD[r.weekday]}
                  </div>
                  <div className="text-xs text-gray-500">
                    {r.department || 'All departments'} &middot; {r.location || 'All locations'}{' '}
                    &middot; min {r.min_headcount}
                    {r.max_headcount != null && `, max ${r.max_headcount}`}
                  </div>
                </div>
                {confirmDel === r.id ? (
                  <>
                    <span className="text-xs text-red-700">Delete?</span>
                    <Button size="sm" variant="outline" disabled={busy} onClick={() => setConfirmDel(null)}>
                      No
                    </Button>
                    <Button
                      size="sm"
                      disabled={busy}
                      onClick={() => remove(r.id)}
                      className="bg-red-600 hover:bg-red-700 text-white"
                    >
                      {busy ? 'Deleting…' : 'Yes, delete'}
                    </Button>
                  </>
                ) : (
                  <>
                    <button
                      type="button"
                      aria-label={`Edit requirement ${r.id}`}
                      disabled={busy}
                      onClick={() => startEdit(r)}
                      className="p-1 text-gray-500 hover:text-indigo-600"
                    >
                      <Pencil className="w-4 h-4" />
                    </button>
                    <button
                      type="button"
                      aria-label={`Delete requirement ${r.id}`}
                      disabled={busy}
                      onClick={() => {
                        setEditId(null);
                        setConfirmDel(r.id);
                      }}
                      className="p-1 text-gray-500 hover:text-red-600"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </>
                )}
              </li>
            ))}
          </ul>

          {editId == null ? (
            <Button
              size="sm"
              onClick={() => startEdit(null)}
              disabled={templates.length === 0}
              className="bg-indigo-600 hover:bg-indigo-700 text-white"
            >
              Add requirement
            </Button>
          ) : (
            <div className="border rounded-lg p-3 space-y-3 bg-gray-50">
              <div className="text-sm font-medium text-gray-800">
                {editId === 'new' ? 'New requirement' : 'Edit requirement'}
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div className="space-y-1">
                  <label htmlFor="cr-dept" className="text-xs text-gray-600">Department</label>
                  <input
                    id="cr-dept"
                    list="cr-dept-list"
                    className={fieldCls}
                    placeholder="All departments"
                    value={form.department}
                    onChange={set('department')}
                  />
                  <datalist id="cr-dept-list">
                    {depts.map((d) => (
                      <option key={d} value={d} />
                    ))}
                  </datalist>
                </div>
                <div className="space-y-1">
                  <label htmlFor="cr-loc" className="text-xs text-gray-600">Location</label>
                  <input
                    id="cr-loc"
                    className={fieldCls}
                    placeholder="All locations"
                    value={form.location}
                    onChange={set('location')}
                  />
                </div>
                <div className="space-y-1">
                  <label htmlFor="cr-shift" className="text-xs text-gray-600">Shift</label>
                  <select id="cr-shift" className={fieldCls} value={form.shift} onChange={set('shift')}>
                    <option value="">Select shift…</option>
                    {form.shift && !templates.some((t) => String(t.id) === form.shift) && (
                      <option value={form.shift}>Shift #{form.shift} (unavailable)</option>
                    )}
                    {templates.map((t) => (
                      <option key={t.id} value={t.id}>
                        {t.name}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="space-y-1">
                  <label htmlFor="cr-wd" className="text-xs text-gray-600">Weekday</label>
                  <select id="cr-wd" className={fieldCls} value={form.weekday} onChange={set('weekday')}>
                    <option value="">Every day</option>
                    {WD.map((w, i) => (
                      <option key={w} value={i}>
                        {w}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="space-y-1">
                  <label htmlFor="cr-min" className="text-xs text-gray-600">Minimum headcount</label>
                  <input id="cr-min" type="number" min={0} className={fieldCls} value={form.min} onChange={set('min')} />
                </div>
                <div className="space-y-1">
                  <label htmlFor="cr-max" className="text-xs text-gray-600">Maximum (optional)</label>
                  <input id="cr-max" type="number" min={0} className={fieldCls} value={form.max} onChange={set('max')} />
                </div>
              </div>
              {formErr && (
                <div role="alert" className="text-sm text-red-700">
                  {formErr}
                </div>
              )}
              <div className="flex justify-end gap-2">
                <Button size="sm" variant="outline" disabled={busy} onClick={() => setEditId(null)}>
                  Cancel
                </Button>
                <Button
                  size="sm"
                  disabled={busy}
                  onClick={save}
                  className="bg-indigo-600 hover:bg-indigo-700 text-white"
                >
                  {busy ? 'Saving…' : 'Save'}
                </Button>
              </div>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
};
