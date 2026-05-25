import React, { useEffect, useMemo, useState } from 'react';
import { Archive, CheckCircle2, ClipboardList, Eye, Plus, RefreshCcw, Send, Trash2, Users, Calculator, UserCog } from 'lucide-react';
import { toast } from 'sonner';

import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';
import { Button, Card, Input, Badge, cn } from './ui-elements';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from './ui/dialog';

type UserLink = {
  id: number;
  full_name?: string;
  email?: string;
};

type LeadBidTaskRead = {
  id: number;
  lead_id: number;
  title: string;
  description?: string | null;
  bd_estimated_hours?: number | null;
  bd_estimated_cost?: number | null;
  is_archived?: boolean;
  created_by_id?: number | null;
  created_at: string;
  updated_at: string;
};

type LeadBidTaskAssignmentRead = {
  id: number;
  bid_task_id: number;
  pm_user_id: number;
  assigned_by_id?: number | null;
  deadline?: string | null;
  created_at: string;
  pm_user?: UserLink | null;
};

type LeadBidTaskWithAssignments = {
  task: LeadBidTaskRead;
  assignments: LeadBidTaskAssignmentRead[];
};

type EstimateVersion = {
  id: number;
  lead_id: number;
  version_number?: number;
  status?: string;
  currency?: string;
  created_at?: string;
  updated_at?: string;
};

type ReviewStatus = 'DRAFT' | 'SUBMITTED' | string;

type LeadBidTaskReviewRead = {
  id: number;
  assignment_id: number;
  estimate_version_id: number;
  revision_number: number;
  status: ReviewStatus;
  currency: string;
  total_hours: number;
  total_cost: number;
  pm_notes?: string | null;
  bd_notes?: string | null;
  submitted_at?: string | null;
  lines?: Array<{
    id: number;
    review_id: number;
    title: string;
    role?: string | null;
    description?: string | null;
    hours: number;
    cost: number;
    sort_order: number;
  }>;
};

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

type IncludedLineItem = {
  review_id: number;
  assignment_id: number;
  revision_number: number;
  title: string;
  role?: string | null;
  hours: number;
  cost: number;
};

type LeadBidTaskReviewSummary = {
  assignment: LeadBidTaskAssignmentRead;
  latest_review?: LeadBidTaskReviewRead | null;
};

type LeadBidEvaluationsResponse = {
  lead_id: number;
  estimate_version_id: number;
  tasks: LeadBidTaskWithAssignments[];
  reviews: LeadBidTaskReviewSummary[];
};

type PMUser = {
  id: number;
  full_name: string;
  email?: string;
};

type LeadDocumentRead = {
  id: number;
  lead_id: number;
  file_name: string;
  mime_type: string;
  file_size: number;
  uploaded_at: string;
  uploader_id: number;
  download_url?: string;
};

type BidLineItemRead = {
  id: number;
  title: string;
  description?: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
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

const formatHours = (value: unknown) => {
  const n = Number(value || 0);
  if (!Number.isFinite(n) || n <= 0) return null;
  const s = n.toFixed(2).replace(/\.00$/, '').replace(/(\.[0-9])0$/, '$1');
  return `${s}h`;
};

const StatusBadge = ({ status }: { status: ReviewStatus }) => {
  const normalized = String(status || '').toUpperCase();
  const variant = normalized === 'SUBMITTED' ? 'success' : 'warning';
  return (
    <Badge
      variant={variant as any}
      className={cn(
        'text-[10px] px-2 py-0.5 font-bold tracking-wide',
        normalized === 'SUBMITTED'
          ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
          : 'bg-amber-50 text-amber-700 border-amber-200',
      )}
    >
      {normalized}
    </Badge>
  );
};

export const LeadBidTasksPanel = ({
  leadId,
  onViewEstimates,
}: {
  leadId: number;
  onViewEstimates?: () => void;
}) => {
  const [loading, setLoading] = useState(true);
  const [tasks, setTasks] = useState<LeadBidTaskWithAssignments[]>([]);
  const [versions, setVersions] = useState<EstimateVersion[]>([]);
  const [selectedVersionId, setSelectedVersionId] = useState<number | null>(null);
  const [evaluations, setEvaluations] = useState<LeadBidEvaluationsResponse | null>(null);

  const [createOpen, setCreateOpen] = useState(false);
  const [createTemplateId, setCreateTemplateId] = useState<number | null>(null);
  const [createTitle, setCreateTitle] = useState('');
  const [createDescription, setCreateDescription] = useState('');
  const [createBdHours, setCreateBdHours] = useState('');
  const [createBdCost, setCreateBdCost] = useState('');
  const [createSaving, setCreateSaving] = useState(false);

  const [bidLineItemsLoading, setBidLineItemsLoading] = useState(false);
  const [bidLineItems, setBidLineItems] = useState<BidLineItemRead[]>([]);

  const [assignDialogOpen, setAssignDialogOpen] = useState(false);
  const [assignTask, setAssignTask] = useState<LeadBidTaskRead | null>(null);
  const [pmUsers, setPmUsers] = useState<PMUser[]>([]);
  const [pmSearch, setPmSearch] = useState('');
  const [selectedPms, setSelectedPms] = useState<Set<number>>(new Set());
  const [deliveryPmUserId, setDeliveryPmUserId] = useState<number | null>(null);
  const [assignDeadline, setAssignDeadline] = useState('');
  const [assignSaving, setAssignSaving] = useState(false);
  const [cooAssigning, setCooAssigning] = useState(false);

  const [leadDocuments, setLeadDocuments] = useState<LeadDocumentRead[]>([]);
  const [leadDocsLoading, setLeadDocsLoading] = useState(false);
  const [docSearch, setDocSearch] = useState('');
  const [selectedDocs, setSelectedDocs] = useState<Set<number>>(new Set());

  const [revisionDialogOpen, setRevisionDialogOpen] = useState(false);
  const [revisionReview, setRevisionReview] = useState<LeadBidTaskReviewRead | null>(null);
  const [revisionNotes, setRevisionNotes] = useState('');
  const [revisionSaving, setRevisionSaving] = useState(false);
  const [acceptingReviewId, setAcceptingReviewId] = useState<number | null>(null);

  const [detailsOpen, setDetailsOpen] = useState(false);
  const [detailsLoading, setDetailsLoading] = useState(false);
  const [detailsReview, setDetailsReview] = useState<LeadBidTaskReviewRead | null>(null);
  const [detailsPmName, setDetailsPmName] = useState<string>('');

  const [applyOpen, setApplyOpen] = useState(false);
  const [applyLoading, setApplyLoading] = useState(false);
  const [applyApplying, setApplyApplying] = useState(false);
  const [applySummary, setApplySummary] = useState<PMSubmissionsSummaryResponse | null>(null);
  const [applyLineItems, setApplyLineItems] = useState<IncludedLineItem[]>([]);
  const [applyLinesLoading, setApplyLinesLoading] = useState(false);

  const loadIncludedLineItems = async (summary: PMSubmissionsSummaryResponse) => {
    if (!summary?.included_reviews?.length) {
      setApplyLineItems([]);
      return;
    }

    setApplyLinesLoading(true);
    try {
      const reviews = await Promise.all(
        summary.included_reviews.map(async (inc) => {
          const res = await client.get<LeadBidTaskReviewRead>(
            ENDPOINTS.BD.BID_TASKS.REVIEW_UPDATE(inc.review_id),
          );
          return { inc, review: res.data };
        }),
      );

      const items: IncludedLineItem[] = [];
      for (const r of reviews) {
        const lines = r.review?.lines || [];
        for (const line of lines) {
          items.push({
            review_id: r.inc.review_id,
            assignment_id: r.inc.assignment_id,
            revision_number: r.inc.revision_number,
            title: String(line.title || ''),
            role: (line.role as any) ?? null,
            hours: Number(line.hours || 0),
            cost: Number(line.cost || 0),
          });
        }
      }
      setApplyLineItems(items);
    } catch (error: any) {
      console.error('Failed to load included review line items', error);
      const msg =
        error?.response?.data?.error?.message ||
        error?.response?.data?.detail ||
        'Failed to load included line items';
      toast.error(msg);
      setApplyLineItems([]);
    } finally {
      setApplyLinesLoading(false);
    }
  };

  const loadBidTasks = async () => {
    const res = await client.get<LeadBidTaskWithAssignments[]>(
      ENDPOINTS.BD.BID_TASKS.LIST(leadId),
    );
    setTasks(res.data || []);
  };

  const loadEstimateVersions = async () => {
    const res = await client.get<EstimateVersion[]>(
      ENDPOINTS.BD.LEAD_ESTIMATES(leadId),
    );
    const items = res.data || [];
    setVersions(items);

    if (!selectedVersionId && items.length > 0) {
      setSelectedVersionId(items[0].id);
    }
  };

  const loadEvaluations = async (estimateVersionId: number) => {
    const res = await client.get<LeadBidEvaluationsResponse>(
      ENDPOINTS.BD.BID_TASKS.EVALUATIONS(leadId),
      { params: { estimate_version_id: estimateVersionId } },
    );
    setEvaluations(res.data);
  };

  const refreshAll = async () => {
    setLoading(true);
    try {
      await Promise.all([loadBidTasks(), loadEstimateVersions()]);
      if (selectedVersionId) {
        await loadEvaluations(selectedVersionId);
      } else {
        setEvaluations(null);
      }
    } catch (error: any) {
      console.error('Failed to load bid tasks', error);
      const msg =
        error?.response?.data?.error?.message ||
        error?.response?.data?.detail ||
        'Failed to load bid tasks';
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  };

  const openApply = async () => {
    if (!selectedVersionId) {
      toast.error('Select an estimate version first');
      return;
    }

    setApplyOpen(true);
    setApplyLoading(true);
    setApplySummary(null);

    try {
      const res = await client.get<PMSubmissionsSummaryResponse>(
        ENDPOINTS.BD.BID_TASKS.PM_SUBMISSIONS_SUMMARY(leadId, selectedVersionId),
      );
      const summary = res.data || null;
      setApplySummary(summary);
      if (summary) {
        await loadIncludedLineItems(summary);
      } else {
        setApplyLineItems([]);
      }
    } catch (error: any) {
      console.error('Failed to load PM submissions summary', error);
      const msg =
        error?.response?.data?.error?.message ||
        error?.response?.data?.detail ||
        'Failed to load PM submissions summary';
      toast.error(msg);
      setApplyOpen(false);
    } finally {
      setApplyLoading(false);
    }
  };

  const refreshApplySummary = async () => {
    if (!selectedVersionId) {
      toast.error('Select an estimate version first');
      return;
    }
    setApplyLoading(true);
    setApplySummary(null);
    setApplyLineItems([]);
    try {
      const res = await client.get<PMSubmissionsSummaryResponse>(
        ENDPOINTS.BD.BID_TASKS.PM_SUBMISSIONS_SUMMARY(leadId, selectedVersionId),
      );
      const summary = res.data || null;
      setApplySummary(summary);
      if (summary) {
        await loadIncludedLineItems(summary);
      }
    } catch (error: any) {
      console.error('Failed to load PM submissions summary', error);
      const msg =
        error?.response?.data?.error?.message ||
        error?.response?.data?.detail ||
        'Failed to load PM submissions summary';
      toast.error(msg);
    } finally {
      setApplyLoading(false);
    }
  };

  const applyToEstimate = async () => {
    if (!selectedVersionId) {
      toast.error('Select an estimate version first');
      return;
    }

    setApplyApplying(true);
    try {
      await client.post(
        ENDPOINTS.BD.BID_TASKS.APPLY_PM_SUBMISSIONS(leadId, selectedVersionId),
      );
      toast.success('Applied PM submissions to estimate');
      setApplyOpen(false);
      await Promise.all([loadEstimateVersions(), loadEvaluations(selectedVersionId)]);
    } catch (error: any) {
      console.error('Failed to apply PM submissions', error);
      const errData = error?.response?.data?.error || error?.response?.data?.detail;
      const code = typeof errData === 'object' ? errData?.code : '';
      if (code === 'UNASSIGNED_BID_TASKS') {
        toast.error('Some bid tasks are unassigned. Assign all tasks before applying.');
      } else {
        const msg =
          (typeof errData === 'object' ? errData?.message : errData) ||
          'Failed to apply PM submissions';
        toast.error(msg);
      }
    } finally {
      setApplyApplying(false);
    }
  };

  useEffect(() => {
    refreshAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [leadId]);

  useEffect(() => {
    if (!selectedVersionId) {
      setEvaluations(null);
      return;
    }
    loadEvaluations(selectedVersionId).catch((error) => {
      console.error('Failed to load evaluations', error);
      toast.error('Failed to load PM evaluations');
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedVersionId]);

  const openAssign = async (task: LeadBidTaskRead) => {
    setAssignTask(task);
    setAssignDialogOpen(true);
    setPmSearch('');
    setSelectedPms(new Set());
    setDeliveryPmUserId(null);
    setAssignDeadline('');
    setDocSearch('');
    setSelectedDocs(new Set());

    try {
      const res = await client.get<PMUser[]>(ENDPOINTS.BD.PROJECT_MANAGERS);
      setPmUsers(res.data || []);
    } catch (error) {
      console.error('Failed to load PMs', error);
      toast.error('Failed to load PM list');
      setPmUsers([]);
    }

    setLeadDocsLoading(true);
    try {
      const docsRes = await client.get<LeadDocumentRead[]>(ENDPOINTS.BD.LEAD_DOCUMENTS(leadId));
      setLeadDocuments(docsRes.data || []);
    } catch (error: any) {
      console.error('Failed to load lead documents', error);
      const msg =
        error?.response?.data?.error?.message ||
        error?.response?.data?.detail ||
        'Failed to load lead documents';
      toast.error(msg);
      setLeadDocuments([]);
    } finally {
      setLeadDocsLoading(false);
    }
  };

  const filteredPms = useMemo(() => {
    const q = pmSearch.trim().toLowerCase();
    if (!q) return pmUsers;
    return pmUsers.filter((u) => {
      const name = (u.full_name || '').toLowerCase();
      const email = (u.email || '').toLowerCase();
      return name.includes(q) || email.includes(q);
    });
  }, [pmUsers, pmSearch]);

  const togglePm = (pmId: number) => {
    setSelectedPms((prev) => {
      const next = new Set(prev);
      if (next.has(pmId)) next.delete(pmId);
      else next.add(pmId);

      setDeliveryPmUserId((cur) => {
        const firstSelected = Array.from(next.values())[0] ?? null;
        if (cur == null) return firstSelected;
        const wasSelected = prev.has(cur);
        const stillSelected = next.has(cur);
        if (wasSelected && !stillSelected) return firstSelected;
        return cur;
      });

      return next;
    });
  };

  const filteredDocs = useMemo(() => {
    const q = docSearch.trim().toLowerCase();
    if (!q) return leadDocuments;
    return leadDocuments.filter((d) => (d.file_name || '').toLowerCase().includes(q));
  }, [leadDocuments, docSearch]);

  const toggleDoc = (docId: number) => {
    setSelectedDocs((prev) => {
      const next = new Set(prev);
      if (next.has(docId)) next.delete(docId);
      else next.add(docId);
      return next;
    });
  };

  const loadBidLineItemTemplates = async () => {
    setBidLineItemsLoading(true);
    try {
      const res = await client.get<BidLineItemRead[]>(ENDPOINTS.BD.BID_LINE_ITEMS);
      setBidLineItems((res.data || []).filter((t) => t.is_active));
    } catch (error: any) {
      console.error('Failed to load bid line items', error);
      const msg =
        error?.response?.data?.error?.message ||
        error?.response?.data?.detail ||
        'Failed to load bid line item templates';
      toast.error(msg);
      setBidLineItems([]);
    } finally {
      setBidLineItemsLoading(false);
    }
  };

  const createTask = async () => {
    const title = createTitle.trim();
    if (!title && createTemplateId == null) {
      toast.error('Task title is required');
      return;
    }

    setCreateSaving(true);
    try {
      const bdH = parseFloat(createBdHours);
      const bdC = parseFloat(createBdCost);
      const payload: any = {
        title: title || undefined,
        description: createDescription?.trim() || undefined,
        template_id: createTemplateId ?? undefined,
        bd_estimated_hours: Number.isFinite(bdH) && bdH >= 0 ? bdH : undefined,
        bd_estimated_cost: Number.isFinite(bdC) && bdC >= 0 ? bdC : undefined,
      };
      await client.post(ENDPOINTS.BD.BID_TASKS.CREATE(leadId), payload);
      toast.success('Bid task created');
      setCreateTemplateId(null);
      setCreateTitle('');
      setCreateDescription('');
      setCreateBdHours('');
      setCreateBdCost('');
      setCreateOpen(false);
      await loadBidTasks();
    } catch (error: any) {
      console.error('Failed to create task', error);
      const msg =
        error?.response?.data?.error?.message ||
        error?.response?.data?.detail ||
        'Failed to create bid task';
      toast.error(msg);
    } finally {
      setCreateSaving(false);
    }
  };

  useEffect(() => {
    if (!createOpen) return;
    void loadBidLineItemTemplates();
  }, [createOpen]);

  const saveAssignment = async () => {
    if (!assignTask) return;

    const pmIds = Array.from(selectedPms);
    if (pmIds.length === 0) {
      toast.error('Select at least one PM');
      return;
    }

    if (!deliveryPmUserId) {
      toast.error('Select a delivery PM');
      return;
    }

    setAssignSaving(true);
    try {
      await client.post(ENDPOINTS.BD.BID_TASKS.ASSIGN(leadId, assignTask.id), {
        pm_user_ids: pmIds,
        delivery_pm_user_id: deliveryPmUserId,
        lead_document_ids: Array.from(selectedDocs),
        deadline: assignDeadline || undefined,
      });
      toast.success('Assigned to PM(s)');
      setAssignDialogOpen(false);
      setAssignTask(null);
      setSelectedDocs(new Set());
      await loadBidTasks();
      if (selectedVersionId) {
        await loadEvaluations(selectedVersionId);
      }
    } catch (error: any) {
      console.error('Failed to assign', error);
      const msg =
        error?.response?.data?.error?.message ||
        error?.response?.data?.detail ||
        'Failed to assign bid task';
      toast.error(msg);
    } finally {
      setAssignSaving(false);
    }
  };

  const openRevision = (review: LeadBidTaskReviewRead) => {
    setRevisionReview(review);
    setRevisionNotes('');
    setRevisionDialogOpen(true);
  };

  const openDetails = async (assignment: LeadBidTaskAssignmentRead) => {
    if (!selectedVersionId) {
      toast.error('Select an estimate version first');
      return;
    }

    const pmName = assignment.pm_user?.full_name || `PM #${assignment.pm_user_id}`;
    setDetailsPmName(pmName);
    setDetailsReview(null);
    setDetailsOpen(true);
    setDetailsLoading(true);

    try {
      const res = await client.get<LeadBidTaskReviewRead>(
        ENDPOINTS.BD.BID_TASKS.ASSIGNMENT_LATEST_REVIEW(assignment.id),
        {
          params: {
            estimate_version_id: selectedVersionId,
          },
        },
      );
      setDetailsReview(res.data);
    } catch (error: any) {
      console.error('Failed to load review details', error);
      const msg =
        error?.response?.data?.error?.message ||
        error?.response?.data?.detail ||
        'Failed to load review details';
      toast.error(msg);
      setDetailsOpen(false);
    } finally {
      setDetailsLoading(false);
    }
  };

  const acceptReview = async (review: LeadBidTaskReviewRead) => {
    setAcceptingReviewId(review.id);
    try {
      await client.post(ENDPOINTS.BD.BID_TASKS.REVIEW_ACCEPT(review.id));
      toast.success('Review accepted');
      if (selectedVersionId) {
        await loadEvaluations(selectedVersionId);
      }
    } catch (error: any) {
      const msg =
        error?.response?.data?.error?.message ||
        error?.response?.data?.detail ||
        'Failed to accept review';
      toast.error(msg);
    } finally {
      setAcceptingReviewId(null);
    }
  };

  const requestRevision = async () => {
    if (!revisionReview) return;
    const notes = revisionNotes.trim();
    if (!notes) {
      toast.error('Revision notes are required');
      return;
    }

    setRevisionSaving(true);
    try {
      await client.post(
        ENDPOINTS.BD.BID_TASKS.REVIEW_REQUEST_REVISION(revisionReview.id),
        { bd_notes: notes },
      );
      toast.success('Revision requested');
      setRevisionDialogOpen(false);
      setRevisionReview(null);
      setRevisionNotes('');
      if (selectedVersionId) {
        await loadEvaluations(selectedVersionId);
      }
    } catch (error: any) {
      console.error('Failed to request revision', error);
      const msg =
        error?.response?.data?.error?.message ||
        error?.response?.data?.detail ||
        'Failed to request revision';
      toast.error(msg);
    } finally {
      setRevisionSaving(false);
    }
  };

  const assignUnassignedToCoo = async () => {
    setCooAssigning(true);
    try {
      await client.post(ENDPOINTS.BD.BID_TASKS.ASSIGN_UNASSIGNED_TO_COO(leadId));
      toast.success('Unassigned tasks assigned to COO');
      await loadBidTasks();
      if (selectedVersionId) await loadEvaluations(selectedVersionId);
    } catch (error: any) {
      const msg =
        error?.response?.data?.error?.message ||
        error?.response?.data?.detail ||
        'Failed to assign to COO';
      toast.error(msg);
    } finally {
      setCooAssigning(false);
    }
  };

  const archiveTask = async (taskId: number) => {
    try {
      await client.post(ENDPOINTS.BD.BID_TASKS.ARCHIVE(leadId, taskId));
      toast.success('Bid task archived');
      await loadBidTasks();
    } catch (error: any) {
      const msg =
        error?.response?.data?.error?.message ||
        error?.response?.data?.detail ||
        'Failed to archive task';
      toast.error(msg);
    }
  };

  const deleteTask = async (taskId: number) => {
    try {
      await client.delete(ENDPOINTS.BD.BID_TASKS.DELETE(leadId, taskId));
      toast.success('Bid task deleted');
      await loadBidTasks();
    } catch (error: any) {
      const msg =
        error?.response?.data?.error?.message ||
        error?.response?.data?.detail ||
        'Failed to delete task';
      toast.error(msg);
    }
  };

  const hasUnassignedTasks = tasks.some((t) => (t.assignments || []).length === 0);

  const reviewsByAssignment = useMemo(() => {
    const map = new Map<number, LeadBidTaskReviewRead>();
    (evaluations?.reviews || []).forEach((r) => {
      if (r.latest_review) {
        map.set(r.assignment.id, r.latest_review);
      }
    });
    return map;
  }, [evaluations]);

  return (
    <Card className="p-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h3 className="font-bold text-slate-900 flex items-center gap-2">
            <ClipboardList className="w-5 h-5 text-indigo-600" />
            Bid Tasks & PM Estimates
          </h3>
          <p className="text-sm text-slate-500 mt-1">
            Create bid tasks, assign PMs, and review submissions per estimate version.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={refreshAll}
            className="flex items-center gap-2"
            disabled={loading}
          >
            <RefreshCcw className="w-4 h-4" />
            Refresh
          </Button>
          {hasUnassignedTasks && (
            <Button
              size="sm"
              variant="outline"
              className="flex items-center gap-2 border-orange-200 text-orange-700 hover:bg-orange-50"
              onClick={assignUnassignedToCoo}
              disabled={cooAssigning}
            >
              <UserCog className="w-4 h-4" />
              {cooAssigning ? 'Assigning…' : 'Assign Unassigned to COO'}
            </Button>
          )}
          <Button
            size="sm"
            className="bg-indigo-600 hover:bg-indigo-700 text-white flex items-center gap-2"
            onClick={() => setCreateOpen((v) => !v)}
          >
            <Plus className="w-4 h-4" />
            New Bid Task
          </Button>
        </div>
      </div>

      {createOpen && (
        <div className="mt-5 bg-slate-50 border border-slate-100 rounded-xl p-4 space-y-3">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <label className="text-sm font-medium text-slate-700">Template (optional)</label>
              <select
                title="Select bid line item template"
                value={createTemplateId ?? ''}
                onChange={(e) => {
                  const nextId = e.target.value ? Number(e.target.value) : null;
                  setCreateTemplateId(nextId);
                  if (nextId == null) return;

                  const selected = bidLineItems.find((t) => t.id === nextId);
                  if (!selected) return;
                  setCreateTitle(selected.title || '');
                  setCreateDescription(selected.description || '');
                }}
                disabled={bidLineItemsLoading}
                className="h-10 px-3 rounded-md border border-slate-200 focus:outline-none focus:ring-2 focus:ring-indigo-500 text-sm bg-white"
              >
                <option value="">Custom (no template)</option>
                {bidLineItems.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.title}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-1.5">
              <label className="text-sm font-medium text-slate-700">Title</label>
              <Input
                value={createTitle}
                onChange={(e) => setCreateTitle(e.target.value)}
                placeholder="e.g. Scope clarification + initial delivery plan"
              />
            </div>
            <div className="space-y-1.5">
              <label className="text-sm font-medium text-slate-700">Description (optional)</label>
              <Input
                value={createDescription}
                onChange={(e) => setCreateDescription(e.target.value)}
                placeholder="Short context for PMs"
              />
            </div>
            <div className="space-y-1.5">
              <label className="text-sm font-medium text-slate-700">BD Est. Hours</label>
              <Input
                type="number"
                min="0"
                step="0.5"
                value={createBdHours}
                onChange={(e) => setCreateBdHours(e.target.value)}
                placeholder="e.g. 40"
              />
            </div>
            <div className="space-y-1.5">
              <label className="text-sm font-medium text-slate-700">BD Est. Cost</label>
              <Input
                type="number"
                min="0"
                step="100"
                value={createBdCost}
                onChange={(e) => setCreateBdCost(e.target.value)}
                placeholder="e.g. 50000"
              />
            </div>
          </div>
          <div className="flex justify-end gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setCreateOpen(false);
                setCreateTemplateId(null);
                setCreateTitle('');
                setCreateDescription('');
                setCreateBdHours('');
                setCreateBdCost('');
              }}
            >
              Cancel
            </Button>
            <Button
              size="sm"
              className="bg-indigo-600 hover:bg-indigo-700 text-white"
              onClick={createTask}
              disabled={createSaving}
            >
              {createSaving ? 'Creating…' : 'Create'}
            </Button>
          </div>
        </div>
      )}

      <div className="mt-6 grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-4">
          <div className="flex items-center justify-between">
            <h4 className="text-sm font-bold text-slate-900">Bid Tasks</h4>
            <div className="flex items-center gap-2">
              <span className="text-xs text-slate-500">Estimate version</span>
              <select
                title="Select estimate version"
                value={selectedVersionId ?? ''}
                onChange={(e) => setSelectedVersionId(e.target.value ? Number(e.target.value) : null)}
                disabled={versions.length === 0}
                className="h-9 px-3 rounded-md border border-slate-200 focus:outline-none focus:ring-2 focus:ring-indigo-500 text-sm bg-white"
              >
                {versions.length === 0 ? (
                  <option value="">No estimate versions</option>
                ) : (
                  versions.map((v) => (
                    <option key={v.id} value={v.id}>
                      Version #{v.version_number ?? v.id}
                    </option>
                  ))
                )}
              </select>

              <Button
                size="sm"
                variant="outline"
                className="flex items-center gap-2"
                onClick={openApply}
                disabled={versions.length === 0 || !selectedVersionId}
                title="Apply latest submitted PM reviews to estimate resource lines"
              >
                <Send className="w-4 h-4" />
                Apply
              </Button>
            </div>
          </div>

          {versions.length === 0 ? (
            <div className="p-4 rounded-xl border border-amber-100 bg-amber-50 text-sm text-amber-900">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="font-semibold">No estimate versions yet</p>
                  <p className="text-amber-800/80 text-xs mt-1">
                    PM bid requests are tied to an estimate version. Create an estimate version first so PMs can see assigned tasks and you can review submissions per version.
                  </p>
                </div>
                {onViewEstimates ? (
                  <Button
                    size="sm"
                    variant="outline"
                    className="shrink-0 flex items-center gap-2 border-amber-200 bg-white hover:bg-amber-50"
                    onClick={onViewEstimates}
                  >
                    <Calculator className="w-4 h-4" />
                    Create Estimate
                  </Button>
                ) : null}
              </div>
            </div>
          ) : null}

          {loading ? (
            <div className="py-10 flex flex-col items-center justify-center text-slate-400">
              <div className="w-8 h-8 border-4 border-indigo-600 border-t-transparent rounded-full animate-spin mb-3" />
              <p className="text-sm">Loading bid tasks…</p>
            </div>
          ) : tasks.length === 0 ? (
            <div className="py-10 text-center text-slate-400 border border-dashed border-slate-200 rounded-xl">
              <ClipboardList className="w-10 h-10 mx-auto mb-2 opacity-20" />
              <p className="text-sm">No bid tasks created yet.</p>
              <p className="text-xs mt-1">Create tasks before requesting PM estimates.</p>
            </div>
          ) : (
            <div className="space-y-3">
              {tasks.map((row) => (
                <div
                  key={row.task.id}
                  className="p-4 rounded-xl border border-slate-100 bg-white hover:border-indigo-100 transition-colors"
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <p className="font-bold text-slate-900 truncate">{row.task.title}</p>
                        {(row.assignments || []).length > 0 ? (
                          <Badge className="text-[10px] px-2 py-0.5 bg-green-50 text-green-700 border-green-200">
                            Assigned
                          </Badge>
                        ) : (
                          <Badge className="text-[10px] px-2 py-0.5 bg-orange-50 text-orange-700 border-orange-200">
                            Unassigned
                          </Badge>
                        )}
                      </div>
                      {row.task.description ? (
                        <p className="text-sm text-slate-500 mt-1 line-clamp-2">{row.task.description}</p>
                      ) : (
                        <p className="text-sm text-slate-400 mt-1">No description</p>
                      )}
                      {(row.task.bd_estimated_hours || row.task.bd_estimated_cost) ? (
                        <div className="flex items-center gap-3 mt-1.5 text-xs text-slate-500">
                          {row.task.bd_estimated_hours ? (
                            <span>BD Est: <span className="font-semibold text-slate-700">{row.task.bd_estimated_hours}h</span></span>
                          ) : null}
                          {row.task.bd_estimated_cost ? (
                            <span>Cost: <span className="font-semibold text-slate-700">{formatMoney(row.task.bd_estimated_cost)}</span></span>
                          ) : null}
                        </div>
                      ) : null}
                    </div>
                    <div className="flex items-center gap-1.5 shrink-0">
                      <Button
                        size="sm"
                        variant="outline"
                        className="flex items-center gap-2"
                        onClick={() => openAssign(row.task)}
                      >
                        <Users className="w-4 h-4" />
                        Assign
                      </Button>
                      {(row.assignments || []).length === 0 ? (
                        <Button
                          size="sm"
                          variant="outline"
                          className="text-red-600 border-red-200 hover:bg-red-50 p-2"
                          title="Delete task"
                          onClick={() => deleteTask(row.task.id)}
                        >
                          <Trash2 className="w-4 h-4" />
                        </Button>
                      ) : (
                        <Button
                          size="sm"
                          variant="outline"
                          className="text-amber-600 border-amber-200 hover:bg-amber-50 p-2"
                          title="Archive task"
                          onClick={() => archiveTask(row.task.id)}
                        >
                          <Archive className="w-4 h-4" />
                        </Button>
                      )}
                    </div>
                  </div>

                  <div className="mt-3 flex flex-wrap gap-2">
                    {(row.assignments || []).length === 0 ? (
                      <span className="text-xs text-slate-400">Not assigned yet</span>
                    ) : (
                      row.assignments.map((a) => {
                        const name = a.pm_user?.full_name || `PM #${a.pm_user_id}`;
                        const review = reviewsByAssignment.get(a.id);
                        const hours = review ? formatHours(review.total_hours) : null;
                        const label = hours ? `${name} (${hours})` : name;
                        return (
                          <div
                            key={a.id}
                            className="flex items-center gap-2 px-2.5 py-1 rounded-full border border-slate-200 bg-slate-50"
                            title={a.pm_user?.email || ''}
                          >
                            <span className="text-xs font-semibold text-slate-700">{label}</span>
                            {review ? (
                              <StatusBadge status={review.status} />
                            ) : (
                              <Badge className="text-[10px] px-2 py-0.5 bg-slate-100 text-slate-600 border-slate-200">
                                PENDING
                              </Badge>
                            )}
                          </div>
                        );
                      })
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="space-y-4">
          <h4 className="text-sm font-bold text-slate-900">Latest Submissions</h4>

          {versions.length === 0 ? (
            <div className="p-4 rounded-xl border border-amber-100 bg-amber-50 text-sm text-amber-900">
              <p className="font-semibold">Create an estimate version to begin</p>
              <p className="text-amber-800/80 text-xs mt-1">
                Once an estimate version exists, you can track PM submissions and revisions per version.
              </p>
              {onViewEstimates ? (
                <Button
                  size="sm"
                  variant="outline"
                  className="mt-3 flex items-center gap-2 border-amber-200 bg-white hover:bg-amber-50"
                  onClick={onViewEstimates}
                >
                  <Calculator className="w-4 h-4" />
                  Create Estimate
                </Button>
              ) : null}
            </div>
          ) : !selectedVersionId ? (
            <div className="p-4 rounded-xl border border-slate-100 bg-slate-50 text-sm text-slate-500">
              Select an estimate version to view PM submissions.
            </div>
          ) : (evaluations?.reviews || []).length === 0 ? (
            <div className="p-4 rounded-xl border border-slate-100 bg-slate-50 text-sm text-slate-500">
              No PM submissions yet for this version.
            </div>
          ) : (
            <div className="space-y-3">
              {(evaluations?.reviews || []).map((r) => {
                const pmName = r.assignment.pm_user?.full_name || `PM #${r.assignment.pm_user_id}`;
                const review = r.latest_review;
                return (
                  <div
                    key={r.assignment.id}
                    className="p-4 rounded-xl border border-slate-100 bg-white"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="text-sm font-bold text-slate-900">{pmName}</p>
                        <p className="text-xs text-slate-500 mt-0.5">
                          Assignment #{r.assignment.id}
                        </p>
                      </div>
                      {review ? <StatusBadge status={review.status} /> : null}
                    </div>

                    {review ? (
                      <div className="mt-3 space-y-2">
                        <div className="flex items-center justify-between text-xs">
                          <span className="text-slate-500">Revision</span>
                          <span className="font-semibold text-slate-700">#{review.revision_number}</span>
                        </div>
                        <div className="flex items-center justify-between text-xs">
                          <span className="text-slate-500">Total hours</span>
                          <span className="font-semibold text-slate-700">{Number(review.total_hours || 0).toFixed(2)}</span>
                        </div>
                        <div className="flex items-center justify-between text-xs">
                          <span className="text-slate-500">Total cost</span>
                          <span className="font-semibold text-slate-700">{formatMoney(Number(review.total_cost || 0), review.currency)}</span>
                        </div>

                        <Button
                          size="sm"
                          variant="outline"
                          className="w-full mt-2 flex items-center justify-center gap-2"
                          onClick={() => openDetails(r.assignment)}
                        >
                          <Eye className="w-4 h-4" />
                          View Breakdown
                        </Button>

                        {String(review.status).toUpperCase() === 'SUBMITTED' ? (
                          <div className="flex gap-2 mt-2">
                            <Button
                              size="sm"
                              className="flex-1 flex items-center justify-center gap-1.5 bg-green-600 hover:bg-green-700 text-white"
                              onClick={() => acceptReview(review)}
                              disabled={acceptingReviewId === review.id}
                            >
                              {acceptingReviewId === review.id
                                ? <span className="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin" />
                                : <CheckCircle2 className="w-3.5 h-3.5" />}
                              Accept
                            </Button>
                            <Button
                              size="sm"
                              variant="outline"
                              className="flex-1 flex items-center justify-center gap-1.5"
                              onClick={() => openRevision(review)}
                            >
                              <Send className="w-3.5 h-3.5" />
                              Revise
                            </Button>
                          </div>
                        ) : String(review.status).toUpperCase() === 'ACCEPTED' ? (
                          <div className="mt-2 flex items-center gap-1.5 text-green-600 text-[11px] font-semibold">
                            <CheckCircle2 className="w-3.5 h-3.5" />
                            Accepted by BD
                          </div>
                        ) : String(review.status).toUpperCase() === 'REVISION_REQUESTED' ? (
                          <div className="mt-2 text-[11px] text-amber-600 font-semibold italic">
                            Revision requested — awaiting PM resubmission.
                          </div>
                        ) : (
                          <div className="text-[11px] text-slate-500 italic mt-2">
                            Waiting for PM to submit.
                          </div>
                        )}
                      </div>
                    ) : (
                      <div className="mt-3 text-xs text-slate-500">
                        No review yet.
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      <Dialog open={detailsOpen} onOpenChange={setDetailsOpen}>
        <DialogContent className="sm:max-w-3xl">
          <DialogHeader>
            <DialogTitle>PM Submission Details</DialogTitle>
          </DialogHeader>

          {detailsLoading ? (
            <div className="py-10 flex flex-col items-center justify-center text-slate-400">
              <div className="w-10 h-10 border-4 border-indigo-600 border-t-transparent rounded-full animate-spin mb-3" />
              <p className="text-sm">Loading breakdown…</p>
            </div>
          ) : !detailsReview ? (
            <div className="py-6 text-sm text-slate-500">No details available.</div>
          ) : (
            <div className="space-y-5">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="text-sm font-bold text-slate-900">{detailsPmName}</p>
                  <p className="text-xs text-slate-500 mt-0.5">
                    Revision #{detailsReview.revision_number} • Assignment #{detailsReview.assignment_id}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <StatusBadge status={detailsReview.status} />
                  <Badge className="text-[10px] px-2 py-0.5 bg-slate-100 text-slate-700 border-slate-200">
                    {Number(detailsReview.total_hours || 0).toFixed(2)} hrs
                  </Badge>
                  <Badge className="text-[10px] px-2 py-0.5 bg-slate-100 text-slate-700 border-slate-200">
                    {formatMoney(Number(detailsReview.total_cost || 0), detailsReview.currency)}
                  </Badge>
                </div>
              </div>

              {detailsReview.pm_notes ? (
                <div className="p-4 rounded-xl border border-slate-100 bg-slate-50">
                  <p className="text-xs font-bold text-slate-700">PM Notes</p>
                  <p className="text-sm text-slate-700 mt-1 whitespace-pre-wrap">{detailsReview.pm_notes}</p>
                </div>
              ) : null}

              {detailsReview.bd_notes ? (
                <div className="p-4 rounded-xl border border-indigo-100 bg-indigo-50">
                  <p className="text-xs font-bold text-indigo-700">BD Notes</p>
                  <p className="text-sm text-indigo-900 mt-1 whitespace-pre-wrap">{detailsReview.bd_notes}</p>
                </div>
              ) : null}

              <div className="space-y-2">
                <p className="text-sm font-bold text-slate-900">Line Items</p>
                {Array.isArray(detailsReview.lines) && detailsReview.lines.length > 0 ? (
                  <div className="border border-slate-200 rounded-xl overflow-hidden">
                    <div className="grid grid-cols-12 gap-2 px-4 py-2 bg-slate-50 text-[11px] font-bold text-slate-600">
                      <div className="col-span-5">Title</div>
                      <div className="col-span-3">Role</div>
                      <div className="col-span-2">Hours</div>
                      <div className="col-span-2">Cost</div>
                    </div>
                    {detailsReview.lines
                      .slice()
                      .sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0))
                      .map((l) => (
                        <div key={l.id} className="grid grid-cols-12 gap-2 px-4 py-3 border-t border-slate-100">
                          <div className="col-span-5">
                            <p className="text-sm font-semibold text-slate-900">{l.title}</p>
                            {l.description ? (
                              <p className="text-xs text-slate-500 mt-0.5 whitespace-pre-wrap">{l.description}</p>
                            ) : null}
                          </div>
                          <div className="col-span-3 text-sm text-slate-700">{(l.role || '').trim() || '—'}</div>
                          <div className="col-span-2 text-sm text-slate-700">{Number(l.hours || 0).toFixed(2)}</div>
                          <div className="col-span-2 text-sm text-slate-700">{formatMoney(Number(l.cost || 0), detailsReview.currency)}</div>
                        </div>
                      ))}
                  </div>
                ) : (
                  <div className="p-4 rounded-xl border border-dashed border-slate-200 text-sm text-slate-500">
                    No line items provided.
                  </div>
                )}
              </div>

              <div className="flex justify-end gap-2">
                {String(detailsReview.status).toUpperCase() === 'SUBMITTED' ? (
                  <Button
                    className="bg-indigo-600 hover:bg-indigo-700 text-white flex items-center gap-2"
                    onClick={() => {
                      setDetailsOpen(false);
                      openRevision(detailsReview);
                    }}
                  >
                    <Send className="w-4 h-4" />
                    Request Revision
                  </Button>
                ) : null}
                <Button variant="outline" onClick={() => setDetailsOpen(false)}>
                  Close
                </Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      <Dialog
        open={assignDialogOpen}
        onOpenChange={(open: boolean) => {
          setAssignDialogOpen(open);
          if (!open) {
            setAssignTask(null);
            setPmSearch('');
            setSelectedPms(new Set());
            setDeliveryPmUserId(null);
            setAssignDeadline('');
            setDocSearch('');
            setSelectedDocs(new Set());
          }
        }}
      >
        <DialogContent className="sm:max-w-xl">
          <DialogHeader>
            <DialogTitle>Assign PMs</DialogTitle>
          </DialogHeader>

          <div className="space-y-4">
            <div className="text-sm text-slate-600">
              <span className="font-semibold text-slate-900">Task:</span> {assignTask?.title}
            </div>

            <div className="space-y-1.5">
              <label className="text-sm font-medium text-slate-700">Delivery PM</label>
              <select
                value={deliveryPmUserId ?? ''}
                onChange={(e) => {
                  const v = Number(e.target.value || 0);
                  setDeliveryPmUserId(Number.isFinite(v) && v > 0 ? v : null);
                }}
                className="w-full h-10 px-3 rounded-md border border-slate-200 bg-white text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              >
                <option value="" disabled>
                  Select delivery PM
                </option>
                {pmUsers.map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.full_name}
                  </option>
                ))}
              </select>
              <div className="text-xs text-slate-500">
                This PM will receive the delivery task when the lead converts to a project.
              </div>
            </div>

            <div className="space-y-1.5">
              <label className="text-sm font-medium text-slate-700">Deadline (optional)</label>
              <Input
                type="datetime-local"
                value={assignDeadline}
                onChange={(e) => setAssignDeadline(e.target.value)}
              />
            </div>

            <div className="space-y-1.5">
              <label className="text-sm font-medium text-slate-700">Search</label>
              <Input
                value={pmSearch}
                onChange={(e) => setPmSearch(e.target.value)}
                placeholder="Filter by name or email"
              />
            </div>

            <div className="border border-slate-200 rounded-lg max-h-[260px] overflow-y-auto">
              {filteredPms.length === 0 ? (
                <div className="p-4 text-sm text-slate-500">No PMs found.</div>
              ) : (
                filteredPms.map((u) => (
                  <label
                    key={u.id}
                    className="flex items-center gap-3 px-4 py-2 border-b border-slate-100 last:border-b-0 hover:bg-slate-50 cursor-pointer"
                  >
                    <input
                      type="checkbox"
                      checked={selectedPms.has(u.id)}
                      onChange={() => togglePm(u.id)}
                      className="accent-indigo-600"
                    />
                    <div className="min-w-0">
                      <div className="text-sm font-semibold text-slate-900 truncate">{u.full_name}</div>
                      {u.email ? (
                        <div className="text-xs text-slate-500 truncate">{u.email}</div>
                      ) : null}
                    </div>
                  </label>
                ))
              )}
            </div>

            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <label className="text-sm font-medium text-slate-700">Attach Documents (optional)</label>
                <span className="text-xs text-slate-500">
                  Selected: <span className="font-semibold text-slate-700">{selectedDocs.size}</span>
                </span>
              </div>
              <Input
                value={docSearch}
                onChange={(e) => setDocSearch(e.target.value)}
                placeholder="Search uploaded documents"
              />
              <div className="border border-slate-200 rounded-lg max-h-[220px] overflow-y-auto bg-white">
                {leadDocsLoading ? (
                  <div className="p-4 text-sm text-slate-500">Loading documents…</div>
                ) : filteredDocs.length === 0 ? (
                  <div className="p-4 text-sm text-slate-500">No documents found for this lead.</div>
                ) : (
                  filteredDocs.map((d) => (
                    <label
                      key={d.id}
                      className="flex items-center gap-3 px-4 py-2 border-b border-slate-100 last:border-b-0 hover:bg-slate-50 cursor-pointer"
                    >
                      <input
                        type="checkbox"
                        checked={selectedDocs.has(d.id)}
                        onChange={() => toggleDoc(d.id)}
                        className="accent-indigo-600"
                      />
                      <div className="min-w-0">
                        <div className="text-sm font-semibold text-slate-900 truncate">{d.file_name}</div>
                        <div className="text-xs text-slate-500 truncate">
                          {new Date(d.uploaded_at).toLocaleString()}
                        </div>
                      </div>
                    </label>
                  ))
                )}
              </div>
            </div>

            <div className="flex items-center justify-between">
              <div className="text-xs text-slate-500">
                Selected: <span className="font-semibold text-slate-700">{selectedPms.size}</span>
              </div>
              <div className="flex gap-2">
                <Button variant="outline" onClick={() => setAssignDialogOpen(false)}>
                  Cancel
                </Button>
                <Button
                  className="bg-indigo-600 hover:bg-indigo-700 text-white"
                  onClick={saveAssignment}
                  disabled={assignSaving}
                >
                  {assignSaving ? 'Assigning…' : 'Assign'}
                </Button>
              </div>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog
        open={applyOpen}
        onOpenChange={(open: boolean) => {
          setApplyOpen(open);
          if (!open) {
            setApplyLoading(false);
            setApplyApplying(false);
            setApplySummary(null);
            setApplyLineItems([]);
            setApplyLinesLoading(false);
          }
        }}
      >
        <DialogContent className="sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>Apply PM Submissions</DialogTitle>
          </DialogHeader>

          {applyLoading ? (
            <div className="py-10 flex flex-col items-center justify-center text-slate-400">
              <div className="w-8 h-8 border-4 border-indigo-600 border-t-transparent rounded-full animate-spin mb-3" />
              <p className="text-sm">Loading summary…</p>
            </div>
          ) : !applySummary ? (
            <div className="py-6 text-sm text-slate-500">Summary not available.</div>
          ) : (
            <div className="space-y-4">
              <div className="p-3 rounded-xl border border-slate-100 bg-slate-50 text-sm text-slate-700">
                This replaces the estimate’s resource lines for the selected version with aggregated totals from the latest
                <span className="font-semibold"> submitted</span> PM reviews (drafts are not included).
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div className="p-3 rounded-xl bg-white border border-slate-200">
                  <p className="text-[11px] text-slate-500">Submitted reviews included</p>
                  <p className="text-sm font-bold text-slate-900">{applySummary.included_reviews.length}</p>
                </div>
                <div className="p-3 rounded-xl bg-white border border-slate-200">
                  <p className="text-[11px] text-slate-500">Line items</p>
                  <p className="text-sm font-bold text-slate-900">{applySummary.role_totals.length}</p>
                </div>
                <div className="p-3 rounded-xl bg-white border border-slate-200">
                  <p className="text-[11px] text-slate-500">Version</p>
                  <p className="text-sm font-bold text-slate-900">#{applySummary.estimate_version_id}</p>
                </div>
              </div>

              {applySummary.included_reviews.length === 0 ? (
                <div className="p-4 rounded-xl border border-dashed border-slate-200 text-sm text-slate-500">
                  No submitted PM reviews found for this estimate version.
                </div>
              ) : applyLinesLoading ? (
                <div className="py-6 flex items-center justify-center text-slate-400">
                  <div className="w-6 h-6 border-4 border-indigo-600 border-t-transparent rounded-full animate-spin mr-3" />
                  <p className="text-sm">Loading line items…</p>
                </div>
              ) : applyLineItems.length > 0 ? (
                <div className="border border-slate-200 rounded-xl overflow-hidden">
                  <div className="grid grid-cols-12 gap-2 px-4 py-2 bg-slate-50 text-[11px] font-bold text-slate-600">
                    <div className="col-span-5">Line item (task/subtask)</div>
                    <div className="col-span-3">Role</div>
                    <div className="col-span-2">Hours</div>
                    <div className="col-span-2">Cost</div>
                  </div>
                  <div className="max-h-52 overflow-y-auto">
                    {applyLineItems.map((li, idx) => (
                      <div key={`${li.review_id}-${idx}`} className="grid grid-cols-12 gap-2 px-4 py-2 border-t border-slate-100">
                        <div className="col-span-5 text-sm font-semibold text-slate-900">{li.title}</div>
                        <div className="col-span-3 text-sm text-slate-700">{li.role || 'Uncategorized'}</div>
                        <div className="col-span-2 text-sm text-slate-700">{Number(li.hours || 0).toFixed(2)}</div>
                        <div className="col-span-2 text-sm text-slate-700">
                          {formatMoney(Number(li.cost || 0), versions.find(v => v.id === selectedVersionId)?.currency)}
                        </div>
                      </div>
                    ))}
                  </div>

                  <div className="px-4 py-2 bg-white border-t border-slate-100 text-xs text-slate-500">
                    Note: Resource lines are aggregated by <span className="font-semibold">line item title</span>. Role is optional.
                  </div>
                </div>
              ) : applySummary.role_totals.length === 0 ? (
                <div className="p-4 rounded-xl border border-dashed border-slate-200 text-sm text-slate-500">
                  No role totals found.
                </div>
              ) : (
                <div className="border border-slate-200 rounded-xl overflow-hidden">
                  <div className="grid grid-cols-12 gap-2 px-4 py-2 bg-slate-50 text-[11px] font-bold text-slate-600">
                    <div className="col-span-4">Line item</div>
                    <div className="col-span-3">Hours</div>
                    <div className="col-span-2">Rate</div>
                    <div className="col-span-3">Cost</div>
                  </div>
                  {applySummary.role_totals.map((r) => (
                    <div key={r.role} className="grid grid-cols-12 gap-2 px-4 py-3 border-t border-slate-100">
                      <div className="col-span-4 text-sm font-semibold text-slate-900">{r.role}</div>
                      <div className="col-span-3 text-sm text-slate-700">{Number(r.hours || 0).toFixed(2)}</div>
                      <div className="col-span-2 text-sm text-slate-700">{Number(r.rate || 0).toFixed(2)}</div>
                      <div className="col-span-3 text-sm text-slate-700">{formatMoney(Number(r.cost || 0), versions.find(v => v.id === selectedVersionId)?.currency)}</div>
                    </div>
                  ))}
                </div>
              )}

              <div className="flex justify-end gap-2">
                <Button
                  variant="outline"
                  onClick={refreshApplySummary}
                  disabled={applyApplying || applyLoading}
                  title="Re-load the latest submitted PM revisions"
                >
                  <RefreshCcw className="w-4 h-4 mr-2" />
                  Refresh
                </Button>
                <Button variant="outline" onClick={() => setApplyOpen(false)} disabled={applyApplying}>
                  Close
                </Button>
                <Button
                  className="bg-indigo-600 hover:bg-indigo-700 text-white"
                  onClick={applyToEstimate}
                  disabled={applyApplying || applySummary.included_reviews.length === 0}
                >
                  {applyApplying ? 'Applying…' : 'Apply to Estimate'}
                </Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      <Dialog open={revisionDialogOpen} onOpenChange={setRevisionDialogOpen}>
        <DialogContent className="sm:max-w-xl">
          <DialogHeader>
            <DialogTitle>Request Revision</DialogTitle>
          </DialogHeader>

          <div className="space-y-3">
            <div className="text-sm text-slate-600">
              Add notes for the PM to revise their estimate.
            </div>
            <div className="space-y-1.5">
              <label className="text-sm font-medium text-slate-700">Notes</label>
              <textarea
                className="w-full bg-white border border-slate-200 rounded-lg p-3 text-sm min-h-[120px] focus:ring-2 focus:ring-indigo-500 outline-none"
                value={revisionNotes}
                onChange={(e) => setRevisionNotes(e.target.value)}
                placeholder="e.g. Please re-check integration effort and adjust hours for QA + UAT…"
              />
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => setRevisionDialogOpen(false)}>
                Cancel
              </Button>
              <Button
                className="bg-indigo-600 hover:bg-indigo-700 text-white"
                onClick={requestRevision}
                disabled={revisionSaving}
              >
                {revisionSaving ? 'Sending…' : 'Send Request'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </Card>
  );
};
