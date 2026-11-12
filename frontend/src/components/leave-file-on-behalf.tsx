import React, { useEffect, useMemo, useState } from 'react';
import { UserPlus, Send } from 'lucide-react';
import { Card, Button } from './ui-elements';
import { toast } from 'sonner';
import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';
import { Input } from './ui/input';

const errMsg = (e: any, f: string) => {
  const d = e?.response?.data?.detail;
  if (typeof d === 'string') return d;
  if (Array.isArray(d)) return d.map((x: any) => x?.msg || JSON.stringify(x)).join('; ');
  return e?.message || f;
};
const selectCls = 'mt-1.5 w-full h-11 px-3 bg-slate-50 border border-slate-200 rounded-xl text-sm font-bold text-[#0F172A] outline-none';

export const FileLeaveOnBehalfPanel: React.FC = () => {
  const [employees, setEmployees] = useState<any[]>([]);
  const [leaveTypes, setLeaveTypes] = useState<any[]>([]);
  const [form, setForm] = useState({
    employee_id: '', leave_type_id: '', start_date: '', end_date: '',
    is_half_day: false, reason: '', auto_approve: true, is_emergency: false,
  });
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    client.get(ENDPOINTS.HR.EMPLOYEES, { params: { limit: 500 } })
      .then(r => setEmployees(r.data?.items ?? (Array.isArray(r.data) ? r.data : [])))
      .catch(() => setEmployees([]));
    client.get(ENDPOINTS.LEAVE.TYPES).then(r => setLeaveTypes(r.data || [])).catch(() => setLeaveTypes([]));
  }, []);

  const empOptions = useMemo(() => employees
    .filter(e => e?.user)
    .map(e => ({ id: e.user.id, name: e.user.full_name || e.user.email })), [employees]);

  const submit = async () => {
    if (!form.employee_id || !form.leave_type_id || !form.start_date || !form.end_date || !form.reason.trim()) {
      toast.error('Employee, leave type, dates and reason are required');
      return;
    }
    setSubmitting(true);
    try {
      const res = await client.post(ENDPOINTS.LEAVE.APPLY_ON_BEHALF, {
        employee_id: Number(form.employee_id),
        leave_type_id: Number(form.leave_type_id),
        start_date: form.start_date, end_date: form.end_date,
        is_half_day: form.is_half_day, reason: form.reason,
        auto_approve: form.auto_approve, is_emergency: form.is_emergency,
      });
      toast.success(`Leave filed (${res.data.status}) for the employee`);
      setForm({ ...form, start_date: '', end_date: '', reason: '' });
    } catch (e: any) {
      toast.error(errMsg(e, 'Failed to file leave'));
    } finally { setSubmitting(false); }
  };

  return (
    <Card className="p-6 border-slate-200 bg-white max-w-2xl">
      <div className="flex items-center gap-2 mb-1">
        <UserPlus size={18} className="text-blue-600" />
        <h3 className="text-lg font-black text-[#0F172A] uppercase tracking-tight">File Leave on Behalf</h3>
      </div>
      <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-5">
        HR files a leave for an employee · You are recorded as the filer (separation of duties)
      </p>
      <div className="space-y-4">
        <div>
          <label className="text-[10px] font-black uppercase tracking-widest text-[#0F172A]">Employee</label>
          <select value={form.employee_id} onChange={e => setForm({ ...form, employee_id: e.target.value })} className={selectCls}>
            <option value="">Select employee…</option>
            {empOptions.map(o => <option key={o.id} value={o.id}>{o.name}</option>)}
          </select>
        </div>
        <div>
          <label className="text-[10px] font-black uppercase tracking-widest text-[#0F172A]">Leave Type</label>
          <select value={form.leave_type_id} onChange={e => setForm({ ...form, leave_type_id: e.target.value })} className={selectCls}>
            <option value="">Select type…</option>
            {leaveTypes.map((l: any) => <option key={l.id} value={l.id}>{l.name}</option>)}
          </select>
        </div>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="text-[10px] font-black uppercase tracking-widest text-[#0F172A]">Start Date</label>
            <Input type="date" value={form.start_date} onChange={(e: any) => setForm({ ...form, start_date: e.target.value })} className="mt-1.5" />
          </div>
          <div>
            <label className="text-[10px] font-black uppercase tracking-widest text-[#0F172A]">End Date</label>
            <Input type="date" value={form.end_date} onChange={(e: any) => setForm({ ...form, end_date: e.target.value })} className="mt-1.5" />
          </div>
        </div>
        <div>
          <label className="text-[10px] font-black uppercase tracking-widest text-[#0F172A]">Reason</label>
          <Input value={form.reason} onChange={(e: any) => setForm({ ...form, reason: e.target.value })} placeholder="e.g. Family emergency" className="mt-1.5" />
        </div>
        <div className="flex items-center gap-4">
          <label className="inline-flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-[#0F172A] cursor-pointer">
            <input type="checkbox" checked={form.is_half_day} onChange={e => setForm({ ...form, is_half_day: e.target.checked })} className="w-3.5 h-3.5 accent-blue-600" /> Half day
          </label>
          <label className="inline-flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-[#0F172A] cursor-pointer">
            <input type="checkbox" checked={form.auto_approve} onChange={e => setForm({ ...form, auto_approve: e.target.checked })} className="w-3.5 h-3.5 accent-blue-600" /> Auto-approve (debit balance now)
          </label>
        </div>
        <div>
          <label className="inline-flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-[#0F172A] cursor-pointer">
            <input type="checkbox" aria-label="Emergency leave" checked={form.is_emergency} onChange={e => setForm({ ...form, is_emergency: e.target.checked })} className="w-3.5 h-3.5 accent-rose-600" /> Emergency (same-day / back-dated)
          </label>
          {form.is_emergency && (
            <p className="text-[10px] font-bold text-slate-500 mt-1.5">
              May start up to the configured back-date window in the past. Proof can follow later; if it is not
              submitted by the due date the leave converts to loss of pay. Schedulers are alerted to cover the shifts.
            </p>
          )}
        </div>
        <Button onClick={submit} isLoading={submitting} className="bg-blue-600 hover:bg-blue-700 text-white font-black uppercase text-[10px] tracking-widest h-11">
          <Send size={14} className="mr-1.5" /> File Leave
        </Button>
      </div>
    </Card>
  );
};
