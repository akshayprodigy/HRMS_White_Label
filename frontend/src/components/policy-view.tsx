import React, { useState, useEffect, useCallback } from 'react';
import {
  FileText,
  CheckCircle,
  Download,
  Shield,
  Clock,
  AlertCircle,
  Eye,
  Upload,
  Trash2,
  X,
  Plus,
  FileUp
} from 'lucide-react';
import { Card, Button, Badge } from './ui-elements';
import { toast } from 'sonner@2.0.3';
import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';

const errMsg = (err: any, fallback = 'Something went wrong'): string => {
  const detail = err?.response?.data?.detail;
  if (!detail) return err?.message || fallback;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) return detail.map((d: any) => d?.msg || JSON.stringify(d)).join('; ');
  return fallback;
};

interface Policy {
    id: number;
    title: string;
    description: string;
    file_url: string;
    version: string;
    is_active: boolean;
    created_at: string;
}

export const PolicyView = () => {
    const [policies, setPolicies] = useState<Policy[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [showUploadModal, setShowUploadModal] = useState(false);
    const [deleteTarget, setDeleteTarget] = useState<Policy | null>(null);
    const [userRole, setUserRole] = useState('');

    useEffect(() => {
        const role = localStorage.getItem('hr_role') || '';
        setUserRole(role);
        fetchPolicies();
    }, []);

    const isHR = userRole === 'hr' || userRole === 'super admin' || userRole === 'admin';

    const fetchPolicies = async () => {
        setIsLoading(true);
        try {
            const res = await client.get(ENDPOINTS.HR.POLICIES);
            setPolicies(res.data);
        } catch (error) {
            toast.error("Failed to load policies");
        } finally {
            setIsLoading(false);
        }
    };

    const handleAcknowledge = async (id: number) => {
        try {
            await client.post(ENDPOINTS.HR.POLICY_ACKNOWLEDGE(id));
            toast.success("Policy acknowledged successfully");
            fetchPolicies();
        } catch (error: any) {
            toast.error(errMsg(error, 'Acknowledgement failed'));
        }
    };

    const handleDelete = async () => {
        if (!deleteTarget) return;
        try {
            await client.delete(ENDPOINTS.HR.POLICY_DELETE(deleteTarget.id));
            toast.success(`"${deleteTarget.title}" deleted successfully`);
            setDeleteTarget(null);
            fetchPolicies();
        } catch (error: any) {
            toast.error(errMsg(error, 'Failed to delete policy'));
        }
    };

    const handleDownload = async (policy: Policy) => {
        try {
            const res = await client.get(ENDPOINTS.HR.POLICY_DOWNLOAD(policy.id), { responseType: 'blob' });
            const url = window.URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }));
            const a = document.createElement('a');
            a.href = url;
            a.download = `${policy.title}.pdf`;
            a.click();
            window.URL.revokeObjectURL(url);
        } catch {
            toast.error("Failed to download policy");
        }
    };

    const handleViewPdf = async (policy: Policy) => {
        try {
            const res = await client.get(ENDPOINTS.HR.POLICY_DOWNLOAD(policy.id), { responseType: 'blob' });
            const url = window.URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }));
            window.open(url, '_blank');
        } catch {
            toast.error("Failed to open policy");
        }
    };

    if (isLoading) {
        return <div className="p-20 text-center font-black uppercase text-slate-400 tracking-widest animate-pulse">Synchronizing Policy Bureau...</div>;
    }

    return (
        <div className="p-8 space-y-8 max-w-[1200px] mx-auto animate-in fade-in duration-500">
            <div className="flex justify-between items-end mb-8">
                <div>
                    <h2 className="text-3xl font-black text-[#0F172A] tracking-tighter uppercase">Corporate Policy Center</h2>
                    <p className="text-[#64748B] font-bold uppercase tracking-widest text-[10px] mt-1">Official Governance & Operational Standards Manifest</p>
                </div>
                <div className="flex gap-3 items-center">
                    <Badge variant="neutral" className="bg-slate-100 border-slate-200 text-[#0F172A] p-2 px-4 rounded-xl text-[10px] font-black uppercase"><Shield size={14} className="mr-2 text-blue-600"/> ISO 27001 Compliant</Badge>
                    {isHR && (
                        <Button
                            onClick={() => setShowUploadModal(true)}
                            className="h-10 bg-blue-600 text-white rounded-xl text-[10px] font-black uppercase tracking-widest hover:bg-blue-700 transition-all flex items-center gap-2 px-5"
                        >
                            <Plus size={16} /> Upload Policy
                        </Button>
                    )}
                </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {policies.length === 0 ? (
                    <div className="col-span-full p-20 text-center bg-white rounded-3xl border border-dashed border-slate-200">
                        <FileText size={48} className="mx-auto mb-4 text-slate-300" />
                        <p className="text-slate-400 font-bold uppercase tracking-widest text-sm">No active policies found</p>
                        {isHR && <p className="text-slate-300 text-xs mt-2">Click "Upload Policy" to add a new company policy PDF</p>}
                    </div>
                ) : policies.map((policy) => (
                    <Card key={policy.id} className="p-0 border-slate-200 shadow-sm overflow-hidden bg-white hover:border-blue-600 transition-all flex flex-col group">
                        <div className="p-8 flex-1">
                             <div className="flex justify-between items-start mb-6">
                                <div className="p-4 bg-red-50 text-red-600 rounded-2xl group-hover:bg-red-600 group-hover:text-white transition-all">
                                    <FileText size={24} />
                                </div>
                                <div className="flex items-center gap-2">
                                    <Badge variant="neutral" className="bg-slate-50 text-slate-500 text-[9px] font-black uppercase">v{policy.version}</Badge>
                                    {isHR && (
                                        <button
                                            onClick={() => setDeleteTarget(policy)}
                                            className="p-2 text-slate-300 hover:text-red-500 hover:bg-red-50 rounded-lg transition-all"
                                            title="Delete policy"
                                        >
                                            <Trash2 size={16} />
                                        </button>
                                    )}
                                </div>
                             </div>
                             <h3 className="text-xl font-black text-[#0F172A] tracking-tight mb-2 uppercase">{policy.title}</h3>
                             <p className="text-xs text-slate-500 font-medium leading-relaxed mb-8">{policy.description}</p>

                             <div className="flex flex-wrap gap-3 mt-auto">
                                <button
                                    onClick={() => handleViewPdf(policy)}
                                    className="flex-1 flex items-center justify-center gap-2 h-12 bg-slate-900 text-white rounded-xl text-[10px] font-black uppercase tracking-widest hover:bg-slate-800 transition-all"
                                >
                                    <Eye size={16} /> View PDF
                                </button>
                                <button
                                    onClick={() => handleDownload(policy)}
                                    className="h-12 w-12 flex items-center justify-center bg-slate-100 text-slate-600 rounded-xl hover:bg-slate-200 transition-all"
                                    title="Download PDF"
                                >
                                    <Download size={16} />
                                </button>
                                <Button
                                    onClick={() => handleAcknowledge(policy.id)}
                                    className="flex-1 h-12 bg-blue-600 text-white rounded-xl text-[10px] font-black uppercase tracking-widest hover:bg-blue-700 transition-all"
                                >
                                    <CheckCircle size={16} className="mr-2"/> Acknowledge
                                </Button>
                             </div>
                        </div>
                        <div className="px-8 py-4 bg-slate-50/50 border-t border-slate-100 flex items-center justify-between">
                            <div className="flex items-center gap-2 text-slate-400">
                                <Clock size={12} />
                                <span className="text-[9px] font-bold uppercase">Published: {new Date(policy.created_at).toLocaleDateString()}</span>
                            </div>
                            <Badge variant="neutral" className="bg-green-50 text-green-600 text-[8px] font-black uppercase border-green-100">PDF Document</Badge>
                        </div>
                    </Card>
                ))}
            </div>

            <Card className="p-8 border-none bg-[#0F172A] text-white overflow-hidden relative">
                <div className="relative z-10">
                    <h4 className="text-xl font-black tracking-tight mb-2 uppercase">Acknowledgement Protocol</h4>
                    <p className="text-slate-400 text-xs font-medium max-w-xl leading-relaxed">
                        By clicking "Acknowledge", you verify that you have read, understood, and agree to abide by the terms set forth in the corporate document. Digital signatures are logged with IP & timestamp for audit integrity.
                    </p>
                </div>
                <AlertCircle size={120} className="absolute -right-10 -bottom-10 opacity-5 rotate-12" />
            </Card>

            {/* Upload Modal */}
            {showUploadModal && <UploadPolicyModal onClose={() => setShowUploadModal(false)} onSuccess={() => { setShowUploadModal(false); fetchPolicies(); }} />}

            {/* Delete Confirmation Modal */}
            {deleteTarget && (
                <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4" onClick={() => setDeleteTarget(null)}>
                    <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md p-8 animate-in zoom-in-95 duration-200" onClick={e => e.stopPropagation()}>
                        <div className="flex items-center gap-4 mb-6">
                            <div className="p-3 bg-red-50 rounded-xl">
                                <Trash2 size={24} className="text-red-500" />
                            </div>
                            <div>
                                <h3 className="text-lg font-black text-[#0F172A] uppercase tracking-tight">Delete Policy</h3>
                                <p className="text-xs text-slate-500">This action cannot be undone</p>
                            </div>
                        </div>
                        <p className="text-sm text-slate-600 mb-6">
                            Are you sure you want to delete <strong>"{deleteTarget.title}"</strong>? The PDF file and all acknowledgement records will be permanently removed.
                        </p>
                        <div className="flex gap-3">
                            <Button onClick={() => setDeleteTarget(null)} className="flex-1 h-11 bg-slate-100 text-slate-700 rounded-xl text-xs font-black uppercase hover:bg-slate-200">
                                Cancel
                            </Button>
                            <Button onClick={handleDelete} className="flex-1 h-11 bg-red-600 text-white rounded-xl text-xs font-black uppercase hover:bg-red-700">
                                Delete Policy
                            </Button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};


// ─── Upload Policy Modal ───────────────────────────────────────

const UploadPolicyModal = ({ onClose, onSuccess }: { onClose: () => void; onSuccess: () => void }) => {
    const [title, setTitle] = useState('');
    const [description, setDescription] = useState('');
    const [version, setVersion] = useState('1.0');
    const [file, setFile] = useState<File | null>(null);
    const [isUploading, setIsUploading] = useState(false);
    const [dragOver, setDragOver] = useState(false);

    const handleDrop = useCallback((e: React.DragEvent) => {
        e.preventDefault();
        setDragOver(false);
        const dropped = e.dataTransfer.files[0];
        if (dropped && dropped.type === 'application/pdf') {
            setFile(dropped);
            if (!title) setTitle(dropped.name.replace(/\.pdf$/i, '').replace(/[-_]/g, ' '));
        } else {
            toast.error("Only PDF files are allowed");
        }
    }, [title]);

    const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
        const selected = e.target.files?.[0];
        if (selected && selected.type === 'application/pdf') {
            setFile(selected);
            if (!title) setTitle(selected.name.replace(/\.pdf$/i, '').replace(/[-_]/g, ' '));
        } else if (selected) {
            toast.error("Only PDF files are allowed");
        }
    };

    const handleUpload = async () => {
        if (!file || !title.trim()) {
            toast.error("Title and PDF file are required");
            return;
        }

        setIsUploading(true);
        try {
            const formData = new FormData();
            formData.append('file', file);

            const params = new URLSearchParams();
            params.set('title', title.trim());
            if (description.trim()) params.set('description', description.trim());
            params.set('version', version.trim() || '1.0');

            await client.post(`${ENDPOINTS.HR.POLICY_UPLOAD}?${params.toString()}`, formData, {
                headers: { 'Content-Type': 'multipart/form-data' },
            });

            toast.success(`"${title}" uploaded successfully`);
            onSuccess();
        } catch (error: any) {
            toast.error(errMsg(error, 'Upload failed'));
        } finally {
            setIsUploading(false);
        }
    };

    const formatSize = (bytes: number) => {
        if (bytes < 1024) return `${bytes} B`;
        if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
        return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    };

    return (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4" onClick={onClose}>
            <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg animate-in zoom-in-95 duration-200" onClick={e => e.stopPropagation()}>
                <div className="p-6 border-b border-slate-100 flex items-center justify-between">
                    <div className="flex items-center gap-3">
                        <div className="p-2.5 bg-blue-50 rounded-xl">
                            <Upload size={20} className="text-blue-600" />
                        </div>
                        <div>
                            <h3 className="text-lg font-black text-[#0F172A] uppercase tracking-tight">Upload Policy</h3>
                            <p className="text-[10px] text-slate-400 font-bold uppercase tracking-widest">Add new company policy document</p>
                        </div>
                    </div>
                    <button onClick={onClose} className="p-2 hover:bg-slate-100 rounded-lg transition-colors">
                        <X size={20} className="text-slate-400" />
                    </button>
                </div>

                <div className="p-6 space-y-5">
                    {/* Drop Zone */}
                    <div
                        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
                        onDragLeave={() => setDragOver(false)}
                        onDrop={handleDrop}
                        className={`border-2 border-dashed rounded-2xl p-8 text-center transition-all cursor-pointer ${
                            dragOver ? 'border-blue-500 bg-blue-50' : file ? 'border-green-300 bg-green-50' : 'border-slate-200 hover:border-blue-300 hover:bg-blue-50/30'
                        }`}
                        onClick={() => document.getElementById('policy-file-input')?.click()}
                    >
                        <input
                            id="policy-file-input"
                            type="file"
                            accept=".pdf"
                            className="hidden"
                            onChange={handleFileSelect}
                        />
                        {file ? (
                            <div className="flex items-center justify-center gap-3">
                                <FileText size={24} className="text-green-600" />
                                <div className="text-left">
                                    <p className="text-sm font-black text-green-800">{file.name}</p>
                                    <p className="text-[10px] text-green-600 font-bold">{formatSize(file.size)}</p>
                                </div>
                                <button
                                    onClick={(e) => { e.stopPropagation(); setFile(null); }}
                                    className="p-1.5 hover:bg-green-100 rounded-lg ml-2"
                                >
                                    <X size={16} className="text-green-600" />
                                </button>
                            </div>
                        ) : (
                            <>
                                <FileUp size={36} className="mx-auto mb-3 text-slate-300" />
                                <p className="text-sm font-black text-slate-500 uppercase tracking-wide">Drop PDF here or click to browse</p>
                                <p className="text-[10px] text-slate-400 mt-1">Maximum file size: 25MB</p>
                            </>
                        )}
                    </div>

                    {/* Title */}
                    <div>
                        <label className="text-[10px] font-black text-slate-500 uppercase tracking-widest mb-1.5 block">Policy Title *</label>
                        <input
                            type="text"
                            value={title}
                            onChange={e => setTitle(e.target.value)}
                            placeholder="e.g. Time Office Policy"
                            className="w-full h-11 bg-slate-50 border border-slate-200 rounded-xl px-4 text-sm font-bold focus:ring-2 focus:ring-blue-600/10 outline-none"
                        />
                    </div>

                    {/* Description */}
                    <div>
                        <label className="text-[10px] font-black text-slate-500 uppercase tracking-widest mb-1.5 block">Description</label>
                        <textarea
                            value={description}
                            onChange={e => setDescription(e.target.value)}
                            placeholder="Brief description of the policy..."
                            rows={2}
                            className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-sm font-medium focus:ring-2 focus:ring-blue-600/10 outline-none resize-none"
                        />
                    </div>

                    {/* Version */}
                    <div>
                        <label className="text-[10px] font-black text-slate-500 uppercase tracking-widest mb-1.5 block">Version</label>
                        <input
                            type="text"
                            value={version}
                            onChange={e => setVersion(e.target.value)}
                            placeholder="1.0"
                            className="w-full h-11 bg-slate-50 border border-slate-200 rounded-xl px-4 text-sm font-bold focus:ring-2 focus:ring-blue-600/10 outline-none"
                        />
                    </div>
                </div>

                <div className="p-6 border-t border-slate-100 flex gap-3">
                    <Button onClick={onClose} className="flex-1 h-11 bg-slate-100 text-slate-700 rounded-xl text-xs font-black uppercase hover:bg-slate-200">
                        Cancel
                    </Button>
                    <Button
                        onClick={handleUpload}
                        disabled={isUploading || !file || !title.trim()}
                        className="flex-1 h-11 bg-blue-600 text-white rounded-xl text-xs font-black uppercase hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                        {isUploading ? 'Uploading...' : 'Upload Policy'}
                    </Button>
                </div>
            </div>
        </div>
    );
};
