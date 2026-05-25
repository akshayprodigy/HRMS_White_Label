import React, { useState, useEffect } from 'react';
import { 
  ArrowLeft, 
  Plus, 
  Save, 
  FileText, 
  Trash2, 
  Send, 
  Archive, 
  PlusCircle, 
  ChevronRight,
  TrendingUp,
  DollarSign,
  Briefcase,
  History,
  Copy,
  LayoutGrid
} from 'lucide-react';
import { Card, Button, Badge, Input, cn } from './ui-elements';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from './ui/dialog';
import { toast } from 'sonner';
import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';

interface EstimatePhase {
  id?: number;
  phase_name: string;
  start_offset_days?: number;
  duration_days: number;
  description?: string;
}

interface EstimateResourceLine {
  id?: number;
  role_name: string;
  quantity: number;
  hours: number;
  rate: number;
  cost_decimal: number;
}

interface UserLink {
  id: number;
  email: string;
  full_name?: string | null;
}

interface EstimateVersion {
  id: number;
  lead_id: number;
  version_number: number;
  name: string;
  status: 'draft' | 'submitted' | 'approved' | 'rejected' | 'archived';
  assumptions?: string;
  scope_included?: string;
  scope_excluded?: string;
  currency: string;
  total_cost_decimal: number;
  contingency_percent: number;
  margin_percent: number;
  total_price_decimal: number;
  created_at: string;
  phases: EstimatePhase[];
  resource_lines: EstimateResourceLine[];
}

interface EstimateCompareResponse {
  version_a: EstimateVersion;
  version_b: EstimateVersion;
  summary_a: any;
  summary_b: any;
}

interface ApprovalStep {
  id: number;
  step_number: number;
  status: string;
  comment?: string;
  approver?: { full_name: string };
  role?: { name: string };
  actioned_at?: string;
}

interface ApprovalItem {
  id: number;
  resource_type: string;
  resource_id: string;
  status: string;
  requested_by_id: number;
  created_at: string;
  steps: ApprovalStep[];
}

interface QuotationVersion {
  id: number;
  estimate_version_id: number;
  version_number: number;
  status: string;
  filename: string;
  mime_type: string;
  sha256: string;
  created_by_id: number;
  created_at: string;
}

type PMSubmissionsSummaryResponse = {
  lead_id: number;
  estimate_version_id: number;
  included_reviews: Array<{
    review_id: number;
    assignment_id: number;
    revision_number: number;
  }>;
  role_totals: Array<{
    role: string;
    hours: number;
    cost: number;
    rate: number;
  }>;
};

const formatMoney = (value: number, currency?: string) => {
  if (!Number.isFinite(value)) return '-';
  const code = currency || 'INR';
  try {
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: code,
      maximumFractionDigits: 2,
    }).format(value);
  } catch {
    return `₹${value.toFixed(2)}`;
  }
};

export const EstimateWorkspace = ({ 
  leadId, 
  onBack, 
  leadTitle,
  onLeadUpdated,
}: { 
  leadId: number, 
  onBack: () => void,
  leadTitle?: string,
  onLeadUpdated?: () => void | Promise<void>,
}) => {
  const [versions, setVersions] = useState<any[]>([]);
  const [selectedVersion, setSelectedVersion] = useState<EstimateVersion | null>(null);
  const [loading, setLoading] = useState(true);
  const [isEditing, setIsEditing] = useState(false);
  const [compareId, setCompareId] = useState<number | null>(null);
  const [compareData, setCompareData] = useState<EstimateCompareResponse | null>(null);
  const [approvals, setApprovals] = useState<ApprovalItem[]>([]);
  const [proposalData, setProposalData] = useState<any | null>(null);
  const [quotations, setQuotations] = useState<QuotationVersion[]>([]);
  const [quotationsLoading, setQuotationsLoading] = useState(false);
  const [quotationGenerating, setQuotationGenerating] = useState(false);

  const [pmApplyOpen, setPmApplyOpen] = useState(false);
  const [pmApplyLoading, setPmApplyLoading] = useState(false);
  const [pmApplyApplying, setPmApplyApplying] = useState(false);
  const [pmApplySummary, setPmApplySummary] = useState<PMSubmissionsSummaryResponse | null>(null);

  const moveLeadToStage = async (stage: string) => {
    try {
      await client.patch(ENDPOINTS.BD.LEAD_DETAIL(leadId), { stage });
      toast.success(`Lead moved to ${String(stage).toUpperCase()}`);
      await onLeadUpdated?.();
    } catch (error: any) {
      console.error('Failed to move lead stage', error);
      const msg =
        error?.response?.data?.error?.message ||
        error?.response?.data?.detail ||
        'Failed to update lead stage';
      toast.error(msg);
    }
  };

  const [newVersionOpen, setNewVersionOpen] = useState(false);
  const [newVersionName, setNewVersionName] = useState('');
  const [newVersionSaving, setNewVersionSaving] = useState(false);

  const [submitOpen, setSubmitOpen] = useState(false);
  const [submitApprovers, setSubmitApprovers] = useState<UserLink[]>([]);
  const [submitApproversLoading, setSubmitApproversLoading] = useState(false);
  const [submitApproverId, setSubmitApproverId] = useState<string>('');
  const [submitSaving, setSubmitSaving] = useState(false);

  useEffect(() => {
    fetchVersions();
    fetchApprovals();
  }, [leadId]);

  useEffect(() => {
    if (!selectedVersion?.id) {
      setQuotations([]);
      return;
    }
    fetchQuotations(selectedVersion.id);
  }, [selectedVersion?.id]);

  const loadPmSubmissionsSummary = async (estimateVersionId: number) => {
    setPmApplyLoading(true);
    setPmApplySummary(null);
    try {
      const res = await client.get<PMSubmissionsSummaryResponse>(
        ENDPOINTS.BD.BID_TASKS.PM_SUBMISSIONS_SUMMARY(leadId, estimateVersionId),
      );
      setPmApplySummary((res.data as any) || null);
    } catch (error: any) {
      console.error('Failed to load PM submissions summary', error);
      const msg =
        error?.response?.data?.error?.message ||
        error?.response?.data?.detail ||
        'Failed to load PM submissions summary';
      toast.error(msg);
      setPmApplyOpen(false);
    } finally {
      setPmApplyLoading(false);
    }
  };

  const openPmSubmissions = async () => {
    if (!selectedVersion?.id) {
      toast.error('Select an estimate version first');
      return;
    }
    setPmApplyOpen(true);
    await loadPmSubmissionsSummary(selectedVersion.id);
  };

  const applyPmSubmissions = async () => {
    if (!selectedVersion?.id) {
      toast.error('Select an estimate version first');
      return;
    }
    if (selectedVersion.status !== 'draft') {
      toast.error('You can only apply PM submissions to a draft estimate version');
      return;
    }

    setPmApplyApplying(true);
    try {
      await client.post(
        ENDPOINTS.BD.BID_TASKS.APPLY_PM_SUBMISSIONS(leadId, selectedVersion.id),
      );
      toast.success('Applied PM submissions to estimate', {
        action: {
          label: 'Move to Proposal',
          onClick: () => moveLeadToStage('proposal'),
        },
      });
      setPmApplyOpen(false);
      await Promise.all([fetchVersions(), fetchVersionDetail(selectedVersion.id)]);
    } catch (error: any) {
      console.error('Failed to apply PM submissions', error);
      const msg =
        error?.response?.data?.error?.message ||
        error?.response?.data?.detail ||
        'Failed to apply PM submissions';
      toast.error(msg);
    } finally {
      setPmApplyApplying(false);
    }
  };

  const fetchApprovals = async () => {
    try {
      const res = await client.get<ApprovalItem[]>(ENDPOINTS.BD.LEAD_ESTIMATE_APPROVALS(leadId));
      setApprovals((res.data as any) || []);
    } catch (error) {
      console.error('Failed to load approvals');
    }
  };

  const fetchVersions = async () => {
    try {
      setLoading(true);
      const res = await client.get<any[]>(ENDPOINTS.BD.LEAD_ESTIMATES(leadId));
      const items = (res.data as any) || [];
      setVersions(items);
      if (items && items.length > 0 && !selectedVersion) {
        fetchVersionDetail(items[0].id);
      }
    } catch (error) {
      toast.error('Failed to load estimates');
    } finally {
      setLoading(false);
    }
  };

  const fetchVersionDetail = async (id: number) => {
    try {
      const res = await client.get<EstimateVersion>(ENDPOINTS.BD.ESTIMATE_DETAIL(id));
      setSelectedVersion(res.data as any);
      setIsEditing(false);
      setCompareData(null);
    } catch (error) {
      toast.error('Failed to load version details');
    }
  };

  const fetchQuotations = async (estimateVersionId: number) => {
    setQuotationsLoading(true);
    try {
      const res = await client.get<QuotationVersion[]>(
        ENDPOINTS.BD.ESTIMATE_QUOTATIONS(estimateVersionId)
      );
      setQuotations((res.data as any) || []);
    } catch (error) {
      setQuotations([]);
    } finally {
      setQuotationsLoading(false);
    }
  };

  const openNewVersionDialog = () => {
    const suggested = `Revision ${versions.length + 1}`;
    setNewVersionName(suggested);
    setNewVersionOpen(true);
  };

  const createNewVersion = async () => {
    const name = newVersionName.trim();
    if (!name) {
      toast.error('Version name is required');
      return;
    }

    setNewVersionSaving(true);
    try {
      const payload = selectedVersion
        ? {
            name,
            assumptions: selectedVersion.assumptions,
            scope_included: selectedVersion.scope_included,
            scope_excluded: selectedVersion.scope_excluded,
            currency: selectedVersion.currency,
            contingency_percent: selectedVersion.contingency_percent,
            margin_percent: selectedVersion.margin_percent,
            phases: selectedVersion.phases.map(({ id, ...p }) => p),
            resource_lines: selectedVersion.resource_lines.map(({ id, ...r }) => r),
          }
        : { name };

      const res = await client.post<EstimateVersion>(
        ENDPOINTS.BD.LEAD_ESTIMATES(leadId),
        payload,
      );
      const created = res.data as any;
      toast.success('New version created');
      setNewVersionOpen(false);
      await fetchVersions();
      if (created?.id) {
        await fetchVersionDetail(created.id);
      }
    } catch (error) {
      toast.error('Failed to create version');
    } finally {
      setNewVersionSaving(false);
    }
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedVersion) return;

    try {
      const { id, version_number, status, created_at, ...updateData } = selectedVersion;
      await client.patch(ENDPOINTS.BD.ESTIMATE_DETAIL(id), updateData);
      toast.success('Estimate saved successfully');
      setIsEditing(false);
      fetchVersionDetail(id);
    } catch (error) {
      toast.error('Failed to save estimate');
    }
  };

  const handleSubmit = async () => {
    if (!selectedVersion) return;
    setSubmitOpen(true);
    setSubmitApproverId('');
    setSubmitApprovers([]);
    setSubmitApproversLoading(true);
    try {
      const res = await client.get<UserLink[]>(ENDPOINTS.BD.ESTIMATE_APPROVERS);
      setSubmitApprovers(Array.isArray((res as any).data) ? ((res as any).data as any) : []);
    } catch (error: any) {
      const msg =
        error?.response?.data?.error?.message ||
        error?.response?.data?.detail ||
        'Failed to load approvers';
      toast.error(msg);
      setSubmitOpen(false);
    } finally {
      setSubmitApproversLoading(false);
    }
  };

  const confirmSubmit = async () => {
    if (!selectedVersion) return;
    if (!submitApproverId) {
      toast.error('Select an approver');
      return;
    }
    setSubmitSaving(true);
    try {
      await client.post(ENDPOINTS.BD.ESTIMATE_SUBMIT(selectedVersion.id), {
        approver_id: Number(submitApproverId),
      });
      toast.success('Submitted for approval', {
        description:
          'The selected approver will review it in the Approvals Center. After the final approval, the estimate status becomes approved.',
        action: {
          label: 'Open Approvals',
          onClick: () => {
            window.dispatchEvent(
              new CustomEvent('erp:navigate', { detail: { tab: 'approvals' } })
            );
          },
        },
      });
      setSubmitOpen(false);
      await fetchVersionDetail(selectedVersion.id);
      await fetchApprovals();
    } catch (error: any) {
      const msg =
        error?.response?.data?.error?.message ||
        error?.response?.data?.detail ||
        'Failed to submit estimate';
      toast.error(msg);
    } finally {
      setSubmitSaving(false);
    }
  };

  const handleCompare = async (otherId: number) => {
    if (!selectedVersion) return;
    try {
      const res = await client.get<EstimateCompareResponse>(ENDPOINTS.BD.ESTIMATE_COMPARE(selectedVersion.id, otherId));
      setCompareData(res.data as any);
    } catch (error) {
      toast.error('Failed to compare versions');
    }
  };
  const handleGenerateProposal = async () => {
    if (!selectedVersion) return;
    try {
      const res = await client.post<any>(ENDPOINTS.BD.ESTIMATE_GENERATE_PROPOSAL(selectedVersion.id), {});
      setProposalData((res.data as any)?.snapshot_data);
      toast.success('Proposal snapshot generated', {
        action: {
          label: 'Move to Proposal',
          onClick: () => moveLeadToStage('proposal'),
        },
      });
    } catch (error) {
      toast.error('Failed to generate proposal');
    }
  };

  const downloadQuotationPdf = async (quotationId: number, fallbackName?: string) => {
    const res = await client.get(
      ENDPOINTS.BD.QUOTATION_PDF(quotationId),
      { responseType: 'blob' }
    );
    const blob = new Blob([res.data], { type: 'application/pdf' });
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = fallbackName || `quotation_${quotationId}.pdf`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);
  };

  const handleGenerateQuotation = async () => {
    if (!selectedVersion) return;
    setQuotationGenerating(true);
    try {
      const res = await client.post<QuotationVersion>(
        ENDPOINTS.BD.ESTIMATE_QUOTATIONS(selectedVersion.id),
        {}
      );
      const q = res.data as any;
      toast.success('Quotation PDF generated');
      await fetchQuotations(selectedVersion.id);
      await downloadQuotationPdf(q.id, q.filename);
    } catch (error: any) {
      toast.error(error?.response?.data?.error?.message || 'Failed to generate quotation');
    } finally {
      setQuotationGenerating(false);
    }
  };
  const addResourceLine = () => {
    if (!selectedVersion) return;
    const newLine: EstimateResourceLine = { role_name: 'New Role', quantity: 1, hours: 0, rate: 0, cost_decimal: 0 };
    setSelectedVersion({
      ...selectedVersion,
      resource_lines: [...selectedVersion.resource_lines, newLine]
    });
  };

  const updateResourceLine = (index: number, field: string, value: any) => {
    if (!selectedVersion) return;
    const lines = [...selectedVersion.resource_lines];
    lines[index] = { ...lines[index], [field]: value };
    
    // Auto calculate line cost
    if (field === 'hours' || field === 'rate' || field === 'quantity') {
      const l = lines[index];
      l.cost_decimal = l.quantity * l.hours * l.rate;
    }
    
    setSelectedVersion({ ...selectedVersion, resource_lines: lines });
  };

  const addPhase = () => {
    if (!selectedVersion) return;
    const newPhase: EstimatePhase = { phase_name: 'New Phase', duration_days: 0 };
    setSelectedVersion({
      ...selectedVersion,
      phases: [...selectedVersion.phases, newPhase]
    });
  };

  const updatePhase = (index: number, field: string, value: any) => {
    if (!selectedVersion) return;
    const phases = [...selectedVersion.phases];
    phases[index] = { ...phases[index], [field]: value };
    setSelectedVersion({ ...selectedVersion, phases });
  };

  if (loading) {
    return (
      <div className="p-12 flex flex-col items-center justify-center">
        <div className="w-10 h-10 border-4 border-indigo-600 border-t-transparent rounded-full animate-spin mb-4" />
        <p className="text-slate-500">Loading workspace...</p>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6 max-w-[1400px] mx-auto animate-in fade-in duration-500">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <button onClick={onBack} className="p-2 bg-white rounded-lg border border-slate-200 hover:text-indigo-600 transition-all">
            <ArrowLeft className="w-5 h-5" />
          </button>
          <div>
            <h1 className="text-2xl font-bold text-slate-900">Estimate Workspace</h1>
            <p className="text-slate-500 text-sm">{leadTitle || "Lead Estimates"}</p>
          </div>
        </div>
        <div className="flex gap-3">
          {selectedVersion?.status === 'draft' && (
            <>
              {isEditing ? (
                <Button onClick={handleSave} className="bg-green-600 hover:bg-green-700 text-white">
                  <Save className="w-4 h-4 mr-2" />
                  Save Changes
                </Button>
              ) : (
                <Button onClick={() => setIsEditing(true)} variant="outline">
                  Edit Version
                </Button>
              )}
              <Button onClick={handleSubmit} className="bg-indigo-600 text-white">
                <Send className="w-4 h-4 mr-2" />
                Submit for Approval
              </Button>
            </>
          )}
          {selectedVersion && (
            <Button
              onClick={openPmSubmissions}
              variant="outline"
              className="border-slate-200 text-slate-800"
            >
              <LayoutGrid className="w-4 h-4 mr-2" />
              PM Submissions
            </Button>
          )}
          <Button onClick={openNewVersionDialog} variant="outline" className="border-indigo-200 text-indigo-700">
            <PlusCircle className="w-4 h-4 mr-2" />
            New Version
          </Button>
          {selectedVersion && (
            <Button onClick={handleGenerateProposal} className="bg-slate-900 text-white">
              <FileText className="w-4 h-4 mr-2" />
              Preview Proposal
            </Button>
          )}
          {selectedVersion && (
            <>
              <Button
                onClick={handleGenerateQuotation}
                disabled={quotationGenerating}
                variant="outline"
              >
                <FileText className="w-4 h-4 mr-2" />
                {quotationGenerating ? 'Generating PDF…' : 'Generate Quotation PDF'}
              </Button>
              {quotations.length > 0 && (
                <Button
                  onClick={() => downloadQuotationPdf(quotations[0].id, quotations[0].filename)}
                  variant="outline"
                >
                  Download Latest PDF
                </Button>
              )}
            </>
          )}
        </div>
      </div>

      <Dialog
        open={newVersionOpen}
        onOpenChange={(open: boolean) => {
          setNewVersionOpen(open);
          if (!open) {
            setNewVersionSaving(false);
          }
        }}
      >
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Create New Version</DialogTitle>
            <DialogDescription>
              Enter a version name. This copies the current version’s phases and resource lines as a starting point.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-2">
            <label className="text-sm font-medium text-slate-700">Version name</label>
            <Input
              autoFocus
              value={newVersionName}
              onChange={(e) => setNewVersionName(e.target.value)}
              placeholder={`Revision ${versions.length + 1}`}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault();
                  if (!newVersionSaving) createNewVersion();
                }
              }}
            />
          </div>

          <div className="flex justify-end gap-2">
            <Button
              variant="outline"
              onClick={() => setNewVersionOpen(false)}
              disabled={newVersionSaving}
            >
              Cancel
            </Button>
            <Button
              className="bg-indigo-600 hover:bg-indigo-700 text-white"
              onClick={createNewVersion}
              disabled={newVersionSaving || !newVersionName.trim()}
            >
              {newVersionSaving ? 'Creating…' : 'Create Version'}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog
        open={submitOpen}
        onOpenChange={(open: boolean) => {
          setSubmitOpen(open);
          if (!open) {
            setSubmitSaving(false);
            setSubmitApproversLoading(false);
          }
        }}
      >
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Send for Approval</DialogTitle>
            <DialogDescription>
              Select the first approver. They can optionally assign the next approver when approving. If no next approver is assigned,
              their approval finalizes the estimate as approved.
            </DialogDescription>
          </DialogHeader>

          {submitApproversLoading ? (
            <div className="py-8 flex flex-col items-center justify-center text-slate-400">
              <div className="w-8 h-8 border-4 border-indigo-600 border-t-transparent rounded-full animate-spin mb-3" />
              <p className="text-sm">Loading approvers…</p>
            </div>
          ) : (
            <div className="space-y-2">
              <label className="text-sm font-medium text-slate-700">Approver</label>
              <select
                value={submitApproverId}
                onChange={(e) => setSubmitApproverId(e.target.value)}
                className="w-full h-10 rounded-xl border border-slate-200 px-3 text-sm font-semibold text-slate-800 bg-white"
              >
                <option value="">Select an approver…</option>
                {submitApprovers.map((u) => (
                  <option key={u.id} value={String(u.id)}>
                    {u.full_name || u.email}
                  </option>
                ))}
              </select>
              {submitApprovers.length === 0 && (
                <p className="text-xs text-slate-500">
                  No eligible approvers found. Assign the “Lead Estimate Approver” role (or permission) to users.
                </p>
              )}
            </div>
          )}

          <div className="flex justify-end gap-2">
            <Button
              variant="outline"
              onClick={() => setSubmitOpen(false)}
              disabled={submitSaving}
            >
              Cancel
            </Button>
            <Button
              className="bg-indigo-600 hover:bg-indigo-700 text-white"
              onClick={confirmSubmit}
              disabled={submitSaving || submitApproversLoading || !submitApproverId}
            >
              {submitSaving ? 'Submitting…' : 'Submit'}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog
        open={pmApplyOpen}
        onOpenChange={(open: boolean) => {
          setPmApplyOpen(open);
          if (!open) {
            setPmApplyLoading(false);
            setPmApplyApplying(false);
            setPmApplySummary(null);
          }
        }}
      >
        <DialogContent className="sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>PM Submissions</DialogTitle>
            <DialogDescription>
              Preview the latest submitted PM revisions for this estimate version and apply them to replace the resource lines.
            </DialogDescription>
          </DialogHeader>

          {pmApplyLoading ? (
            <div className="py-10 flex flex-col items-center justify-center text-slate-400">
              <div className="w-8 h-8 border-4 border-indigo-600 border-t-transparent rounded-full animate-spin mb-3" />
              <p className="text-sm">Loading summary…</p>
            </div>
          ) : !pmApplySummary ? (
            <div className="py-6 text-sm text-slate-500">Summary not available.</div>
          ) : (
            <div className="space-y-4">
              <div className="p-3 rounded-xl border border-slate-100 bg-slate-50 text-sm text-slate-700">
                Apply uses the latest submitted PM reviews at the moment you click it. This will replace the resource lines for the
                selected estimate version.
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div className="p-3 rounded-xl bg-white border border-slate-200">
                  <p className="text-[11px] text-slate-500">Submitted reviews included</p>
                  <p className="text-sm font-bold text-slate-900">{pmApplySummary.included_reviews.length}</p>
                </div>
                <div className="p-3 rounded-xl bg-white border border-slate-200">
                  <p className="text-[11px] text-slate-500">Roles</p>
                  <p className="text-sm font-bold text-slate-900">{pmApplySummary.role_totals.length}</p>
                </div>
                <div className="p-3 rounded-xl bg-white border border-slate-200">
                  <p className="text-[11px] text-slate-500">Estimate version</p>
                  <p className="text-sm font-bold text-slate-900">V{selectedVersion?.version_number}</p>
                </div>
              </div>

              {pmApplySummary.included_reviews.length > 0 && (
                <div className="border border-slate-200 rounded-xl overflow-hidden">
                  <div className="px-4 py-2 bg-slate-50 text-[11px] font-bold text-slate-600">
                    Included revisions
                  </div>
                  <div className="max-h-40 overflow-y-auto">
                    {pmApplySummary.included_reviews.map((r) => (
                      <div
                        key={r.review_id}
                        className="grid grid-cols-12 gap-2 px-4 py-2 border-t border-slate-100 text-sm"
                      >
                        <div className="col-span-4 text-slate-700">Assignment #{r.assignment_id}</div>
                        <div className="col-span-4 text-slate-700">Review #{r.review_id}</div>
                        <div className="col-span-4 font-semibold text-slate-900">Revision #{r.revision_number}</div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {pmApplySummary.included_reviews.length === 0 ? (
                <div className="p-4 rounded-xl border border-dashed border-slate-200 text-sm text-slate-500">
                  No submitted PM reviews found for this estimate version.
                </div>
              ) : pmApplySummary.role_totals.length === 0 ? (
                <div className="p-4 rounded-xl border border-dashed border-slate-200 text-sm text-slate-500">
                  No role totals found.
                </div>
              ) : (
                <div className="border border-slate-200 rounded-xl overflow-hidden">
                  <div className="grid grid-cols-12 gap-2 px-4 py-2 bg-slate-50 text-[11px] font-bold text-slate-600">
                    <div className="col-span-4">Role</div>
                    <div className="col-span-3">Hours</div>
                    <div className="col-span-2">Rate</div>
                    <div className="col-span-3">Cost</div>
                  </div>
                  {pmApplySummary.role_totals.map((r) => (
                    <div key={r.role} className="grid grid-cols-12 gap-2 px-4 py-3 border-t border-slate-100">
                      <div className="col-span-4 text-sm font-semibold text-slate-900">{r.role}</div>
                      <div className="col-span-3 text-sm text-slate-700">{Number(r.hours || 0).toFixed(2)}</div>
                      <div className="col-span-2 text-sm text-slate-700">{Number(r.rate || 0).toFixed(2)}</div>
                      <div className="col-span-3 text-sm text-slate-700">
                        {formatMoney(Number(r.cost || 0), selectedVersion?.currency)}
                      </div>
                    </div>
                  ))}
                </div>
              )}

              <div className="flex items-center justify-between gap-2">
                <Button
                  variant="outline"
                  onClick={() => selectedVersion?.id && loadPmSubmissionsSummary(selectedVersion.id)}
                  disabled={pmApplyApplying || pmApplyLoading}
                >
                  Refresh
                </Button>
                <div className="flex justify-end gap-2">
                  <Button variant="outline" onClick={() => setPmApplyOpen(false)} disabled={pmApplyApplying}>
                    Close
                  </Button>
                  <Button
                    className="bg-indigo-600 hover:bg-indigo-700 text-white"
                    onClick={applyPmSubmissions}
                    disabled={
                      pmApplyApplying ||
                      pmApplySummary.included_reviews.length === 0 ||
                      selectedVersion?.status !== 'draft'
                    }
                  >
                    {selectedVersion?.status !== 'draft'
                      ? 'Apply (draft only)'
                      : pmApplyApplying
                        ? 'Applying…'
                        : 'Apply to Estimate'}
                  </Button>
                </div>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        {/* Left Sidebar: Versions */}
        <Card className="p-4 h-fit space-y-4">
          <h3 className="font-bold text-slate-900 border-b pb-2 flex items-center justify-between">
            Versions
            <Badge variant="neutral">{versions.length}</Badge>
          </h3>
          <div className="space-y-2">
            {versions.map(v => (
              <button
                key={v.id}
                onClick={() => fetchVersionDetail(v.id)}
                className={cn(
                  "w-full text-left p-3 rounded-lg border transition-all relative group",
                  selectedVersion?.id === v.id 
                    ? "bg-indigo-50 border-indigo-200 ring-1 ring-indigo-100" 
                    : "bg-white border-slate-100 hover:border-indigo-200"
                )}
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs font-black text-indigo-600 uppercase tracking-tighter">V{v.version_number}</span>
                  <Badge variant={v.status === 'draft' ? 'warning' : v.status === 'submitted' ? 'info' : 'success'} className="scale-[0.8] origin-right">
                    {v.status}
                  </Badge>
                </div>
                <p className="text-sm font-bold text-slate-900 line-clamp-1">{v.name}</p>
                <p className="text-[10px] text-slate-400 mt-1">{new Date(v.created_at).toLocaleDateString()}</p>
                
                {selectedVersion?.id !== v.id && (
                  <div 
                    onClick={(e) => { e.stopPropagation(); handleCompare(v.id); }}
                    className="absolute right-2 bottom-2 hidden group-hover:block p-1 bg-indigo-600 text-white rounded cursor-pointer"
                    title="Compare with selected"
                  >
                    <Copy className="w-3 h-3" />
                  </div>
                )}
              </button>
            ))}
          </div>
        </Card>

        {/* Main Workspace */}
        <div className="lg:col-span-3 space-y-6">
          {compareData ? (
            <div className="animate-in zoom-in-95 duration-300">
              <div className="bg-indigo-900 text-white p-4 rounded-t-xl flex justify-between items-center">
                <span className="font-bold flex items-center gap-2">
                  <Copy className="w-5 h-5" />
                  Comparison View
                </span>
                <Button size="sm" variant="ghost" className="text-white hover:bg-white/10" onClick={() => setCompareData(null)}>
                  Close
                </Button>
              </div>
              <div className="grid grid-cols-2 gap-px bg-slate-200 border-x border-b border-slate-200 rounded-b-xl overflow-hidden">
                {[compareData.version_a, compareData.version_b].map((v, idx) => (
                  <div key={v.id} className="bg-white p-6 space-y-4">
                    <div className="border-b pb-4">
                      <p className="text-xs font-bold text-indigo-600 mb-1">VERSION {v.version_number}</p>
                      <h4 className="text-lg font-bold text-slate-900">{v.name}</h4>
                    </div>
                    <div className="space-y-3">
                      <div className="flex justify-between items-center bg-slate-50 p-3 rounded-lg">
                        <span className="text-sm text-slate-500">Total Price</span>
                        <span className="text-lg font-black text-slate-900">{formatMoney(v.total_price_decimal, v.currency)}</span>
                      </div>
                      <div className="flex justify-between items-center border-b border-slate-50 py-2">
                        <span className="text-sm text-slate-500">Margin</span>
                        <span className="font-bold text-slate-900">{v.margin_percent}%</span>
                      </div>
                      <div className="flex justify-between items-center border-b border-slate-50 py-2">
                        <span className="text-sm text-slate-500">Resources</span>
                        <span className="font-bold text-slate-900">{v.resource_lines.length}</span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : selectedVersion ? (
            <>
              {/* Summary Bar */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <Card className="p-4 flex items-center gap-4 bg-indigo-600 text-white border-none">
                  <div className="p-2 bg-white/10 rounded-lg">
                    <TrendingUp className="w-6 h-6" />
                  </div>
                  <div>
                    <p className="text-xs text-indigo-100 uppercase font-bold tracking-wider">Total Price</p>
                    <p className="text-2xl font-black">{formatMoney(selectedVersion.total_price_decimal, selectedVersion.currency)}</p>
                  </div>
                </Card>
                <Card className="p-4 flex items-center gap-4">
                  <div className="p-2 bg-slate-100 rounded-lg">
                    <History className="w-6 h-6 text-slate-600" />
                  </div>
                  <div>
                    <p className="text-xs text-slate-500 uppercase font-bold tracking-wider">Total Cost</p>
                    <p className="text-2xl font-bold text-slate-900">{formatMoney(selectedVersion.total_cost_decimal, selectedVersion.currency)}</p>
                  </div>
                </Card>
                <Card className="p-4 flex items-center gap-4">
                  <div className="p-2 bg-green-50 rounded-lg">
                    <DollarSign className="w-6 h-6 text-green-600" />
                  </div>
                  <div>
                    <p className="text-xs text-slate-500 uppercase font-bold tracking-wider">Gross Margin</p>
                    <div className="flex items-center gap-2">
                      <p className="text-2xl font-bold text-slate-900">
                        {selectedVersion.margin_percent}%
                      </p>
                    </div>
                  </div>
                </Card>
              </div>

              {proposalData && (
                <Card className="p-8 bg-white border-2 border-slate-900 shadow-2xl relative animate-in zoom-in-95 duration-300">
                  <button 
                    onClick={() => setProposalData(null)}
                    className="absolute top-4 right-4 p-2 hover:bg-slate-100 rounded-full"
                  >
                    <Plus className="w-5 h-5 rotate-45" />
                  </button>
                  
                  <div className="max-w-[800px] mx-auto space-y-8">
                    <div className="border-b-4 border-slate-900 pb-8 flex justify-between items-end">
                      <div>
                        <h2 className="text-4xl font-black text-slate-900 uppercase tracking-tighter">Project Proposal</h2>
                        <p className="text-slate-500 font-bold">{proposalData.proposal_info.version_name} (V{proposalData.proposal_info.version_number})</p>
                      </div>
                      <div className="text-right">
                        <p className="text-xs font-black text-slate-400 uppercase">Generated</p>
                        <p className="font-bold text-slate-900">{new Date(proposalData.proposal_info.generated_at).toLocaleDateString()}</p>
                      </div>
                    </div>

                    <div className="grid grid-cols-2 gap-12">
                      <div className="space-y-4">
                        <h4 className="text-xs font-black text-indigo-600 uppercase tracking-widest px-2 py-1 bg-indigo-50 w-fit rounded">Client Info</h4>
                        <div className="space-y-1">
                          <p className="text-2xl font-bold text-slate-900">{proposalData.lead_info.account}</p>
                          <p className="text-slate-500 font-medium">Attn: {proposalData.lead_info.contact}</p>
                        </div>
                      </div>
                      <div className="space-y-4">
                        <h4 className="text-xs font-black text-green-600 uppercase tracking-widest px-2 py-1 bg-green-50 w-fit rounded">Investment</h4>
                        <div className="space-y-1">
                          <p className="text-4xl font-black text-slate-900">
                            {formatMoney(proposalData.financial_summary.total_price, proposalData.financial_summary.currency)}
                          </p>
                        </div>
                      </div>
                    </div>

                    <div className="space-y-4">
                      <h4 className="text-xs font-black text-slate-900 uppercase tracking-widest border-b pb-2">Included Scope</h4>
                      <p className="text-slate-700 whitespace-pre-wrap leading-relaxed">{proposalData.scope.included || "No scope defined."}</p>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                      <div className="space-y-4">
                        <h4 className="text-xs font-black text-slate-900 uppercase tracking-widest border-b pb-2">Phases</h4>
                        <div className="space-y-3">
                          {proposalData.phases.map((p: any, idx: number) => (
                            <div key={idx} className="flex justify-between items-start">
                              <div>
                                <p className="font-bold text-slate-900">{p.name}</p>
                                <p className="text-xs text-slate-500 line-clamp-1">{p.description}</p>
                              </div>
                              <Badge variant="neutral" className="text-[10px]">{p.duration} days</Badge>
                            </div>
                          ))}
                        </div>
                      </div>
                      <div className="space-y-4">
                        <h4 className="text-xs font-black text-slate-900 uppercase tracking-widest border-b pb-2">Exclusions & Assumptions</h4>
                        <div className="space-y-4">
                          <div>
                            <p className="text-[10px] font-black text-slate-400 uppercase mb-1">Exclusions</p>
                            <p className="text-xs text-slate-600 italic">{proposalData.scope.excluded || "N/A"}</p>
                          </div>
                          <div>
                            <p className="text-[10px] font-black text-slate-400 uppercase mb-1">Key Assumptions</p>
                            <p className="text-xs text-slate-600 italic">{proposalData.scope.assumptions || "N/A"}</p>
                          </div>
                        </div>
                      </div>
                    </div>

                    <div className="pt-12 mt-12 border-t border-slate-100 flex justify-between items-center opacity-50">
                      <p className="text-[10px] font-bold text-slate-400 uppercase">Enterprise ERP System - Confidential Proposal</p>
                      <p className="text-[10px] font-bold text-slate-400 uppercase">By {proposalData.proposal_info.generated_by}</p>
                    </div>
                  </div>
                </Card>
              )}

              <Card className="p-4">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-bold text-slate-900">Quotation PDFs</p>
                    <p className="text-xs text-slate-500">Versioned downloads for this estimate</p>
                  </div>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={handleGenerateQuotation}
                    disabled={quotationGenerating}
                  >
                    {quotationGenerating ? 'Generating…' : 'Generate'}
                  </Button>
                </div>
                <div className="mt-3 space-y-2">
                  {quotationsLoading ? (
                    <p className="text-xs text-slate-400">Loading quotation versions…</p>
                  ) : quotations.length === 0 ? (
                    <p className="text-xs text-slate-400">No quotation PDFs generated yet.</p>
                  ) : (
                    quotations.slice(0, 5).map((q) => (
                      <div key={q.id} className="flex items-center justify-between text-sm border rounded-lg px-3 py-2">
                        <div className="min-w-0">
                          <p className="font-semibold text-slate-900 truncate">Q{q.version_number} • {q.status}</p>
                          <p className="text-[11px] text-slate-500 truncate">{new Date(q.created_at).toLocaleString()}</p>
                        </div>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => downloadQuotationPdf(q.id, q.filename)}
                        >
                          Download
                        </Button>
                      </div>
                    ))
                  )}
                </div>
              </Card>

              {/* Approval status */}
              <Card className="p-4 border-l-4 border-l-indigo-500 bg-indigo-50/30">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <div className="p-2 bg-white rounded-full text-indigo-600 shadow-sm border border-indigo-100">
                        <History className="w-5 h-5" />
                      </div>
                      <div>
                        <p className="text-xs font-black text-indigo-600 uppercase tracking-widest">Approval Workflow</p>
                        <p className="text-slate-600 text-sm">
                          {selectedVersion.status === 'draft'
                            ? 'Not submitted yet'
                            : approvals.find((a: any) => a.resource_id === String(selectedVersion.id))?.status === 'pending'
                              ? 'Currently under review'
                              : `Final Status: ${selectedVersion.status.split('_').join(' ').toUpperCase()}`}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      {selectedVersion.status === 'draft' && (
                        <Button
                          size="sm"
                          onClick={handleSubmit}
                          className="bg-indigo-600 hover:bg-indigo-700 text-white"
                        >
                          <Send className="w-4 h-4 mr-2" />
                          Submit
                        </Button>
                      )}
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => {
                          window.dispatchEvent(
                            new CustomEvent('erp:navigate', { detail: { tab: 'approvals' } })
                          );
                        }}
                      >
                        Open Approvals Center
                      </Button>
                    </div>
                  </div>
                  
                  {/* Steps visualization */}
                  {approvals.find((a: any) => a.resource_id === String(selectedVersion.id))?.steps && (
                    <div className="mt-4 flex gap-4 overflow-x-auto pb-2">
                       {approvals.find((a: any) => a.resource_id === String(selectedVersion.id))?.steps?.map((step: any, idx: number) => (
                         <div key={idx} className="flex-shrink-0 flex items-center gap-2">
                            <div className={cn(
                              "w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold border-2",
                              step.status === 'approved' ? "bg-green-100 border-green-500 text-green-700" :
                              step.status === 'rejected' ? "bg-red-100 border-red-500 text-red-700" :
                              "bg-white border-slate-300 text-slate-400"
                            )}>
                              {step.step_number}
                            </div>
                            <div className="text-[10px]">
                              <p className="font-bold text-slate-700 uppercase">{step.role?.name || 'Approver'}</p>
                              <p className={cn(
                                "capitalize",
                                step.status === 'approved' ? "text-green-600" :
                                step.status === 'rejected' ? "text-red-600" : "text-slate-400"
                              )}>{step.status}</p>
                            </div>
                            {idx < ((approvals.find((a: any) => a.resource_id === String(selectedVersion.id))?.steps?.length || 0) - 1) && (
                              <ChevronRight className="w-4 h-4 text-slate-300 ml-2" />
                            )}
                         </div>
                       ))}
                    </div>
                  )}
              </Card>

              {/* Tabs / Content */}
              <div className="space-y-6">
                <Card className="p-6">
                  <div className="flex items-center justify-between mb-6 border-b pb-4">
                    <h3 className="font-bold text-slate-900 flex items-center gap-2 text-lg">
                      <Briefcase className="w-5 h-5 text-indigo-600" />
                      Resource Lines
                    </h3>
                    {isEditing && (
                      <Button size="sm" variant="outline" onClick={addResourceLine}>
                        <Plus className="w-4 h-4 mr-2" />
                        Add Role
                      </Button>
                    )}
                  </div>
                  
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead className="text-slate-500 uppercase text-[10px] font-black tracking-widest border-b">
                        <tr>
                          <th className="text-left pb-3 px-2">Role/Skill</th>
                          <th className="text-center pb-3 px-2">Qty</th>
                          <th className="text-center pb-3 px-2">Hours</th>
                          <th className="text-center pb-3 px-2">Rate/Hr</th>
                          <th className="text-right pb-3 px-2">Total Cost</th>
                          <th className="w-10 pb-3"></th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-50">
                        {selectedVersion.resource_lines.map((line, idx) => (
                          <tr key={idx} className="group hover:bg-slate-50/50">
                            <td className="py-3 px-2">
                              {isEditing ? (
                                <Input 
                                  value={line.role_name} 
                                  onChange={(e) => updateResourceLine(idx, 'role_name', e.target.value)}
                                  className="h-8 py-1"
                                />
                              ) : line.role_name}
                            </td>
                            <td className="py-3 px-2 text-center">
                              {isEditing ? (
                                <Input 
                                  type="number" 
                                  value={line.quantity} 
                                  onChange={(e) => updateResourceLine(idx, 'quantity', parseFloat(e.target.value))}
                                  className="h-8 py-1 w-16 mx-auto"
                                />
                              ) : line.quantity}
                            </td>
                            <td className="py-3 px-2 text-center">
                              {isEditing ? (
                                <Input 
                                  type="number" 
                                  value={line.hours} 
                                  onChange={(e) => updateResourceLine(idx, 'hours', parseFloat(e.target.value))}
                                  className="h-8 py-1 w-20 mx-auto"
                                />
                              ) : line.hours}
                            </td>
                            <td className="py-3 px-2 text-center">
                              {isEditing ? (
                                <Input 
                                  type="number" 
                                  value={line.rate} 
                                  onChange={(e) => updateResourceLine(idx, 'rate', parseFloat(e.target.value))}
                                  className="h-8 py-1 w-24 mx-auto"
                                  prefix="₹"
                                />
                              ) : formatMoney(line.rate, selectedVersion.currency)}
                            </td>
                            <td className="py-3 px-2 text-right font-medium text-slate-900">
                              {formatMoney(line.cost_decimal || 0, selectedVersion.currency)}
                            </td>
                            <td className="py-3 text-right">
                              {isEditing && (
                                <button 
                                  onClick={() => setSelectedVersion({...selectedVersion, resource_lines: selectedVersion.resource_lines.filter((_, i) => i !== idx)})}
                                  className="text-slate-300 hover:text-red-500 transition-colors"
                                >
                                  <Trash2 className="w-4 h-4" />
                                </button>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </Card>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  {/* Scope / Assumptions */}
                  <Card className="p-6">
                    <h3 className="font-bold text-slate-900 mb-4 flex items-center gap-2">
                      <FileText className="w-5 h-5 text-indigo-600" />
                      Assumptions & Scope
                    </h3>
                    <div className="space-y-4">
                      <div>
                        <label className="text-[10px] font-black text-slate-400 uppercase tracking-wider mb-1 block">Assumptions</label>
                        {isEditing ? (
                          <textarea 
                            value={selectedVersion.assumptions || ''} 
                            onChange={(e) => setSelectedVersion({...selectedVersion, assumptions: e.target.value})}
                            className="w-full min-h-[100px] border border-slate-200 rounded-lg p-3 text-sm focus:ring-2 focus:ring-indigo-500 outline-none"
                            placeholder="Key assumptions for this estimate..."
                          />
                        ) : (
                          <p className="text-sm text-slate-600 bg-slate-50 p-3 rounded-lg min-h-[60px] whitespace-pre-wrap">
                            {selectedVersion.assumptions || 'No assumptions specified.'}
                          </p>
                        )}
                      </div>
                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <label className="text-[10px] font-black text-green-600 uppercase tracking-wider mb-1 block">Included</label>
                          <textarea 
                            disabled={!isEditing}
                            value={selectedVersion.scope_included || ''} 
                            onChange={(e) => setSelectedVersion({...selectedVersion, scope_included: e.target.value})}
                            className="w-full min-h-[100px] border border-slate-200 rounded-lg p-3 text-sm focus:ring-2 focus:ring-indigo-500 outline-none disabled:bg-slate-50 disabled:text-slate-500"
                          />
                        </div>
                        <div>
                          <label className="text-[10px] font-black text-red-600 uppercase tracking-wider mb-1 block">Excluded</label>
                          <textarea 
                            disabled={!isEditing}
                            value={selectedVersion.scope_excluded || ''} 
                            onChange={(e) => setSelectedVersion({...selectedVersion, scope_excluded: e.target.value})}
                            className="w-full min-h-[100px] border border-slate-200 rounded-lg p-3 text-sm focus:ring-2 focus:ring-indigo-500 outline-none disabled:bg-slate-50 disabled:text-slate-500"
                          />
                        </div>
                      </div>
                    </div>
                  </Card>

                  {/* Phases */}
                  <Card className="p-6">
                    <div className="flex items-center justify-between mb-4">
                      <h3 className="font-bold text-slate-900 flex items-center gap-2">
                        <LayoutGrid className="w-5 h-5 text-indigo-600" />
                        Project Phases
                      </h3>
                      {isEditing && (
                        <button onClick={addPhase} className="text-indigo-600 hover:text-indigo-700 text-xs font-bold flex items-center gap-1">
                          <Plus className="w-3 h-3" /> Add Phase
                        </button>
                      )}
                    </div>
                    <div className="space-y-3">
                      {selectedVersion.phases.map((phase, idx) => (
                        <div key={idx} className="bg-slate-50 p-3 rounded-lg border border-slate-100 flex items-center gap-4">
                          <div className="grow">
                            {isEditing ? (
                              <Input 
                                value={phase.phase_name} 
                                onChange={(e) => updatePhase(idx, 'phase_name', e.target.value)}
                                className="h-8 font-bold text-xs"
                              />
                            ) : (
                              <p className="font-bold text-slate-900 text-sm">{phase.phase_name}</p>
                            )}
                          </div>
                          <div className="flex items-center gap-2">
                            <label className="text-[9px] text-slate-400 uppercase font-black">Days:</label>
                            {isEditing ? (
                              <Input 
                                type="number"
                                value={phase.duration_days} 
                                onChange={(e) => updatePhase(idx, 'duration_days', parseInt(e.target.value))}
                                className="h-8 w-16 text-center text-xs"
                              />
                            ) : (
                              <Badge variant="neutral">{phase.duration_days}d</Badge>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  </Card>
                </div>

                {/* Pricing / Margin Editor */}
                {isEditing && (
                  <Card className="p-6 border-indigo-100 bg-indigo-50/20">
                    <h3 className="font-bold text-slate-900 mb-4">Pricing Adjustments</h3>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                      <div>
                        <label className="text-xs font-bold text-slate-600 mb-1 block">Contingency (%)</label>
                        <Input 
                          type="number"
                          value={selectedVersion.contingency_percent}
                          onChange={(e) => setSelectedVersion({...selectedVersion, contingency_percent: parseFloat(e.target.value)})}
                        />
                        <p className="text-[10px] text-slate-400 mt-1">Buffer added to total cost before margin.</p>
                      </div>
                      <div>
                        <label className="text-xs font-bold text-slate-600 mb-1 block">Commercial Margin (%)</label>
                        <Input 
                          type="number"
                          value={selectedVersion.margin_percent}
                          onChange={(e) => setSelectedVersion({...selectedVersion, margin_percent: parseFloat(e.target.value)})}
                        />
                        <p className="text-[10px] text-slate-400 mt-1">Gross profit margin for final pricing.</p>
                      </div>
                    </div>
                  </Card>
                )}
              </div>
            </>
          ) : (
            <Card className="h-full flex flex-col items-center justify-center py-20 bg-slate-50 border-dashed">
              <PlusCircle className="w-12 h-12 text-slate-200 mb-4" />
              <p className="text-slate-500 font-medium">No version selected.</p>
              <Button onClick={openNewVersionDialog} variant="outline" className="mt-4">
                Create First Estimate
              </Button>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
};
