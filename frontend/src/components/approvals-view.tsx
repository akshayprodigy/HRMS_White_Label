import React, { useState, useEffect } from 'react';
import { 
  CheckCircle2, 
  XCircle, 
  User, 
  Calendar, 
  Clock, 
  ChevronRight,
  Filter,
  Search,
  Loader2,
  RefreshCw
} from 'lucide-react';
import { Card, Button, Badge, Input, cn } from './ui-elements';
import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';
import { ApprovalItem } from '../types/erp';
import { toast } from 'sonner';
import { normalizeRoleName } from '../utils/roles';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from './ui/dialog';

type ResourceTypeFilter =
  | 'all'
  | 'estimate'
  | 'estimate_version'
  | 'leave_request'
  | 'comp_off_accrual'
  | 'requisition';
type ApprovalStatusFilter = 'all' | 'pending' | 'approved' | 'rejected' | 'changes_requested';

type ApprovalResourcePayload = {
  resource_type: string;
  data: any;
};

type UserLink = {
  id: number;
  email: string;
  full_name?: string | null;
};

export const ApprovalsView = () => {
  const role = normalizeRoleName(localStorage.getItem('hr_role') || '');
  const isAdminViewer = role === 'admin' || role === 'super admin';

  const [resourceType, setResourceType] = useState<ResourceTypeFilter>('all');
  const [statusFilter, setStatusFilter] = useState<ApprovalStatusFilter>('all');
  const [dueBefore, setDueBefore] = useState<string>('');
  const [search, setSearch] = useState<string>('');
  const [approvals, setApprovals] = useState<ApprovalItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<number | null>(null);

  const [detailsOpen, setDetailsOpen] = useState(false);
  const [detailsLoading, setDetailsLoading] = useState(false);
  const [selectedApproval, setSelectedApproval] = useState<ApprovalItem | null>(null);
  const [selectedResource, setSelectedResource] = useState<ApprovalResourcePayload | null>(null);

  const [estimateApprovers, setEstimateApprovers] = useState<UserLink[]>([]);
  const [estimateApproversLoading, setEstimateApproversLoading] = useState(false);
  const [nextApproverId, setNextApproverId] = useState<string>('');

  useEffect(() => {
    fetchApprovals();
  }, [resourceType, statusFilter, dueBefore]);

  const fetchApprovals = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (resourceType !== 'all') params.set('resource_type', resourceType);
      if (statusFilter !== 'all') params.set('status', statusFilter);
      if (dueBefore) {
        // Backend expects an ISO datetime; use end-of-day UTC for the selected date.
        params.set('due_before', new Date(`${dueBefore}T23:59:59.999Z`).toISOString());
      }
      const url = `${ENDPOINTS.APPROVALS.INBOX}${params.toString() ? `?${params.toString()}` : ''}`;

      const response = await client.get(url);
      setApprovals(response.data);
    } catch (error: any) {
      toast.error('Failed to fetch approvals');
    } finally {
      setLoading(false);
    }
  };

  const openDetails = async (item: ApprovalItem) => {
    setDetailsOpen(true);
    setSelectedApproval(null);
    setSelectedResource(null);
    setEstimateApprovers([]);
    setNextApproverId('');
    setDetailsLoading(true);
    try {
      const [detailResp, resourceResp] = await Promise.all([
        client.get(ENDPOINTS.APPROVALS.DETAIL(item.id)),
        client.get(ENDPOINTS.APPROVALS.RESOURCE(item.id)),
      ]);

      setSelectedApproval(detailResp.data);
      setSelectedResource(resourceResp.data);

      const rt = (resourceResp.data?.resource_type || item.resource_type) as string;
      if (rt === 'estimate' || rt === 'estimate_version') {
        setEstimateApproversLoading(true);
        try {
          const approversResp = await client.get<UserLink[]>(ENDPOINTS.BD.ESTIMATE_APPROVERS);
          setEstimateApprovers(Array.isArray(approversResp.data) ? approversResp.data : []);
        } catch {
          setEstimateApprovers([]);
        } finally {
          setEstimateApproversLoading(false);
        }
      }
    } catch (error: any) {
      toast.error(
        error.response?.data?.error?.message ||
          error.response?.data?.detail ||
          'Failed to load approval details'
      );
    } finally {
      setDetailsLoading(false);
    }
  };

  const handleDetailsAction = async (
    status: 'approved' | 'rejected' | 'changes_requested'
  ) => {
    if (!selectedApproval) return;
    setActionLoading(selectedApproval.id);
    try {
      const isEstimate =
        selectedApproval.resource_type === 'estimate' ||
        selectedApproval.resource_type === 'estimate_version' ||
        selectedResource?.resource_type === 'estimate' ||
        selectedResource?.resource_type === 'estimate_version';

      await client.post(ENDPOINTS.APPROVALS.ACTION(selectedApproval.id), {
        status,
        comment:
          status === 'approved'
            ? 'Approved via unified center'
            : 'Actioned via unified center',
        next_approver_id:
          status === 'approved' && isEstimate && nextApproverId
            ? Number(nextApproverId)
            : undefined,
      });
      toast.success(`Request ${status} successfully`);

      // Keep dialog and list in sync
      const [detailResp, resourceResp] = await Promise.all([
        client.get(ENDPOINTS.APPROVALS.DETAIL(selectedApproval.id)),
        client.get(ENDPOINTS.APPROVALS.RESOURCE(selectedApproval.id)),
      ]);
      setSelectedApproval(detailResp.data);
      setSelectedResource(resourceResp.data);

      if (isAdminViewer) {
        // Keep the item visible after action:
        // - Backend inbox defaults to pending-only unless a status filter is provided.
        // - For admin, setting a non-pending status enables history mode.
        setStatusFilter(status);
      } else {
        fetchApprovals();
      }
    } catch (error: any) {
      toast.error(
        error.response?.data?.error?.message ||
          error.response?.data?.detail ||
          error.message ||
          'Action failed'
      );
    } finally {
      setActionLoading(null);
    }
  };

  const handleAction = async (id: number, status: string) => {
    setActionLoading(id);
    try {
      await client.post(ENDPOINTS.APPROVALS.ACTION(id), {
        status,
        comment: status === 'approved' ? 'Approved via unified center' : 'Actioned via unified center'
      });
      toast.success(`Request ${status} successfully`);

      if (isAdminViewer && (status === 'approved' || status === 'rejected' || status === 'changes_requested')) {
        setStatusFilter(status as ApprovalStatusFilter);
      } else {
        fetchApprovals();
      }
    } catch (error: any) {
      toast.error(error.message || 'Action failed');
    } finally {
      setActionLoading(null);
    }
  };

  const filteredApprovals = approvals.filter((item) => {
    const needle = search.trim().toLowerCase();
    if (!needle) return true;
    const haystack = [
      item.resource_id,
      item.resource_type,
      String(item.id),
    ]
      .filter(Boolean)
      .join(' ')
      .toLowerCase();
    return haystack.includes(needle);
  });

  return (
    <div className="p-8 space-y-8 max-w-[1200px] mx-auto animate-in fade-in duration-700">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-3xl font-black text-[#0F172A] tracking-tighter uppercase">Approvals Command Center</h2>
          <p className="text-[#64748B] font-bold uppercase tracking-widest text-[10px] mt-1">Unified Multi-Entity Reconciliation & Authorization Hub</p>
        </div>
        <div className="flex flex-col sm:flex-row gap-2 sm:items-center">
          <div className="flex bg-[#F1F5F9] p-1.5 rounded-2xl overflow-x-auto">
            {[
              { value: 'all', label: 'all' },
              { value: 'estimate', label: 'estimate' },
              { value: 'leave_request', label: 'leave' },
              { value: 'comp_off_accrual', label: 'comp-off' },
              { value: 'requisition', label: 'requisition' },
            ].map((tab) => (
              <button
                key={tab.value}
                onClick={() => setResourceType(tab.value as ResourceTypeFilter)}
                className={cn(
                  "px-4 py-2 rounded-xl text-[10px] font-black transition-all uppercase tracking-widest whitespace-nowrap",
                  resourceType === tab.value
                    ? "bg-blue-600 text-white shadow-lg shadow-blue-600/20"
                    : "text-[#64748B] hover:text-[#0F172A]"
                )}
              >
                {tab.label}
              </button>
            ))}
          </div>

          <div className="flex items-center gap-2">
            <div className="relative">
              <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
              <Input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search by ID/type"
                className="pl-9 h-10 rounded-xl text-xs font-semibold w-[200px]"
              />
            </div>

            <div className="flex items-center gap-2 bg-white border border-slate-200 rounded-xl px-3 h-10">
              <Filter className="w-4 h-4 text-slate-400" />
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value as ApprovalStatusFilter)}
                className="bg-transparent text-xs font-bold text-slate-700 outline-none"
              >
                <option value="all">All statuses</option>
                <option value="pending">Pending</option>
                <option value="approved">Approved</option>
                <option value="rejected">Rejected</option>
                <option value="changes_requested">Changes requested</option>
              </select>
            </div>

            <div className="flex items-center gap-2 bg-white border border-slate-200 rounded-xl px-3 h-10">
              <span className="text-[10px] font-black uppercase tracking-widest text-slate-500">Due</span>
              <input
                type="date"
                value={dueBefore}
                onChange={(e) => setDueBefore(e.target.value)}
                className="bg-transparent text-xs font-bold text-slate-700 outline-none"
              />
            </div>

            <Button
              onClick={fetchApprovals}
              variant="outline"
              className="h-10 rounded-xl font-black text-[10px] uppercase tracking-widest"
            >
              <RefreshCw size={14} className="mr-2" /> Refresh
            </Button>
          </div>
        </div>
      </div>

      {loading ? (
        <div className="py-20 flex justify-center">
           <Loader2 className="w-10 h-10 animate-spin text-blue-600" />
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4">
          {filteredApprovals.map((item) => (
            <Card
              key={item.id}
              onClick={() => openDetails(item)}
              className="p-6 border-slate-200 hover:shadow-xl hover:shadow-slate-200/50 transition-all group rounded-3xl cursor-pointer"
            >
              <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
                <div className="flex items-center space-x-4">
                  <div className="w-14 h-14 rounded-2xl bg-slate-50 flex items-center justify-center text-blue-600 group-hover:bg-blue-600 group-hover:text-white transition-all duration-500">
                    <CheckCircle2 size={24} />
                  </div>
                  <div>
                    <h4 className="text-lg font-black text-[#0F172A] tracking-tight truncate max-w-[220px]">ID: {item.resource_id}</h4>
                    <div className="flex items-center gap-2">
                      <p className="text-[10px] text-blue-600 font-black uppercase tracking-widest">{item.resource_type}</p>
                      <Badge
                        className={cn(
                          'rounded-full px-2 py-0.5 text-[10px] font-black uppercase tracking-widest',
                          item.status === 'approved'
                            ? 'bg-green-100 text-green-700'
                            : item.status === 'rejected'
                              ? 'bg-red-100 text-red-700'
                              : item.status === 'changes_requested'
                                ? 'bg-amber-100 text-amber-700'
                                : 'bg-slate-100 text-slate-700'
                        )}
                      >
                        {item.status}
                      </Badge>
                    </div>
                  </div>
                </div>

                <div className="flex flex-col md:items-start">
                  <div className="flex items-center text-xs font-bold text-slate-600">
                    <Calendar className="w-4 h-4 mr-2 text-slate-400" />
                    Requested: {new Date(item.created_at).toLocaleDateString()}
                  </div>
                  {item.due_date && (
                    <div className="flex items-center text-xs font-bold text-red-500 mt-1">
                      <Clock className="w-3.5 h-3.5 mr-2" /> 
                      Due: {new Date(item.due_date).toLocaleDateString()}
                    </div>
                  )}
                </div>

                <div className="flex items-center space-x-3">
                  <Button 
                    onClick={(e) => {
                      e.stopPropagation();
                      handleAction(item.id, 'rejected');
                    }}
                    disabled={actionLoading === item.id}
                    variant="outline" 
                    className="h-12 px-6 rounded-xl border-red-100 text-red-600 hover:bg-red-50 font-black text-xs uppercase tracking-widest"
                  >
                    Reject
                  </Button>
                  <Button 
                    onClick={(e) => {
                      e.stopPropagation();
                      handleAction(item.id, 'changes_requested');
                    }}
                    disabled={actionLoading === item.id}
                    variant="outline" 
                    className="h-12 px-6 rounded-xl border-amber-100 text-amber-600 hover:bg-amber-50 font-black text-xs uppercase tracking-widest"
                  >
                    Changes
                  </Button>
                  <Button 
                    onClick={(e) => {
                      e.stopPropagation();
                      if (item.resource_type === 'estimate' || item.resource_type === 'estimate_version') {
                        openDetails(item);
                        return;
                      }
                      handleAction(item.id, 'approved');
                    }}
                    disabled={actionLoading === item.id}
                    className="h-12 px-6 rounded-xl bg-green-600 hover:bg-green-700 font-black text-xs uppercase tracking-widest shadow-lg shadow-green-600/20"
                  >
                    {actionLoading === item.id ? (
                      <Loader2 size={16} className="animate-spin" />
                    ) : item.resource_type === 'estimate' || item.resource_type === 'estimate_version' ? (
                      'Review'
                    ) : (
                      'Approve'
                    )}
                  </Button>
                </div>
              </div>
            </Card>
          ))}
          {filteredApprovals.length === 0 && (
            <div className="py-24 text-center space-y-4 border-2 border-dashed border-slate-100 rounded-[40px]">
              <div className="inline-flex items-center justify-center w-20 h-20 rounded-3xl bg-green-50 text-green-500">
                <CheckCircle2 size={36} />
              </div>
              <div>
                <h3 className="text-xl font-black text-[#0F172A] tracking-tight">Zero Pending Actions</h3>
                <p className="text-[#64748B] font-bold uppercase tracking-widest text-[10px] mt-1">Operational status is clear for Category: {resourceType}</p>
              </div>
              <Button onClick={fetchApprovals} variant="outline" className="rounded-xl font-black text-[10px] uppercase tracking-widest h-10">
                <RefreshCw size={14} className="mr-2" /> Refresh State
              </Button>
            </div>
          )}
        </div>
      )}

      {filteredApprovals.length > 0 && (
        <div className="mt-12 bg-[#F8FAFC] border border-[#E5E7EB] rounded-[32px] p-10">
          <h3 className="text-xl font-black text-[#0F172A] tracking-tight mb-6 uppercase">System Logs & History</h3>
          <div className="divide-y divide-slate-100">
             <p className="py-10 text-center font-bold text-slate-400 uppercase tracking-widest text-[10px]">History data synchronization in progress...</p>
          </div>
        </div>
      )}

      <Dialog open={detailsOpen} onOpenChange={setDetailsOpen}>
        <DialogContent className="max-w-3xl p-0 overflow-hidden rounded-3xl border-none max-h-[90vh] flex flex-col">
          <DialogHeader className="p-6 bg-[#0F172A] text-white">
            <DialogTitle className="text-xl font-black uppercase tracking-tight">
              Approval Details
            </DialogTitle>
            <p className="text-[10px] font-bold uppercase tracking-widest text-white/70">
              Review steps and underlying request data
            </p>
          </DialogHeader>

          <div className="p-6 overflow-y-auto">
            {detailsLoading ? (
              <div className="py-14 flex justify-center">
                <Loader2 className="w-8 h-8 animate-spin text-blue-600" />
              </div>
            ) : !selectedApproval ? (
              <div className="py-10 text-center text-sm text-slate-600">No details loaded.</div>
            ) : (
              <div className="space-y-6">
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                  <Card className="p-4 rounded-2xl border-slate-200">
                    <div className="text-[10px] font-black uppercase tracking-widest text-slate-500">Type</div>
                    <div className="text-sm font-extrabold text-slate-900 mt-1">{selectedApproval.resource_type}</div>
                  </Card>
                  <Card className="p-4 rounded-2xl border-slate-200">
                    <div className="text-[10px] font-black uppercase tracking-widest text-slate-500">Resource ID</div>
                    <div className="text-sm font-extrabold text-slate-900 mt-1">{selectedApproval.resource_id}</div>
                  </Card>
                  <Card className="p-4 rounded-2xl border-slate-200">
                    <div className="text-[10px] font-black uppercase tracking-widest text-slate-500">Status</div>
                    <div className="text-sm font-extrabold text-slate-900 mt-1">{selectedApproval.status}</div>
                  </Card>
                </div>

                {selectedApproval.status === 'pending' && (
                  <div className="space-y-3">
                    {(selectedApproval.resource_type === 'estimate' ||
                      selectedApproval.resource_type === 'estimate_version' ||
                      selectedResource?.resource_type === 'estimate' ||
                      selectedResource?.resource_type === 'estimate_version') && (
                      <Card className="p-4 rounded-2xl border-slate-200">
                        <div className="text-[10px] font-black uppercase tracking-widest text-slate-500">
                          Next approver (optional)
                        </div>
                        <div className="mt-2 flex flex-col sm:flex-row gap-2 sm:items-center">
                          <select
                            value={nextApproverId}
                            onChange={(e) => setNextApproverId(e.target.value)}
                            className="h-10 rounded-xl border border-slate-200 bg-white px-3 text-xs font-bold text-slate-800 outline-none"
                            disabled={estimateApproversLoading}
                          >
                            <option value="">No next approver (final approval)</option>
                            {estimateApprovers.map((u) => (
                              <option key={u.id} value={String(u.id)}>
                                {(u.full_name || u.email || `User #${u.id}`).toString()}
                              </option>
                            ))}
                          </select>
                          {estimateApproversLoading && (
                            <div className="text-xs font-semibold text-slate-500 flex items-center gap-2">
                              <Loader2 size={14} className="animate-spin" /> Loading approvers
                            </div>
                          )}
                        </div>
                        <div className="mt-2 text-[11px] font-semibold text-slate-500">
                          Leave empty to mark the estimate as fully approved.
                        </div>
                      </Card>
                    )}

                    <div className="flex flex-col sm:flex-row gap-3">
                      <Button
                        onClick={() => handleDetailsAction('rejected')}
                        disabled={actionLoading === selectedApproval.id}
                        variant="outline"
                        className="h-11 rounded-xl border-red-200 text-red-700 hover:bg-red-50 font-black text-[10px] uppercase tracking-widest"
                      >
                        Reject
                      </Button>
                      <Button
                        onClick={() => handleDetailsAction('changes_requested')}
                        disabled={actionLoading === selectedApproval.id}
                        variant="outline"
                        className="h-11 rounded-xl border-amber-200 text-amber-700 hover:bg-amber-50 font-black text-[10px] uppercase tracking-widest"
                      >
                        Changes Requested
                      </Button>
                      <Button
                        onClick={() => handleDetailsAction('approved')}
                        disabled={actionLoading === selectedApproval.id}
                        className="h-11 rounded-xl bg-green-600 hover:bg-green-700 font-black text-[10px] uppercase tracking-widest shadow-lg shadow-green-600/20"
                      >
                        {actionLoading === selectedApproval.id ? (
                          <Loader2 size={16} className="animate-spin" />
                        ) : (
                          'Approve'
                        )}
                      </Button>
                    </div>
                  </div>
                )}

                <Card className="p-5 rounded-3xl border-slate-200">
                  <div className="flex items-center justify-between">
                    <h4 className="text-sm font-black uppercase tracking-widest text-slate-900">Approval Steps</h4>
                    <span className="text-xs font-bold text-slate-500">Current step: {selectedApproval.current_step_number}</span>
                  </div>
                  <div className="mt-4 space-y-3">
                    {selectedApproval.steps?.map((s) => (
                      <div key={s.id} className="flex items-start justify-between gap-3 p-3 rounded-2xl bg-slate-50">
                        <div>
                          <div className="text-xs font-extrabold text-slate-900">Step {s.step_number}</div>
                          <div className="text-[11px] font-semibold text-slate-600 mt-0.5">Status: {s.status}</div>
                          {s.comment && (
                            <div className="text-[11px] text-slate-700 mt-1">Comment: {s.comment}</div>
                          )}
                        </div>
                        {s.actioned_at && (
                          <div className="text-[11px] font-semibold text-slate-500 whitespace-nowrap">
                            {new Date(s.actioned_at).toLocaleString()}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </Card>

                <Card className="p-5 rounded-3xl border-slate-200">
                  <h4 className="text-sm font-black uppercase tracking-widest text-slate-900">Request Details</h4>
                  <div className="mt-4">
                    {!selectedResource?.data ? (
                      <div className="text-sm text-slate-600">No resource details available.</div>
                    ) : (selectedResource.resource_type === 'estimate' ||
                        selectedResource.resource_type === 'estimate_version') ? (
                      <div className="space-y-4">
                        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                          <Card className="p-4 rounded-2xl border-slate-200">
                            <div className="text-[10px] font-black uppercase tracking-widest text-slate-500">Version</div>
                            <div className="text-sm font-extrabold text-slate-900 mt-1">#{selectedResource.data.version_number}</div>
                          </Card>
                          <Card className="p-4 rounded-2xl border-slate-200">
                            <div className="text-[10px] font-black uppercase tracking-widest text-slate-500">Estimate Status</div>
                            <div className="text-sm font-extrabold text-slate-900 mt-1">{selectedResource.data.status}</div>
                          </Card>
                          <Card className="p-4 rounded-2xl border-slate-200">
                            <div className="text-[10px] font-black uppercase tracking-widest text-slate-500">Total Cost</div>
                            <div className="text-sm font-extrabold text-slate-900 mt-1">₹ {Number(selectedResource.data.total_cost_decimal || 0).toLocaleString()}</div>
                          </Card>
                        </div>

                        <Card className="p-4 rounded-2xl border-slate-200">
                          <div className="text-[10px] font-black uppercase tracking-widest text-slate-500">Total Price</div>
                          <div className="text-sm font-extrabold text-slate-900 mt-1">₹ {Number(selectedResource.data.total_price_decimal || 0).toLocaleString()}</div>
                        </Card>

                        <div>
                          <div className="text-xs font-black uppercase tracking-widest text-slate-700">Resource Lines</div>
                          <div className="mt-2 overflow-x-auto border border-slate-200 rounded-2xl">
                            <table className="w-full text-xs">
                              <thead className="bg-slate-50 text-slate-600">
                                <tr>
                                  <th className="text-left p-3 font-black uppercase tracking-widest text-[10px]">Role</th>
                                  <th className="text-right p-3 font-black uppercase tracking-widest text-[10px]">Qty</th>
                                  <th className="text-right p-3 font-black uppercase tracking-widest text-[10px]">Hours</th>
                                  <th className="text-right p-3 font-black uppercase tracking-widest text-[10px]">Rate</th>
                                  <th className="text-right p-3 font-black uppercase tracking-widest text-[10px]">Cost</th>
                                </tr>
                              </thead>
                              <tbody>
                                {(selectedResource.data.resource_lines || []).map((rl: any) => (
                                  <tr key={rl.id} className="border-t border-slate-100">
                                    <td className="p-3 font-bold text-slate-800">{rl.role_name}</td>
                                    <td className="p-3 text-right font-semibold text-slate-700">{rl.quantity}</td>
                                    <td className="p-3 text-right font-semibold text-slate-700">{rl.hours}</td>
                                    <td className="p-3 text-right font-semibold text-slate-700">₹ {Number(rl.rate || 0).toLocaleString()}</td>
                                    <td className="p-3 text-right font-bold text-slate-900">₹ {Number(rl.cost_decimal || 0).toLocaleString()}</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        </div>
                      </div>
                    ) : (selectedResource.resource_type === 'leave' || selectedResource.resource_type === 'leave_request') ? (
                      <div className="space-y-3">
                        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                          <Card className="p-4 rounded-2xl border-slate-200">
                            <div className="text-[10px] font-black uppercase tracking-widest text-slate-500">Leave Type</div>
                            <div className="text-sm font-extrabold text-slate-900 mt-1">{selectedResource.data.leave_type?.name || '-'}</div>
                          </Card>
                          <Card className="p-4 rounded-2xl border-slate-200">
                            <div className="text-[10px] font-black uppercase tracking-widest text-slate-500">Dates</div>
                            <div className="text-sm font-extrabold text-slate-900 mt-1">{selectedResource.data.start_date} → {selectedResource.data.end_date}</div>
                          </Card>
                          <Card className="p-4 rounded-2xl border-slate-200">
                            <div className="text-[10px] font-black uppercase tracking-widest text-slate-500">Total Days</div>
                            <div className="text-sm font-extrabold text-slate-900 mt-1">{selectedResource.data.total_days}</div>
                          </Card>
                        </div>
                        <Card className="p-4 rounded-2xl border-slate-200">
                          <div className="text-[10px] font-black uppercase tracking-widest text-slate-500">Reason</div>
                          <div className="text-sm font-semibold text-slate-800 mt-1 whitespace-pre-wrap">{selectedResource.data.reason || '-'}</div>
                        </Card>
                      </div>
                    ) : selectedResource.resource_type === 'comp_off_accrual' ? (
                      <div className="space-y-3">
                        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                          <Card className="p-4 rounded-2xl border-slate-200">
                            <div className="text-[10px] font-black uppercase tracking-widest text-slate-500">Holiday</div>
                            <div className="text-sm font-extrabold text-slate-900 mt-1">{selectedResource.data.holiday_name || '-'}</div>
                            <div className="text-xs text-slate-500 mt-0.5">{selectedResource.data.holiday_date}</div>
                          </Card>
                          <Card className="p-4 rounded-2xl border-slate-200">
                            <div className="text-[10px] font-black uppercase tracking-widest text-slate-500">Hours Worked</div>
                            <div className="text-sm font-extrabold text-slate-900 mt-1">{selectedResource.data.worked_hours_label || '-'}</div>
                          </Card>
                          <Card className="p-4 rounded-2xl border-slate-200">
                            <div className="text-[10px] font-black uppercase tracking-widest text-slate-500">Comp-Off Days</div>
                            <div className="text-sm font-extrabold text-emerald-700 mt-1">+{selectedResource.data.days_credited}</div>
                          </Card>
                        </div>
                        <Card className="p-4 rounded-2xl border-slate-200">
                          <div className="text-[10px] font-black uppercase tracking-widest text-slate-500">Reason</div>
                          <div className="text-sm font-semibold text-slate-800 mt-1 whitespace-pre-wrap">{selectedResource.data.reason || '-'}</div>
                        </Card>
                      </div>
                    ) : (
                      <pre className="text-xs bg-slate-50 border border-slate-200 rounded-2xl p-4 overflow-auto">{JSON.stringify(selectedResource.data, null, 2)}</pre>
                    )}
                  </div>
                </Card>
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};
