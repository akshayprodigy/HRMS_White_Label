import React, { useState, useEffect } from 'react';
import {
  Banknote, Plus, Search, Eye, XCircle, FileX, DollarSign,
  ArrowLeft, Loader2, ChevronRight, Clock, CheckCircle2,
  AlertTriangle, RotateCcw
} from 'lucide-react';
import { Card, Button, Badge, cn } from './ui-elements';
import { toast } from 'sonner';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from './ui/dialog';
import { Input } from './ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';
import type { SalaryAdvance, AdvanceRecovery } from '../types/erp';

const STATUS_CONFIG: Record<string, { label: string; color: string; icon: any }> = {
  active: { label: 'Active', color: 'bg-blue-100 text-blue-700', icon: Clock },
  fully_recovered: { label: 'Fully Recovered', color: 'bg-green-100 text-green-700', icon: CheckCircle2 },
  written_off: { label: 'Written Off', color: 'bg-amber-100 text-amber-700', icon: FileX },
  cancelled: { label: 'Cancelled', color: 'bg-red-100 text-red-700', icon: XCircle },
};

const getError = (error: any, fallback: string) =>
  error?.response?.data?.error?.message ||
  error?.response?.data?.detail ||
  error?.message ||
  fallback;

export const SalaryAdvanceManagement = () => {
  const [view, setView] = useState<'list' | 'detail'>('list');
  const [advances, setAdvances] = useState<SalaryAdvance[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedAdvance, setSelectedAdvance] = useState<SalaryAdvance | null>(null);
  const [recoveries, setRecoveries] = useState<AdvanceRecovery[]>([]);
  const [statusFilter, setStatusFilter] = useState('');
  const [search, setSearch] = useState('');
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showRecoverModal, setShowRecoverModal] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);

  // Employee list for create modal
  const [employees, setEmployees] = useState<any[]>([]);

  useEffect(() => { fetchAdvances(); }, [statusFilter]);

  const fetchAdvances = async () => {
    setLoading(true);
    try {
      const params: any = {};
      if (statusFilter) params.status = statusFilter;
      const res = await client.get(ENDPOINTS.HR.ADVANCES, { params });
      setAdvances(res.data);
    } catch (e: any) {
      toast.error(getError(e, 'Failed to fetch advances'));
    } finally {
      setLoading(false);
    }
  };

  const fetchEmployees = async () => {
    try {
      const res = await client.get(ENDPOINTS.HR.EMPLOYEES, { params: { size: 100 } });
      setEmployees(res.data.items || res.data);
    } catch {}
  };

  const openDetail = async (adv: SalaryAdvance) => {
    setSelectedAdvance(adv);
    setView('detail');
    try {
      const res = await client.get(ENDPOINTS.HR.ADVANCE_RECOVERIES(adv.id));
      setRecoveries(res.data);
    } catch {}
  };

  const handleWriteOff = async () => {
    if (!selectedAdvance) return;
    setActionLoading(true);
    try {
      await client.post(ENDPOINTS.HR.ADVANCE_WRITE_OFF(selectedAdvance.id), { remarks: 'Written off by HR' });
      toast.success('Advance written off');
      fetchAdvances();
      setView('list');
    } catch (e: any) {
      toast.error(getError(e, 'Failed to write off'));
    } finally {
      setActionLoading(false);
    }
  };

  const handleCancel = async () => {
    if (!selectedAdvance) return;
    setActionLoading(true);
    try {
      await client.post(ENDPOINTS.HR.ADVANCE_CANCEL(selectedAdvance.id));
      toast.success('Advance cancelled');
      fetchAdvances();
      setView('list');
    } catch (e: any) {
      toast.error(getError(e, 'Failed to cancel'));
    } finally {
      setActionLoading(false);
    }
  };

  const filtered = advances.filter(a => {
    if (!search) return true;
    const q = search.toLowerCase();
    return (
      a.employee_name?.toLowerCase().includes(q) ||
      a.employee_code?.toLowerCase().includes(q) ||
      a.department?.toLowerCase().includes(q)
    );
  });

  const totalOutstanding = advances
    .filter(a => a.status === 'active')
    .reduce((s, a) => s + (a.outstanding || 0), 0);

  const totalDisbursed = advances
    .filter(a => a.status !== 'cancelled')
    .reduce((s, a) => s + a.amount, 0);

  if (view === 'detail' && selectedAdvance) {
    const st = STATUS_CONFIG[selectedAdvance.status] || STATUS_CONFIG.active;
    return (
      <div className="p-8 max-w-[1000px] mx-auto animate-in slide-in-from-bottom duration-500">
        <div className="flex items-center gap-4 mb-8">
          <button onClick={() => setView('list')} className="p-3 bg-white border border-slate-200 rounded-2xl hover:bg-slate-50 transition-colors">
            <ArrowLeft size={20} className="text-slate-600" />
          </button>
          <div className="flex-1">
            <h2 className="text-2xl font-black text-[#0F172A] tracking-tight">{selectedAdvance.employee_name}</h2>
            <p className="text-[#64748B] text-sm font-bold">{selectedAdvance.employee_code} &middot; {selectedAdvance.department}</p>
          </div>
          <Badge className={cn('text-xs font-black px-3 py-1', st.color)}>{st.label}</Badge>
        </div>

        {/* Summary Cards */}
        <div className="grid grid-cols-4 gap-4 mb-8">
          {[
            { label: 'Amount', value: `\u20B9${selectedAdvance.amount.toLocaleString('en-IN')}`, color: 'text-blue-600' },
            { label: 'Recovered', value: `\u20B9${selectedAdvance.recovered_amount.toLocaleString('en-IN')}`, color: 'text-green-600' },
            { label: 'Outstanding', value: `\u20B9${(selectedAdvance.outstanding || 0).toLocaleString('en-IN')}`, color: 'text-red-600' },
            { label: 'Monthly EMI', value: `\u20B9${(selectedAdvance.monthly_emi || 0).toLocaleString('en-IN')}`, color: 'text-amber-600' },
          ].map((c, i) => (
            <Card key={i} className="p-5 border-slate-200">
              <span className="text-[10px] font-black text-slate-400 uppercase tracking-widest">{c.label}</span>
              <p className={cn("text-xl font-black mt-1", c.color)}>{c.value}</p>
            </Card>
          ))}
        </div>

        {/* Details */}
        <Card className="p-6 border-slate-200 mb-6">
          <h3 className="text-sm font-black text-slate-900 mb-4 uppercase tracking-widest">Details</h3>
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div><span className="text-slate-400 font-bold">Disbursed Date:</span> <span className="font-black text-slate-900 ml-2">{new Date(selectedAdvance.disbursed_date).toLocaleDateString()}</span></div>
            <div><span className="text-slate-400 font-bold">Recovery Mode:</span> <span className="font-black text-slate-900 ml-2">{selectedAdvance.recovery_mode === 'installment' ? `Installment (${selectedAdvance.installment_months} months)` : 'One Time'}</span></div>
            <div><span className="text-slate-400 font-bold">Approved By:</span> <span className="font-black text-slate-900 ml-2">{selectedAdvance.approved_by_name}</span></div>
            <div><span className="text-slate-400 font-bold">Reason:</span> <span className="font-black text-slate-900 ml-2">{selectedAdvance.reason || '—'}</span></div>
            {selectedAdvance.remarks && (
              <div className="col-span-2"><span className="text-slate-400 font-bold">Remarks:</span> <span className="font-black text-slate-900 ml-2">{selectedAdvance.remarks}</span></div>
            )}
          </div>
        </Card>

        {/* Progress Bar */}
        <Card className="p-6 border-slate-200 mb-6">
          <div className="flex justify-between items-center mb-3">
            <span className="text-sm font-black text-slate-900">Recovery Progress</span>
            <span className="text-sm font-black text-slate-600">{Math.round((selectedAdvance.recovered_amount / selectedAdvance.amount) * 100)}%</span>
          </div>
          <div className="w-full h-3 bg-slate-100 rounded-full overflow-hidden">
            <div
              className="h-full bg-green-500 rounded-full transition-all duration-700"
              style={{ width: `${Math.min(100, (selectedAdvance.recovered_amount / selectedAdvance.amount) * 100)}%` }}
            />
          </div>
        </Card>

        {/* Recovery History */}
        <Card className="p-6 border-slate-200 mb-6">
          <h3 className="text-sm font-black text-slate-900 mb-4 uppercase tracking-widest">Recovery History</h3>
          {recoveries.length === 0 ? (
            <p className="text-slate-400 font-bold text-center py-6">No recoveries recorded yet</p>
          ) : (
            <div className="space-y-3">
              {recoveries.map(r => (
                <div key={r.id} className="flex items-center justify-between p-3 bg-slate-50 rounded-xl">
                  <div>
                    <span className="font-black text-slate-900">{`\u20B9`}{r.amount.toLocaleString('en-IN')}</span>
                    <span className="text-xs text-slate-400 font-bold ml-3">{r.remarks}</span>
                  </div>
                  <span className="text-xs text-slate-500 font-bold">{new Date(r.recovered_at).toLocaleDateString()}</span>
                </div>
              ))}
            </div>
          )}
        </Card>

        {/* Actions */}
        {selectedAdvance.status === 'active' && (
          <div className="flex gap-3 justify-end">
            <Button
              variant="outline"
              onClick={() => setShowRecoverModal(true)}
              className="rounded-xl font-black h-11"
            >
              <DollarSign size={16} className="mr-2" /> Manual Recovery
            </Button>
            <Button
              variant="outline"
              onClick={handleCancel}
              disabled={actionLoading || selectedAdvance.recovered_amount > 0}
              className="rounded-xl font-black h-11 text-red-600 border-red-200 hover:bg-red-50"
            >
              <XCircle size={16} className="mr-2" /> Cancel
            </Button>
            <Button
              onClick={handleWriteOff}
              disabled={actionLoading}
              className="bg-amber-600 hover:bg-amber-700 rounded-xl font-black h-11"
            >
              <FileX size={16} className="mr-2" /> Write Off Balance
            </Button>
          </div>
        )}

        {/* Manual Recovery Modal */}
        <ManualRecoveryModal
          open={showRecoverModal}
          onClose={() => setShowRecoverModal(false)}
          advance={selectedAdvance}
          onSuccess={() => {
            setShowRecoverModal(false);
            fetchAdvances();
            openDetail(selectedAdvance);
          }}
        />
      </div>
    );
  }

  // List View
  return (
    <div className="p-8 max-w-[1400px] mx-auto animate-in fade-in duration-700">
      <div className="flex justify-between items-start mb-10">
        <div>
          <h1 className="text-4xl font-black text-[#0F172A] tracking-tighter">Salary Advances</h1>
          <p className="text-[#64748B] font-bold uppercase tracking-widest text-[10px] mt-1">Advance Disbursement & Recovery Tracker</p>
        </div>
        <Button
          onClick={() => { setShowCreateModal(true); fetchEmployees(); }}
          className="bg-blue-600 hover:bg-blue-700 h-12 px-8 rounded-xl font-black shadow-lg shadow-blue-600/20"
        >
          <Plus size={20} className="mr-2" /> Disburse Advance
        </Button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-10">
        {[
          { label: 'Total Disbursed', value: `\u20B9${totalDisbursed.toLocaleString('en-IN')}`, icon: Banknote, color: 'text-blue-600' },
          { label: 'Outstanding', value: `\u20B9${totalOutstanding.toLocaleString('en-IN')}`, icon: AlertTriangle, color: 'text-red-600' },
          { label: 'Active Advances', value: advances.filter(a => a.status === 'active').length, icon: Clock, color: 'text-amber-600' },
          { label: 'Fully Recovered', value: advances.filter(a => a.status === 'fully_recovered').length, icon: CheckCircle2, color: 'text-green-600' },
        ].map((stat, i) => (
          <Card key={i} className="p-6 border-slate-200 hover:shadow-xl hover:shadow-slate-200/50 transition-all duration-500 group">
            <div className="flex justify-between items-start mb-4">
              <div className={cn("p-3 rounded-2xl bg-slate-50 transition-colors group-hover:bg-white", stat.color)}>
                <stat.icon size={24} />
              </div>
            </div>
            <span className="text-[10px] font-black text-slate-400 uppercase tracking-widest">{stat.label}</span>
            <h4 className="text-2xl font-black text-slate-900 mt-1">{stat.value}</h4>
          </Card>
        ))}
      </div>

      {/* Filters */}
      <div className="flex gap-4 mb-6">
        <div className="relative flex-1 max-w-xs">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <Input
            placeholder="Search employees..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="pl-9 h-11 rounded-xl"
          />
        </div>
        <Select value={statusFilter || 'all'} onValueChange={v => setStatusFilter(v === 'all' ? '' : v)}>
          <SelectTrigger className="w-44 h-11 rounded-xl font-bold">
            <SelectValue placeholder="All statuses" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All</SelectItem>
            <SelectItem value="active">Active</SelectItem>
            <SelectItem value="fully_recovered">Fully Recovered</SelectItem>
            <SelectItem value="written_off">Written Off</SelectItem>
            <SelectItem value="cancelled">Cancelled</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Table */}
      {loading ? (
        <div className="flex h-48 items-center justify-center"><Loader2 className="h-8 w-8 animate-spin text-blue-600" /></div>
      ) : filtered.length === 0 ? (
        <div className="p-12 border-2 border-dashed border-slate-200 rounded-3xl text-center">
          <Banknote size={48} className="mx-auto text-slate-300 mb-4" />
          <p className="font-bold text-slate-400">No salary advances found</p>
        </div>
      ) : (
        <Card className="border-slate-200 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead className="bg-slate-50">
                <tr>
                  {['Employee', 'Department', 'Amount', 'Outstanding', 'Mode', 'Status', ''].map(h => (
                    <th key={h} className="px-5 py-4 text-[10px] font-black text-slate-400 uppercase tracking-widest">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {filtered.map(adv => {
                  const st = STATUS_CONFIG[adv.status] || STATUS_CONFIG.active;
                  return (
                    <tr key={adv.id} className="hover:bg-slate-50/50 cursor-pointer" onClick={() => openDetail(adv)}>
                      <td className="px-5 py-4">
                        <div className="font-black text-slate-900">{adv.employee_name}</div>
                        <div className="text-xs text-slate-400 font-bold">{adv.employee_code}</div>
                      </td>
                      <td className="px-5 py-4 font-bold text-slate-600">{adv.department}</td>
                      <td className="px-5 py-4 font-black text-slate-900">{`\u20B9`}{adv.amount.toLocaleString('en-IN')}</td>
                      <td className="px-5 py-4 font-black text-red-600">{`\u20B9`}{(adv.outstanding || 0).toLocaleString('en-IN')}</td>
                      <td className="px-5 py-4 font-bold text-slate-600 capitalize">{adv.recovery_mode === 'installment' ? `${adv.installment_months}m EMI` : 'One-time'}</td>
                      <td className="px-5 py-4"><Badge className={cn('text-[9px] font-black', st.color)}>{st.label}</Badge></td>
                      <td className="px-5 py-4"><ChevronRight size={16} className="text-slate-300" /></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* Create Modal */}
      <CreateAdvanceModal
        open={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        employees={employees}
        onSuccess={() => { setShowCreateModal(false); fetchAdvances(); }}
      />
    </div>
  );
};


// ─── Create Advance Modal ────────────────────────────────────────

const CreateAdvanceModal = ({
  open, onClose, employees, onSuccess
}: {
  open: boolean;
  onClose: () => void;
  employees: any[];
  onSuccess: () => void;
}) => {
  const [form, setForm] = useState({
    employee_id: '',
    amount: '',
    reason: '',
    recovery_mode: 'one_time',
    installment_months: '1',
    remarks: '',
  });
  const [saving, setSaving] = useState(false);

  const handleSubmit = async () => {
    if (!form.employee_id || !form.amount) {
      toast.error('Employee and amount are required');
      return;
    }
    setSaving(true);
    try {
      await client.post(ENDPOINTS.HR.ADVANCES, {
        employee_id: parseInt(form.employee_id),
        amount: parseFloat(form.amount),
        reason: form.reason || null,
        disbursed_date: new Date().toISOString(),
        recovery_mode: form.recovery_mode,
        installment_months: parseInt(form.installment_months) || 1,
        remarks: form.remarks || null,
      });
      toast.success('Salary advance disbursed');
      setForm({ employee_id: '', amount: '', reason: '', recovery_mode: 'one_time', installment_months: '1', remarks: '' });
      onSuccess();
    } catch (e: any) {
      toast.error(getError(e, 'Failed to create advance'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="text-xl font-black">Disburse Salary Advance</DialogTitle>
        </DialogHeader>
        <div className="space-y-4 mt-4">
          <div>
            <label className="text-xs font-black text-slate-500 uppercase tracking-widest mb-1.5 block">Employee</label>
            <Select value={form.employee_id || undefined} onValueChange={v => setForm(f => ({ ...f, employee_id: v }))}>
              <SelectTrigger className="w-full rounded-xl"><SelectValue placeholder="Select employee" /></SelectTrigger>
              <SelectContent>
                {employees.map((emp: any) => (
                  <SelectItem key={emp.id} value={emp.id.toString()}>
                    {emp.user?.full_name || emp.employee_id} — {emp.department}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <label className="text-xs font-black text-slate-500 uppercase tracking-widest mb-1.5 block">Amount ({`\u20B9`})</label>
            <Input type="number" value={form.amount} onChange={e => setForm(f => ({ ...f, amount: e.target.value }))} className="rounded-xl" placeholder="e.g. 25000" />
          </div>
          <div>
            <label className="text-xs font-black text-slate-500 uppercase tracking-widest mb-1.5 block">Reason</label>
            <Select value={form.reason} onValueChange={v => setForm(f => ({ ...f, reason: v }))}>
              <SelectTrigger className="w-full rounded-xl"><SelectValue placeholder="Select reason" /></SelectTrigger>
              <SelectContent>
                {['Medical Emergency', 'Festival Advance', 'Personal Emergency', 'Relocation', 'Other'].map(r => (
                  <SelectItem key={r} value={r}>{r}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-xs font-black text-slate-500 uppercase tracking-widest mb-1.5 block">Recovery Mode</label>
              <Select value={form.recovery_mode} onValueChange={v => setForm(f => ({ ...f, recovery_mode: v }))}>
                <SelectTrigger className="w-full rounded-xl"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="one_time">One Time</SelectItem>
                  <SelectItem value="installment">Installment (EMI)</SelectItem>
                </SelectContent>
              </Select>
            </div>
            {form.recovery_mode === 'installment' && (
              <div>
                <label className="text-xs font-black text-slate-500 uppercase tracking-widest mb-1.5 block">Months</label>
                <Input type="number" min="2" max="24" value={form.installment_months} onChange={e => setForm(f => ({ ...f, installment_months: e.target.value }))} className="rounded-xl" />
              </div>
            )}
          </div>
          <div>
            <label className="text-xs font-black text-slate-500 uppercase tracking-widest mb-1.5 block">Remarks (optional)</label>
            <Input value={form.remarks} onChange={e => setForm(f => ({ ...f, remarks: e.target.value }))} className="rounded-xl" placeholder="Any notes..." />
          </div>
        </div>
        <DialogFooter className="mt-6">
          <Button variant="outline" onClick={onClose} className="rounded-xl font-bold">Cancel</Button>
          <Button onClick={handleSubmit} disabled={saving} className="bg-blue-600 hover:bg-blue-700 rounded-xl font-black">
            {saving ? <Loader2 className="animate-spin mr-2" size={16} /> : <Banknote size={16} className="mr-2" />}
            Disburse
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};


// ─── Manual Recovery Modal ───────────────────────────────────────

const ManualRecoveryModal = ({
  open, onClose, advance, onSuccess
}: {
  open: boolean;
  onClose: () => void;
  advance: SalaryAdvance;
  onSuccess: () => void;
}) => {
  const [amount, setAmount] = useState('');
  const [remarks, setRemarks] = useState('');
  const [saving, setSaving] = useState(false);

  const handleSubmit = async () => {
    if (!amount || parseFloat(amount) <= 0) {
      toast.error('Enter a valid amount');
      return;
    }
    setSaving(true);
    try {
      await client.post(ENDPOINTS.HR.ADVANCE_RECOVER(advance.id), {
        amount: parseFloat(amount),
        remarks: remarks || 'Manual recovery by HR',
      });
      toast.success('Recovery recorded');
      setAmount('');
      setRemarks('');
      onSuccess();
    } catch (e: any) {
      toast.error(getError(e, 'Failed to record recovery'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="text-xl font-black">Manual Recovery</DialogTitle>
        </DialogHeader>
        <div className="space-y-4 mt-4">
          <div className="p-4 bg-slate-50 rounded-xl">
            <div className="flex justify-between text-sm">
              <span className="text-slate-500 font-bold">Outstanding:</span>
              <span className="font-black text-red-600">{`\u20B9`}{(advance.outstanding || 0).toLocaleString('en-IN')}</span>
            </div>
          </div>
          <div>
            <label className="text-xs font-black text-slate-500 uppercase tracking-widest mb-1.5 block">Recovery Amount ({`\u20B9`})</label>
            <Input type="number" value={amount} onChange={e => setAmount(e.target.value)} className="rounded-xl" placeholder="e.g. 5000" />
          </div>
          <div>
            <label className="text-xs font-black text-slate-500 uppercase tracking-widest mb-1.5 block">Remarks</label>
            <Input value={remarks} onChange={e => setRemarks(e.target.value)} className="rounded-xl" placeholder="Cash/cheque/bank transfer..." />
          </div>
        </div>
        <DialogFooter className="mt-6">
          <Button variant="outline" onClick={onClose} className="rounded-xl font-bold">Cancel</Button>
          <Button onClick={handleSubmit} disabled={saving} className="bg-green-600 hover:bg-green-700 rounded-xl font-black">
            {saving ? <Loader2 className="animate-spin mr-2" size={16} /> : <DollarSign size={16} className="mr-2" />}
            Record Recovery
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
