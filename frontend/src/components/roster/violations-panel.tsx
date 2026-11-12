import { useMemo, useState } from 'react';
import { AlertTriangle, ChevronDown, ChevronRight } from 'lucide-react';
import { Card, cn } from '../ui-elements';
import type { Violation } from './roster-api';

export const violationKey = (userId: number, date: string) => `${userId}-${date}`;

export const ViolationsPanel = ({ violations, stale = false }: { violations: Violation[]; stale?: boolean }) => {
  const [open, setOpen] = useState(false);
  const sorted = useMemo(
    () =>
      [...violations].sort(
        (a, b) =>
          a.work_date.localeCompare(b.work_date) ||
          (a.employee_name || '').localeCompare(b.employee_name || '')
      ),
    [violations]
  );
  if (violations.length === 0) return null;
  return (
    <Card className={cn('border-amber-200 bg-amber-50', stale && 'opacity-60')}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="w-full flex items-center gap-2 px-3 py-2 text-sm font-medium text-amber-800"
      >
        {open ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
        <AlertTriangle className="w-4 h-4" />
        {violations.length} rule warning{violations.length === 1 ? '' : 's'}
        <span className="text-xs font-normal text-amber-700">
          {stale ? '(out of date: refresh failed)' : '(warnings never block saving)'}
        </span>
      </button>
      {open && (
        <ul className="px-3 pb-3 space-y-1 max-h-60 overflow-y-auto">
          {sorted.map((v, i) => (
            <li key={i} className="text-xs text-amber-900 flex gap-2">
              <span className="font-medium whitespace-nowrap">{v.work_date}</span>
              <span className="font-medium">
                {v.employee_name || `User #${v.user_id}`}
              </span>
              <span>{v.message}</span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
};
