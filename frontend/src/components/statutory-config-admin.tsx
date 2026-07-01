/**
 * Statutory config admin: Employer identifiers, effective-dated
 * StatutoryConfig (PF/ESIC rates + ceilings), per-state PT slabs,
 * and per-employee statutory details (UAN / IP / state).
 */
import React, { useEffect, useMemo, useState } from 'react';
import {
  Plus, Edit2, Power, Search, RefreshCw, Building2, Shield, FileText, Users,
} from 'lucide-react';
import { Card, Button, Badge, cn } from './ui-elements';
import { toast } from 'sonner';
import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';
import { Dialog, DialogContent, DialogTitle, DialogFooter } from './ui/dialog';
import { Input } from './ui/input';

interface Employer {
  id: number; name: string; pf_establishment_code: string | null;
  pf_extension: string | null; esic_employer_code: string | null;
  tan: string | null; pan: string | null; lin: string | null;
  default_pt_state: string | null; address_line: string | null;
  is_active: boolean;
}
interface Config {
  id: number; name: string; effective_from: string; is_active: boolean;
  pf_employee_rate: number; pf_employer_rate: number; eps_rate: number;
  pf_wage_ceiling: number; eps_wage_ceiling: number;
  edli_rate: number; edli_wage_ceiling: number; epf_admin_rate: number;
  esic_employee_rate: number; esic_employer_rate: number; esic_wage_ceiling: number;
  notes: string | null;
}
interface PTSlab {
  id: number; state: string; effective_from: string;
  slab_min: number; slab_max: number | null; monthly_amount: number;
  gender: string; month_index: number | null; is_active: boolean;
  notes: string | null;
}

const errMsg = (e: any, f: string) => {
  const d = e?.response?.data?.detail;
  if (typeof d === 'string') return d;
  if (Array.isArray(d)) return d.map((x: any) => x?.msg || JSON.stringify(x)).join('; ');
  return e?.message || f;
};

const today = () => new Date().toISOString().slice(0, 10);

export const StatutoryConfigAdmin: React.FC = () => {
  const [tab, setTab] = useState<'configs' | 'employers' | 'pt' | 'details'>('configs');
  const [configs, setConfigs] = useState<Config[]>([]);
  const [employers, setEmployers] = useState<Employer[]>([]);
  const [ptSlabs, setPtSlabs] = useState<PTSlab[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');

  // modals
  const [configOpen, setConfigOpen] = useState(false);
  const [editingConfig, setEditingConfig] = useState<Config | null>(null);
  const [configForm, setConfigForm] = useState({
    name: '', effective_from: today(), is_active: true,
    pf_employee_rate: 12, pf_employer_rate: 12, eps_rate: 8.33,
    pf_wage_ceiling: 15000, eps_wage_ceiling: 15000,
    edli_rate: 0.5, edli_wage_ceiling: 15000, epf_admin_rate: 0.5,
    esic_employee_rate: 0.75, esic_employer_rate: 3.25, esic_wage_ceiling: 21000,
    notes: '',
  });

  const [empOpen, setEmpOpen] = useState(false);
  const [editingEmp, setEditingEmp] = useState<Employer | null>(null);
  const [empForm, setEmpForm] = useState({
    name: '', pf_establishment_code: '', pf_extension: '', esic_employer_code: '',
    tan: '', pan: '', lin: '', default_pt_state: '', address_line: '', is_active: true,
  });

  const [ptOpen, setPtOpen] = useState(false);
  const [ptForm, setPtForm] = useState({
    state: 'WB', effective_from: today(),
    slab_min: 0, slab_max: '' as number | '', monthly_amount: 0,
    gender: 'ALL' as 'ALL' | 'M' | 'F' | 'O',
    month_index: '' as number | '', is_active: true, notes: '',
  });

  const [busy, setBusy] = useState(false);

  const fetchAll = async () => {
    setLoading(true);
    try {
      const [c, e, p] = await Promise.all([
        client.get(ENDPOINTS.STATUTORY.CONFIGS),
        client.get(ENDPOINTS.STATUTORY.EMPLOYERS),
        client.get(ENDPOINTS.STATUTORY.PT_SLABS),
      ]);
      setConfigs(c.data || []); setEmployers(e.data || []); setPtSlabs(p.data || []);
    } catch (e: any) { toast.error(errMsg(e, 'Failed to load')); }
    finally { setLoading(false); }
  };

  useEffect(() => { fetchAll(); }, []);

  const filteredConfigs = useMemo(() => {
    const q = search.trim().toLowerCase();
    return configs.filter(c => !q || c.name.toLowerCase().includes(q));
  }, [configs, search]);
  const filteredEmployers = useMemo(() => {
    const q = search.trim().toLowerCase();
    return employers.filter(e => !q || e.name.toLowerCase().includes(q));
  }, [employers, search]);
  const filteredPT = useMemo(() => {
    const q = search.trim().toLowerCase();
    return ptSlabs.filter(s => !q || s.state.toLowerCase().includes(q));
  }, [ptSlabs, search]);

  const openCreateConfig = () => {
    setEditingConfig(null);
    setConfigForm({
      name: '', effective_from: today(), is_active: true,
      pf_employee_rate: 12, pf_employer_rate: 12, eps_rate: 8.33,
      pf_wage_ceiling: 15000, eps_wage_ceiling: 15000,
      edli_rate: 0.5, edli_wage_ceiling: 15000, epf_admin_rate: 0.5,
      esic_employee_rate: 0.75, esic_employer_rate: 3.25, esic_wage_ceiling: 21000,
      notes: '',
    });
    setConfigOpen(true);
  };
  const openEditConfig = (c: Config) => {
    setEditingConfig(c);
    setConfigForm({
      name: c.name, effective_from: c.effective_from, is_active: c.is_active,
      pf_employee_rate: c.pf_employee_rate, pf_employer_rate: c.pf_employer_rate,
      eps_rate: c.eps_rate,
      pf_wage_ceiling: c.pf_wage_ceiling, eps_wage_ceiling: c.eps_wage_ceiling,
      edli_rate: c.edli_rate, edli_wage_ceiling: c.edli_wage_ceiling,
      epf_admin_rate: c.epf_admin_rate,
      esic_employee_rate: c.esic_employee_rate, esic_employer_rate: c.esic_employer_rate,
      esic_wage_ceiling: c.esic_wage_ceiling, notes: c.notes || '',
    });
    setConfigOpen(true);
  };
  const submitConfig = async () => {
    setBusy(true);
    try {
      if (editingConfig) {
        await client.patch(ENDPOINTS.STATUTORY.CONFIG_DETAIL(editingConfig.id), configForm);
      } else {
        await client.post(ENDPOINTS.STATUTORY.CONFIGS, configForm);
      }
      toast.success('Saved'); setConfigOpen(false); fetchAll();
    } catch (e: any) { toast.error(errMsg(e, 'Save failed')); }
    finally { setBusy(false); }
  };

  const openCreateEmp = () => {
    setEditingEmp(null);
    setEmpForm({
      name: '', pf_establishment_code: '', pf_extension: '', esic_employer_code: '',
      tan: '', pan: '', lin: '', default_pt_state: '', address_line: '', is_active: true,
    });
    setEmpOpen(true);
  };
  const openEditEmp = (e: Employer) => {
    setEditingEmp(e);
    setEmpForm({
      name: e.name, pf_establishment_code: e.pf_establishment_code || '',
      pf_extension: e.pf_extension || '', esic_employer_code: e.esic_employer_code || '',
      tan: e.tan || '', pan: e.pan || '', lin: e.lin || '',
      default_pt_state: e.default_pt_state || '', address_line: e.address_line || '',
      is_active: e.is_active,
    });
    setEmpOpen(true);
  };
  const submitEmp = async () => {
    setBusy(true);
    try {
      if (editingEmp) {
        await client.patch(ENDPOINTS.STATUTORY.EMPLOYER_DETAIL(editingEmp.id), empForm);
      } else {
        await client.post(ENDPOINTS.STATUTORY.EMPLOYERS, empForm);
      }
      toast.success('Saved'); setEmpOpen(false); fetchAll();
    } catch (e: any) { toast.error(errMsg(e, 'Save failed')); }
    finally { setBusy(false); }
  };

  const submitPt = async () => {
    setBusy(true);
    try {
      await client.post(ENDPOINTS.STATUTORY.PT_SLABS, {
        state: ptForm.state.toUpperCase(),
        effective_from: ptForm.effective_from,
        slab_min: Number(ptForm.slab_min),
        slab_max: ptForm.slab_max === '' ? null : Number(ptForm.slab_max),
        monthly_amount: Number(ptForm.monthly_amount),
        gender: ptForm.gender,
        month_index: ptForm.month_index === '' ? null : Number(ptForm.month_index),
        is_active: ptForm.is_active, notes: ptForm.notes || null,
      });
      toast.success('Slab added'); setPtOpen(false); fetchAll();
    } catch (e: any) { toast.error(errMsg(e, 'Save failed')); }
    finally { setBusy(false); }
  };

  const togglePtSlab = async (s: PTSlab) => {
    try {
      if (s.is_active) await client.delete(ENDPOINTS.STATUTORY.PT_SLAB_DETAIL(s.id));
      else await client.patch(ENDPOINTS.STATUTORY.PT_SLAB_DETAIL(s.id), { is_active: true });
      fetchAll();
    } catch (e: any) { toast.error(errMsg(e, 'Toggle failed')); }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Shield className="w-6 h-6 text-blue-600" /> Statutory Configuration
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Effective-dated PF/ESIC rates + ceilings, employer identifiers and per-state PT slabs.
          </p>
        </div>
        <div className="flex gap-2">
          {tab === 'configs' && <Button onClick={openCreateConfig}><Plus className="w-4 h-4 mr-2" /> New config</Button>}
          {tab === 'employers' && <Button onClick={openCreateEmp}><Plus className="w-4 h-4 mr-2" /> New employer</Button>}
          {tab === 'pt' && <Button onClick={() => setPtOpen(true)}><Plus className="w-4 h-4 mr-2" /> New PT slab</Button>}
        </div>
      </div>

      <Card className="p-4">
        <div className="flex items-center gap-2 mb-3">
          {([
            ['configs', 'PF / ESIC config', FileText],
            ['employers', 'Employer IDs', Building2],
            ['pt', 'PT slabs', Shield],
            ['details', 'Employee details', Users],
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
          : tab === 'configs' ? (
            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead className="text-left text-xs uppercase text-slate-500 border-b">
                  <tr>
                    <th className="p-3">Name</th>
                    <th className="p-3">Effective from</th>
                    <th className="p-3">PF (EE/ER/EPS)</th>
                    <th className="p-3">PF ceiling</th>
                    <th className="p-3">ESIC (EE/ER)</th>
                    <th className="p-3">ESIC ceiling</th>
                    <th className="p-3">Status</th>
                    <th className="p-3 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredConfigs.map(c => (
                    <tr key={c.id} className="border-b hover:bg-slate-50">
                      <td className="p-3 font-medium">{c.name}</td>
                      <td className="p-3">{c.effective_from}</td>
                      <td className="p-3 text-xs">{c.pf_employee_rate}% / {c.pf_employer_rate}% / {c.eps_rate}%</td>
                      <td className="p-3 text-xs">₹{c.pf_wage_ceiling.toLocaleString('en-IN')}</td>
                      <td className="p-3 text-xs">{c.esic_employee_rate}% / {c.esic_employer_rate}%</td>
                      <td className="p-3 text-xs">₹{c.esic_wage_ceiling.toLocaleString('en-IN')}</td>
                      <td className="p-3">
                        <Badge variant={c.is_active ? 'success' : 'error'}>{c.is_active ? 'Active' : 'Inactive'}</Badge>
                      </td>
                      <td className="p-3 text-right">
                        <Button size="sm" variant="outline" onClick={() => openEditConfig(c)}>
                          <Edit2 className="w-3 h-3" />
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : tab === 'employers' ? (
            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead className="text-left text-xs uppercase text-slate-500 border-b">
                  <tr>
                    <th className="p-3">Name</th>
                    <th className="p-3">PF code</th>
                    <th className="p-3">ESIC code</th>
                    <th className="p-3">TAN / PAN</th>
                    <th className="p-3">Default PT state</th>
                    <th className="p-3">Status</th>
                    <th className="p-3 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredEmployers.map(e => (
                    <tr key={e.id} className="border-b hover:bg-slate-50">
                      <td className="p-3 font-medium">{e.name}</td>
                      <td className="p-3 text-xs">{e.pf_establishment_code || '—'}{e.pf_extension ? `/${e.pf_extension}` : ''}</td>
                      <td className="p-3 text-xs">{e.esic_employer_code || '—'}</td>
                      <td className="p-3 text-xs">{e.tan || '—'} / {e.pan || '—'}</td>
                      <td className="p-3 text-xs">{e.default_pt_state || '—'}</td>
                      <td className="p-3">
                        <Badge variant={e.is_active ? 'success' : 'error'}>{e.is_active ? 'Active' : 'Inactive'}</Badge>
                      </td>
                      <td className="p-3 text-right">
                        <Button size="sm" variant="outline" onClick={() => openEditEmp(e)}>
                          <Edit2 className="w-3 h-3" />
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : tab === 'pt' ? (
            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead className="text-left text-xs uppercase text-slate-500 border-b">
                  <tr>
                    <th className="p-3">State</th>
                    <th className="p-3">Effective</th>
                    <th className="p-3">Slab</th>
                    <th className="p-3">Amount</th>
                    <th className="p-3">Gender</th>
                    <th className="p-3">Month override</th>
                    <th className="p-3">Status</th>
                    <th className="p-3 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredPT.map(s => (
                    <tr key={s.id} className="border-b hover:bg-slate-50">
                      <td className="p-3 font-medium">{s.state}</td>
                      <td className="p-3 text-xs">{s.effective_from}</td>
                      <td className="p-3 text-xs">
                        ₹{s.slab_min.toLocaleString('en-IN')} – {s.slab_max != null ? `₹${s.slab_max.toLocaleString('en-IN')}` : 'above'}
                      </td>
                      <td className="p-3 font-mono">₹{s.monthly_amount}</td>
                      <td className="p-3 text-xs">{s.gender}</td>
                      <td className="p-3 text-xs">{s.month_index || '—'}</td>
                      <td className="p-3">
                        <Badge variant={s.is_active ? 'success' : 'error'}>{s.is_active ? 'Active' : 'Inactive'}</Badge>
                      </td>
                      <td className="p-3 text-right">
                        <Button size="sm" variant="outline" onClick={() => togglePtSlab(s)}>
                          <Power className={cn('w-3 h-3', s.is_active ? 'text-red-600' : 'text-green-600')} />
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="p-12 text-center text-slate-500">
              Employee statutory details (UAN / ESIC IP / PT state / continuation)
              are edited from the employee directory (see employee row → Statutory tab).
              <br />
              API: <code>PUT /statutory/employee-details</code> with employee_id payload.
            </div>
          )}
      </Card>

      {/* Config modal */}
      <Dialog open={configOpen} onOpenChange={setConfigOpen}>
        <DialogContent className="max-w-2xl">
          <DialogTitle>{editingConfig ? 'Edit' : 'New'} Statutory Config</DialogTitle>
          <div className="space-y-4 mt-4 max-h-[60vh] overflow-y-auto pr-1">
            <div className="grid grid-cols-2 gap-3">
              <div className="col-span-2">
                <label className="text-xs font-semibold text-slate-600">Name</label>
                <Input value={configForm.name}
                  onChange={e => setConfigForm({ ...configForm, name: e.target.value })} />
              </div>
              <div>
                <label className="text-xs font-semibold text-slate-600">Effective from</label>
                <Input type="date" value={configForm.effective_from}
                  onChange={e => setConfigForm({ ...configForm, effective_from: e.target.value })} />
              </div>
              <div className="flex items-end">
                <label className="text-sm flex items-center gap-2">
                  <input type="checkbox" checked={configForm.is_active}
                    onChange={e => setConfigForm({ ...configForm, is_active: e.target.checked })} />
                  Active
                </label>
              </div>
              <div className="col-span-2 mt-3 text-[10px] font-semibold text-blue-700 uppercase tracking-wide">EPF</div>
              <div>
                <label className="text-xs text-slate-600">Employee rate %</label>
                <Input type="number" step={0.01} value={configForm.pf_employee_rate}
                  onChange={e => setConfigForm({ ...configForm, pf_employee_rate: Number(e.target.value) })} />
              </div>
              <div>
                <label className="text-xs text-slate-600">Employer rate %</label>
                <Input type="number" step={0.01} value={configForm.pf_employer_rate}
                  onChange={e => setConfigForm({ ...configForm, pf_employer_rate: Number(e.target.value) })} />
              </div>
              <div>
                <label className="text-xs text-slate-600">EPS rate % (of employer)</label>
                <Input type="number" step={0.01} value={configForm.eps_rate}
                  onChange={e => setConfigForm({ ...configForm, eps_rate: Number(e.target.value) })} />
              </div>
              <div>
                <label className="text-xs text-slate-600">PF wage ceiling ₹</label>
                <Input type="number" step={100} value={configForm.pf_wage_ceiling}
                  onChange={e => setConfigForm({ ...configForm, pf_wage_ceiling: Number(e.target.value) })} />
              </div>
              <div>
                <label className="text-xs text-slate-600">EPS wage ceiling ₹</label>
                <Input type="number" step={100} value={configForm.eps_wage_ceiling}
                  onChange={e => setConfigForm({ ...configForm, eps_wage_ceiling: Number(e.target.value) })} />
              </div>
              <div>
                <label className="text-xs text-slate-600">EDLI ceiling ₹</label>
                <Input type="number" step={100} value={configForm.edli_wage_ceiling}
                  onChange={e => setConfigForm({ ...configForm, edli_wage_ceiling: Number(e.target.value) })} />
              </div>
              <div>
                <label className="text-xs text-slate-600">EDLI rate %</label>
                <Input type="number" step={0.01} value={configForm.edli_rate}
                  onChange={e => setConfigForm({ ...configForm, edli_rate: Number(e.target.value) })} />
              </div>
              <div>
                <label className="text-xs text-slate-600">EPF admin %</label>
                <Input type="number" step={0.01} value={configForm.epf_admin_rate}
                  onChange={e => setConfigForm({ ...configForm, epf_admin_rate: Number(e.target.value) })} />
              </div>

              <div className="col-span-2 mt-3 text-[10px] font-semibold text-purple-700 uppercase tracking-wide">ESIC</div>
              <div>
                <label className="text-xs text-slate-600">Employee rate %</label>
                <Input type="number" step={0.01} value={configForm.esic_employee_rate}
                  onChange={e => setConfigForm({ ...configForm, esic_employee_rate: Number(e.target.value) })} />
              </div>
              <div>
                <label className="text-xs text-slate-600">Employer rate %</label>
                <Input type="number" step={0.01} value={configForm.esic_employer_rate}
                  onChange={e => setConfigForm({ ...configForm, esic_employer_rate: Number(e.target.value) })} />
              </div>
              <div className="col-span-2">
                <label className="text-xs text-slate-600">ESIC wage ceiling ₹</label>
                <Input type="number" step={100} value={configForm.esic_wage_ceiling}
                  onChange={e => setConfigForm({ ...configForm, esic_wage_ceiling: Number(e.target.value) })} />
              </div>
              <div className="col-span-2">
                <label className="text-xs text-slate-600">Notes</label>
                <textarea value={configForm.notes}
                  onChange={e => setConfigForm({ ...configForm, notes: e.target.value })}
                  className="w-full border border-slate-200 rounded-md p-2 text-sm" rows={2} />
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfigOpen(false)}>Cancel</Button>
            <Button isLoading={busy} onClick={submitConfig}>Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Employer modal */}
      <Dialog open={empOpen} onOpenChange={setEmpOpen}>
        <DialogContent className="max-w-xl">
          <DialogTitle>{editingEmp ? 'Edit' : 'New'} Employer Identifier</DialogTitle>
          <div className="grid grid-cols-2 gap-3 mt-4">
            <div className="col-span-2">
              <label className="text-xs font-semibold text-slate-600">Name</label>
              <Input value={empForm.name}
                onChange={e => setEmpForm({ ...empForm, name: e.target.value })} />
            </div>
            <div>
              <label className="text-xs text-slate-600">PF establishment code</label>
              <Input value={empForm.pf_establishment_code}
                onChange={e => setEmpForm({ ...empForm, pf_establishment_code: e.target.value })} />
            </div>
            <div>
              <label className="text-xs text-slate-600">PF extension</label>
              <Input value={empForm.pf_extension}
                onChange={e => setEmpForm({ ...empForm, pf_extension: e.target.value })} />
            </div>
            <div>
              <label className="text-xs text-slate-600">ESIC employer code</label>
              <Input value={empForm.esic_employer_code}
                onChange={e => setEmpForm({ ...empForm, esic_employer_code: e.target.value })} />
            </div>
            <div>
              <label className="text-xs text-slate-600">TAN</label>
              <Input value={empForm.tan}
                onChange={e => setEmpForm({ ...empForm, tan: e.target.value })} />
            </div>
            <div>
              <label className="text-xs text-slate-600">PAN</label>
              <Input value={empForm.pan}
                onChange={e => setEmpForm({ ...empForm, pan: e.target.value })} />
            </div>
            <div>
              <label className="text-xs text-slate-600">LIN</label>
              <Input value={empForm.lin}
                onChange={e => setEmpForm({ ...empForm, lin: e.target.value })} />
            </div>
            <div>
              <label className="text-xs text-slate-600">Default PT state</label>
              <Input value={empForm.default_pt_state}
                onChange={e => setEmpForm({ ...empForm, default_pt_state: e.target.value })}
                placeholder="e.g. WB, MH, KA" />
            </div>
            <div className="col-span-2">
              <label className="text-xs text-slate-600">Address</label>
              <Input value={empForm.address_line}
                onChange={e => setEmpForm({ ...empForm, address_line: e.target.value })} />
            </div>
            <label className="col-span-2 text-sm flex items-center gap-2">
              <input type="checkbox" checked={empForm.is_active}
                onChange={e => setEmpForm({ ...empForm, is_active: e.target.checked })} />
              Active
            </label>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEmpOpen(false)}>Cancel</Button>
            <Button isLoading={busy} onClick={submitEmp}>Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* PT slab modal */}
      <Dialog open={ptOpen} onOpenChange={setPtOpen}>
        <DialogContent className="max-w-md">
          <DialogTitle>New PT slab</DialogTitle>
          <div className="space-y-3 mt-4">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs text-slate-600">State (code or name)</label>
                <Input value={ptForm.state}
                  onChange={e => setPtForm({ ...ptForm, state: e.target.value })} />
              </div>
              <div>
                <label className="text-xs text-slate-600">Effective from</label>
                <Input type="date" value={ptForm.effective_from}
                  onChange={e => setPtForm({ ...ptForm, effective_from: e.target.value })} />
              </div>
              <div>
                <label className="text-xs text-slate-600">Slab min ₹</label>
                <Input type="number" min={0} value={ptForm.slab_min}
                  onChange={e => setPtForm({ ...ptForm, slab_min: Number(e.target.value) })} />
              </div>
              <div>
                <label className="text-xs text-slate-600">Slab max ₹ (blank = above)</label>
                <Input type="number" min={0} value={ptForm.slab_max}
                  onChange={e => setPtForm({ ...ptForm, slab_max: e.target.value === '' ? '' : Number(e.target.value) })} />
              </div>
              <div>
                <label className="text-xs text-slate-600">Monthly amount ₹</label>
                <Input type="number" min={0} value={ptForm.monthly_amount}
                  onChange={e => setPtForm({ ...ptForm, monthly_amount: Number(e.target.value) })} />
              </div>
              <div>
                <label className="text-xs text-slate-600">Gender</label>
                <select value={ptForm.gender}
                  onChange={e => setPtForm({ ...ptForm, gender: e.target.value as any })}
                  className="w-full border border-slate-200 rounded-md h-9 px-2 text-sm">
                  <option value="ALL">ALL</option>
                  <option value="M">M</option>
                  <option value="F">F</option>
                  <option value="O">O</option>
                </select>
              </div>
              <div className="col-span-2">
                <label className="text-xs text-slate-600">Month override (1-12, blank = every month)</label>
                <Input type="number" min={1} max={12} value={ptForm.month_index}
                  onChange={e => setPtForm({ ...ptForm, month_index: e.target.value === '' ? '' : Number(e.target.value) })} />
              </div>
              <div className="col-span-2">
                <label className="text-xs text-slate-600">Notes</label>
                <Input value={ptForm.notes}
                  onChange={e => setPtForm({ ...ptForm, notes: e.target.value })} />
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setPtOpen(false)}>Cancel</Button>
            <Button isLoading={busy} onClick={submitPt}>Add slab</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};
