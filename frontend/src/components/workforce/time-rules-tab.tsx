import React, { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Clock3, Save } from 'lucide-react';
import { Card, Button } from '../ui-elements';
import { client } from '../../api/client';
import { ENDPOINTS } from '../../api/endpoints';

// Section Q: org-level attendance time rules (flag & report). Employees
// WITH a shift use their shift's own grace; these are the org defaults
// for everyone else, plus the master flag toggle.

type Rules = Record<string, string>;

const FIELDS: {
  key: string;
  label: string;
  hint: string;
  type: 'time' | 'number';
}[] = [
  {
    key: 'attendance.default_start_time',
    label: 'Default Start Time',
    hint: 'Workday start for employees with no shift assigned',
    type: 'time',
  },
  {
    key: 'attendance.default_end_time',
    label: 'Default End Time',
    hint: 'Workday end for employees with no shift assigned',
    type: 'time',
  },
  {
    key: 'attendance.late_grace_minutes',
    label: 'Late Grace (minutes)',
    hint: 'Punch-in later than start + grace is flagged Late',
    type: 'number',
  },
  {
    key: 'attendance.early_exit_grace_minutes',
    label: 'Early Exit Grace (minutes)',
    hint: 'Punch-out earlier than end − grace is flagged Early',
    type: 'number',
  },
];

const SCHEDULE_FIELDS: { key: string; label: string; hint: string; max: number }[] = [
  { key: 'schedule.min_rest_hours', label: 'Minimum Rest (hours)', hint: 'Minimum gap between consecutive shifts. 0 = off (range 0–24)', max: 24 },
  { key: 'schedule.max_consecutive_days', label: 'Max Consecutive Days', hint: 'Longest run of working days. 0 = off (range 0–31)', max: 31 },
  { key: 'schedule.max_consecutive_nights', label: 'Max Consecutive Nights', hint: 'Longest run of night shifts. 0 = off (range 0–31)', max: 31 },
  { key: 'schedule.max_weekly_hours', label: 'Max Weekly Hours', hint: 'Scheduled hours per week. 0 = off (range 0–168)', max: 168 },
  { key: 'schedule.no_show_minutes', label: 'No-show After (minutes)', hint: 'Minutes after shift start with no punch-in before a no-show alert. 0 = no automatic alerts; the board still shows missed shifts after they end (range 0–240)', max: 240 },
  { key: 'schedule.lock_days', label: 'Schedule Lock Window (days)', hint: 'Published shifts from today up to this many days ahead can only be changed by HR/admin or an emergency-override delegate, with a reason; the employee must acknowledge. 0 = off (range 0–30)', max: 30 },
];

const LEAVE_FIELDS: { key: string; label: string; hint: string; max: number }[] = [
  { key: 'leave.emergency_backdate_days', label: 'Emergency Leave Back-date (days)', hint: 'Emergency leave may start this many days in the past (range 0–31)', max: 31 },
  { key: 'leave.emergency_proof_days', label: 'Emergency Proof Deadline (days)', hint: 'Days after leave end to submit a required medical certificate, else it becomes LOP. 0 = attach it upfront (range 0–60)', max: 60 },
];

const inputCls =
  'w-full h-10 px-3 rounded-lg border border-slate-200 text-sm text-[#0F172A] ' +
  'focus:outline-none focus:ring-2 focus:ring-blue-600/30 focus:border-blue-500 bg-white';

export const TimeRulesTab: React.FC = () => {
  const [rules, setRules] = useState<Rules>({});
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const res = await client.get(ENDPOINTS.HR.TIME_RULES);
        setRules(res.data?.rules ?? {});
      } catch {
        toast.error('Failed to load time rules');
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const enabled = rules['attendance.enable_late_flags'] === '1';
  const absenceLop = ['1', 'true', 'yes', 'on'].includes(
    (rules['attendance.absence_lop_enabled'] ?? '').trim().toLowerCase(),
  );

  const weekoffCompOff = ['1', 'true', 'yes', 'on'].includes(
    (rules['attendance.weekoff_comp_off_enabled'] ?? '').trim().toLowerCase(),
  );

  const save = async () => {
    for (const f of [...SCHEDULE_FIELDS, ...LEAVE_FIELDS]) {
      const raw = (rules[f.key] ?? '').toString().trim();
      if (raw === '') {
        toast.error(`${f.label} is required (enter 0 to turn it off)`);
        return;
      }
      const n = Number(raw);
      if (!/^\d+$/.test(raw) || !Number.isInteger(n) || n < 0 || n > f.max) {
        toast.error(`${f.label} must be a whole number from 0 to ${f.max}`);
        return;
      }
    }
    const amt = Number((rules['schedule.callback_allowance_amount'] ?? '0').toString().trim());
    if (!Number.isFinite(amt) || amt < 0) {
      toast.error('Call-back allowance must be a number of 0 or more');
      return;
    }
    setBusy(true);
    try {
      const res = await client.put(ENDPOINTS.HR.TIME_RULES, { rules });
      setRules(res.data?.rules ?? rules);
      toast.success('Time rules saved');
    } catch (e: any) {
      toast.error(
        e?.response?.data?.detail ||
          e?.response?.data?.error?.message ||
          'Failed to save time rules',
      );
    } finally {
      setBusy(false);
    }
  };

  if (loading) {
    return (
      <p className="text-[10px] font-black uppercase tracking-widest text-slate-400 py-12 text-center">
        Loading time rules…
      </p>
    );
  }

  return (
    <div className="max-w-2xl space-y-4">
      <Card className="p-6 border-slate-200 bg-white space-y-5">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h3 className="text-sm font-black uppercase tracking-tight text-[#0F172A] inline-flex items-center gap-2">
              <Clock3 size={15} className="text-blue-600" /> Late / Early Flags
            </h3>
            <p className="text-[10px] font-bold text-slate-500 mt-1">
              Flags appear on attendance records — no automatic pay impact.
              Shift-assigned employees use their shift's own grace settings.
            </p>
          </div>
          <label className="inline-flex items-center gap-2 cursor-pointer select-none shrink-0">
            <input
              type="checkbox"
              checked={enabled}
              onChange={(e) =>
                setRules({
                  ...rules,
                  'attendance.enable_late_flags': e.target.checked ? '1' : '0',
                })
              }
              className="w-4 h-4 accent-blue-600"
            />
            <span className="text-[9px] font-black uppercase tracking-widest text-slate-600">
              {enabled ? 'Enabled' : 'Disabled'}
            </span>
          </label>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {FIELDS.map((f) => (
            <div key={f.key} className="space-y-1">
              <label className="text-[9px] font-black uppercase tracking-widest text-slate-400">
                {f.label}
              </label>
              <input
                type={f.type}
                min={f.type === 'number' ? 0 : undefined}
                className={inputCls}
                value={rules[f.key] ?? ''}
                onChange={(e) => setRules({ ...rules, [f.key]: e.target.value })}
              />
              <p className="text-[9px] font-bold text-slate-400">{f.hint}</p>
            </div>
          ))}
        </div>
      </Card>
      <Card className="p-6 border-slate-200 bg-white space-y-5">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h3 className="text-sm font-black uppercase tracking-tight text-[#0F172A] inline-flex items-center gap-2">
              <Clock3 size={15} className="text-blue-600" /> Absence LOP
            </h3>
            <p className="text-[10px] font-bold text-slate-500 mt-1">
              Count unexplained absences on scheduled working days as LOP in
              payroll. Holidays, week-offs and approved leave are excused.
            </p>
          </div>
          <label className="inline-flex items-center gap-2 cursor-pointer select-none shrink-0">
            <input
              type="checkbox"
              aria-label="Count unexplained absences as LOP in payroll"
              checked={absenceLop}
              onChange={(e) =>
                setRules({
                  ...rules,
                  'attendance.absence_lop_enabled': e.target.checked ? '1' : '0',
                })
              }
              className="w-4 h-4 accent-blue-600"
            />
            <span className="text-[9px] font-black uppercase tracking-widest text-slate-600">
              {absenceLop ? 'Enabled' : 'Disabled'}
            </span>
          </label>
        </div>

        <div className="flex items-start justify-between gap-4">
          <div>
            <h3 className="text-sm font-black uppercase tracking-tight text-[#0F172A] inline-flex items-center gap-2">
              <Clock3 size={15} className="text-blue-600" /> Week-off Comp-off
            </h3>
            <p className="text-[10px] font-bold text-slate-500 mt-1">
              Grant a comp-off accrual (manager and HR approval) when an
              employee works a rostered week-off for at least 6.5 hours.
            </p>
          </div>
          <label className="inline-flex items-center gap-2 cursor-pointer select-none shrink-0">
            <input
              type="checkbox"
              aria-label="Grant comp-off for work on a rostered week-off"
              checked={weekoffCompOff}
              onChange={(e) =>
                setRules({
                  ...rules,
                  'attendance.weekoff_comp_off_enabled': e.target.checked ? '1' : '0',
                })
              }
              className="w-4 h-4 accent-blue-600"
            />
            <span className="text-[9px] font-black uppercase tracking-widest text-slate-600">
              {weekoffCompOff ? 'Enabled' : 'Disabled'}
            </span>
          </label>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div className="space-y-1">
            <label className="text-[9px] font-black uppercase tracking-widest text-slate-400">
              Default Weekly Offs
            </label>
            <input
              type="text"
              className={inputCls}
              placeholder="e.g. 6 for Sunday, 5,6 for Sat+Sun"
              value={rules['attendance.default_weekly_offs'] ?? ''}
              onChange={(e) =>
                setRules({ ...rules, 'attendance.default_weekly_offs': e.target.value })
              }
            />
            <p className="text-[9px] font-bold text-slate-400">
              Comma-separated weekdays off for employees with no shift (Mon=0 … Sun=6)
            </p>
          </div>
        </div>
      </Card>

      <Card className="p-6 border-slate-200 bg-white space-y-5">
        <div>
          <h3 className="text-sm font-black uppercase tracking-tight text-[#0F172A] inline-flex items-center gap-2">
            <Clock3 size={15} className="text-blue-600" /> Scheduling rules
          </h3>
          <p className="text-[10px] font-bold text-slate-500 mt-1">
            Roster planner warns when a schedule breaks these limits. Warnings
            never block saving. Whole numbers; 0 = off.
          </p>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {SCHEDULE_FIELDS.map((f) => (
            <div key={f.key} className="space-y-1">
              <label
                htmlFor={f.key}
                className="text-[9px] font-black uppercase tracking-widest text-slate-400"
              >
                {f.label}
              </label>
              <input
                id={f.key}
                type="number"
                min={0}
                max={f.max}
                step={1}
                className={inputCls}
                value={rules[f.key] ?? ''}
                onChange={(e) => setRules({ ...rules, [f.key]: e.target.value })}
              />
              <p className="text-[9px] font-bold text-slate-400">{f.hint}</p>
            </div>
          ))}
        </div>
      </Card>

      <Card className="p-6 border-slate-200 bg-white space-y-5">
        <div>
          <h3 className="text-sm font-black uppercase tracking-tight text-[#0F172A] inline-flex items-center gap-2">
            <Clock3 size={15} className="text-blue-600" /> Call-back compensation
          </h3>
          <p className="text-[10px] font-bold text-slate-500 mt-1">
            When an emergency change (inside the lock window) calls an employee
            in on a day off. Not reversed if the change is later undone.
          </p>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div className="space-y-1">
            <label
              htmlFor="schedule.callback_compensation"
              className="text-[9px] font-black uppercase tracking-widest text-slate-400"
            >
              Compensation
            </label>
            <select
              id="schedule.callback_compensation"
              className={inputCls}
              value={rules['schedule.callback_compensation'] ?? 'none'}
              onChange={(e) =>
                setRules({ ...rules, 'schedule.callback_compensation': e.target.value })
              }
            >
              <option value="none">None</option>
              <option value="comp_off">Comp-off (manager → HR approval)</option>
              <option value="allowance">Allowance (added to payroll)</option>
            </select>
          </div>
          <div className="space-y-1">
            <label
              htmlFor="schedule.callback_allowance_amount"
              className="text-[9px] font-black uppercase tracking-widest text-slate-400"
            >
              Allowance per call-back day
            </label>
            <input
              id="schedule.callback_allowance_amount"
              type="number"
              min={0}
              step="0.01"
              className={inputCls}
              value={rules['schedule.callback_allowance_amount'] ?? '0'}
              onChange={(e) =>
                setRules({ ...rules, 'schedule.callback_allowance_amount': e.target.value })
              }
            />
            <p className="text-[9px] font-bold text-slate-400">
              Used when compensation is Allowance (0 or more)
            </p>
          </div>
        </div>
      </Card>

      <Card className="p-6 border-slate-200 bg-white space-y-5">
        <div>
          <h3 className="text-sm font-black uppercase tracking-tight text-[#0F172A] inline-flex items-center gap-2">
            <Clock3 size={15} className="text-blue-600" /> Emergency leave
          </h3>
          <p className="text-[10px] font-bold text-slate-500 mt-1">
            Same-day / back-dated leave. A medical certificate the leave type
            requires can be submitted afterwards; overdue, it converts the leave to loss of pay. Whole numbers.
          </p>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {LEAVE_FIELDS.map((f) => (
            <div key={f.key} className="space-y-1">
              <label
                htmlFor={f.key}
                className="text-[9px] font-black uppercase tracking-widest text-slate-400"
              >
                {f.label}
              </label>
              <input
                id={f.key}
                type="number"
                min={0}
                max={f.max}
                step={1}
                className={inputCls}
                value={rules[f.key] ?? ''}
                onChange={(e) => setRules({ ...rules, [f.key]: e.target.value })}
              />
              <p className="text-[9px] font-bold text-slate-400">{f.hint}</p>
            </div>
          ))}
        </div>
      </Card>

      <div className="flex justify-end pt-1">
        <Button onClick={save} isLoading={busy}>
          <Save size={13} className="mr-2" /> Save Rules
        </Button>
      </div>
    </div>
  );
};
