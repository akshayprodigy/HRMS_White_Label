import React, { useEffect, useMemo, useState } from 'react';
import {
  ClipboardList,
  RefreshCcw,
  Search,
  Plus,
  Trash2,
  Save,
  Send,
  ChevronRight,
} from 'lucide-react';
import { toast } from 'sonner';

import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';
import { Badge, Button, Card, Input, cn } from './ui-elements';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from './ui/dialog';

type ReviewStatus = 'DRAFT' | 'SUBMITTED' | string;

type AttachedDocument = {
  id: number;
  file_name: string;
  mime_type: string;
  file_size: number;
  uploaded_at: string;
  download_url: string;
};

type MyBidRequestItem = {
  lead_id: number;
  lead_title: string;
  lead_code: string;
  estimate_version_id: number;
  bid_task_id: number;
  bid_task_title: string;
  bd_estimated_hours?: number | null;
  bd_estimated_cost?: number | null;
  assignment_id: number;
  deadline?: string | null;
  latest_review_status: ReviewStatus;
  latest_revision_number: number;
  updated_at: string;
  documents?: AttachedDocument[];
};

type ReviewLine = {
  title: string;
  role?: string | null;
  description?: string | null;
  hours: number;
  cost: number;
  sort_order: number;
};

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

  lines: Array<ReviewLine & { id?: number; review_id?: number }>;
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

const StatusBadge = ({ status }: { status: ReviewStatus }) => {
  const normalized = String(status || '').toUpperCase();
  const tone =
    normalized === 'PENDING'
      ? 'info'
      :
    normalized === 'SUBMITTED' || normalized === 'RESUBMITTED'
      ? 'success'
      : normalized === 'REVISION_REQUESTED'
        ? 'danger'
        : 'warning';
  return (
    <Badge
      className={cn(
        'text-[10px] px-2 py-0.5 font-bold tracking-wide border',
        tone === 'info'
          ? 'bg-sky-50 text-sky-700 border-sky-200'
          : tone === 'success'
          ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
          : tone === 'danger'
            ? 'bg-rose-50 text-rose-700 border-rose-200'
            : 'bg-amber-50 text-amber-700 border-amber-200',
      )}
    >
      {normalized}
    </Badge>
  );
};

export const PMBidRequestsView = () => {
  const [loading, setLoading] = useState(true);
  const [items, setItems] = useState<MyBidRequestItem[]>([]);
  const [query, setQuery] = useState('');
  const [sortOrder, setSortOrder] = useState<'latest' | 'oldest'>('latest');
  const [columnQueries, setColumnQueries] = useState<Record<string, string>>({});

  const [workspaceOpen, setWorkspaceOpen] = useState(false);

  const [selected, setSelected] = useState<MyBidRequestItem | null>(null);
  const [reviewLoading, setReviewLoading] = useState(false);
  const [review, setReview] = useState<LeadBidTaskReviewRead | null>(null);

  const [pmNotes, setPmNotes] = useState('');
  const [lines, setLines] = useState<ReviewLine[]>([]);
  const [saving, setSaving] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const openAttachedDocument = async (doc: AttachedDocument) => {
    try {
      const res = await client.get(doc.download_url, { responseType: 'blob' });
      const blobUrl = URL.createObjectURL(res.data as any);
      window.open(blobUrl, '_blank', 'noopener,noreferrer');
      window.setTimeout(() => URL.revokeObjectURL(blobUrl), 60_000);
    } catch (error: any) {
      console.error('Failed to open document', error);
      const msg =
        error?.response?.data?.error?.message ||
        error?.response?.data?.detail ||
        'Failed to open document';
      toast.error(msg);
    }
  };

  const computedTotals = useMemo(() => {
    const totalHours = lines.reduce((sum, l) => sum + Number(l.hours || 0), 0);
    const totalCost = lines.reduce((sum, l) => sum + Number(l.cost || 0), 0);
    return {
      totalHours: Number.isFinite(totalHours) ? totalHours : 0,
      totalCost: Number.isFinite(totalCost) ? totalCost : 0,
    };
  }, [lines]);

  const workflowStatus = useMemo((): ReviewStatus => {
    const base = String(review?.status || '').toUpperCase().trim();
    const rev = Number(review?.revision_number || 0);
    if (!review || rev <= 0) return 'PENDING';
    if (base === 'DRAFT' && rev > 1) return 'REVISION_REQUESTED';
    if (base === 'SUBMITTED' && rev > 1) return 'RESUBMITTED';
    return base || 'DRAFT';
  }, [review]);

  const loadItems = async () => {
    const res = await client.get<MyBidRequestItem[]>(ENDPOINTS.BD.BID_TASKS.MY_REQUESTS);
    setItems(res.data || []);
  };

  const refresh = async () => {
    setLoading(true);
    try {
      await loadItems();
    } catch (error: any) {
      console.error('Failed to load bid requests', error);
      const msg =
        error?.response?.data?.error?.message ||
        error?.response?.data?.detail ||
        'Failed to load bid requests';
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
  }, []);

  const globalFiltered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return items;
    return items.filter((i) => {
      return (
        (i.lead_title || '').toLowerCase().includes(q) ||
        (i.lead_code || '').toLowerCase().includes(q) ||
        (i.bid_task_title || '').toLowerCase().includes(q)
      );
    });
  }, [items, query]);

  const sorted = useMemo(() => {
    const list = globalFiltered.slice();
    list.sort((a, b) => {
      const at = new Date(a.updated_at).getTime();
      const bt = new Date(b.updated_at).getTime();
      if (Number.isFinite(at) && Number.isFinite(bt)) {
        return sortOrder === 'latest' ? bt - at : at - bt;
      }
      return sortOrder === 'latest'
        ? String(b.updated_at).localeCompare(String(a.updated_at))
        : String(a.updated_at).localeCompare(String(b.updated_at));
    });
    return list;
  }, [globalFiltered, sortOrder]);

  const statusColumns = useMemo(() => {
    const normalize = (value: unknown) => {
      const s = String(value || '').toUpperCase().trim();
      if (!s) return 'DRAFT';
      if (s === 'SUBMITTED') return 'SUBMITTED';
      if (s === 'DRAFT') return 'DRAFT';
      return s;
    };

    const derivedColumnKey = (row: MyBidRequestItem) => {
      const base = normalize(row.latest_review_status);
      const rev = Number(row.latest_revision_number || 0);
      // Assignments should show up even before a review exists.
      if (rev <= 0) return 'PENDING';
      if (base === 'DRAFT' && rev > 1) return 'REVISION_REQUESTED';
      if (base === 'SUBMITTED' && rev > 1) return 'RESUBMITTED';
      return base;
    };

    const formatTitle = (key: string) => {
      if (key === 'PENDING') return 'Pending';
      if (key === 'DRAFT') return 'Draft';
      if (key === 'SUBMITTED') return 'Submitted';
      if (key === 'REVISION_REQUESTED') return 'Revision Requested';
      if (key === 'RESUBMITTED') return 'Resubmitted';
      return key
        .toLowerCase()
        .split('_')
        .filter(Boolean)
        .map((p) => p.charAt(0).toUpperCase() + p.slice(1))
        .join(' ');
    };

    const groups = new Map<string, MyBidRequestItem[]>();
    for (const row of sorted) {
      const key = derivedColumnKey(row);
      const bucket = groups.get(key) || [];
      bucket.push(row);
      groups.set(key, bucket);
    }

    // Always show the primary workflow columns (even if empty).
    const primaryOrder = [
      'PENDING',
      'DRAFT',
      'REVISION_REQUESTED',
      'SUBMITTED',
      'RESUBMITTED',
    ];
    const keys = Array.from(new Set([...primaryOrder, ...groups.keys()]));
    const ordered: string[] = [];
    for (const k of primaryOrder) {
      if (keys.includes(k)) ordered.push(k);
    }
    keys
      .filter((k) => !primaryOrder.includes(k))
      .sort()
      .forEach((k) => ordered.push(k));

    return ordered.map((key) => ({
      key,
      title: formatTitle(key),
      items: groups.get(key) || [],
    }));
  }, [sorted]);

  const setColumnQuery = (statusKey: string, value: string) => {
    setColumnQueries((prev) => ({ ...prev, [statusKey]: value }));
  };

  const loadLatestReview = async (row: MyBidRequestItem) => {
    setSelected(row);
    setWorkspaceOpen(true);
    setReviewLoading(true);
    setReview(null);

    try {
      const res = await client.get<LeadBidTaskReviewRead>(
        ENDPOINTS.BD.BID_TASKS.ASSIGNMENT_LATEST_REVIEW(row.assignment_id),
        {
          params: {
            estimate_version_id: row.estimate_version_id,
          },
        },
      );

      const data = res.data as any;
      setReview(data);
      setPmNotes(data?.pm_notes || '');
      setLines(
        Array.isArray(data?.lines)
          ? data.lines
              .slice()
              .sort((a: any, b: any) => (a.sort_order ?? 0) - (b.sort_order ?? 0))
              .map((l: any, idx: number) => ({
                title: l.title || '',
                role: l.role ?? null,
                description: l.description ?? null,
                hours: Number(l.hours || 0),
                cost: Number(l.cost || 0),
                sort_order: Number.isFinite(l.sort_order) ? l.sort_order : idx,
              }))
          : [],
      );
    } catch (error: any) {
      console.error('Failed to load latest review', error);
      const msg =
        error?.response?.data?.error?.message ||
        error?.response?.data?.detail ||
        'Failed to load latest review';
      toast.error(msg);
    } finally {
      setReviewLoading(false);
    }
  };

  const canEdit = useMemo(() => {
    const status = String(review?.status || '').toUpperCase();
    return !!review && status !== 'SUBMITTED';
  }, [review]);

  const addLine = () => {
    setLines((prev) => [
      ...prev,
      {
        title: '',
        role: null,
        description: null,
        hours: 0,
        cost: 0,
        sort_order: prev.length,
      },
    ]);
  };

  const removeLine = (index: number) => {
    setLines((prev) => prev.filter((_, i) => i !== index).map((l, i) => ({ ...l, sort_order: i })));
  };

  const updateLine = (index: number, patch: Partial<ReviewLine>) => {
    setLines((prev) =>
      prev.map((l, i) => (i === index ? { ...l, ...patch } : l)),
    );
  };

  const validateDraft = () => {
    const trimmed = lines.map((l) => ({
      ...l,
      title: l.title.trim(),
      role: (l.role || '').trim() || null,
    }));
    for (const l of trimmed) {
      if (!l.title) {
        toast.error('Line item title is required');
        return null;
      }
      if (!Number.isFinite(l.hours) || l.hours < 0) {
        toast.error('Hours must be 0 or more');
        return null;
      }
      if (!Number.isFinite(l.cost) || l.cost < 0) {
        toast.error('Cost must be 0 or more');
        return null;
      }
    }
    return trimmed;
  };

  const saveDraft = async () => {
    if (!selected || !review) return;
    if (!canEdit) {
      toast.error('This review is already submitted');
      return;
    }

    const validated = validateDraft();
    if (!validated) return;

    setSaving(true);
    try {
      const payload = {
        pm_notes: pmNotes.trim() || null,
        lines: validated.map((l, idx) => ({
          title: l.title,
          role: (l.role || '').trim() || null,
          description: l.description?.trim() || null,
          hours: Number(l.hours || 0),
          cost: Number(l.cost || 0),
          sort_order: idx,
        })),
      };

      const res = await client.put<LeadBidTaskReviewRead>(
            ENDPOINTS.BD.BID_TASKS.REVIEW_UPDATE(review.id),
            payload,
      );

      setReview(res.data);
      toast.success('Draft saved');
      await loadItems();
    } catch (error: any) {
      console.error('Failed to save draft', error);
      const msg =
        error?.response?.data?.error?.message ||
        error?.response?.data?.detail ||
        'Failed to save draft';
      toast.error(msg);
    } finally {
      setSaving(false);
    }
  };

  const submitReview = async () => {
    if (!selected || !review) return;
    if (!canEdit) {
      toast.error('This review is already submitted');
      return;
    }

    const validated = validateDraft();
    if (!validated) return;

    setSubmitting(true);
    try {
      // Ensure latest draft is persisted before submit.
      const payload = {
        pm_notes: pmNotes.trim() || null,
        lines: validated.map((l, idx) => ({
          title: l.title,
          role: (l.role || '').trim() || null,
          description: l.description?.trim() || null,
          hours: Number(l.hours || 0),
          cost: Number(l.cost || 0),
          sort_order: idx,
        })),
      };

      const upsert = await client.put<LeadBidTaskReviewRead>(
        ENDPOINTS.BD.BID_TASKS.REVIEW_UPDATE(review.id),
        payload,
      );

      const updated = upsert.data;
      setReview(updated);

      await client.post(
        ENDPOINTS.BD.BID_TASKS.REVIEW_SUBMIT(updated.id),
      );

      toast.success('Submitted to BD');
      await Promise.all([loadItems(), loadLatestReview(selected)]);
    } catch (error: any) {
      console.error('Failed to submit', error);
      const msg =
        error?.response?.data?.error?.message ||
        error?.response?.data?.detail ||
        'Failed to submit';
      toast.error(msg);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="p-6 max-w-[1400px] mx-auto animate-in fade-in slide-in-from-bottom-2 duration-300">
      <div className="flex items-start justify-between gap-4 mb-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
            <ClipboardList className="w-6 h-6 text-indigo-600" />
            My Bid Requests
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Review tasks assigned by BD, provide detailed line items, and submit estimates.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-500">Sort</span>
            <select
              className="h-10 px-3 rounded-md border border-slate-200 focus:ring-2 focus:ring-indigo-500 text-sm bg-white"
              value={sortOrder}
              onChange={(e) => setSortOrder(e.target.value as any)}
              aria-label="Sort bid requests"
            >
              <option value="latest">Latest</option>
              <option value="oldest">Oldest</option>
            </select>
          </div>

          <Button
            variant="outline"
            className="flex items-center gap-2"
            onClick={refresh}
            disabled={loading}
          >
            <RefreshCcw className="w-4 h-4" />
            Refresh
          </Button>
        </div>
      </div>

      <Card className="p-5 mb-6">
        <div className="flex items-center gap-2">
          <Search className="w-4 h-4 text-slate-400" />
          <Input
            placeholder="Search leads or tasks…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
      </Card>

      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-bold text-slate-900">Requests Board</h2>
          <p className="text-xs text-slate-500">Click a card to open workspace</p>
        </div>

        {loading ? (
          <Card className="p-10 flex flex-col items-center justify-center text-slate-400">
            <div className="w-10 h-10 border-4 border-indigo-600 border-t-transparent rounded-full animate-spin mb-3" />
            <p className="text-sm">Loading requests…</p>
          </Card>
        ) : statusColumns.length === 0 ? (
          <Card className="p-10 text-center text-slate-400 border border-dashed border-slate-200 rounded-xl">
            <ClipboardList className="w-12 h-12 mx-auto mb-3 opacity-20" />
            <p className="text-sm">No bid requests found.</p>
          </Card>
        ) : (
          <div className="space-y-6 overflow-x-auto pb-6">
            <div className="flex gap-4 min-w-[1400px]">
              {statusColumns.map((col) => {
                const colQuery = (columnQueries[col.key] || '').trim().toLowerCase();
                const colItems = !colQuery
                  ? col.items
                  : col.items.filter((i) => {
                      return (
                        (i.lead_title || '').toLowerCase().includes(colQuery) ||
                        (i.lead_code || '').toLowerCase().includes(colQuery) ||
                        (i.bid_task_title || '').toLowerCase().includes(colQuery)
                      );
                    });

                return (
                  <div key={col.key} className="flex-1 min-w-[280px] flex flex-col gap-4">
                    <div className="flex items-center justify-between px-1">
                      <div className="flex items-center gap-2 min-w-0">
                        <StatusBadge status={col.key} />
                        <span className="text-xs font-bold text-slate-400 bg-slate-100 px-2 py-0.5 rounded-full">
                          {col.items.length}
                        </span>
                        <span className="text-sm font-semibold text-slate-900 truncate">
                          {col.title}
                        </span>
                      </div>
                    </div>

                    <div className="bg-slate-50/50 p-2 rounded-xl border border-dashed border-slate-200 min-h-[520px] flex flex-col gap-3">
                      <div className="flex items-center gap-2 bg-white rounded-lg border border-slate-200 px-3 py-2">
                        <Search className="w-4 h-4 text-slate-400" />
                        <Input
                          placeholder="Search…"
                          value={columnQueries[col.key] || ''}
                          onChange={(e) => setColumnQuery(col.key, e.target.value)}
                          className="h-8 border-0 focus-visible:ring-0 shadow-none px-0"
                        />
                      </div>

                      {colItems.length === 0 ? (
                        <div className="flex-1 flex flex-col items-center justify-center text-slate-300 py-10">
                          <Plus className="w-8 h-8 opacity-20 mb-2" />
                          <p className="text-xs font-medium">No requests</p>
                        </div>
                      ) : (
                        colItems.map((row) => {
                          const isActive = selected?.assignment_id === row.assignment_id;
                          const docCount = Array.isArray(row.documents) ? row.documents.length : 0;
                          return (
                            <Card
                              key={`${row.assignment_id}_${row.estimate_version_id}`}
                              className={cn(
                                'p-3 hover:border-indigo-300 transition-all cursor-pointer group shadow-sm bg-white',
                                isActive && 'border-indigo-300 ring-1 ring-indigo-100',
                              )}
                              onClick={() => loadLatestReview(row)}
                            >
                              <p className="text-xs font-bold text-slate-900 group-hover:text-indigo-600 transition-colors mb-2 line-clamp-1">
                                {row.lead_title}
                              </p>
                              <div className="flex items-center gap-1.5 text-[10px] text-slate-500 mb-1.5">
                                <span className="font-semibold text-slate-600">{row.lead_code}</span>
                                <span className="text-slate-300">•</span>
                                <span className="line-clamp-1">{row.bid_task_title}</span>
                              </div>
                              <div className="flex flex-wrap items-center gap-2 text-[10px] text-slate-500 mb-3">
                                {row.bd_estimated_hours ? (
                                  <span>BD: <span className="font-semibold text-slate-600">{row.bd_estimated_hours}h</span></span>
                                ) : null}
                                {row.bd_estimated_cost ? (
                                  <span>Est: <span className="font-semibold text-slate-600">{formatMoney(row.bd_estimated_cost)}</span></span>
                                ) : null}
                                {row.deadline ? (() => {
                                  const dl = new Date(row.deadline);
                                  const overdue = dl < new Date();
                                  return (
                                    <span className={overdue ? 'text-red-600 font-semibold' : ''}>
                                      Due: {dl.toLocaleDateString()}
                                      {overdue ? ' (overdue)' : ''}
                                    </span>
                                  );
                                })() : null}
                              </div>
                              <div className="flex items-center justify-between pt-2 border-t border-slate-50">
                                <div className="flex items-center gap-2">
                                  <Badge className="text-[10px] px-2 py-0.5 bg-slate-100 text-slate-700 border-slate-200">
                                    Rev #{row.latest_revision_number}
                                  </Badge>
                                  {docCount > 0 ? (
                                    <Badge className="text-[10px] px-2 py-0.5 bg-indigo-50 text-indigo-700 border-indigo-200">
                                      Docs {docCount}
                                    </Badge>
                                  ) : null}
                                  <span className="text-[10px] text-slate-500">V#{row.estimate_version_id}</span>
                                </div>
                                <div className="text-[10px] text-slate-500 flex items-center gap-1">
                                  Open <ChevronRight className="w-3 h-3" />
                                </div>
                              </div>
                            </Card>
                          );
                        })
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>

      <Dialog
        open={workspaceOpen}
        onOpenChange={(open: boolean) => {
          setWorkspaceOpen(open);
          if (!open) {
            setReviewLoading(false);
            setSaving(false);
            setSubmitting(false);
          }
        }}
      >
        <DialogContent
          className="max-w-[1100px] p-0"
          style={{ maxHeight: '85vh', maxWidth: '1100px' }}
        >
          <div className="flex flex-col max-h-[85vh] min-h-0">
            <DialogHeader className="p-4 border-b border-slate-200 bg-white pr-12">
              <DialogTitle className="text-base">Task Workspace</DialogTitle>
              <DialogDescription className="text-xs">
                Add subtasks with hours/cost, then submit to BD.
              </DialogDescription>
            </DialogHeader>

            {!selected ? (
              <div className="p-10 text-center text-slate-400">
                <ClipboardList className="w-12 h-12 mx-auto mb-3 opacity-20" />
                <p className="text-sm">Select a bid request to open workspace.</p>
              </div>
            ) : reviewLoading ? (
              <div className="p-10 flex flex-col items-center justify-center text-slate-400">
                <div className="w-10 h-10 border-4 border-indigo-600 border-t-transparent rounded-full animate-spin mb-3" />
                <p className="text-sm">Opening workspace…</p>
              </div>
            ) : !review ? (
              <div className="p-10 text-center text-slate-400">
                <p className="text-sm">Workspace not available for this request.</p>
              </div>
            ) : (
              <>
                <div className="flex-1 min-h-0 overflow-y-auto bg-slate-50">
                  <div className="p-4 border-b border-slate-200 bg-white sticky top-0 z-10 pr-12">
                    <div className="flex items-start justify-between gap-4">
                      <div className="min-w-0">
                        <p className="text-xs text-slate-500">{selected.lead_code} • Version #{selected.estimate_version_id}</p>
                        <p className="text-base font-bold text-slate-900 truncate">{selected.lead_title}</p>
                        <p className="text-xs text-slate-500 mt-1 truncate">
                          {selected.bid_task_title}
                        </p>
                        <div className="flex flex-wrap items-center gap-3 mt-1.5 text-xs text-slate-500">
                          {selected.bd_estimated_hours ? (
                            <span>BD Est: <span className="font-semibold text-slate-700">{selected.bd_estimated_hours}h</span></span>
                          ) : null}
                          {selected.bd_estimated_cost ? (
                            <span>BD Cost: <span className="font-semibold text-slate-700">{formatMoney(selected.bd_estimated_cost)}</span></span>
                          ) : null}
                          {selected.deadline ? (() => {
                            const dl = new Date(selected.deadline);
                            const overdue = dl < new Date();
                            return (
                              <span className={overdue ? 'text-red-600 font-semibold' : ''}>
                                Deadline: {dl.toLocaleDateString()}{overdue ? ' (OVERDUE)' : ''}
                              </span>
                            );
                          })() : null}
                        </div>

                        {Array.isArray(selected.documents) && selected.documents.length > 0 ? (
                          <div className="mt-3">
                            <p className="text-[11px] font-bold text-slate-600">Attached documents</p>
                            <div className="mt-2 flex flex-wrap gap-2">
                              {selected.documents.map((d) => (
                                <Button
                                  key={d.id}
                                  size="sm"
                                  variant="outline"
                                  className="h-8"
                                  onClick={() => openAttachedDocument(d)}
                                  title="Open document"
                                >
                                  {d.file_name}
                                </Button>
                              ))}
                            </div>
                          </div>
                        ) : null}
                      </div>

                      <div className="flex flex-col items-end gap-2 shrink-0">
                        <div className="flex items-center gap-2">
                          <StatusBadge status={workflowStatus} />
                          <Badge className="text-[10px] px-2 py-0.5 bg-slate-100 text-slate-700 border-slate-200">
                            Rev #{review.revision_number}
                          </Badge>
                        </div>

                        <div className="flex items-center gap-2">
                          <Button
                            size="sm"
                            variant="outline"
                            className="flex items-center gap-2"
                            onClick={saveDraft}
                            disabled={!canEdit || saving}
                          >
                            <Save className="w-4 h-4" />
                            {saving ? 'Saving…' : 'Save'}
                          </Button>
                          <Button
                            size="sm"
                            className="bg-indigo-600 hover:bg-indigo-700 text-white flex items-center gap-2"
                            onClick={submitReview}
                            disabled={!canEdit || submitting}
                          >
                            <Send className="w-4 h-4" />
                            {submitting ? 'Submitting…' : 'Submit'}
                          </Button>
                        </div>
                      </div>
                    </div>

                    {String(workflowStatus).toUpperCase() === 'SUBMITTED' ||
                    String(workflowStatus).toUpperCase() === 'RESUBMITTED' ? (
                      <div className="mt-3 text-xs text-slate-500 italic">
                        This revision is submitted. Wait for BD revision request.
                      </div>
                    ) : null}
                  </div>

                  <div className="p-4">
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                    <div className="p-3 rounded-xl bg-white border border-slate-200">
                      <p className="text-[11px] text-slate-500">Current hours</p>
                      <p className="text-sm font-bold text-slate-900">{computedTotals.totalHours.toFixed(2)}</p>
                    </div>
                    <div className="p-3 rounded-xl bg-white border border-slate-200">
                      <p className="text-[11px] text-slate-500">Current cost</p>
                      <p className="text-sm font-bold text-slate-900">
                        {formatMoney(computedTotals.totalCost, review.currency)}
                      </p>
                    </div>
                    <div className="p-3 rounded-xl bg-white border border-slate-200">
                      <p className="text-[11px] text-slate-500">Currency</p>
                      <p className="text-sm font-bold text-slate-900">{review.currency}</p>
                    </div>
                  </div>

                  {review.bd_notes ? (
                    <div className="mt-4 p-4 rounded-xl border border-indigo-100 bg-indigo-50">
                      <p className="text-xs font-bold text-indigo-700">BD Notes</p>
                      <p className="text-sm text-indigo-900 mt-1 whitespace-pre-wrap">{review.bd_notes}</p>
                    </div>
                  ) : null}

                  <div className="mt-4 space-y-1.5">
                    <label className="text-sm font-semibold text-slate-800">PM Notes</label>
                    <textarea
                      className={cn(
                        'w-full bg-white border border-slate-200 rounded-xl p-3 text-sm min-h-[90px] focus:ring-2 focus:ring-indigo-500 outline-none',
                        !canEdit && 'bg-slate-100',
                      )}
                      value={pmNotes}
                      onChange={(e) => setPmNotes(e.target.value)}
                      placeholder="Add context, assumptions, and delivery approach…"
                      disabled={!canEdit}
                    />
                  </div>

                  <div className="mt-5 flex items-center justify-between gap-3">
                    <div>
                      <h3 className="text-sm font-bold text-slate-900">Subtasks</h3>
                      <p className="text-xs text-slate-500 mt-0.5">Add items with hours and cost.</p>
                    </div>
                    <Button
                      size="sm"
                      variant="outline"
                      className="flex items-center gap-2"
                      onClick={addLine}
                      disabled={!canEdit}
                    >
                      <Plus className="w-4 h-4" />
                      Add Subtask
                    </Button>
                  </div>

                  {lines.length === 0 ? (
                    <div className="mt-3 py-10 text-center text-slate-400 border border-dashed border-slate-200 rounded-xl bg-white">
                      <p className="text-sm">No subtasks yet.</p>
                      <p className="text-xs mt-1">Add at least one before submitting.</p>
                    </div>
                  ) : (
                    <div className="mt-3 space-y-3">
                      {lines.map((l, idx) => (
                        <div key={idx} className="p-3 rounded-xl border border-slate-200 bg-white">
                          <div className="grid grid-cols-12 gap-2 items-start">
                            <div className="col-span-12 md:col-span-5 space-y-1">
                              <label className="text-[11px] font-semibold text-slate-600">Title</label>
                              <Input
                                value={l.title}
                                onChange={(e) => updateLine(idx, { title: e.target.value })}
                                placeholder="e.g. Backend API wiring"
                                disabled={!canEdit}
                              />
                            </div>

                            <div className="col-span-6 md:col-span-2 space-y-1">
                              <label className="text-[11px] font-semibold text-slate-600">Role (optional)</label>
                              <Input
                                value={String(l.role || '')}
                                onChange={(e) => updateLine(idx, { role: e.target.value })}
                                placeholder="e.g. Backend"
                                disabled={!canEdit}
                              />
                            </div>

                            <div className="col-span-3 md:col-span-2 space-y-1">
                              <label className="text-[11px] font-semibold text-slate-600">Hours</label>
                              <Input
                                type="number"
                                value={String(l.hours)}
                                onChange={(e) => updateLine(idx, { hours: Number(e.target.value) })}
                                disabled={!canEdit}
                              />
                            </div>

                            <div className="col-span-3 md:col-span-2 space-y-1">
                              <label className="text-[11px] font-semibold text-slate-600">Cost</label>
                              <Input
                                type="number"
                                value={String(l.cost)}
                                onChange={(e) => updateLine(idx, { cost: Number(e.target.value) })}
                                disabled={!canEdit}
                              />
                            </div>

                            <div className="col-span-12 md:col-span-1 flex md:justify-end">
                              <Button
                                size="sm"
                                variant="outline"
                                className="mt-6"
                                onClick={() => removeLine(idx)}
                                disabled={!canEdit}
                                aria-label="Remove subtask"
                                title="Remove"
                              >
                                <Trash2 className="w-4 h-4" />
                              </Button>
                            </div>
                          </div>

                          <div className="mt-3 space-y-1">
                            <label className="text-[11px] font-semibold text-slate-600">Description</label>
                            <textarea
                              className={cn(
                                'w-full bg-white border border-slate-200 rounded-xl p-3 text-sm min-h-[70px] focus:ring-2 focus:ring-indigo-500 outline-none',
                                !canEdit && 'bg-slate-100',
                              )}
                              value={l.description || ''}
                              onChange={(e) => updateLine(idx, { description: e.target.value })}
                              placeholder="Notes / assumptions…"
                              disabled={!canEdit}
                            />
                          </div>
                        </div>
                      ))}
                    </div>
                  )}

                  <div className="mt-5 flex items-start justify-between gap-3">
                    <p className="text-xs text-slate-500">
                      Tip: Save frequently; Submit sends this revision to BD.
                    </p>
                  </div>
                  </div>
                </div>
              </>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};
