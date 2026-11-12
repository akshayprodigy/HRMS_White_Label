import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Repeat, RefreshCw, Trash2, Plus, X } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '../ui-elements';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogDescription,
  DialogTitle,
} from '../ui/dialog';
import { client } from '../../api/client';
import { ENDPOINTS } from '../../api/endpoints';
import { errMsg } from '../schedule-delegations-utils';
import { daysBetween } from './roster-api';
import type {
  BulkResult,
  RosterGridRow,
  RotationPattern,
  ShiftTemplateLite,
} from './roster-api';

interface Props {
  open: boolean;
  onClose: () => void;
  isAdmin: boolean;
  canPublish: boolean;
  lockDays?: number;
  templates: ShiftTemplateLite[];
  rows: RosterGridRow[];
  start: string;
  end: string;
  onApplied: () => void;
}

type Cycle = (number | null)[];
const inputCls =
  'px-3 py-1.5 border rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500';

const rep = (v: number | null, n: number): Cycle => Array(n).fill(v);

export const RotationDialog = ({
  open, onClose, isAdmin, canPublish, lockDays = 0, templates, rows, start, end, onApplied,
}: Props) => {
  const [reason, setReason] = useState('');
  const [patterns, setPatterns] = useState<RotationPattern[]>([]);
  const [loading, setLoading] = useState(false);
  const reqId = useRef(0);

  // create form
  const [name, setName] = useState('');
  const [desc, setDesc] = useState('');
  const [cycle, setCycle] = useState<Cycle>([]);
  const [saving, setSaving] = useState(false);

  // apply form
  const [patternId, setPatternId] = useState<number | ''>('');
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [aStart, setAStart] = useState(start);
  const [aEnd, setAEnd] = useState(end);
  const [aAnchor, setAAnchor] = useState(start);
  const [offsets, setOffsets] = useState<Record<number, string>>({});
  const [status, setStatus] = useState<'draft' | 'published'>('draft');
  const [applying, setApplying] = useState(false);
  const [confirmDel, setConfirmDel] = useState<number | null>(null);
  const [deleting, setDeleting] = useState<number | null>(null);

  const load = useCallback(async () => {
    const id = ++reqId.current;
    setLoading(true);
    try {
      const { data } = await client.get<RotationPattern[]>(ENDPOINTS.ROSTER.ROTATIONS);
      if (id === reqId.current) setPatterns((data || []).filter((p) => p.is_active));
    } catch (err: any) {
      if (id === reqId.current) toast.error(errMsg(err, 'Failed to load rotations'));
    } finally {
      if (id === reqId.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!open) return;
    load();
    setAStart(start);
    setAEnd(end);
    setAAnchor(start);
    setSelected(new Set());
    setOffsets({});
    setStatus('draft');
    setReason('');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const tplName = (id: number | null) =>
    id === null ? 'Off' : templates.find((t) => t.id === id)?.name || `#${id}`;

  const presets: { label: string; build: () => Cycle | null }[] = [
    {
      label: '4-on-4-off',
      build: () => (templates[0] ? [...rep(templates[0].id, 4), ...rep(null, 4)] : null),
    },
    {
      label: '2-2-3 (Panama)',
      build: () => {
        if (!templates[0]) return null;
        const a = templates[0].id;
        return [a, a, null, null, a, a, a, null, null, a, a, null, null, null];
      },
    },
    {
      label: 'Weekly A→B→C',
      build: () =>
        templates.length < 3
          ? null
          : templates.slice(0, 3).flatMap((t) => [...rep(t.id, 5), ...rep(null, 2)]),
    },
  ];

  const create = async () => {
    if (!name.trim() || cycle.length === 0) {
      toast.error('Name and at least one cycle day are required');
      return;
    }
    setSaving(true);
    try {
      await client.post(ENDPOINTS.ROSTER.ROTATIONS, {
        name: name.trim(),
        description: desc.trim() || null,
        cycle,
      });
      toast.success('Rotation pattern created');
      setName('');
      setDesc('');
      setCycle([]);
      load();
    } catch (err: any) {
      toast.error(errMsg(err, 'Failed to create rotation'));
    } finally {
      setSaving(false);
    }
  };

  const remove = async (p: RotationPattern) => {
    setDeleting(p.id);
    try {
      await client.delete(ENDPOINTS.ROSTER.ROTATION_DETAIL(p.id));
      toast.success('Rotation deleted');
      if (patternId === p.id) setPatternId('');
      load();
    } catch (err: any) {
      toast.error(errMsg(err, 'Failed to delete rotation'));
    } finally {
      setDeleting(null);
      setConfirmDel(null);
    }
  };

  const toggle = (id: number) =>
    setSelected((s) => {
      const n = new Set(s);
      n.has(id) ? n.delete(id) : n.add(id);
      return n;
    });
  const allSelected = rows.length > 0 && selected.size === rows.length;

  const apply = async () => {
    if (patternId === '' || selected.size === 0) {
      toast.error('Pick a pattern and at least one employee');
      return;
    }
    if (aStart > aEnd) {
      toast.error('Start must be on or before end');
      return;
    }
    if (daysBetween(aStart, aEnd) > 62) {
      toast.error('Range too large (max 62 days)');
      return;
    }
    const offs: Record<number, number> = {};
    for (const id of selected) {
      const n = parseInt(offsets[id] ?? '0', 10);
      offs[id] = Number.isFinite(n) ? n : 0;
    }
    setApplying(true);
    try {
      const { data } = await client.post<BulkResult>(
        ENDPOINTS.ROSTER.ROTATION_APPLY(patternId),
        {
          employee_ids: [...selected],
          start: aStart,
          end: aEnd,
          anchor: aAnchor,
          offsets: offs,
          default_offset: 0,
          overwrite: true,
          status: canPublish ? status : 'draft',
          reason: reason.trim() || undefined,
        }
      );
      toast.success(
        `Rotation applied — ${data.created} created, ${data.updated} updated, ${data.skipped} skipped` +
          (data.out_of_scope.length ? `, ${data.out_of_scope.length} out of scope` : '')
      );
      if (data.errors.length) toast.error(data.errors.slice(0, 3).join('; '));
      onApplied();
    } catch (err: any) {
      toast.error(errMsg(err, 'Failed to apply rotation'));
    } finally {
      setApplying(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o: boolean) => !o && !applying && onClose()}>
      <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Repeat className="w-5 h-5 text-indigo-600" />
            Rotations
          </DialogTitle>
          <DialogDescription className="sr-only">Manage rotation patterns and apply them to employees.</DialogDescription>
        </DialogHeader>

        <section className="space-y-2">
          <h3 className="text-sm font-semibold text-gray-800">Patterns</h3>
          {loading ? (
            <p className="text-sm text-gray-400">Loading…</p>
          ) : patterns.length === 0 ? (
            <p className="text-sm text-gray-400">No rotation patterns yet.</p>
          ) : (
            <ul className="space-y-1.5 max-h-40 overflow-y-auto">
              {patterns.map((p) => (
                <li key={p.id} className="flex items-start gap-2 p-2 border rounded-lg text-sm">
                  <div className="flex-1 min-w-0">
                    <div className="font-medium text-gray-900">
                      {p.name}{' '}
                      <span className="text-xs text-gray-400">({p.cycle.length} days)</span>
                    </div>
                    <div className="text-xs text-gray-500 break-words">
                      {p.cycle.map(tplName).join(' · ')}
                    </div>
                  </div>
                  {isAdmin &&
                    (confirmDel === p.id ? (
                      <div className="flex items-center gap-1.5 shrink-0">
                        <span className="text-xs text-gray-600">Delete?</span>
                        <Button
                          size="sm"
                          disabled={deleting === p.id}
                          onClick={() => remove(p)}
                          className="bg-red-600 hover:bg-red-700 text-white"
                        >
                          {deleting === p.id && <RefreshCw className="w-3.5 h-3.5 animate-spin" />}
                          Yes
                        </Button>
                        <Button size="sm" variant="outline" disabled={deleting === p.id} onClick={() => setConfirmDel(null)}>
                          No
                        </Button>
                      </div>
                    ) : (
                      <Button size="sm" variant="outline" onClick={() => setConfirmDel(p.id)} aria-label={`Delete ${p.name}`}>
                        <Trash2 className="w-4 h-4" />
                      </Button>
                    ))}
                </li>
              ))}
            </ul>
          )}
        </section>

        {isAdmin && (
          <section className="space-y-2 border-t pt-3">
            <h3 className="text-sm font-semibold text-gray-800">Create pattern</h3>
            <div className="flex flex-wrap gap-2">
              <input aria-label="Pattern name" className={inputCls} placeholder="Name" value={name} maxLength={80} onChange={(e) => setName(e.target.value)} />
              <input aria-label="Pattern description" className={`${inputCls} flex-1 min-w-[160px]`} placeholder="Description (optional)" value={desc} maxLength={255} onChange={(e) => setDesc(e.target.value)} />
            </div>
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <span className="text-gray-500">Presets:</span>
              {presets.map((p) => {
                const built = p.build();
                return (
                  <Button
                    key={p.label}
                    size="sm"
                    variant="outline"
                    disabled={!built}
                    title={built ? undefined : 'Not enough active shift templates'}
                    onClick={() => built && setCycle(built)}
                  >
                    {p.label}
                  </Button>
                );
              })}
            </div>
            <div className="flex flex-wrap gap-1.5">
              {cycle.map((v, i) => (
                <div key={i} className="flex items-center gap-0.5 border rounded px-1 py-0.5">
                  <span className="text-[10px] text-gray-400 w-4">{i + 1}</span>
                  <select
                    aria-label={`Cycle day ${i + 1}`}
                    value={v === null ? '' : String(v)}
                    onChange={(e) =>
                      setCycle((c) => c.map((x, j) => (j === i ? (e.target.value ? Number(e.target.value) : null) : x)))
                    }
                    className="text-xs border rounded px-1 py-0.5"
                  >
                    <option value="">Off</option>
                    {templates.map((t) => (
                      <option key={t.id} value={t.id}>{t.name}</option>
                    ))}
                  </select>
                  <button
                    onClick={() => setCycle((c) => c.filter((_, j) => j !== i))}
                    aria-label={`Remove day ${i + 1}`}
                    className="text-gray-400 hover:text-red-600"
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                </div>
              ))}
              <Button size="sm" variant="outline" disabled={cycle.length >= 56} onClick={() => setCycle((c) => [...c, null])}>
                <Plus className="w-4 h-4" /> Day
              </Button>
            </div>
            <Button
              size="sm"
              onClick={create}
              disabled={saving || !name.trim() || cycle.length === 0}
              className="bg-indigo-600 hover:bg-indigo-700 text-white gap-1.5"
            >
              {saving && <RefreshCw className="w-4 h-4 animate-spin" />}
              Save pattern
            </Button>
          </section>
        )}

        <section className="space-y-2 border-t pt-3">
          <h3 className="text-sm font-semibold text-gray-800">Apply pattern</h3>
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <select aria-label="Pattern to apply" className={inputCls} value={patternId} onChange={(e) => setPatternId(e.target.value ? Number(e.target.value) : '')}>
              <option value="">Select pattern…</option>
              {patterns.map((p) => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>
            <label className="flex items-center gap-1 text-gray-600">Start
              <input type="date" aria-label="Start date" className={inputCls} value={aStart} onChange={(e) => setAStart(e.target.value)} />
            </label>
            <label className="flex items-center gap-1 text-gray-600">End
              <input type="date" aria-label="End date" className={inputCls} value={aEnd} onChange={(e) => setAEnd(e.target.value)} />
            </label>
            <label className="flex items-center gap-1 text-gray-600">Anchor
              <input type="date" aria-label="Anchor date" className={inputCls} value={aAnchor} onChange={(e) => setAAnchor(e.target.value)} />
            </label>
          </div>
          <div className="flex items-center gap-3 text-sm text-gray-600">
            Save as:
            {(['draft', 'published'] as const).map((s) => (
              <label key={s} className="flex items-center gap-1 capitalize">
                <input
                  type="radio"
                  checked={(canPublish ? status : 'draft') === s}
                  disabled={s === 'published' && !canPublish}
                  onChange={() => setStatus(s)}
                />
                {s}
              </label>
            ))}
          </div>
          <p className="text-xs text-amber-700">
            Existing cells in the range, including published ones (when saving
            as Published), are overwritten and recorded in history as "bulk re-plan".
          </p>
          <div className="border rounded-lg max-h-56 overflow-y-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-gray-500 border-b">
                  <th className="p-2 w-8">
                    <input
                      type="checkbox"
                      checked={allSelected}
                      aria-label="Select all"
                      onChange={() => setSelected(allSelected ? new Set() : new Set(rows.map((r) => r.employee_id)))}
                    />
                  </th>
                  <th>Employee</th>
                  <th className="w-28">Offset (days)</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.employee_id} className="border-b last:border-0">
                    <td className="p-2">
                      <input type="checkbox" aria-label={`Select ${r.full_name || r.employee_id}`} checked={selected.has(r.employee_id)} onChange={() => toggle(r.employee_id)} />
                    </td>
                    <td>{r.full_name || `User #${r.employee_id}`}</td>
                    <td>
                      <input
                        type="number"
                        aria-label={`Offset for ${r.full_name || r.employee_id}`}
                        value={offsets[r.employee_id] ?? '0'}
                        onChange={(e) => setOffsets((o) => ({ ...o, [r.employee_id]: e.target.value }))}
                        className="w-20 px-2 py-1 border rounded text-sm"
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {lockDays > 0 && (
            <div className="space-y-1">
              <label htmlFor="rot-reason" className="text-sm font-medium text-gray-700">
                Reason (required if it changes published shifts in the next {lockDays} days)
              </label>
              <input
                id="rot-reason"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                maxLength={500}
                className={`w-full ${inputCls}`}
              />
            </div>
          )}
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={onClose} disabled={applying}>Close</Button>
            <Button
              onClick={apply}
              disabled={applying || patternId === '' || selected.size === 0}
              className="bg-indigo-600 hover:bg-indigo-700 text-white gap-2"
            >
              {applying && <RefreshCw className="w-4 h-4 animate-spin" />}
              Apply rotation
            </Button>
          </div>
        </section>
      </DialogContent>
    </Dialog>
  );
};
