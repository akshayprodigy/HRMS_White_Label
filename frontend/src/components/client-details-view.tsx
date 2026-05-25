import React, { useCallback, useEffect, useRef, useState } from 'react';
import { AlertCircle, ArrowLeft, Building2, CheckCircle2, ChevronLeft, ChevronRight, Download, FileSpreadsheet, Plus, RefreshCcw, Save, Search, Trash2, Upload, X } from 'lucide-react';
import { toast } from 'sonner';
import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';
import { Button, Card, Input, cn } from './ui-elements';
import { UserRole } from '../types/erp';

const formatFileSize = (bytes: number) => {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
};

type Account = {
  id: number;
  name: string;
  domain?: string | null;
  industry?: string | null;
};

type ClientDetails = {
  account_id: number;
  name: string;
  domain?: string | null;
  industry?: string | null;
  address?: string | null;
  email?: string | null;
  website?: string | null;
  contact_person_name?: string | null;
  contact_person_phone?: string | null;
  contact_person_email?: string | null;
  gst_number?: string | null;
};

/* ── Bulk Upload Modal ── */
const BulkUploadModal = ({
  open,
  onClose,
  onSuccess,
}: {
  open: boolean;
  onClose: () => void;
  onSuccess: () => void;
}) => {
  const fileRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [result, setResult] = useState<{
    created: number;
    updated: number;
    skipped?: number;
    errors: string[];
    total_processed: number;
  } | null>(null);

  useEffect(() => {
    if (!open) {
      setFile(null);
      setUploading(false);
      setDragging(false);
      setResult(null);
    }
  }, [open]);

  const handleDownloadTemplate = useCallback(async () => {
    try {
      const res = await client.get(ENDPOINTS.CLIENTS.TEMPLATE, {
        responseType: 'blob',
      });
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const a = document.createElement('a');
      a.href = url;
      a.download = 'client_template.xlsx';
      a.click();
      window.URL.revokeObjectURL(url);
    } catch {
      toast.error('Failed to download template');
    }
  }, []);

  const handleFile = (f: File | null) => {
    if (f && !f.name.match(/\.xlsx?$/i)) {
      toast.error('Please select an Excel file (.xlsx)');
      return;
    }
    setFile(f);
    setResult(null);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const f = e.dataTransfer.files?.[0] || null;
    handleFile(f);
  };

  const handleUpload = async () => {
    if (!file) return;
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append('file', file);
      const res = await client.post(ENDPOINTS.CLIENTS.BULK_UPLOAD, fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setResult(res.data);
      if (res.data.errors.length === 0) {
        toast.success(
          `${res.data.created} created, ${res.data.updated} updated`,
        );
        onSuccess();
        setTimeout(() => onClose(), 1200);
      } else {
        toast.warning('Upload completed with some errors');
        onSuccess();
      }
    } catch (err: any) {
      toast.error(
        err.response?.data?.detail || 'Bulk upload failed',
      );
    } finally {
      setUploading(false);
    }
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-lg mx-4 overflow-hidden">
        <div className="flex items-center justify-between px-6 py-4 border-b">
          <h3 className="text-lg font-bold text-[#0F172A]">
            Bulk Upload Clients
          </h3>
          <button
            onClick={onClose}
            className="p-1 rounded-lg hover:bg-slate-100 transition"
          >
            <X className="w-5 h-5 text-slate-500" />
          </button>
        </div>

        <div className="px-6 py-5 space-y-4">
          <button
            onClick={handleDownloadTemplate}
            className="flex items-center gap-2 text-sm text-blue-600 hover:text-blue-700 font-medium"
          >
            <Download className="w-4 h-4" />
            Download Template (.xlsx)
          </button>

          {/* Drag & drop zone */}
          <div
            onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={handleDrop}
            onClick={() => fileRef.current?.click()}
            className={cn(
              'border-2 border-dashed rounded-xl p-6 text-center cursor-pointer transition-all',
              dragging
                ? 'border-blue-500 bg-blue-50'
                : 'border-slate-300 hover:border-blue-400 hover:bg-slate-50',
            )}
          >
            <input
              ref={fileRef}
              type="file"
              accept=".xlsx,.xls"
              className="hidden"
              onChange={(e) => handleFile(e.target.files?.[0] || null)}
            />
            {file ? (
              <div className="flex items-center justify-center gap-3">
                <FileSpreadsheet className="w-8 h-8 text-green-600" />
                <div className="text-left">
                  <p className="text-sm font-semibold text-[#0F172A]">
                    {file.name}
                  </p>
                  <p className="text-xs text-slate-500">
                    {formatFileSize(file.size)}
                  </p>
                </div>
                <button
                  onClick={(e) => { e.stopPropagation(); setFile(null); setResult(null); }}
                  className="ml-2 p-1 rounded-lg hover:bg-red-50 text-slate-400 hover:text-red-500 transition"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            ) : (
              <div className="space-y-1">
                <Upload className="w-8 h-8 mx-auto text-slate-400" />
                <p className="text-sm font-medium text-slate-600">
                  Drag & drop an Excel file here, or click to browse
                </p>
                <p className="text-xs text-slate-400">
                  .xlsx files only
                </p>
              </div>
            )}
          </div>

          {result && (
            <div className="rounded-lg border p-4 space-y-2">
              <div className="flex items-center gap-2 text-sm">
                <CheckCircle2 className="w-4 h-4 text-green-600" />
                <span className="font-medium">
                  {result.created} created, {result.updated} updated
                  {(result.skipped ?? 0) > 0 && (
                    <span className="text-slate-500">
                      {' '}({result.skipped} example rows skipped)
                    </span>
                  )}
                </span>
              </div>
              {result.errors.length > 0 && (
                <div className="space-y-1">
                  <div className="flex items-center gap-2 text-sm text-red-600">
                    <AlertCircle className="w-4 h-4" />
                    <span className="font-medium">
                      {result.errors.length} error(s)
                    </span>
                  </div>
                  <ul className="text-xs text-red-600 list-disc list-inside max-h-32 overflow-y-auto">
                    {result.errors.map((e, i) => (
                      <li key={i}>{e}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>

        <div className="flex items-center justify-end gap-3 px-6 py-4 border-t">
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            onClick={handleUpload}
            disabled={!file || uploading}
            isLoading={uploading}
          >
            <Upload className="w-4 h-4 mr-2" />
            Upload
          </Button>
        </div>
      </div>
    </div>
  );
};

// Mirrors backend GST_RE in clients.py — accepts the canonical 15-char
// Indian GSTIN, e.g. "27AABCU9603R1ZM".
const GST_RE = /^\d{2}[A-Z]{5}\d{4}[A-Z]{1}[A-Z\d]{1}Z[A-Z\d]{1}$/;
// Permissive phone check — digits, spaces, hyphens, parens, optional +.
const PHONE_RE = /^[+0-9][0-9\s\-()]{6,19}$/;

const isValidGst = (value: string) => GST_RE.test(value.trim().toUpperCase());
const isValidPhone = (value: string) => PHONE_RE.test(value.trim());

const isValidEmail = (value: string) => {
  const v = value.trim();
  if (!v) return true;
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v);
};

const PAGE_SIZE_OPTIONS = [10, 25, 50, 100];

type ClientsPage = {
  items: Account[];
  total: number;
  limit: number;
  offset: number;
};

export const ClientDetailsView = ({ userRole }: { userRole: UserRole }) => {
  const canEdit = userRole === 'client manager' || userRole === 'super admin';

  const [clients, setClients] = useState<Account[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState<number>(PAGE_SIZE_OPTIONS[0]);
  const [searchInput, setSearchInput] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [clientsLoading, setClientsLoading] = useState(false);
  const loadAbortRef = useRef<AbortController | null>(null);

  const [selectedClientId, setSelectedClientId] = useState<number | null>(null);
  const [detailsLoading, setDetailsLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  const [bulkUploadOpen, setBulkUploadOpen] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [deleteState, setDeleteState] = useState<{
    open: boolean;
    blockers: { project_count: number; lead_count: number } | null;
    deleting: boolean;
  }>({ open: false, blockers: null, deleting: false });

  const [form, setForm] = useState({
    name: '',
    domain: '',
    industry: '',
    address: '',
    email: '',
    website: '',
    contact_person_name: '',
    contact_person_phone: '',
    contact_person_email: '',
    gst_number: '',
  });

  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  // Debounce the search input → searchQuery (250ms)
  useEffect(() => {
    const t = setTimeout(() => {
      setSearchQuery(searchInput.trim());
      setPage(1);
    }, 250);
    return () => clearTimeout(t);
  }, [searchInput]);

  const loadClients = useCallback(async () => {
    // Cancel any in-flight request so a slow earlier response can't
    // race-overwrite the latest page/search state.
    loadAbortRef.current?.abort();
    const controller = new AbortController();
    loadAbortRef.current = controller;

    setClientsLoading(true);
    try {
      const res = await client.get<ClientsPage>(ENDPOINTS.CLIENTS.PAGE, {
        params: {
          q: searchQuery || undefined,
          limit: pageSize,
          offset: (page - 1) * pageSize,
        },
        signal: controller.signal,
      });
      if (controller.signal.aborted) return;
      setClients(res.data.items || []);
      setTotal(res.data.total || 0);
    } catch (error: any) {
      if (controller.signal.aborted || error?.code === 'ERR_CANCELED') return;
      console.error('Failed to load clients', error);
      toast.error('Failed to load clients');
    } finally {
      if (loadAbortRef.current === controller) {
        setClientsLoading(false);
      }
    }
  }, [page, pageSize, searchQuery]);

  const hydrateForm = (payload: ClientDetails) => {
    setForm({
      name: payload.name || '',
      domain: payload.domain || '',
      industry: payload.industry || '',
      address: payload.address || '',
      email: payload.email || '',
      website: payload.website || '',
      contact_person_name: payload.contact_person_name || '',
      contact_person_phone: payload.contact_person_phone || '',
      contact_person_email: payload.contact_person_email || '',
      gst_number: payload.gst_number || '',
    });
  };

  const loadDetails = async (clientId: number) => {
    setDetailsLoading(true);
    try {
      const res = await client.get<ClientDetails>(
        ENDPOINTS.CLIENTS.DETAILS(clientId),
      );
      hydrateForm(res.data);
    } catch (error: any) {
      console.error('Failed to load client details', error);
      toast.error(
        error.response?.data?.error?.message || 'Failed to load client details',
      );
    } finally {
      setDetailsLoading(false);
    }
  };

  useEffect(() => {
    loadClients();
  }, [loadClients]);

  useEffect(() => {
    if (!selectedClientId) return;
    loadDetails(selectedClientId);
  }, [selectedClientId]);

  const setField = (key: keyof typeof form, value: string) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const validate = () => {
    const errors: Record<string, string> = {};

    if (!form.name.trim()) {
      errors.name = 'Client name is required';
    }

    if (!isValidEmail(form.email)) {
      errors.email = 'Enter a valid email address';
    }

    if (!isValidEmail(form.contact_person_email)) {
      errors.contact_person_email = 'Enter a valid email address';
    }

    if (form.gst_number.trim() && !isValidGst(form.gst_number)) {
      errors.gst_number = 'Enter a valid 15-character GSTIN';
    }

    if (form.contact_person_phone.trim() && !isValidPhone(form.contact_person_phone)) {
      errors.contact_person_phone = 'Enter a valid phone number';
    }

    return errors;
  };

  const toNullable = (value: string) => {
    const v = value.trim();
    return v ? v : null;
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedClientId) {
      toast.error('Please select a client first');
      return;
    }

    const errors = validate();
    const errorKeys = Object.keys(errors);
    if (errorKeys.length > 0) {
      toast.error('Please fix the highlighted fields');
      return;
    }

    setSaving(true);
    try {
      const payload = {
        name: form.name.trim(),
        domain: toNullable(form.domain),
        industry: toNullable(form.industry),
        address: toNullable(form.address),
        email: toNullable(form.email),
        website: toNullable(form.website),
        contact_person_name: toNullable(form.contact_person_name),
        contact_person_phone: toNullable(form.contact_person_phone),
        contact_person_email: toNullable(form.contact_person_email),
        gst_number: toNullable(form.gst_number),
      };

      const res = await client.patch<ClientDetails>(
        ENDPOINTS.CLIENTS.DETAILS(selectedClientId),
        payload,
      );
      hydrateForm(res.data);
      toast.success('Client details saved');

      // Refresh client list in case name changed.
      await loadClients();
    } catch (error: any) {
      console.error('Failed to save client details', error);
      toast.error(
        error.response?.data?.error?.message || 'Failed to save client details',
      );
    } finally {
      setSaving(false);
    }
  };

  const errors = validate();

  const openDeleteDialog = async () => {
    if (!selectedClientId) return;
    setDeleteState({ open: true, blockers: null, deleting: false });
    try {
      const res = await client.get<{
        project_count: number;
        lead_count: number;
      }>(ENDPOINTS.CLIENTS.DELETE_BLOCKERS(selectedClientId));
      setDeleteState((s) => ({ ...s, blockers: res.data }));
    } catch (error: any) {
      toast.error(
        error.response?.data?.error?.message ||
          error.response?.data?.detail ||
          'Failed to load delete blockers',
      );
      setDeleteState({ open: false, blockers: null, deleting: false });
    }
  };

  const performDelete = async (force: boolean) => {
    if (!selectedClientId) return;
    setDeleteState((s) => ({ ...s, deleting: true }));
    try {
      await client.delete(ENDPOINTS.CLIENTS.DELETE(selectedClientId), {
        params: force ? { force: true } : undefined,
      });
      toast.success('Client deleted');
      setDeleteState({ open: false, blockers: null, deleting: false });
      setSelectedClientId(null);
      await loadClients();
    } catch (error: any) {
      const detail = error?.response?.data?.detail;
      const msg =
        (detail && typeof detail === 'object' && detail.error?.message) ||
        (typeof detail === 'string' ? detail : null) ||
        'Failed to delete client';
      toast.error(msg);
      setDeleteState((s) => ({ ...s, deleting: false }));
    }
  };

  const handleCreate = async (payload: typeof form) => {
    const trimmed = payload.name.trim();
    if (!trimmed) {
      toast.error('Client name is required');
      return null;
    }
    if (payload.email.trim() && !isValidEmail(payload.email)) {
      toast.error('Enter a valid client email');
      return null;
    }
    if (
      payload.contact_person_email.trim() &&
      !isValidEmail(payload.contact_person_email)
    ) {
      toast.error('Enter a valid contact person email');
      return null;
    }
    if (payload.gst_number.trim() && !isValidGst(payload.gst_number)) {
      toast.error('Enter a valid 15-character GSTIN');
      return null;
    }
    if (
      payload.contact_person_phone.trim() &&
      !isValidPhone(payload.contact_person_phone)
    ) {
      toast.error('Enter a valid contact person phone');
      return null;
    }
    try {
      // Single atomic create — POST /clients/ now accepts both the basic
      // Account fields and the full ClientDetails payload, so a partial
      // create is impossible.
      const createRes = await client.post<Account>(ENDPOINTS.CLIENTS.CREATE, {
        name: trimmed,
        domain: toNullable(payload.domain),
        industry: toNullable(payload.industry),
        address: toNullable(payload.address),
        email: toNullable(payload.email),
        website: toNullable(payload.website),
        contact_person_name: toNullable(payload.contact_person_name),
        contact_person_phone: toNullable(payload.contact_person_phone),
        contact_person_email: toNullable(payload.contact_person_email),
        gst_number: toNullable(payload.gst_number),
      });
      const newId = createRes.data.id;
      toast.success(`Client "${trimmed}" created`);
      setCreateOpen(false);
      await loadClients();
      setSelectedClientId(newId);
      return newId;
    } catch (error: any) {
      const detail = error?.response?.data?.detail;
      const msg =
        error.response?.data?.error?.message ||
        (typeof detail === 'string' ? detail : null) ||
        'Failed to create client';
      toast.error(msg);
      return null;
    }
  };

  return (
    <div className="p-8 space-y-6">
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="w-12 h-12 rounded-2xl bg-blue-50 text-blue-600 flex items-center justify-center">
            <Building2 className="w-6 h-6" />
          </div>
          <div>
            <h2 className="text-xl font-black text-[#0F172A] tracking-tight">
              Client Details
            </h2>
            <p className="text-xs text-[#64748B] font-bold uppercase tracking-widest mt-1">
              {canEdit
                ? 'Create and maintain client master details'
                : 'View-only access'}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {canEdit && (
            <>
              <Button
                variant="outline"
                onClick={async () => {
                  try {
                    const res = await client.get(ENDPOINTS.CLIENTS.EXPORT, {
                      responseType: 'blob',
                    });
                    const url = window.URL.createObjectURL(new Blob([res.data]));
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = 'clients_export.xlsx';
                    a.click();
                    window.URL.revokeObjectURL(url);
                  } catch {
                    toast.error('Failed to export clients');
                  }
                }}
              >
                <Download className="w-4 h-4 mr-2" />
                Export
              </Button>
              <Button
                variant="outline"
                onClick={() => setBulkUploadOpen(true)}
              >
                <Upload className="w-4 h-4 mr-2" />
                Bulk Upload
              </Button>
              <Button onClick={() => setCreateOpen(true)}>
                <Plus className="w-4 h-4 mr-2" />
                Add Client
              </Button>
            </>
          )}
          <Button
            variant="outline"
            onClick={() => {
              if (selectedClientId) loadDetails(selectedClientId);
              else loadClients();
            }}
            isLoading={clientsLoading || detailsLoading}
          >
            <RefreshCcw className="w-4 h-4 mr-2" />
            Refresh
          </Button>
        </div>
      </div>

      {!selectedClientId && (
        <Card className="overflow-hidden">
          <div className="p-4 border-b border-slate-100 flex flex-wrap items-center gap-3 justify-between bg-white">
            <div className="relative flex-1 min-w-[260px] max-w-md">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
              <input
                type="text"
                placeholder="Search by name, domain, or industry…"
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
                className="w-full pl-10 pr-4 py-2 border border-slate-200 rounded-lg text-sm bg-slate-50 focus:outline-none focus:ring-1 focus:ring-blue-600"
              />
            </div>
            <div className="text-xs font-bold text-slate-500">
              {clientsLoading
                ? 'Loading…'
                : `${total} client${total === 1 ? '' : 's'}`}
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="bg-slate-50 border-b border-slate-100">
                  <th className="px-6 py-3 text-xs font-bold text-slate-600 uppercase tracking-wider">Client</th>
                  <th className="px-6 py-3 text-xs font-bold text-slate-600 uppercase tracking-wider">Industry</th>
                  <th className="px-6 py-3 text-xs font-bold text-slate-600 uppercase tracking-wider">Domain</th>
                  <th className="px-6 py-3 text-xs font-bold text-slate-600 uppercase tracking-wider w-12"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {clients.map((c) => (
                  <tr
                    key={c.id}
                    className="hover:bg-blue-50/40 cursor-pointer transition-colors group"
                    onClick={() => setSelectedClientId(c.id)}
                  >
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-3">
                        <div className="w-9 h-9 rounded-lg bg-blue-50 text-blue-600 flex items-center justify-center font-bold text-xs border border-blue-100">
                          {(c.name || '?').slice(0, 2).toUpperCase()}
                        </div>
                        <div>
                          <p className="text-sm font-bold text-[#0F172A] group-hover:text-blue-600">
                            {c.name}
                          </p>
                          <p className="text-[11px] text-slate-400">#{c.id}</p>
                        </div>
                      </div>
                    </td>
                    <td className="px-6 py-4 text-sm text-slate-700">
                      {c.industry || <span className="text-slate-300">—</span>}
                    </td>
                    <td className="px-6 py-4 text-sm text-slate-700">
                      {c.domain || <span className="text-slate-300">—</span>}
                    </td>
                    <td className="px-6 py-4">
                      <ChevronRight className="w-4 h-4 text-slate-400 group-hover:text-blue-600 group-hover:translate-x-0.5 transition-all" />
                    </td>
                  </tr>
                ))}
                {!clientsLoading && clients.length === 0 && (
                  <tr>
                    <td colSpan={4} className="px-6 py-16 text-center">
                      <div className="flex flex-col items-center gap-2 text-slate-400">
                        <Building2 className="w-8 h-8 text-slate-300" />
                        <p className="text-sm font-bold">
                          {searchQuery ? 'No clients match your search.' : 'No clients yet.'}
                        </p>
                      </div>
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          <div className="flex items-center justify-between gap-4 px-6 py-3 border-t border-slate-100 bg-white text-sm">
            <div className="flex items-center gap-3">
              <div className="text-xs text-slate-500">
                {total === 0
                  ? '0 results'
                  : `Showing ${(page - 1) * pageSize + 1}–${Math.min(page * pageSize, total)} of ${total}`}
              </div>
              <label className="text-xs text-slate-500 flex items-center gap-1.5">
                Rows
                <select
                  value={pageSize}
                  onChange={(e) => {
                    setPageSize(Number(e.target.value));
                    setPage(1);
                  }}
                  className="text-xs font-bold bg-slate-50 border border-slate-200 rounded px-1.5 py-0.5"
                >
                  {PAGE_SIZE_OPTIONS.map((n) => (
                    <option key={n} value={n}>{n}</option>
                  ))}
                </select>
              </label>
            </div>
            <div className="flex items-center gap-2">
              <Button
                size="sm"
                variant="outline"
                disabled={page <= 1 || clientsLoading}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
              >
                <ChevronLeft className="w-4 h-4 mr-1" />
                Prev
              </Button>
              <span className="text-xs font-bold text-slate-600 px-2">
                Page {page} / {totalPages}
              </span>
              <Button
                size="sm"
                variant="outline"
                disabled={page >= totalPages || clientsLoading}
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              >
                Next
                <ChevronRight className="w-4 h-4 ml-1" />
              </Button>
            </div>
          </div>
        </Card>
      )}

      {selectedClientId && (
      <Card className="p-6">
        <div className="flex items-center justify-between mb-4 gap-3">
          <Button variant="outline" size="sm" onClick={() => setSelectedClientId(null)}>
            <ArrowLeft className="w-4 h-4 mr-2" />
            Back to list
          </Button>
          <div className="flex items-center gap-3">
            <span className="text-xs font-bold text-slate-500">
              Editing client #{selectedClientId}
            </span>
            {canEdit && (
              <Button
                size="sm"
                variant="outline"
                className="border-red-200 text-red-600 hover:bg-red-50"
                onClick={openDeleteDialog}
              >
                <Trash2 className="w-4 h-4 mr-1.5" />
                Delete
              </Button>
            )}
          </div>
        </div>
        <form onSubmit={handleSave} className="space-y-6">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <Input
              label="Client Name *"
              placeholder="Client name"
              value={form.name}
              onChange={(e) => setField('name', e.target.value)}
              disabled={!selectedClientId || detailsLoading || !canEdit}
              error={errors.name}
            />

            <Input
              label="Client Email"
              placeholder="accounts@client.com"
              value={form.email}
              onChange={(e) => setField('email', e.target.value)}
              disabled={!selectedClientId || detailsLoading || !canEdit}
              error={errors.email}
            />

            <Input
              label="Website"
              placeholder="https://client.com"
              value={form.website}
              onChange={(e) => setField('website', e.target.value)}
              disabled={!selectedClientId || detailsLoading || !canEdit}
            />

            <Input
              label="GST Number"
              placeholder="GSTIN"
              value={form.gst_number}
              onChange={(e) => setField('gst_number', e.target.value)}
              disabled={!selectedClientId || detailsLoading || !canEdit}
              error={errors.gst_number}
            />

            <Input
              label="Contact Person Name"
              placeholder="Full name"
              value={form.contact_person_name}
              onChange={(e) => setField('contact_person_name', e.target.value)}
              disabled={!selectedClientId || detailsLoading || !canEdit}
            />

            <Input
              label="Contact Person Phone"
              placeholder="Phone number"
              value={form.contact_person_phone}
              onChange={(e) => setField('contact_person_phone', e.target.value)}
              disabled={!selectedClientId || detailsLoading || !canEdit}
              error={errors.contact_person_phone}
            />

            <Input
              label="Contact Person Email"
              placeholder="person@client.com"
              value={form.contact_person_email}
              onChange={(e) => setField('contact_person_email', e.target.value)}
              disabled={!selectedClientId || detailsLoading || !canEdit}
              error={errors.contact_person_email}
            />

            <Input
              label="Domain"
              placeholder="client.com"
              value={form.domain}
              onChange={(e) => setField('domain', e.target.value)}
              disabled={!selectedClientId || detailsLoading || !canEdit}
            />

            <Input
              label="Industry"
              placeholder="e.g. Manufacturing"
              value={form.industry}
              onChange={(e) => setField('industry', e.target.value)}
              disabled={!selectedClientId || detailsLoading || !canEdit}
            />
          </div>

          <div className="space-y-1.5">
            <label className="text-sm font-medium text-[#374151] block">
              Address
            </label>
            <textarea
              className={cn(
                'w-full bg-white border border-[#D1D5DB] rounded-lg px-4 py-2 text-[#0F172A] placeholder:text-[#94A3B8] outline-none transition-all duration-200',
                'focus:border-[#2563EB] focus:ring-1 focus:ring-[#2563EB]',
                'min-h-[120px] resize-none',
                !canEdit && 'bg-slate-50',
              )}
              placeholder="Address"
              value={form.address}
              onChange={(e) => setField('address', e.target.value)}
              disabled={!selectedClientId || detailsLoading || !canEdit}
            />
          </div>

          <div className="flex items-center justify-end gap-3">
            {!canEdit ? (
              <p className="text-xs text-[#64748B] font-bold uppercase tracking-widest">
                You have read-only access
              </p>
            ) : null}
            <Button
              type="submit"
              isLoading={saving}
              disabled={!canEdit || !selectedClientId || detailsLoading}
            >
              <Save className="w-4 h-4 mr-2" />
              Save Changes
            </Button>
          </div>
        </form>
      </Card>
      )}

      <BulkUploadModal
        open={bulkUploadOpen}
        onClose={() => setBulkUploadOpen(false)}
        onSuccess={() => loadClients()}
      />

      <CreateClientModal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onCreate={handleCreate}
      />

      {deleteState.open && (
        <DeleteClientDialog
          clientName={form.name}
          blockers={deleteState.blockers}
          deleting={deleteState.deleting}
          onCancel={() =>
            setDeleteState({ open: false, blockers: null, deleting: false })
          }
          onConfirm={performDelete}
        />
      )}
    </div>
  );
};

/* ── Create Client Modal ── */
const CreateClientModal = ({
  open,
  onClose,
  onCreate,
}: {
  open: boolean;
  onClose: () => void;
  onCreate: (form: {
    name: string;
    domain: string;
    industry: string;
    address: string;
    email: string;
    website: string;
    contact_person_name: string;
    contact_person_phone: string;
    contact_person_email: string;
    gst_number: string;
  }) => Promise<number | null>;
}) => {
  const empty = {
    name: '',
    domain: '',
    industry: '',
    address: '',
    email: '',
    website: '',
    contact_person_name: '',
    contact_person_phone: '',
    contact_person_email: '',
    gst_number: '',
  };
  const [form, setForm] = useState(empty);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!open) {
      setForm(empty);
      setSubmitting(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  if (!open) return null;

  const update = (key: keyof typeof empty, value: string) =>
    setForm((prev) => ({ ...prev, [key]: value }));

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    const id = await onCreate(form);
    setSubmitting(false);
    if (id) onClose();
  };

  return (
    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <Card
        className="w-full max-w-2xl p-7 space-y-5 animate-in zoom-in-95 duration-200"
        style={{ maxHeight: '85vh', overflowY: 'auto' }}
      >
        <div className="flex items-center justify-between">
          <h3 className="text-xl font-bold text-[#0F172A]">Add New Client</h3>
          <button
            type="button"
            onClick={onClose}
            className="p-2 hover:bg-slate-100 rounded-full"
          >
            <X size={20} className="text-slate-400" />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="space-y-5">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <Input
              label="Client Name *"
              placeholder="Acme Corp"
              value={form.name}
              onChange={(e) => update('name', e.target.value)}
              required
            />
            <Input
              label="Industry"
              placeholder="e.g. Manufacturing"
              value={form.industry}
              onChange={(e) => update('industry', e.target.value)}
            />
            <Input
              label="Domain"
              placeholder="acmecorp.com"
              value={form.domain}
              onChange={(e) => update('domain', e.target.value)}
            />
            <Input
              label="Website"
              placeholder="https://acmecorp.com"
              value={form.website}
              onChange={(e) => update('website', e.target.value)}
            />
            <Input
              label="Client Email"
              placeholder="accounts@client.com"
              value={form.email}
              onChange={(e) => update('email', e.target.value)}
            />
            <Input
              label="GST Number"
              placeholder="GSTIN"
              value={form.gst_number}
              onChange={(e) => update('gst_number', e.target.value)}
            />
            <Input
              label="Contact Person Name"
              placeholder="Full name"
              value={form.contact_person_name}
              onChange={(e) => update('contact_person_name', e.target.value)}
            />
            <Input
              label="Contact Person Phone"
              placeholder="Phone"
              value={form.contact_person_phone}
              onChange={(e) => update('contact_person_phone', e.target.value)}
            />
            <Input
              label="Contact Person Email"
              placeholder="person@client.com"
              value={form.contact_person_email}
              onChange={(e) => update('contact_person_email', e.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <label className="text-sm font-medium text-[#374151] block">
              Address
            </label>
            <textarea
              className="w-full bg-white border border-[#D1D5DB] rounded-lg px-4 py-2 text-[#0F172A] placeholder:text-[#94A3B8] outline-none focus:border-[#2563EB] focus:ring-1 focus:ring-[#2563EB] min-h-[100px] resize-none"
              placeholder="Address"
              value={form.address}
              onChange={(e) => update('address', e.target.value)}
            />
          </div>
          <div className="flex justify-end gap-3 pt-2">
            <Button
              variant="outline"
              type="button"
              onClick={onClose}
              disabled={submitting}
            >
              Cancel
            </Button>
            <Button type="submit" isLoading={submitting}>
              <Plus className="w-4 h-4 mr-2" />
              Create Client
            </Button>
          </div>
        </form>
      </Card>
    </div>
  );
};

/* ── Delete Client Dialog ── */
const DeleteClientDialog = ({
  clientName,
  blockers,
  deleting,
  onCancel,
  onConfirm,
}: {
  clientName: string;
  blockers: { project_count: number; lead_count: number } | null;
  deleting: boolean;
  onCancel: () => void;
  onConfirm: (force: boolean) => void;
}) => {
  const hasBlockers =
    !!blockers && (blockers.project_count > 0 || blockers.lead_count > 0);

  return (
    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <Card className="w-full max-w-md p-6 space-y-4 animate-in zoom-in-95 duration-200">
        <div className="flex items-start gap-3">
          <div className="w-10 h-10 rounded-full bg-red-50 text-red-600 flex items-center justify-center flex-shrink-0">
            <AlertCircle className="w-5 h-5" />
          </div>
          <div className="flex-1">
            <h3 className="text-lg font-bold text-[#0F172A]">
              Delete client{clientName ? ` "${clientName}"` : ''}?
            </h3>
            <p className="text-sm text-slate-600 mt-1">
              {!blockers
                ? 'Checking linked records…'
                : hasBlockers
                  ? 'This client has linked records.'
                  : 'No linked records found. This action cannot be undone.'}
            </p>
          </div>
        </div>

        {blockers && hasBlockers && (
          <div className="border border-amber-200 bg-amber-50 rounded-lg p-3 text-sm text-amber-800 space-y-1">
            {blockers.project_count > 0 && (
              <div>
                • <b>{blockers.project_count}</b> linked project
                {blockers.project_count === 1 ? '' : 's'}
              </div>
            )}
            {blockers.lead_count > 0 && (
              <div>
                • <b>{blockers.lead_count}</b> linked lead
                {blockers.lead_count === 1 ? '' : 's'}
              </div>
            )}
            <div className="text-xs text-amber-700 pt-1">
              Force delete will keep these records but unlink them from this client.
            </div>
          </div>
        )}

        <div className="flex justify-end gap-2 pt-2">
          <Button variant="outline" onClick={onCancel} disabled={deleting}>
            Cancel
          </Button>
          {blockers && (
            <Button
              className="bg-red-600 hover:bg-red-700 text-white"
              onClick={() => onConfirm(hasBlockers)}
              isLoading={deleting}
            >
              <Trash2 className="w-4 h-4 mr-1.5" />
              {hasBlockers ? 'Force Delete' : 'Delete'}
            </Button>
          )}
        </div>
      </Card>
    </div>
  );
};
