import React, { useState, useMemo, useEffect } from 'react';
import { ChevronDown, X } from 'lucide-react';
import { DayPicker, type DateRange as DayPickerRange } from 'react-day-picker';
import { Popover, PopoverTrigger, PopoverContent } from './ui/popover';
import { Button, cn } from './ui-elements';

export interface DateRange {
  from: Date;
  to: Date;
}

export type PresetId =
  | 'today'
  | 'yesterday'
  | 'this_week'
  | 'last_week'
  | 'this_month'
  | 'last_month'
  | 'this_quarter'
  | 'ytd'
  | 'custom';

const PRESETS: { id: PresetId; label: string }[] = [
  { id: 'today', label: 'Today' },
  { id: 'yesterday', label: 'Yesterday' },
  { id: 'this_week', label: 'This Week' },
  { id: 'last_week', label: 'Last Week' },
  { id: 'this_month', label: 'This Month' },
  { id: 'last_month', label: 'Last Month' },
  { id: 'this_quarter', label: 'This Quarter' },
  { id: 'ytd', label: 'Year to Date' },
  { id: 'custom', label: 'Custom' },
];

const startOfDay = (d: Date): Date =>
  new Date(d.getFullYear(), d.getMonth(), d.getDate());

export function presetToRange(p: PresetId, today: Date = new Date()): DateRange {
  const t = startOfDay(today);
  switch (p) {
    case 'today':
      return { from: t, to: t };
    case 'yesterday': {
      const y = new Date(t);
      y.setDate(t.getDate() - 1);
      return { from: y, to: y };
    }
    case 'this_week': {
      const day = t.getDay() || 7;
      const monday = new Date(t);
      monday.setDate(t.getDate() - (day - 1));
      return { from: monday, to: t };
    }
    case 'last_week': {
      const day = t.getDay() || 7;
      const lastSunday = new Date(t);
      lastSunday.setDate(t.getDate() - day);
      const lastMonday = new Date(lastSunday);
      lastMonday.setDate(lastSunday.getDate() - 6);
      return { from: lastMonday, to: lastSunday };
    }
    case 'this_month':
      return { from: new Date(t.getFullYear(), t.getMonth(), 1), to: t };
    case 'last_month': {
      const start = new Date(t.getFullYear(), t.getMonth() - 1, 1);
      const end = new Date(t.getFullYear(), t.getMonth(), 0);
      return { from: start, to: end };
    }
    case 'this_quarter': {
      const q = Math.floor(t.getMonth() / 3);
      return { from: new Date(t.getFullYear(), q * 3, 1), to: t };
    }
    case 'ytd':
      return { from: new Date(t.getFullYear(), 0, 1), to: t };
    case 'custom':
    default:
      return { from: t, to: t };
  }
}

export function toIsoDate(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

export function fromIsoDate(s: string): Date {
  const [y, m, d] = s.split('-').map(Number);
  return new Date(y, m - 1, d);
}

export function formatRangeLabel(r: DateRange): string {
  const fmt = (d: Date) =>
    d.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' });
  const same = startOfDay(r.from).getTime() === startOfDay(r.to).getTime();
  return same ? fmt(r.from) : `${fmt(r.from)} – ${fmt(r.to)}`;
}

export function countDays(r: DateRange): number {
  const ms = startOfDay(r.to).getTime() - startOfDay(r.from).getTime();
  return Math.floor(ms / 86_400_000) + 1;
}

export function countByCategory(
  r: DateRange,
  holidays: Set<string> = new Set(),
): { working: number; weekend: number; holiday: number } {
  let working = 0,
    weekend = 0,
    holiday = 0;
  const cursor = new Date(r.from);
  cursor.setHours(0, 0, 0, 0);
  const end = new Date(r.to);
  end.setHours(0, 0, 0, 0);
  while (cursor <= end) {
    // Sunday only — Saturdays count as working days.
    const day = cursor.getDay();
    const iso = toIsoDate(cursor);
    if (day === 0) weekend++;
    else if (holidays.has(iso)) holiday++;
    else working++;
    cursor.setDate(cursor.getDate() + 1);
  }
  return { working, weekend, holiday };
}

interface PeriodPickerProps {
  value: DateRange;
  onChange: (range: DateRange) => void;
  holidays?: Set<string>;
  className?: string;
  align?: 'start' | 'end' | 'center';
  initialPreset?: PresetId;
}

export const PeriodPicker: React.FC<PeriodPickerProps> = ({
  value,
  onChange,
  holidays = new Set(),
  className,
  align = 'start',
  initialPreset = 'custom',
}) => {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<DateRange>(value);
  const [activePreset, setActivePreset] = useState<PresetId>(initialPreset);

  useEffect(() => {
    if (open) {
      setDraft(value);
      setActivePreset('custom');
    }
  }, [open, value]);

  const stats = useMemo(() => countByCategory(draft, holidays), [draft, holidays]);
  const totalDays = useMemo(() => countDays(draft), [draft]);
  const holidayDates = useMemo(
    () => Array.from(holidays).map(fromIsoDate),
    [holidays],
  );

  const apply = () => {
    onChange(draft);
    setOpen(false);
  };
  const cancel = () => setOpen(false);

  const handlePreset = (id: PresetId) => {
    if (id === 'custom') {
      setActivePreset('custom');
      return;
    }
    setDraft(presetToRange(id));
    setActivePreset(id);
  };

  const handleCalendar = (rng: DayPickerRange | undefined) => {
    if (!rng?.from) return;
    const from = startOfDay(rng.from);
    const to = startOfDay(rng.to ?? rng.from);
    setDraft({ from, to });
    setActivePreset('custom');
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          className={cn(
            'inline-flex items-center gap-2 px-4 py-2 bg-white border border-slate-200 rounded-xl text-[10px] font-black uppercase tracking-widest text-[#0F172A] hover:border-blue-600 transition-colors',
            className,
          )}
        >
          <span className="text-slate-400">PERIOD</span>
          <span>{formatRangeLabel(value)}</span>
          <span className="text-slate-300">·</span>
          <span className="text-blue-600">{countDays(value)}D</span>
          <ChevronDown size={12} className="text-slate-400" />
        </button>
      </PopoverTrigger>
      <PopoverContent
        align={align}
        sideOffset={8}
        style={{ maxHeight: 'unset', overflowY: 'visible' }}
        className="w-auto p-0 rounded-2xl border-slate-200 shadow-2xl shadow-slate-900/10"
      >
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-100">
          <h4 className="text-[10px] font-black uppercase tracking-widest text-[#0F172A]">
            Select Period
          </h4>
          <button
            type="button"
            onClick={cancel}
            className="text-slate-400 hover:text-slate-700"
            aria-label="Close period picker"
          >
            <X size={14} />
          </button>
        </div>
        <div className="flex">
          <div className="w-44 border-r border-slate-100 p-2 space-y-0.5 bg-slate-50/40">
            {PRESETS.map((p) => (
              <button
                key={p.id}
                type="button"
                onClick={() => handlePreset(p.id)}
                className={cn(
                  'w-full text-left px-3 py-2 rounded-lg text-[10px] font-black uppercase tracking-widest transition-colors',
                  activePreset === p.id
                    ? 'bg-blue-600 text-white'
                    : 'text-slate-600 hover:bg-white hover:text-[#0F172A]',
                )}
              >
                {p.label}
              </button>
            ))}
          </div>
          <div className="p-3">
            <DayPicker
              mode="range"
              numberOfMonths={2}
              selected={{ from: draft.from, to: draft.to }}
              onSelect={handleCalendar}
              weekStartsOn={1}
              showOutsideDays
              modifiers={{ holiday: holidayDates }}
              modifiersClassNames={{
                holiday: 'rdp-day_holiday',
              }}
              classNames={{
                months: 'flex gap-6',
                month: 'flex flex-col gap-3',
                caption:
                  'flex justify-center pt-1 relative items-center text-[11px] font-black uppercase tracking-widest text-[#0F172A]',
                caption_label: 'text-[11px] font-black uppercase tracking-widest',
                nav: 'flex items-center gap-1',
                nav_button:
                  'h-7 w-7 rounded-lg text-slate-400 hover:bg-slate-100 hover:text-[#0F172A] inline-flex items-center justify-center transition-colors',
                nav_button_previous: 'absolute left-1',
                nav_button_next: 'absolute right-1',
                table: 'w-full border-collapse',
                head_row: 'flex',
                head_cell:
                  'w-9 h-7 text-[9px] font-black text-slate-400 uppercase tracking-widest flex items-center justify-center',
                row: 'flex w-full mt-1',
                cell: 'relative w-9 h-9 p-0 text-center',
                day: 'w-9 h-9 inline-flex items-center justify-center text-[11px] font-black text-slate-700 rounded-lg hover:bg-slate-100 transition-colors',
                day_selected:
                  'bg-blue-600 text-white hover:bg-blue-600 hover:text-white',
                day_range_start:
                  'bg-blue-600 text-white rounded-l-lg rounded-r-none',
                day_range_end:
                  'bg-blue-600 text-white rounded-r-lg rounded-l-none',
                day_range_middle:
                  'bg-blue-50 text-blue-700 rounded-none hover:bg-blue-100',
                day_today: 'ring-2 ring-blue-600/30',
                day_outside: 'text-slate-300',
                day_disabled: 'text-slate-300 opacity-50',
                day_hidden: 'invisible',
              }}
            />
          </div>
        </div>
        <div className="flex items-center justify-between px-5 py-3 border-t border-slate-100 bg-slate-50/40 gap-4">
          <div className="text-[9px] font-black uppercase tracking-widest text-slate-500 tabular-nums">
            <span className="text-[#0F172A]">{stats.working}</span> WORKING
            <span className="text-slate-300 mx-1.5">·</span>
            <span className="text-[#0F172A]">{stats.holiday}</span> HOLIDAY
            <span className="text-slate-300 mx-1.5">·</span>
            <span className="text-[#0F172A]">{stats.weekend}</span> WEEKEND
            <span className="text-slate-300 mx-1.5">·</span>
            <span className="text-[#0F172A]">{totalDays}</span> TOTAL
          </div>
          <div className="flex gap-2">
            <Button
              variant="ghost"
              onClick={cancel}
              className="h-8 px-4 text-[9px] font-black uppercase tracking-widest"
            >
              Cancel
            </Button>
            <Button
              onClick={apply}
              className="h-8 px-5 bg-blue-600 hover:bg-blue-700 text-white text-[9px] font-black uppercase tracking-widest shadow-lg shadow-blue-600/20"
            >
              Apply
            </Button>
          </div>
        </div>
      </PopoverContent>
    </Popover>
  );
};
