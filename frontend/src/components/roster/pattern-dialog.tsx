import { useEffect, useState } from 'react';
import { Wand2, RefreshCw } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '../ui-elements';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '../ui/dialog';
import { client } from '../../api/client';
import { ENDPOINTS } from '../../api/endpoints';
import { errMsg } from '../schedule-delegations-utils';
import { WEEKOFF, type ShiftTemplateLite } from './roster-api';

const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

interface Props {
  open: boolean;
  mode: 'week' | 'month';
  templates: ShiftTemplateLite[];
  range: () => { start: string; end: string };
  department: string;
  status: 'draft' | 'published';
  onClose: () => void;
  onDone: () => void;
}

export const PatternDialog = ({
  open,
  mode,
  templates,
  range,
  department,
  status,
  onClose,
  onDone,
}: Props) => {
  const [pattern, setPattern] = useState<Record<number, string>>({});
  const [applying, setApplying] = useState(false);

  useEffect(() => {
    if (!open) setPattern({}); // reset on close so reopening has no stale first frame
  }, [open]);
  const close = () => {
    if (!applying) onClose();
  };

  const applyPattern = async () => {
    const { start, end } = range();
    const pat: Record<number, number | null> = {};
    Object.entries(pattern).forEach(([wd, val]) => {
      if (val === '') return; // untouched weekday
      pat[Number(wd)] = val === WEEKOFF ? null : Number(val);
    });
    if (Object.keys(pat).length === 0) {
      toast.error('Set at least one weekday in the pattern');
      return;
    }
    setApplying(true);
    try {
      const res = await client.post(ENDPOINTS.ROSTER.BULK, {
        start,
        end,
        department: department || null,
        status,
        overwrite: true,
        pattern: pat,
      });
      const r = res.data as any;
      toast.success(
        `Roster applied — ${r.created} created, ${r.updated} updated` +
          (r.out_of_scope.length
            ? `, ${r.out_of_scope.length} out of scope`
            : '')
      );
      if (r.errors?.length) toast.error(r.errors.slice(0, 3).join('; '));
      onClose();
      onDone();
    } catch (err: any) {
      toast.error(errMsg(err, 'Failed to apply pattern'));
    } finally {
      setApplying(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o: boolean) => !o && close()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Wand2 className="w-5 h-5 text-indigo-600" />
            Apply weekday pattern
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-3 py-2">
          <p className="text-sm text-gray-500">
            Assign a shift (or week-off) to each weekday across the current{' '}
            {mode}. Leave a weekday blank to keep it unchanged.
          </p>
          <p className="text-xs text-amber-700">
            Existing cells in this period, including published ones, are
            overwritten (recorded in history as "bulk re-plan").
          </p>
          {WEEKDAYS.map((label, wd) => (
            <div key={wd} className="flex items-center gap-3">
              <span className="w-12 text-sm font-medium text-gray-700">
                {label}
              </span>
              <select
                value={pattern[wd] ?? ''}
                aria-label={`${label} shift`}
                onChange={(e) =>
                  setPattern((p) => ({ ...p, [wd]: e.target.value }))
                }
                className="flex-1 px-3 py-1.5 border rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
              >
                <option value="">— unchanged —</option>
                {templates.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name} ({t.start_time}–{t.end_time})
                  </option>
                ))}
                <option value={WEEKOFF}>Week off</option>
              </select>
            </div>
          ))}
        </div>
        <DialogFooter>
          <Button variant="outline" disabled={applying} onClick={close}>
            Cancel
          </Button>
          <Button
            onClick={applyPattern}
            disabled={applying}
            className="bg-indigo-600 hover:bg-indigo-700 text-white gap-2"
          >
            {applying ? (
              <RefreshCw className="w-4 h-4 animate-spin" />
            ) : (
              <Wand2 className="w-4 h-4" />
            )}
            Apply to {mode}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
