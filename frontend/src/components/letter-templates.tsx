import React, { useState, useEffect, useRef } from 'react';
import {
  FileText,
  Plus,
  Pencil,
  Trash2,
  Search,
  Eye,
  Download,
  Mail,
  Clock,
  X,
  Upload,
  AlertTriangle,
} from 'lucide-react';
import { Card, Button, Badge, cn } from './ui-elements';
import { toast } from 'sonner';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from './ui/dialog';
import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';

interface LetterTemplate {
  id: number;
  name: string;
  category: string;
  description: string | null;
  body: string;
  is_active: boolean;
  created_by_id: number | null;
  created_at: string;
  updated_at: string;
}

interface Placeholder {
  token: string;
  label: string;
  source: string;
}

interface EmployeeOption {
  id: number;
  employee_id: string;
  designation: string;
  department: string;
  date_of_joining: string;
  user: { id: number; full_name: string; email: string };
}

const CATEGORY_OPTIONS = [
  'custom',
  'offer',
  'appointment',
  'confirmation',
  'warning',
  'verification',
];

const CATEGORY_COLOR: Record<string, string> = {
  custom: 'bg-slate-50 text-slate-700 border-slate-200',
  offer: 'bg-blue-50 text-blue-700 border-blue-200',
  appointment: 'bg-indigo-50 text-indigo-700 border-indigo-200',
  confirmation: 'bg-green-50 text-green-700 border-green-200',
  warning: 'bg-amber-50 text-amber-700 border-amber-200',
  verification: 'bg-violet-50 text-violet-700 border-violet-200',
};

export const LetterTemplatesHR = () => {
  const [view, setView] = useState<'templates' | 'generate'>('templates');
  const [templates, setTemplates] = useState<LetterTemplate[]>([]);
  const [placeholders, setPlaceholders] = useState<Placeholder[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  // Editor dialog
  const [editorOpen, setEditorOpen] = useState(false);
  const [editing, setEditing] = useState<LetterTemplate | null>(null);
  const [form, setForm] = useState({
    name: '',
    category: 'custom',
    description: '',
    body: '',
    is_active: true,
  });
  const [saving, setSaving] = useState(false);
  const bodyRef = useRef<HTMLTextAreaElement | null>(null);
  const fileRef = useRef<HTMLInputElement | null>(null);

  // Generate view
  const [genTemplateId, setGenTemplateId] = useState<number | ''>('');
  const [empSearch, setEmpSearch] = useState('');
  const [empDropdown, setEmpDropdown] = useState<EmployeeOption[]>([]);
  const [isSearchingEmp, setIsSearchingEmp] = useState(false);
  const [selectedEmp, setSelectedEmp] = useState<EmployeeOption | null>(null);
  const [preview, setPreview] = useState<{
    rendered_body: string;
    missing_placeholders: string[];
  } | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [lastLetterId, setLastLetterId] = useState<number | null>(null);
  const [extraCtx, setExtraCtx] = useState<Record<string, string>>({});

  useEffect(() => {
    fetchTemplates();
    fetchPlaceholders();
  }, []);

  useEffect(() => {
    if (empSearch.length < 3) {
      setEmpDropdown([]);
      return;
    }
    const timer = setTimeout(async () => {
      setIsSearchingEmp(true);
      try {
        const res = await client.get<{ items: EmployeeOption[] }>(
          ENDPOINTS.HR.EMPLOYEES +
            `?search=${encodeURIComponent(empSearch)}&size=15`
        );
        setEmpDropdown(res.data.items || []);
      } catch {
        setEmpDropdown([]);
      } finally {
        setIsSearchingEmp(false);
      }
    }, 300);
    return () => clearTimeout(timer);
  }, [empSearch]);

  const fetchTemplates = async () => {
    setIsLoading(true);
    try {
      const res = await client.get<LetterTemplate[]>(
        ENDPOINTS.HR.LETTER_TEMPLATES
      );
      setTemplates(res.data);
    } catch {
      toast.error('Failed to load templates');
    } finally {
      setIsLoading(false);
    }
  };

  const fetchPlaceholders = async () => {
    try {
      const res = await client.get<Placeholder[]>(
        ENDPOINTS.HR.LETTER_TEMPLATE_PLACEHOLDERS
      );
      setPlaceholders(res.data);
    } catch {
      // non-fatal — palette just won't show
    }
  };

  const openCreate = () => {
    setEditing(null);
    setForm({
      name: '',
      category: 'custom',
      description: '',
      body: '',
      is_active: true,
    });
    setEditorOpen(true);
  };

  const openEdit = (t: LetterTemplate) => {
    setEditing(t);
    setForm({
      name: t.name,
      category: t.category,
      description: t.description || '',
      body: t.body,
      is_active: t.is_active,
    });
    setEditorOpen(true);
  };

  const insertToken = (token: string) => {
    const ta = bodyRef.current;
    const snippet = `{{${token}}}`;
    if (!ta) {
      setForm((f) => ({ ...f, body: f.body + snippet }));
      return;
    }
    const start = ta.selectionStart ?? form.body.length;
    const end = ta.selectionEnd ?? form.body.length;
    const next = form.body.slice(0, start) + snippet + form.body.slice(end);
    setForm((f) => ({ ...f, body: next }));
    requestAnimationFrame(() => {
      ta.focus();
      const pos = start + snippet.length;
      ta.setSelectionRange(pos, pos);
    });
  };

  const onFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      setForm((f) => ({ ...f, body: String(reader.result || '') }));
      toast.success(`Loaded ${file.name}`);
    };
    reader.readAsText(file);
    if (fileRef.current) fileRef.current.value = '';
  };

  const saveTemplate = async () => {
    if (!form.name.trim() || !form.body.trim()) {
      toast.error('Name and body are required');
      return;
    }
    setSaving(true);
    try {
      if (editing) {
        await client.patch(
          ENDPOINTS.HR.LETTER_TEMPLATE_DETAIL(editing.id),
          form
        );
        toast.success('Template updated');
      } else {
        await client.post(ENDPOINTS.HR.LETTER_TEMPLATES, form);
        toast.success('Template created');
      }
      setEditorOpen(false);
      fetchTemplates();
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Failed to save template');
    } finally {
      setSaving(false);
    }
  };

  const deleteTemplate = async (t: LetterTemplate) => {
    if (!window.confirm(`Deactivate template "${t.name}"?`)) return;
    try {
      await client.delete(ENDPOINTS.HR.LETTER_TEMPLATE_DETAIL(t.id));
      toast.success('Template deactivated');
      fetchTemplates();
    } catch {
      toast.error('Failed to deactivate template');
    }
  };

  const runPreview = async () => {
    if (!genTemplateId || !selectedEmp) {
      toast.error('Pick a template and employee');
      return;
    }
    setPreviewing(true);
    setPreview(null);
    try {
      const res = await client.post(
        ENDPOINTS.HR.LETTER_TEMPLATE_PREVIEW(genTemplateId as number),
        {
          employee_id: selectedEmp.id,
          extra_context: extraCtx,
        }
      );
      setPreview(res.data as any);
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Preview failed');
    } finally {
      setPreviewing(false);
    }
  };

  const generate = async (thenEmail: boolean) => {
    if (!genTemplateId || !selectedEmp) {
      toast.error('Pick a template and employee');
      return;
    }
    setGenerating(true);
    try {
      const res = await client.post(
        ENDPOINTS.HR.LETTER_TEMPLATE_GENERATE(genTemplateId as number),
        { employee_id: selectedEmp.id, extra_context: extraCtx },
        { responseType: 'blob' }
      );
      const blob = new Blob([res.data as any], { type: 'application/pdf' });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      const disp = res.headers?.['content-disposition'] || '';
      const m = disp.match(/filename="(.+?)"/);
      link.download = m ? m[1] : `letter_${selectedEmp.id}.pdf`;
      link.click();
      window.URL.revokeObjectURL(url);
      toast.success('Letter generated');

      // Find the just-created letter to enable emailing
      const list = await client.get<any[]>(
        ENDPOINTS.HR.LETTERS + `?employee_id=${selectedEmp.id}`
      );
      const custom = (list.data || []).filter(
        (l) => l.letter_type === 'custom'
      );
      const newest = custom[0];
      if (newest) setLastLetterId(newest.id);

      if (thenEmail && newest) {
        await sendEmail(newest.id);
      }
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Failed to generate');
    } finally {
      setGenerating(false);
    }
  };

  const sendEmail = async (letterId: number) => {
    try {
      const res = await client.post(ENDPOINTS.HR.LETTER_SEND(letterId), {});
      const data = res.data as any;
      if (data.status === 'sent') {
        toast.success(`Emailed to employee (via ${data.provider})`);
      } else {
        toast.error(`Send failed: ${data.error || 'unknown error'}`);
      }
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Failed to send email');
    }
  };

  const activeTemplates = templates.filter((t) => t.is_active);
  const selectedTemplate = templates.find((t) => t.id === genTemplateId);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-gray-900">
            Letter Templates
          </h2>
          <p className="text-sm text-gray-500 mt-0.5">
            Author reusable letter templates with placeholders, then
            generate &amp; email letters per employee
          </p>
        </div>
        {view === 'templates' && (
          <Button
            onClick={openCreate}
            className="bg-indigo-600 hover:bg-indigo-700 text-white gap-2"
          >
            <Plus className="w-4 h-4" />
            New Template
          </Button>
        )}
      </div>

      {/* View toggle */}
      <div className="flex gap-1 border-b border-gray-200">
        {(['templates', 'generate'] as const).map((v) => (
          <button
            key={v}
            onClick={() => setView(v)}
            className={cn(
              'px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors',
              view === v
                ? 'border-indigo-600 text-indigo-600'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            )}
          >
            {v === 'templates' ? 'Manage Templates' : 'Generate Letter'}
          </button>
        ))}
      </div>

      {view === 'templates' ? (
        <Card className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50 border-b">
                  <th className="text-left px-4 py-3 font-medium text-gray-600">
                    Name
                  </th>
                  <th className="text-left px-4 py-3 font-medium text-gray-600">
                    Category
                  </th>
                  <th className="text-left px-4 py-3 font-medium text-gray-600">
                    Description
                  </th>
                  <th className="text-left px-4 py-3 font-medium text-gray-600">
                    Status
                  </th>
                  <th className="text-right px-4 py-3 font-medium text-gray-600">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  <tr>
                    <td colSpan={5} className="px-4 py-12 text-center text-gray-400">
                      Loading templates...
                    </td>
                  </tr>
                ) : templates.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="px-4 py-12 text-center text-gray-400">
                      <FileText className="w-8 h-8 mx-auto mb-2 opacity-40" />
                      No templates yet. Click "New Template" to author one.
                    </td>
                  </tr>
                ) : (
                  templates.map((t) => (
                    <tr
                      key={t.id}
                      className={cn(
                        'border-b hover:bg-gray-50 transition-colors',
                        !t.is_active && 'opacity-50'
                      )}
                    >
                      <td className="px-4 py-3 font-medium text-gray-900">
                        {t.name}
                      </td>
                      <td className="px-4 py-3">
                        <Badge
                          className={cn(
                            'text-xs',
                            CATEGORY_COLOR[t.category] ||
                              CATEGORY_COLOR.custom
                          )}
                        >
                          {t.category}
                        </Badge>
                      </td>
                      <td className="px-4 py-3 text-gray-500 max-w-xs truncate">
                        {t.description || '-'}
                      </td>
                      <td className="px-4 py-3">
                        {t.is_active ? (
                          <Badge className="bg-green-50 text-green-700 border-green-200 text-xs">
                            active
                          </Badge>
                        ) : (
                          <Badge className="bg-gray-100 text-gray-500 border-gray-200 text-xs">
                            inactive
                          </Badge>
                        )}
                      </td>
                      <td className="px-4 py-3 text-right whitespace-nowrap">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => openEdit(t)}
                          className="text-gray-600 hover:text-indigo-700 gap-1"
                        >
                          <Pencil className="w-3.5 h-3.5" />
                        </Button>
                        {t.is_active && (
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => deleteTemplate(t)}
                            className="text-gray-600 hover:text-rose-700 gap-1"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </Button>
                        )}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </Card>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Left: pick template + employee */}
          <Card className="p-5 space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1.5">
                Template
              </label>
              <select
                value={genTemplateId}
                onChange={(e) => {
                  setGenTemplateId(
                    e.target.value ? Number(e.target.value) : ''
                  );
                  setPreview(null);
                }}
                className="w-full px-3 py-2 border rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
              >
                <option value="">Select a template...</option>
                {activeTemplates.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name} ({t.category})
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1.5">
                Employee
              </label>
              {selectedEmp ? (
                <div className="flex items-center gap-3 px-3 py-2.5 bg-indigo-50 border border-indigo-200 rounded-lg">
                  <div className="w-8 h-8 rounded-full bg-indigo-200 flex items-center justify-center text-xs font-bold text-indigo-700">
                    {selectedEmp.user?.full_name?.charAt(0) || '?'}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium text-indigo-900 truncate">
                      {selectedEmp.user?.full_name}
                    </div>
                    <div className="text-xs text-indigo-600">
                      {selectedEmp.employee_id} &middot;{' '}
                      {selectedEmp.designation}
                    </div>
                  </div>
                  <button
                    onClick={() => {
                      setSelectedEmp(null);
                      setEmpSearch('');
                      setPreview(null);
                    }}
                    className="text-indigo-400 hover:text-indigo-600 p-1"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>
              ) : (
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                  <input
                    type="text"
                    placeholder="Type at least 3 characters..."
                    value={empSearch}
                    onChange={(e) => setEmpSearch(e.target.value)}
                    className="w-full pl-10 pr-4 py-2 border rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
                  />
                  {empSearch.length >= 3 && (
                    <div className="absolute z-10 w-full mt-1 bg-white border border-gray-200 rounded-lg shadow-lg max-h-48 overflow-y-auto divide-y">
                      {isSearchingEmp ? (
                        <div className="px-4 py-3 text-sm text-gray-400 text-center">
                          Searching...
                        </div>
                      ) : empDropdown.length === 0 ? (
                        <div className="px-4 py-3 text-sm text-gray-400 text-center">
                          No employees found
                        </div>
                      ) : (
                        empDropdown.map((emp) => (
                          <button
                            key={emp.id}
                            onClick={() => {
                              setSelectedEmp(emp);
                              setEmpSearch('');
                            }}
                            className="w-full flex items-center gap-3 px-3 py-2 text-left hover:bg-indigo-50 transition-colors"
                          >
                            <div className="w-8 h-8 rounded-full bg-gray-200 flex items-center justify-center text-xs font-bold text-gray-600">
                              {emp.user?.full_name?.charAt(0) || '?'}
                            </div>
                            <div className="flex-1 min-w-0">
                              <div className="text-sm font-medium truncate">
                                {emp.user?.full_name}
                              </div>
                              <div className="text-xs text-gray-500">
                                {emp.employee_id} &middot; {emp.designation}
                              </div>
                            </div>
                          </button>
                        ))
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Extra context for any {{custom}} tokens */}
            {selectedTemplate && (
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1.5">
                  Extra context{' '}
                  <span className="text-gray-400 font-normal">
                    (fills any non-standard placeholders)
                  </span>
                </label>
                <textarea
                  placeholder='One per line, e.g. purpose=visa application'
                  rows={3}
                  className="w-full px-3 py-2 border rounded-lg text-sm font-mono focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
                  onChange={(e) => {
                    const ctx: Record<string, string> = {};
                    e.target.value.split('\n').forEach((line) => {
                      const idx = line.indexOf('=');
                      if (idx > 0) {
                        ctx[line.slice(0, idx).trim()] = line
                          .slice(idx + 1)
                          .trim();
                      }
                    });
                    setExtraCtx(ctx);
                  }}
                />
              </div>
            )}

            <div className="flex gap-2 pt-2">
              <Button
                variant="outline"
                onClick={runPreview}
                disabled={!genTemplateId || !selectedEmp || previewing}
                className="gap-2"
              >
                <Eye className="w-4 h-4" />
                {previewing ? 'Previewing...' : 'Preview'}
              </Button>
              <Button
                onClick={() => generate(false)}
                disabled={!genTemplateId || !selectedEmp || generating}
                className="bg-indigo-600 hover:bg-indigo-700 text-white gap-2"
              >
                {generating ? (
                  <Clock className="w-4 h-4 animate-spin" />
                ) : (
                  <Download className="w-4 h-4" />
                )}
                Generate
              </Button>
              <Button
                onClick={() => generate(true)}
                disabled={!genTemplateId || !selectedEmp || generating}
                variant="outline"
                className="gap-2"
              >
                <Mail className="w-4 h-4" />
                Generate &amp; Email
              </Button>
            </div>
            {lastLetterId && (
              <button
                onClick={() => sendEmail(lastLetterId)}
                className="text-xs text-indigo-600 hover:underline"
              >
                Re-send last generated letter by email
              </button>
            )}
          </Card>

          {/* Right: preview */}
          <Card className="p-5">
            <div className="text-sm font-medium text-gray-700 mb-3">
              Preview
            </div>
            {preview ? (
              <div className="space-y-3">
                {preview.missing_placeholders.length > 0 && (
                  <div className="flex items-start gap-2 p-3 bg-amber-50 border border-amber-200 rounded-lg text-xs text-amber-800">
                    <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
                    <div>
                      Unresolved placeholders:{' '}
                      <span className="font-mono font-medium">
                        {preview.missing_placeholders
                          .map((p) => `{{${p}}}`)
                          .join(', ')}
                      </span>
                      . Add them under "Extra context".
                    </div>
                  </div>
                )}
                <pre className="whitespace-pre-wrap text-sm text-gray-800 bg-gray-50 border rounded-lg p-4 max-h-[60vh] overflow-y-auto font-sans">
                  {preview.rendered_body}
                </pre>
              </div>
            ) : (
              <div className="text-sm text-gray-400 text-center py-16">
                <Eye className="w-8 h-8 mx-auto mb-2 opacity-40" />
                Select a template and employee, then click Preview.
              </div>
            )}
          </Card>
        </div>
      )}

      {/* Editor dialog */}
      <Dialog open={editorOpen} onOpenChange={setEditorOpen}>
        <DialogContent className="max-w-3xl max-h-[92vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <FileText className="w-5 h-5 text-indigo-600" />
              {editing ? 'Edit Template' : 'New Template'}
            </DialogTitle>
          </DialogHeader>

          <div className="space-y-4 py-2">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">
                  Name
                </label>
                <input
                  type="text"
                  value={form.name}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, name: e.target.value }))
                  }
                  className="w-full px-3 py-2 border rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">
                  Category
                </label>
                <select
                  value={form.category}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, category: e.target.value }))
                  }
                  className="w-full px-3 py-2 border rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
                >
                  {CATEGORY_OPTIONS.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">
                Description
              </label>
              <input
                type="text"
                value={form.description}
                onChange={(e) =>
                  setForm((f) => ({ ...f, description: e.target.value }))
                }
                className="w-full px-3 py-2 border rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
              />
            </div>

            {/* Placeholder palette */}
            {placeholders.length > 0 && (
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1.5">
                  Insert placeholder
                </label>
                <div className="flex flex-wrap gap-1.5">
                  {placeholders.map((p) => (
                    <button
                      key={p.token}
                      type="button"
                      onClick={() => insertToken(p.token)}
                      title={`${p.label} (${p.source})`}
                      className="px-2 py-1 text-xs font-mono rounded border border-gray-200 bg-gray-50 hover:bg-indigo-50 hover:border-indigo-300 text-gray-700"
                    >
                      {`{{${p.token}}}`}
                    </button>
                  ))}
                </div>
              </div>
            )}

            <div>
              <div className="flex items-center justify-between mb-1">
                <label className="block text-xs font-medium text-gray-600">
                  Body
                </label>
                <button
                  type="button"
                  onClick={() => fileRef.current?.click()}
                  className="text-xs text-indigo-600 hover:underline flex items-center gap-1"
                >
                  <Upload className="w-3 h-3" />
                  Upload .txt
                </button>
                <input
                  ref={fileRef}
                  type="file"
                  accept=".txt,text/plain"
                  onChange={onFileUpload}
                  className="hidden"
                />
              </div>
              <textarea
                ref={bodyRef}
                value={form.body}
                onChange={(e) =>
                  setForm((f) => ({ ...f, body: e.target.value }))
                }
                rows={12}
                placeholder="Write the letter body. Use {{placeholders}} — separate paragraphs with a blank line."
                className="w-full px-3 py-2 border rounded-lg text-sm font-mono focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
              />
            </div>

            {editing && (
              <label className="flex items-center gap-2 text-sm text-gray-700">
                <input
                  type="checkbox"
                  checked={form.is_active}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, is_active: e.target.checked }))
                  }
                />
                Active
              </label>
            )}
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setEditorOpen(false)}>
              Cancel
            </Button>
            <Button
              onClick={saveTemplate}
              disabled={saving}
              className="bg-indigo-600 hover:bg-indigo-700 text-white gap-2"
            >
              {saving ? (
                <>
                  <Clock className="w-4 h-4 animate-spin" />
                  Saving...
                </>
              ) : (
                <>
                  <FileText className="w-4 h-4" />
                  {editing ? 'Update' : 'Create'}
                </>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};
