/**
 * Generic report viewer: takes a ReportDescriptor + optional initial
 * filters, renders the filter panel, runs the report on submit, and
 * shows a sortable table with export buttons.
 *
 * Currency, hours, dates, percents are formatted using the column-def
 * type — same dispatch the backend uses so exports match the on-screen
 * table byte-for-byte.
 */
import React, { useMemo, useState } from 'react';
import {
  Play, Download, FileSpreadsheet, FileText, File, Bookmark,
  ArrowLeft, ChevronUp, ChevronDown, AlertTriangle,
} from 'lucide-react';
import { Card, Button, Badge, cn } from './ui-elements';
import { toast } from 'sonner@2.0.3';
import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';
import { Dialog, DialogContent, DialogTitle, DialogFooter } from './ui/dialog';
import { Input } from './ui/input';

interface FilterSchema {
  key: string; label: string; type: string;
  required: boolean; options: any[] | null; hint: string | null;
}
interface ReportDesc {
  key: string; name: string; description: string;
  category: string; permission: string;
  is_sensitive: boolean; manager_scoped: boolean;
  filters: FilterSchema[];
}
interface Column {
  key: string; label: string; type: string; width: number | null;
}
interface RunResult {
  columns: Column[]; rows: any[]; totals: any; meta: any;
}

const errMsg = (e: any, fb: string) => {
  const d = e?.response?.data?.detail;
  if (typeof d === 'string') return d;
  return e?.message || fb;
};

// Indian currency formatter — matches backend fmt_inr.
const fmtInr = (v: any): string => {
  if (v == null || v === '') return '';
  const n = Number(v);
  if (isNaN(n)) return String(v);
  const neg = n < 0;
  const abs = Math.abs(n);
  const intPart = Math.trunc(abs);
  const dec = (abs - intPart).toFixed(2).slice(2);
  const s = String(intPart);
  let grouped: string;
  if (s.length <= 3) grouped = s;
  else {
    const last3 = s.slice(-3);
    let rest = s.slice(0, -3);
    const chunks: string[] = [];
    while (rest.length > 2) { chunks.push(rest.slice(-2)); rest = rest.slice(0, -2); }
    if (rest) chunks.push(rest);
    grouped = chunks.reverse().join(',') + ',' + last3;
  }
  return (neg ? '-' : '') + '₹' + grouped + '.' + dec;
};

const fmtHours = (v: any): string => {
  if (v == null || v === '') return '';
  const m = Number(v);
  if (isNaN(m)) return String(v);
  if (m === 0) return '0h';
  const sign = m < 0 ? '-' : '';
  const a = Math.abs(m);
  const h = Math.floor(a / 60); const rem = a % 60;
  if (rem === 0) return `${sign}${h}h`;
  return `${sign}${h}h ${String(rem).padStart(2, '0')}m`;
};

const fmtPercent = (v: any): string => v == null ? '' : `${Number(v).toFixed(2)}%`;

const fmtDate = (v: any): string => {
  if (!v) return '';
  const d = new Date(v);
  if (isNaN(d.getTime())) return String(v);
  return d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
};

const fmtDateTime = (v: any): string => {
  if (!v) return '';
  const d = new Date(v);
  if (isNaN(d.getTime())) return String(v);
  return d.toLocaleString('en-IN', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
};

const fmtCell = (value: any, type: string): string => {
  switch (type) {
    case 'currency': return fmtInr(value);
    case 'hours': return fmtHours(value);
    case 'percent': return fmtPercent(value);
    case 'date': return fmtDate(value);
    case 'datetime': return fmtDateTime(value);
    default: return value == null ? '' : String(value);
  }
};

interface Props {
  report: ReportDesc;
  initialFilters?: any;
  onBack: () => void;
}

export const ReportViewer: React.FC<Props> = ({
  report, initialFilters, onBack,
}) => {
  const [filters, setFilters] = useState<Record<string, any>>(initialFilters || {});
  const [result, setResult] = useState<RunResult | null>(null);
  const [running, setRunning] = useState(false);
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc');
  const [saveOpen, setSaveOpen] = useState(false);
  const [saveForm, setSaveForm] = useState({ name: '', description: '' });

  const missingRequired = report.filters.some(
    f => f.required && (filters[f.key] == null || filters[f.key] === ''),
  );

  const run = async () => {
    setRunning(true); setResult(null);
    try {
      const r = await client.post(
        ENDPOINTS.REPORTS_ENGINE.RUN(report.key),
        filters,
        { params: { format: 'json' } },
      );
      setResult(r.data);
    } catch (e: any) { toast.error(errMsg(e, 'Run failed')); }
    finally { setRunning(false); }
  };

  const download = async (format: 'xlsx' | 'csv' | 'pdf') => {
    try {
      const res = await client.post(
        ENDPOINTS.REPORTS_ENGINE.RUN(report.key),
        filters,
        { params: { format }, responseType: 'blob' },
      );
      const media = format === 'xlsx'
        ? 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        : format === 'csv' ? 'text/csv' : 'application/pdf';
      const blob = new Blob([res.data], { type: media });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = `${report.key}.${format}`;
      a.click(); URL.revokeObjectURL(url);
    } catch (e: any) { toast.error(errMsg(e, 'Export failed')); }
  };

  const save = async () => {
    if (!saveForm.name.trim()) { toast.error('Name required'); return; }
    try {
      await client.post(ENDPOINTS.REPORTS_ENGINE.SAVED, {
        name: saveForm.name,
        report_key: report.key,
        description: saveForm.description || null,
        filters_json: filters,
      });
      toast.success('Saved');
      setSaveOpen(false);
    } catch (e: any) { toast.error(errMsg(e, 'Save failed')); }
  };

  const sortedRows = useMemo(() => {
    if (!result) return [];
    if (!sortKey) return result.rows;
    const rows = [...result.rows];
    rows.sort((a, b) => {
      const av = a[sortKey]; const bv = b[sortKey];
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      if (typeof av === 'number' && typeof bv === 'number') {
        return sortDir === 'asc' ? av - bv : bv - av;
      }
      return sortDir === 'asc'
        ? String(av).localeCompare(String(bv))
        : String(bv).localeCompare(String(av));
    });
    return rows;
  }, [result, sortKey, sortDir]);

  const clickSort = (key: string) => {
    if (sortKey === key) { setSortDir(sortDir === 'asc' ? 'desc' : 'asc'); }
    else { setSortKey(key); setSortDir('asc'); }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-start gap-3">
          <Button variant="outline" onClick={onBack}><ArrowLeft className="w-4 h-4" /></Button>
          <div>
            <h1 className="text-2xl font-bold">{report.name}</h1>
            <p className="text-sm text-slate-500 mt-1">{report.description}</p>
            <div className="flex gap-1 mt-2">
              {report.is_sensitive && (
                <Badge variant="warning" className="text-[10px]">
                  <AlertTriangle className="w-2.5 h-2.5 mr-0.5" /> Sensitive · exports audit-logged
                </Badge>
              )}
              {report.manager_scoped && (
                <Badge variant="info" className="text-[10px]">Manager sees own team</Badge>
              )}
            </div>
          </div>
        </div>
      </div>

      <Card className="p-4">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-600 mb-3">Filters</h2>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
          {report.filters.map(f => (
            <div key={f.key}>
              <label className="text-xs font-semibold text-slate-600">
                {f.label}{f.required && <span className="text-red-500 ml-0.5">*</span>}
              </label>
              {f.type === 'date' ? (
                <Input type="date" value={filters[f.key] || ''}
                  onChange={e => setFilters({ ...filters, [f.key]: e.target.value })} />
              ) : f.type === 'select' && f.options ? (
                <select value={filters[f.key] || ''}
                  onChange={e => setFilters({ ...filters, [f.key]: e.target.value })}
                  className="w-full border border-slate-200 rounded-md h-9 px-2 text-sm">
                  <option value="">—</option>
                  {f.options.map((o: any) => (
                    <option key={o.value} value={o.value}>{o.label}</option>
                  ))}
                </select>
              ) : f.type === 'payroll_run' || f.type === 'int' || f.type === 'shift' ? (
                <Input type="number" value={filters[f.key] || ''}
                  onChange={e => setFilters({ ...filters, [f.key]: e.target.value ? Number(e.target.value) : undefined })}
                  placeholder={f.hint || ''} />
              ) : (
                <Input value={filters[f.key] || ''}
                  onChange={e => setFilters({ ...filters, [f.key]: e.target.value })}
                  placeholder={f.hint || ''} />
              )}
            </div>
          ))}
        </div>
        <div className="flex gap-2 mt-4">
          <Button onClick={run} isLoading={running}
            disabled={missingRequired}>
            <Play className="w-4 h-4 mr-2" /> Run
          </Button>
          {result && (
            <>
              <Button variant="outline" onClick={() => download('xlsx')}>
                <FileSpreadsheet className="w-4 h-4 mr-2" /> Excel
              </Button>
              <Button variant="outline" onClick={() => download('csv')}>
                <File className="w-4 h-4 mr-2" /> CSV
              </Button>
              <Button variant="outline" onClick={() => download('pdf')}>
                <FileText className="w-4 h-4 mr-2" /> PDF
              </Button>
            </>
          )}
          <Button variant="outline" onClick={() => setSaveOpen(true)} className="ml-auto">
            <Bookmark className="w-4 h-4 mr-2" /> Save
          </Button>
        </div>
      </Card>

      {result && (
        <Card className="p-4">
          <div className="flex items-center justify-between mb-3">
            <div className="text-xs text-slate-500">
              {result.meta?.row_count != null && (
                <span className="font-semibold">{result.meta.row_count} rows</span>
              )}
              {result.meta?.period && <span className="ml-2">· {result.meta.period}</span>}
              {result.meta?.payroll_period && <span className="ml-2">· Payroll {result.meta.payroll_period}</span>}
            </div>
          </div>
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead className="text-left text-xs uppercase text-slate-500 border-b bg-slate-50">
                <tr>
                  {result.columns.map(c => (
                    <th key={c.key}
                      onClick={() => clickSort(c.key)}
                      className="p-2 cursor-pointer hover:text-slate-700 whitespace-nowrap">
                      <span className="flex items-center gap-1">
                        {c.label}
                        {sortKey === c.key && (
                          sortDir === 'asc'
                            ? <ChevronUp className="w-3 h-3" />
                            : <ChevronDown className="w-3 h-3" />
                        )}
                      </span>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {sortedRows.map((row, i) => (
                  <tr key={i} className="border-b hover:bg-slate-50">
                    {result.columns.map(c => (
                      <td key={c.key} className={cn('p-2 whitespace-nowrap',
                        (c.type === 'currency' || c.type === 'int' || c.type === 'hours' || c.type === 'percent') && 'text-right font-mono')}>
                        {fmtCell(row[c.key], c.type)}
                      </td>
                    ))}
                  </tr>
                ))}
                {result.totals && Object.keys(result.totals).length > 0 && (
                  <tr className="bg-blue-50 font-semibold border-t-2 border-blue-200">
                    {result.columns.map(c => (
                      <td key={c.key} className={cn('p-2 whitespace-nowrap',
                        (c.type === 'currency' || c.type === 'int' || c.type === 'hours' || c.type === 'percent') && 'text-right font-mono')}>
                        {fmtCell(result.totals[c.key], c.type)}
                      </td>
                    ))}
                  </tr>
                )}
              </tbody>
            </table>
            {sortedRows.length === 0 && (
              <div className="py-12 text-center text-slate-500">No rows.</div>
            )}
          </div>
        </Card>
      )}

      <Dialog open={saveOpen} onOpenChange={setSaveOpen}>
        <DialogContent className="max-w-md">
          <DialogTitle>Save this report</DialogTitle>
          <div className="space-y-3 mt-4">
            <div>
              <label className="text-xs font-semibold text-slate-600">Name</label>
              <Input value={saveForm.name}
                onChange={e => setSaveForm({ ...saveForm, name: e.target.value })} />
            </div>
            <div>
              <label className="text-xs font-semibold text-slate-600">Description</label>
              <Input value={saveForm.description}
                onChange={e => setSaveForm({ ...saveForm, description: e.target.value })} />
            </div>
            <div className="text-[10px] text-slate-500">
              Current filters are captured with the report. Scheduling (email delivery) is planned; for now use "run-now" from the catalog card.
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setSaveOpen(false)}>Cancel</Button>
            <Button onClick={save}>Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};
