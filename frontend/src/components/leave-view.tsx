import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import {
  Calendar as CalendarIcon,
  AlertCircle,
  Search,
  Coffee,
  Plus,
  Umbrella,
  Briefcase,
  Paperclip,
  XCircle,
  Loader2,
  FileText,
} from 'lucide-react';
import { Card, Button, Badge, cn } from './ui-elements';
import { toast } from 'sonner';
import { Dialog, DialogContent, DialogTitle, DialogFooter } from './ui/dialog';
import { Input } from './ui/input';
import { Textarea } from './ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';
import { LeaveBalance, LeaveRequest } from '../types/erp';

export const LeaveView = () => {
  const [activeSubTab, setActiveSubTab] = useState<'balance' | 'history' | 'holidays'>('balance');
  const [searchQuery, setSearchQuery] = useState('');
  const [isRequestingLeave, setIsRequestingLeave] = useState(false);
  
  const [balances, setBalances] = useState<LeaveBalance[]>([]);
  const [leaveTypes, setLeaveTypes] = useState<any[]>([]);
  const [history, setHistory] = useState<LeaveRequest[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [holidays, setHolidays] = useState<any[]>([]);

  // Form State
  const [leaveTypeId, setLeaveTypeId] = useState<string>('');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [reason, setReason] = useState('');
  const [emergencyContact, setEmergencyContact] = useState('');
  const [isHalfDay, setIsHalfDay] = useState(false);
  const [halfDaySession, setHalfDaySession] = useState<'morning' | 'afternoon' | ''>('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [attachmentFile, setAttachmentFile] = useState<File | null>(null);
  const [attachmentName, setAttachmentName] = useState<string>('');
  const [isUploading, setIsUploading] = useState(false);

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    setIsLoading(true);
    try {
      const [balRes, typeRes, histRes, holidayRes] = await Promise.all([
        client.get<LeaveBalance[]>(ENDPOINTS.LEAVE.BALANCES),
        client.get<any[]>(ENDPOINTS.LEAVE.TYPES),
        client.get<LeaveRequest[]>(ENDPOINTS.LEAVE.MY),
        client.get<any[]>(ENDPOINTS.HR.HOLIDAYS)
      ]);
      setBalances(balRes.data);
      setLeaveTypes(typeRes.data);
      setHistory(histRes.data);
      setHolidays(holidayRes.data);
    } catch (error) {
      toast.error("Failed to load leave data");
    } finally {
      setIsLoading(false);
    }
  };

  const selectedLeaveType = leaveTypes.find((t: any) => t.id.toString() === leaveTypeId);
  const computedDays = (() => {
    if (!startDate || !endDate) return 0;
    if (isHalfDay) return 0.5;
    const start = new Date(startDate);
    const end = new Date(endDate);
    const diffMs = end.getTime() - start.getTime();
    if (isNaN(diffMs) || diffMs < 0) return 0;
    return Math.floor(diffMs / (1000 * 60 * 60 * 24)) + 1;
  })();
  const medicalCertThreshold: number | null = selectedLeaveType?.requires_medical_cert_after ?? null;
  const showAttachmentField = medicalCertThreshold != null;
  const attachmentRequired = medicalCertThreshold != null && computedDays >= medicalCertThreshold;

  const resetForm = () => {
    setLeaveTypeId('');
    setStartDate('');
    setEndDate('');
    setReason('');
    setEmergencyContact('');
    setIsHalfDay(false);
    setHalfDaySession('');
    setAttachmentFile(null);
    setAttachmentName('');
  };

  const handleFilePick = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (!f) return;
    const allowed = ['application/pdf', 'image/jpeg', 'image/png', 'image/webp', 'image/heic'];
    if (!allowed.includes(f.type)) {
      toast.error('Only PDF, JPEG, PNG, WebP, or HEIC files are allowed');
      e.target.value = '';
      return;
    }
    if (f.size > 10 * 1024 * 1024) {
      toast.error('File must be under 10 MB');
      e.target.value = '';
      return;
    }
    setAttachmentFile(f);
    setAttachmentName(f.name);
    e.target.value = '';
  };

  const clearAttachment = () => {
    setAttachmentFile(null);
    setAttachmentName('');
  };

  const openAttachment = async (filename: string) => {
    try {
      const res = await client.get(ENDPOINTS.LEAVE.ATTACHMENT_DOWNLOAD(filename), { responseType: 'blob' });
      const blobUrl = window.URL.createObjectURL(res.data as Blob);
      window.open(blobUrl, '_blank', 'noopener,noreferrer');
      // Revoke later; browsers need time to open the URL first.
      setTimeout(() => window.URL.revokeObjectURL(blobUrl), 60000);
    } catch {
      toast.error('Failed to open attachment');
    }
  };

  const handleApplyLeave = async () => {
    if (!leaveTypeId || !startDate || !endDate || !reason) {
      toast.error("Please fill all required fields");
      return;
    }
    if (attachmentRequired && !attachmentFile) {
      toast.error(`A medical certificate is required for ${medicalCertThreshold}+ days`);
      return;
    }

    setIsSubmitting(true);
    try {
      let attachmentUrl: string | null = null;
      if (attachmentFile) {
        setIsUploading(true);
        const form = new FormData();
        form.append('file', attachmentFile);
        try {
          const uploadRes = await client.post(ENDPOINTS.LEAVE.ATTACHMENT_UPLOAD, form);
          attachmentUrl = (uploadRes.data as any)?.attachment_url || null;
        } finally {
          setIsUploading(false);
        }
        if (!attachmentUrl) {
          toast.error('Failed to upload attachment');
          setIsSubmitting(false);
          return;
        }
      }

      await client.post(ENDPOINTS.LEAVE.APPLY, {
        leave_type_id: parseInt(leaveTypeId),
        start_date: startDate,
        end_date: endDate,
        reason,
        emergency_contact: emergencyContact,
        is_half_day: isHalfDay,
        half_day_session: isHalfDay ? halfDaySession : null,
        attachment_url: attachmentUrl,
      });
      toast.success("Leave request submitted successfully");
      setIsRequestingLeave(false);
      fetchData(); // Refresh data
      resetForm();
    } catch (error: any) {
      const msg = error.response?.data?.detail
        || error.response?.data?.error?.message
        || "Failed to submit leave request";
      toast.error(typeof msg === 'string' ? msg : 'Failed to submit leave request');
    } finally {
      setIsSubmitting(false);
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'approved': return <Badge variant="success" className="text-[10px] font-bold uppercase px-2.5 py-0.5 rounded-full bg-emerald-100 text-emerald-700 border-none">Approved</Badge>;
      case 'rejected': return <Badge variant="error" className="text-[10px] font-bold uppercase px-2.5 py-0.5 rounded-full bg-rose-100 text-rose-700 border-none">Rejected</Badge>;
      case 'cancelled': return <Badge variant="neutral" className="text-[10px] font-bold uppercase px-2.5 py-0.5 rounded-full bg-slate-100 text-slate-700 border-none">Cancelled</Badge>;
      case 'submitted': return <Badge variant="warning" className="text-[10px] font-bold uppercase px-2.5 py-0.5 rounded-full bg-amber-100 text-amber-700 border-none">Pending</Badge>;
      default: return <Badge variant="neutral" className="text-[10px] font-bold uppercase px-2.5 py-0.5 rounded-full bg-slate-100 text-slate-700 border-none">{status}</Badge>;
    }
  };

  const getBalanceIcon = (typeName: string) => {
    const n = typeName.toLowerCase();
    if (n.includes('casual')) return <Coffee size={20} />;
    if (n.includes('privilege') || n.includes('annual') || n.includes('earned')) return <Umbrella size={20} />;
    if (n.includes('sick')) return <Plus size={20} />;
    if (n.includes('comp')) return <Briefcase size={20} />;
    if (n.includes('maternity')) return <Umbrella size={20} />;
    return <Briefcase size={20} />;
  };

  const getBalanceColor = (typeName: string) => {
    const n = typeName.toLowerCase();
    if (n.includes('casual')) return 'text-amber-600 bg-amber-50 border-amber-100';
    if (n.includes('privilege') || n.includes('annual') || n.includes('earned')) return 'text-indigo-600 bg-indigo-50 border-indigo-100';
    if (n.includes('sick')) return 'text-rose-600 bg-rose-50 border-rose-100';
    if (n.includes('comp')) return 'text-teal-600 bg-teal-50 border-teal-100';
    if (n.includes('maternity')) return 'text-pink-600 bg-pink-50 border-pink-100';
    if (n.includes('without pay') || n.includes('lwp')) return 'text-gray-600 bg-gray-50 border-gray-100';
    return 'text-slate-600 bg-slate-50 border-slate-100';
  };

  const filteredHistory = history.filter(h => 
    h.leave_type?.name.toLowerCase().includes(searchQuery.toLowerCase()) || 
    h.status.toLowerCase().includes(searchQuery.toLowerCase()) ||
    h.reason.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="flex-1 overflow-auto bg-slate-50/50">
      <div className="p-8 max-w-[1600px] mx-auto space-y-8">
        {/* Header Section */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Time Off Management</h1>
            <p className="text-slate-500 text-sm mt-1">Submit requests, view balances, and track your attendance history.</p>
          </div>
          <Button 
            onClick={() => setIsRequestingLeave(true)}
            className="bg-indigo-600 hover:bg-indigo-700 text-white shadow-sm shadow-indigo-200 px-6 h-11 rounded-xl transition-all duration-200 flex items-center gap-2 group"
          >
            <Plus size={18} className="group-hover:rotate-90 transition-transform duration-300" />
            Apply for Leave
          </Button>
        </div>

        {/* Balance Cards Grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
          {isLoading ? (
            Array(4).fill(0).map((_, i) => (
              <Card key={i} className="h-32 animate-pulse bg-white border-slate-200" />
            ))
          ) : (
            balances.map((bal) => (
              <Card key={bal.id} className="relative overflow-hidden group border-slate-200 hover:border-indigo-200 transition-all duration-300 bg-white">
                <div className="p-5 flex items-start gap-4">
                  <div className={cn("p-2.5 rounded-xl border transition-colors duration-300", getBalanceColor(bal.leave_type.name))}>
                    {getBalanceIcon(bal.leave_type.name)}
                  </div>
                  <div>
                    <h3 className="text-sm font-semibold text-slate-500 truncate max-w-[150px]">{bal.leave_type.name}</h3>
                    <div className="flex items-baseline gap-1.5 mt-1">
                      <span className="text-2xl font-bold text-slate-900">{bal.remaining}</span>
                      <span className="text-xs text-slate-400 font-medium">days left</span>
                    </div>
                  </div>
                </div>
                <div className="h-1 w-full bg-slate-100 mt-auto">
                   <motion.div 
                    initial={{ width: 0 }}
                    animate={{ width: `${Math.min((bal.remaining / (bal.total || 20)) * 100, 100)}%` }}
                    className={cn("h-full transition-all duration-500", 
                      bal.remaining < 3 ? "bg-rose-500" : "bg-indigo-500"
                    )}
                   />
                </div>
              </Card>
            ))
          )}
        </div>

        {/* Main Content Area */}
        <Card className="border-slate-200 bg-white shadow-sm overflow-hidden rounded-2xl">
          <div className="border-b border-slate-100 flex items-center justify-between px-6 bg-slate-50/50">
            <div className="flex">
              {[
                { id: 'balance', label: 'My Requests', icon: CalendarIcon },
                { id: 'holidays', label: 'Holiday Calendar', icon: Umbrella },
              ].map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setActiveSubTab(tab.id as any)}
                  className={cn(
                    "px-6 py-4 text-sm font-semibold transition-all relative flex items-center gap-2",
                    activeSubTab === tab.id 
                      ? "text-indigo-600" 
                      : "text-slate-500 hover:text-slate-700"
                  )}
                >
                  <tab.icon size={16} />
                  {tab.label}
                  {activeSubTab === tab.id && (
                    <motion.div 
                      layoutId="activeTab" 
                      className="absolute bottom-0 left-0 right-0 h-0.5 bg-indigo-600 rounded-t-full"
                    />
                  )}
                </button>
              ))}
            </div>
            
            {activeSubTab === 'balance' && (
              <div className="py-2.5">
                <div className="relative group">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 group-focus-within:text-indigo-500 transition-colors" size={16} />
                  <input 
                    type="text"
                    placeholder="Search history..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="pl-10 pr-4 py-2 bg-white border border-slate-200 rounded-xl text-sm w-64 focus:outline-none focus:ring-2 focus:ring-indigo-500/10 focus:border-indigo-500 transition-all placeholder:text-slate-400"
                  />
                </div>
              </div>
            )}
          </div>

          <div className="p-0">
            {activeSubTab === 'balance' ? (
              <div className="overflow-x-auto">
                <table className="w-full text-left">
                  <thead>
                    <tr className="bg-slate-50/50 text-[11px] font-bold text-slate-400 uppercase tracking-widest border-b border-slate-100">
                      <th className="px-6 py-4">Type & Period</th>
                      <th className="px-6 py-4">Reason</th>
                      <th className="px-6 py-4 text-center">Duration</th>
                      <th className="px-6 py-4">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-50">
                    {isLoading ? (
                      Array(5).fill(0).map((_, i) => (
                        <tr key={i} className="animate-pulse">
                          <td colSpan={4} className="px-6 py-8"><div className="h-4 bg-slate-100 rounded w-full"></div></td>
                        </tr>
                      ))
                    ) : filteredHistory.length === 0 ? (
                      <tr>
                        <td colSpan={4} className="px-6 py-20 text-center">
                          <div className="flex flex-col items-center gap-3">
                            <div className="p-4 bg-slate-50 rounded-full text-slate-300">
                              <CalendarIcon size={32} />
                            </div>
                            <p className="text-slate-400 font-medium">No leave records found</p>
                          </div>
                        </td>
                      </tr>
                    ) : (
                      filteredHistory.map((request) => (
                        <tr key={request.id} className="hover:bg-slate-50/80 transition-colors group">
                          <td className="px-6 py-5">
                            <div className="flex flex-col">
                              <span className="font-bold text-slate-900 text-sm">{request.leave_type?.name}</span>
                              <span className="text-xs text-slate-500 mt-1 flex items-center gap-1.5 font-medium">
                                <CalendarIcon size={12} className="text-slate-400" />
                                {new Date(request.start_date).toLocaleDateString()} - {new Date(request.end_date).toLocaleDateString()}
                              </span>
                            </div>
                          </td>
                          <td className="px-6 py-5">
                            <p className="text-sm text-slate-600 max-w-[300px] truncate leading-relaxed" title={request.reason}>
                              {request.reason}
                            </p>
                            {request.emergency_contact && (
                              <div className="flex items-center gap-1.5 mt-1.5 text-[10px] text-slate-400 uppercase font-black tracking-tight">
                                <AlertCircle size={10} />
                                Emergency: {request.emergency_contact}
                              </div>
                            )}
                            {(request as any).attachment_url && (
                              <button
                                type="button"
                                onClick={() => openAttachment((request as any).attachment_url)}
                                className="inline-flex items-center gap-1.5 mt-1.5 text-[10px] font-black uppercase tracking-tight text-indigo-600 hover:text-indigo-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500/30 rounded"
                                aria-label="View attachment"
                              >
                                <Paperclip size={10} />
                                View attachment
                              </button>
                            )}
                          </td>
                          <td className="px-6 py-5 text-center">
                            {(request as any).is_half_day ? (
                              <Badge variant="neutral" className="bg-indigo-50 text-indigo-700 font-bold px-2 py-0.5 border-none">
                                {(request as any).half_day_session === 'morning' ? 'HD1' : 'HD2'}
                              </Badge>
                            ) : (
                              <Badge variant="neutral" className="bg-slate-100 text-slate-700 font-bold px-2 py-0.5 border-none">
                                {request.total_days} {request.total_days === 1 ? 'Day' : 'Days'}
                              </Badge>
                            )}
                          </td>
                          <td className="px-6 py-5">
                            {getStatusBadge(request.status)}
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="p-8 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                 {holidays.length === 0 ? (
                    <div className="col-span-full py-20 text-center text-slate-400 font-medium">
                        No upcoming company holidays scheduled.
                    </div>
                 ) : (
                    holidays.map((holiday, i) => (
                        <Card key={i} className={`p-5 border-slate-100 hover:border-indigo-100 transition-all bg-white relative group overflow-hidden ${holiday.is_optional ? 'border-amber-100 hover:border-amber-200' : ''}`}>
                            <div className="absolute top-0 right-0 p-3 opacity-10 group-hover:opacity-20 transition-opacity">
                                <Umbrella size={48} />
                            </div>
                            <div className="relative z-10">
                                <span className={`text-[10px] font-black uppercase tracking-widest mb-2 block ${holiday.is_optional ? 'text-amber-500' : 'text-indigo-500'}`}>
                                    {holiday.is_optional ? 'Optional Holiday' : 'Company Holiday'}
                                </span>
                                <h3 className="font-bold text-slate-900 text-lg mb-1">{holiday.name}</h3>
                                <div className="flex items-center gap-4 mt-3">
                                    <div className="flex items-center gap-2 text-sm text-slate-500 font-medium">
                                        <CalendarIcon size={14} className="text-slate-400" />
                                        {new Date(holiday.date).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })}
                                    </div>
                                    <div className="h-1 w-1 rounded-full bg-slate-300" />
                                    <div className="text-sm text-slate-500 font-medium">{new Date(holiday.date).toLocaleDateString(undefined, { weekday: 'long' })}</div>
                                </div>
                                {holiday.is_optional && (
                                    <p className="text-[10px] text-amber-500 font-bold mt-2 uppercase tracking-wide">Apply any 2 optional holidays</p>
                                )}
                            </div>
                        </Card>
                    ))
                 )}
              </div>
            )}
          </div>
        </Card>
      </div>

      {/* Modern Dialog Implementation */}
      <Dialog open={isRequestingLeave} onOpenChange={(open: boolean) => {
        setIsRequestingLeave(open);
        if (!open) { setAttachmentFile(null); setAttachmentName(''); }
      }}>
        <DialogContent className="max-w-xl p-0 overflow-hidden border-none bg-white rounded-3xl shadow-2xl">
          <div className="bg-indigo-600 p-8 text-white relative">
             <div className="relative z-10">
                <DialogTitle className="text-2xl font-bold tracking-tight">Submit Leave Request</DialogTitle>
                <p className="text-indigo-100 mt-2 text-sm max-w-sm">Please provide the details below to request a workspace separation period.</p>
             </div>
             <div className="absolute -right-8 -bottom-8 opacity-20 pointer-events-none">
                <Umbrella size={180} />
             </div>
          </div>
          
          <div className="p-8 space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div className="space-y-2">
                <label className="text-[11px] font-bold text-slate-400 uppercase tracking-widest">Absence Category</label>
                <Select
                  value={leaveTypeId}
                  onValueChange={(val: string) => {
                    setLeaveTypeId(val);
                    const next = leaveTypes.find((t: any) => t.id.toString() === val);
                    // Reset half-day state if the new type does not allow it
                    if (!next?.allow_half_day) {
                      setIsHalfDay(false);
                      setHalfDaySession('');
                    }
                    // Drop any staged attachment when switching to a leave type
                    // that doesn't track medical certs (field disappears).
                    if (next?.requires_medical_cert_after == null) {
                      setAttachmentFile(null);
                      setAttachmentName('');
                    }
                  }}
                >
                  <SelectTrigger className="w-full bg-slate-50 border-slate-200 h-11 rounded-xl text-slate-700 font-medium focus:ring-indigo-500/20 shadow-none">
                    <SelectValue placeholder="Select Type" />
                  </SelectTrigger>
                  <SelectContent className="rounded-xl border-slate-200">
                    {leaveTypes.map(type => (
                      <SelectItem key={type.id} value={type.id.toString()} className="focus:bg-indigo-50 rounded-lg">
                        {type.name} {type.code ? `(${type.code})` : ''} {type.unpaid_allowed ? '- Unpaid' : ''}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {leaveTypeId && (() => {
                  const sel = leaveTypes.find((t: any) => t.id.toString() === leaveTypeId);
                  if (!sel) return null;
                  const bal = balances.find((b: any) => b.leave_type?.id === sel.id);
                  const hints: string[] = [];
                  if (sel.max_consecutive_days) hints.push(`Max ${sel.max_consecutive_days} consecutive days`);
                  if (sel.requires_medical_cert_after) hints.push(`Medical cert required for ${sel.requires_medical_cert_after}+ days`);
                  if (sel.annual_quota) hints.push(`${sel.annual_quota} days/year`);
                  if (!sel.is_cumulative) hints.push('Non-cumulative');
                  if (sel.use_within_days) hints.push(`Use within ${sel.use_within_days} days`);
                  const isLow = bal ? bal.remaining <= 0 : false;
                  const pct = bal && bal.total > 0
                    ? Math.max(0, Math.min(100, (bal.remaining / bal.total) * 100))
                    : 0;
                  return (
                    <>
                      {bal ? (
                        <div className="mt-3 rounded-2xl bg-white border border-indigo-100 p-4 shadow-sm tabular-nums">
                          <div className="flex items-end justify-between gap-4">
                            <div>
                              <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Your balance</p>
                              <div className="flex items-baseline gap-1.5 mt-1">
                                <span className={cn(
                                  'text-3xl font-black leading-none',
                                  isLow ? 'text-rose-600' : 'text-slate-900'
                                )}>{bal.remaining}</span>
                                <span className="text-xs font-bold text-slate-500">days left</span>
                              </div>
                            </div>
                            <div className="text-right">
                              <p className="text-[10px] font-bold text-slate-500">
                                <span className="text-slate-900 font-black">{bal.used}</span> used
                              </p>
                              <p className="text-[10px] font-bold text-slate-500 mt-0.5">
                                <span className="text-slate-900 font-black">{bal.total}</span> granted
                              </p>
                            </div>
                          </div>
                          <div className="h-1.5 rounded-full bg-slate-100 mt-3 overflow-hidden">
                            <div
                              className={cn(
                                'h-full rounded-full transition-all duration-500',
                                isLow ? 'bg-rose-500' : 'bg-indigo-500'
                              )}
                              style={{ width: `${pct}%` }}
                              aria-hidden="true"
                            />
                          </div>
                          {isLow && (
                            <p className="mt-2 text-[11px] font-bold text-rose-600" role="alert">
                              No balance left — your request may be rejected.
                            </p>
                          )}
                        </div>
                      ) : (
                        <div className="mt-3 rounded-2xl bg-amber-50 border border-amber-100 p-4 flex items-start gap-3">
                          <AlertCircle size={16} className="text-amber-600 mt-0.5 shrink-0" aria-hidden="true" />
                          <div>
                            <p className="text-xs font-black text-amber-800">No balance on record</p>
                            <p className="text-[11px] font-bold text-amber-700 mt-0.5">
                              Ask HR to assign a balance for this leave type before applying.
                            </p>
                          </div>
                        </div>
                      )}
                      {hints.length > 0 && (
                        <p className="text-xs text-indigo-500 mt-2 font-medium">{hints.join(' · ')}</p>
                      )}
                    </>
                  );
                })()}
              </div>

              <div className="space-y-2">
                 <label className="text-[11px] font-bold text-slate-400 uppercase tracking-widest">Emergency Contact</label>
                 <Input 
                  placeholder="+91-0000000000"
                  value={emergencyContact}
                  onChange={(e) => setEmergencyContact(e.target.value)}
                  className="bg-slate-50 border-slate-200 h-11 rounded-xl text-slate-700 font-medium focus:ring-indigo-500/20 shadow-none border"
                 />
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div className="space-y-2">
                <label className="text-[11px] font-bold text-slate-400 uppercase tracking-widest">Start Date</label>
                <div className="relative">
                  <CalendarIcon className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" size={16} />
                  <Input 
                    type="date" 
                    value={startDate}
                    onChange={(e) => setStartDate(e.target.value)}
                    className="pl-11 bg-slate-50 border-slate-200 h-11 rounded-xl text-slate-700 font-medium focus:ring-indigo-500/20 shadow-none border"
                  />
                </div>
              </div>
              <div className="space-y-2">
                <label className="text-[11px] font-bold text-slate-400 uppercase tracking-widest">End Date</label>
                <div className="relative">
                   <CalendarIcon className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" size={16} />
                   <Input
                    type="date"
                    value={endDate}
                    disabled={isHalfDay}
                    onChange={(e) => setEndDate(e.target.value)}
                    className="pl-11 bg-slate-50 border-slate-200 h-11 rounded-xl text-slate-700 font-medium focus:ring-indigo-500/20 shadow-none border disabled:opacity-60"
                   />
                </div>
              </div>
            </div>

            {/* Day Type — HD1/HD2 only available for leave types that allow half-day (CL, SL) */}
            {(() => {
              const sel = leaveTypes.find((t: any) => t.id.toString() === leaveTypeId);
              if (!sel?.allow_half_day) return null;
              const pick = (choice: 'full' | 'HD1' | 'HD2') => {
                if (choice === 'full') {
                  setIsHalfDay(false);
                  setHalfDaySession('');
                  return;
                }
                setIsHalfDay(true);
                setHalfDaySession(choice === 'HD1' ? 'morning' : 'afternoon');
                // Half-day must be single-day; force end = start
                if (startDate) setEndDate(startDate);
              };
              const current = !isHalfDay ? 'full' : (halfDaySession === 'morning' ? 'HD1' : 'HD2');
              const options: { id: 'full' | 'HD1' | 'HD2'; label: string; hint: string }[] = [
                { id: 'full', label: 'Full Day', hint: 'Entire working day' },
                { id: 'HD1', label: 'HD1', hint: 'First half' },
                { id: 'HD2', label: 'HD2', hint: 'Second half' },
              ];
              return (
                <div className="space-y-2">
                  <label className="text-[11px] font-bold text-slate-400 uppercase tracking-widest">Day Type</label>
                  <div role="radiogroup" aria-label="Day type" className="grid grid-cols-3 gap-2">
                    {options.map((opt) => {
                      const active = current === opt.id;
                      return (
                        <button
                          key={opt.id}
                          type="button"
                          role="radio"
                          aria-checked={active}
                          onClick={() => pick(opt.id)}
                          className={cn(
                            'h-14 rounded-xl border text-left px-4 transition-all focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:outline-none',
                            active
                              ? 'bg-indigo-600 border-indigo-600 text-white shadow-sm'
                              : 'bg-slate-50 border-slate-200 text-slate-700 hover:border-indigo-200'
                          )}
                        >
                          <p className="text-sm font-black tracking-tight">{opt.label}</p>
                          <p className={cn('text-[10px] font-bold uppercase tracking-widest', active ? 'text-indigo-100' : 'text-slate-400')}>
                            {opt.hint}
                          </p>
                        </button>
                      );
                    })}
                  </div>
                  {isHalfDay && (
                    <p className="text-[11px] font-bold text-slate-500">
                      Half-day leave counts as 0.5 and must be on a single date — end date is locked.
                    </p>
                  )}
                </div>
              );
            })()}

            <div className="space-y-2">
              <label className="text-[11px] font-bold text-slate-400 uppercase tracking-widest">Separation Justification</label>
              <Textarea
                placeholder="Briefly explain the reason for your leave..."
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                className="bg-slate-50 border-slate-200 rounded-2xl resize-none h-28 focus:ring-indigo-500/20 shadow-none border p-4 text-slate-700 font-medium"
              />
            </div>

            {/* Supporting document upload — shown for leave types that track medical certs */}
            {showAttachmentField && (
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <label htmlFor="leave-attachment" className="text-[11px] font-bold text-slate-400 uppercase tracking-widest">
                    Supporting Document{' '}
                    <span className={cn('normal-case tracking-normal', attachmentRequired ? 'text-rose-500 font-bold' : 'text-slate-400 font-medium')}>
                      {attachmentRequired ? '(required)' : '(optional)'}
                    </span>
                  </label>
                  {medicalCertThreshold != null && (
                    <span className="text-[10px] font-bold text-slate-400">
                      Required for {medicalCertThreshold}+ days
                    </span>
                  )}
                </div>

                {!attachmentFile ? (
                  <label
                    htmlFor="leave-attachment"
                    className={cn(
                      'flex items-center gap-3 px-4 py-3 rounded-2xl border-2 border-dashed cursor-pointer transition-colors focus-within:ring-2 focus-within:ring-indigo-500/30',
                      attachmentRequired
                        ? 'bg-rose-50/50 border-rose-200 hover:border-rose-300 hover:bg-rose-50'
                        : 'bg-slate-50 border-slate-200 hover:border-indigo-300 hover:bg-indigo-50/40'
                    )}
                  >
                    <Paperclip size={16} className={attachmentRequired ? 'text-rose-500' : 'text-slate-400'} aria-hidden="true" />
                    <span className="text-xs font-bold text-slate-700">
                      Click to upload medical certificate
                    </span>
                    <span className="ml-auto text-[10px] font-bold text-slate-400">
                      PDF, JPG, PNG · Max 10 MB
                    </span>
                    <input
                      id="leave-attachment"
                      type="file"
                      className="sr-only"
                      accept="application/pdf,image/jpeg,image/png,image/webp,image/heic"
                      onChange={handleFilePick}
                      aria-label="Upload supporting document"
                    />
                  </label>
                ) : (
                  <div className="flex items-center gap-3 px-4 py-3 rounded-2xl border border-emerald-200 bg-emerald-50/60">
                    <FileText size={16} className="text-emerald-600 shrink-0" aria-hidden="true" />
                    <div className="min-w-0 flex-1">
                      <p className="text-xs font-bold text-slate-800 truncate">{attachmentName}</p>
                      <p className="text-[10px] font-medium text-slate-500">
                        {(attachmentFile.size / 1024).toFixed(0)} KB · Ready to attach
                      </p>
                    </div>
                    {isUploading && (
                      <Loader2 size={16} className="text-indigo-500 animate-spin shrink-0" aria-hidden="true" />
                    )}
                    <button
                      type="button"
                      onClick={clearAttachment}
                      disabled={isUploading || isSubmitting}
                      aria-label="Remove attachment"
                      className="h-8 w-8 rounded-lg flex items-center justify-center text-slate-400 hover:text-slate-700 hover:bg-white transition-colors disabled:opacity-40"
                    >
                      <XCircle size={16} />
                    </button>
                  </div>
                )}
              </div>
            )}

            {/* Attendance Rule Notice */}
            <div className="bg-amber-50 border border-amber-100 p-4 rounded-xl flex items-start gap-3">
               <AlertCircle size={18} className="text-amber-500 mt-0.5 shrink-0" />
               <div>
                  <h4 className="text-xs font-bold text-amber-800 uppercase tracking-tight">Policy Assurance</h4>
                  <p className="text-[11px] text-amber-700 leading-relaxed mt-1">
                    Your leave request will notify your direct manager and department supervisor. Please ensure your current worklog is submitted before separation.
                  </p>
               </div>
            </div>
          </div>

          <DialogFooter className="p-8 pt-0 gap-3">
            <Button 
              variant="outline" 
              onClick={() => setIsRequestingLeave(false)}
              className="px-6 h-11 rounded-xl font-semibold border-slate-200 text-slate-600 hover:bg-slate-50"
            >
              Cancel
            </Button>
            <Button 
              onClick={handleApplyLeave}
              disabled={isSubmitting}
              className="bg-indigo-600 hover:bg-indigo-700 text-white shadow-sm shadow-indigo-100 flex-1 h-11 rounded-xl font-bold transition-all px-6 py-2"
            >
              {isSubmitting ? 'Processing Application...' : 'Confirm Submission'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};
