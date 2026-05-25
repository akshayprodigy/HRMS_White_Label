import React, { useState, useEffect, useRef } from 'react';
import {
  Calendar,
  CheckCircle2,
  XCircle,
  Clock,
  User,
  FileText,
  MoreVertical,
  Search,
  Filter,
  ChevronRight,
  ArrowRight,
  MessageSquare,
  Paperclip,
  Upload,
  Download,
  Loader2,
  Gift,
  Coffee,
  Plus,
  CheckCheck
} from 'lucide-react';
import { Card, Button, Badge, cn } from './ui-elements';
import { toast } from 'sonner@2.0.3';
import { Tabs, TabsContent, TabsList, TabsTrigger } from './ui/tabs';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from './ui/dialog';
import { Textarea } from './ui/textarea';
import { Input } from './ui/input';
import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';
import { ApprovalItem } from '../types/erp';

// Safely extract a string message from axios error responses
// Pydantic 422 detail is an array of objects — this converts them to a readable string
const errMsg = (err: any, fallback = 'Something went wrong'): string => {
  const detail = err?.response?.data?.detail;
  if (!detail) return err?.message || fallback;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) return detail.map((d: any) => d?.msg || JSON.stringify(d)).join('; ');
  return fallback;
};

// Open a leave attachment via the authenticated client (server checks permission).
// Used in both the approval cards and the history rows.
const openLeaveAttachment = async (filename: string) => {
  if (!filename) return;
  try {
    const res = await client.get(ENDPOINTS.LEAVE.ATTACHMENT_DOWNLOAD(filename), { responseType: 'blob' });
    const blob = res.data as Blob;
    const blobUrl = window.URL.createObjectURL(blob);
    window.open(blobUrl, '_blank', 'noopener,noreferrer');
    setTimeout(() => window.URL.revokeObjectURL(blobUrl), 60000);
  } catch (e: any) {
    toast.error(errMsg(e, 'Failed to open attachment'));
  }
};

const downloadLeaveAttachment = async (filename: string, fallbackName?: string) => {
  if (!filename) return;
  try {
    const res = await client.get(ENDPOINTS.LEAVE.ATTACHMENT_DOWNLOAD(filename), { responseType: 'blob' });
    const blob = res.data as Blob;
    const blobUrl = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = blobUrl;
    a.download = fallbackName || filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => window.URL.revokeObjectURL(blobUrl), 60000);
  } catch (e: any) {
    toast.error(errMsg(e, 'Failed to download attachment'));
  }
};

export const LeaveHR = () => {
  const [inbox, setInbox] = useState<ApprovalItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [selectedLeave, setSelectedLeave] = useState<ApprovalItem | null>(null);
  const [isReviewing, setIsReviewing] = useState(false);
  const [comment, setComment] = useState('');
  const [isProcessing, setIsProcessing] = useState(false);
  const [uploadingBalances, setUploadingBalances] = useState(false);
  const [uploadResult, setUploadResult] = useState<any>(null);
  const balanceFileRef = useRef<HTMLInputElement>(null);
  const [activeTab, setActiveTab] = useState('pending');
  // Track which HR-only tabs have been visited so they lazy-mount
  const [mountedTabs, setMountedTabs] = useState<Set<string>>(new Set(['pending']));

  useEffect(() => {
    fetchInbox();
  }, []);

  const fetchInbox = async () => {
    setIsLoading(true);
    try {
      const response = await client.get<ApprovalItem[]>(ENDPOINTS.LEAVE.APPROVALS);
      setInbox(response.data);
    } catch (error) {
      toast.error("Failed to load approvals inbox");
    } finally {
      setIsLoading(false);
    }
  };

  const handleAction = async (approvalId: number, status: 'approved' | 'rejected') => {
    setIsProcessing(true);
    try {
      await client.post(ENDPOINTS.LEAVE.APPROVAL_ACTION(approvalId), {
        status,
        comment: comment || (status === 'approved' ? 'Approved' : 'Rejected')
      });
      toast.success(`Application ${status} successfully`);
      setIsReviewing(false);
      setComment('');
      setSelectedLeave(null);
      fetchInbox(); // Refresh
    } catch (error: any) {
      toast.error(errMsg(error, `Failed to ${status} application`));
    } finally {
      setIsProcessing(false);
    }
  };

  const handleDownloadTemplate = async () => {
    try {
      const res = await client.get(ENDPOINTS.LEAVE.BALANCE_TEMPLATE, { responseType: 'blob' });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'leave_balance_template.xlsx';
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      toast.error('Failed to download template');
    }
  };

  const handleBalanceUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploadingBalances(true);
    setUploadResult(null);
    try {
      const form = new FormData();
      form.append('file', file);
      const res = await client.post(ENDPOINTS.LEAVE.BALANCE_BULK_UPLOAD, form);
      setUploadResult(res.data);
      toast.success(`Done: ${res.data.created} created, ${res.data.updated} updated, ${res.data.skipped} skipped`);
    } catch (err: any) {
      toast.error(errMsg(err, 'Upload failed'));
    } finally {
      setUploadingBalances(false);
      if (balanceFileRef.current) balanceFileRef.current.value = '';
    }
  };

  return (
    <div className="p-8 space-y-8 max-w-[1600px] mx-auto animate-in fade-in duration-500">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
        <div>
          <h2 className="text-3xl font-black text-[#0F172A] tracking-tighter">Leave Management Bureau</h2>
          <p className="text-[#64748B] font-bold uppercase tracking-widest text-[10px] mt-1">Absence Approval Workflows & Resource Availability Analysis</p>
        </div>
        <div className="flex gap-3">
           <Button variant="outline" className="font-black h-12 px-6 uppercase text-[10px] tracking-widest border-slate-200" onClick={fetchInbox}>Refresh List</Button>
        </div>
      </div>

      <Tabs
        defaultValue="pending"
        className="space-y-8"
        onValueChange={tab => {
          setActiveTab(tab);
          setMountedTabs(prev => new Set([...prev, tab]));
        }}
      >
        <TabsList className="bg-slate-100 p-1.5 rounded-2xl h-14 w-fit flex-wrap">
          <TabsTrigger value="pending" className="rounded-xl px-8 font-black text-[10px] uppercase tracking-widest data-[state=active]:bg-white data-[state=active]:shadow-sm h-full flex items-center gap-2">
            Pending Review <Badge variant="error" className="h-5 px-1.5 min-w-[20px] justify-center text-[8px] font-black">{inbox.length}</Badge>
          </TabsTrigger>
          <TabsTrigger value="history" className="rounded-xl px-8 font-black text-[10px] uppercase tracking-widest data-[state=active]:bg-white data-[state=active]:shadow-sm h-full">History</TabsTrigger>
          <TabsTrigger value="balances" className="rounded-xl px-8 font-black text-[10px] uppercase tracking-widest data-[state=active]:bg-white data-[state=active]:shadow-sm h-full">Leave Balances</TabsTrigger>
          <TabsTrigger value="grant" className="rounded-xl px-8 font-black text-[10px] uppercase tracking-widest data-[state=active]:bg-white data-[state=active]:shadow-sm h-full">Grant Leave</TabsTrigger>
          <TabsTrigger value="compoff" className="rounded-xl px-8 font-black text-[10px] uppercase tracking-widest data-[state=active]:bg-white data-[state=active]:shadow-sm h-full">Comp Off</TabsTrigger>
        </TabsList>

        <TabsContent value="pending" className="space-y-6">
          <div className="grid grid-cols-1 gap-6">
            {isLoading ? (
              [1,2].map(i => <div key={i} className="h-48 bg-slate-100 animate-pulse rounded-3xl" />)
            ) : inbox.length === 0 ? (
              <Card className="p-20 text-center border-dashed border-2 border-slate-200">
                <CheckCircle2 size={40} className="mx-auto text-slate-200 mb-4" />
                <p className="text-sm font-black text-slate-400 uppercase tracking-widest">No pending leave applications found</p>
              </Card>
            ) : inbox.map((item) => (
              <Card key={item.id} className="p-0 border-slate-200 overflow-hidden hover:shadow-xl transition-all group">
                <div className="flex flex-col md:flex-row h-full">
                  <div className="w-full md:w-2 bg-amber-500" />
                  <div className="flex-1 p-8">
                    <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
                      <div className="flex items-center gap-5">
                        <div className="w-14 h-14 rounded-2xl bg-slate-50 border border-slate-100 flex items-center justify-center font-black text-blue-600 shadow-sm group-hover:bg-blue-600 group-hover:text-white transition-all duration-300">
                          {item.requested_by_name?.charAt(0) || 'U'}
                        </div>
                        <div>
                          <h3 className="text-xl font-black text-[#0F172A] tracking-tight">{item.requested_by_name || 'Unknown Employee'}</h3>
                          <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mt-0.5">Request Step {item.current_step_number} of {item.steps?.length ?? 1}</p>
                        </div>
                      </div>
                      <div className="flex flex-col items-end gap-2">
                        <div className="flex items-center gap-2 text-slate-400">
                          <Calendar size={14} />
                          <span className="text-xs font-black uppercase tracking-widest">Resource ID: {item.resource_id}</span>
                        </div>
                        <Badge variant="warning" className="text-[8px] px-2 h-5 font-black uppercase tracking-widest">Action Required</Badge>
                      </div>
                    </div>

                    {/* Leave detail — shown when the approval item references a LeaveRequest */}
                    {(item as any).leave_detail && (() => {
                      const ld = (item as any).leave_detail;
                      return (
                        <div className="mt-6 p-5 rounded-2xl bg-slate-50 border border-slate-100">
                          <div className="flex flex-wrap items-start gap-x-8 gap-y-4">
                            <div>
                              <p className="text-[9px] font-black text-slate-400 uppercase tracking-widest">Leave Type</p>
                              <p className="text-sm font-black text-slate-900 mt-1">
                                {ld.leave_type}
                                {ld.leave_type_code && (
                                  <span className="ml-2 text-[10px] font-black text-slate-500">({ld.leave_type_code})</span>
                                )}
                              </p>
                            </div>
                            <div>
                              <p className="text-[9px] font-black text-slate-400 uppercase tracking-widest">Dates</p>
                              <p className="text-sm font-bold text-slate-800 mt-1 tabular-nums">
                                {ld.start_date}
                                {ld.start_date !== ld.end_date && ` → ${ld.end_date}`}
                                {ld.is_half_day && (
                                  <span className="ml-2 text-[9px] font-black text-indigo-700 uppercase tracking-widest px-1.5 py-0.5 rounded bg-indigo-50 border border-indigo-100">
                                    {ld.half_day_session === 'morning' ? 'HD1' : 'HD2'}
                                  </span>
                                )}
                              </p>
                            </div>
                            <div>
                              <p className="text-[9px] font-black text-slate-400 uppercase tracking-widest">Days</p>
                              <p className="text-sm font-black text-slate-900 mt-1 tabular-nums">{ld.days}</p>
                            </div>
                            {ld.emergency_contact && (
                              <div>
                                <p className="text-[9px] font-black text-slate-400 uppercase tracking-widest">Emergency Contact</p>
                                <p className="text-sm font-bold text-slate-700 mt-1 tabular-nums">{ld.emergency_contact}</p>
                              </div>
                            )}
                          </div>
                          {ld.reason && (
                            <div className="mt-4">
                              <p className="text-[9px] font-black text-slate-400 uppercase tracking-widest">Reason</p>
                              <p className="text-sm text-slate-700 font-medium mt-1 leading-relaxed">{ld.reason}</p>
                            </div>
                          )}
                          {ld.attachment_url && (
                            <div className="mt-4">
                              <p className="text-[9px] font-black text-slate-400 uppercase tracking-widest mb-2">Supporting Document</p>
                              <div className="inline-flex items-center gap-3 px-4 py-2.5 rounded-xl border border-slate-200 bg-white">
                                <Paperclip size={14} className="text-indigo-600 shrink-0" aria-hidden="true" />
                                <span className="text-xs font-bold text-slate-700">Medical certificate / supporting document</span>
                                <div className="flex items-center gap-1 ml-2">
                                  <button
                                    type="button"
                                    onClick={() => openLeaveAttachment(ld.attachment_url)}
                                    className="inline-flex items-center gap-1.5 h-8 px-3 rounded-lg text-[10px] font-black uppercase tracking-widest text-indigo-600 hover:bg-indigo-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500/30 transition-colors"
                                    aria-label="View attachment in a new tab"
                                  >
                                    <FileText size={12} /> View
                                  </button>
                                  <button
                                    type="button"
                                    onClick={() => downloadLeaveAttachment(ld.attachment_url)}
                                    className="inline-flex items-center gap-1.5 h-8 px-3 rounded-lg text-[10px] font-black uppercase tracking-widest text-slate-700 hover:bg-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400/30 transition-colors"
                                    aria-label="Download attachment"
                                  >
                                    <Download size={12} /> Download
                                  </button>
                                </div>
                              </div>
                            </div>
                          )}
                        </div>
                      );
                    })()}

                    <div className="mt-8 pt-8 border-t border-slate-100 flex justify-end gap-3">
                       <Button 
                        variant="outline" 
                        className="h-11 px-8 font-black uppercase text-[10px] tracking-widest border-slate-200 hover:bg-red-50 hover:text-red-600 hover:border-red-200" 
                        onClick={() => {setSelectedLeave(item); setIsReviewing(true);}}
                       >
                        Reject
                       </Button>
                       <Button 
                        className="h-11 px-8 font-black uppercase text-[10px] tracking-widest bg-blue-600 hover:bg-blue-700 shadow-lg shadow-blue-600/20" 
                        onClick={() => handleAction(item.id, 'approved')}
                        disabled={isProcessing}
                       >
                        Approve Leave
                       </Button>
                    </div>
                  </div>
                </div>
              </Card>
            ))}
          </div>
        </TabsContent>

        <TabsContent value="history" className="space-y-6">
          {mountedTabs.has('history') && <LeaveHistoryPanel />}
        </TabsContent>

        <TabsContent value="balances" className="space-y-6">
          <Card className="p-8 border-slate-200">
            <div className="flex items-start justify-between mb-6">
              <div>
                <h3 className="text-lg font-black text-slate-900 tracking-tight">Bulk Leave Balance Upload</h3>
                <p className="text-xs text-slate-400 font-bold mt-1 uppercase tracking-widest">Upload opening or adjusted leave balances for all employees at once</p>
              </div>
              <Button variant="outline" onClick={handleDownloadTemplate} className="font-black h-10 px-5 uppercase text-[9px] tracking-widest border-slate-200 flex items-center gap-2">
                <Download size={14} /> Download Template
              </Button>
            </div>


            <div
              className="border-2 border-dashed border-slate-200 rounded-2xl p-12 text-center hover:border-blue-300 hover:bg-blue-50/30 transition-all cursor-pointer"
              onClick={() => balanceFileRef.current?.click()}
            >
              <input ref={balanceFileRef} type="file" accept=".xlsx,.xls" className="hidden" onChange={handleBalanceUpload} />
              {uploadingBalances ? (
                <div className="flex flex-col items-center gap-3">
                  <Loader2 size={32} className="text-blue-600 animate-spin" />
                  <p className="text-sm font-black text-slate-500 uppercase tracking-widest">Processing upload...</p>
                </div>
              ) : (
                <div className="flex flex-col items-center gap-3">
                  <Upload size={32} className="text-slate-300" />
                  <p className="text-sm font-black text-slate-500 uppercase tracking-widest">Click to upload Excel file</p>
                  <p className="text-xs text-slate-400 font-bold">.xlsx or .xls — Download the template above for the correct format</p>
                </div>
              )}
            </div>

            {uploadResult && (
              <div className="mt-6 p-6 bg-slate-50 rounded-2xl border border-slate-200 space-y-3">
                <h4 className="text-xs font-black text-slate-600 uppercase tracking-widest mb-3">Upload Results</h4>
                <div className="grid grid-cols-3 gap-4">
                  <div className="text-center p-4 bg-green-50 rounded-xl border border-green-100">
                    <p className="text-2xl font-black text-green-600">{uploadResult.created}</p>
                    <p className="text-[9px] font-black text-green-500 uppercase tracking-widest mt-1">New Balances Created</p>
                  </div>
                  <div className="text-center p-4 bg-blue-50 rounded-xl border border-blue-100">
                    <p className="text-2xl font-black text-blue-600">{uploadResult.updated}</p>
                    <p className="text-[9px] font-black text-blue-500 uppercase tracking-widest mt-1">Balances Updated</p>
                  </div>
                  <div className="text-center p-4 bg-slate-100 rounded-xl border border-slate-200">
                    <p className="text-2xl font-black text-slate-500">{uploadResult.skipped}</p>
                    <p className="text-[9px] font-black text-slate-400 uppercase tracking-widest mt-1">Rows Skipped</p>
                  </div>
                </div>
                {uploadResult.errors?.length > 0 && (
                  <div className="mt-4 p-4 bg-red-50 rounded-xl border border-red-100">
                    <p className="text-[9px] font-black text-red-600 uppercase tracking-widest mb-2">Errors ({uploadResult.errors.length})</p>
                    <ul className="space-y-1">
                      {uploadResult.errors.map((err: string, i: number) => (
                        <li key={i} className="text-xs text-red-500 font-bold">{err}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}
          </Card>

          {/* Current Employee Balances — single source of truth */}
          <BalancesListPanel />
        </TabsContent>

        {/* ── Grant Leave Tab — only mounts when first visited ── */}
        <TabsContent value="grant" className="space-y-6">
          {mountedTabs.has('grant') && <GrantLeavePanel />}
        </TabsContent>

        {/* ── Comp Off Tab — only mounts when first visited ── */}
        <TabsContent value="compoff" className="space-y-6">
          {mountedTabs.has('compoff') && <CompOffPanel />}
        </TabsContent>

      </Tabs>

      {/* Rejection Modal */}
      <Dialog open={isReviewing} onOpenChange={setIsReviewing}>
        <DialogContent className="max-w-md p-0 overflow-hidden rounded-3xl border-none max-h-[90vh] min-h-[240px] flex flex-col">
          <DialogHeader className="p-8 bg-red-600 text-white">
            <DialogTitle className="text-2xl font-black tracking-tighter flex items-center gap-3">
              Application Rejection
            </DialogTitle>
            <p className="text-red-100 text-[10px] font-bold uppercase tracking-widest mt-1">Specify decline reason for {selectedLeave?.requested_by_name || 'this employee'}</p>
          </DialogHeader>
          <div className="p-8 space-y-4 flex-1 overflow-y-auto min-h-0">
            <div className="space-y-2">
              <label className="text-[10px] font-black text-[#64748B] uppercase tracking-widest">Review Comments</label>
              <Textarea 
                value={comment}
                onChange={(e) => setComment(e.target.value)}
                placeholder="Explain the reasoning for this rejection..." 
                className="min-h-[120px] font-bold rounded-2xl bg-slate-50 resize-none" 
              />
            </div>
            <p className="text-[10px] font-bold text-slate-400 leading-relaxed uppercase tracking-tight">Decline notification will be sent immediately to the employee.</p>
          </div>
          <DialogFooter className="p-8 bg-slate-50 border-t border-slate-100 flex gap-3">
            <Button variant="outline" className="flex-1 h-12 font-black uppercase text-[10px] tracking-widest" onClick={() => setIsReviewing(false)}>Back</Button>
            <Button 
              className="flex-1 h-12 font-black uppercase text-[10px] tracking-widest bg-red-600 hover:bg-red-700 shadow-lg shadow-red-600/20" 
              onClick={() => selectedLeave && handleAction(selectedLeave.id, 'rejected')}
              disabled={isProcessing}
            >
              {isProcessing ? "Processing..." : "Confirm Rejection"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

// ─────────────────────────────────────────────────────────────
// SkeletonTable — generic shimmer rows that match table shape while loading
// ─────────────────────────────────────────────────────────────
const SkeletonTable = ({ columns, rows = 5 }: { columns: number; rows?: number }) => (
  <div className="rounded-2xl border border-slate-200 overflow-hidden" aria-busy="true" aria-live="polite">
    <div className="bg-slate-50 border-b border-slate-200 px-5 py-3 flex gap-6">
      {Array.from({ length: columns }).map((_, i) => (
        <div key={i} className="h-3 rounded bg-slate-200 animate-pulse" style={{ width: i === 0 ? '12rem' : '4rem' }} />
      ))}
    </div>
    {Array.from({ length: rows }).map((_, ri) => (
      <div key={ri} className={`px-5 py-4 flex gap-6 ${ri % 2 === 0 ? 'bg-white' : 'bg-slate-50/40'}`}>
        {Array.from({ length: columns }).map((_, ci) => (
          <div
            key={ci}
            className="h-3 rounded bg-slate-200/80 animate-pulse"
            style={{ width: ci === 0 ? '14rem' : `${3 + (ci % 3)}rem` }}
          />
        ))}
      </div>
    ))}
  </div>
);


// ─────────────────────────────────────────────────────────────
// Leave History Panel — org-wide approved/rejected/cancelled history
// ─────────────────────────────────────────────────────────────
const LeaveHistoryPanel = () => {
  const [rows, setRows] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState('approved');
  const [query, setQuery] = useState('');

  const load = async (status: string) => {
    setLoading(true);
    try {
      const params: any = status && status !== 'all' ? { status_filter: status } : {};
      const res = await client.get(ENDPOINTS.LEAVE.HISTORY, { params });
      setRows(res.data || []);
    } catch (err: any) {
      toast.error(errMsg(err, 'Failed to load leave history'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(statusFilter); }, [statusFilter]);

  const q = query.trim().toLowerCase();
  const filtered = q
    ? rows.filter((r: any) =>
        (r.employee_name || '').toLowerCase().includes(q) ||
        (r.employee_email || '').toLowerCase().includes(q) ||
        (r.leave_type || '').toLowerCase().includes(q)
      )
    : rows;

  const badgeClass = (s: string) => {
    const v = (s || '').toLowerCase();
    if (v === 'approved') return 'bg-emerald-50 text-emerald-800 border-emerald-200';
    if (v === 'rejected') return 'bg-red-50 text-red-800 border-red-200';
    if (v === 'cancelled') return 'bg-slate-100 text-slate-700 border-slate-300';
    if (v === 'submitted') return 'bg-amber-50 text-amber-800 border-amber-200';
    return 'bg-slate-50 text-slate-600 border-slate-200';
  };

  return (
    <Card className="p-8 border-slate-200">
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 mb-6">
        <div>
          <h3 className="text-lg font-black text-slate-900 tracking-tight">Leave History</h3>
          <p className="text-xs text-slate-500 font-bold mt-1 uppercase tracking-widest">
            Every leave request across the organisation
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <div className="relative">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" aria-hidden="true" />
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search employee or type…"
              aria-label="Search leave history"
              className="h-10 pl-9 w-64 rounded-xl font-bold"
            />
          </div>
          <label className="sr-only" htmlFor="leave-history-status">Status filter</label>
          <select
            id="leave-history-status"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="h-10 px-4 rounded-xl bg-slate-50 border border-slate-200 text-xs font-black uppercase tracking-widest outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
          >
            <option value="all">All Statuses</option>
            <option value="approved">Approved</option>
            <option value="rejected">Rejected</option>
            <option value="submitted">Pending</option>
            <option value="cancelled">Cancelled</option>
            <option value="draft">Draft</option>
          </select>
          <Button variant="outline" onClick={() => load(statusFilter)} className="h-10 px-4 font-black uppercase text-[9px] tracking-widest">
            Refresh
          </Button>
        </div>
      </div>

      {loading ? (
        <SkeletonTable columns={8} rows={6} />
      ) : filtered.length === 0 ? (
        <div className="py-16 px-6 text-center border border-dashed border-slate-200 rounded-2xl">
          <Clock size={28} className="mx-auto text-slate-300 mb-3" aria-hidden="true" />
          <p className="text-sm font-black text-slate-700">No leaves match this view</p>
          <p className="text-xs font-bold text-slate-500 mt-1">
            {q ? 'Try clearing the search box' : 'Try switching the status filter'}
          </p>
          {(q || statusFilter !== 'all') && (
            <Button
              variant="outline"
              className="mt-4 h-9 px-4 font-black uppercase text-[9px] tracking-widest"
              onClick={() => { setQuery(''); setStatusFilter('all'); }}
            >
              Clear filters
            </Button>
          )}
        </div>
      ) : (
        <div className="overflow-x-auto rounded-2xl border border-slate-200">
          <table className="w-full text-sm tabular-nums">
            <thead className="sticky top-0 z-10">
              <tr className="bg-slate-50 border-b border-slate-200">
                <th scope="col" className="text-left px-5 py-3 text-[9px] font-black text-slate-600 uppercase tracking-widest">Employee</th>
                <th scope="col" className="text-left px-5 py-3 text-[9px] font-black text-slate-600 uppercase tracking-widest">Type</th>
                <th scope="col" className="text-left px-5 py-3 text-[9px] font-black text-slate-600 uppercase tracking-widest">Dates</th>
                <th scope="col" className="text-right px-5 py-3 text-[9px] font-black text-slate-600 uppercase tracking-widest">Days</th>
                <th scope="col" className="text-left px-5 py-3 text-[9px] font-black text-slate-600 uppercase tracking-widest">Reason</th>
                <th scope="col" className="text-left px-5 py-3 text-[9px] font-black text-slate-600 uppercase tracking-widest">Status</th>
                <th scope="col" className="text-left px-5 py-3 text-[9px] font-black text-slate-600 uppercase tracking-widest">Submitted</th>
                <th scope="col" className="text-center px-5 py-3 text-[9px] font-black text-slate-600 uppercase tracking-widest">Doc</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((r: any, idx: number) => (
                <tr key={r.id} className={idx % 2 === 0 ? 'bg-white' : 'bg-slate-50/50'}>
                  <td className="px-5 py-3">
                    <p className="font-black text-slate-800">{r.employee_name || '—'}</p>
                    <p className="text-[10px] font-bold text-slate-400">{r.employee_email}</p>
                  </td>
                  <td className="px-5 py-3 font-bold text-slate-700">{r.leave_type || '—'}</td>
                  <td className="px-5 py-3 font-bold text-slate-600">
                    {r.start_date}{r.start_date !== r.end_date ? ` → ${r.end_date}` : ''}
                    {r.is_half_day && (
                      <span className="ml-2 text-[9px] font-black text-indigo-700 uppercase tracking-widest px-1.5 py-0.5 rounded bg-indigo-50 border border-indigo-100">
                        {r.half_day_session === 'morning' ? 'HD1' : 'HD2'}
                      </span>
                    )}
                  </td>
                  <td className="px-5 py-3 text-right font-black text-slate-800">{r.days}</td>
                  <td className="px-5 py-3 text-xs text-slate-500 font-bold max-w-xs truncate" title={r.reason}>{r.reason || '—'}</td>
                  <td className="px-5 py-3">
                    <span className={`text-[9px] font-black uppercase tracking-widest px-3 py-1 rounded-full border ${badgeClass(r.status)}`}>
                      {r.status}
                    </span>
                  </td>
                  <td className="px-5 py-3 text-xs font-bold text-slate-500">
                    {r.created_at ? new Date(r.created_at).toLocaleDateString() : '—'}
                  </td>
                  <td className="px-5 py-3 text-center">
                    {r.attachment_url ? (
                      <button
                        type="button"
                        onClick={() => openLeaveAttachment(r.attachment_url)}
                        className="inline-flex items-center justify-center h-8 w-8 rounded-lg text-indigo-600 hover:bg-indigo-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500/30"
                        aria-label={`View attachment for ${r.employee_name || 'employee'}`}
                        title="View attachment"
                      >
                        <Paperclip size={14} />
                      </button>
                    ) : (
                      <span className="text-slate-300" aria-hidden="true">—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="text-[10px] font-bold text-slate-500 px-5 py-3 border-t border-slate-100 bg-slate-50/40">
            Showing <span className="text-slate-800">{filtered.length}</span> of <span className="text-slate-800">{rows.length}</span> records
          </p>
        </div>
      )}
    </Card>
  );
};


// ─────────────────────────────────────────────────────────────
// Balances List Panel — single source of truth view of everyone's ledger
// ─────────────────────────────────────────────────────────────
const BalancesListPanel = () => {
  const [rows, setRows] = useState<any[]>([]);
  const [leaveTypes, setLeaveTypes] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState('');

  const load = async () => {
    setLoading(true);
    try {
      const [listRes, ltRes] = await Promise.all([
        client.get(ENDPOINTS.LEAVE.BALANCES_ALL),
        client.get(ENDPOINTS.LEAVE.TYPES),
      ]);
      setRows(listRes.data || []);
      setLeaveTypes(ltRes.data || []);
    } catch (err: any) {
      toast.error(errMsg(err, 'Failed to load balances'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const q = query.trim().toLowerCase();
  const filtered = q
    ? rows.filter((r: any) =>
        (r.full_name || '').toLowerCase().includes(q) ||
        (r.email || '').toLowerCase().includes(q)
      )
    : rows;

  return (
    <Card className="p-8 border-slate-200">
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 mb-6">
        <div>
          <h3 className="text-lg font-black text-slate-900 tracking-tight">Current Leave Balances</h3>
          <p className="text-xs text-slate-500 font-bold mt-1 uppercase tracking-widest">
            Live ledger — reflects bulk uploads, manual grants, and approved leaves
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="relative">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" aria-hidden="true" />
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search employee…"
              aria-label="Search employees"
              className="h-10 pl-9 w-64 rounded-xl font-bold"
            />
          </div>
          <Button variant="outline" onClick={load} className="h-10 px-4 font-black uppercase text-[9px] tracking-widest">
            Refresh
          </Button>
        </div>
      </div>

      {loading ? (
        <SkeletonTable columns={Math.max(2, leaveTypes.length + 1)} rows={5} />
      ) : filtered.length === 0 ? (
        <div className="py-16 px-6 text-center border border-dashed border-slate-200 rounded-2xl">
          <Gift size={28} className="mx-auto text-slate-300 mb-3" aria-hidden="true" />
          <p className="text-sm font-black text-slate-700">
            {q ? 'No employee matches that search' : 'No balances recorded yet'}
          </p>
          <p className="text-xs font-bold text-slate-500 mt-1">
            {q
              ? 'Try a different name or email'
              : 'Upload opening balances above, or use "Grant Leave" to assign per employee'}
          </p>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-2xl border border-slate-200">
          <table className="w-full text-sm tabular-nums">
            <thead className="sticky top-0 z-10">
              <tr className="bg-slate-50 border-b border-slate-200">
                <th scope="col" className="text-left px-5 py-3 text-[9px] font-black text-slate-600 uppercase tracking-widest sticky left-0 bg-slate-50 z-20">Employee</th>
                {leaveTypes.map((lt: any) => (
                  <th key={lt.id} scope="col" className="text-right px-4 py-3 text-[9px] font-black text-slate-600 uppercase tracking-widest" title={lt.name}>
                    {lt.code || lt.name}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.map((r: any, idx: number) => {
                const map: Record<number, any> = {};
                (r.balances || []).forEach((b: any) => { map[b.leave_type_id] = b; });
                const rowBg = idx % 2 === 0 ? 'bg-white' : 'bg-slate-50/50';
                return (
                  <tr key={r.user_id} className={rowBg}>
                    <td className={`px-5 py-3 sticky left-0 ${rowBg}`}>
                      <p className="font-black text-slate-800">{r.full_name}</p>
                      <p className="text-[10px] font-bold text-slate-500">{r.email}</p>
                    </td>
                    {leaveTypes.map((lt: any) => {
                      const b = map[lt.id];
                      if (!b) {
                        return (
                          <td key={lt.id} className="px-4 py-3 text-right text-slate-400 font-bold" aria-label="no balance">—</td>
                        );
                      }
                      return (
                        <td key={lt.id} className="px-4 py-3 text-right">
                          <span className="font-black text-slate-800">{b.remaining}</span>
                          <span className="text-[10px] font-bold text-slate-500 ml-1">/ {b.balance}</span>
                        </td>
                      );
                    })}
                  </tr>
                );
              })}
            </tbody>
          </table>
          <p className="text-[10px] font-bold text-slate-500 px-5 py-3 border-t border-slate-100 bg-slate-50/40 flex justify-between">
            <span>
              Cell: <span className="text-slate-800">remaining</span> / <span className="text-slate-700">total</span>
            </span>
            <span>
              Showing <span className="text-slate-800">{filtered.length}</span> of <span className="text-slate-800">{rows.length}</span> employees
            </span>
          </p>
        </div>
      )}
    </Card>
  );
};


// ─────────────────────────────────────────────────────────────
// Grant Leave Panel — HR assigns opening leave balances to an employee
// ─────────────────────────────────────────────────────────────
const GrantLeavePanel = () => {
  const [employees, setEmployees] = useState<any[]>([]);
  const [leaveTypes, setLeaveTypes] = useState<any[]>([]);
  const [loadingInit, setLoadingInit] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [selectedEmpId, setSelectedEmpId] = useState('');
  const [empSearch, setEmpSearch] = useState('');
  // Map of leave_type_id → { days (signed delta), reason }
  const [grants, setGrants] = useState<Record<number, { days: string; reason: string }>>({});
  // Map of leave_type_id → { balance, used } for currently selected employee
  const [currentBalances, setCurrentBalances] = useState<Record<number, { balance: number; used: number }>>({});
  const [loadingBalances, setLoadingBalances] = useState(false);

  useEffect(() => {
    const load = async () => {
      try {
        // GET /hr/employees returns { items: [...], total: N }
        const [empRes, ltRes] = await Promise.all([
          client.get(ENDPOINTS.HR.EMPLOYEES, { params: { size: 500 } }),
          client.get(ENDPOINTS.LEAVE.TYPES),
        ]);
        const empList = empRes.data?.items ?? (Array.isArray(empRes.data) ? empRes.data : []);
        setEmployees(empList);
        const types = ltRes.data;
        setLeaveTypes(types);
        const init: Record<number, { days: string; reason: string }> = {};
        types.forEach((lt: any) => { init[lt.id] = { days: '', reason: '' }; });
        setGrants(init);
      } catch (err: any) {
        toast.error(errMsg(err, 'Failed to load employees or leave types'));
      } finally {
        setLoadingInit(false);
      }
    };
    load();
  }, []);

  // Fetch the selected employee's current balances whenever selection changes.
  useEffect(() => {
    if (!selectedEmpId) {
      setCurrentBalances({});
      return;
    }
    let cancelled = false;
    const fetchBalances = async () => {
      setLoadingBalances(true);
      try {
        const res = await client.get(ENDPOINTS.LEAVE.BALANCES_BY_USER(Number(selectedEmpId)));
        if (cancelled) return;
        const map: Record<number, { balance: number; used: number }> = {};
        (res.data || []).forEach((b: any) => {
          map[b.leave_type.id] = { balance: Number(b.balance || 0), used: Number(b.used || 0) };
        });
        setCurrentBalances(map);
      } catch (err: any) {
        if (!cancelled) toast.error(errMsg(err, 'Failed to load current balances'));
      } finally {
        if (!cancelled) setLoadingBalances(false);
      }
    };
    fetchBalances();
    return () => { cancelled = true; };
  }, [selectedEmpId]);

  const showDropdown = empSearch.trim().length >= 3;
  const filteredEmployees = showDropdown
    ? employees.filter((e: any) => {
        const name = (e.user?.full_name || e.full_name || '').toLowerCase();
        const empId = (e.employee_id || '').toLowerCase();
        const dept = (e.department || '').toLowerCase();
        const q = empSearch.toLowerCase();
        return name.includes(q) || empId.includes(q) || dept.includes(q);
      })
    : [];

  const refetchBalances = async () => {
    if (!selectedEmpId) return;
    try {
      const res = await client.get(ENDPOINTS.LEAVE.BALANCES_BY_USER(Number(selectedEmpId)));
      const map: Record<number, { balance: number; used: number }> = {};
      (res.data || []).forEach((b: any) => {
        map[b.leave_type.id] = { balance: Number(b.balance || 0), used: Number(b.used || 0) };
      });
      setCurrentBalances(map);
    } catch {
      // silent — toast already shown on initial load error
    }
  };

  const handleSubmit = async () => {
    if (!selectedEmpId) { toast.error('Please select an employee'); return; }
    const selectedEmp = employees.find((e: any) => String(e.user_id) === selectedEmpId);

    const entries = Object.entries(grants)
      .map(([ltId, v]) => ({ ltId: Number(ltId), days: Number(v.days), reason: v.reason }))
      .filter((e) => e.days && !Number.isNaN(e.days));

    if (!entries.length) { toast.error('Enter a non-zero delta for at least one leave type'); return; }

    // Client-side guard: resulting balance must stay >= used
    for (const e of entries) {
      const cur = currentBalances[e.ltId] || { balance: 0, used: 0 };
      const newBal = cur.balance + e.days;
      if (newBal < cur.used) {
        const lt = leaveTypes.find((l: any) => l.id === e.ltId);
        toast.error(`${lt?.name || 'Leave type'}: new balance (${newBal}) cannot be less than used (${cur.used})`);
        return;
      }
    }

    setIsSubmitting(true);
    try {
      const res = await client.post(ENDPOINTS.LEAVE.GRANT, {
        employee_id: Number(selectedEmpId),
        grants: entries.map((e) => ({
          leave_type_id: e.ltId,
          days: e.days,
          reason: e.reason || 'HR adjustment',
        })),
      });
      const granted: any[] = res.data?.grants ?? [];
      const summary = granted
        .map((g: any) => `${g.leave_type}: ${g.previous_balance} → ${g.new_balance}`)
        .join(', ');
      toast.success(`Saved for ${selectedEmp?.user?.full_name}: ${summary}`);
      setGrants(prev => {
        const reset = { ...prev };
        Object.keys(reset).forEach(k => { reset[Number(k)] = { days: '', reason: '' }; });
        return reset;
      });
      await refetchBalances();
    } catch (err: any) {
      toast.error(errMsg(err, 'Failed to save leave balances'));
    } finally {
      setIsSubmitting(false);
    }
  };

  const selectedEmp = employees.find((e: any) => String(e.user_id) === selectedEmpId);

  if (loadingInit) {
    return (
      <div className="flex justify-center py-20">
        <Loader2 size={28} className="text-blue-600 animate-spin" />
      </div>
    );
  }

  return (
    <Card className="p-0 border-slate-200 overflow-hidden">
      <div className="p-8 border-b border-slate-100 bg-slate-50/50">
        <div className="flex items-center gap-4">
          <div className="w-12 h-12 bg-green-100 rounded-2xl flex items-center justify-center">
            <Gift size={22} className="text-green-600" />
          </div>
          <div>
            <h3 className="text-xl font-black text-[#0F172A] tracking-tight">Assign Leave Balances</h3>
            <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mt-0.5">Set opening leave balances for a new or existing employee</p>
          </div>
        </div>
      </div>

      <div className="p-8 space-y-8">
        {/* Step 1 — Pick employee */}
        <div className="space-y-3">
          <label className="text-[9px] font-black text-slate-500 uppercase tracking-widest">
            Step 1 — Select Employee <span className="text-red-500">*</span>
          </label>

          {/* Selected employee chip — shown when an employee is chosen and not actively searching */}
          {selectedEmp && !empSearch ? (
            <div className="flex items-center gap-4 p-4 bg-blue-50 rounded-2xl border border-blue-100">
              <div className="w-10 h-10 rounded-xl bg-blue-600 flex items-center justify-center font-black text-white text-sm flex-shrink-0">
                {(selectedEmp.user?.full_name || selectedEmp.full_name || '?').charAt(0).toUpperCase()}
              </div>
              <div className="flex-1">
                <p className="text-sm font-black text-slate-800">{selectedEmp.user?.full_name || selectedEmp.full_name}</p>
                <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">{selectedEmp.employee_id} · {selectedEmp.department || '—'}</p>
              </div>
              <button
                onClick={() => { setSelectedEmpId(''); setEmpSearch(''); }}
                className="text-xs font-black text-slate-400 hover:text-red-500 uppercase tracking-widest"
              >
                Change
              </button>
            </div>
          ) : (
            /* Search box + floating dropdown */
            <div className="relative">
              <Search size={15} className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400 z-10" />
              <input
                type="text"
                placeholder={employees.length > 0 ? `Search from ${employees.length} employees…` : 'Type to search…'}
                value={empSearch}
                onChange={e => setEmpSearch(e.target.value)}
                className="w-full h-12 pl-11 pr-4 rounded-2xl border border-slate-200 bg-white text-sm font-bold text-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />

              {/* Floating results — absolutely positioned so it doesn't push content */}
              {showDropdown && (
                <div className="absolute z-50 left-0 right-0 top-[calc(100%+4px)] rounded-2xl border border-slate-200 bg-white shadow-xl overflow-hidden max-h-56 overflow-y-auto">
                  {filteredEmployees.length === 0 ? (
                    <div className="px-5 py-6 text-center text-xs font-bold text-slate-400 uppercase tracking-widest">
                      No match found
                    </div>
                  ) : (
                    filteredEmployees.map((emp: any) => {
                      const uid = String(emp.user_id);
                      const name = emp.user?.full_name || emp.full_name || '—';
                      return (
                        <button
                          key={emp.id}
                          onMouseDown={e => e.preventDefault()}
                          onClick={() => { setSelectedEmpId(uid); setEmpSearch(''); }}
                          className="w-full flex items-center gap-4 px-5 py-3 text-left hover:bg-blue-50 transition-colors border-b border-slate-100 last:border-b-0 bg-white"
                        >
                          <div className="w-9 h-9 rounded-xl bg-blue-100 flex items-center justify-center font-black text-blue-600 text-sm flex-shrink-0">
                            {name.charAt(0).toUpperCase()}
                          </div>
                          <div className="flex-1 min-w-0">
                            <p className="text-sm font-black text-slate-800 truncate">{name}</p>
                            <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">{emp.employee_id} · {emp.department || '—'}</p>
                          </div>
                        </button>
                      );
                    })
                  )}
                </div>
              )}

              {empSearch.trim().length > 0 && empSearch.trim().length < 3 && (
                <p className="mt-2 text-[10px] font-bold text-slate-400">Keep typing… ({3 - empSearch.trim().length} more character{3 - empSearch.trim().length !== 1 ? 's' : ''})</p>
              )}
            </div>
          )}
        </div>

        {/* Step 2 — Adjust balance per leave type (signed delta) */}
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <label className="text-[9px] font-black text-slate-600 uppercase tracking-widest">
              Step 2 — Adjust Balance <span className="text-slate-400 normal-case tracking-normal font-bold">(+ adds, − subtracts)</span>
            </label>
            {selectedEmpId && loadingBalances && (
              <span className="text-[10px] font-bold text-slate-500 flex items-center gap-2">
                <Loader2 size={12} className="animate-spin" aria-hidden="true" /> Loading current balances…
              </span>
            )}
          </div>
          <div className="rounded-2xl border border-slate-200 overflow-hidden">
            <table className="w-full text-sm tabular-nums">
              <thead>
                <tr className="bg-slate-50 border-b border-slate-200">
                  <th scope="col" className="text-left px-5 py-3 text-[9px] font-black text-slate-600 uppercase tracking-widest">Leave Type</th>
                  <th scope="col" className="text-right px-5 py-3 text-[9px] font-black text-slate-600 uppercase tracking-widest w-24">Current</th>
                  <th scope="col" className="text-right px-5 py-3 text-[9px] font-black text-slate-600 uppercase tracking-widest w-20">Used</th>
                  <th scope="col" className="text-left px-5 py-3 text-[9px] font-black text-slate-600 uppercase tracking-widest w-32">Δ Days</th>
                  <th scope="col" className="text-right px-5 py-3 text-[9px] font-black text-slate-600 uppercase tracking-widest w-24">New Balance</th>
                  <th scope="col" className="text-left px-5 py-3 text-[9px] font-black text-slate-600 uppercase tracking-widest">Reason <span className="text-slate-400 normal-case tracking-normal">(optional)</span></th>
                </tr>
              </thead>
              <tbody>
                {leaveTypes.map((lt: any, idx: number) => {
                  const cur = currentBalances[lt.id] || { balance: 0, used: 0 };
                  const deltaStr = grants[lt.id]?.days ?? '';
                  const deltaNum = deltaStr === '' || deltaStr === '-' ? 0 : Number(deltaStr);
                  const projected = cur.balance + (Number.isFinite(deltaNum) ? deltaNum : 0);
                  const invalid = Number.isFinite(deltaNum) && projected < cur.used;
                  const errorId = `grant-err-${lt.id}`;
                  return (
                    <tr key={lt.id} className={idx % 2 === 0 ? 'bg-white' : 'bg-slate-50/50'}>
                      <td className="px-5 py-3 font-bold text-slate-800">{lt.name}</td>
                      <td className="px-5 py-3 text-right font-black text-slate-700">{selectedEmpId ? cur.balance : '—'}</td>
                      <td className="px-5 py-3 text-right font-bold text-slate-600">{selectedEmpId ? cur.used : '—'}</td>
                      <td className="px-5 py-3">
                        <Input
                          type="number"
                          step="0.5"
                          placeholder="e.g. 5 or -2"
                          value={deltaStr}
                          disabled={!selectedEmpId}
                          aria-label={`Delta days for ${lt.name}. Positive adds, negative subtracts.`}
                          aria-invalid={invalid || undefined}
                          aria-describedby={invalid ? errorId : undefined}
                          onChange={e => setGrants(prev => ({ ...prev, [lt.id]: { ...prev[lt.id], days: e.target.value } }))}
                          className={`h-9 rounded-xl font-bold w-28 text-center ${invalid ? 'border-red-400 focus:ring-red-400' : ''}`}
                        />
                        {invalid && (
                          <p id={errorId} role="alert" className="mt-1 text-[10px] font-bold text-red-600">
                            New balance cannot be less than {cur.used} used
                          </p>
                        )}
                      </td>
                      <td className={`px-5 py-3 text-right font-black ${invalid ? 'text-red-700' : 'text-emerald-800'}`}>
                        {selectedEmpId ? projected : '—'}
                      </td>
                      <td className="px-5 py-3">
                        <Input
                          placeholder="e.g. Annual top-up / correction"
                          value={grants[lt.id]?.reason ?? ''}
                          disabled={!selectedEmpId}
                          aria-label={`Reason for ${lt.name} adjustment`}
                          onChange={e => setGrants(prev => ({ ...prev, [lt.id]: { ...prev[lt.id], reason: e.target.value } }))}
                          className="h-9 rounded-xl font-bold"
                        />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className="text-[10px] font-bold text-slate-500">
            Leave Δ blank or 0 to skip a row. Positive adds; negative subtracts. New balance cannot drop below Used.
          </p>
        </div>

        <div className="flex justify-end pt-2">
          <Button
            className="h-12 px-10 font-black uppercase text-[10px] tracking-widest bg-green-600 hover:bg-green-700 shadow-lg shadow-green-600/20"
            onClick={handleSubmit}
            disabled={isSubmitting || !selectedEmpId}
          >
            {isSubmitting ? <><Loader2 size={14} className="animate-spin mr-2" />Saving…</> : <><Plus size={14} className="mr-2" />Save Leave Balances</>}
          </Button>
        </div>
      </div>
    </Card>
  );
};

// ─────────────────────────────────────────────────────────────
// Comp Off Panel — generate comp-off for employees who worked
// on a holiday/weekend, and manage pending requests
// ─────────────────────────────────────────────────────────────
const CompOffPanel = () => {
  const [employees, setEmployees] = useState<any[]>([]);
  const [pendingRequests, setPendingRequests] = useState<any[]>([]);
  const [loadingInit, setLoadingInit] = useState(true);
  const [loadingRequests, setLoadingRequests] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [processingId, setProcessingId] = useState<number | null>(null);

  const [form, setForm] = useState({
    employee_id: '',
    worked_date: '',
    reason: '',
    days: '1',
  });

  useEffect(() => {
    const load = async () => {
      try {
        const empRes = await client.get(ENDPOINTS.HR.EMPLOYEES, { params: { size: 500 } });
        setEmployees(empRes.data?.items ?? (Array.isArray(empRes.data) ? empRes.data : []));
      } catch (err: any) {
        toast.error(errMsg(err, 'Failed to load employees'));
      } finally {
        setLoadingInit(false);
      }
    };
    load();
    fetchPendingRequests();
  }, []);

  const fetchPendingRequests = async () => {
    setLoadingRequests(true);
    try {
      const res = await client.get(ENDPOINTS.LEAVE.COMP_OFF_REQUESTS);
      setPendingRequests(res.data);
    } catch {
      setPendingRequests([]);
    } finally {
      setLoadingRequests(false);
    }
  };

  const handleGenerate = async () => {
    if (!form.employee_id || !form.worked_date || !form.reason) {
      toast.error('Please fill all required fields');
      return;
    }
    setIsSubmitting(true);
    try {
      await client.post(ENDPOINTS.LEAVE.COMP_OFF_GENERATE, {
        employee_id: Number(form.employee_id),
        worked_date: form.worked_date,
        days: Number(form.days),
        reason: form.reason,
      });
      toast.success('Comp off generated and added to employee balance');
      setForm({ employee_id: '', worked_date: '', reason: '', days: '1' });
      fetchPendingRequests();
    } catch (err: any) {
      toast.error(errMsg(err, 'Failed to generate comp off'));
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleAction = async (id: number, action: 'approved' | 'rejected') => {
    setProcessingId(id);
    try {
      await client.post(ENDPOINTS.LEAVE.COMP_OFF_ACTION(id), { status: action });
      toast.success(`Comp off request ${action}`);
      fetchPendingRequests();
    } catch (err: any) {
      toast.error(errMsg(err, 'Action failed'));
    } finally {
      setProcessingId(null);
    }
  };

  return (
    <div className="space-y-8">
      {/* Generation Form */}
      <Card className="p-0 border-slate-200 overflow-hidden">
        <div className="p-8 border-b border-slate-100 bg-slate-50/50">
          <div className="flex items-center gap-4">
            <div className="w-12 h-12 bg-amber-100 rounded-2xl flex items-center justify-center">
              <Coffee size={22} className="text-amber-600" />
            </div>
            <div>
              <h3 className="text-xl font-black text-[#0F172A] tracking-tight">Generate Compensatory Off</h3>
              <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mt-0.5">Issue comp off for an employee who worked on a holiday or weekend</p>
            </div>
          </div>
        </div>

        <div className="p-8 space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Employee */}
            <div className="space-y-2">
              <label className="text-[9px] font-black text-slate-500 uppercase tracking-widest">Employee <span className="text-red-500">*</span></label>
              {loadingInit ? (
                <div className="h-12 bg-slate-100 animate-pulse rounded-2xl" />
              ) : (
                <select
                  value={form.employee_id}
                  onChange={e => setForm(f => ({ ...f, employee_id: e.target.value }))}
                  className="w-full h-12 px-4 rounded-2xl border border-slate-200 bg-white text-sm font-bold text-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  <option value="">Select employee…</option>
                  {employees.map((emp: any) => (
                    <option key={emp.id} value={emp.id}>{emp.user?.full_name || emp.full_name} — {emp.employee_id}</option>
                  ))}
                </select>
              )}
            </div>

            {/* Worked Date */}
            <div className="space-y-2">
              <label className="text-[9px] font-black text-slate-500 uppercase tracking-widest">Date Worked (Holiday/Weekend) <span className="text-red-500">*</span></label>
              <Input
                type="date"
                value={form.worked_date}
                onChange={e => setForm(f => ({ ...f, worked_date: e.target.value }))}
                className="h-12 rounded-2xl font-bold"
              />
            </div>

            {/* Days */}
            <div className="space-y-2">
              <label className="text-[9px] font-black text-slate-500 uppercase tracking-widest">Comp Off Days to Grant</label>
              <select
                value={form.days}
                onChange={e => setForm(f => ({ ...f, days: e.target.value }))}
                className="w-full h-12 px-4 rounded-2xl border border-slate-200 bg-white text-sm font-bold text-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="0.5">Half Day (0.5)</option>
                <option value="1">Full Day (1.0)</option>
              </select>
            </div>
          </div>

          {/* Reason */}
          <div className="space-y-2">
            <label className="text-[9px] font-black text-slate-500 uppercase tracking-widest">Reason / Work Description <span className="text-red-500">*</span></label>
            <Textarea
              placeholder="e.g. Worked on client deployment on Republic Day holiday, emergency production fix on Sunday…"
              value={form.reason}
              onChange={e => setForm(f => ({ ...f, reason: e.target.value }))}
              className="min-h-[100px] rounded-2xl font-bold bg-slate-50 resize-none"
            />
          </div>

          <div className="flex justify-end pt-2">
            <Button
              className="h-12 px-10 font-black uppercase text-[10px] tracking-widest bg-amber-600 hover:bg-amber-700 shadow-lg shadow-amber-600/20"
              onClick={handleGenerate}
              disabled={isSubmitting}
            >
              {isSubmitting ? <><Loader2 size={14} className="animate-spin mr-2" />Processing…</> : <><CheckCheck size={14} className="mr-2" />Generate Comp Off</>}
            </Button>
          </div>
        </div>
      </Card>

      {/* Pending Comp Off Requests */}
      <Card className="p-0 border-slate-200 overflow-hidden">
        <div className="p-8 border-b border-slate-100 bg-slate-50/50 flex items-center justify-between">
          <div>
            <h3 className="text-lg font-black text-[#0F172A] tracking-tight">Pending Comp Off Requests</h3>
            <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mt-0.5">Requests raised by employees awaiting HR approval</p>
          </div>
          <Button variant="outline" className="h-10 px-5 font-black uppercase text-[9px] tracking-widest border-slate-200" onClick={fetchPendingRequests}>
            Refresh
          </Button>
        </div>

        <div className="p-6">
          {loadingRequests ? (
            <div className="space-y-3">
              {[1, 2].map(i => <div key={i} className="h-20 bg-slate-100 animate-pulse rounded-2xl" />)}
            </div>
          ) : pendingRequests.length === 0 ? (
            <div className="py-16 flex flex-col items-center gap-4">
              <CheckCircle2 size={36} className="text-slate-200" />
              <p className="text-sm font-black text-slate-400 uppercase tracking-widest">No pending comp off requests</p>
            </div>
          ) : (
            <div className="space-y-4">
              {pendingRequests.map((req: any) => (
                <div key={req.id} className="flex flex-col md:flex-row md:items-center justify-between gap-4 p-5 bg-white border border-slate-200 rounded-2xl hover:shadow-md transition-all">
                  <div className="flex items-center gap-4">
                    <div className="w-11 h-11 rounded-xl bg-amber-50 border border-amber-100 flex items-center justify-center font-black text-amber-600 text-sm">
                      {req.employee_name?.charAt(0) || req.user?.full_name?.charAt(0) || 'U'}
                    </div>
                    <div>
                      <p className="text-sm font-black text-[#0F172A]">{req.employee_name || req.user?.full_name}</p>
                      <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mt-0.5">
                        Worked: {req.worked_date ? new Date(req.worked_date).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' }) : '—'} · {req.days || 1} day(s)
                      </p>
                      {req.reason && <p className="text-xs text-slate-500 font-bold mt-1 truncate max-w-sm">{req.reason}</p>}
                    </div>
                  </div>
                  <div className="flex gap-2 shrink-0">
                    <Button
                      variant="outline"
                      size="sm"
                      className="h-9 px-5 font-black uppercase text-[9px] tracking-widest border-slate-200 hover:bg-red-50 hover:text-red-600 hover:border-red-200"
                      onClick={() => handleAction(req.id, 'rejected')}
                      disabled={processingId === req.id}
                    >
                      Reject
                    </Button>
                    <Button
                      size="sm"
                      className="h-9 px-6 font-black uppercase text-[9px] tracking-widest bg-amber-600 hover:bg-amber-700 shadow-md shadow-amber-600/20"
                      onClick={() => handleAction(req.id, 'approved')}
                      disabled={processingId === req.id}
                    >
                      {processingId === req.id ? <Loader2 size={12} className="animate-spin" /> : 'Approve'}
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </Card>
    </div>
  );
};
