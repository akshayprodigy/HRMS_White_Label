import React, { useState, useEffect, useRef } from 'react';
import {
  User,
  Mail,
  Phone,
  MapPin,
  Briefcase,
  Shield,
  Key,
  Bell,
  Globe,
  Camera,
  CheckCircle2,
  Save,
  Award,
  Lock,
  UserCheck,
  Loader2,
  Eye,
  EyeOff,
  Target,
  LogOut,
  Clock,
  AlertTriangle,
  CheckCircle,
  XCircle,
  FileText,
  Star,
  Upload,
  Download,
  Trash2,
  Plus,
} from 'lucide-react';
import { Card, Button, Badge, cn } from './ui-elements';
import { Dialog, DialogContent, DialogTitle, DialogFooter } from './ui/dialog';
import { Input } from './ui/input';
import { toast } from 'sonner@2.0.3';
import { UserRole } from '../types/erp';
import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';

const errMsg = (err: any, fallback = 'Something went wrong'): string => {
  const detail = err?.response?.data?.detail;
  if (!detail) return err?.message || fallback;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) return detail.map((d: any) => d?.msg || JSON.stringify(d)).join('; ');
  return fallback;
};

interface ProfileProps {
  avatarUrl: string;
  userName?: string;
  userRole?: UserRole;
  onAvatarUpdated?: (url: string) => void;
}

export const ProfileView = ({ avatarUrl, userName = "Alex Thompson", userRole = "employee", onAvatarUpdated }: ProfileProps) => {
  const [activeSection, setActiveSection] = useState<'info' | 'security' | 'preferences' | 'kra' | 'documents' | 'assets' | 'resignation'>('info');
  const [isSaving, setIsSaving] = useState(false);
  const [isPwModalOpen, setIsPwModalOpen] = useState(false);
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [changingPw, setChangingPw] = useState(false);
  const [showCurrentPw, setShowCurrentPw] = useState(false);
  const [showNewPw, setShowNewPw] = useState(false);
  const [kra, setKra] = useState('');
  const [kraOriginal, setKraOriginal] = useState('');
  const [savingKra, setSavingKra] = useState(false);
  const [empProfile, setEmpProfile] = useState<any>(null);
  const [profileName, setProfileName] = useState('');
  const [profileEmail, setProfileEmail] = useState('');
  const [profilePhone, setProfilePhone] = useState('');
  const [profileLocation, setProfileLocation] = useState('');
  const [exitData, setExitData] = useState<any>(null);
  const [showResignModal, setShowResignModal] = useState(false);
  const [resignReason, setResignReason] = useState('');
  const [resignDetails, setResignDetails] = useState('');
  const [submittingResign, setSubmittingResign] = useState(false);
  const [showExitInterviewForm, setShowExitInterviewForm] = useState(false);
  const [avatarSrc, setAvatarSrc] = useState<string | null>(null);
  const [uploadingAvatar, setUploadingAvatar] = useState(false);
  const avatarInputRef = useRef<HTMLInputElement>(null);

  const isHR = userRole === 'hr';

  const fetchExitData = async () => {
    try {
      const res = await client.get(ENDPOINTS.EXIT.MY_RESIGNATION);
      setExitData(res.data);
    } catch { /* no resignation */ }
  };

  useEffect(() => {
    const fetchProfile = async () => {
      try {
        const res = await client.get(ENDPOINTS.HR.MY_PROFILE);
        setEmpProfile(res.data);
        setKra(res.data.kra || '');
        setKraOriginal(res.data.kra || '');
        setProfileName(res.data.user?.full_name || userName || '');
        setProfileEmail(res.data.user?.email || '');
        setProfilePhone(res.data.phone || res.data.user?.phone || '');
        setProfileLocation(res.data.location || res.data.user?.location || '');
      } catch {
        // No employee profile — fall back to /auth/me
        try {
          const meRes = await client.get(ENDPOINTS.AUTH.ME);
          setProfileName(meRes.data.full_name || userName || '');
          setProfileEmail(meRes.data.email || '');
        } catch {
          setProfileName(userName || '');
        }
      }
    };
    fetchProfile();
    fetchExitData();
    // Load avatar as blob so it works with auth headers
    client.get(ENDPOINTS.HR.MY_AVATAR, { responseType: 'blob' })
      .then(res => setAvatarSrc(URL.createObjectURL(res.data)))
      .catch(() => { /* no avatar yet */ });
  }, []);

  const handleSaveKra = async () => {
    setSavingKra(true);
    try {
      await client.patch(ENDPOINTS.HR.MY_KRA, { kra });
      setKraOriginal(kra);
      toast.success('KRA updated successfully');
    } catch {
      toast.error('Failed to save KRA');
    } finally {
      setSavingKra(false);
    }
  };

  const handleAvatarChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploadingAvatar(true);
    try {
      const form = new FormData();
      form.append('file', file);
      await client.post(ENDPOINTS.HR.MY_AVATAR, form);
      // Revoke old blob and create new one
      if (avatarSrc) URL.revokeObjectURL(avatarSrc);
      const newUrl = URL.createObjectURL(file);
      setAvatarSrc(newUrl);
      // Notify parent so the header avatar updates instantly
      onAvatarUpdated?.(newUrl);
      toast.success('Profile photo updated');
    } catch {
      toast.error('Failed to upload photo');
    } finally {
      setUploadingAvatar(false);
      if (avatarInputRef.current) avatarInputRef.current.value = '';
    }
  };

  const handleChangePassword = async () => {
    if (!currentPassword) { toast.error('Enter your current password'); return; }
    if (newPassword.length < 6) { toast.error('New password must be at least 6 characters'); return; }
    if (newPassword !== confirmPassword) { toast.error('Passwords do not match'); return; }
    setChangingPw(true);
    try {
      await client.post(ENDPOINTS.AUTH.CHANGE_PASSWORD, { current_password: currentPassword, new_password: newPassword });
      toast.success('Password changed successfully');
      setIsPwModalOpen(false);
      setCurrentPassword(''); setNewPassword(''); setConfirmPassword('');
    } catch (e: any) {
      toast.error(errMsg(e, 'Failed to change password'));
    } finally {
      setChangingPw(false);
    }
  };

  const handleSave = async () => {
    setIsSaving(true);
    try {
      await client.patch(ENDPOINTS.HR.MY_PROFILE_UPDATE, {
        full_name: profileName || undefined,
        phone: profilePhone || undefined,
        location: profileLocation || undefined,
      });
      toast.success("Profile Updated", { description: "Your changes have been saved." });
    } catch (e: any) {
      toast.error(errMsg(e, 'Failed to update profile'));
    } finally {
      setIsSaving(false);
    }
  };

  const handleSubmitResignation = async () => {
    if (!resignReason) { toast.error('Please select a reason'); return; }
    setSubmittingResign(true);
    try {
      await client.post(ENDPOINTS.EXIT.RESIGN, { reason: resignReason, reason_details: resignDetails || null });
      toast.success('Resignation submitted successfully');
      setShowResignModal(false);
      setResignReason(''); setResignDetails('');
      fetchExitData();
    } catch (e: any) {
      toast.error(errMsg(e, 'Failed to submit resignation'));
    } finally {
      setSubmittingResign(false);
    }
  };

  const handleWithdrawResignation = async () => {
    try {
      await client.post(ENDPOINTS.EXIT.WITHDRAW);
      toast.success('Resignation withdrawn');
      setExitData(null);
    } catch (e: any) {
      toast.error(errMsg(e, 'Failed to withdraw'));
    }
  };

  const getRoleDisplay = () => {
    if (isHR) return "Strategic HR Director";
    if (userRole === 'admin') return "System Architect & Admin";
    if (userRole === 'pm') return "Senior Project Manager";
    return "Senior Backend Engineer";
  };

  const getDepartment = () => {
    if (isHR) return "Human Resources & People Ops";
    if (userRole === 'pm') return "Project Management Office";
    return "Product Engineering";
  };

  return (
    <div className="p-8 space-y-8 max-w-[1200px] mx-auto animate-in fade-in duration-500">
      <div className="flex flex-col md:flex-row items-start md:items-end justify-between gap-6 pb-6 border-b border-slate-100">
        <div className="flex flex-col md:flex-row items-center gap-8">
          <div className="relative group">
            <button
              type="button"
              onClick={() => avatarInputRef.current?.click()}
              disabled={uploadingAvatar}
              aria-label="Change profile photo"
              className="block w-40 h-40 rounded-3xl overflow-hidden border-4 border-white shadow-2xl ring-1 ring-slate-100 focus-visible:ring-2 focus-visible:ring-[#2563EB] focus-visible:ring-offset-2 focus-visible:outline-none disabled:cursor-wait"
            >
              <img src={avatarSrc || avatarUrl} alt="Profile" className="w-full h-full object-cover" />
              {/* Hover dim overlay so the camera icon stays legible over bright photos */}
              <span className="absolute inset-0 bg-slate-900/0 group-hover:bg-slate-900/30 transition-colors pointer-events-none" />
            </button>
            <input
              ref={avatarInputRef}
              type="file"
              accept="image/jpeg,image/png,image/webp,image/gif"
              className="hidden"
              onChange={handleAvatarChange}
            />
            <button
              type="button"
              onClick={() => avatarInputRef.current?.click()}
              disabled={uploadingAvatar}
              aria-label="Change profile photo"
              className="absolute bottom-2 right-2 p-3 bg-[#2563EB] text-white rounded-2xl shadow-xl transition-all hover:scale-110 hover:bg-blue-700 active:scale-95 disabled:opacity-60 focus-visible:ring-2 focus-visible:ring-[#2563EB] focus-visible:ring-offset-2 focus-visible:outline-none"
            >
              {uploadingAvatar ? <Loader2 size={20} className="animate-spin" aria-hidden="true" /> : <Camera size={20} aria-hidden="true" />}
            </button>
            <p className="mt-2 text-center text-[10px] font-black text-slate-400 uppercase tracking-widest">
              {uploadingAvatar ? 'Uploading…' : 'Tap photo to change'}
            </p>
          </div>
          <div className="text-center md:text-left">
            <div className="flex items-center justify-center md:justify-start gap-2 mb-1">
              <h2 className="text-4xl font-black text-[#0F172A] tracking-tighter">{profileName || userName}</h2>
              {isHR && <CheckCircle2 className="text-[#2563EB] w-6 h-6 fill-blue-50" />}
            </div>
            <div className="flex flex-wrap justify-center md:justify-start gap-3 items-center">
              <Badge variant={isHR ? "success" : "info"} className="font-black text-[10px] uppercase tracking-widest px-4 py-1.5">
                {empProfile?.designation || getRoleDisplay()}
              </Badge>
              <span className="text-xs font-black text-slate-400 uppercase tracking-widest">
                ID: {empProfile?.employee_id || '—'}
              </span>
            </div>
          </div>
        </div>
        <Button 
          className="font-black h-14 px-10 uppercase text-[10px] tracking-[0.2em] shadow-xl shadow-blue-600/10"
          onClick={handleSave}
          isLoading={isSaving}
        >
          <Save className="w-4 h-4 mr-2" /> Save Global Changes
        </Button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-8">
        <Card className="lg:col-span-1 p-4 bg-slate-50 border-slate-200 h-fit space-y-2">
          {[
            { id: 'info', label: 'Identity Information', icon: <User size={18} /> },
            { id: 'kra', label: 'Key Result Areas', icon: <Target size={18} /> },
            { id: 'documents', label: 'My Documents', icon: <FileText size={18} /> },
            { id: 'assets', label: 'My Assets', icon: <Briefcase size={18} /> },
            { id: 'security', label: 'Security & Access', icon: <Shield size={18} /> },
            { id: 'preferences', label: 'System Preferences', icon: <Globe size={18} /> },
            { id: 'resignation', label: 'Resignation / Exit', icon: <LogOut size={18} /> },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveSection(tab.id as any)}
              className={cn(
                "w-full flex items-center gap-4 px-6 py-4 rounded-2xl text-[10px] font-black uppercase tracking-widest transition-all",
                activeSection === tab.id 
                  ? "bg-white text-[#2563EB] shadow-lg shadow-blue-600/5 border border-blue-100" 
                  : "text-slate-400 hover:bg-white hover:text-[#0F172A]"
              )}
            >
              {tab.icon}
              {tab.label}
            </button>
          ))}
          
          {isHR && (
             <div className="mt-8 p-6 bg-[#2563EB] rounded-2xl text-white space-y-4 shadow-lg shadow-blue-600/20">
                <div className="flex items-center gap-3">
                   <div className="p-2 bg-white/20 rounded-lg">
                      <Lock size={18} />
                   </div>
                   <p className="text-[10px] font-black uppercase tracking-widest">HR Admin Access</p>
                </div>
                <p className="text-[9px] leading-relaxed font-bold opacity-80 uppercase tracking-wider">
                  You have full organizational oversight. Changes here affect enterprise audit logs.
                </p>
             </div>
          )}
        </Card>

        <Card className="lg:col-span-3 p-10 bg-white border-slate-200">
           {activeSection === 'info' && (
             <div className="space-y-10">
                <section>
                   <div className="flex items-center justify-between mb-6">
                      <h3 className="text-[10px] font-black text-[#94A3B8] uppercase tracking-[0.2em]">Personal Artifacts</h3>
                      {isHR && <Badge variant="info" className="text-[8px] font-black">HR VERIFIED PROFILE</Badge>}
                   </div>
                   <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                      <div className="space-y-2">
                         <label className="text-[10px] font-black text-slate-600 uppercase tracking-widest">Full Name</label>
                         <input type="text" value={profileName} onChange={(e) => setProfileName(e.target.value)} className="w-full h-12 bg-slate-50 border border-slate-200 rounded-xl px-4 text-sm font-bold focus:ring-2 focus:ring-blue-600/10 outline-none" />
                      </div>
                      <div className="space-y-2">
                         <label className="text-[10px] font-black text-slate-600 uppercase tracking-widest">Corporate Email</label>
                         <input type="email" value={profileEmail} disabled className="w-full h-12 bg-slate-100 border border-slate-200 rounded-xl px-4 text-sm font-bold text-slate-500 cursor-not-allowed outline-none" />
                      </div>
                      <div className="space-y-2">
                         <label className="text-[10px] font-black text-slate-600 uppercase tracking-widest">Contact Number</label>
                         <input type="text" value={profilePhone} onChange={(e) => setProfilePhone(e.target.value)} placeholder="+91 98765 43210" className="w-full h-12 bg-slate-50 border border-slate-200 rounded-xl px-4 text-sm font-bold focus:ring-2 focus:ring-blue-600/10 outline-none" />
                      </div>
                      <div className="space-y-2">
                         <label className="text-[10px] font-black text-slate-600 uppercase tracking-widest">Location</label>
                         <input type="text" value={profileLocation} onChange={(e) => setProfileLocation(e.target.value)} placeholder="e.g. Kolkata HQ" className="w-full h-12 bg-slate-50 border border-slate-200 rounded-xl px-4 text-sm font-bold focus:ring-2 focus:ring-blue-600/10 outline-none" />
                      </div>
                   </div>
                </section>

                <section>
                   <div className="flex items-center justify-between mb-6">
                      <h3 className="text-[10px] font-black text-[#94A3B8] uppercase tracking-[0.2em]">Employment Details</h3>
                      <span className="inline-flex items-center gap-1.5 text-[9px] font-black text-slate-400 uppercase tracking-widest">
                        <Lock size={10} aria-hidden="true" /> HR-managed
                      </span>
                   </div>
                   <p className="text-xs text-slate-400 font-medium mb-4">
                     These fields are set and updated by HR. To request a change, please contact your HR partner.
                   </p>
                   <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                      <div className="p-5 bg-slate-50 rounded-2xl border border-slate-100">
                         <p className="text-[10px] font-black text-slate-400 uppercase mb-1">Employee ID</p>
                         <p className="text-sm font-black text-[#0F172A] tabular-nums">{empProfile?.employee_id || '—'}</p>
                      </div>
                      <div className="p-5 bg-slate-50 rounded-2xl border border-slate-100">
                         <p className="text-[10px] font-black text-slate-400 uppercase mb-1">Joined</p>
                         <p className="text-sm font-black text-[#0F172A] tabular-nums">{empProfile?.date_of_joining ? new Date(empProfile.date_of_joining).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' }) : '—'}</p>
                      </div>
                      <div className="p-5 bg-slate-50 rounded-2xl border border-slate-100">
                         <p className="text-[10px] font-black text-slate-400 uppercase mb-1">Status</p>
                         <p className={cn("text-sm font-black uppercase", empProfile?.status === 'active' ? 'text-green-600' : 'text-amber-600')}>{empProfile?.status || '—'}</p>
                      </div>
                      <div className="p-5 bg-slate-50 rounded-2xl border border-slate-100">
                         <p className="text-[10px] font-black text-slate-400 uppercase mb-1">Employment Type</p>
                         <p className="text-sm font-black text-[#0F172A] capitalize">{empProfile?.employment_type || 'permanent'}</p>
                      </div>
                      <div className="p-5 bg-slate-50 rounded-2xl border border-slate-100">
                         <p className="text-[10px] font-black text-slate-400 uppercase mb-1">Department</p>
                         <p className="text-sm font-black text-[#2563EB]">{empProfile?.department || '—'}</p>
                      </div>
                      <div className="p-5 bg-slate-50 rounded-2xl border border-slate-100">
                         <p className="text-[10px] font-black text-slate-400 uppercase mb-1">Designation</p>
                         <p className="text-sm font-black text-[#0F172A]">{empProfile?.designation || '—'}</p>
                      </div>
                      <div className="p-5 bg-slate-50 rounded-2xl border border-slate-100">
                         <p className="text-[10px] font-black text-slate-400 uppercase mb-1">Reporting Manager</p>
                         <p className="text-sm font-black text-[#0F172A]">{empProfile?.user?.manager?.full_name || '—'}</p>
                      </div>
                      <div className="p-5 bg-slate-50 rounded-2xl border border-slate-100">
                         <p className="text-[10px] font-black text-slate-400 uppercase mb-1">Notice Period</p>
                         <p className="text-sm font-black text-[#0F172A] tabular-nums">{empProfile?.notice_period_days ?? 30} days</p>
                      </div>
                   </div>
                </section>

                {isHR && (
                   <section className="p-8 bg-blue-50/50 rounded-3xl border border-blue-100">
                      <h3 className="text-[10px] font-black text-[#2563EB] uppercase tracking-[0.2em] mb-6 flex items-center gap-2">
                        <Award size={14} /> HR Qualifications & Certs
                      </h3>
                      <div className="flex flex-wrap gap-4">
                         {['SHRM-SCP Senior Certified', 'HR-CIP Professional', 'Employee Relations Expert'].map((cert, i) => (
                           <div key={i} className="flex items-center gap-2 bg-white px-4 py-2 rounded-xl shadow-sm border border-blue-100">
                              <UserCheck size={14} className="text-blue-600" />
                              <span className="text-[10px] font-black text-[#0F172A] uppercase tracking-wider">{cert}</span>
                           </div>
                         ))}
                      </div>
                   </section>
                )}
             </div>
           )}

           {activeSection === 'kra' && (
             <div className="space-y-8">
                <section>
                   <div className="flex items-center justify-between mb-6">
                      <div>
                         <h3 className="text-[10px] font-black text-[#94A3B8] uppercase tracking-[0.2em]">Key Result Areas (KRA)</h3>
                         <p className="text-xs text-slate-400 mt-1">Define your key responsibilities, goals, and measurable outcomes</p>
                      </div>
                      <Button
                         onClick={handleSaveKra}
                         disabled={savingKra || kra === kraOriginal}
                         className="font-black h-10 px-6 uppercase text-[9px] tracking-[0.15em]"
                         isLoading={savingKra}
                      >
                         <Save className="w-3.5 h-3.5 mr-2" /> Save KRA
                      </Button>
                   </div>
                   <textarea
                      value={kra}
                      onChange={(e) => setKra(e.target.value)}
                      placeholder="Describe your Key Result Areas...&#10;&#10;Example:&#10;- Deliver assigned project milestones on time with zero critical defects&#10;- Maintain 85%+ timesheet utilization across billable projects&#10;- Complete mandatory compliance and skill training each quarter&#10;- Collaborate with cross-functional teams to achieve client satisfaction targets"
                      className="w-full min-h-[300px] bg-slate-50 border border-slate-200 rounded-2xl p-6 text-sm font-medium text-slate-700 leading-relaxed focus:ring-2 focus:ring-blue-600/10 focus:border-blue-300 outline-none resize-y"
                   />
                   {kra !== kraOriginal && (
                      <p className="text-xs text-amber-600 font-bold mt-2">You have unsaved changes</p>
                   )}
                </section>

                {empProfile && (
                   <section className="p-6 bg-slate-50 rounded-2xl border border-slate-100">
                      <h3 className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-4">Profile Summary</h3>
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                         <div>
                            <p className="text-[9px] font-black text-slate-400 uppercase">Employee ID</p>
                            <p className="text-sm font-bold text-[#0F172A]">{empProfile.employee_id}</p>
                         </div>
                         <div>
                            <p className="text-[9px] font-black text-slate-400 uppercase">Department</p>
                            <p className="text-sm font-bold text-[#0F172A]">{empProfile.department}</p>
                         </div>
                         <div>
                            <p className="text-[9px] font-black text-slate-400 uppercase">Designation</p>
                            <p className="text-sm font-bold text-[#0F172A]">{empProfile.designation}</p>
                         </div>
                         <div>
                            <p className="text-[9px] font-black text-slate-400 uppercase">Date of Joining</p>
                            <p className="text-sm font-bold text-[#0F172A]">{new Date(empProfile.date_of_joining).toLocaleDateString()}</p>
                         </div>
                      </div>
                   </section>
                )}
             </div>
           )}

           {activeSection === 'documents' && <MyDocumentsSection />}

           {activeSection === 'assets' && <MyAssetsSection />}

           {activeSection === 'security' && (
             <div className="space-y-10">
                <section className="space-y-6">
                   <h3 className="text-[10px] font-black text-[#94A3B8] uppercase tracking-[0.2em]">Credential Management</h3>
                   <div className="space-y-4">
                      <Button variant="outline" className="h-12 w-full justify-between font-black text-[10px] uppercase tracking-widest px-6" onClick={() => setIsPwModalOpen(true)}>
                         <span>Change Password</span>
                         <Key size={14} className="text-[#2563EB]" />
                      </Button>
                      <Button variant="outline" className="h-12 w-full justify-between font-black text-[10px] uppercase tracking-widest px-6" onClick={() => toast.success("MFA synchronization active.")}>
                         <span>Multi-Factor Authentication (MFA)</span>
                         <Badge variant="success" className="text-[8px] font-black">ACTIVE</Badge>
                      </Button>
                   </div>
                </section>

                {isHR && (
                   <section className="space-y-6">
                      <h3 className="text-[10px] font-black text-[#94A3B8] uppercase tracking-[0.2em]">Privileged Audit Log</h3>
                      <div className="bg-slate-50 p-6 rounded-3xl border border-slate-100">
                         <div className="flex items-center justify-between">
                            <div className="flex items-center gap-4">
                               <Shield size={20} className="text-[#2563EB]" />
                               <div>
                                  <p className="text-sm font-black text-[#0F172A]">Management View Activity</p>
                                  <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Monitored for enterprise security compliance</p>
                               </div>
                            </div>
                            <Button variant="outline" size="sm" className="text-[8px] font-black h-8 px-4 uppercase">VIEW LOGS</Button>
                         </div>
                      </div>
                   </section>
                )}
             </div>
           )}

           {activeSection === 'preferences' && (
             <div className="space-y-10">
                <section className="space-y-8">
                   <h3 className="text-[10px] font-black text-[#94A3B8] uppercase tracking-[0.2em]">System Interface</h3>
                   <div className="space-y-6">
                      <div className="flex items-center justify-between">
                         <div>
                            <p className="text-sm font-black text-[#0F172A]">Push Notifications</p>
                            <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Deliver alerts to OS level</p>
                         </div>
                         <div className="w-12 h-6 bg-[#2563EB] rounded-full relative cursor-pointer">
                            <div className="absolute right-1 top-1 w-4 h-4 bg-white rounded-full" />
                         </div>
                      </div>
                      <div className="flex items-center justify-between">
                         <div>
                            <p className="text-sm font-black text-[#0F172A]">HR Intelligence Alerts</p>
                            <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Receive high-priority recruitment & leave alerts</p>
                         </div>
                         <div className="w-12 h-6 bg-[#2563EB] rounded-full relative cursor-pointer">
                            <div className="absolute right-1 top-1 w-4 h-4 bg-white rounded-full" />
                         </div>
                      </div>
                   </div>
                </section>
             </div>
           )}

           {activeSection === 'resignation' && (
             <ResignationSection
               exitData={exitData}
               empProfile={empProfile}
               onSubmitResignation={() => setShowResignModal(true)}
               onWithdraw={handleWithdrawResignation}
               onExitInterviewOpen={() => setShowExitInterviewForm(true)}
               fetchExitData={fetchExitData}
             />
           )}
        </Card>
      </div>
      <Dialog open={isPwModalOpen} onOpenChange={(open: boolean) => { setIsPwModalOpen(open); if (!open) { setCurrentPassword(''); setNewPassword(''); setConfirmPassword(''); } }}>
        <DialogContent className="max-w-md p-0 overflow-hidden rounded-3xl border-none">
          <div className="bg-[#2563EB] p-8 text-white">
            <DialogTitle className="text-2xl font-bold">Change Password</DialogTitle>
            <p className="text-blue-100 text-sm mt-1">Enter your current password and choose a new one</p>
          </div>
          <div className="p-8 space-y-4">
            <div className="space-y-2">
              <label className="text-sm font-semibold text-slate-700">Current Password</label>
              <div className="relative">
                <Input
                  type={showCurrentPw ? 'text' : 'password'}
                  placeholder="Enter current password"
                  value={currentPassword}
                  onChange={(e) => setCurrentPassword(e.target.value)}
                  className="h-11 rounded-xl bg-slate-50 pr-10"
                />
                <button type="button" onClick={() => setShowCurrentPw(!showCurrentPw)} className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600">
                  {showCurrentPw ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </div>
            <div className="space-y-2">
              <label className="text-sm font-semibold text-slate-700">New Password</label>
              <div className="relative">
                <Input
                  type={showNewPw ? 'text' : 'password'}
                  placeholder="Enter new password (min 6 characters)"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  className="h-11 rounded-xl bg-slate-50 pr-10"
                />
                <button type="button" onClick={() => setShowNewPw(!showNewPw)} className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600">
                  {showNewPw ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </div>
            <div className="space-y-2">
              <label className="text-sm font-semibold text-slate-700">Confirm New Password</label>
              <Input
                type="password"
                placeholder="Re-enter new password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                className="h-11 rounded-xl bg-slate-50"
              />
              {confirmPassword && newPassword !== confirmPassword && (
                <p className="text-xs text-red-500">Passwords do not match</p>
              )}
            </div>
          </div>
          <DialogFooter className="p-8 pt-0">
            <Button
              onClick={handleChangePassword}
              disabled={changingPw || newPassword.length < 6 || newPassword !== confirmPassword || !currentPassword}
              className="bg-[#2563EB] hover:bg-blue-700 text-white rounded-xl w-full h-11"
            >
              {changingPw ? <><Loader2 className="w-4 h-4 animate-spin mr-2" /> Changing...</> : 'Change Password'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Resignation Modal */}
      {showResignModal && (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4" onClick={() => setShowResignModal(false)}>
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg animate-in zoom-in-95 duration-200" onClick={e => e.stopPropagation()}>
            <div className="p-6 border-b border-slate-100 bg-red-50">
              <div className="flex items-center gap-3">
                <div className="p-2.5 bg-red-100 rounded-xl"><LogOut size={20} className="text-red-600" /></div>
                <div>
                  <h3 className="text-lg font-black text-[#0F172A] uppercase tracking-tight">Submit Resignation</h3>
                  <p className="text-[10px] text-slate-500 font-bold uppercase tracking-widest">
                    Notice period: {empProfile?.notice_period_days ?? 30} days
                  </p>
                </div>
              </div>
            </div>
            <div className="p-6 space-y-5">
              <div>
                <label className="text-[10px] font-black text-slate-500 uppercase tracking-widest mb-2 block">Reason for Leaving *</label>
                <select value={resignReason} onChange={e => setResignReason(e.target.value)} className="w-full h-11 bg-slate-50 border border-slate-200 rounded-xl px-4 text-sm font-bold outline-none">
                  <option value="">Select reason...</option>
                  <option value="better_opportunity">Better Career Opportunity</option>
                  <option value="higher_studies">Higher Studies</option>
                  <option value="personal">Personal Reasons</option>
                  <option value="relocation">Relocation</option>
                  <option value="health">Health Reasons</option>
                  <option value="work_environment">Work Environment</option>
                  <option value="compensation">Compensation & Benefits</option>
                  <option value="relationship">Relationship with Manager/Team</option>
                  <option value="role_mismatch">Role Mismatch</option>
                  <option value="other">Other</option>
                </select>
              </div>
              <div>
                <label className="text-[10px] font-black text-slate-500 uppercase tracking-widest mb-2 block">Additional Details</label>
                <textarea value={resignDetails} onChange={e => setResignDetails(e.target.value)} placeholder="Brief explanation (optional)..." rows={3} className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-sm font-medium outline-none resize-none" />
              </div>
              <div className="p-4 bg-amber-50 border border-amber-100 rounded-xl">
                <p className="text-[10px] font-black text-amber-800 uppercase tracking-widest mb-1">Important</p>
                <p className="text-xs text-amber-700">Your last working day will be calculated as {empProfile?.notice_period_days ?? 30} days from today. You can withdraw your resignation before HR accepts it.</p>
              </div>
            </div>
            <div className="p-6 border-t border-slate-100 flex gap-3">
              <Button onClick={() => setShowResignModal(false)} className="flex-1 h-11 bg-slate-100 text-slate-700 rounded-xl text-xs font-black uppercase hover:bg-slate-200">Cancel</Button>
              <Button onClick={handleSubmitResignation} disabled={submittingResign || !resignReason} className="flex-1 h-11 bg-red-600 text-white rounded-xl text-xs font-black uppercase hover:bg-red-700 disabled:opacity-50">
                {submittingResign ? 'Submitting...' : 'Submit Resignation'}
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Exit Interview Form Modal */}
      {showExitInterviewForm && exitData?.resignation && (
        <ExitInterviewFormModal
          resignationId={exitData.resignation.id}
          onClose={() => setShowExitInterviewForm(false)}
          onSuccess={() => { setShowExitInterviewForm(false); fetchExitData(); }}
        />
      )}
    </div>
  );
};


// ─── Resignation Section Component ──────────────────────────

const RESIGNATION_REASONS: Record<string, string> = {
  better_opportunity: 'Better Career Opportunity',
  higher_studies: 'Higher Studies',
  personal: 'Personal Reasons',
  relocation: 'Relocation',
  health: 'Health Reasons',
  work_environment: 'Work Environment',
  compensation: 'Compensation & Benefits',
  relationship: 'Relationship with Manager/Team',
  role_mismatch: 'Role Mismatch',
  other: 'Other',
};

const STATUS_CONFIG: Record<string, { color: string; bg: string; icon: any; label: string }> = {
  submitted: { color: 'text-amber-700', bg: 'bg-amber-50 border-amber-200', icon: Clock, label: 'Pending Review' },
  accepted: { color: 'text-blue-700', bg: 'bg-blue-50 border-blue-200', icon: CheckCircle, label: 'Accepted' },
  notice_period: { color: 'text-orange-700', bg: 'bg-orange-50 border-orange-200', icon: Clock, label: 'Serving Notice' },
  exit_interview: { color: 'text-purple-700', bg: 'bg-purple-50 border-purple-200', icon: FileText, label: 'Exit Interview Required' },
  clearance: { color: 'text-cyan-700', bg: 'bg-cyan-50 border-cyan-200', icon: Shield, label: 'Clearance In Progress' },
  released: { color: 'text-green-700', bg: 'bg-green-50 border-green-200', icon: CheckCircle, label: 'Released' },
  withdrawn: { color: 'text-slate-500', bg: 'bg-slate-50 border-slate-200', icon: XCircle, label: 'Withdrawn' },
  rejected: { color: 'text-red-700', bg: 'bg-red-50 border-red-200', icon: XCircle, label: 'Rejected' },
};

const DOC_TYPES = ['Legal', 'KYC', 'Education', 'Experience', 'Finance', 'Other'] as const;

const MyDocumentsSection = () => {
  const [docs, setDocs] = useState<any[]>([]);
  const [requiredStatus, setRequiredStatus] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [docType, setDocType] = useState<string>('KYC');
  const [remark, setRemark] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const refresh = async () => {
    setLoading(true);
    try {
      const [docsRes, statusRes] = await Promise.allSettled([
        client.get(ENDPOINTS.HR.MY_DOCUMENTS),
        client.get(ENDPOINTS.HR.MY_REQUIRED_STATUS),
      ]);
      if (docsRes.status === 'fulfilled') {
        setDocs(docsRes.value.data || []);
      } else {
        const e: any = docsRes.reason;
        if (e?.response?.status !== 404) {
          toast.error(errMsg(e, 'Failed to load documents'));
        }
        setDocs([]);
      }
      if (statusRes.status === 'fulfilled') setRequiredStatus(statusRes.value.data);
      else setRequiredStatus(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { refresh(); }, []);

  const handleUpload = async () => {
    if (!file) { toast.error('Pick a file first'); return; }
    setUploading(true);
    try {
      const form = new FormData();
      form.append('file', file);
      const url = `${ENDPOINTS.HR.MY_DOCUMENT_UPLOAD}?doc_type=${encodeURIComponent(docType)}${remark ? `&remark=${encodeURIComponent(remark)}` : ''}`;
      await client.post(url, form);
      toast.success('Document uploaded');
      setShowForm(false);
      setFile(null);
      setRemark('');
      setDocType('KYC');
      refresh();
    } catch (e: any) {
      toast.error(errMsg(e, 'Upload failed'));
    } finally {
      setUploading(false);
    }
  };

  const handleDownload = async (doc: any) => {
    try {
      const res = await client.get(ENDPOINTS.HR.MY_DOCUMENT_DOWNLOAD(doc.id), { responseType: 'blob' });
      const blobUrl = window.URL.createObjectURL(res.data as Blob);
      const a = document.createElement('a');
      a.href = blobUrl;
      a.download = doc.original_filename || 'document';
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => window.URL.revokeObjectURL(blobUrl), 60000);
    } catch (e: any) {
      toast.error(errMsg(e, 'Failed to download'));
    }
  };

  const handleDelete = async (doc: any) => {
    if (!confirm(`Delete "${doc.original_filename}"?`)) return;
    try {
      await client.delete(ENDPOINTS.HR.MY_DOCUMENT_DELETE(doc.id));
      toast.success('Document deleted');
      refresh();
    } catch (e: any) {
      toast.error(errMsg(e, 'Failed to delete'));
    }
  };

  const totalRequired = requiredStatus?.total_required || 0;
  const verifiedSatisfied = requiredStatus?.verified_satisfied || 0;
  const uploadedSatisfied = requiredStatus?.satisfied || 0;
  const allVerified = totalRequired > 0 && verifiedSatisfied === totalRequired;
  const allUploaded = totalRequired > 0 && uploadedSatisfied === totalRequired;

  return (
    <div className="space-y-8">
      {totalRequired > 0 && (
        <section className={cn(
          'p-6 rounded-3xl border',
          allVerified ? 'border-emerald-200 bg-emerald-50/40'
            : allUploaded ? 'border-amber-200 bg-amber-50/40'
            : 'border-red-200 bg-red-50/40',
        )}>
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="flex items-center gap-4">
              <div className={cn(
                'w-12 h-12 rounded-2xl flex items-center justify-center border',
                allVerified ? 'bg-emerald-100 text-emerald-700 border-emerald-200'
                  : allUploaded ? 'bg-amber-100 text-amber-700 border-amber-200'
                  : 'bg-red-100 text-red-700 border-red-200',
              )}>
                {allVerified ? <CheckCircle2 size={20} /> : <AlertTriangle size={20} />}
              </div>
              <div>
                <p className="text-[10px] font-black uppercase tracking-widest text-slate-500">Required documents</p>
                <p className="text-sm font-black text-[#0F172A] mt-1">
                  {uploadedSatisfied} of {totalRequired} uploaded
                  {' • '}
                  <span className="text-slate-500 font-bold">{verifiedSatisfied} verified by HR</span>
                </p>
                {!allUploaded && (
                  <p className="text-[11px] font-medium text-red-700 mt-1">
                    Please upload the missing documents below.
                  </p>
                )}
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              {(requiredStatus?.required_types || []).map((t: any) => (
                <span
                  key={t.doc_type}
                  className={cn(
                    'text-[9px] font-black uppercase tracking-widest px-3 py-1 rounded-full border',
                    t.is_verified ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                      : t.is_uploaded ? 'bg-amber-50 text-amber-700 border-amber-200'
                      : 'bg-slate-50 text-slate-500 border-slate-200',
                  )}
                  title={t.description || ''}
                >
                  {t.doc_type} · {t.is_verified ? 'verified' : t.is_uploaded ? 'pending' : 'missing'}
                </span>
              ))}
            </div>
          </div>
        </section>
      )}

      <section>
        <div className="flex items-center justify-between mb-2">
          <div>
            <h3 className="text-[10px] font-black text-[#94A3B8] uppercase tracking-[0.2em]">My Documents</h3>
            <p className="text-xs text-slate-400 mt-1">Upload your KYC, education certificates, and other personal records. HR can view documents you upload here.</p>
          </div>
          <Button onClick={() => setShowForm(s => !s)} className="font-black h-10 px-6 uppercase text-[9px] tracking-[0.15em]">
            <Plus className="w-3.5 h-3.5 mr-2" /> Upload Document
          </Button>
        </div>

        {showForm && (
          <Card className="mt-4 p-6 border-blue-100 bg-blue-50/30 animate-in slide-in-from-top-2 duration-200">
            <h4 className="text-[10px] font-black text-blue-600 uppercase tracking-[0.2em] mb-4">New Document</h4>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="space-y-2">
                <label className="text-[9px] font-black text-slate-500 uppercase tracking-widest">Type</label>
                <select
                  value={docType}
                  onChange={e => setDocType(e.target.value)}
                  className="w-full h-11 px-3 rounded-xl border border-slate-200 bg-white text-sm font-bold text-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-500/30"
                  aria-label="Document type"
                >
                  {DOC_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
                </select>
              </div>
              <div className="space-y-2">
                <label className="text-[9px] font-black text-slate-500 uppercase tracking-widest">Remarks (optional)</label>
                <Input value={remark} onChange={e => setRemark(e.target.value)} placeholder="e.g. Aadhaar front + back" className="h-11 font-bold" />
              </div>
              <div className="space-y-2">
                <label className="text-[9px] font-black text-slate-500 uppercase tracking-widest">File</label>
                <button
                  type="button"
                  onClick={() => fileRef.current?.click()}
                  className="w-full h-11 flex items-center gap-3 px-4 rounded-xl border border-dashed border-slate-300 bg-white hover:border-blue-400 transition-colors text-left"
                >
                  <Upload size={14} className="text-slate-400 shrink-0" aria-hidden="true" />
                  {file ? (
                    <span className="text-xs font-black text-blue-600 truncate">{file.name}</span>
                  ) : (
                    <span className="text-xs font-bold text-slate-400">Click to select…</span>
                  )}
                </button>
                <input
                  ref={fileRef}
                  type="file"
                  className="hidden"
                  accept="application/pdf,image/jpeg,image/png,image/webp,image/heic,image/gif,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/vnd.ms-excel,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,text/plain"
                  onChange={e => setFile(e.target.files?.[0] || null)}
                />
              </div>
            </div>
            <p className="mt-3 text-[10px] text-slate-400 font-bold">PDF · JPG · PNG · Word · Excel · 25 MB max</p>
            <div className="mt-4 flex justify-end gap-3">
              <Button variant="outline" onClick={() => { setShowForm(false); setFile(null); }} className="h-10 px-6 font-black uppercase text-[9px] tracking-widest">
                Cancel
              </Button>
              <Button onClick={handleUpload} disabled={uploading || !file} isLoading={uploading} className="h-10 px-8 font-black uppercase text-[9px] tracking-widest">
                Upload
              </Button>
            </div>
          </Card>
        )}
      </section>

      <section>
        {loading ? (
          <div className="p-12 flex justify-center"><Loader2 className="w-6 h-6 text-blue-600 animate-spin" aria-hidden="true" /></div>
        ) : docs.length === 0 ? (
          <div className="p-12 bg-slate-50 rounded-3xl border border-dashed border-slate-200 text-center">
            <FileText size={36} className="mx-auto text-slate-300 mb-3" aria-hidden="true" />
            <p className="text-sm font-black text-slate-500 uppercase tracking-widest">No documents yet</p>
            <p className="text-xs text-slate-400 mt-1 font-medium">Upload your KYC and personal records — HR will see them on their side.</p>
          </div>
        ) : (
          <div className="overflow-hidden rounded-2xl border border-slate-200">
            <table className="w-full text-left">
              <thead>
                <tr className="bg-slate-50 border-b border-slate-200">
                  <th className="px-5 py-3 text-[9px] font-black text-slate-500 uppercase tracking-widest">Filename</th>
                  <th className="px-5 py-3 text-[9px] font-black text-slate-500 uppercase tracking-widest">Type</th>
                  <th className="px-5 py-3 text-[9px] font-black text-slate-500 uppercase tracking-widest">HR Status</th>
                  <th className="px-5 py-3 text-[9px] font-black text-slate-500 uppercase tracking-widest">Uploaded By</th>
                  <th className="px-5 py-3 text-[9px] font-black text-slate-500 uppercase tracking-widest">Uploaded On</th>
                  <th className="px-5 py-3 text-[9px] font-black text-slate-500 uppercase tracking-widest">Remarks</th>
                  <th className="px-5 py-3 text-[9px] font-black text-slate-500 uppercase tracking-widest text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {docs.map((d: any) => {
                  const status = d.verification_status || (d.verified_at ? 'verified' : d.rejection_reason ? 'rejected' : 'pending');
                  return (
                  <tr key={d.id} className="hover:bg-slate-50/60 transition-colors">
                    <td className="px-5 py-4 text-sm font-black text-slate-800">{d.original_filename}</td>
                    <td className="px-5 py-4">
                      <span className="text-[9px] font-black text-slate-600 uppercase tracking-widest px-2 py-1 rounded bg-slate-100">{d.doc_type}</span>
                    </td>
                    <td className="px-5 py-4">
                      {status === 'verified' ? (
                        <span className="inline-flex items-center gap-1 text-[9px] font-black uppercase tracking-widest px-2 py-1 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200">
                          <CheckCircle2 size={10} /> Verified
                        </span>
                      ) : status === 'rejected' ? (
                        <div className="flex flex-col gap-1 max-w-[200px]">
                          <span className="inline-flex items-center gap-1 self-start text-[9px] font-black uppercase tracking-widest px-2 py-1 rounded-full bg-red-50 text-red-700 border border-red-200">
                            <XCircle size={10} /> Rejected
                          </span>
                          {d.rejection_reason && (
                            <span className="text-[10px] font-medium text-red-600 italic line-clamp-2" title={d.rejection_reason}>
                              {d.rejection_reason}
                            </span>
                          )}
                        </div>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-[9px] font-black uppercase tracking-widest px-2 py-1 rounded-full bg-amber-50 text-amber-700 border border-amber-200">
                          <Clock size={10} /> Pending
                        </span>
                      )}
                    </td>
                    <td className="px-5 py-4">
                      <div className="flex flex-col gap-1">
                        <span className="text-xs font-bold text-slate-700">{d.uploaded_by_name || '—'}</span>
                        {!d.is_self_uploaded && (
                          <span className="self-start text-[8px] font-black uppercase tracking-widest px-2 py-0.5 rounded-full bg-blue-50 text-blue-700 border border-blue-200">
                            Uploaded by HR
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-5 py-4 text-xs font-bold text-slate-500 tabular-nums">
                      {d.uploaded_at ? new Date(d.uploaded_at).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' }) : '—'}
                    </td>
                    <td className="px-5 py-4 text-xs font-medium text-slate-500 italic max-w-[220px] truncate" title={d.remark || ''}>
                      {d.remark || '—'}
                    </td>
                    <td className="px-5 py-4 text-right">
                      <div className="flex justify-end gap-2">
                        <Button
                          variant="outline"
                          size="sm"
                          className="h-8 w-8 p-0 rounded-lg"
                          onClick={() => handleDownload(d)}
                          aria-label={`Download ${d.original_filename}`}
                          title="Download"
                        >
                          <Download size={12} />
                        </Button>
                        {d.is_self_uploaded ? (
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-8 w-8 p-0 rounded-lg text-red-500 hover:bg-red-50"
                            onClick={() => handleDelete(d)}
                            aria-label={`Delete ${d.original_filename}`}
                            title="Delete"
                          >
                            <Trash2 size={12} />
                          </Button>
                        ) : (
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-8 w-8 p-0 rounded-lg text-slate-300 cursor-not-allowed"
                            disabled
                            aria-label="Cannot delete — uploaded by HR"
                            title="Uploaded by HR — contact HR to remove"
                          >
                            <Lock size={11} />
                          </Button>
                        )}
                      </div>
                    </td>
                  </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
};

const MyAssetsSection = () => {
  const [assets, setAssets] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      try {
        const res = await client.get(ENDPOINTS.HR.MY_ASSETS);
        setAssets(res.data || []);
      } catch (e: any) {
        if (e?.response?.status !== 404) {
          toast.error(errMsg(e, 'Failed to load assets'));
        }
        setAssets([]);
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  const tone: Record<string, string> = {
    allocated: 'bg-blue-50 text-blue-700 border-blue-200',
    returned: 'bg-emerald-50 text-emerald-700 border-emerald-200',
    lost: 'bg-red-50 text-red-700 border-red-200',
  };

  return (
    <div className="space-y-8">
      <section>
        <h3 className="text-[10px] font-black text-[#94A3B8] uppercase tracking-[0.2em]">My Assigned Assets</h3>
        <p className="text-xs text-slate-400 mt-1">Hardware and equipment HR has issued to you. Read-only — contact HR if anything looks wrong.</p>
      </section>

      {loading ? (
        <div className="p-12 flex justify-center"><Loader2 className="w-6 h-6 text-blue-600 animate-spin" /></div>
      ) : assets.length === 0 ? (
        <div className="p-12 bg-slate-50 rounded-3xl border border-dashed border-slate-200 text-center">
          <Briefcase size={36} className="mx-auto text-slate-300 mb-3" />
          <p className="text-sm font-black text-slate-500 uppercase tracking-widest">No assets on record</p>
          <p className="text-xs text-slate-400 mt-1 font-medium">When HR issues you hardware, it will appear here.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          {assets.map(a => (
            <Card key={a.id} className="p-6 border-slate-200 bg-white">
              <div className="flex justify-between items-start mb-4">
                <div className="p-3 bg-blue-50 text-blue-600 rounded-xl">
                  <Briefcase size={18} />
                </div>
                <span className={cn('text-[9px] font-black uppercase tracking-widest px-2 py-1 rounded-full border', tone[a.status] || 'bg-slate-100 text-slate-700 border-slate-200')}>
                  {a.status}
                </span>
              </div>
              <p className="text-base font-black text-[#0F172A]">{a.model}</p>
              <p className="text-[10px] font-bold text-blue-600 uppercase tracking-widest mt-1">
                {a.asset_type}{a.identifier ? ` · ${a.identifier}` : ''}
              </p>
              <div className="mt-4 pt-4 border-t border-slate-100 grid grid-cols-2 gap-3 text-[11px] font-bold text-slate-500">
                <div>
                  <p className="text-[9px] font-black text-slate-400 uppercase tracking-widest">Serial</p>
                  <p className="text-slate-700 mt-0.5">{a.serial_no || '—'}</p>
                </div>
                <div>
                  <p className="text-[9px] font-black text-slate-400 uppercase tracking-widest">Issued</p>
                  <p className="text-slate-700 mt-0.5">
                    {a.issued_date ? new Date(a.issued_date).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' }) : '—'}
                  </p>
                </div>
                {a.condition && (
                  <div>
                    <p className="text-[9px] font-black text-slate-400 uppercase tracking-widest">Condition</p>
                    <p className="text-slate-700 mt-0.5">{a.condition}</p>
                  </div>
                )}
                {a.returned_date && (
                  <div>
                    <p className="text-[9px] font-black text-slate-400 uppercase tracking-widest">Returned</p>
                    <p className="text-slate-700 mt-0.5">
                      {new Date(a.returned_date).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })}
                    </p>
                  </div>
                )}
              </div>
              {a.remarks && (
                <p className="mt-4 text-[10px] text-slate-500 italic line-clamp-2" title={a.remarks}>{a.remarks}</p>
              )}
            </Card>
          ))}
        </div>
      )}
    </div>
  );
};

const ResignationSection = ({ exitData, empProfile, onSubmitResignation, onWithdraw, onExitInterviewOpen, fetchExitData }: any) => {
  if (!exitData || !exitData.resignation) {
    // No active resignation — show submit button
    return (
      <div className="space-y-8">
        <section>
          <h3 className="text-[10px] font-black text-[#94A3B8] uppercase tracking-[0.2em] mb-6">Resignation & Exit</h3>
          <div className="p-10 bg-slate-50 rounded-3xl border border-slate-100 text-center">
            <LogOut size={48} className="mx-auto mb-4 text-slate-300" />
            <p className="text-sm font-black text-slate-500 uppercase tracking-wide mb-2">No Active Resignation</p>
            <p className="text-xs text-slate-400 mb-6 max-w-md mx-auto">
              If you wish to resign, you can submit your resignation here. Your notice period is <strong>{empProfile?.notice_period_days ?? 30} days</strong>.
            </p>
            <Button onClick={onSubmitResignation} className="h-11 px-8 bg-red-600 text-white rounded-xl text-[10px] font-black uppercase tracking-widest hover:bg-red-700">
              <LogOut size={16} className="mr-2" /> Submit Resignation
            </Button>
          </div>
        </section>
      </div>
    );
  }

  const r = exitData.resignation;
  const statusCfg = STATUS_CONFIG[r.status] || STATUS_CONFIG.submitted;
  const StatusIcon = statusCfg.icon;
  const canWithdraw = r.status === 'submitted' || r.status === 'accepted';
  const needsExitInterview = (r.status === 'exit_interview' || r.status === 'notice_period' || r.status === 'accepted' || r.status === 'clearance') && !exitData.exit_interview;

  return (
    <div className="space-y-8">
      <section>
        <h3 className="text-[10px] font-black text-[#94A3B8] uppercase tracking-[0.2em] mb-6">Resignation Status</h3>

        {/* Status Banner */}
        <div className={`p-6 rounded-2xl border ${statusCfg.bg} mb-6`}>
          <div className="flex items-center gap-4">
            <div className="p-3 bg-white rounded-xl shadow-sm">
              <StatusIcon size={24} className={statusCfg.color} />
            </div>
            <div className="flex-1">
              <p className={`text-lg font-black uppercase tracking-tight ${statusCfg.color}`}>{statusCfg.label}</p>
              <p className="text-xs text-slate-500 mt-0.5">
                Submitted on {new Date(r.resignation_date).toLocaleDateString()}
              </p>
            </div>
            {exitData.days_remaining !== null && r.status !== 'released' && r.status !== 'withdrawn' && (
              <div className="text-right">
                <p className="text-2xl font-black text-slate-800">{exitData.days_remaining}</p>
                <p className="text-[9px] font-black text-slate-400 uppercase tracking-widest">Days Left</p>
              </div>
            )}
          </div>
        </div>

        {/* Details Grid */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          <div className="p-4 bg-slate-50 rounded-xl border border-slate-100">
            <p className="text-[9px] font-black text-slate-400 uppercase">Reason</p>
            <p className="text-sm font-bold text-[#0F172A] mt-1">{RESIGNATION_REASONS[r.reason] || r.reason}</p>
          </div>
          <div className="p-4 bg-slate-50 rounded-xl border border-slate-100">
            <p className="text-[9px] font-black text-slate-400 uppercase">Notice Period</p>
            <p className="text-sm font-bold text-[#0F172A] mt-1">{r.notice_period_days} days</p>
          </div>
          <div className="p-4 bg-slate-50 rounded-xl border border-slate-100">
            <p className="text-[9px] font-black text-slate-400 uppercase">Last Working Day</p>
            <p className="text-sm font-bold text-[#0F172A] mt-1">{new Date(r.last_working_day).toLocaleDateString()}</p>
          </div>
          <div className="p-4 bg-slate-50 rounded-xl border border-slate-100">
            <p className="text-[9px] font-black text-slate-400 uppercase">Resignation Date</p>
            <p className="text-sm font-bold text-[#0F172A] mt-1">{new Date(r.resignation_date).toLocaleDateString()}</p>
          </div>
        </div>

        {/* Clearance Status */}
        {exitData.clearance_requests && exitData.clearance_requests.length > 0 && (
          <div className="mb-6">
            <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-3">Clearance Status</p>
            <div className="space-y-2">
              {exitData.clearance_requests.map((c: any) => (
                <div key={c.id} className="flex items-center justify-between p-3 bg-slate-50 rounded-xl border border-slate-100">
                  <div className="flex items-center gap-3">
                    {c.status === 'cleared' ? <CheckCircle size={16} className="text-green-500" /> :
                     c.status === 'flagged' ? <AlertTriangle size={16} className="text-red-500" /> :
                     <Clock size={16} className="text-amber-500" />}
                    <div>
                      <p className="text-xs font-black text-[#0F172A] uppercase">{c.department}</p>
                      <p className="text-[9px] text-slate-400">{c.assigned_to_name}</p>
                    </div>
                  </div>
                  <Badge variant={c.status === 'cleared' ? 'success' : c.status === 'flagged' ? 'danger' : 'warning'} className="text-[8px] font-black uppercase">
                    {c.status}
                  </Badge>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Exit Interview Status */}
        {exitData.exit_interview && (
          <div className="p-4 bg-green-50 border border-green-200 rounded-xl mb-6">
            <div className="flex items-center gap-2">
              <CheckCircle size={16} className="text-green-600" />
              <p className="text-xs font-black text-green-700 uppercase">Exit Interview Completed</p>
              <span className="text-[9px] text-green-600 ml-auto">{exitData.exit_interview.submitted_at ? new Date(exitData.exit_interview.submitted_at).toLocaleDateString() : ''}</span>
            </div>
          </div>
        )}

        {/* Actions */}
        <div className="flex flex-wrap gap-3">
          {canWithdraw && (
            <Button onClick={onWithdraw} className="h-11 px-6 bg-slate-100 text-slate-700 rounded-xl text-[10px] font-black uppercase tracking-widest hover:bg-slate-200">
              <XCircle size={16} className="mr-2" /> Withdraw Resignation
            </Button>
          )}
          {needsExitInterview && (
            <Button onClick={onExitInterviewOpen} className="h-11 px-6 bg-purple-600 text-white rounded-xl text-[10px] font-black uppercase tracking-widest hover:bg-purple-700">
              <FileText size={16} className="mr-2" /> Fill Exit Interview
            </Button>
          )}
        </div>
      </section>
    </div>
  );
};


// ─── Exit Interview Form Modal ──────────────────────────────

const ExitInterviewFormModal = ({ resignationId, onClose, onSuccess }: { resignationId: number; onClose: () => void; onSuccess: () => void }) => {
  const [form, setForm] = useState({
    reason_career: false, reason_studies: false, reason_personal: false,
    reason_relocation: false, reason_health: false, reason_work_environment: false,
    reason_compensation: false, reason_relationship: false, reason_role_mismatch: false,
    reason_other: '', reason_explanation: '',
    rating_job_satisfaction: 0, rating_work_life_balance: 0, rating_team_cooperation: 0,
    rating_management_communication: 0, rating_training_development: 0,
    rating_career_growth: 0, rating_compensation: 0, rating_company_culture: 0,
    feedback_liked_most: '', feedback_liked_least: '', feedback_suggestions: '',
  });
  const [submitting, setSubmitting] = useState(false);

  const setField = (key: string, val: any) => setForm(prev => ({ ...prev, [key]: val }));

  const reasonChecks = [
    { key: 'reason_career', label: 'Better career opportunity' },
    { key: 'reason_studies', label: 'Higher studies' },
    { key: 'reason_personal', label: 'Personal reasons' },
    { key: 'reason_relocation', label: 'Relocation' },
    { key: 'reason_health', label: 'Health reasons' },
    { key: 'reason_work_environment', label: 'Work environment' },
    { key: 'reason_compensation', label: 'Compensation and benefits' },
    { key: 'reason_relationship', label: 'Relationship with manager/team' },
    { key: 'reason_role_mismatch', label: 'Nature of work/role mismatch' },
  ];

  const ratings = [
    { key: 'rating_job_satisfaction', label: 'Job Satisfaction' },
    { key: 'rating_work_life_balance', label: 'Work-Life Balance' },
    { key: 'rating_team_cooperation', label: 'Team Cooperation' },
    { key: 'rating_management_communication', label: 'Communication from Management' },
    { key: 'rating_training_development', label: 'Training & Development' },
    { key: 'rating_career_growth', label: 'Growth & Career Advancement' },
    { key: 'rating_compensation', label: 'Compensation & Benefits' },
    { key: 'rating_company_culture', label: 'Company Policies & Culture' },
  ];

  const handleSubmit = async () => {
    setSubmitting(true);
    try {
      const payload = {
        ...form,
        rating_job_satisfaction: form.rating_job_satisfaction || null,
        rating_work_life_balance: form.rating_work_life_balance || null,
        rating_team_cooperation: form.rating_team_cooperation || null,
        rating_management_communication: form.rating_management_communication || null,
        rating_training_development: form.rating_training_development || null,
        rating_career_growth: form.rating_career_growth || null,
        rating_compensation: form.rating_compensation || null,
        rating_company_culture: form.rating_company_culture || null,
        reason_other: form.reason_other || null,
        reason_explanation: form.reason_explanation || null,
      };
      await client.post(ENDPOINTS.EXIT.EXIT_INTERVIEW, payload);
      toast.success('Exit interview submitted successfully');
      onSuccess();
    } catch (e: any) {
      toast.error(errMsg(e, 'Failed to submit'));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[90vh] overflow-y-auto animate-in zoom-in-95 duration-200" onClick={e => e.stopPropagation()}>
        <div className="sticky top-0 z-10 p-6 border-b border-slate-100 bg-white flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2.5 bg-purple-50 rounded-xl"><FileText size={20} className="text-purple-600" /></div>
            <div>
              <h3 className="text-lg font-black text-[#0F172A] uppercase tracking-tight">Exit Interview Form</h3>
              <p className="text-[10px] text-slate-400 font-bold uppercase tracking-widest">United Exploration India Pvt. Ltd.</p>
            </div>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-slate-100 rounded-lg"><XCircle size={20} className="text-slate-400" /></button>
        </div>

        <div className="p-6 space-y-8">
          {/* Section 1: Reason for Leaving */}
          <section>
            <h4 className="text-sm font-black text-[#0F172A] uppercase tracking-tight mb-4">1. Reason for Leaving</h4>
            <div className="space-y-2">
              {reasonChecks.map(r => (
                <label key={r.key} className="flex items-center gap-3 p-3 bg-slate-50 rounded-xl border border-slate-100 hover:bg-slate-100 cursor-pointer transition-colors">
                  <input type="checkbox" checked={(form as any)[r.key]} onChange={e => setField(r.key, e.target.checked)} className="w-4 h-4 rounded border-slate-300 text-purple-600 focus:ring-purple-500" />
                  <span className="text-sm font-medium text-slate-700">{r.label}</span>
                </label>
              ))}
              <div className="mt-3">
                <label className="text-[10px] font-black text-slate-500 uppercase tracking-widest mb-1.5 block">Other (please specify)</label>
                <input type="text" value={form.reason_other} onChange={e => setField('reason_other', e.target.value)} className="w-full h-10 bg-slate-50 border border-slate-200 rounded-xl px-4 text-sm outline-none" />
              </div>
              <div className="mt-3">
                <label className="text-[10px] font-black text-slate-500 uppercase tracking-widest mb-1.5 block">Brief explanation (in your own words)</label>
                <textarea value={form.reason_explanation} onChange={e => setField('reason_explanation', e.target.value)} rows={3} className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-sm outline-none resize-none" />
              </div>
            </div>
          </section>

          {/* Section 2: Ratings */}
          <section>
            <h4 className="text-sm font-black text-[#0F172A] uppercase tracking-tight mb-4">2. Work Experience at UEIPL</h4>
            <p className="text-xs text-slate-500 mb-4">Rate the following on a scale of 1-5 (1 = Poor, 5 = Excellent)</p>
            <div className="space-y-3">
              {ratings.map(r => (
                <div key={r.key} className="flex items-center justify-between p-3 bg-slate-50 rounded-xl border border-slate-100">
                  <span className="text-sm font-medium text-slate-700 flex-1">{r.label}</span>
                  <div className="flex gap-1">
                    {[1, 2, 3, 4, 5].map(n => (
                      <button
                        key={n}
                        onClick={() => setField(r.key, n)}
                        className={`w-8 h-8 rounded-lg text-xs font-black transition-all ${
                          (form as any)[r.key] >= n
                            ? 'bg-purple-600 text-white'
                            : 'bg-white border border-slate-200 text-slate-400 hover:border-purple-300'
                        }`}
                      >
                        {n}
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </section>

          {/* Section 3: Open Feedback */}
          <section>
            <h4 className="text-sm font-black text-[#0F172A] uppercase tracking-tight mb-4">3. Open Feedback</h4>
            <div className="space-y-4">
              <div>
                <label className="text-[10px] font-black text-slate-500 uppercase tracking-widest mb-1.5 block">What did you like most about working with UEIPL?</label>
                <textarea value={form.feedback_liked_most} onChange={e => setField('feedback_liked_most', e.target.value)} rows={3} className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-sm outline-none resize-none" />
              </div>
              <div>
                <label className="text-[10px] font-black text-slate-500 uppercase tracking-widest mb-1.5 block">What did you like least about working with UEIPL?</label>
                <textarea value={form.feedback_liked_least} onChange={e => setField('feedback_liked_least', e.target.value)} rows={3} className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-sm outline-none resize-none" />
              </div>
              <div>
                <label className="text-[10px] font-black text-slate-500 uppercase tracking-widest mb-1.5 block">Suggestions for improving the workplace</label>
                <textarea value={form.feedback_suggestions} onChange={e => setField('feedback_suggestions', e.target.value)} rows={3} className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-sm outline-none resize-none" />
              </div>
            </div>
          </section>
        </div>

        <div className="sticky bottom-0 p-6 border-t border-slate-100 bg-white flex gap-3">
          <Button onClick={onClose} className="flex-1 h-11 bg-slate-100 text-slate-700 rounded-xl text-xs font-black uppercase hover:bg-slate-200">Cancel</Button>
          <Button onClick={handleSubmit} disabled={submitting} className="flex-1 h-11 bg-purple-600 text-white rounded-xl text-xs font-black uppercase hover:bg-purple-700 disabled:opacity-50">
            {submitting ? 'Submitting...' : 'Submit Exit Interview'}
          </Button>
        </div>
      </div>
    </div>
  );
};
