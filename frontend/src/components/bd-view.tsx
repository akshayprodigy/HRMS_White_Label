import React, { useState, useEffect, useMemo, useRef } from 'react';
import { 
  Users, 
  Search, 
  Filter, 
  Plus, 
  ChevronRight, 
  ChevronLeft,
  Phone, 
  Mail, 
  Calendar, 
  MessageSquare, 
  ArrowLeft,
  MoreVertical,
  Building2,
  FileText,
  Paperclip,
  Upload,
  ExternalLink,
  Trash2,
  Edit,
  LayoutGrid,
  List,
  Trophy,
  TrendingUp,
  Calculator,
  PlusCircle,
  X,
  XCircle,
  Briefcase,
  User as UserIcon
} from 'lucide-react';
import { Card, Button, Badge, Input, cn } from './ui-elements';
import { toast } from 'sonner';
import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';
import { EstimateWorkspace } from './estimate-view';
import type { UserRole } from '../types/erp';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from './ui/popover';
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from './ui/command';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from './ui/dialog';
import { ClientDetailsView } from './client-details-view';
import { LeadBidTasksPanel } from './lead-bid-tasks-panel';

// --- Types ---

interface ProjectConversionData {
  project_code: string;
  project_manager_id: number;
  start_date: string;
}

interface LeadDocument {
  id: number;
  lead_id: number;
  file_name: string;
  mime_type: string;
  file_size: number;
  uploaded_at: string;
  uploader_id: number;
  download_url?: string | null;
}

const formatBytes = (bytes: number) => {
  if (!bytes || bytes < 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'] as const;
  let size = bytes;
  let idx = 0;
  while (size >= 1024 && idx < units.length - 1) {
    size /= 1024;
    idx += 1;
  }
  return `${size.toFixed(idx === 0 ? 0 : 1)} ${units[idx]}`;
};

const LeadDocumentsModal = ({
  leadId,
  open,
  onOpenChange,
}: {
  leadId: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) => {
  const [docs, setDocs] = useState<LeadDocument[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [uploading, setUploading] = useState(false);

  const fetchDocs = async () => {
    setLoading(true);
    try {
      const res = await client.get<LeadDocument[]>(
        ENDPOINTS.BD.LEAD_DOCUMENTS(leadId),
      );
      setDocs(res.data || []);
    } catch (error: any) {
      toast.error(
        error.response?.data?.error?.message || 'Failed to load documents',
      );
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (open) {
      fetchDocs();
    } else {
      setSelectedFiles([]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, leadId]);

  const handleUpload = async () => {
    if (selectedFiles.length === 0) return;
    setUploading(true);
    try {
      const form = new FormData();
      selectedFiles.forEach((f) => form.append('files', f));
      await client.post(ENDPOINTS.BD.LEAD_DOCUMENTS(leadId), form);
      toast.success('Documents uploaded');
      setSelectedFiles([]);
      await fetchDocs();
    } catch (error: any) {
      toast.error(
        error.response?.data?.error?.message || 'Failed to upload documents',
      );
    } finally {
      setUploading(false);
    }
  };

  const handleOpenDoc = (docId: number) => {
    // Can't rely on Authorization headers in a new-tab navigation.
    // Fetch via axios (with Bearer token) as a Blob, then open.
    (async () => {
      try {
        const res = await client.get(
          ENDPOINTS.BD.LEAD_DOCUMENT_DOWNLOAD(leadId, docId),
          {
            responseType: 'blob',
          },
        );
        const blob = res.data as Blob;
        const blobUrl = window.URL.createObjectURL(blob);
        window.open(blobUrl, '_blank', 'noopener,noreferrer');
        // Best-effort cleanup.
        window.setTimeout(() => window.URL.revokeObjectURL(blobUrl), 60_000);
      } catch (error: any) {
        toast.error(
          error.response?.data?.error?.message || 'Failed to open document',
        );
      }
    })();
  };

  const handleDeleteDoc = async (docId: number) => {
    const ok = window.confirm('Delete this document?');
    if (!ok) return;
    try {
      await client.delete(ENDPOINTS.BD.LEAD_DOCUMENT_DELETE(leadId, docId));
      toast.success('Document deleted');
      await fetchDocs();
    } catch (error: any) {
      toast.error(
        error.response?.data?.error?.message || 'Failed to delete document',
      );
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="w-[95vw] sm:w-[60vw] sm:max-w-none">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Paperclip className="w-4 h-4 text-indigo-600" />
            Documents
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          <div className="flex flex-col sm:flex-row gap-3 sm:items-center">
            <div className="flex-1">
              <Input
                type="file"
                multiple
                onChange={(e: React.ChangeEvent<HTMLInputElement>) => {
                  setSelectedFiles(Array.from(e.target.files || []));
                }}
              />
              <div className="text-xs text-slate-500 mt-1">
                {selectedFiles.length > 0
                  ? `${selectedFiles.length} file(s) selected`
                  : 'Upload PDF, Word, images'}
              </div>
            </div>
            <Button
              type="button"
              onClick={handleUpload}
              disabled={uploading || selectedFiles.length === 0}
              className="bg-indigo-600 hover:bg-indigo-700 text-white flex items-center gap-2"
            >
              <Upload className="w-4 h-4" />
              {uploading ? 'Uploading...' : 'Upload'}
            </Button>
          </div>

          <div className="border border-slate-200 rounded-xl overflow-hidden">
            <div className="bg-slate-50 px-4 py-2 text-xs font-bold text-slate-600 flex items-center justify-between">
              <span>Files</span>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={fetchDocs}
                className="text-xs"
              >
                Refresh
              </Button>
            </div>

            {loading ? (
              <div className="p-6 text-sm text-slate-500">Loading…</div>
            ) : docs.length === 0 ? (
              <div className="p-6 text-sm text-slate-500">No documents yet.</div>
            ) : (
              <div className="divide-y divide-slate-100">
                {docs.map((d) => (
                  <div
                    key={d.id}
                    className="px-4 py-3 flex items-center justify-between gap-3"
                  >
                    <button
                      type="button"
                      className="text-left flex-1 min-w-0"
                      onClick={() => handleOpenDoc(d.id)}
                      title="Open in new tab"
                    >
                      <div className="flex items-center gap-2 min-w-0">
                        <FileText className="w-4 h-4 text-slate-500" />
                        <div className="font-medium text-slate-900 truncate">
                          {d.file_name}
                        </div>
                        <ExternalLink className="w-3.5 h-3.5 text-slate-400" />
                      </div>
                      <div className="text-xs text-slate-500 mt-1">
                        {formatBytes(d.file_size)} •{' '}
                        {d.mime_type || 'unknown'} •{' '}
                        {new Date(d.uploaded_at).toLocaleString()}
                      </div>
                    </button>

                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => handleDeleteDoc(d.id)}
                      className="flex items-center gap-2"
                      title="Delete"
                    >
                      <Trash2 className="w-4 h-4 text-red-600" />
                      <span className="text-red-600">Delete</span>
                    </Button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
};

const LEAD_STAGES = [
  'new',
  'qualified',
  'discovery',
  'proposal',
  'negotiation',
  'won',
  'lost',
] as const;

export type LeadStage = (typeof LEAD_STAGES)[number];

const ACTIVITY_TYPES = ['call', 'email', 'meeting', 'note'] as const;
type ActivityType = (typeof ACTIVITY_TYPES)[number];

export interface Activity {
  id: number;
  type: ActivityType;
  summary: string;
  notes?: string;
  created_at: string;
  created_by_name?: string;
}

export interface Account {
  id: number;
  name: string;
  industry?: string;
  domain?: string;
}

export interface Contact {
  id: number;
  first_name: string;
  last_name: string;
  email: string;
  phone?: string;
  job_title?: string;
}

export interface Lead {
  id: number;
  lead_id: string;
  title: string;
  stage: LeadStage;
  source?: string;
  estimated_value?: number;
  owner_user_id: number;
  owner_name?: string;
  created_at: string;
  updated_at: string;
  account?: Account;
  contact?: Contact;
  activities?: Activity[];
}

export interface PipelineStageSummary {
  stage: LeadStage;
  count: number;
  total_value: number;
  weighted_value: number;
}

export interface PipelineSummary {
  stages: PipelineStageSummary[];
  total_count: number;
  total_value: number;
  total_weighted_value: number;
}

export interface BDDashboardData {
  pipeline: PipelineSummary;
  expected_closes_this_month: number;
  win_count: number;
  loss_count: number;
  avg_sales_cycle_days: number;
  win_rate_percent: number;
}

const LEAD_STAGE_LABEL: Record<LeadStage, string> = {
  new: 'New',
  qualified: 'Qualified',
  discovery: 'Discovery',
  proposal: 'Proposal',
  negotiation: 'Negotiation',
  won: 'Won',
  lost: 'Lost',
};

const getLeadStageLabel = (stage: LeadStage) => LEAD_STAGE_LABEL[stage];

const normalizeLeadStage = (value: unknown): LeadStage => {
  if (typeof value !== 'string') return 'new';
  const normalized = value.toLowerCase();
  return (LEAD_STAGES as readonly string[]).includes(normalized)
    ? (normalized as LeadStage)
    : 'new';
};

const normalizeActivityType = (value: unknown): ActivityType => {
  if (typeof value !== 'string') return 'note';
  const normalized = value.toLowerCase();
  return (ACTIVITY_TYPES as readonly string[]).includes(normalized)
    ? (normalized as ActivityType)
    : 'note';
};

const normalizeLead = (value: any): Lead => {
  const lead = value || {};
  return {
    ...lead,
    stage: normalizeLeadStage(lead.stage),
    activities: Array.isArray(lead.activities)
      ? lead.activities.map((a: any) => ({
          ...a,
          type: normalizeActivityType(a.type),
        }))
      : lead.activities,
  } as Lead;
};

const LeadCreateForm = ({
  onClose,
  onSuccess,
  userRole = 'bd',
}: {
  onClose: () => void;
  onSuccess: () => void;
  userRole?: UserRole;
}) => {
  const [formData, setFormData] = useState({
    title: '',
    account_name: '',
    account_id: undefined as number | undefined,
    estimated_value: '',
    expected_close_date: new Date().toISOString().split('T')[0],
    source: 'REFERRAL',
    notes: ''
  });
  const [attachments, setAttachments] = useState<File[]>([]);
  const [loading, setLoading] = useState(false);
  const [clients, setClients] = useState<Account[]>([]);
  const [clientsLoading, setClientsLoading] = useState(false);
  const [clientPickerOpen, setClientPickerOpen] = useState(false);
  const [clientPickerQuery, setClientPickerQuery] = useState('');
  const [clientDetailsOpen, setClientDetailsOpen] = useState(false);

  useEffect(() => {
    const loadClients = async () => {
      setClientsLoading(true);
      try {
        const res = await client.get<Account[]>(ENDPOINTS.CLIENTS.LIST);
        setClients(res.data || []);
      } catch (error: any) {
        // Don't block lead creation; user can still type a new account.
        console.error('Failed to load clients', error);
      } finally {
        setClientsLoading(false);
      }
    };
    loadClients();
  }, []);

  const filteredClients = useMemo(() => {
    const q = clientPickerQuery.trim().toLowerCase();
    if (!q) return clients;
    return clients.filter((c) => (c.name || '').toLowerCase().includes(q));
  }, [clients, clientPickerQuery]);

  const setAccountName = (value: string) => {
    setClientPickerQuery(value);
    setFormData((prev) => {
      const nextName = value;

      // Command/Popover selection can trigger an input value update; don't
      // accidentally clear a valid selected client id in that case.
      const keepSelectedId =
        prev.account_id &&
        nextName.trim() === (prev.account_name || '').trim();

      return {
        ...prev,
        account_name: nextName,
        account_id: keepSelectedId ? prev.account_id : undefined,
      };
    });
  };

  const selectClient = (selected: Account) => {
    setClientPickerQuery(selected.name);
    setFormData((prev) => ({
      ...prev,
      account_name: selected.name,
      account_id: selected.id,
    }));
    setClientPickerOpen(false);
  };

  const handleViewClientDetails = () => {
    if (!formData.account_id) {
      toast.error('Select an existing client first');
      return;
    }

    localStorage.setItem(
      'client_details_selected_id',
      String(formData.account_id),
    );
    setClientDetailsOpen(true);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formData.account_name.trim()) {
      toast.error('Account name is required');
      return;
    }
    setLoading(true);
    try {
      const payload: any = { ...formData };
      if (!payload.account_id) {
        delete payload.account_id;
      }
      if (typeof payload.estimated_value === 'string') {
        const raw = payload.estimated_value.trim();
        if (!raw) {
          delete payload.estimated_value;
        } else {
          const parsed = Number(raw);
          if (Number.isNaN(parsed)) {
            delete payload.estimated_value;
          } else {
            payload.estimated_value = parsed;
          }
        }
      }
      const created = await client.post(ENDPOINTS.BD.LEADS, payload);

      const leadId = (created.data as any)?.id;
      if (leadId && attachments.length > 0) {
        try {
          const form = new FormData();
          attachments.forEach((file) => {
            form.append('files', file);
          });
          await client.post(ENDPOINTS.BD.LEAD_DOCUMENTS(leadId), form);
        } catch (uploadError: any) {
          toast.error(
            uploadError.response?.data?.error?.message ||
              'Lead created, but document upload failed',
          );
        }
      }

      toast.success('Lead created successfully');
      setAttachments([]);
      onSuccess();
    } catch (error: any) {
      toast.error(error.response?.data?.error?.message || 'Failed to create lead');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-slate-900/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <Card
        className="w-full max-w-lg bg-white shadow-2xl animate-in zoom-in-95 duration-200"
        style={{
          maxHeight: "70vh",
          overflowY: "auto",
          overscrollBehavior: "contain",
          WebkitOverflowScrolling: "touch",
        }}
      >
        <div className="p-6">
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-xl font-bold text-slate-900 flex items-center gap-2">
              <PlusCircle className="w-5 h-5 text-indigo-600" />
              Capture New Opportunity
            </h2>
            <button onClick={onClose} className="text-slate-400 hover:text-slate-600">
              <X className="w-5 h-5" />
            </button>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-1.5">
              <label className="text-sm font-medium text-slate-700">Lead Title</label>
              <Input 
                placeholder="e.g. Enterprise Cloud Migration" 
                value={formData.title}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) => setFormData({ ...formData, title: e.target.value })}
                required
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <label className="text-sm font-medium text-slate-700">Account Name</label>
                <Popover
                  open={clientPickerOpen}
                  onOpenChange={(open: boolean) => {
                    setClientPickerOpen(open);
                    if (open) setClientPickerQuery(formData.account_name);
                  }}
                >
                  <PopoverTrigger asChild>
                    <button
                      type="button"
                      className={cn(
                        'w-full h-10 px-3 rounded-md border border-slate-200 focus:ring-2 focus:ring-indigo-500 text-sm text-left',
                        !formData.account_name ? 'text-slate-400' : 'text-slate-900',
                      )}
                      aria-haspopup="listbox"
                      aria-expanded={clientPickerOpen}
                    >
                      {formData.account_name || 'Select or type company name'}
                    </button>
                  </PopoverTrigger>
                  <PopoverContent align="start" className="p-0 w-[340px]">
                    <Command>
                      <CommandInput
                        placeholder="Search clients or type a new one..."
                        value={clientPickerQuery}
                        onValueChange={(value: string) => setAccountName(value)}
                        autoFocus
                      />
                      <CommandList>
                        <CommandEmpty>
                          {clientsLoading
                            ? 'Loading clients…'
                            : 'No clients found'}
                        </CommandEmpty>
                        <CommandGroup heading="Use typed value">
                          <CommandItem
                            disabled={!clientPickerQuery.trim()}
                            onSelect={() => {
                              const typed = clientPickerQuery.trim();
                              if (!typed) return;
                              setAccountName(typed);
                              setClientPickerOpen(false);
                            }}
                          >
                            {clientPickerQuery.trim()
                              ? `Use "${clientPickerQuery.trim()}" (new client)`
                              : 'Type a company name to use it'}
                          </CommandItem>
                        </CommandGroup>
                        <CommandSeparator />
                        <CommandGroup heading="Existing clients">
                          {filteredClients.slice(0, 100).map((c) => (
                            <CommandItem
                              key={c.id}
                              onSelect={() => selectClient(c)}
                            >
                              {c.name}
                            </CommandItem>
                          ))}
                        </CommandGroup>
                      </CommandList>
                    </Command>
                  </PopoverContent>
                </Popover>
                {clientsLoading ? (
                  <p className="text-xs text-slate-400">Loading clients…</p>
                ) : null}

                <div className="pt-1">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={handleViewClientDetails}
                    disabled={!formData.account_id}
                    className="text-xs"
                  >
                    View Client Details
                  </Button>
                </div>
              </div>
              <div className="space-y-1.5">
                <label className="text-sm font-medium text-slate-700">Source</label>
                <select 
                  className="w-full h-10 px-3 rounded-md border border-slate-200 focus:ring-2 focus:ring-indigo-500 text-sm"
                  value={formData.source}
                  onChange={(e: React.ChangeEvent<HTMLSelectElement>) => setFormData({ ...formData, source: e.target.value })}
                >
                  <option value="REFERRAL">Referral</option>
                  <option value="COLD_OUTREACH">Cold Outreach</option>
                  <option value="MARKETING">Marketing</option>
                  <option value="PARTNER">Partner</option>
                  <option value="DIRECT">Direct</option>
                </select>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <label className="text-sm font-medium text-slate-700">Est. Value (₹)</label>
                <Input 
                  type="number"
                  value={formData.estimated_value}
                  placeholder=""
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                    setFormData({
                      ...formData,
                      estimated_value: e.target.value,
                    })
                  }
                />
              </div>
              <div className="space-y-1.5">
                <label className="text-sm font-medium text-slate-700">Expected Close</label>
                <Input 
                  type="date"
                  value={formData.expected_close_date}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => setFormData({ ...formData, expected_close_date: e.target.value })}
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <label className="text-sm font-medium text-slate-700">Strategic Notes</label>
              <textarea 
                className="w-full p-3 rounded-md border border-slate-200 focus:ring-2 focus:ring-indigo-500 text-sm min-h-[100px]"
                placeholder="Key drivers for this opportunity..."
                value={formData.notes}
                onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setFormData({ ...formData, notes: e.target.value })}
              />
            </div>

            <div className="space-y-1.5">
              <label className="text-sm font-medium text-slate-700">
                Attachments (optional)
              </label>
              <Input
                type="file"
                multiple
                onChange={(e: React.ChangeEvent<HTMLInputElement>) => {
                  const list = Array.from(e.target.files || []);
                  setAttachments(list);
                }}
              />
              {attachments.length > 0 ? (
                <div className="text-xs text-slate-600">
                  {attachments.length} file(s) selected
                </div>
              ) : (
                <div className="text-xs text-slate-400">
                  PDF, Word, images supported
                </div>
              )}
            </div>

            <div className="pt-4 flex gap-3">
              <Button type="button" variant="outline" onClick={onClose} className="flex-1">
                Discard
              </Button>
              <Button type="submit" disabled={loading} className="flex-1 bg-indigo-600 text-white">
                {loading ? "Capturing..." : "Create Opportunity"}
              </Button>
            </div>
          </form>
        </div>
      </Card>

      <Dialog open={clientDetailsOpen} onOpenChange={setClientDetailsOpen}>
        <DialogContent className="sm:max-w-5xl p-0">
          <DialogHeader className="px-6 pt-6">
            <DialogTitle>Client Details</DialogTitle>
          </DialogHeader>
          <div className="px-2 pb-6">
            <ClientDetailsView userRole={userRole} />
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export const BDView = ({ userRole = 'bd' }: { userRole?: UserRole }) => {
  const [leads, setLeads] = useState<Lead[]>([]);
  const [dashboard, setDashboard] = useState<BDDashboardData | null>(null);
  const [selectedLeadId, setSelectedLeadId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedStage, setSelectedStage] = useState<LeadStage | 'ALL'>('ALL');
  const [viewMode, setViewMode] = useState<'LIST' | 'BOARD' | 'DETAIL' | 'ESTIMATE' | 'REPORTS'>('BOARD');
  const [showLeadForm, setShowLeadForm] = useState(false);

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    setLoading(true);
    await Promise.all([fetchLeads(), fetchDashboard()]);
    setLoading(false);
  };

  const fetchLeads = async () => {
    try {
      const response = await client.get<Lead[]>(ENDPOINTS.BD.LEADS);
      setLeads((response.data || []).map(normalizeLead));
    } catch (error) {
      console.error('Failed to fetch leads:', error);
      toast.error('Failed to load leads');
    }
  };

  const fetchDashboard = async () => {
    try {
      const response = await client.get<BDDashboardData>(ENDPOINTS.BD.DASHBOARD);
      const data = response.data;
      if (!data) {
        setDashboard(null);
        return;
      }
      setDashboard({
        ...data,
        pipeline: {
          ...data.pipeline,
          stages: (data.pipeline?.stages || []).map((s: any) => ({
            ...s,
            stage: normalizeLeadStage(s.stage),
          })),
        },
      });
    } catch (error) {
      console.error('Failed to fetch dashboard:', error);
    }
  };

  const filteredLeads = useMemo(() => {
    return leads.filter((lead: Lead) => {
      const matchesSearch = lead.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
                          (lead.account?.name || '').toLowerCase().includes(searchQuery.toLowerCase()) ||
                          lead.lead_id.toLowerCase().includes(searchQuery.toLowerCase());
      const matchesStage = selectedStage === 'ALL' || lead.stage === selectedStage;
      return matchesSearch && matchesStage;
    });
  }, [leads, searchQuery, selectedStage]);

  const STAGES: LeadStage[] = [...LEAD_STAGES];
  // Stage step buttons (Prev/Next) intentionally stop at NEGOTIATION.
  // Winning requires PM assignment + conversion, handled via the conversion modal.
  const STAGE_FORWARD_FLOW: LeadStage[] = ['new', 'qualified', 'discovery', 'proposal', 'negotiation'];

  const getNextStage = (stage: LeadStage): LeadStage | null => {
    if (stage === 'won' || stage === 'lost') return null;
    const idx = STAGE_FORWARD_FLOW.indexOf(stage);
    if (idx < 0 || idx >= STAGE_FORWARD_FLOW.length - 1) return null;
    return STAGE_FORWARD_FLOW[idx + 1];
  };

  const getPrevStage = (stage: LeadStage): LeadStage | null => {
    if (stage === 'new') return null;
    if (stage === 'lost') return 'negotiation';
    const idx = STAGE_FORWARD_FLOW.indexOf(stage);
    if (idx <= 0) return null;
    return STAGE_FORWARD_FLOW[idx - 1];
  };

  const updateLeadStage = async (leadId: number, newStage: LeadStage) => {
    const previousStage = leads.find((l) => l.id === leadId)?.stage;
    setLeads((prev) =>
      prev.map((l) => (l.id === leadId ? { ...l, stage: newStage } : l)),
    );

    try {
      await client.patch(ENDPOINTS.BD.LEAD_DETAIL(leadId), { stage: newStage });
      toast.success(`Moved to ${getLeadStageLabel(newStage)}`);
      await fetchDashboard();
    } catch (error: any) {
      console.error('Failed to update stage', error);
      const msg =
        error?.response?.data?.error?.message ||
        error?.response?.data?.detail ||
        'Failed to update stage';
      toast.error(msg);
      if (previousStage) {
        setLeads((prev) =>
          prev.map((l) => (l.id === leadId ? { ...l, stage: previousStage } : l)),
        );
      } else {
        await fetchLeads();
      }
    }
  };

  const LeadQuickActions = ({ lead }: { lead: Lead }) => {
    const nextStage = getNextStage(lead.stage);
    const prevStage = getPrevStage(lead.stage);

    return (
      <Popover>
        <PopoverTrigger asChild>
          <button
            type="button"
            className="text-slate-400 hover:text-slate-900"
            title="Actions"
            onClick={(e) => e.stopPropagation()}
          >
            <MoreVertical className="w-4 h-4" />
          </button>
        </PopoverTrigger>
        <PopoverContent
          align="end"
          className="w-56 p-1"
          onClick={(e: React.MouseEvent) => e.stopPropagation()}
        >
          <button
            className="w-full text-left px-3 py-2 text-sm rounded-md hover:bg-slate-100"
            onClick={() => handleLeadClick(lead.id)}
          >
            Open lead
          </button>
          <button
            className={cn(
              'w-full text-left px-3 py-2 text-sm rounded-md',
              nextStage
                ? 'hover:bg-slate-100'
                : 'opacity-50 cursor-not-allowed',
            )}
            disabled={!nextStage}
            onClick={() => nextStage && updateLeadStage(lead.id, nextStage)}
          >
            Move to next stage
          </button>
          <button
            className={cn(
              'w-full text-left px-3 py-2 text-sm rounded-md',
              prevStage
                ? 'hover:bg-slate-100'
                : 'opacity-50 cursor-not-allowed',
            )}
            disabled={!prevStage}
            onClick={() => prevStage && updateLeadStage(lead.id, prevStage)}
          >
            Move to previous stage
          </button>

          <div className="h-px bg-slate-100 my-1" />
          <p className="px-3 py-1 text-[10px] font-black uppercase tracking-widest text-slate-400">
            Set Stage
          </p>
          {LEAD_STAGES.filter((s) => s !== 'won').map((s) => (
            <button
              key={s}
              className={cn(
                'w-full text-left px-3 py-2 text-sm rounded-md hover:bg-indigo-50',
                lead.stage === s
                  ? 'text-indigo-700 font-bold bg-indigo-50'
                  : 'text-slate-700',
              )}
              onClick={() => updateLeadStage(lead.id, s)}
            >
              {getLeadStageLabel(s)}
            </button>
          ))}
        </PopoverContent>
      </Popover>
    );
  };

  const LeadStageStepButtons = ({ lead }: { lead: Lead }) => {
    const nextStage = getNextStage(lead.stage);
    const prevStage = getPrevStage(lead.stage);

    return (
      <div className="flex items-center gap-1">
        <button
          type="button"
          title="Move to previous stage"
          className={cn(
            'h-7 w-7 rounded-md border border-slate-200 bg-slate-50/60 text-slate-700 flex items-center justify-center',
            prevStage
              ? 'hover:text-indigo-600 hover:border-indigo-200'
              : 'opacity-40 cursor-not-allowed',
          )}
          disabled={!prevStage}
          onClick={(e) => {
            e.stopPropagation();
            if (prevStage) updateLeadStage(lead.id, prevStage);
          }}
        >
          <ChevronLeft className="w-4 h-4" />
        </button>
        <button
          type="button"
          title="Move to next stage"
          className={cn(
            'h-7 w-7 rounded-md border border-slate-200 bg-slate-50/60 text-slate-700 flex items-center justify-center',
            nextStage
              ? 'hover:text-indigo-600 hover:border-indigo-200'
              : 'opacity-40 cursor-not-allowed',
          )}
          disabled={!nextStage}
          onClick={(e) => {
            e.stopPropagation();
            if (nextStage) updateLeadStage(lead.id, nextStage);
          }}
        >
          <ChevronRight className="w-4 h-4" />
        </button>
      </div>
    );
  };

  const getStageBadgeVariant = (stage: LeadStage): "success" | "warning" | "error" | "info" | "neutral" => {
    switch (stage) {
      case 'new': return 'info';
      case 'qualified': return 'info';
      case 'discovery': return 'warning';
      case 'proposal': return 'warning';
      case 'negotiation': return 'warning';
      case 'won': return 'success';
      case 'lost': return 'error';
      default: return 'neutral';
    }
  };

  const handleLeadClick = (id: number) => {
    setSelectedLeadId(id);
    setViewMode('DETAIL');
  };

  if (viewMode === 'DETAIL' && selectedLeadId) {
    return (
      <LeadDetailView 
        id={selectedLeadId} 
        onBack={() => setViewMode('BOARD')} 
        refreshLeads={fetchData} 
        onViewEstimates={() => setViewMode('ESTIMATE')}
      />
    );
  }

  if (viewMode === 'ESTIMATE' && selectedLeadId) {
    const lead = leads.find((l: Lead) => l.id === selectedLeadId);
    return (
      <EstimateWorkspace 
        leadId={selectedLeadId} 
        leadTitle={lead?.title}
        onLeadUpdated={fetchData}
        onBack={() => setViewMode('DETAIL')} 
      />
    );
  }

  if (viewMode === 'REPORTS') {
    return (
      <BDReportsView onBack={() => setViewMode('BOARD')} />
    );
  }

  return (
    <div className="p-6 space-y-6 max-w-[1600px] mx-auto">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Business Development</h1>
          <p className="text-slate-500">Manage pipeline, leads, and client interactions</p>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex bg-slate-100 p-1 rounded-lg mr-2">
            <button
              onClick={() => setViewMode('BOARD')}
              className={cn(
                "p-2 rounded-md transition-all",
                viewMode === 'BOARD' ? "bg-white shadow-sm text-indigo-600" : "text-slate-500 hover:text-slate-700"
              )}
            >
              <LayoutGrid className="w-4 h-4" />
            </button>
            <button
              onClick={() => setViewMode('LIST')}
              className={cn(
                "p-2 rounded-md transition-all",
                viewMode === 'LIST' ? "bg-white shadow-sm text-indigo-600" : "text-slate-500 hover:text-slate-700"
              )}
            >
              <List className="w-4 h-4" />
            </button>
            <button
              onClick={() => setViewMode('REPORTS')}
              className={cn(
                "p-2 rounded-md transition-all",
                "text-slate-500 hover:text-slate-700"
              )}
              title="Reports"
            >
              <TrendingUp className="w-4 h-4" />
            </button>
          </div>
          <Button variant="outline" className="flex items-center gap-2">
            <Filter className="w-4 h-4" />
            Export
          </Button>
          <Button 
            className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-700 text-white"
            onClick={() => setShowLeadForm(true)}
          >
            <Plus className="w-4 h-4" />
            New Lead
          </Button>
        </div>
      </div>

      {showLeadForm && (
        <LeadCreateForm 
          onClose={() => setShowLeadForm(false)} 
          onSuccess={() => {
            setShowLeadForm(false);
            fetchData();
          }}
          userRole={userRole}
        />
      )}

      {loading ? (
        <div className="py-24 flex flex-col items-center justify-center text-slate-400">
          <div className="w-10 h-10 border-4 border-indigo-600 border-t-transparent rounded-full animate-spin mb-4" />
          <p>Loading pipeline data...</p>
        </div>
      ) : viewMode === 'BOARD' ? (
        <div className="space-y-6 overflow-x-auto pb-6">
          <div className="flex gap-4 min-w-[1400px]">
            {STAGES.map((stage) => {
              const stageSummary = dashboard?.pipeline?.stages.find((s: any) => s.stage === stage);
              const leadsInStage = leads.filter((l: any) => l.stage === stage);
              
              return (
                <div key={stage} className="flex-1 min-w-[280px] flex flex-col gap-4">
                  <div className="flex items-center justify-between px-1">
                    <div className="flex items-center gap-2">
                      <Badge variant={getStageBadgeVariant(stage)} className="font-bold">
                        {getLeadStageLabel(stage)}
                      </Badge>
                      <span className="text-xs font-bold text-slate-400 bg-slate-100 px-2 py-0.5 rounded-full">
                        {stageSummary?.count || 0}
                      </span>
                    </div>
                    <div className="text-right">
                      <p className="text-[10px] font-black text-slate-400 uppercase tracking-wider">Weighted</p>
                      <p className="text-xs font-bold text-slate-900">₹{(stageSummary?.weighted_value || 0).toLocaleString('en-IN')}</p>
                    </div>
                  </div>

                  <div className="bg-slate-50/50 p-2 rounded-xl border border-dashed border-slate-200 min-h-[500px] flex flex-col gap-3">
                    {leadsInStage.length === 0 ? (
                      <div className="flex-1 flex flex-col items-center justify-center text-slate-300 py-10">
                        <Plus className="w-8 h-8 opacity-20 mb-2" />
                        <p className="text-xs font-medium">No leads in {getLeadStageLabel(stage)}</p>
                      </div>
                    ) : (
                      leadsInStage.map((lead: any) => (
                        <Card 
                          key={lead.id} 
                          className="p-3 hover:border-indigo-300 transition-all cursor-pointer group shadow-sm bg-white relative"
                          onClick={() => handleLeadClick(lead.id)}
                        >
                          <div className="absolute top-2 right-2 flex items-center gap-1">
                            <LeadStageStepButtons lead={lead} />
                            <LeadQuickActions lead={lead} />
                          </div>
                          <p className="text-xs font-bold text-slate-900 group-hover:text-indigo-600 transition-colors mb-2 line-clamp-1">
                            {lead.title}
                          </p>
                          <div className="flex items-center gap-1.5 text-[10px] text-slate-500 mb-3">
                            <Building2 className="w-3 h-3" />
                            {lead.account?.name || 'No Account'}
                          </div>
                          <div className="flex items-center justify-between pt-2 border-t border-slate-50">
                            <div className="flex -space-x-1.5 overflow-hidden">
                              <div className="w-5 h-5 rounded-full bg-indigo-100 border border-white flex items-center justify-center text-[8px] font-bold text-indigo-700">
                                {lead.owner_name?.[0] || 'U'}
                              </div>
                            </div>
                            <div className="text-right">
                              <p className="text-[11px] font-bold text-slate-900">₹{(lead.estimated_value || 0).toLocaleString('en-IN')}</p>
                            </div>
                          </div>
                        </Card>
                      ))
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      ) : (
        <>
          {/* Stats Summary */}
          <div className="grid grid-cols-1 md:grid-cols-4 lg:grid-cols-5 gap-4">
            <Card className="p-4 flex items-center gap-4 border-l-4 border-blue-500">
              <div className="p-2 bg-blue-50 rounded-lg">
                <Users className="w-6 h-6 text-blue-600" />
              </div>
              <div>
                <p className="text-sm text-slate-500 font-medium">Pipeline Value</p>
                <p className="text-2xl font-bold text-slate-900">
                  ₹{(dashboard?.pipeline.total_value || 0).toLocaleString('en-IN')}
                </p>
              </div>
            </Card>
            <Card className="p-4 flex items-center gap-4 border-l-4 border-yellow-500">
              <div className="p-2 bg-yellow-50 rounded-lg">
                <Calendar className="w-6 h-6 text-yellow-600" />
              </div>
              <div>
                <p className="text-sm text-slate-500 font-medium">Closes This Month</p>
                <p className="text-2xl font-bold text-slate-900">
                  {dashboard?.expected_closes_this_month || 0}
                </p>
              </div>
            </Card>
            <Card className="p-4 flex items-center gap-4 border-l-4 border-emerald-500">
              <div className="p-2 bg-emerald-50 rounded-lg">
                <Trophy className="w-6 h-6 text-emerald-600" />
              </div>
              <div>
                <p className="text-sm text-slate-500 font-medium">Win Rate</p>
                <p className="text-2xl font-bold text-slate-900">
                  {dashboard?.win_rate_percent.toFixed(1) || 0}%
                </p>
              </div>
            </Card>
            <Card className="p-4 flex items-center gap-4 border-l-4 border-indigo-500">
              <div className="p-2 bg-indigo-50 rounded-lg">
                <TrendingUp className="w-6 h-6 text-indigo-600" />
              </div>
              <div>
                <p className="text-sm text-slate-500 font-medium">Weighted Value</p>
                <p className="text-2xl font-bold text-slate-900">
                  ₹{(dashboard?.pipeline.total_weighted_value || 0).toLocaleString('en-IN')}
                </p>
              </div>
            </Card>
            <Card className="p-4 flex items-center gap-4 border-l-4 border-slate-500">
              <div className="p-2 bg-slate-100 rounded-lg">
                <MessageSquare className="w-6 h-6 text-slate-600" />
              </div>
              <div>
                <p className="text-sm text-slate-500 font-medium">Avg Sales Cycle</p>
                <p className="text-2xl font-bold text-slate-900">
                  {dashboard?.avg_sales_cycle_days.toFixed(0) || 0}d
                </p>
              </div>
            </Card>
          </div>

          <div className="flex flex-col md:flex-row gap-4 items-center justify-between">
            <div className="relative w-full md:w-96">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
              <Input 
                placeholder="Search leads, accounts, or ID..." 
                className="pl-10"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
            </div>
            <div className="flex items-center gap-2 overflow-x-auto w-full md:w-auto pb-2 md:pb-0">
              <Button 
                variant={selectedStage === 'ALL' ? 'primary' : 'outline'}
                size="sm"
                onClick={() => setSelectedStage('ALL')}
                className="whitespace-nowrap"
              >
                All
              </Button>
              {STAGES.map(stage => (
                <Button
                  key={stage}
                  variant={selectedStage === stage ? 'primary' : 'outline'}
                  size="sm"
                  onClick={() => setSelectedStage(stage)}
                  className="whitespace-nowrap"
                >
                  {getLeadStageLabel(stage)}
                </Button>
              ))}
            </div>
          </div>

          {filteredLeads.length === 0 ? (
            <Card className="py-20 flex flex-col items-center justify-center text-center opacity-70">
              <div className="p-4 bg-slate-100 rounded-full mb-4">
                <Search className="w-8 h-8 text-slate-400" />
              </div>
              <h3 className="text-lg font-semibold text-slate-900">No leads found</h3>
              <p className="text-slate-500 max-w-sm">
                We couldn't find any leads matching your criteria. Try adjusting your search or filters.
              </p>
            </Card>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {filteredLeads.map((lead) => (
                <Card 
                  key={lead.id} 
                  className="p-5 hover:border-indigo-300 transition-all cursor-pointer group relative"
                  onClick={() => handleLeadClick(lead.id)}
                >
                  <div className="flex justify-between items-start mb-4">
                    <Badge variant={getStageBadgeVariant(lead.stage)}>
                      {getLeadStageLabel(lead.stage)}
                    </Badge>
                    <div className="flex items-center gap-1">
                      <LeadStageStepButtons lead={lead} />
                      <LeadQuickActions lead={lead} />
                    </div>
                  </div>

                  <div className="space-y-3">
                    <div>
                      <h3 className="font-bold text-slate-900 group-hover:text-indigo-600 transition-colors">
                        {lead.title}
                      </h3>
                      <div className="flex items-center gap-1.5 text-xs text-slate-500 mt-1">
                        <Building2 className="w-3 h-3" />
                        {lead.account?.name || 'No Account'}
                      </div>
                    </div>

                    <div className="flex items-center justify-between pt-2 border-t border-slate-50">
                      <div className="flex items-center gap-2">
                        <div className="w-7 h-7 rounded-full bg-indigo-100 flex items-center justify-center text-[10px] font-bold text-indigo-700">
                          {lead.owner_name?.split(' ').map(n => n[0]).join('') || 'U'}
                        </div>
                        <span className="text-xs text-slate-600 font-medium">{lead.owner_name || 'Unassigned'}</span>
                      </div>
                      <div className="text-right">
                        <p className="text-xs text-slate-400">Value</p>
                        <p className="text-sm font-bold text-slate-900">
                          ₹{(lead.estimated_value || 0).toLocaleString('en-IN')}
                        </p>
                      </div>
                    </div>

                    <div className="flex items-center gap-4 pt-1">
                      <div className="flex items-center gap-1.5 text-[11px] text-slate-500">
                        <Calendar className="w-3 h-3" />
                        {new Date(lead.updated_at).toLocaleDateString()}
                      </div>
                      <div className="flex items-center gap-1.5 text-[11px] text-slate-500">
                        <MessageSquare className="w-3 h-3" />
                        {lead.activities?.length || 0} activities
                      </div>
                    </div>
                  </div>
                </Card>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
};

// --- Components ---

const BDReportsView = ({ onBack }: { onBack: () => void }) => {
  const [accuracy, setAccuracy] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchReports();
  }, []);

  const fetchReports = async () => {
    try {
      setLoading(true);
      const response = await client.get<any>(ENDPOINTS.BD.REPORTS.ESTIMATE_ACCURACY);
      setAccuracy(response.data);
    } catch (error) {
      console.error('Failed to fetch reports', error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="p-6 space-y-6 max-w-[1200px] mx-auto animate-in fade-in slide-in-from-bottom-2 duration-300">
      <button 
        onClick={onBack}
        className="flex items-center gap-2 text-slate-500 hover:text-indigo-600 transition-colors mb-2"
      >
        <ArrowLeft className="w-4 h-4" />
        Back to Dashboard
      </button>

      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">BD Reports & Analytics</h1>
          <p className="text-slate-500">Track pipeline performance and estimate precision</p>
        </div>
        <Button variant="outline" onClick={fetchReports} className="flex items-center gap-2">
          <TrendingUp className="w-4 h-4" />
          Refresh Reports
        </Button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Card className="p-6">
          <h3 className="font-bold text-slate-900 mb-4 flex items-center gap-2">
            <Calculator className="w-5 h-5 text-indigo-600" />
            Estimate Accuracy (Post-Project)
          </h3>
          {loading ? (
            <div className="h-40 flex items-center justify-center">
              <div className="w-6 h-6 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin" />
            </div>
          ) : (
            <div className="space-y-6">
              <div className="grid grid-cols-2 gap-4">
                <div className="p-4 bg-slate-50 rounded-xl border border-slate-100">
                  <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">Total Estimates</p>
                  <p className="text-2xl font-bold text-slate-900">{accuracy?.total_estimates || 0}</p>
                </div>
                <div className="p-4 bg-slate-50 rounded-xl border border-slate-100">
                  <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">Avg Variance</p>
                  <p className="text-2xl font-bold text-slate-900">{accuracy?.avg_variance_percent || 0}%</p>
                </div>
              </div>
              <p className="text-sm text-slate-500 italic">
                * Variance measures the deviation between estimated costs and actual project expenditure.
              </p>
            </div>
          )}
        </Card>

        <Card className="p-6 flex flex-col items-center justify-center text-center space-y-4 bg-slate-50/50 border-dashed">
          <div className="p-4 bg-white rounded-full shadow-sm border border-slate-100">
            <TrendingUp className="w-10 h-10 text-slate-300" />
          </div>
          <div>
            <h4 className="font-bold text-slate-900">Historical Pipeline Trends</h4>
            <p className="text-sm text-slate-500 max-w-[280px]">
              Visual charts for quarterly pipeline growth and win/loss velocity are coming in the next update.
            </p>
          </div>
        </Card>
      </div>
    </div>
  );
};

const ProjectConversionModal = ({
  lead,
  onClose,
  onSuccess
}: {
  lead: Lead,
  onClose: () => void,
  onSuccess: (projectId: number) => void
}) => {
  const [loading, setLoading] = useState(false);
  const [users, setUsers] = useState<any[]>([]);
  const [formData, setFormData] = useState<ProjectConversionData>({
    project_code: `PRJ-${lead.lead_id.split('-')[1] || lead.id}`,
    project_manager_id: 0,
    start_date: new Date().toISOString().split('T')[0]
  });

  // After conversion, the modal flips into a "workorder upload" step.
  // Upload is optional — BD/COO/admin can also do it later from the
  // project's Documents section.
  const [convertedProjectId, setConvertedProjectId] = useState<number | null>(null);
  const [workorderFile, setWorkorderFile] = useState<File | null>(null);
  const [workorderRemark, setWorkorderRemark] = useState('');
  const [uploadingWorkorder, setUploadingWorkorder] = useState(false);
  const workorderInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    fetchUsers();
  }, []);

  const fetchUsers = async () => {
    try {
      const response = await client.get<any[]>(
        ENDPOINTS.BD.ELIGIBLE_PORTFOLIO_MANAGERS(lead.id),
      );
      const data = response.data || [];
      setUsers(data);
      if (data.length > 0) {
        setFormData(prev => ({ ...prev, project_manager_id: data[0].id }));
      }
    } catch (error) {
      console.error('Failed to fetch eligible portfolio managers', error);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formData.project_manager_id) {
      toast.error("Please select a Portfolio Manager (COO)");
      return;
    }
    setLoading(true);
    try {
      const result = await client.post<any>(ENDPOINTS.BD.CONVERT_TO_PROJECT(lead.id), formData);
      toast.success("Lead converted to project successfully!");
      const projectId = result.data?.id;
      if (typeof projectId !== 'number') {
        toast.error('Conversion succeeded but project ID was missing');
        return;
      }
      // Stay open for the optional workorder upload — onSuccess fires
      // either when they upload or when they skip.
      setConvertedProjectId(projectId);
    } catch (error: any) {
      // Surface the server's actual reason (e.g. "Lead must have an
      // APPROVED estimate version to convert") instead of axios's
      // generic "Request failed with status code 400".
      const detail = error?.response?.data?.detail;
      const msg = typeof detail === 'string' ? detail
        : Array.isArray(detail) ? detail.map((d: any) => d?.msg || JSON.stringify(d)).join('; ')
        : (error?.message || 'Failed to convert lead');
      toast.error(msg, { duration: 6000 });
    } finally {
      setLoading(false);
    }
  };

  const handleUploadWorkorder = async () => {
    if (!convertedProjectId || !workorderFile) return;
    setUploadingWorkorder(true);
    try {
      const form = new FormData();
      form.append('file', workorderFile);
      const params = new URLSearchParams({ doc_type: 'Workorder' });
      if (workorderRemark.trim()) params.set('remark', workorderRemark.trim());
      await client.post(
        `${ENDPOINTS.PROJECTS.DOCUMENT_UPLOAD(convertedProjectId)}?${params.toString()}`,
        form,
      );
      toast.success('Workorder uploaded');
      onSuccess(convertedProjectId);
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || err?.message || 'Upload failed');
    } finally {
      setUploadingWorkorder(false);
    }
  };

  const handleSkipWorkorder = () => {
    if (convertedProjectId) onSuccess(convertedProjectId);
  };

  if (convertedProjectId !== null) {
    return (
      <div className="fixed inset-0 bg-slate-900/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
        <Card
          className="w-full max-w-md bg-white shadow-2xl animate-in zoom-in-95 duration-200"
          style={{ maxHeight: '70vh', overflowY: 'auto', overscrollBehavior: 'contain' }}
        >
          <div className="p-6 space-y-5">
            <div className="flex items-start gap-3">
              <div className="p-2 bg-emerald-50 rounded-lg">
                <Briefcase className="w-5 h-5 text-emerald-600" />
              </div>
              <div className="flex-1">
                <h2 className="text-lg font-bold text-slate-900">Project created</h2>
                <p className="text-xs text-slate-500 mt-0.5">
                  Optionally attach the workorder now. You can also upload it later from the project's Documents section.
                </p>
              </div>
            </div>

            <div className="space-y-3">
              <button
                type="button"
                onClick={() => workorderInputRef.current?.click()}
                className="w-full h-11 flex items-center gap-3 px-4 rounded-md border border-dashed border-slate-300 bg-slate-50 hover:border-indigo-400 transition-colors text-left"
              >
                {workorderFile ? (
                  <span className="text-sm font-semibold text-indigo-700 truncate">{workorderFile.name}</span>
                ) : (
                  <span className="text-sm text-slate-500">Click to select a workorder file…</span>
                )}
              </button>
              <input
                ref={workorderInputRef}
                type="file"
                className="hidden"
                accept="application/pdf,image/jpeg,image/png,image/webp,image/heic,image/gif,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/vnd.ms-excel,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,text/plain"
                onChange={e => setWorkorderFile(e.target.files?.[0] || null)}
              />
              <Input
                value={workorderRemark}
                onChange={e => setWorkorderRemark(e.target.value)}
                placeholder="Remark (optional) — e.g. signed PO from client"
              />
              <p className="text-[11px] text-slate-400">PDF · JPG · PNG · Word · Excel · 25 MB max</p>
            </div>

            <div className="flex gap-3 pt-2">
              <Button
                type="button"
                variant="outline"
                onClick={handleSkipWorkorder}
                disabled={uploadingWorkorder}
                className="flex-1"
              >
                Skip for now
              </Button>
              <Button
                type="button"
                onClick={handleUploadWorkorder}
                disabled={!workorderFile || uploadingWorkorder}
                className="flex-1 bg-indigo-600 text-white hover:bg-indigo-700"
              >
                {uploadingWorkorder ? 'Uploading…' : 'Upload workorder'}
              </Button>
            </div>
          </div>
        </Card>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 bg-slate-900/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <Card
        className="w-full max-w-md bg-white shadow-2xl animate-in zoom-in-95 duration-200"
        style={{
          maxHeight: "70vh",
          overflowY: "auto",
          overscrollBehavior: "contain",
          WebkitOverflowScrolling: "touch",
        }}
      >
        <div className="p-6">
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-xl font-bold text-slate-900 flex items-center gap-2">
              <Briefcase className="w-5 h-5 text-indigo-600" />
              Convert to Project
            </h2>
            <button onClick={onClose} className="text-slate-400 hover:text-slate-600">
              <X className="w-5 h-5" />
            </button>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-1.5">
              <label className="text-sm font-medium text-slate-700">Project Name</label>
              <Input value={lead.title} disabled className="bg-slate-50" />
            </div>

            <div className="space-y-1.5">
              <label className="text-sm font-medium text-slate-700">Project Code</label>
              <Input 
                value={formData.project_code} 
                onChange={e => setFormData({ ...formData, project_code: e.target.value })}
                placeholder="PROJ-001"
              />
            </div>

            <div className="space-y-1.5">
              <label className="text-sm font-medium text-slate-700">Portfolio Manager (COO)</label>
              <select
                title="Select Portfolio Manager"
                value={formData.project_manager_id}
                onChange={e => setFormData({ ...formData, project_manager_id: Number(e.target.value) })}
                disabled={users.length === 0}
                className="w-full h-10 px-3 rounded-md border border-slate-200 focus:outline-none focus:ring-2 focus:ring-indigo-500 text-sm disabled:bg-slate-50 disabled:text-slate-400"
              >
                <option value={0}>{users.length === 0 ? 'No portfolio managers configured' : 'Select a portfolio manager…'}</option>
                {users.map(u => (
                  <option key={u.id} value={u.id}>{u.full_name}</option>
                ))}
              </select>
              {users.length === 0 ? (
                <p className="text-xs text-amber-600 leading-relaxed">
                  No active user is assigned the COO, CEO, or Super Admin role. Ask HR to assign one of these roles via Employee Management → Manage Roles, then reload.
                </p>
              ) : (
                <p className="text-xs text-slate-500">This person will oversee the full project portfolio and all PM sub-projects.</p>
              )}
            </div>

            <div className="space-y-1.5">
              <label className="text-sm font-medium text-slate-700">Project Start Date</label>
              <Input 
                type="date"
                value={formData.start_date}
                onChange={e => setFormData({ ...formData, start_date: e.target.value })}
              />
            </div>

            <div className="pt-4 flex gap-3">
              <Button type="button" variant="outline" onClick={onClose} className="flex-1">
                Cancel
              </Button>
              <Button type="submit" disabled={loading} className="flex-1 bg-indigo-600 text-white hover:bg-indigo-700">
                {loading ? "Converting..." : "Convert Now"}
              </Button>
            </div>
          </form>
        </div>
      </Card>
    </div>
  );
};

const LeadDetailView = ({ 
  id, 
  onBack, 
  refreshLeads, 
  onViewEstimates 
}: { 
  id: number, 
  onBack: () => void, 
  refreshLeads: () => void,
  onViewEstimates: () => void
}) => {
  const [lead, setLead] = useState<Lead | null>(null);
  const [loading, setLoading] = useState(true);
  const [showConversionModal, setShowConversionModal] = useState(false);
  const [docsOpen, setDocsOpen] = useState(false);
  const [newActivity, setNewActivity] = useState({ type: 'call' as Activity['type'], summary: '', notes: '' });

  useEffect(() => {
    fetchLeadDetail();
  }, [id]);

  const fetchLeadDetail = async () => {
    try {
      setLoading(true);
      const response = await client.get<Lead>(ENDPOINTS.BD.LEAD_DETAIL(id));
      setLead(normalizeLead(response.data));
    } catch (error) {
      console.error('Failed to fetch lead detail:', error);
      toast.error('Failed to load lead details');
      onBack();
    } finally {
      setLoading(false);
    }
  };

  const handleUpdateStage = async (newStage: LeadStage) => {
    try {
      await client.patch(ENDPOINTS.BD.LEAD_DETAIL(id), { stage: newStage });
      toast.success(`Stage updated to ${getLeadStageLabel(newStage)}`);
      fetchLeadDetail();
      refreshLeads();
    } catch (error) {
      toast.error('Failed to update stage');
    }
  };

  const handleAddActivity = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newActivity.summary) return;

    try {
      await client.post(ENDPOINTS.BD.LEAD_ACTIVITIES(id), newActivity);
      toast.success('Activity logged');
      setNewActivity({ type: 'call', summary: '', notes: '' });
      fetchLeadDetail();
    } catch (error) {
      toast.error('Failed to log activity');
    }
  };

  if (loading || !lead) {
    return (
      <div className="h-full flex flex-col items-center justify-center space-y-4">
        <div className="w-12 h-12 border-4 border-indigo-600 border-t-transparent rounded-full animate-spin" />
        <p className="text-slate-500">Retrieving lead records...</p>
      </div>
    );
  }

  const leadStageFlow: LeadStage[] = ['new', 'qualified', 'discovery', 'proposal', 'negotiation'];
  const leadStageIdx = leadStageFlow.indexOf(lead.stage);
  const prevStage: LeadStage | null =
    lead.stage === 'new'
      ? null
      : lead.stage === 'lost'
        ? 'negotiation'
        : leadStageIdx > 0
          ? leadStageFlow[leadStageIdx - 1]
          : null;
  const nextStage: LeadStage | null =
    lead.stage === 'won' || lead.stage === 'lost'
      ? null
      : leadStageIdx >= 0 && leadStageIdx < leadStageFlow.length - 1
        ? leadStageFlow[leadStageIdx + 1]
        : null;

  return (
    <div className="p-6 space-y-6 max-w-[1200px] mx-auto animate-in fade-in slide-in-from-bottom-2 duration-300">
      <button 
        onClick={onBack}
        className="flex items-center gap-2 text-slate-500 hover:text-indigo-600 transition-colors mb-2"
      >
        <ArrowLeft className="w-4 h-4" />
        Back to Pipeline
      </button>

      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-3 mb-1">
            <h1 className="text-2xl font-bold text-slate-900">{lead.title}</h1>
            <Badge className="px-2 py-0.5 text-xs bg-slate-100 text-slate-600 border-slate-200">
              {lead.lead_id}
            </Badge>
          </div>
          <div className="flex items-center gap-4 text-slate-500">
            <div className="flex items-center gap-1.5">
              <Building2 className="w-4 h-4" />
              {lead.account?.name || 'No Account'}
            </div>
            <div className="flex items-center gap-1.5 border-l pl-4 border-slate-200">
              <Calendar className="w-4 h-4" />
              Created {new Date(lead.created_at).toLocaleDateString()}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {lead.stage === 'negotiation' && (
            <>
              <Button
                onClick={() => setShowConversionModal(true)}
                className="bg-green-600 hover:bg-green-700 text-white flex items-center gap-2 px-4 h-10 rounded-xl font-black uppercase text-[10px] tracking-widest shadow-sm"
              >
                <Trophy className="w-4 h-4" />
                Mark Won
              </Button>
              <Button
                onClick={() => {
                  const ok = window.confirm('Mark this lead as LOST?');
                  if (!ok) return;
                  handleUpdateStage('lost');
                }}
                className="bg-red-600 hover:bg-red-700 text-white flex items-center gap-2 px-4 h-10 rounded-xl font-black uppercase text-[10px] tracking-widest shadow-sm"
              >
                <XCircle className="w-4 h-4" />
                Mark Lost
              </Button>
            </>
          )}
          {lead.stage === 'won' && (
            <Button 
              onClick={() => setShowConversionModal(true)}
              className="bg-emerald-600 hover:bg-emerald-700 text-white flex items-center gap-2 px-4 shadow-lg shadow-emerald-600/20 animate-pulse-once"
            >
              <Briefcase className="w-4 h-4" />
              Convert to Project
            </Button>
          )}
          <Button 
            variant="outline" 
            onClick={onViewEstimates}
            className="flex items-center gap-2 px-4"
          >
            <Calculator className="w-4 h-4" />
            Estimates
          </Button>
          <Button
            variant="outline"
            disabled={!prevStage}
            onClick={() => prevStage && handleUpdateStage(prevStage)}
            className="flex items-center gap-2 px-4"
            title="Move to previous stage"
          >
            <ChevronLeft className="w-4 h-4" />
            Prev
          </Button>
          <Button
            variant="outline"
            disabled={!nextStage}
            onClick={() => nextStage && handleUpdateStage(nextStage)}
            className="flex items-center gap-2 px-4"
            title="Move to next stage"
          >
            Next
            <ChevronRight className="w-4 h-4" />
          </Button>
          <div className="relative group">
            <Button className="bg-indigo-600 hover:bg-indigo-700 text-white flex items-center gap-2 px-6">
              Update Stage: {getLeadStageLabel(lead.stage)}
              <ChevronRight className="w-4 h-4 rotate-90" />
            </Button>
            <div className="absolute right-0 top-full mt-2 w-48 bg-white rounded-lg shadow-xl border border-slate-100 py-1 hidden group-hover:block z-10">
              {LEAD_STAGES.filter((s) => s !== 'won').map((s) => (
                <button
                  key={s}
                  onClick={() => handleUpdateStage(s)}
                  className={cn(
                    "w-full text-left px-4 py-2 hover:bg-indigo-50 text-sm transition-colors",
                    lead.stage === s ? "text-indigo-600 font-bold bg-indigo-50" : "text-slate-700"
                  )}
                >
                  {getLeadStageLabel(s)}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-6">
          <Card className="p-6">
            <h3 className="font-bold text-slate-900 mb-6 flex items-center gap-2">
              <MessageSquare className="w-5 h-5 text-indigo-600" />
              Activity History
            </h3>

            <div className="space-y-6">
              {/* Add Activity Form */}
              <form onSubmit={handleAddActivity} className="bg-slate-50 p-4 rounded-xl space-y-4 border border-slate-100">
                <div className="flex items-center gap-4">
                  <div className="flex grow gap-2 p-1 bg-white border border-slate-200 rounded-lg">
                    {ACTIVITY_TYPES.map((type) => (
                      <button
                        key={type}
                        type="button"
                        onClick={() => setNewActivity({ ...newActivity, type })}
                        className={cn(
                          "px-3 py-1.5 text-xs font-bold rounded flex items-center gap-1.5 transition-all",
                          newActivity.type === type 
                            ? "bg-indigo-600 text-white" 
                            : "text-slate-500 hover:bg-slate-100"
                        )}
                      >
                        {type === 'call' && <Phone className="w-3 h-3" />}
                        {type === 'email' && <Mail className="w-3 h-3" />}
                        {type === 'meeting' && <Users className="w-3 h-3" />}
                        {type === 'note' && <FileText className="w-3 h-3" />}
                        {type.toUpperCase()}
                      </button>
                    ))}
                  </div>
                </div>
                <Input 
                  placeholder="Summary of action taken..." 
                  className="bg-white"
                  value={newActivity.summary}
                  onChange={(e) => setNewActivity({ ...newActivity, summary: e.target.value })}
                />
                <textarea 
                  className="w-full bg-white border border-slate-200 rounded-lg p-3 text-sm min-h-[80px] focus:ring-2 focus:ring-indigo-500 outline-none"
                  placeholder="Detailed notes (optional)..."
                  value={newActivity.notes}
                  onChange={(e) => setNewActivity({ ...newActivity, notes: e.target.value })}
                />
                <div className="flex justify-end">
                  <Button type="submit" disabled={!newActivity.summary} variant="primary" size="sm">
                    Log Activity
                  </Button>
                </div>
              </form>

              {/* Activity Timeline */}
              <div className="relative pl-6 space-y-8 before:absolute before:left-2 before:top-2 before:bottom-2 before:w-0.5 before:bg-slate-100">
                {lead.activities?.length === 0 ? (
                  <p className="text-slate-400 text-sm text-center py-4">No activities logged yet.</p>
                ) : (
                  lead.activities?.map((activity) => (
                    <div key={activity.id} className="relative">
                      <div className={cn(
                        "absolute -left-[22px] top-1 w-4 h-4 rounded-full border-2 border-white",
                        activity.type === 'call' ? "bg-blue-500" :
                        activity.type === 'email' ? "bg-indigo-500" :
                        activity.type === 'meeting' ? "bg-green-500" : "bg-slate-500"
                      )} />
                      <div className="space-y-1">
                        <div className="flex items-center justify-between">
                          <p className="text-sm font-bold text-slate-900">{activity.summary}</p>
                          <span className="text-[10px] text-slate-400 font-medium">
                            {new Date(activity.created_at).toLocaleString()}
                          </span>
                        </div>
                        <p className="text-sm text-slate-600">{activity.notes}</p>
                        <p className="text-[11px] text-indigo-600 font-medium">
                          Logged by {activity.created_by_name || 'System'}
                        </p>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          </Card>

          <LeadBidTasksPanel leadId={id} onViewEstimates={onViewEstimates} />
        </div>

        <div className="space-y-6">
          <Card className="p-5">
            <h3 className="font-bold text-slate-900 mb-4 flex items-center gap-2">
              <Paperclip className="w-5 h-5 text-indigo-600" />
              Documents
            </h3>
            <div className="text-sm text-slate-500">
              Upload and manage opportunity files.
            </div>
            <Button
              variant="outline"
              className="w-full mt-4 flex items-center gap-2"
              onClick={() => setDocsOpen(true)}
            >
              <Paperclip className="w-4 h-4" />
              Manage Documents
            </Button>
          </Card>

          <Card className="p-5">
            <h3 className="font-bold text-slate-900 mb-4 flex items-center gap-2">
              <Users className="w-5 h-5 text-indigo-600" />
              Contact Info
            </h3>
            {lead.contact ? (
              <div className="space-y-4">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-full bg-slate-100 flex items-center justify-center text-slate-600 font-bold">
                    {lead.contact.first_name[0]}{lead.contact.last_name[0]}
                  </div>
                  <div>
                    <p className="font-bold text-slate-900">{lead.contact.first_name} {lead.contact.last_name}</p>
                    <p className="text-xs text-slate-500">{lead.contact.job_title || 'Lead Contact'}</p>
                  </div>
                </div>
                <div className="space-y-2 pt-2">
                  <a href={`mailto:${lead.contact.email}`} className="flex items-center gap-2 text-sm text-slate-600 hover:text-indigo-600">
                    <Mail className="w-4 h-4" />
                    {lead.contact.email}
                  </a>
                  {lead.contact.phone && (
                    <a href={`tel:${lead.contact.phone}`} className="flex items-center gap-2 text-sm text-slate-600 hover:text-indigo-600">
                      <Phone className="w-4 h-4" />
                      {lead.contact.phone}
                    </a>
                  )}
                </div>
              </div>
            ) : (
              <div className="text-center py-4 text-slate-400">
                <Users className="w-8 h-8 opacity-20 mx-auto mb-2" />
                <p className="text-sm">No primary contact recorded</p>
                <Button variant="outline" size="sm" className="mt-2">Add Contact</Button>
              </div>
            )}
          </Card>

          <Card className="p-5">
            <h3 className="font-bold text-slate-900 mb-4 flex items-center gap-2">
              <Calendar className="w-5 h-5 text-indigo-600" />
              Lead Details
            </h3>
            <div className="space-y-4 text-sm">
              <div className="flex justify-between items-center py-2 border-b border-slate-50">
                <span className="text-slate-500">Estimated Value</span>
                <span className="font-bold text-slate-900">₹{lead.estimated_value?.toLocaleString('en-IN')}</span>
              </div>
              <div className="flex justify-between items-center py-2 border-b border-slate-50">
                <span className="text-slate-500">Source</span>
                <span className="text-slate-900">{lead.source || 'Direct'}</span>
              </div>
              <div className="flex justify-between items-center py-2 border-b border-slate-50">
                <span className="text-slate-500">Account Manager</span>
                <span className="text-indigo-600 font-medium">{lead.owner_name}</span>
              </div>
              <div className="flex justify-between items-center py-2">
                <span className="text-slate-500">Last Updated</span>
                <span className="text-slate-900">{new Date(lead.updated_at).toLocaleDateString()}</span>
              </div>
            </div>
            <Button variant="outline" className="w-full mt-4 flex items-center gap-2">
              <Edit className="w-4 h-4" />
              Edit Properties
            </Button>
          </Card>
        </div>
      </div>

      {showConversionModal && (
        <ProjectConversionModal 
          lead={lead} 
          onClose={() => setShowConversionModal(false)}
          onSuccess={(projectId) => {
            setShowConversionModal(false);
            // In a real app we might redirect to project detail
            toast.success(`Project created with ID: ${projectId}`);
            fetchLeadDetail();
            refreshLeads();
          }}
        />
      )}

      <LeadDocumentsModal
        leadId={id}
        open={docsOpen}
        onOpenChange={setDocsOpen}
      />
    </div>
  );
};
