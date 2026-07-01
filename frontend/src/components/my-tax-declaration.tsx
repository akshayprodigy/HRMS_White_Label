/**
 * Employee tax declaration form with LIVE old-vs-new regime comparison.
 * Investments + HRA inputs + previous-employer income. On save, the
 * status flips to SUBMITTED; HR verifies separately.
 */
import React, { useEffect, useMemo, useState } from 'react';
import {
  Send, RefreshCw, TrendingDown, TrendingUp, Save,
} from 'lucide-react';
import { Card, Button, Badge, cn } from './ui-elements';
import { toast } from 'sonner';
import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';
import { Input } from './ui/input';

interface SectionLimit {
  fy: string; section_code: string; limit_amount: number;
  is_percentage: boolean; applies_to: string;
}
interface MyDeclaration {
  id: number; fy: string; regime: string;
  declarations_json: Record<string, number>;
  monthly_rent_paid: number; rented_in_metro: boolean;
  landlord_pan: string | null;
  other_income_annual: number;
  previous_employer_income: number; previous_employer_tds: number;
  status: string; rejection_reason: string | null;
  verified_at: string | null;
}
interface Projection {
  fy: string; old: any; new: any;
  better_regime: string; saving: number;
  declared_regime: string | null;
}

const DEFAULT_SECTIONS = [
  '80C', '80D', '80CCD_1B', '80E', '80G', '80TTA',
];

const errMsg = (e: any, fb: string) => {
  const d = e?.response?.data?.detail;
  if (typeof d === 'string') return d;
  if (Array.isArray(d)) return d.map((x: any) => x?.msg || JSON.stringify(x)).join('; ');
  return e?.message || fb;
};

const fyDefault = () => {
  const d = new Date();
  const y = d.getFullYear();
  const a = d.getMonth() + 1 >= 4 ? y : y - 1;
  const b = a + 1;
  return `${String(a).slice(-2)}-${String(b).slice(-2)}`;
};

export const MyTaxDeclarationView: React.FC = () => {
  const [fy, setFy] = useState(fyDefault());
  const [mine, setMine] = useState<MyDeclaration | null>(null);
  const [limits, setLimits] = useState<SectionLimit[]>([]);
  const [projection, setProjection] = useState<Projection | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [employeeId, setEmployeeId] = useState<number | null>(null);

  const [form, setForm] = useState({
    regime: 'new' as 'old' | 'new',
    declarations_json: {} as Record<string, number>,
    monthly_rent_paid: 0,
    rented_in_metro: false,
    landlord_pan: '',
    other_income_annual: 0,
    previous_employer_income: 0,
    previous_employer_tds: 0,
  });

  const fetchAll = async () => {
    setLoading(true);
    try {
      const [d, l, me] = await Promise.all([
        client.get(ENDPOINTS.TAX.MY_DECLARATIONS),
        client.get(ENDPOINTS.TAX.SECTION_LIMITS, { params: { fy } }),
        client.get(ENDPOINTS.AUTH.ME).catch(() => ({ data: null })),
      ]);
      setLimits(l.data || []);
      const list: MyDeclaration[] = d.data || [];
      const cur = list.find(x => x.fy === fy) || null;
      setMine(cur);
      if (cur) {
        setForm({
          regime: cur.regime as any,
          declarations_json: cur.declarations_json || {},
          monthly_rent_paid: cur.monthly_rent_paid,
          rented_in_metro: cur.rented_in_metro,
          landlord_pan: cur.landlord_pan || '',
          other_income_annual: cur.other_income_annual,
          previous_employer_income: cur.previous_employer_income,
          previous_employer_tds: cur.previous_employer_tds,
        });
      }
      // employee_id is derived from "me" — try profile.id or employee_id
      const empId = me.data?.employee?.id || null;
      setEmployeeId(empId);
      if (empId) {
        const p = await client.get(ENDPOINTS.TAX.PROJECTION(empId), { params: { fy } });
        setProjection(p.data);
      }
    } catch (e: any) { toast.error(errMsg(e, 'Failed to load')); }
    finally { setLoading(false); }
  };
  useEffect(() => { fetchAll(); /* eslint-disable-line */ }, [fy]);

  const refreshProjection = async () => {
    if (!employeeId) return;
    try {
      const p = await client.get(ENDPOINTS.TAX.PROJECTION(employeeId), { params: { fy } });
      setProjection(p.data);
    } catch (e: any) { /* silent */ }
  };

  const knownSections = useMemo(() => {
    const fromLimits = limits.map(l => l.section_code);
    const merged = Array.from(new Set([...DEFAULT_SECTIONS, ...fromLimits]));
    return merged;
  }, [limits]);

  const submit = async () => {
    if (!employeeId) { toast.error('Employee profile not found'); return; }
    setSaving(true);
    try {
      await client.put(ENDPOINTS.TAX.DECLARATIONS, {
        employee_id: employeeId, fy, ...form,
      });
      toast.success('Declaration submitted'); fetchAll();
    } catch (e: any) { toast.error(errMsg(e, 'Save failed')); }
    finally { setSaving(false); }
  };

  const statusChip = (s?: string) => {
    if (!s) return null;
    const v = s === 'verified' ? 'success'
      : s === 'rejected' ? 'error'
      : s === 'submitted' ? 'info'
      : 'warning';
    return <Badge variant={v as any}>{s}</Badge>;
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">My Tax Declaration</h1>
          <p className="text-sm text-slate-500 mt-1">
            Investments + HRA + previous-employer income. Live old-vs-new regime comparison on the right.
          </p>
        </div>
        <div className="flex items-end gap-2">
          <div>
            <label className="text-xs font-semibold text-slate-600">FY</label>
            <Input value={fy} onChange={e => setFy(e.target.value)}
              className="w-28" placeholder="24-25" />
          </div>
          <Button variant="outline" onClick={fetchAll}><RefreshCw className="w-4 h-4" /></Button>
        </div>
      </div>

      {mine && (
        <Card className="p-3 bg-slate-50 flex items-center justify-between">
          <div className="text-xs text-slate-600">
            <span className="font-semibold">Current status:</span> {statusChip(mine.status)}
            {mine.verified_at && <span className="ml-2">verified {new Date(mine.verified_at).toLocaleDateString()}</span>}
          </div>
          {mine.rejection_reason && (
            <div className="text-xs text-red-600">Rejected: {mine.rejection_reason}</div>
          )}
        </Card>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card className="p-4 lg:col-span-2 space-y-4">
          <h2 className="text-sm font-semibold uppercase text-slate-600 tracking-wide">Inputs</h2>

          <div>
            <label className="text-xs font-semibold text-slate-600">Regime</label>
            <div className="flex gap-3 mt-1">
              {(['old', 'new'] as const).map(r => (
                <button key={r}
                  onClick={() => setForm({ ...form, regime: r })}
                  className={cn(
                    'px-4 py-2 rounded-md text-sm font-semibold',
                    form.regime === r ? 'bg-blue-600 text-white' : 'bg-slate-100 text-slate-700',
                  )}>
                  {r.toUpperCase()}
                </button>
              ))}
            </div>
            <div className="text-[10px] text-slate-500 mt-1">
              Default is NEW from FY 2023-24 onwards if you don't pick.
            </div>
          </div>

          <div>
            <h3 className="text-xs font-semibold text-slate-600 uppercase tracking-wide mb-2">Chapter VI-A investments</h3>
            <div className="grid grid-cols-2 gap-3">
              {knownSections.map(code => {
                const limit = limits.find(l => l.section_code === code);
                return (
                  <div key={code}>
                    <label className="text-xs text-slate-600">
                      {code}
                      {limit && !limit.is_percentage && (
                        <span className="text-[10px] text-slate-400 ml-1">
                          (cap ₹{limit.limit_amount.toLocaleString('en-IN')})
                        </span>
                      )}
                    </label>
                    <Input type="number" min={0}
                      value={form.declarations_json[code] ?? ''}
                      onChange={e => {
                        const v = e.target.value === '' ? 0 : Number(e.target.value);
                        setForm({
                          ...form,
                          declarations_json: { ...form.declarations_json, [code]: v },
                        });
                      }} />
                  </div>
                );
              })}
            </div>
          </div>

          <div>
            <h3 className="text-xs font-semibold text-slate-600 uppercase tracking-wide mb-2">HRA</h3>
            <div className="grid grid-cols-3 gap-3">
              <div>
                <label className="text-xs text-slate-600">Monthly rent paid ₹</label>
                <Input type="number" min={0} value={form.monthly_rent_paid}
                  onChange={e => setForm({ ...form, monthly_rent_paid: Number(e.target.value) })} />
              </div>
              <div className="flex items-end">
                <label className="text-sm flex items-center gap-2">
                  <input type="checkbox" checked={form.rented_in_metro}
                    onChange={e => setForm({ ...form, rented_in_metro: e.target.checked })} />
                  Metro
                </label>
              </div>
              <div>
                <label className="text-xs text-slate-600">Landlord PAN (rent &gt; 1L/yr)</label>
                <Input value={form.landlord_pan}
                  onChange={e => setForm({ ...form, landlord_pan: e.target.value })} />
              </div>
            </div>
          </div>

          <div>
            <h3 className="text-xs font-semibold text-slate-600 uppercase tracking-wide mb-2">Other income</h3>
            <div className="grid grid-cols-3 gap-3">
              <div>
                <label className="text-xs text-slate-600">Other income (annual) ₹</label>
                <Input type="number" min={0} value={form.other_income_annual}
                  onChange={e => setForm({ ...form, other_income_annual: Number(e.target.value) })} />
              </div>
              <div>
                <label className="text-xs text-slate-600">Previous employer income ₹</label>
                <Input type="number" min={0} value={form.previous_employer_income}
                  onChange={e => setForm({ ...form, previous_employer_income: Number(e.target.value) })} />
              </div>
              <div>
                <label className="text-xs text-slate-600">Previous employer TDS ₹</label>
                <Input type="number" min={0} value={form.previous_employer_tds}
                  onChange={e => setForm({ ...form, previous_employer_tds: Number(e.target.value) })} />
              </div>
            </div>
          </div>

          <div className="flex gap-2 pt-2 border-t border-slate-100">
            <Button variant="outline" onClick={refreshProjection}>
              <RefreshCw className="w-3 h-3 mr-2" /> Refresh comparison
            </Button>
            <Button isLoading={saving} onClick={submit}>
              <Send className="w-3 h-3 mr-2" /> Save & submit
            </Button>
          </div>
        </Card>

        <Card className="p-4 space-y-3">
          <h2 className="text-sm font-semibold uppercase text-slate-600 tracking-wide">
            Old vs New (live)
          </h2>
          {!projection ? (
            <div className="py-6 text-center text-slate-500 text-sm">
              No projection yet — payroll for this FY may not be finalized.
            </div>
          ) : (
            <>
              <div className={cn(
                'p-3 rounded-lg flex items-center gap-2',
                projection.better_regime === 'old' ? 'bg-blue-50' : 'bg-purple-50',
              )}>
                {projection.saving > 0
                  ? <TrendingDown className="w-4 h-4 text-green-600" />
                  : <TrendingUp className="w-4 h-4 text-slate-400" />}
                <div className="text-xs">
                  <div className="font-semibold">
                    {projection.better_regime.toUpperCase()} regime saves
                    <span className="ml-1 text-green-700">₹{projection.saving.toLocaleString('en-IN')}</span>
                  </div>
                  <div className="text-slate-500 text-[10px]">
                    Based on your current declared inputs + projected annual gross.
                  </div>
                </div>
              </div>

              <table className="w-full text-xs">
                <thead className="text-left text-[10px] uppercase text-slate-500 border-b">
                  <tr>
                    <th className="py-1">Item</th>
                    <th className="py-1 text-right">Old</th>
                    <th className="py-1 text-right">New</th>
                  </tr>
                </thead>
                <tbody>
                  {[
                    ['Taxable income', 'taxable_income'],
                    ['Tax on slabs', 'tax_on_slabs'],
                    ['Rebate u/s 87A', 'rebate_87a'],
                    ['Surcharge', 'surcharge'],
                    ['Cess', 'cess'],
                    ['HRA exempt.', 'hra_exemption'],
                    ['Chap VI-A ded.', 'chapter_via_deductions'],
                  ].map(([label, k]) => (
                    <tr key={k} className="border-b">
                      <td className="py-1 text-slate-600">{label}</td>
                      <td className="py-1 text-right font-mono">
                        ₹{(projection.old[k as string] || 0).toLocaleString('en-IN')}
                      </td>
                      <td className="py-1 text-right font-mono">
                        ₹{(projection.new[k as string] || 0).toLocaleString('en-IN')}
                      </td>
                    </tr>
                  ))}
                  <tr className="font-bold">
                    <td className="py-1">Total tax</td>
                    <td className="py-1 text-right font-mono">
                      ₹{(projection.old.total_tax || 0).toLocaleString('en-IN')}
                    </td>
                    <td className="py-1 text-right font-mono">
                      ₹{(projection.new.total_tax || 0).toLocaleString('en-IN')}
                    </td>
                  </tr>
                </tbody>
              </table>
            </>
          )}
        </Card>
      </div>
    </div>
  );
};
