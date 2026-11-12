import { cn } from '../ui-elements';
import type { CoverageCell, ShiftTemplateLite } from './roster-api';

const STATUS_CLS: Record<string, string> = {
  under: 'bg-red-50 text-red-700',
  ok: 'bg-emerald-50 text-emerald-700',
  over: 'bg-amber-50 text-amber-700',
};

const tip = (c: CoverageCell) => {
  const scope =
    [c.department, c.location].filter(Boolean).join(' / ') || 'All employees';
  return (
    `${scope}: ${c.scheduled} scheduled, minimum ${c.required_min}` +
    (c.required_max != null ? `, maximum ${c.required_max}` : '') +
    ` (${c.status})`
  );
};

/** Table rows (to render inside the grid's <tbody>): one per shift template
 *  that has coverage cells in view. When several requirements hit the same
 *  (shift, date) each is shown stacked, with its own tooltip. */
export const CoverageRows = ({
  dates,
  templates,
  coverage,
}: {
  dates: string[];
  templates: ShiftTemplateLite[];
  coverage: CoverageCell[];
}) => {
  const byShift = new Map<number, Map<string, CoverageCell[]>>();
  for (const c of coverage) {
    const m = byShift.get(c.shift_template_id) || new Map<string, CoverageCell[]>();
    const l = m.get(c.date) || [];
    l.push(c);
    m.set(c.date, l);
    byShift.set(c.shift_template_id, m);
  }
  const name = (id: number) =>
    templates.find((t) => t.id === id)?.name ||
    coverage.find((c) => c.shift_template_id === id)?.shift_name ||
    `Shift #${id}`;
  return (
    <>
      {[...byShift.entries()].map(([sid, m]) => (
        <tr key={`cov-${sid}`} className="border-b bg-gray-50">
          <td className="sticky left-0 z-10 bg-gray-50 px-3 py-1.5 border-r text-xs text-gray-600">
            <div className="font-medium">Coverage: {name(sid)}</div>
            <div className="text-[10px] text-gray-400">scheduled / min</div>
          </td>
          {dates.map((d) => (
            <td key={d} className="px-1.5 py-1 text-center align-top">
              {(m.get(d) || []).map((c, i) => (
                <div
                  key={i}
                  title={tip(c)}
                  className={cn(
                    'text-[11px] font-medium rounded px-1 py-0.5 mb-0.5',
                    STATUS_CLS[c.status] || ''
                  )}
                >
                  {c.scheduled}/{c.required_min}
                  {c.required_max != null && ` ≤${c.required_max}`}
                </div>
              ))}
            </td>
          ))}
        </tr>
      ))}
    </>
  );
};
