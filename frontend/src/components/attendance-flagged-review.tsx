import React, { useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  Moon,
  RefreshCw,
  Search,
  Calendar,
  Filter,
  CheckCircle2,
} from 'lucide-react';
import { Card, Button, Badge, cn } from './ui-elements';
import { toast } from 'sonner@2.0.3';
import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';

interface FlaggedRecord {
  id: number;
  user_id: number;
  user_name?: string | null;
  user_email?: string | null;
  captured_at: string;
  punch_out_time: string | null;
  work_date: string | null;
  shift_template_id: number | null;
  shift_template_name?: string | null;
  is_cross_midnight: boolean;
  attribution_flag: string | null;
}

const FLAG_META: Record<
  string,
  { label: string; tone: string; description: string }
> = {
  no_shift: {
    label: 'No Shift',
    tone: 'bg-slate-100 text-slate-700',
    description:
      'Employee has no shift assignment on this date — record uses calendar-date fallback.',
  },
  outside_window: {
    label: 'Outside Window',
    tone: 'bg-amber-100 text-amber-800',
    description:
      'Punch fell outside the expected window for the assigned shift (incl. grace).',
  },
  ambiguous: {
    label: 'Ambiguous',
    tone: 'bg-rose-100 text-rose-800',
    description:
      'Punch matched more than one shift window. The resolver picked the nearer one.',
  },
};

const errMsg = (err: any, fallback: string): string => {
  const detail = err?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail))
    return detail.map((d: any) => d?.msg || JSON.stringify(d)).join('; ');
  return err?.message || fallback;
};

const fmtTs = (ts: string | null): string => {
  if (!ts) return '—';
  try {
    return new Date(ts).toLocaleString(undefined, {
      year: 'numeric',
      month: 'short',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return ts;
  }
};

const toISODate = (d: Date) => d.toISOString().slice(0, 10);

const daysAgo = (n: number) => {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return toISODate(d);
};

export const AttendanceFlaggedReview: React.FC = () => {
  const [items, setItems] = useState<FlaggedRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [dateFrom, setDateFrom] = useState(daysAgo(30));
  const [dateTo, setDateTo] = useState(toISODate(new Date()));
  const [flagFilter, setFlagFilter] = useState<string>('');
  const [search, setSearch] = useState('');

  const fetchItems = async () => {
    setLoading(true);
    try {
      const params: any = { date_from: dateFrom, date_to: dateTo };
      if (flagFilter) params.flag = flagFilter;
      const res = await client.get(ENDPOINTS.ATTENDANCE.FLAGGED, { params });
      setItems(res.data || []);
    } catch (e: any) {
      toast.error(errMsg(e, 'Failed to load flagged records'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchItems();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dateFrom, dateTo, flagFilter]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return items;
    return items.filter(
      (i) =>
        (i.user_name || '').toLowerCase().includes(q) ||
        (i.user_email || '').toLowerCase().includes(q) ||
        (i.shift_template_name || '').toLowerCase().includes(q),
    );
  }, [items, search]);

  const counts = useMemo(() => {
    const c = { no_shift: 0, outside_window: 0, ambiguous: 0 };
    items.forEach((i) => {
      if (i.attribution_flag && i.attribution_flag in c) {
        (c as any)[i.attribution_flag] += 1;
      }
    });
    return c;
  }, [items]);

  return (
    <div className="p-8 space-y-6 max-w-[1600px] mx-auto animate-in fade-in duration-300">
      <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-4">
        <div>
          <h2 className="text-3xl font-black text-[#0F172A] tracking-tighter uppercase">
            Attendance Review Queue
          </h2>
          <p className="text-[#64748B] font-bold uppercase tracking-widest text-[10px] mt-1">
            Punches The Shift Resolver Wasn't Confident About
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={fetchItems}
            className="p-2 text-slate-400 hover:text-blue-600 transition-colors"
            title="Refresh"
            aria-label="Refresh"
          >
            <RefreshCw size={16} className={cn(loading && 'animate-spin')} />
          </button>
        </div>
      </div>

      {/* Count tiles */}
      <div className="grid grid-cols-3 gap-3">
        {(['no_shift', 'outside_window', 'ambiguous'] as const).map((k) => (
          <Card
            key={k}
            className="p-4 border-slate-200 flex items-center justify-between"
          >
            <div>
              <div className="text-[10px] font-black uppercase tracking-widest text-slate-500">
                {FLAG_META[k].label}
              </div>
              <div className="text-3xl font-black text-[#0F172A] tabular-nums mt-1">
                {counts[k as keyof typeof counts]}
              </div>
            </div>
            <button
              type="button"
              onClick={() => setFlagFilter(flagFilter === k ? '' : k)}
              className={cn(
                'text-[9px] font-black uppercase tracking-widest px-2.5 py-1.5 rounded-lg transition-colors',
                flagFilter === k
                  ? 'bg-blue-600 text-white'
                  : 'bg-slate-100 text-slate-600 hover:bg-slate-200',
              )}
            >
              {flagFilter === k ? 'Showing' : 'Show'}
            </button>
          </Card>
        ))}
      </div>

      <Card className="p-0 border-slate-200 overflow-hidden bg-white">
        <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between bg-slate-50/40 gap-4 flex-wrap">
          <div className="flex items-center gap-3 flex-wrap">
            <h4 className="text-sm font-black text-[#0F172A] tracking-tight uppercase">
              Flagged Records
              {!loading && (
                <span className="ml-2 text-slate-400 font-bold text-[10px]">
                  ({filtered.length}/{items.length})
                </span>
              )}
            </h4>
            <div className="flex items-center gap-1.5">
              <Calendar size={12} className="text-slate-400" />
              <input
                type="date"
                value={dateFrom}
                onChange={(e) => setDateFrom(e.target.value)}
                className="h-9 px-2 bg-white border border-slate-200 rounded-xl text-[10px] font-black uppercase tracking-widest outline-none"
              />
              <span className="text-[9px] text-slate-400 font-bold">to</span>
              <input
                type="date"
                value={dateTo}
                onChange={(e) => setDateTo(e.target.value)}
                className="h-9 px-2 bg-white border border-slate-200 rounded-xl text-[10px] font-black uppercase tracking-widest outline-none"
              />
            </div>
            {flagFilter && (
              <span className="inline-flex items-center gap-1 text-[10px] font-black uppercase tracking-widest px-2.5 py-1 bg-blue-50 text-blue-700 rounded-lg">
                <Filter size={10} /> {FLAG_META[flagFilter]?.label}
                <button
                  type="button"
                  onClick={() => setFlagFilter('')}
                  className="ml-1 text-blue-400 hover:text-blue-700"
                >
                  ×
                </button>
              </span>
            )}
          </div>
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 pointer-events-none" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search name, email, shift..."
              className="pl-10 pr-4 h-9 bg-white border border-slate-200 rounded-xl text-[10px] font-black uppercase tracking-widest w-72 focus:ring-2 focus:ring-blue-600/10 outline-none"
            />
          </div>
        </div>

        {loading ? (
          <div className="py-16 text-center text-[10px] font-black uppercase tracking-widest text-slate-400 animate-pulse">
            Loading…
          </div>
        ) : filtered.length === 0 ? (
          <div className="py-16 flex flex-col items-center gap-2 text-slate-400">
            <CheckCircle2 size={28} className="text-emerald-500" />
            <div className="text-[10px] font-black uppercase tracking-widest">
              No flagged records in this range — every punch resolved cleanly.
            </div>
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
                    Work Date
                  </th>
                  <th className="px-6 py-3 text-[9px] font-black text-slate-400 uppercase tracking-widest">
                    Shift
                  </th>
                  <th className="px-6 py-3 text-[9px] font-black text-slate-400 uppercase tracking-widest">
                    Punches
                  </th>
                  <th className="px-6 py-3 text-[9px] font-black text-slate-400 uppercase tracking-widest">
                    Flag
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {filtered.map((r) => {
                  const meta = r.attribution_flag
                    ? FLAG_META[r.attribution_flag]
                    : null;
                  return (
                    <tr
                      key={r.id}
                      className="hover:bg-slate-50/60 transition-colors"
                    >
                      <td className="px-6 py-3">
                        <div className="text-sm font-black text-[#0F172A]">
                          {r.user_name || `User #${r.user_id}`}
                        </div>
                        {r.user_email && (
                          <div className="text-[10px] font-bold text-slate-400">
                            {r.user_email}
                          </div>
                        )}
                      </td>
                      <td className="px-6 py-3 text-sm font-black text-[#0F172A] tabular-nums">
                        {r.work_date || '—'}
                        {r.is_cross_midnight && (
                          <span className="ml-2 inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md bg-indigo-50 text-indigo-700 text-[9px] font-black uppercase tracking-widest">
                            <Moon size={9} /> crosses
                          </span>
                        )}
                      </td>
                      <td className="px-6 py-3 text-[11px] font-bold text-slate-700">
                        {r.shift_template_name || (
                          <span className="text-slate-400 italic">none</span>
                        )}
                      </td>
                      <td className="px-6 py-3 text-[11px] font-bold text-slate-700 tabular-nums">
                        <div>In: {fmtTs(r.captured_at)}</div>
                        <div className="text-slate-500">
                          Out: {fmtTs(r.punch_out_time)}
                        </div>
                      </td>
                      <td className="px-6 py-3">
                        {meta ? (
                          <span
                            className={cn(
                              'inline-flex items-center gap-1 px-2 py-1 rounded-md text-[9px] font-black uppercase tracking-widest',
                              meta.tone,
                            )}
                            title={meta.description}
                          >
                            <AlertTriangle size={9} /> {meta.label}
                          </span>
                        ) : (
                          <Badge variant="success" className="text-[8px] uppercase">
                            OK
                          </Badge>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card className="p-4 border-slate-200 bg-blue-50/40 border-blue-100">
        <div className="flex gap-3 items-start">
          <Filter className="text-blue-600 mt-0.5" size={16} />
          <div className="flex-1 text-[11px] text-slate-700 leading-relaxed">
            <strong className="text-[#0F172A]">How to clear these:</strong>{' '}
            Use the existing <em>Attendance Corrections</em> flow. A correction
            request can now include a <code>requested_work_date</code> — when
            HR approves, the underlying record is retagged to the corrected
            logical date and the flag is cleared automatically.
          </div>
        </div>
      </Card>
    </div>
  );
};
