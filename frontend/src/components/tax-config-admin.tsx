/**
 * Tax config admin: TaxSlabConfig (FY-scoped slabs JSON for both
 * regimes + standard deduction + 87A + cess), SectionLimitConfig
 * (per FY per section), GratuityConfig.
 *
 * Slabs are stored as a JSON blob; the admin lets HR paste / edit the
 * JSON directly (Pydantic validates it at the API).
 */
import React, { useEffect, useMemo, useState } from 'react';
import {
  Plus, Edit2, Search, RefreshCw, FileText, BookOpen, Award,
} from 'lucide-react';
import { Card, Button, Badge, cn } from './ui-elements';
import { toast } from 'sonner@2.0.3';
import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';
import { Dialog, DialogContent, DialogTitle, DialogFooter } from './ui/dialog';
import { Input } from './ui/input';

interface SlabConfig {
  id: number; fy: string; name: string;
  slabs_json: any;
  standard_deduction_old: number; standard_deduction_new: number;
  rebate_87a_old_threshold: number; rebate_87a_old_max: number;
  rebate_87a_new_threshold: number; rebate_87a_new_max: number;
  cess_rate: number; is_active: boolean; notes: string | null;
}
interface SectionLimit {
  id: number; fy: string; section_code: string;
  limit_amount: number; is_percentage: boolean;
  applies_to: string; notes: string | null;
}
interface GratuityCfg {
  id: number; effective_from: string; statutory_cap: number;
  eligibility_years: number; days_basis: number;
  is_active: boolean; notes: string | null;
}

const errMsg = (e: any, fb: string) => {
  const d = e?.response?.data?.detail;
  if (typeof d === 'string') return d;
  if (Array.isArray(d)) return d.map((x: any) => x?.msg || JSON.stringify(x)).join('; ');
  return e?.message || fb;
};

const DEFAULT_SLABS = JSON.stringify({
  old: [
    { upto: 250000, rate: 0 },
    { upto: 500000, rate: 5 },
    { upto: 1000000, rate: 20 },
    { upto: null, rate: 30 },
  ],
  new: [
    { upto: 300000, rate: 0 },
    { upto: 700000, rate: 5 },
    { upto: 1000000, rate: 10 },
    { upto: 1200000, rate: 15 },
    { upto: 1500000, rate: 20 },
    { upto: null, rate: 30 },
  ],
  surcharge_old: [
    { upto: 5000000, rate: 0 },
    { upto: 10000000, rate: 10 },
    { upto: 20000000, rate: 15 },
    { upto: 50000000, rate: 25 },
    { upto: null, rate: 37 },
  ],
  surcharge_new: [
    { upto: 5000000, rate: 0 },
    { upto: 10000000, rate: 10 },
    { upto: 20000000, rate: 15 },
    { upto: null, rate: 25 },
  ],
}, null, 2);

export const TaxConfigAdmin: React.FC = () => {
  const [tab, setTab] = useState<'slabs' | 'sections' | 'gratuity'>('slabs');
  const [slabs, setSlabs] = useState<SlabConfig[]>([]);
  const [limits, setLimits] = useState<SectionLimit[]>([]);
  const [gconfigs, setGconfigs] = useState<GratuityCfg[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');

  // Slab modal
  const [slabModal, setSlabModal] = useState(false);
  const [editingSlab, setEditingSlab] = useState<SlabConfig | null>(null);
  const [slabForm, setSlabForm] = useState({
    fy: '24-25', name: 'FY 2024-25', slabs_json_text: DEFAULT_SLABS,
    standard_deduction_old: 50000, standard_deduction_new: 75000,
    rebate_87a_old_threshold: 500000, rebate_87a_old_max: 12500,
    rebate_87a_new_threshold: 700000, rebate_87a_new_max: 25000,
    cess_rate: 4.0, is_active: true, notes: '',
  });

  // Section limit modal
  const [limitModal, setLimitModal] = useState(false);
  const [limitForm, setLimitForm] = useState({
    fy: '24-25', section_code: '80C', limit_amount: 150000,
    is_percentage: false, applies_to: 'BOTH' as 'BOTH' | 'OLD' | 'NEW',
    notes: '',
  });

  // Gratuity modal
  const [gratModal, setGratModal] = useState(false);
  const [gratForm, setGratForm] = useState({
    effective_from: new Date().toISOString().slice(0, 10),
    statutory_cap: 2000000, eligibility_years: 5,
    days_basis: 26, is_active: true, notes: '',
  });

  const [submitting, setSubmitting] = useState(false);

  const fetchAll = async () => {
    setLoading(true);
    try {
      const [s, l, g] = await Promise.all([
        client.get(ENDPOINTS.TAX.CONFIGS),
        client.get(ENDPOINTS.TAX.SECTION_LIMITS),
        client.get(ENDPOINTS.TAX.GRATUITY_CONFIGS),
      ]);
      setSlabs(s.data || []); setLimits(l.data || []); setGconfigs(g.data || []);
    } catch (e: any) { toast.error(errMsg(e, 'Failed to load')); }
    finally { setLoading(false); }
  };
  useEffect(() => { fetchAll(); }, []);

  const filteredSlabs = useMemo(() => {
    const q = search.trim().toLowerCase();
    return slabs.filter(s => !q || s.fy.toLowerCase().includes(q) || s.name.toLowerCase().includes(q));
  }, [slabs, search]);
  const filteredLimits = useMemo(() => {
    const q = search.trim().toLowerCase();
    return limits.filter(l => !q || l.fy.toLowerCase().includes(q) || l.section_code.toLowerCase().includes(q));
  }, [limits, search]);

  const openCreateSlab = () => {
    setEditingSlab(null);
    setSlabForm({
      fy: '24-25', name: 'FY 2024-25', slabs_json_text: DEFAULT_SLABS,
      standard_deduction_old: 50000, standard_deduction_new: 75000,
      rebate_87a_old_threshold: 500000, rebate_87a_old_max: 12500,
      rebate_87a_new_threshold: 700000, rebate_87a_new_max: 25000,
      cess_rate: 4.0, is_active: true, notes: '',
    });
    setSlabModal(true);
  };
  const openEditSlab = (s: SlabConfig) => {
    setEditingSlab(s);
    setSlabForm({
      fy: s.fy, name: s.name,
      slabs_json_text: JSON.stringify(s.slabs_json, null, 2),
      standard_deduction_old: s.standard_deduction_old,
      standard_deduction_new: s.standard_deduction_new,
      rebate_87a_old_threshold: s.rebate_87a_old_threshold,
      rebate_87a_old_max: s.rebate_87a_old_max,
      rebate_87a_new_threshold: s.rebate_87a_new_threshold,
      rebate_87a_new_max: s.rebate_87a_new_max,
      cess_rate: s.cess_rate, is_active: s.is_active, notes: s.notes || '',
    });
    setSlabModal(true);
  };
  const submitSlab = async () => {
    let parsed: any;
    try { parsed = JSON.parse(slabForm.slabs_json_text); }
    catch (e: any) { toast.error('Invalid JSON: ' + e.message); return; }
    setSubmitting(true);
    try {
      const payload = { ...slabForm, slabs_json: parsed };
      delete (payload as any).slabs_json_text;
      if (editingSlab) {
        await client.patch(ENDPOINTS.TAX.CONFIG_DETAIL(editingSlab.id), payload);
      } else {
        await client.post(ENDPOINTS.TAX.CONFIGS, payload);
      }
      toast.success('Saved'); setSlabModal(false); fetchAll();
    } catch (e: any) { toast.error(errMsg(e, 'Save failed')); }
    finally { setSubmitting(false); }
  };

  const submitLimit = async () => {
    setSubmitting(true);
    try {
      await client.post(ENDPOINTS.TAX.SECTION_LIMITS, limitForm);
      toast.success('Saved'); setLimitModal(false); fetchAll();
    } catch (e: any) { toast.error(errMsg(e, 'Save failed')); }
    finally { setSubmitting(false); }
  };

  const submitGrat = async () => {
    setSubmitting(true);
    try {
      await client.post(ENDPOINTS.TAX.GRATUITY_CONFIGS, gratForm);
      toast.success('Saved'); setGratModal(false); fetchAll();
    } catch (e: any) { toast.error(errMsg(e, 'Save failed')); }
    finally { setSubmitting(false); }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <FileText className="w-6 h-6 text-blue-600" /> Tax Configuration
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            FY-scoped slabs (both regimes), Section limits and Gratuity config.
            Effective-dated — historical FYs replay correctly.
          </p>
        </div>
        <div className="flex gap-2">
          {tab === 'slabs' && <Button onClick={openCreateSlab}><Plus className="w-4 h-4 mr-2" /> New FY config</Button>}
          {tab === 'sections' && <Button onClick={() => setLimitModal(true)}><Plus className="w-4 h-4 mr-2" /> New limit</Button>}
          {tab === 'gratuity' && <Button onClick={() => setGratModal(true)}><Plus className="w-4 h-4 mr-2" /> New gratuity config</Button>}
        </div>
      </div>

      <Card className="p-4">
        <div className="flex items-center gap-2 mb-3">
          {([
            ['slabs', 'TaxSlabConfig', FileText],
            ['sections', 'Section Limits', BookOpen],
            ['gratuity', 'Gratuity Config', Award],
          ] as const).map(([t, label, Icon]) => (
            <button key={t}
              onClick={() => setTab(t as any)}
              className={cn(
                'px-3 py-1.5 text-sm rounded-md font-medium flex items-center gap-2',
                tab === t ? 'bg-blue-600 text-white' : 'bg-slate-100 text-slate-700',
              )}>
              <Icon className="w-3 h-3" /> {label}
            </button>
          ))}
          <div className="relative flex-1 max-w-sm ml-auto">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <Input placeholder="Search…" value={search}
              onChange={e => setSearch(e.target.value)} className="pl-9" />
          </div>
          <Button variant="outline" onClick={fetchAll}><RefreshCw className="w-4 h-4" /></Button>
        </div>

        {loading ? <div className="py-8 text-center text-slate-500">Loading…</div>
          : tab === 'slabs' ? (
            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead className="text-left text-xs uppercase text-slate-500 border-b">
                  <tr>
                    <th className="p-3">FY</th>
                    <th className="p-3">Name</th>
                    <th className="p-3">Std deduction (Old/New)</th>
                    <th className="p-3">87A (Old/New)</th>
                    <th className="p-3">Cess</th>
                    <th className="p-3">Status</th>
                    <th className="p-3 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredSlabs.map(s => (
                    <tr key={s.id} className="border-b hover:bg-slate-50">
                      <td className="p-3 font-medium">{s.fy}</td>
                      <td className="p-3">{s.name}</td>
                      <td className="p-3 text-xs">₹{s.standard_deduction_old.toLocaleString('en-IN')} / ₹{s.standard_deduction_new.toLocaleString('en-IN')}</td>
                      <td className="p-3 text-xs">
                        ≤₹{(s.rebate_87a_old_threshold / 1000).toFixed(0)}K cap ₹{s.rebate_87a_old_max.toLocaleString('en-IN')}
                        <br />
                        ≤₹{(s.rebate_87a_new_threshold / 1000).toFixed(0)}K cap ₹{s.rebate_87a_new_max.toLocaleString('en-IN')}
                      </td>
                      <td className="p-3 text-xs">{s.cess_rate}%</td>
                      <td className="p-3">
                        <Badge variant={s.is_active ? 'success' : 'error'}>
                          {s.is_active ? 'Active' : 'Inactive'}
                        </Badge>
                      </td>
                      <td className="p-3 text-right">
                        <Button size="sm" variant="outline" onClick={() => openEditSlab(s)}>
                          <Edit2 className="w-3 h-3" />
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : tab === 'sections' ? (
            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead className="text-left text-xs uppercase text-slate-500 border-b">
                  <tr>
                    <th className="p-3">FY</th>
                    <th className="p-3">Section</th>
                    <th className="p-3">Limit</th>
                    <th className="p-3">Applies to</th>
                    <th className="p-3">Notes</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredLimits.map(l => (
                    <tr key={l.id} className="border-b hover:bg-slate-50">
                      <td className="p-3">{l.fy}</td>
                      <td className="p-3 font-medium">{l.section_code}</td>
                      <td className="p-3 font-mono">
                        {l.is_percentage ? `${l.limit_amount}%` : `₹${l.limit_amount.toLocaleString('en-IN')}`}
                      </td>
                      <td className="p-3 text-xs">{l.applies_to}</td>
                      <td className="p-3 text-xs text-slate-500">{l.notes || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead className="text-left text-xs uppercase text-slate-500 border-b">
                  <tr>
                    <th className="p-3">Effective from</th>
                    <th className="p-3">Statutory cap</th>
                    <th className="p-3">Eligibility years</th>
                    <th className="p-3">Days basis</th>
                    <th className="p-3">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {gconfigs.map(g => (
                    <tr key={g.id} className="border-b hover:bg-slate-50">
                      <td className="p-3 font-medium">{g.effective_from}</td>
                      <td className="p-3 font-mono">₹{g.statutory_cap.toLocaleString('en-IN')}</td>
                      <td className="p-3">{g.eligibility_years}</td>
                      <td className="p-3">{g.days_basis}</td>
                      <td className="p-3">
                        <Badge variant={g.is_active ? 'success' : 'error'}>
                          {g.is_active ? 'Active' : 'Inactive'}
                        </Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
      </Card>

      {/* Slab modal */}
      <Dialog open={slabModal} onOpenChange={setSlabModal}>
        <DialogContent className="max-w-3xl">
          <DialogTitle>{editingSlab ? 'Edit' : 'New'} Tax Slab Config</DialogTitle>
          <div className="space-y-3 mt-4 max-h-[65vh] overflow-y-auto pr-1">
            <div className="grid grid-cols-3 gap-3">
              <div>
                <label className="text-xs font-semibold text-slate-600">FY (e.g. 24-25)</label>
                <Input value={slabForm.fy}
                  onChange={e => setSlabForm({ ...slabForm, fy: e.target.value })} />
              </div>
              <div className="col-span-2">
                <label className="text-xs font-semibold text-slate-600">Name</label>
                <Input value={slabForm.name}
                  onChange={e => setSlabForm({ ...slabForm, name: e.target.value })} />
              </div>
            </div>
            <div>
              <label className="text-xs font-semibold text-slate-600">Slabs JSON (both regimes + surcharge)</label>
              <textarea value={slabForm.slabs_json_text}
                onChange={e => setSlabForm({ ...slabForm, slabs_json_text: e.target.value })}
                className="w-full border border-slate-200 rounded-md p-2 text-xs font-mono"
                rows={12} />
              <div className="text-[10px] text-slate-400 mt-1">
                Schema: {`{ old: [{upto, rate}], new: [...], surcharge_old: [...], surcharge_new: [...] }`}
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs text-slate-600">Std deduction (Old) ₹</label>
                <Input type="number" min={0} value={slabForm.standard_deduction_old}
                  onChange={e => setSlabForm({ ...slabForm, standard_deduction_old: Number(e.target.value) })} />
              </div>
              <div>
                <label className="text-xs text-slate-600">Std deduction (New) ₹</label>
                <Input type="number" min={0} value={slabForm.standard_deduction_new}
                  onChange={e => setSlabForm({ ...slabForm, standard_deduction_new: Number(e.target.value) })} />
              </div>
              <div>
                <label className="text-xs text-slate-600">87A threshold (Old) ₹</label>
                <Input type="number" min={0} value={slabForm.rebate_87a_old_threshold}
                  onChange={e => setSlabForm({ ...slabForm, rebate_87a_old_threshold: Number(e.target.value) })} />
              </div>
              <div>
                <label className="text-xs text-slate-600">87A max (Old) ₹</label>
                <Input type="number" min={0} value={slabForm.rebate_87a_old_max}
                  onChange={e => setSlabForm({ ...slabForm, rebate_87a_old_max: Number(e.target.value) })} />
              </div>
              <div>
                <label className="text-xs text-slate-600">87A threshold (New) ₹</label>
                <Input type="number" min={0} value={slabForm.rebate_87a_new_threshold}
                  onChange={e => setSlabForm({ ...slabForm, rebate_87a_new_threshold: Number(e.target.value) })} />
              </div>
              <div>
                <label className="text-xs text-slate-600">87A max (New) ₹</label>
                <Input type="number" min={0} value={slabForm.rebate_87a_new_max}
                  onChange={e => setSlabForm({ ...slabForm, rebate_87a_new_max: Number(e.target.value) })} />
              </div>
              <div>
                <label className="text-xs text-slate-600">Cess rate %</label>
                <Input type="number" min={0} step={0.01} value={slabForm.cess_rate}
                  onChange={e => setSlabForm({ ...slabForm, cess_rate: Number(e.target.value) })} />
              </div>
              <div className="flex items-end">
                <label className="text-sm flex items-center gap-2">
                  <input type="checkbox" checked={slabForm.is_active}
                    onChange={e => setSlabForm({ ...slabForm, is_active: e.target.checked })} />
                  Active
                </label>
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setSlabModal(false)}>Cancel</Button>
            <Button isLoading={submitting} onClick={submitSlab}>Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Limit modal */}
      <Dialog open={limitModal} onOpenChange={setLimitModal}>
        <DialogContent className="max-w-md">
          <DialogTitle>New Section Limit</DialogTitle>
          <div className="space-y-3 mt-4">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs text-slate-600">FY</label>
                <Input value={limitForm.fy}
                  onChange={e => setLimitForm({ ...limitForm, fy: e.target.value })} />
              </div>
              <div>
                <label className="text-xs text-slate-600">Section code</label>
                <Input value={limitForm.section_code}
                  onChange={e => setLimitForm({ ...limitForm, section_code: e.target.value })}
                  placeholder="80C, 80D, 80CCD_1B…" />
              </div>
            </div>
            <div>
              <label className="text-xs text-slate-600">Limit amount</label>
              <Input type="number" min={0} value={limitForm.limit_amount}
                onChange={e => setLimitForm({ ...limitForm, limit_amount: Number(e.target.value) })} />
            </div>
            <div>
              <label className="text-xs text-slate-600">Applies to</label>
              <select value={limitForm.applies_to}
                onChange={e => setLimitForm({ ...limitForm, applies_to: e.target.value as any })}
                className="w-full border border-slate-200 rounded-md h-9 px-2 text-sm">
                <option value="BOTH">Both regimes</option>
                <option value="OLD">Old regime only</option>
                <option value="NEW">New regime only</option>
              </select>
            </div>
            <label className="text-sm flex items-center gap-2">
              <input type="checkbox" checked={limitForm.is_percentage}
                onChange={e => setLimitForm({ ...limitForm, is_percentage: e.target.checked })} />
              Limit is a percentage (e.g. HRA metro_pct)
            </label>
            <div>
              <label className="text-xs text-slate-600">Notes</label>
              <Input value={limitForm.notes}
                onChange={e => setLimitForm({ ...limitForm, notes: e.target.value })} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setLimitModal(false)}>Cancel</Button>
            <Button isLoading={submitting} onClick={submitLimit}>Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Gratuity modal */}
      <Dialog open={gratModal} onOpenChange={setGratModal}>
        <DialogContent className="max-w-md">
          <DialogTitle>New Gratuity Config</DialogTitle>
          <div className="space-y-3 mt-4 grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-slate-600">Effective from</label>
              <Input type="date" value={gratForm.effective_from}
                onChange={e => setGratForm({ ...gratForm, effective_from: e.target.value })} />
            </div>
            <div>
              <label className="text-xs text-slate-600">Statutory cap ₹</label>
              <Input type="number" min={0} value={gratForm.statutory_cap}
                onChange={e => setGratForm({ ...gratForm, statutory_cap: Number(e.target.value) })} />
            </div>
            <div>
              <label className="text-xs text-slate-600">Eligibility years</label>
              <Input type="number" min={0} max={20} value={gratForm.eligibility_years}
                onChange={e => setGratForm({ ...gratForm, eligibility_years: Number(e.target.value) })} />
            </div>
            <div>
              <label className="text-xs text-slate-600">Days basis</label>
              <Input type="number" min={1} max={31} value={gratForm.days_basis}
                onChange={e => setGratForm({ ...gratForm, days_basis: Number(e.target.value) })} />
            </div>
            <label className="col-span-2 text-sm flex items-center gap-2">
              <input type="checkbox" checked={gratForm.is_active}
                onChange={e => setGratForm({ ...gratForm, is_active: e.target.checked })} />
              Active
            </label>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setGratModal(false)}>Cancel</Button>
            <Button isLoading={submitting} onClick={submitGrat}>Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};
