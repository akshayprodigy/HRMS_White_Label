import React, { useState } from 'react';
import { toast } from 'sonner';
import { Card, Button } from '../ui-elements';
import { client } from '../../api/client';
import { ENDPOINTS } from '../../api/endpoints';
import { errMsg } from '../schedule-delegations-utils';
import { BackfillResp, COMMON_OFFSETS, countsText, downloadTextFile, utcText } from './biometric-utils';
import { Th, inputCls, labelCls, useBackfill } from './shared';

/** API timestamps are UTC instants; show them in the UTC convention. */
const isoText = (v: string) => utcText(v);

interface Preview {
  rows: number; valid: number; invalid: number; unknown_people: number;
  duplicates_in_file: number; already_imported: number;
  date_range: { from: string; to: string } | null;
  errors: { row: number; message: string }[];
  sample: { row: number; identifier: string; timestamp: string; device_serial: string | null; known_person: boolean }[];
  warnings: { code: string; count: number; rows: number[]; message: string }[];
}

interface CommitResult extends BackfillResp {
  import_batch: string; inserted: number; already_imported: number; duplicates_in_file: number;
  skipped_invalid: number; unknown_people: number; by_state: Record<string, number>;
}

export const ImportTab: React.FC<{ backfill: ReturnType<typeof useBackfill> }> = ({ backfill }) => {
  const [file, setFile] = useState<File | null>(null);
  const [identifyBy, setIdentifyBy] = useState<'employee_code' | 'pin'>('employee_code');
  const [offset, setOffset] = useState('330');
  const [customOffset, setCustomOffset] = useState('0');
  const [preview, setPreview] = useState<Preview | null>(null);
  const [result, setResult] = useState<CommitResult | null>(null);
  const [skipInvalid, setSkipInvalid] = useState(false);
  const [busy, setBusy] = useState<'preview' | 'commit' | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [commitErrors, setCommitErrors] = useState<{ row: number; message: string }[]>([]);
  const [fileKey, setFileKey] = useState(0);

  const minutes = offset === 'custom' && !customOffset.trim() ? NaN : offset === 'custom' ? Number(customOffset) : Number(offset);

  const form = (extra?: Record<string, string>) => {
    const f = new FormData();
    f.append('file', file!);
    f.append('identify_by', identifyBy);
    f.append('utc_offset_minutes', String(minutes));
    Object.entries(extra ?? {}).forEach(([k, v]) => f.append(k, v));
    return f;
  };

  const resetOutput = () => { setPreview(null); setResult(null); setError(null); setCommitErrors([]); setSkipInvalid(false); };

  const doPreview = async () => {
    if (!file) return;
    if (!Number.isInteger(minutes) || minutes < -720 || minutes > 840) {
      setError('UTC offset must be a whole number of minutes between -720 and 840.');
      return;
    }
    setBusy('preview');
    resetOutput();
    try {
      const r = await client.post<Preview>(ENDPOINTS.BIOMETRIC.IMPORT_PREVIEW, form());
      setPreview(r.data);
    } catch (err: any) {
      setError(errMsg(err, 'Could not preview the file'));
    } finally {
      setBusy(null);
    }
  };

  const doCommit = async () => {
    if (!file || !preview) return;
    setBusy('commit');
    setError(null);
    setCommitErrors([]);
    try {
      const r = await client.post<CommitResult>(
        ENDPOINTS.BIOMETRIC.IMPORT_COMMIT,
        form(skipInvalid ? { skip_invalid: 'true' } : undefined)
      );
      setResult(r.data);
      setPreview(null);
      toast.success(`Imported ${r.data.inserted} tap(s)`);
      if ((r.data.remaining ?? 0) > 0) backfill.start(r.data, { import_batch: r.data.import_batch });
      else toast.success(`All taps processed: ${countsText(r.data.backfill ?? {})}`);
      setFile(null);
      setFileKey((k) => k + 1);
    } catch (err: any) {
      setError(errMsg(err, 'Import failed'));
      const errs = err?.response?.data?.error?.details?.errors;
      if (Array.isArray(errs)) setCommitErrors(errs);
    } finally {
      setBusy(null);
    }
  };

  const template = async () => {
    try {
      const r = await client.get<string>(ENDPOINTS.BIOMETRIC.IMPORT_TEMPLATE, {
        params: { identify_by: identifyBy }, responseType: 'text',
      });
      downloadTextFile(r.data, `biometric-import-template-${identifyBy}.csv`);
    } catch (err: any) {
      toast.error(errMsg(err, 'Could not download the template'));
    }
  };

  return (
    <div className="space-y-4">
      <Card className="p-4 space-y-3">
        <p className="text-sm text-gray-600">
          Import punches from any vendor's export (.csv or .xlsx, up to 5 MB). Timestamps are read as device wall-clock
          time in the offset below. Re-importing the same file is safe: existing taps are skipped.
        </p>
        <div className="flex items-end gap-3 flex-wrap">
          <div>
            <label htmlFor="imp-file" className={labelCls}>File</label>
            <input
              key={fileKey}
              id="imp-file"
              type="file"
              accept=".csv,.xlsx"
              className="text-sm"
              onChange={(e) => { setFile(e.target.files?.[0] ?? null); resetOutput(); }}
            />
          </div>
          <div>
            <label htmlFor="imp-by" className={labelCls}>Identify people by</label>
            <select id="imp-by" className={inputCls} value={identifyBy}
              onChange={(e) => { setIdentifyBy(e.target.value as 'employee_code' | 'pin'); resetOutput(); }}>
              <option value="employee_code">Employee code</option>
              <option value="pin">Device PIN</option>
            </select>
          </div>
          <div>
            <label htmlFor="imp-offset" className={labelCls}>Timestamps are in</label>
            <select id="imp-offset" className={inputCls} value={offset} onChange={(e) => { setOffset(e.target.value); resetOutput(); }}>
              {COMMON_OFFSETS.map((o) => <option key={o.minutes} value={o.minutes}>{o.label}</option>)}
              <option value="custom">Custom (minutes)…</option>
            </select>
          </div>
          {offset === 'custom' && (
            <div>
              <label htmlFor="imp-custom" className={labelCls}>Offset minutes</label>
              <input id="imp-custom" type="number" min={-720} max={840} className={`${inputCls} w-28`}
                value={customOffset} onChange={(e) => { setCustomOffset(e.target.value); resetOutput(); }} />
            </div>
          )}
          <Button onClick={doPreview} disabled={!file || busy !== null} isLoading={busy === 'preview'}>Preview</Button>
          <Button variant="outline" onClick={template}>Download template</Button>
        </div>
      </Card>

      {error && (
        <div role="alert" className="p-3 rounded-lg bg-red-50 text-sm text-red-700 space-y-1">
          <p>{error}</p>
          {commitErrors.length > 0 && (
            <ul className="list-disc pl-6">
              {commitErrors.slice(0, 20).map((e, i) => <li key={i}>Row {e.row}: {e.message}</li>)}
            </ul>
          )}
        </div>
      )}

      {preview && (
        <Card className="p-4 space-y-4">
          <div className="flex gap-3 flex-wrap text-sm">
            {([
              ['Rows', preview.rows], ['Valid', preview.valid], ['Invalid', preview.invalid],
              ['Unknown people', preview.unknown_people], ['Duplicates in file', preview.duplicates_in_file],
              ['Already imported', preview.already_imported],
            ] as [string, number][]).map(([k, v]) => (
              <div key={k} className="px-3 py-2 rounded-lg bg-gray-50">
                <span className="text-gray-500">{k}</span>{' '}
                <span className="font-semibold text-gray-900">{v}</span>
              </div>
            ))}
            {preview.date_range && (
              <div className="px-3 py-2 rounded-lg bg-gray-50">
                <span className="text-gray-500">Dates</span>{' '}
                <span className="font-semibold text-gray-900">{isoText(preview.date_range.from)} to {isoText(preview.date_range.to)}</span>
              </div>
            )}
          </div>

          {preview.warnings.map((w) => (
            <div key={w.code} role="alert" className="p-3 rounded-lg bg-amber-50 text-sm text-amber-900">
              <strong>{w.message}</strong>{' '}
              ({w.count} affected{w.rows.length ? `, e.g. rows ${w.rows.slice(0, 8).join(', ')}` : ''})
            </div>
          ))}

          {preview.errors.length > 0 && (
            <div>
              <p className="text-sm font-medium text-gray-800 mb-1">Errors (first {Math.min(preview.errors.length, 20)})</p>
              <ul className="text-sm text-red-700 list-disc pl-6 space-y-1">
                {preview.errors.slice(0, 20).map((e, i) => <li key={i}>Row {e.row}: {e.message}</li>)}
              </ul>
            </div>
          )}

          {preview.sample.length > 0 && (
            <div>
              <p className="text-sm font-medium text-gray-800 mb-1">Sample rows</p>
              <div className="overflow-x-auto border border-gray-100 rounded-lg">
                <table className="w-full text-sm">
                  <thead className="bg-gray-50">
                    <tr><Th>Row</Th><Th>Identifier</Th><Th>Timestamp</Th><Th>Device</Th><Th>Known</Th></tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {preview.sample.map((s) => (
                      <tr key={s.row}>
                        <td className="px-3 py-1.5">{s.row}</td>
                        <td className="px-3 py-1.5 font-mono">{s.identifier}</td>
                        <td className="px-3 py-1.5 whitespace-nowrap">{isoText(s.timestamp)}</td>
                        <td className="px-3 py-1.5">{s.device_serial || '—'}</td>
                        <td className="px-3 py-1.5">{s.known_person ? 'Yes' : 'No'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          <div className="flex items-center gap-4 flex-wrap">
            {preview.invalid > 0 && (
              <label className="flex items-center gap-2 text-sm text-gray-700">
                <input type="checkbox" checked={skipInvalid} onChange={(e) => setSkipInvalid(e.target.checked)} />
                Skip {preview.invalid} invalid row{preview.invalid === 1 ? '' : 's'}
              </label>
            )}
            <Button
              onClick={doCommit}
              isLoading={busy === 'commit'}
              disabled={busy !== null || preview.valid === 0 || (preview.invalid > 0 && !skipInvalid)}
            >
              Import {preview.valid} tap{preview.valid === 1 ? '' : 's'}
            </Button>
          </div>
        </Card>
      )}

      {result && (
        <Card className="p-4 space-y-3">
          <p className="text-sm font-medium text-gray-900">Import complete</p>
          <div className="flex gap-3 flex-wrap text-sm">
            {([
              ['Inserted', result.inserted], ['Already imported', result.already_imported],
              ['Duplicates in file', result.duplicates_in_file], ['Skipped invalid', result.skipped_invalid],
              ['Unknown people', result.unknown_people],
            ] as [string, number][]).map(([k, v]) => (
              <div key={k} className="px-3 py-2 rounded-lg bg-gray-50">
                <span className="text-gray-500">{k}</span> <span className="font-semibold text-gray-900">{v}</span>
              </div>
            ))}
          </div>
          {Object.keys(result.by_state ?? {}).length > 0 && (
            <p className="text-sm text-gray-700">
              By state: {Object.entries(result.by_state).map(([k, v]) => `${v} ${k.replace(/_/g, ' ')}`).join(', ')}
            </p>
          )}
        </Card>
      )}
    </div>
  );
};
