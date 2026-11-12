import React, { useEffect, useMemo, useState } from 'react';
import { RefreshCw, Wand2 } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '../ui-elements';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '../ui/dialog';
import { client } from '../../api/client';
import { ENDPOINTS } from '../../api/endpoints';
import { errMsg } from '../schedule-delegations-utils';
import type { AutofillPreview, AutofillSuggestion, BulkResult } from './roster-api';

interface Props {
  open: boolean;
  start: string;
  end: string;
  department: string;
  onClose: () => void;
  onDone: () => void;
}

const keyOf = (s: AutofillSuggestion) => `${s.employee_id}|${s.work_date}`;

const fmtDay = (iso: string) =>
  new Date(iso + 'T00:00:00').toLocaleDateString(undefined, {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
  });

export const AutofillDialog = ({ open, start, end, department, onClose, onDone }: Props) => {
  const [loading, setLoading] = useState(false);
  const [applying, setApplying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<AutofillPreview | null>(null);
  const [checked, setChecked] = useState<Set<string>>(new Set());

  const load = async () => {
    setLoading(true);
    setError(null);
    setPreview(null);
    try {
      const { data } = await client.post<AutofillPreview>(ENDPOINTS.ROSTER.AUTOFILL_PREVIEW, {
        start,
        end,
        department: department || null,
      });
      setPreview(data);
      setChecked(new Set(data.suggestions.map(keyOf)));
    } catch (err: any) {
      setError(errMsg(err, 'Failed to generate suggestions'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (open && start && end) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, start, end, department]);

  const byDay = useMemo(() => {
    const m = new Map<string, AutofillSuggestion[]>();
    (preview?.suggestions || []).forEach((s) => {
      const l = m.get(s.work_date) || [];
      l.push(s);
      m.set(s.work_date, l);
    });
    return Array.from(m.entries()).sort(([a], [b]) => a.localeCompare(b));
  }, [preview]);

  const toggle = (k: string) =>
    setChecked((prev) => {
      const n = new Set(prev);
      if (n.has(k)) n.delete(k);
      else n.add(k);
      return n;
    });

  const apply = async () => {
    const picked = (preview?.suggestions || []).filter((s) => checked.has(keyOf(s)));
    if (!picked.length) return;
    setApplying(true);
    try {
      const { data } = await client.post<BulkResult>(ENDPOINTS.ROSTER.BULK, {
        start,
        end,
        status: 'draft',
        overwrite: false,
        entries: picked.map((s) => ({
          employee_id: s.employee_id,
          work_date: s.work_date,
          shift_template_id: s.shift_template_id,
          is_week_off: false,
          status: 'draft',
        })),
      });
      toast.success(
        `Auto-fill saved as drafts — ${data.created} created, ${data.skipped} skipped` +
          (data.out_of_scope.length ? `, ${data.out_of_scope.length} out of scope` : '')
      );
      if (data.errors.length) toast.error(data.errors.slice(0, 3).join('; '));
      onClose();
      onDone();
    } catch (err: any) {
      toast.error(errMsg(err, 'Failed to apply suggestions'));
    } finally {
      setApplying(false);
    }
  };

  const n = checked.size;
  return (
    <Dialog open={open} onOpenChange={(o: boolean) => !o && !applying && onClose()}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Wand2 className="w-5 h-5 text-indigo-600" />
            Auto-fill suggestions
          </DialogTitle>
          <DialogDescription>
            Suggested people for under-covered shifts in {start} → {end}
            {department ? ` (${department})` : ''}. Existing cells are never changed; accepted
            suggestions are saved as drafts.
          </DialogDescription>
        </DialogHeader>
        <div className="py-2 text-sm text-gray-700 space-y-3 overflow-y-auto" style={{ maxHeight: '60vh' }}>
          {loading && (
            <p className="flex items-center gap-2 text-gray-500">
              <RefreshCw className="w-4 h-4 animate-spin" /> Generating suggestions…
            </p>
          )}
          {error && (
            <div role="alert" className="text-red-700 text-sm flex items-center gap-3">
              {error}
              <Button variant="outline" size="sm" onClick={load}>
                Retry
              </Button>
            </div>
          )}
          {preview && !byDay.length && !preview.unfilled.length && (
            <p className="text-gray-500">
              Nothing to fill: every coverage requirement in this window is already met (or no
              requirements apply).
            </p>
          )}
          {byDay.map(([day, list]) => (
            <section key={day} aria-label={`Suggestions for ${day}`}>
              <h4 className="font-semibold text-gray-900 mb-1">{fmtDay(day)}</h4>
              <ul className="divide-y border border-gray-200 rounded-lg">
                {list.map((s) => {
                  const k = keyOf(s);
                  const label = `${s.employee_name || `Employee ${s.employee_id}`} — ${s.shift_name || 'shift'} on ${day}`;
                  return (
                    <li key={k} className="flex items-center gap-3 px-3 py-2">
                      <input
                        type="checkbox"
                        aria-label={label}
                        checked={checked.has(k)}
                        onChange={() => toggle(k)}
                        disabled={applying}
                      />
                      <span className="font-medium">{s.employee_name || `Employee ${s.employee_id}`}</span>
                      <span className="text-indigo-700">{s.shift_name}</span>
                      <span className="text-xs text-gray-500 ml-auto">{s.reasons.join(' · ')}</span>
                    </li>
                  );
                })}
              </ul>
            </section>
          ))}
          {!!preview?.unfilled.length && (
            <section aria-label="Unfilled slots">
              <h4 className="font-semibold text-amber-800 mb-1">Could not fill</h4>
              <ul className="text-xs text-amber-800 space-y-1">
                {preview.unfilled.map((u, i) => (
                  <li key={i}>
                    {fmtDay(u.work_date)} · {u.shift_name || 'shift'}
                    {u.department ? ` · ${u.department}` : ''} — {u.missing} more needed (no eligible
                    employee)
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={applying}>
            Cancel
          </Button>
          <Button
            onClick={apply}
            disabled={applying || loading || n === 0}
            className="bg-indigo-600 hover:bg-indigo-700 text-white gap-2"
          >
            {applying && <RefreshCw className="w-4 h-4 animate-spin" />}
            Apply {n} as drafts
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
