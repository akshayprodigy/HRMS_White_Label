import React, { useState, useEffect, useCallback } from 'react';
import {
  Cake,
  Award,
  PartyPopper,
  Mail,
  Clock,
  CheckCircle2,
  Building2,
} from 'lucide-react';
import { Card, Button, Badge, cn } from './ui-elements';
import { toast } from 'sonner';
import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';

interface CelebrationRow {
  id: number;
  user_id: number;
  employee_code: string;
  full_name: string;
  designation: string;
  department: string;
  date: string;
  original_date: string;
  days_away: number;
  age?: number;
  years?: number;
  letter_generated: boolean;
}

interface ReportData {
  start: string;
  end: string;
  birthdays: CelebrationRow[];
  anniversaries: CelebrationRow[];
  counts: {
    birthdays: number;
    anniversaries: number;
    total: number;
    by_department: Record<string, { birthdays: number; anniversaries: number }>;
  };
}

const monthDefaults = () => {
  const now = new Date();
  const first = new Date(now.getFullYear(), now.getMonth(), 1);
  const last = new Date(now.getFullYear(), now.getMonth() + 1, 0);
  const iso = (d: Date) =>
    `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(
      d.getDate()
    ).padStart(2, '0')}`;
  return { start: iso(first), end: iso(last) };
};

const fmtDate = (iso: string) =>
  new Date(iso + 'T00:00:00').toLocaleDateString('en-IN', {
    day: '2-digit',
    month: 'short',
  });

export const CelebrationsReport = () => {
  const def = monthDefaults();
  const [start, setStart] = useState(def.start);
  const [end, setEnd] = useState(def.end);
  const [department, setDepartment] = useState('');
  const [data, setData] = useState<ReportData | null>(null);
  const [loading, setLoading] = useState(false);
  const [bulkKind, setBulkKind] = useState<'birthday' | 'anniversary' | null>(
    null
  );
  const [rowBusy, setRowBusy] = useState<number | null>(null);

  const fetchReport = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ start, end, kind: 'all' });
      if (department) params.set('department', department);
      const res = await client.get<ReportData>(
        ENDPOINTS.HR.CELEBRATIONS_REPORT + '?' + params.toString()
      );
      setData(res.data);
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Failed to load report');
    } finally {
      setLoading(false);
    }
  }, [start, end, department]);

  useEffect(() => {
    fetchReport();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const generateBulk = async (kind: 'birthday' | 'anniversary') => {
    setBulkKind(kind);
    try {
      const res = await client.post(ENDPOINTS.HR.CELEBRATION_LETTERS_BULK, {
        start,
        end,
        kind,
      });
      const c = (res.data as any).counts;
      toast.success(
        `${c.generated} letter(s) generated, ${c.skipped} already existed`
      );
      fetchReport();
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Bulk generation failed');
    } finally {
      setBulkKind(null);
    }
  };

  const generateOne = async (
    row: CelebrationRow,
    kind: 'birthday' | 'anniversary'
  ) => {
    setRowBusy(row.id);
    try {
      const res = await client.post(ENDPOINTS.HR.CELEBRATION_LETTERS_BULK, {
        start,
        end,
        kind,
        employee_ids: [row.id],
      });
      const c = (res.data as any).counts;
      if (c.generated > 0) {
        toast.success(`Letter generated for ${row.full_name}`);
      } else {
        toast.info('Letter already existed for this occasion');
      }
      fetchReport();
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Failed to generate');
    } finally {
      setRowBusy(null);
    }
  };

  const renderTable = (
    rows: CelebrationRow[],
    kind: 'birthday' | 'anniversary'
  ) => (
    <Card className="overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 bg-gray-50 border-b">
        <div className="flex items-center gap-2">
          {kind === 'birthday' ? (
            <Cake className="w-4 h-4 text-pink-600" />
          ) : (
            <Award className="w-4 h-4 text-amber-600" />
          )}
          <span className="text-sm font-semibold text-gray-800">
            {kind === 'birthday' ? 'Birthdays' : 'Work Anniversaries'} (
            {rows.length})
          </span>
        </div>
        <Button
          size="sm"
          variant="outline"
          disabled={rows.length === 0 || bulkKind === kind}
          onClick={() => generateBulk(kind)}
          className="gap-1.5"
        >
          {bulkKind === kind ? (
            <Clock className="w-3.5 h-3.5 animate-spin" />
          ) : (
            <Mail className="w-3.5 h-3.5" />
          )}
          Generate All
        </Button>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b text-gray-500">
              <th className="text-left px-4 py-2 font-medium">Employee</th>
              <th className="text-left px-4 py-2 font-medium">Department</th>
              <th className="text-left px-4 py-2 font-medium">Date</th>
              <th className="text-left px-4 py-2 font-medium">
                {kind === 'birthday' ? 'Age' : 'Years'}
              </th>
              <th className="text-right px-4 py-2 font-medium">Letter</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-gray-400">
                  None in this range
                </td>
              </tr>
            ) : (
              rows.map((r, i) => (
                <tr
                  key={`${r.id}-${r.date}-${i}`}
                  className="border-b hover:bg-gray-50"
                >
                  <td className="px-4 py-2.5">
                    <div className="font-medium text-gray-900">
                      {r.full_name}
                    </div>
                    <div className="text-xs text-gray-500">
                      {r.employee_code} &middot; {r.designation}
                    </div>
                  </td>
                  <td className="px-4 py-2.5 text-gray-600">{r.department}</td>
                  <td className="px-4 py-2.5 text-gray-600">
                    {fmtDate(r.date)}
                  </td>
                  <td className="px-4 py-2.5 text-gray-600">
                    {kind === 'birthday' ? r.age : r.years}
                  </td>
                  <td className="px-4 py-2.5 text-right">
                    {r.letter_generated ? (
                      <Badge className="bg-green-50 text-green-700 border-green-200 text-xs gap-1">
                        <CheckCircle2 className="w-3 h-3" />
                        Generated
                      </Badge>
                    ) : (
                      <Button
                        size="sm"
                        variant="ghost"
                        disabled={rowBusy === r.id}
                        onClick={() => generateOne(r, kind)}
                        className="text-indigo-600 hover:text-indigo-800 gap-1"
                      >
                        {rowBusy === r.id ? (
                          <Clock className="w-3.5 h-3.5 animate-spin" />
                        ) : (
                          <Mail className="w-3.5 h-3.5" />
                        )}
                        Generate
                      </Button>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </Card>
  );

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-2">
        <PartyPopper className="w-5 h-5 text-indigo-600" />
        <div>
          <h2 className="text-lg font-semibold text-gray-900">
            Celebrations &amp; Events
          </h2>
          <p className="text-sm text-gray-500 mt-0.5">
            Birthdays &amp; work anniversaries in a date range, with greeting
            letters
          </p>
        </div>
      </div>

      {/* Filters */}
      <Card className="p-4">
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">
              From
            </label>
            <input
              type="date"
              value={start}
              onChange={(e) => setStart(e.target.value)}
              className="px-3 py-2 border rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">
              To
            </label>
            <input
              type="date"
              value={end}
              onChange={(e) => setEnd(e.target.value)}
              className="px-3 py-2 border rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">
              Department
            </label>
            <input
              type="text"
              placeholder="All departments"
              value={department}
              onChange={(e) => setDepartment(e.target.value)}
              className="px-3 py-2 border rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
            />
          </div>
          <Button
            onClick={fetchReport}
            disabled={loading}
            className="bg-indigo-600 hover:bg-indigo-700 text-white gap-2"
          >
            {loading ? <Clock className="w-4 h-4 animate-spin" /> : null}
            Apply
          </Button>
        </div>
      </Card>

      {/* Count cards */}
      {data && (
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
          <Card className="p-4 flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-pink-50 flex items-center justify-center">
              <Cake className="w-5 h-5 text-pink-600" />
            </div>
            <div>
              <div className="text-2xl font-bold text-gray-900">
                {data.counts.birthdays}
              </div>
              <div className="text-xs text-gray-500">Birthdays</div>
            </div>
          </Card>
          <Card className="p-4 flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-amber-50 flex items-center justify-center">
              <Award className="w-5 h-5 text-amber-600" />
            </div>
            <div>
              <div className="text-2xl font-bold text-gray-900">
                {data.counts.anniversaries}
              </div>
              <div className="text-xs text-gray-500">Anniversaries</div>
            </div>
          </Card>
          <Card className="p-4 flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-indigo-50 flex items-center justify-center">
              <Building2 className="w-5 h-5 text-indigo-600" />
            </div>
            <div>
              <div className="text-2xl font-bold text-gray-900">
                {Object.keys(data.counts.by_department).length}
              </div>
              <div className="text-xs text-gray-500">Departments</div>
            </div>
          </Card>
        </div>
      )}

      {data && (
        <div className="space-y-6">
          {renderTable(data.anniversaries, 'anniversary')}
          {renderTable(data.birthdays, 'birthday')}
        </div>
      )}
    </div>
  );
};
