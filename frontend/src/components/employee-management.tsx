import React, { useState, useEffect, useCallback, useRef } from 'react';
import { 
  Users, 
  Search, 
  Filter, 
  Plus, 
  Download, 
  FileUp,
  Eye, 
  Edit2, 
  Trash2,
  ArrowLeft,
  ArrowRight,
  Mail,
  Phone,
  MapPin,
  Briefcase,
  Building2,
  Calendar,
  CreditCard,
  ShieldCheck,
  FileText,
  Clock,
  History,
  DollarSign,
  UserCheck,
  Laptop,
  Monitor,
  HardDrive,
  CheckCircle2,
  AlertCircle,
  XCircle,
  Undo2,
  MoreVertical,
  ChevronLeft,
  ChevronRight,
  ShieldX,
  KeyRound,
  Loader2,
  LogOut,
  CheckCircle,
  Send,
  Star
} from 'lucide-react';
import { Card, Button, Badge, cn } from './ui-elements';
import { toast } from 'sonner';
import { Tabs, TabsContent, TabsList, TabsTrigger } from './ui/tabs';
import { Input } from './ui/input';
import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from './ui/dialog';
import { AssignShiftDialog } from './assign-shift-dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import type { UserRole } from '../types/erp';

const errMsg = (err: any, fallback = 'Something went wrong'): string => {
  const detail = err?.response?.data?.detail;
  if (!detail) return err?.message || fallback;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) return detail.map((d: any) => d?.msg || JSON.stringify(d)).join('; ');
  return fallback;
};

const downloadEmployeeTemplate = async () => {
  const response = await client.get(ENDPOINTS.HR.TEMPLATE, { responseType: 'blob' });
  const url = window.URL.createObjectURL(new Blob([response.data]));
  const link = document.createElement('a');
  link.href = url;
  link.setAttribute('download', 'employee_template.xlsx');
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
};

// --- Main Component ---
export const EmployeeManagement = ({ userRole = 'employee' }: { userRole?: UserRole }) => {
  const [view, setView] = useState<'directory' | 'details'>('directory');
  const [selectedEmp, setSelectedEmp] = useState<any>(null);
  const [activeMainTab, setActiveMainTab] = useState<'directory' | 'exits'>('directory');
  const [resignations, setResignations] = useState<any[]>([]);
  const [resignationsLoading, setResignationsLoading] = useState(false);
  const [employees, setEmployees] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [employeesError, setEmployeesError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [searchInput, setSearchInput] = useState('');
  const [search, setSearch] = useState('');
  const [deptFilter, setDeptFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [empTypeFilter, setEmpTypeFilter] = useState('');
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingEmp, setEditingEmp] = useState<any>(null);
  const [isBulkUploadOpen, setIsBulkUploadOpen] = useState(false);
  const [departments, setDepartments] = useState<any[]>([]);
  const [assignShiftEmp, setAssignShiftEmp] = useState<any>(null);

  const [isRolesModalOpen, setIsRolesModalOpen] = useState(false);
  const [rolesTargetEmp, setRolesTargetEmp] = useState<any>(null);
  const [availableRoles, setAvailableRoles] = useState<any[]>([]);
  const [selectedRoleIds, setSelectedRoleIds] = useState<number[]>([]);
  const [rolesLoading, setRolesLoading] = useState(false);
  const [rolesSaving, setRolesSaving] = useState(false);

  const [isResetPwModalOpen, setIsResetPwModalOpen] = useState(false);
  const [resetPwEmp, setResetPwEmp] = useState<any>(null);
  const [confirmAction, setConfirmAction] = useState<{ type: 'deactivate' | 'reactivate' | 'delete'; emp: any } | null>(null);
  const [confirmLoading, setConfirmLoading] = useState(false);
  const [deleteBlockers, setDeleteBlockers] = useState<any[] | null>(null);
  const [loadingBlockers, setLoadingBlockers] = useState(false);
  const [transferTargets, setTransferTargets] = useState<any[]>([]);
  const [transferTargetId, setTransferTargetId] = useState<string>('');
  const [transferring, setTransferring] = useState(false);
  const [newPassword, setNewPassword] = useState('');
  const [resettingPw, setResettingPw] = useState(false);

  const handleExportTemplate = async () => {
    try {
      await downloadEmployeeTemplate();
    } catch (error: any) {
      const msg = error?.response?.data?.error?.message || 'Failed to download template';
      toast.error(msg);
    }
  };

  const fetchDeleteBlockers = useCallback(async (empId: number) => {
    setLoadingBlockers(true);
    try {
      const res = await client.get(ENDPOINTS.HR.EMPLOYEE_DELETE_BLOCKERS(empId));
      setDeleteBlockers(res.data?.blockers || []);
    } catch {
      setDeleteBlockers([]);
    } finally {
      setLoadingBlockers(false);
    }
  }, []);

  useEffect(() => {
    if (confirmAction?.type !== 'delete' || !confirmAction.emp?.id) {
      setDeleteBlockers(null);
      setLoadingBlockers(false);
      setTransferTargetId('');
      return;
    }
    let cancelled = false;
    setDeleteBlockers(null);
    setTransferTargetId('');
    fetchDeleteBlockers(confirmAction.emp.id);

    if (transferTargets.length === 0) {
      client.get(ENDPOINTS.HR.EMPLOYEES, { params: { size: 200, status: 'active' } })
        .then(res => {
          if (cancelled) return;
          const items = Array.isArray(res.data?.items) ? res.data.items : [];
          setTransferTargets(items.filter((e: any) => e.id !== confirmAction.emp.id));
        })
        .catch(() => { /* picker will just be empty if this fails */ });
    }

    return () => { cancelled = true; };
  }, [confirmAction, fetchDeleteBlockers]);

  const handleTransferWork = async () => {
    if (!confirmAction?.emp?.id || !transferTargetId) return;
    const target = transferTargets.find((e: any) => String(e.id) === transferTargetId);
    const toUserId = target?.user?.id;
    if (!toUserId) {
      toast.error('Could not resolve target user');
      return;
    }
    setTransferring(true);
    try {
      const res = await client.post(
        ENDPOINTS.HR.EMPLOYEE_TRANSFER_WORK(confirmAction.emp.id),
        { to_user_id: toUserId },
      );
      const s = res.data?.summary || {};
      toast.success(
        `Transferred to ${target.user?.full_name || 'new owner'}: ` +
        `${s.projects || 0} project${s.projects === 1 ? '' : 's'}, ` +
        `${s.tasks || 0} task${s.tasks === 1 ? '' : 's'}, ` +
        `${s.leads || 0} lead${s.leads === 1 ? '' : 's'}`,
      );
      setTransferTargetId('');
      await fetchDeleteBlockers(confirmAction.emp.id);
    } catch (err: any) {
      toast.error(errMsg(err, 'Transfer failed'));
    } finally {
      setTransferring(false);
    }
  };

  const handleConfirmAction = async () => {
    if (!confirmAction) return;
    const { type, emp } = confirmAction;
    try {
      setConfirmLoading(true);
      if (type === 'deactivate') {
        await client.post(ENDPOINTS.HR.DEACTIVATE(emp.id));
        toast.success(`${emp.user?.full_name || 'Employee'} has been deactivated`);
      } else if (type === 'reactivate') {
        await client.post(ENDPOINTS.HR.REACTIVATE(emp.id));
        toast.success(`${emp.user?.full_name || 'Employee'} has been reactivated`);
      } else if (type === 'delete') {
        await client.delete(ENDPOINTS.HR.DELETE_EMPLOYEE(emp.id));
        toast.success(`${emp.user?.full_name || 'Employee'} has been permanently deleted`);
        if (view === 'details') setView('directory');
      }
      setConfirmAction(null);
      fetchEmployees();
    } catch (error: any) {
      const detail = error?.response?.data?.detail;
      if (type === 'delete' && error?.response?.status === 409 && detail && typeof detail === 'object') {
        if (Array.isArray(detail.blockers)) setDeleteBlockers(detail.blockers);
        toast.error(detail.message || 'Cannot delete: employee still tied to active work', { duration: 6000 });
      } else {
        toast.error(errMsg(error, `Failed to ${type} employee`));
      }
    } finally {
      setConfirmLoading(false);
    }
  };

  const isManagement =
    userRole === 'hr' ||
    userRole === 'admin' ||
    userRole === 'super admin' ||
    userRole === 'ceo';

  const canAssignRoles = userRole === 'hr' || userRole === 'admin' || userRole === 'super admin';

  const openRolesModal = async (emp: any) => {
    try {
      setRolesTargetEmp(emp);
      const existingIds = Array.isArray(emp?.user?.roles)
        ? emp.user.roles
            .map((r: any) => r?.id)
            .filter((id: any) => typeof id === 'number')
        : [];
      setSelectedRoleIds(existingIds);

      setIsRolesModalOpen(true);
      setRolesLoading(true);
      const resp = await client.get(ENDPOINTS.HR.ROLES);
      const items = Array.isArray((resp as any).data) ? (resp as any).data : [];
      setAvailableRoles(items);
    } catch (error: any) {
      const msg = error?.response?.data?.error?.message || 'Failed to load roles';
      toast.error(msg);
      setIsRolesModalOpen(false);
      setRolesTargetEmp(null);
    } finally {
      setRolesLoading(false);
    }
  };

  const saveRoles = async () => {
    if (!rolesTargetEmp?.id) return;
    if (selectedRoleIds.length === 0) {
      toast.error('Select at least one role');
      return;
    }

    try {
      setRolesSaving(true);
      const resp = await client.patch(
        ENDPOINTS.HR.EMPLOYEE_ROLES(rolesTargetEmp.id),
        { role_ids: selectedRoleIds }
      );
      const updatedEmp = (resp as any).data;
      setEmployees((prev) => prev.map((e) => (e.id === updatedEmp.id ? updatedEmp : e)));
      if (selectedEmp?.id === updatedEmp.id) setSelectedEmp(updatedEmp);
      toast.success('Roles updated');
      setIsRolesModalOpen(false);
      setRolesTargetEmp(null);
    } catch (error: any) {
      const msg = error?.response?.data?.error?.message || 'Failed to update roles';
      toast.error(msg);
    } finally {
      setRolesSaving(false);
    }
  };

  const fetchEmployees = useCallback(async () => {
    try {
      setLoading(true);
      setEmployeesError(null);
      const params: any = { page, size: pageSize };
      if (search) params.search = search;
      if (deptFilter && deptFilter !== 'ALL') params.department = deptFilter;
      if (statusFilter && statusFilter !== 'ALL') params.status = statusFilter;
      if (empTypeFilter && empTypeFilter !== 'ALL') params.employment_type = empTypeFilter;

      const response = await client.get(ENDPOINTS.HR.EMPLOYEES, { params });
      const items = Array.isArray((response as any).data?.items) ? (response as any).data.items : [];
      const nextTotal = typeof (response as any).data?.total === 'number' ? (response as any).data.total : items.length;
      setEmployees(items);
      setTotal(nextTotal);
    } catch (error: any) {
      const status = error?.response?.status;
      const msg = status >= 500
        ? "Server error while loading employees. Please try again."
        : (error?.response?.data?.error?.message || "Failed to fetch employees");
      setEmployees([]);
      setTotal(0);
      setEmployeesError(msg);
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, search, deptFilter, statusFilter, empTypeFilter]);

  useEffect(() => {
    fetchEmployees();
  }, [fetchEmployees]);

  // Debounce the search input so we don't hit the API on every keystroke.
  useEffect(() => {
    const t = setTimeout(() => setSearch(searchInput.trim()), 250);
    return () => clearTimeout(t);
  }, [searchInput]);

  // Any filter/search/page-size change drops the user back to page 1, so they
  // don't sit on a page that no longer has results.
  useEffect(() => {
    setPage(1);
  }, [search, deptFilter, statusFilter, empTypeFilter, pageSize]);

  useEffect(() => {
    const fetchDepts = async () => {
      try {
        const res = await client.get(ENDPOINTS.HR.DEPARTMENTS);
        setDepartments((res as any).data || []);
      } catch (err: any) {
        // Surface the failure — silent failure here is what made the
        // department dropdown look broken for HR users (admin-only gate).
        toast.error(err?.response?.data?.detail || 'Failed to load departments');
      }
    };
    fetchDepts();
  }, []);

  const fetchResignations = async () => {
    setResignationsLoading(true);
    try {
      const res = await client.get(ENDPOINTS.EXIT.RESIGNATIONS);
      setResignations(res.data);
    } catch {
      setResignations([]);
    } finally {
      setResignationsLoading(false);
    }
  };

  const handleOpenDetails = (emp: any, initialTab?: string) => {
    setSelectedEmp(emp);
    setView('details');
    if (initialTab) {
      // signal to EmployeeDetails which tab to open
      setSelectedEmp({ ...emp, _initialTab: initialTab });
    }
  };

  const handleImpersonate = async (userId: number) => {
    try {
      const response = await client.post(ENDPOINTS.AUTH.IMPERSONATE(userId));
      const { access_token, refresh_token } = response.data;
      // We set it in client's local memory too if it exposes that, 
      // but usually the next refresh/reload handles it.
      // Easiest is to set and reload.
      localStorage.setItem('token', access_token);
      localStorage.setItem('refresh_token', refresh_token);
      toast.success("Impersonation started");
      window.location.href = '/dashboard';
    } catch (error) {
      toast.error("Failed to impersonate user");
    }
  };

  const isSuperAdmin = userRole === 'super admin';

  const handleResetPassword = async () => {
    if (!newPassword || newPassword.length < 6) {
      toast.error('Password must be at least 6 characters');
      return;
    }
    const userId = resetPwEmp?.user_id || resetPwEmp?.user?.id;
    if (!userId) {
      toast.error('No user account linked to this employee');
      return;
    }
    setResettingPw(true);
    try {
      await client.patch(ENDPOINTS.ADMIN.USER_DETAIL(userId), { password: newPassword });
      toast.success(`Password reset for ${resetPwEmp.user?.full_name || resetPwEmp.user?.email || 'employee'}`);
      setIsResetPwModalOpen(false);
      setNewPassword('');
      setResetPwEmp(null);
    } catch (e) {
      toast.error('Password reset failed');
    } finally {
      setResettingPw(false);
    }
  };

  const resetPwDialog = (
    <Dialog open={isResetPwModalOpen} onOpenChange={(open: boolean) => { setIsResetPwModalOpen(open); if (!open) { setNewPassword(''); setResetPwEmp(null); } }}>
      <DialogContent className="max-w-md p-0 overflow-hidden rounded-3xl border-none">
        <div className="bg-amber-600 p-8 text-white">
          <DialogTitle className="text-2xl font-bold">Reset Password</DialogTitle>
          {resetPwEmp && (
            <p className="text-amber-100 text-sm mt-1">
              {resetPwEmp.user?.full_name || resetPwEmp.user?.email || `Employee #${resetPwEmp.employee_id}`}
            </p>
          )}
        </div>
        <div className="p-8 space-y-4">
          <div className="space-y-2">
            <label className="text-sm font-semibold text-slate-700">New Password</label>
            <Input
              type="password"
              placeholder="Enter new password (min 6 characters)"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              className="h-11 rounded-xl bg-slate-50"
            />
          </div>
          <p className="text-xs text-slate-400">This will immediately change the employee's password. They will need to use the new password on their next login.</p>
        </div>
        <DialogFooter className="p-8 pt-0">
          <Button
            onClick={handleResetPassword}
            disabled={resettingPw || newPassword.length < 6}
            className="bg-amber-600 hover:bg-amber-700 text-white rounded-xl w-full h-11"
          >
            {resettingPw ? <><Loader2 className="w-4 h-4 animate-spin mr-2" /> Resetting...</> : 'Reset Password'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );

  if (view === 'details') {
    return (
      <>
        <EmployeeDetails
          emp={selectedEmp}
          onBack={() => setView('directory')}
          userRole={userRole}
          onImpersonate={handleImpersonate}
          onResetPassword={(emp) => {
            setResetPwEmp(emp);
            setNewPassword('');
            setIsResetPwModalOpen(true);
          }}
          onDeactivate={(emp) => setConfirmAction({ type: 'deactivate', emp })}
          onReactivate={(emp) => setConfirmAction({ type: 'reactivate', emp })}
          onDelete={(emp) => setConfirmAction({ type: 'delete', emp })}
          onUpdated={(updated: any) => {
            setSelectedEmp(updated);
            setEmployees((prev) => prev.map((e) => (e.id === updated.id ? updated : e)));
          }}
        />
        {resetPwDialog}
      </>
    );
  }

  // count active resignations for badge
  const activeResignationStatuses = ['submitted', 'accepted', 'notice_period', 'exit_interview', 'clearance'];
  const activeResignationCount = resignations.filter(r => activeResignationStatuses.includes(r.status)).length;

  return (
    <div className="p-8 space-y-8 max-w-[1600px] mx-auto animate-in fade-in duration-500 pb-20">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
        <div>
          <h2 className="text-3xl font-black text-[#0F172A] tracking-tighter uppercase">
            {isManagement ? "Employee Management" : "Team Directory"}
          </h2>
          <p className="text-[#64748B] font-bold uppercase tracking-widest text-[10px] mt-1">
            {isManagement ? "Lifecycle Tracking & Organizational Governance" : "Connect with your colleagues across the enterprise"}
          </p>
        </div>
        {isManagement && activeMainTab === 'directory' && (
          <div className="flex gap-3">
             <Button
               variant="outline"
               className="font-black h-12 px-6 uppercase text-[10px] tracking-widest border-slate-200"
               onClick={() => setIsBulkUploadOpen(true)}
             >
                <FileUp className="w-4 h-4 mr-2" /> Bulk Upload
             </Button>
             <Button
               variant="outline"
               className="font-black h-12 px-6 uppercase text-[10px] tracking-widest border-slate-200"
               onClick={handleExportTemplate}
             >
               <Download className="w-4 h-4 mr-2" /> Export Template
             </Button>
             <Button
               className="font-black h-12 px-6 uppercase text-[10px] tracking-widest bg-blue-600 hover:bg-blue-700 shadow-lg shadow-blue-600/20"
               onClick={() => {
                 setEditingEmp(null);
                 setIsModalOpen(true);
               }}
             >
                <Plus className="w-4 h-4 mr-2" /> Add Employee
             </Button>
          </div>
        )}
      </div>

      {/* Main tab bar — only for management */}
      {isManagement && (
        <div className="flex gap-1 bg-slate-100 p-1.5 rounded-2xl w-fit">
          <button
            onClick={() => setActiveMainTab('directory')}
            className={cn(
              "h-10 px-6 rounded-xl font-black text-[10px] uppercase tracking-widest transition-all",
              activeMainTab === 'directory' ? "bg-white shadow-sm text-[#0F172A]" : "text-slate-400 hover:text-slate-600"
            )}
          >
            All Employees
          </button>
          <button
            onClick={() => {
              setActiveMainTab('exits');
              if (resignations.length === 0) fetchResignations();
            }}
            className={cn(
              "h-10 px-6 rounded-xl font-black text-[10px] uppercase tracking-widest transition-all flex items-center gap-2",
              activeMainTab === 'exits' ? "bg-white shadow-sm text-[#0F172A]" : "text-slate-400 hover:text-slate-600"
            )}
          >
            Exit Pipeline
            {activeResignationCount > 0 && (
              <span className={cn(
                "h-5 min-w-[20px] px-1.5 rounded-full text-[8px] font-black flex items-center justify-center",
                activeMainTab === 'exits' ? "bg-red-100 text-red-600" : "bg-red-500 text-white"
              )}>
                {activeResignationCount}
              </span>
            )}
          </button>
        </div>
      )}

      {/* ── Exit Pipeline Tab ── */}
      {activeMainTab === 'exits' && isManagement && (
        <ExitPipelinePanel
          resignations={resignations}
          loading={resignationsLoading}
          onRefresh={fetchResignations}
          onViewEmployee={(empId) => {
            // find the employee in the already-loaded list or fetch fresh
            const match = employees.find(e => e.id === empId);
            if (match) {
              setSelectedEmp({ ...match, _initialTab: 'exit' });
              setView('details');
            } else {
              client.get(ENDPOINTS.HR.EMPLOYEE_DETAIL(empId)).then(res => {
                setSelectedEmp({ ...res.data, _initialTab: 'exit' });
                setView('details');
              }).catch(() => toast.error('Failed to load employee'));
            }
          }}
        />
      )}

      {activeMainTab === 'directory' && <Card className="border-slate-200 overflow-hidden shadow-sm">
        <div className="p-4 md:p-6 border-b border-slate-100 bg-slate-50/50">
          <div className="flex flex-col md:flex-row md:items-center gap-3">
            {/* Search — dominant, grows to fill */}
            <div className="relative flex-1 min-w-0 md:min-w-[280px]">
              <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-[18px] h-[18px] text-slate-400 pointer-events-none" aria-hidden="true" />
              <input
                type="text"
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
                placeholder="Search by name, employee ID, or email…"
                aria-label="Search employees"
                className="block w-full h-12 pl-12 pr-20 bg-white border border-slate-200 rounded-2xl text-sm font-medium text-slate-900 placeholder:text-slate-400 placeholder:font-normal focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600/30 focus-visible:border-blue-400 transition-colors"
              />
              {searchInput && loading && searchInput === search && (
                <Loader2 className="absolute right-12 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 animate-spin" aria-hidden="true" />
              )}
              {searchInput && (
                <button
                  type="button"
                  onClick={() => setSearchInput('')}
                  aria-label="Clear search"
                  className="absolute right-2 top-1/2 -translate-y-1/2 h-8 w-8 rounded-lg flex items-center justify-center text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600/30"
                >
                  <XCircle size={16} />
                </button>
              )}
            </div>

            {/* Filters — fixed-width group, aligned right on desktop */}
            <div className="flex flex-col sm:flex-row gap-3 md:flex-shrink-0">
              <Select value={deptFilter} onValueChange={setDeptFilter}>
                <SelectTrigger
                  aria-label="Filter by department"
                  className="w-full sm:w-[200px] h-12 bg-white rounded-2xl border-slate-200 text-sm font-medium text-slate-700"
                >
                  <SelectValue placeholder="All departments" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="ALL">All departments</SelectItem>
                  {departments.map(d => (
                    <SelectItem key={d.id} value={d.name}>{d.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Select value={statusFilter} onValueChange={setStatusFilter}>
                <SelectTrigger
                  aria-label="Filter by status"
                  className="w-full sm:w-[160px] h-12 bg-white rounded-2xl border-slate-200 text-sm font-medium text-slate-700"
                >
                  <SelectValue placeholder="All statuses" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="ALL">All statuses</SelectItem>
                  <SelectItem value="active">Active</SelectItem>
                  <SelectItem value="inactive">Inactive</SelectItem>
                  <SelectItem value="on_leave">On leave</SelectItem>
                </SelectContent>
              </Select>
              <Select value={empTypeFilter} onValueChange={setEmpTypeFilter}>
                <SelectTrigger
                  aria-label="Filter by employment type"
                  className="w-full sm:w-[160px] h-12 bg-white rounded-2xl border-slate-200 text-sm font-medium text-slate-700"
                >
                  <SelectValue placeholder="All types" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="ALL">All types</SelectItem>
                  <SelectItem value="permanent">Permanent</SelectItem>
                  <SelectItem value="contractual">Contractual</SelectItem>
                  <SelectItem value="advisor">Advisor</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* Active filter summary */}
          {(search || (deptFilter && deptFilter !== 'ALL') || (statusFilter && statusFilter !== 'ALL') || (empTypeFilter && empTypeFilter !== 'ALL')) && (
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <span className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Active filters:</span>
              {search && (
                <button
                  type="button"
                  onClick={() => setSearchInput('')}
                  className="inline-flex items-center gap-1.5 h-7 pl-3 pr-2 rounded-full bg-blue-50 text-blue-700 text-xs font-bold hover:bg-blue-100 transition-colors"
                >
                  <span className="max-w-[160px] truncate">Search: {search}</span>
                  <XCircle size={13} aria-hidden="true" />
                  <span className="sr-only">Clear search filter</span>
                </button>
              )}
              {deptFilter && deptFilter !== 'ALL' && (
                <button
                  type="button"
                  onClick={() => setDeptFilter('ALL')}
                  className="inline-flex items-center gap-1.5 h-7 pl-3 pr-2 rounded-full bg-slate-100 text-slate-700 text-xs font-bold hover:bg-slate-200 transition-colors"
                >
                  <span>{deptFilter}</span>
                  <XCircle size={13} aria-hidden="true" />
                  <span className="sr-only">Clear department filter</span>
                </button>
              )}
              {statusFilter && statusFilter !== 'ALL' && (
                <button
                  type="button"
                  onClick={() => setStatusFilter('ALL')}
                  className="inline-flex items-center gap-1.5 h-7 pl-3 pr-2 rounded-full bg-slate-100 text-slate-700 text-xs font-bold hover:bg-slate-200 transition-colors capitalize"
                >
                  <span>{statusFilter.replace('_', ' ')}</span>
                  <XCircle size={13} aria-hidden="true" />
                  <span className="sr-only">Clear status filter</span>
                </button>
              )}
              {empTypeFilter && empTypeFilter !== 'ALL' && (
                <button
                  type="button"
                  onClick={() => setEmpTypeFilter('ALL')}
                  className={cn(
                    "inline-flex items-center gap-1.5 h-7 pl-3 pr-2 rounded-full text-xs font-bold transition-colors capitalize",
                    empTypeFilter === 'advisor' ? "bg-purple-50 text-purple-700 hover:bg-purple-100" :
                    empTypeFilter === 'contractual' ? "bg-amber-50 text-amber-700 hover:bg-amber-100" :
                    "bg-slate-100 text-slate-700 hover:bg-slate-200",
                  )}
                >
                  <span>{empTypeFilter}</span>
                  <XCircle size={13} aria-hidden="true" />
                  <span className="sr-only">Clear employment type filter</span>
                </button>
              )}
              <button
                type="button"
                onClick={() => { setSearchInput(''); setDeptFilter('ALL'); setStatusFilter('ALL'); setEmpTypeFilter('ALL'); }}
                className="text-[10px] font-black text-slate-500 uppercase tracking-widest hover:text-slate-900 underline underline-offset-4 ml-1"
              >
                Clear all
              </button>
            </div>
          )}
        </div>

        <div className="overflow-x-auto scrollbar-none">
          <table className="w-full text-left border-collapse min-w-[1200px]">
            <thead>
              <tr className="bg-white border-b border-slate-100">
                <th className="px-8 py-6 text-[10px] font-black text-slate-400 uppercase tracking-[0.2em]">ID & Professional</th>
                <th className="px-8 py-6 text-[10px] font-black text-slate-400 uppercase tracking-[0.2em]">Department</th>
                <th className="px-8 py-6 text-[10px] font-black text-slate-400 uppercase tracking-[0.2em]">Designation</th>
                <th className="px-8 py-6 text-[10px] font-black text-slate-400 uppercase tracking-[0.2em]">Contact</th>
                <th className="px-8 py-6 text-[10px] font-black text-slate-400 uppercase tracking-[0.2em]">Status</th>
                <th className="px-8 py-6 text-[10px] font-black text-slate-400 uppercase tracking-[0.2em]">Joined</th>
                <th className="px-8 py-6 text-[10px] font-black text-slate-400 uppercase tracking-[0.2em] text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {loading ? (
                Array(Math.min(pageSize, 8)).fill(0).map((_, i) => (
                  <tr key={`skeleton-${i}`} aria-hidden="true">
                    <td className="px-8 py-6">
                      <div className="flex items-center gap-4">
                        <div className="w-10 h-10 rounded-xl bg-slate-100 animate-pulse" />
                        <div className="space-y-2">
                          <div className="h-3 w-32 bg-slate-100 rounded animate-pulse" />
                          <div className="h-2 w-16 bg-slate-100 rounded animate-pulse" />
                        </div>
                      </div>
                    </td>
                    <td className="px-8 py-6"><div className="h-3 w-24 bg-slate-100 rounded animate-pulse" /></td>
                    <td className="px-8 py-6"><div className="h-3 w-28 bg-slate-100 rounded animate-pulse" /></td>
                    <td className="px-8 py-6"><div className="h-3 w-36 bg-slate-100 rounded animate-pulse" /></td>
                    <td className="px-8 py-6"><div className="h-4 w-16 bg-slate-100 rounded animate-pulse" /></td>
                    <td className="px-8 py-6"><div className="h-3 w-20 bg-slate-100 rounded animate-pulse" /></td>
                    <td className="px-8 py-6"><div className="h-3 w-24 bg-slate-100 rounded ml-auto animate-pulse" /></td>
                  </tr>
                ))
              ) : employeesError ? (
                <tr>
                  <td colSpan={7} className="p-20 text-center">
                    <div className="flex flex-col items-center gap-3">
                      <AlertCircle className="w-8 h-8 text-red-500" aria-hidden="true" />
                      <p className="font-black text-red-500 uppercase text-xs tracking-widest">{employeesError}</p>
                      <Button variant="outline" size="sm" onClick={() => fetchEmployees()} className="mt-2 text-[10px] uppercase tracking-widest">
                        Retry
                      </Button>
                    </div>
                  </td>
                </tr>
              ) : employees.length === 0 ? (
                <tr>
                  <td colSpan={7} className="p-20 text-center">
                    <div className="flex flex-col items-center gap-3">
                      <Users className="w-8 h-8 text-slate-300" aria-hidden="true" />
                      <p className="font-black text-slate-500 uppercase text-xs tracking-widest">No employees found</p>
                      {(search || (deptFilter && deptFilter !== 'ALL') || (statusFilter && statusFilter !== 'ALL') || (empTypeFilter && empTypeFilter !== 'ALL')) ? (
                        <>
                          <p className="text-[11px] text-slate-400 font-bold">Try broadening your search or clearing filters.</p>
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => { setSearchInput(''); setDeptFilter('ALL'); setStatusFilter('ALL'); setEmpTypeFilter('ALL'); }}
                            className="mt-1 text-[10px] uppercase tracking-widest"
                          >
                            Clear filters
                          </Button>
                        </>
                      ) : (
                        <p className="text-[11px] text-slate-400 font-bold">No employee records yet.</p>
                      )}
                    </div>
                  </td>
                </tr>
              ) : employees.map((emp) => (
                <tr key={emp.id} className="hover:bg-slate-50/80 transition-colors group cursor-pointer" onClick={() => handleOpenDetails(emp)}>
                  <td className="px-8 py-6">
                    <div className="flex items-center gap-4">
                      <div className="w-10 h-10 rounded-xl bg-blue-50 text-blue-600 flex items-center justify-center font-black text-xs shadow-sm border border-blue-100">
                        {emp.user.full_name.charAt(0)}
                      </div>
                      <div>
                        <p className="text-sm font-black text-[#0F172A]">{emp.user.full_name}</p>
                        <p className="text-[10px] font-bold text-blue-600 uppercase tracking-widest">{emp.employee_id}</p>
                      </div>
                    </div>
                  </td>
                  <td className="px-8 py-6 text-sm font-bold text-slate-600">{emp.department}</td>
                  <td className="px-8 py-6 text-sm font-bold text-slate-600">{emp.designation}</td>
                  <td className="px-8 py-6 text-[10px] font-bold text-slate-500">{emp.user.email}</td>
                  <td className="px-8 py-6">
                    <div className="flex flex-col gap-1">
                      <Badge
                        variant={emp.status === 'active' ? 'success' : emp.status === 'on_leave' ? 'warning' : 'error'}
                        className="text-[9px] font-black uppercase tracking-widest"
                      >
                        {emp.status}
                      </Badge>
                      <span className={cn(
                        "text-[8px] font-black uppercase tracking-widest",
                        (emp.employment_type || 'permanent') === 'advisor' ? "text-purple-600" :
                        (emp.employment_type || 'permanent') === 'contractual' ? "text-amber-600" :
                        "text-slate-400"
                      )}>
                        {emp.employment_type || 'permanent'}
                      </span>
                    </div>
                  </td>
                  <td className="px-8 py-6 text-xs font-bold text-slate-500">{new Date(emp.date_of_joining).toLocaleDateString()}</td>
                  <td className="px-8 py-6 text-right" onClick={(e) => e.stopPropagation()}>
                    <div className="flex justify-end gap-2">
                      <Button variant="ghost" size="sm" className="h-9 w-9 p-0 rounded-lg hover:bg-white hover:shadow-sm" onClick={() => handleOpenDetails(emp)} aria-label={`View ${emp.user.full_name}`} title="View Details"><Eye size={14} className="text-blue-600" /></Button>
                      {isManagement && (
                        <>
                          {isSuperAdmin && (
                            <Button
                              variant="ghost"
                              size="sm"
                              className="h-9 w-9 p-0 rounded-lg hover:bg-blue-50 hover:text-blue-600 transition-colors"
                              onClick={() => handleImpersonate(emp.user_id || emp.user.id)}
                              aria-label={`Impersonate ${emp.user.full_name}`}
                              title="Impersonate User"
                            >
                              <UserCheck size={14} />
                            </Button>
                          )}
                          {canAssignRoles && (
                            <Button
                              variant="ghost"
                              size="sm"
                              className="h-9 w-9 p-0 rounded-lg hover:bg-white hover:shadow-sm"
                              onClick={() => openRolesModal(emp)}
                              aria-label={`Manage roles for ${emp.user.full_name}`}
                              title="Manage Roles"
                            >
                              <ShieldCheck size={14} className="text-slate-400" />
                            </Button>
                          )}
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-9 w-9 p-0 rounded-lg hover:bg-white hover:shadow-sm"
                            onClick={() => {
                              setEditingEmp(emp);
                              setIsModalOpen(true);
                            }}
                            aria-label={`Edit ${emp.user.full_name}`}
                            title="Edit Employee"
                          >
                            <Edit2 size={14} className="text-slate-400" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-9 w-9 p-0 rounded-lg hover:bg-blue-50 hover:shadow-sm"
                            onClick={() => setAssignShiftEmp(emp)}
                            aria-label={`Assign shift to ${emp.user.full_name}`}
                            title="Assign Shift"
                          >
                            <Calendar size={14} className="text-blue-500" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-9 w-9 p-0 rounded-lg hover:bg-amber-50 hover:shadow-sm"
                            onClick={() => {
                              setResetPwEmp(emp);
                              setNewPassword('');
                              setIsResetPwModalOpen(true);
                            }}
                            aria-label={`Reset password for ${emp.user.full_name}`}
                            title="Reset Password"
                          >
                            <KeyRound size={14} className="text-amber-500" />
                          </Button>
                          {emp.status === 'active' ? (
                            <Button
                              variant="ghost"
                              size="sm"
                              className="h-9 w-9 p-0 rounded-lg hover:bg-red-50 hover:shadow-sm"
                              onClick={() => setConfirmAction({ type: 'deactivate', emp })}
                              aria-label={`Deactivate ${emp.user.full_name}`}
                              title="Deactivate Employee"
                            >
                              <ShieldX size={14} className="text-red-500" />
                            </Button>
                          ) : (
                            <Button
                              variant="ghost"
                              size="sm"
                              className="h-9 w-9 p-0 rounded-lg hover:bg-green-50 hover:shadow-sm"
                              onClick={() => setConfirmAction({ type: 'reactivate', emp })}
                              aria-label={`Reactivate ${emp.user.full_name}`}
                              title="Reactivate Employee"
                            >
                              <ShieldCheck size={14} className="text-green-500" />
                            </Button>
                          )}
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-9 w-9 p-0 rounded-lg hover:bg-red-50 hover:shadow-sm"
                            onClick={() => setConfirmAction({ type: 'delete', emp })}
                            aria-label={`Delete ${emp.user.full_name}`}
                            title="Delete Employee"
                          >
                            <Trash2 size={14} className="text-red-500" />
                          </Button>
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        
        <PaginationFooter
          page={page}
          pageSize={pageSize}
          total={total}
          visibleCount={employees.length}
          onPageChange={setPage}
          onPageSizeChange={setPageSize}
          disabled={loading}
        />
      </Card>}

      <EmployeeModal 
        isOpen={isModalOpen} 
        onClose={() => setIsModalOpen(false)} 
        onSuccess={fetchEmployees}
        editingEmp={editingEmp}
        departments={departments}
      />

      <Dialog open={isRolesModalOpen} onOpenChange={(open) => {
          setIsRolesModalOpen(open);
          if (!open) setRolesTargetEmp(null);
        }}
      >
        <DialogContent className="max-w-[520px] max-h-[70vh] flex flex-col overflow-hidden">
          <DialogHeader>
            <DialogTitle className="text-lg font-black uppercase tracking-widest">
              Manage Roles
            </DialogTitle>
          </DialogHeader>

          <div className="space-y-3 flex-1 overflow-y-auto">
            <div className="text-xs font-bold text-slate-600">
              {rolesTargetEmp?.user?.full_name || 'Employee'}
            </div>

            {rolesLoading ? (
              <div className="text-sm font-bold text-slate-500">Loading roles...</div>
            ) : availableRoles.length === 0 ? (
              <div className="text-sm font-bold text-slate-500">No roles available</div>
            ) : (
              <div className="grid grid-cols-1 gap-2">
                {availableRoles.map((role) => {
                  const roleId = Number(role?.id);
                  const checked = selectedRoleIds.includes(roleId);
                  const inputId = `role-${roleId}`;
                  return (
                    <label
                      key={roleId}
                      htmlFor={inputId}
                      className={cn(
                        'flex items-center justify-between gap-3 rounded-xl border p-3 cursor-pointer',
                        checked ? 'border-blue-200 bg-blue-50/60' : 'border-slate-200 bg-white'
                      )}
                    >
                      <div className="flex flex-col">
                        <span className="text-xs font-black text-slate-800 uppercase tracking-widest">
                          {role?.name}
                        </span>
                        {role?.description ? (
                          <span className="text-[11px] font-bold text-slate-500">
                            {role.description}
                          </span>
                        ) : null}
                      </div>
                      <input
                        id={inputId}
                        type="checkbox"
                        aria-label={role?.name}
                        checked={checked}
                        onChange={() => {
                          if (!Number.isFinite(roleId)) return;
                          setSelectedRoleIds((prev) =>
                            prev.includes(roleId)
                              ? prev.filter((id) => id !== roleId)
                              : [...prev, roleId]
                          );
                        }}
                        className="h-4 w-4"
                      />
                    </label>
                  );
                })}
              </div>
            )}
          </div>

          <DialogFooter>
            <Button
              variant="outline"
              className="h-11 rounded-xl font-black uppercase tracking-widest text-xs"
              onClick={() => setIsRolesModalOpen(false)}
              disabled={rolesSaving}
            >
              Cancel
            </Button>
            <Button
              className="h-11 rounded-xl font-black uppercase tracking-widest text-xs bg-blue-600 hover:bg-blue-700"
              onClick={saveRoles}
              disabled={rolesLoading || rolesSaving || selectedRoleIds.length === 0}
            >
              {rolesSaving ? 'Saving...' : 'Save Roles'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <BulkUploadModal
        isOpen={isBulkUploadOpen}
        onClose={() => setIsBulkUploadOpen(false)}
        onSuccess={fetchEmployees}
      />

      {resetPwDialog}

      {/* Confirm Deactivate / Reactivate / Delete Dialog */}
      <Dialog open={!!confirmAction} onOpenChange={() => !confirmLoading && setConfirmAction(null)}>
        <DialogContent className="max-w-sm p-0 overflow-hidden rounded-3xl border-none shadow-2xl">
          <DialogTitle className="sr-only">
            {confirmAction?.type === 'delete' ? 'Delete' : confirmAction?.type === 'deactivate' ? 'Deactivate' : 'Reactivate'} Employee
          </DialogTitle>
          <div className="px-6 pt-8 pb-4 text-center">
            {/* Icon */}
            <div className={cn(
              "w-14 h-14 rounded-full mx-auto flex items-center justify-center mb-4",
              confirmAction?.type === 'delete' ? "bg-red-100" :
              confirmAction?.type === 'deactivate' ? "bg-red-100" : "bg-green-100"
            )}>
              {confirmAction?.type === 'delete' && <Trash2 size={24} className="text-red-600" />}
              {confirmAction?.type === 'deactivate' && <ShieldX size={24} className="text-red-600" />}
              {confirmAction?.type === 'reactivate' && <ShieldCheck size={24} className="text-green-600" />}
            </div>

            {/* Title */}
            <h3 className="text-lg font-black text-slate-900 tracking-tight">
              {confirmAction?.type === 'delete' && 'Delete Employee'}
              {confirmAction?.type === 'deactivate' && 'Deactivate Employee'}
              {confirmAction?.type === 'reactivate' && 'Reactivate Employee'}
            </h3>

            {/* Employee card */}
            {confirmAction?.emp && (
              <div className="mt-4 p-3 bg-slate-50 rounded-xl border border-slate-200 inline-flex items-center gap-3">
                <div className="w-9 h-9 rounded-full bg-slate-200 flex items-center justify-center text-xs font-black text-slate-600">
                  {(confirmAction.emp.user?.full_name || '?').charAt(0).toUpperCase()}
                </div>
                <div className="text-left">
                  <p className="text-sm font-bold text-slate-800 leading-tight">{confirmAction.emp.user?.full_name}</p>
                  <p className="text-[10px] text-slate-400 font-semibold">{confirmAction.emp.user?.email} &middot; {confirmAction.emp.employee_id}</p>
                </div>
              </div>
            )}

            {/* Description */}
            <p className="mt-4 text-xs text-slate-500 leading-relaxed max-w-[280px] mx-auto">
              {confirmAction?.type === 'delete' && 'This will permanently remove the user account and all employee data. This action cannot be undone.'}
              {confirmAction?.type === 'deactivate' && 'This employee will be marked as inactive and will no longer be able to log in to the system.'}
              {confirmAction?.type === 'reactivate' && 'This employee will be reactivated and their login access will be restored.'}
            </p>

            {confirmAction?.type === 'delete' && (
              <div className="mt-4">
                {loadingBlockers ? (
                  <div className="flex items-center justify-center gap-2 text-[11px] font-bold text-slate-400 uppercase tracking-widest">
                    <Loader2 size={12} className="animate-spin" /> Checking active assignments…
                  </div>
                ) : deleteBlockers && deleteBlockers.length > 0 ? (
                  <div className="text-left bg-red-50 border border-red-200 rounded-2xl p-4 max-h-48 overflow-y-auto">
                    <div className="flex items-start gap-2 mb-2">
                      <AlertCircle size={14} className="text-red-600 mt-0.5 shrink-0" />
                      <p className="text-[11px] font-black text-red-700 uppercase tracking-widest">
                        Blocked — {deleteBlockers.length} active item{deleteBlockers.length === 1 ? '' : 's'}
                      </p>
                    </div>
                    <p className="text-[11px] text-red-700 mb-3 leading-relaxed">
                      Reassign or close these first, or use <strong>Deactivate</strong> instead to disable login while preserving history.
                    </p>
                    <ul className="space-y-1.5">
                      {deleteBlockers.slice(0, 8).map((b: any, i: number) => (
                        <li key={i} className="text-[11px] text-slate-700 leading-snug">
                          {b.type === 'project_member' && (
                            <>
                              <span className="font-black text-slate-900">{b.project_name}</span>
                              <span className="text-slate-500"> — active project ({b.role || 'member'})</span>
                            </>
                          )}
                          {b.type === 'lead_owner' && (
                            <>
                              <span className="font-black text-slate-900">{b.title}</span>
                              <span className="text-slate-500"> — open BD lead ({b.stage})</span>
                            </>
                          )}
                          {b.type === 'task_assignee' && (
                            <>
                              <span className="font-black text-slate-900">{b.title}</span>
                              <span className="text-slate-500"> — open task on {b.project_name || 'a project'}</span>
                            </>
                          )}
                        </li>
                      ))}
                      {deleteBlockers.length > 8 && (
                        <li className="text-[10px] text-slate-500 italic pt-1">
                          + {deleteBlockers.length - 8} more…
                        </li>
                      )}
                    </ul>
                  </div>
                ) : deleteBlockers ? (
                  <div className="flex items-center justify-center gap-2 text-[11px] font-bold text-emerald-600">
                    <CheckCircle2 size={12} /> No active assignments — safe to delete.
                  </div>
                ) : null}

                {deleteBlockers && deleteBlockers.length > 0 && (
                  <div className="mt-4 text-left bg-slate-50 border border-slate-200 rounded-2xl p-4">
                    <p className="text-[11px] font-black text-slate-700 uppercase tracking-widest mb-2">
                      Transfer all to
                    </p>
                    <p className="text-[11px] text-slate-500 mb-3 leading-relaxed">
                      Pick a replacement and we'll reassign every active project, task, and lead — original ownership is captured in the audit log.
                    </p>
                    <div className="flex gap-2">
                      <select
                        value={transferTargetId}
                        onChange={e => setTransferTargetId(e.target.value)}
                        disabled={transferring}
                        className="flex-1 h-10 px-3 rounded-xl border border-slate-200 bg-white text-xs font-bold text-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-500/30"
                      >
                        <option value="">Select an employee…</option>
                        {transferTargets.map((e: any) => (
                          <option key={e.id} value={e.id}>
                            {e.user?.full_name || '?'} — {e.designation || e.department || 'Employee'}
                          </option>
                        ))}
                      </select>
                      <Button
                        className="h-10 px-4 rounded-xl bg-blue-600 hover:bg-blue-700 text-white font-bold text-xs"
                        onClick={handleTransferWork}
                        disabled={!transferTargetId || transferring}
                      >
                        {transferring ? <Loader2 size={14} className="animate-spin" /> : 'Transfer'}
                      </Button>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Buttons */}
          <div className="px-6 pb-6 grid grid-cols-2 gap-3">
            <Button
              variant="outline"
              className="h-11 rounded-xl font-bold text-xs"
              onClick={() => setConfirmAction(null)}
              disabled={confirmLoading}
            >
              Cancel
            </Button>
            {confirmAction?.type === 'delete' && deleteBlockers && deleteBlockers.length > 0 ? (
              <Button
                className="h-11 rounded-xl font-bold text-xs text-white bg-amber-600 hover:bg-amber-700"
                onClick={() => {
                  if (confirmAction?.emp) {
                    setConfirmAction({ type: 'deactivate', emp: confirmAction.emp });
                  }
                }}
                disabled={confirmLoading}
              >
                Deactivate Instead
              </Button>
            ) : (
              <Button
                className={cn(
                  "h-11 rounded-xl font-bold text-xs text-white",
                  confirmAction?.type === 'delete' ? "bg-red-600 hover:bg-red-700" :
                  confirmAction?.type === 'deactivate' ? "bg-red-600 hover:bg-red-700" :
                  "bg-green-600 hover:bg-green-700"
                )}
                onClick={handleConfirmAction}
                disabled={confirmLoading || (confirmAction?.type === 'delete' && (loadingBlockers || deleteBlockers === null))}
              >
                {confirmLoading ? <Loader2 className="w-4 h-4 animate-spin" /> :
                  confirmAction?.type === 'delete' ? 'Yes, Delete' :
                  confirmAction?.type === 'deactivate' ? 'Yes, Deactivate' : 'Yes, Reactivate'}
              </Button>
            )}
          </div>
        </DialogContent>
      </Dialog>

      {assignShiftEmp && (
        <AssignShiftDialog
          open={!!assignShiftEmp}
          onClose={() => setAssignShiftEmp(null)}
          employeeId={assignShiftEmp.user_id || assignShiftEmp.user?.id}
          employeeName={assignShiftEmp.user?.full_name}
          onAssigned={() => {/* no-op: assignments not shown in this table */}}
        />
      )}
    </div>
  );
};

// ─── Exit Pipeline Panel ──────────────────────────────────────
const EXIT_STATUS_STYLES: Record<string, { bg: string; text: string; label: string }> = {
  submitted:      { bg: 'bg-amber-100',  text: 'text-amber-800',  label: 'Submitted' },
  accepted:       { bg: 'bg-blue-100',   text: 'text-blue-800',   label: 'Accepted' },
  notice_period:  { bg: 'bg-orange-100', text: 'text-orange-800', label: 'Notice Period' },
  exit_interview: { bg: 'bg-purple-100', text: 'text-purple-800', label: 'Exit Interview' },
  clearance:      { bg: 'bg-cyan-100',   text: 'text-cyan-800',   label: 'Clearance' },
  released:       { bg: 'bg-green-100',  text: 'text-green-800',  label: 'Released' },
  withdrawn:      { bg: 'bg-slate-100',  text: 'text-slate-600',  label: 'Withdrawn' },
  rejected:       { bg: 'bg-red-100',    text: 'text-red-800',    label: 'Rejected' },
};

const ACTIVE_STATUSES = ['submitted', 'accepted', 'notice_period', 'exit_interview', 'clearance'];

const ExitPipelinePanel = ({
  resignations,
  loading,
  onRefresh,
  onViewEmployee,
}: {
  resignations: any[];
  loading: boolean;
  onRefresh: () => void;
  onViewEmployee: (empId: number) => void;
}) => {
  const [statusFilter, setStatusFilter] = useState('active');

  const filtered = resignations.filter(r => {
    if (statusFilter === 'active') return ACTIVE_STATUSES.includes(r.status);
    if (statusFilter === 'closed') return ['released', 'withdrawn', 'rejected'].includes(r.status);
    return true;
  });

  const counts = {
    active: resignations.filter(r => ACTIVE_STATUSES.includes(r.status)).length,
    notice_period: resignations.filter(r => r.status === 'notice_period').length,
    overdue: resignations.filter(r =>
      r.status === 'notice_period' && r.last_working_day && new Date(r.last_working_day) < new Date(new Date().toDateString())
    ).length,
  };

  return (
    <div className="space-y-6 animate-in fade-in">
      {/* Summary cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="p-5 bg-white border border-slate-200 rounded-2xl">
          <p className="text-2xl font-black text-[#0F172A]">{resignations.length}</p>
          <p className="text-[9px] font-black text-slate-400 uppercase tracking-widest mt-1">Total</p>
        </div>
        <div className="p-5 bg-amber-50 border border-amber-100 rounded-2xl">
          <p className="text-2xl font-black text-amber-600">{counts.active}</p>
          <p className="text-[9px] font-black text-amber-400 uppercase tracking-widest mt-1">Active</p>
        </div>
        <div className="p-5 bg-orange-50 border border-orange-100 rounded-2xl">
          <p className="text-2xl font-black text-orange-600">{counts.notice_period}</p>
          <p className="text-[9px] font-black text-orange-400 uppercase tracking-widest mt-1">Serving Notice</p>
        </div>
        <div className={cn("p-5 rounded-2xl border", counts.overdue > 0 ? "bg-red-50 border-red-200" : "bg-slate-50 border-slate-100")}>
          <p className={cn("text-2xl font-black", counts.overdue > 0 ? "text-red-600" : "text-slate-300")}>{counts.overdue}</p>
          <p className={cn("text-[9px] font-black uppercase tracking-widest mt-1", counts.overdue > 0 ? "text-red-400" : "text-slate-300")}>Notice Overdue</p>
        </div>
      </div>

      <Card className="border-slate-200 overflow-hidden shadow-sm">
        {/* Filter + refresh bar */}
        <div className="p-5 border-b border-slate-100 bg-slate-50/50 flex items-center justify-between gap-4">
          <div className="flex gap-1 bg-white border border-slate-200 p-1 rounded-xl">
            {[['active', 'Active'], ['closed', 'Closed'], ['all', 'All']].map(([val, label]) => (
              <button
                key={val}
                onClick={() => setStatusFilter(val)}
                className={cn(
                  "h-8 px-4 rounded-lg font-black text-[9px] uppercase tracking-widest transition-all",
                  statusFilter === val ? "bg-slate-900 text-white" : "text-slate-400 hover:text-slate-600"
                )}
              >
                {label}
              </button>
            ))}
          </div>
          <Button
            variant="outline"
            className="h-9 px-4 font-black uppercase text-[9px] tracking-widest border-slate-200"
            onClick={onRefresh}
          >
            Refresh
          </Button>
        </div>

        <div className="overflow-x-auto">
          {loading ? (
            <div className="p-16 flex justify-center">
              <Loader2 size={28} className="text-blue-600 animate-spin" />
            </div>
          ) : filtered.length === 0 ? (
            <div className="p-16 flex flex-col items-center gap-3">
              <CheckCircle2 size={36} className="text-slate-200" />
              <p className="text-sm font-black text-slate-400 uppercase tracking-widest">No resignations found</p>
            </div>
          ) : (
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="bg-white border-b border-slate-100">
                  <th className="px-6 py-4 text-[9px] font-black text-slate-400 uppercase tracking-widest">Employee</th>
                  <th className="px-6 py-4 text-[9px] font-black text-slate-400 uppercase tracking-widest">Department</th>
                  <th className="px-6 py-4 text-[9px] font-black text-slate-400 uppercase tracking-widest">Resigned On</th>
                  <th className="px-6 py-4 text-[9px] font-black text-slate-400 uppercase tracking-widest">Last Working Day</th>
                  <th className="px-6 py-4 text-[9px] font-black text-slate-400 uppercase tracking-widest text-center">Notice Days</th>
                  <th className="px-6 py-4 text-[9px] font-black text-slate-400 uppercase tracking-widest text-center">Days Left</th>
                  <th className="px-6 py-4 text-[9px] font-black text-slate-400 uppercase tracking-widest">Status</th>
                  <th className="px-6 py-4 text-[9px] font-black text-slate-400 uppercase tracking-widest text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {filtered.map((r: any) => {
                  const lwd = r.last_working_day ? new Date(r.last_working_day) : null;
                  const today = new Date(new Date().toDateString());
                  const daysLeft = lwd ? Math.ceil((lwd.getTime() - today.getTime()) / 86400000) : null;
                  const isOverdue = r.status === 'notice_period' && daysLeft !== null && daysLeft < 0;
                  const style = EXIT_STATUS_STYLES[r.status] || { bg: 'bg-slate-100', text: 'text-slate-600', label: r.status };
                  return (
                    <tr key={r.id} className={cn("transition-colors", isOverdue ? "bg-red-50/30 hover:bg-red-50/50" : "hover:bg-slate-50/60")}>
                      <td className="px-6 py-4">
                        <div className="flex items-center gap-3">
                          <div className={cn(
                            "w-9 h-9 rounded-xl flex items-center justify-center font-black text-xs shrink-0",
                            isOverdue ? "bg-red-100 text-red-600" : "bg-slate-100 text-slate-500"
                          )}>
                            {r.employee_name?.charAt(0) || '?'}
                          </div>
                          <div>
                            <p className="text-sm font-black text-[#0F172A]">{r.employee_name}</p>
                            <p className="text-[9px] font-bold text-slate-400 uppercase">{r.employee_emp_id}</p>
                          </div>
                        </div>
                      </td>
                      <td className="px-6 py-4 text-xs font-bold text-slate-500">{r.department || '—'}</td>
                      <td className="px-6 py-4 text-xs font-bold text-slate-500">
                        {r.resignation_date ? new Date(r.resignation_date).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' }) : '—'}
                      </td>
                      <td className="px-6 py-4 text-xs font-bold text-slate-500">
                        {lwd ? lwd.toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' }) : '—'}
                      </td>
                      <td className="px-6 py-4 text-center">
                        <span className="text-sm font-black text-slate-600">{r.notice_period_days ?? '—'}</span>
                      </td>
                      <td className="px-6 py-4 text-center">
                        {daysLeft === null ? <span className="text-slate-300 font-black">—</span>
                          : isOverdue ? (
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-red-100 text-red-600 rounded-lg text-[9px] font-black uppercase">
                              <AlertCircle size={9} /> {Math.abs(daysLeft)}d overdue
                            </span>
                          ) : (
                            <span className={cn("text-sm font-black", daysLeft <= 5 ? "text-amber-600" : "text-slate-600")}>{daysLeft}d</span>
                          )
                        }
                      </td>
                      <td className="px-6 py-4">
                        <span className={cn("px-2.5 py-1 rounded-lg text-[9px] font-black uppercase tracking-widest", style.bg, style.text)}>
                          {style.label}
                        </span>
                      </td>
                      <td className="px-6 py-4 text-right">
                        <Button
                          size="sm"
                          variant="outline"
                          className="h-8 px-4 font-black uppercase text-[9px] tracking-widest border-slate-200 hover:bg-slate-900 hover:text-white transition-all"
                          onClick={() => onViewEmployee(r.employee_id)}
                        >
                          View Exit Tab
                        </Button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </Card>
    </div>
  );
};

const EmployeeDetails = ({
  emp,
  onBack,
  userRole = 'employee',
  onImpersonate,
  onResetPassword,
  onDeactivate,
  onReactivate,
  onDelete,
  onUpdated,
}: {
  emp: any,
  onBack: () => void,
  userRole?: UserRole,
  onImpersonate?: (userId: number) => void,
  onResetPassword?: (emp: any) => void,
  onDeactivate?: (emp: any) => void,
  onReactivate?: (emp: any) => void,
  onDelete?: (emp: any) => void,
  onUpdated?: (updated: any) => void,
}) => {
  const [activeTab, setActiveTab] = useState(emp._initialTab || 'overview');
  const isManagement =
    userRole === 'hr' ||
    userRole === 'admin' ||
    userRole === 'super admin' ||
    userRole === 'ceo';
  const isSuperAdmin = userRole === 'super admin';

  const [managerCandidates, setManagerCandidates] = useState<any[]>([]);
  const [savingField, setSavingField] = useState<string | null>(null);

  useEffect(() => {
    if (!isManagement) return;
    let cancelled = false;
    client.get(ENDPOINTS.HR.EMPLOYEES, { params: { size: 200, status: 'active' } })
      .then(res => {
        if (cancelled) return;
        const items = Array.isArray(res.data?.items) ? res.data.items : [];
        setManagerCandidates(items.filter((m: any) => m.user?.id && m.user.id !== emp.user?.id));
      })
      .catch(() => { /* picker just shows empty */ });
    return () => { cancelled = true; };
  }, [isManagement, emp.user?.id]);

  const patchEmployeeField = async (field: string, value: any, label: string) => {
    setSavingField(field);
    try {
      const res = await client.patch(ENDPOINTS.HR.EMPLOYEE_DETAIL(emp.id), { [field]: value });
      toast.success(`${label} updated`);
      onUpdated?.(res.data);
    } catch (err: any) {
      toast.error(errMsg(err, `Failed to update ${label.toLowerCase()}`));
    } finally {
      setSavingField(null);
    }
  };

  return (
    <div className="p-8 max-w-[1400px] mx-auto animate-in slide-in-from-right duration-500 pb-20">
      <div className="flex items-center justify-between mb-8 gap-4">
        <div className="flex items-center gap-4">
          <button onClick={onBack} className="p-3 bg-white border border-slate-200 rounded-2xl hover:bg-slate-50 transition-colors shadow-sm">
            <ArrowLeft size={20} className="text-slate-600" />
          </button>
          <div>
            <h2 className="text-3xl font-black text-[#0F172A] tracking-tighter uppercase">{emp.user.full_name}</h2>
            <div className="flex items-center gap-3 mt-1">
               <Badge variant="info" className="text-[9px] font-black uppercase tracking-widest">{emp.designation}</Badge>
               <span className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Asset ID: {emp.employee_id}</span>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {isManagement && (
            <>
              <Button
                className="rounded-2xl bg-amber-600 hover:bg-amber-700 text-white font-black uppercase tracking-widest text-xs px-6 h-14 shadow-lg shadow-amber-600/20"
                onClick={() => onResetPassword?.(emp)}
              >
                <KeyRound className="w-4 h-4 mr-2" />
                Reset Password
              </Button>
              {emp.status === 'active' ? (
                <Button
                  className="rounded-2xl bg-red-600 hover:bg-red-700 text-white font-black uppercase tracking-widest text-xs px-6 h-14 shadow-lg shadow-red-600/20"
                  onClick={() => onDeactivate?.(emp)}
                >
                  <ShieldX className="w-4 h-4 mr-2" />
                  Deactivate
                </Button>
              ) : (
                <Button
                  className="rounded-2xl bg-green-600 hover:bg-green-700 text-white font-black uppercase tracking-widest text-xs px-6 h-14 shadow-lg shadow-green-600/20"
                  onClick={() => onReactivate?.(emp)}
                >
                  <ShieldCheck className="w-4 h-4 mr-2" />
                  Reactivate
                </Button>
              )}
              <Button
                className="rounded-2xl bg-red-600 hover:bg-red-700 text-white font-black uppercase tracking-widest text-xs px-6 h-14 shadow-lg shadow-red-600/20"
                onClick={() => onDelete?.(emp)}
              >
                <Trash2 className="w-4 h-4 mr-2" />
                Delete
              </Button>
            </>
          )}
          {isSuperAdmin && (
            <Button
              className="rounded-2xl bg-amber-600 hover:bg-amber-700 text-white font-black uppercase tracking-widest text-xs px-6 h-14 shadow-lg shadow-amber-600/20"
              onClick={() => onImpersonate?.(emp.user_id || emp.user.id)}
            >
              <UserCheck className="w-4 h-4 mr-2" />
              Impersonate Identity
            </Button>
          )}
        </div>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-8">
        <TabsList className="bg-slate-100 p-1.5 rounded-2xl h-14 w-full md:w-auto border border-slate-200 flex flex-wrap lg:flex-nowrap">
          <TabsTrigger value="overview" className="rounded-xl px-6 font-black text-[10px] uppercase tracking-widest data-[state=active]:bg-white data-[state=active]:shadow-md h-full">1. Details</TabsTrigger>
          {isManagement && (
            <>
              <TabsTrigger value="compensation" className="rounded-xl px-6 font-black text-[10px] uppercase tracking-widest data-[state=active]:bg-white data-[state=active]:shadow-md h-full">2. Compensation</TabsTrigger>
              <TabsTrigger value="documents" className="rounded-xl px-6 font-black text-[10px] uppercase tracking-widest data-[state=active]:bg-white data-[state=active]:shadow-md h-full">3. Documents</TabsTrigger>
              <TabsTrigger value="assets" className="rounded-xl px-6 font-black text-[10px] uppercase tracking-widest data-[state=active]:bg-white data-[state=active]:shadow-md h-full">4. Assets</TabsTrigger>
              <TabsTrigger value="exit" className="rounded-xl px-6 font-black text-[10px] uppercase tracking-widest data-[state=active]:bg-white data-[state=active]:shadow-md h-full">5. Exit Management</TabsTrigger>
            </>
          )}
        </TabsList>

        <TabsContent value="overview">
           <div className="space-y-8">
           <Card className="p-10 border-slate-200 shadow-sm space-y-12 bg-white">
              <section className="grid grid-cols-1 md:grid-cols-3 gap-10">
                 <div className="space-y-6">
                    <h4 className="text-[10px] font-black text-slate-400 uppercase tracking-[0.2em] flex items-center gap-2"><Users size={12}/> Personal Info</h4>
                    <InfoItem label="Legal Name" value={emp.user.full_name} />
                    <InfoItem label="Date of Joining" value={new Date(emp.date_of_joining).toLocaleDateString()} />
                    <InfoItem label="Status" value={emp.status} />
                    {isManagement ? (
                      <div className="space-y-1.5">
                        <p className="text-[9px] font-black text-slate-400 uppercase tracking-widest">Employment Type</p>
                        <Select
                          value={emp.employment_type || 'permanent'}
                          onValueChange={(v) => patchEmployeeField('employment_type', v, 'Employment type')}
                          disabled={savingField === 'employment_type'}
                        >
                          <SelectTrigger className="h-10 font-bold rounded-xl bg-white border-slate-200 text-sm capitalize">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="permanent">Permanent</SelectItem>
                            <SelectItem value="contractual">Contractual</SelectItem>
                            <SelectItem value="advisor">Advisor</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                    ) : (
                      <InfoItem label="Employment Type" value={emp.employment_type || 'permanent'} />
                    )}
                    <InfoItem label="Notice Period" value={`${emp.notice_period_days ?? 30} days`} />
                 </div>
                 <div className="space-y-6">
                    <h4 className="text-[10px] font-black text-slate-400 uppercase tracking-[0.2em] flex items-center gap-2"><Mail size={12}/> Contact Info</h4>
                    <InfoItem label="Corporate Email" value={emp.user.email} />
                    <InfoItem label="Primary Contact" value={emp.phone || emp.user?.phone || '—'} />
                    <InfoItem label="Work Location" value={emp.location || emp.user?.location || '—'} />
                 </div>
                 <div className="space-y-6">
                    <h4 className="text-[10px] font-black text-slate-400 uppercase tracking-[0.2em] flex items-center gap-2"><Briefcase size={12}/> Assignment</h4>
                    <InfoItem label="Department" value={emp.department} />
                    <InfoItem label="Designation" value={emp.designation} />
                    {isManagement ? (
                      <div className="space-y-1.5">
                        <p className="text-[9px] font-black text-slate-400 uppercase tracking-widest">Reporting Manager</p>
                        <Select
                          value={emp.user?.manager?.id ? String(emp.user.manager.id) : 'none'}
                          onValueChange={(v) => patchEmployeeField('manager_id', v === 'none' ? null : parseInt(v), 'Reporting manager')}
                          disabled={savingField === 'manager_id'}
                        >
                          <SelectTrigger className="h-10 font-bold rounded-xl bg-white border-slate-200 text-sm">
                            <SelectValue placeholder="Select manager" />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="none">No manager</SelectItem>
                            {managerCandidates.map((m: any) => (
                              <SelectItem key={m.user.id} value={String(m.user.id)}>
                                {m.user.full_name} {m.designation ? `· ${m.designation}` : ''}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                    ) : (
                      <InfoItem label="Reporting Manager" value={emp.user.manager?.full_name || "—"} />
                    )}
                 </div>
              </section>
           </Card>

           <ConfirmationCard emp={emp} onConfirmed={() => {}} />

           <Card className="p-10 border-slate-200 shadow-sm bg-white">
              <h4 className="text-[10px] font-black text-slate-400 uppercase tracking-[0.2em] flex items-center gap-2 mb-4"><FileText size={12}/> Key Result Areas (KRA)</h4>
              {emp.kra ? (
                 <div className="bg-slate-50 rounded-2xl border border-slate-100 p-6">
                    <p className="text-sm text-slate-700 leading-relaxed whitespace-pre-wrap">{emp.kra}</p>
                 </div>
              ) : (
                 <div className="bg-slate-50 rounded-2xl border border-dashed border-slate-200 p-8 text-center">
                    <p className="text-sm font-bold text-slate-400">No KRA defined yet</p>
                    <p className="text-[10px] text-slate-400 mt-1 uppercase tracking-widest">Employee can update this from their profile</p>
                 </div>
              )}
           </Card>
           </div>
        </TabsContent>

        <TabsContent value="compensation">
           <CompensationTab emp={emp} />
        </TabsContent>

        <TabsContent value="documents">
           <DocumentsTab emp={emp} />
        </TabsContent>
        <TabsContent value="assets">
           <AssetsTab emp={emp} />
        </TabsContent>
        <TabsContent value="exit">
           <ExitManagementTab emp={emp} />
        </TabsContent>
      </Tabs>
    </div>
  );
};

// --- SUB-COMPONENTS ---

const PAGE_SIZE_OPTIONS = [10, 25, 50, 100];

function buildPageRange(current: number, totalPages: number): (number | 'ellipsis')[] {
  if (totalPages <= 7) {
    return Array.from({ length: totalPages }, (_, i) => i + 1);
  }
  const pages: (number | 'ellipsis')[] = [1];
  const start = Math.max(2, current - 1);
  const end = Math.min(totalPages - 1, current + 1);
  if (start > 2) pages.push('ellipsis');
  for (let p = start; p <= end; p++) pages.push(p);
  if (end < totalPages - 1) pages.push('ellipsis');
  pages.push(totalPages);
  return pages;
}

const PaginationFooter = ({
  page,
  pageSize,
  total,
  visibleCount,
  onPageChange,
  onPageSizeChange,
  disabled,
}: {
  page: number;
  pageSize: number;
  total: number;
  visibleCount: number;
  onPageChange: (p: number) => void;
  onPageSizeChange: (s: number) => void;
  disabled?: boolean;
}) => {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const safePage = Math.min(page, totalPages);
  const rangeStart = total === 0 ? 0 : (safePage - 1) * pageSize + 1;
  const rangeEnd = total === 0 ? 0 : Math.min(total, (safePage - 1) * pageSize + visibleCount);
  const pages = buildPageRange(safePage, totalPages);

  return (
    <div className="p-4 md:p-6 border-t border-slate-100 flex flex-col md:flex-row md:items-center md:justify-between gap-4 bg-slate-50/50">
      <div className="flex flex-wrap items-center gap-4 text-[10px] font-black text-slate-500 uppercase tracking-widest">
        <span aria-live="polite">
          {total === 0 ? 'No results' : `Showing ${rangeStart}–${rangeEnd} of ${total}`}
        </span>
        <label className="flex items-center gap-2 normal-case tracking-normal">
          <span className="text-slate-400">Rows:</span>
          <select
            value={pageSize}
            onChange={(e) => onPageSizeChange(Number(e.target.value))}
            disabled={disabled}
            aria-label="Rows per page"
            className="h-8 px-2 rounded-lg border border-slate-200 bg-white text-xs font-bold text-slate-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600/30"
          >
            {PAGE_SIZE_OPTIONS.map((opt) => (
              <option key={opt} value={opt}>{opt}</option>
            ))}
          </select>
        </label>
      </div>

      <nav aria-label="Pagination" className="flex items-center gap-1">
        <Button
          variant="outline"
          size="sm"
          className="h-10 w-10 p-0 rounded-xl"
          disabled={disabled || safePage === 1}
          onClick={() => onPageChange(1)}
          aria-label="First page"
        >
          <ChevronLeft size={14} className="-mr-2" />
          <ChevronLeft size={14} />
        </Button>
        <Button
          variant="outline"
          size="sm"
          className="h-10 w-10 p-0 rounded-xl"
          disabled={disabled || safePage === 1}
          onClick={() => onPageChange(safePage - 1)}
          aria-label="Previous page"
        >
          <ChevronLeft size={16} />
        </Button>

        <div className="flex items-center gap-1 px-1">
          {pages.map((p, idx) =>
            p === 'ellipsis' ? (
              <span key={`ellipsis-${idx}`} aria-hidden="true" className="px-2 text-slate-400 text-xs font-bold select-none">
                …
              </span>
            ) : (
              <button
                key={p}
                type="button"
                onClick={() => onPageChange(p)}
                disabled={disabled}
                aria-label={`Page ${p}`}
                aria-current={p === safePage ? 'page' : undefined}
                className={cn(
                  "h-10 min-w-[40px] px-3 rounded-xl text-xs font-black transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600/30",
                  p === safePage
                    ? "bg-blue-600 text-white shadow-sm shadow-blue-600/20"
                    : "bg-white border border-slate-200 text-slate-600 hover:bg-slate-50 hover:text-slate-900"
                )}
              >
                {p}
              </button>
            )
          )}
        </div>

        <Button
          variant="outline"
          size="sm"
          className="h-10 w-10 p-0 rounded-xl"
          disabled={disabled || safePage >= totalPages}
          onClick={() => onPageChange(safePage + 1)}
          aria-label="Next page"
        >
          <ChevronRight size={16} />
        </Button>
        <Button
          variant="outline"
          size="sm"
          className="h-10 w-10 p-0 rounded-xl"
          disabled={disabled || safePage >= totalPages}
          onClick={() => onPageChange(totalPages)}
          aria-label="Last page"
        >
          <ChevronRight size={14} className="-mr-2" />
          <ChevronRight size={14} />
        </Button>
      </nav>
    </div>
  );
};

const InfoItem = ({ label, value }: { label: string, value: string }) => (
  <div className="space-y-1.5">
    <label className="text-[9px] font-black text-slate-400 uppercase tracking-widest">{label}</label>
    <p className="text-sm font-black text-[#0F172A]">{value}</p>
  </div>
);

const formatINR = (amount: number) =>
  new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(amount);

const getProfessionalTax = (totalFixed: number): number => {
  if (totalFixed <= 10000) return 0;
  if (totalFixed <= 15000) return 110;
  if (totalFixed <= 25000) return 130;
  if (totalFixed <= 40000) return 150;
  return 200;
};

const CompensationTab = ({ emp }: { emp: any }) => {
  if (!emp.salary) {
    return (
       <Card className="p-12 border-2 border-dashed border-slate-200 flex flex-col items-center justify-center bg-slate-50/50">
          <div className="w-16 h-16 bg-white rounded-2xl flex items-center justify-center shadow-sm border border-slate-100 mb-6 text-slate-300">
             <DollarSign size={32} />
          </div>
          <h4 className="text-lg font-black text-slate-400 uppercase tracking-tight">No Compensation Data Accessible</h4>
          <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mt-2">You may not have the required "hr payroll view" permission</p>
       </Card>
    );
  }

  const basic = emp.salary;
  const ca = emp.conveyance_allowance != null ? emp.conveyance_allowance : Math.round(basic * 0.30);
  const hra = emp.hra != null ? emp.hra : Math.round(basic * 0.50);
  const other = emp.other_allowance != null ? emp.other_allowance : Math.round(basic * 0.20);
  const esicApplicable = !!emp.esic_applicable;

  const totalFixed = basic + ca + hra + other;

  // Employee deductions
  const employeeESI = esicApplicable ? Math.ceil(totalFixed * 0.0075) : 0;
  const employeePF = Math.ceil(basic * 0.12);
  const professionalTax = getProfessionalTax(totalFixed);
  const totalDeductions = employeeESI + employeePF + professionalTax;
  const netSalary = totalFixed - totalDeductions;

  // Employer contributions
  const employerESIC = esicApplicable && employeeESI > 0 ? Math.ceil(employeeESI / 0.75 * 3.25) : 0;
  const employerPF = Math.ceil(employeePF / 12 * 13);
  const annualCTC = (netSalary + employerESIC + employerPF) * 12;

  return (
    <div className="space-y-8 animate-in fade-in">
       <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Earnings Card */}
          <Card className="p-10 border-slate-200 shadow-sm space-y-6 bg-white">
             <h5 className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Earnings</h5>
             <div className="space-y-4">
                <SalaryRow label="Basic Salary" value={formatINR(basic)} />
                <SalaryRow label="Conveyance Allowance" value={formatINR(ca)} />
                <SalaryRow label="House Rent Allowance" value={formatINR(hra)} />
                <SalaryRow label="Other Allowance" value={formatINR(other)} />
                <div className="h-px bg-slate-100 my-2" />
                <SalaryRow label="Total Fixed Earnings" value={formatINR(totalFixed)} bold />
             </div>
          </Card>

          {/* Deductions Card */}
          <Card className="p-10 border-slate-200 shadow-sm space-y-6 bg-white">
             <h5 className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Deductions</h5>
             <div className="space-y-4">
                {esicApplicable ? (
                  <SalaryRow label="Employee ESI @ 0.75%" value={`-${formatINR(employeeESI)}`} color="text-red-500" />
                ) : (
                  <SalaryRow label="Employee ESI" value="Not Applicable" color="text-slate-400" />
                )}
                <SalaryRow label="Employee PF @ 12%" value={`-${formatINR(employeePF)}`} color="text-red-500" />
                <SalaryRow label="Professional Tax" value={`-${formatINR(professionalTax)}`} color="text-red-500" />
                <div className="h-px bg-slate-100 my-2" />
                <SalaryRow label="Total Deductions" value={`-${formatINR(totalDeductions)}`} bold color="text-red-600" />
             </div>
          </Card>

          {/* Summary Card */}
          <Card className="p-8 border-slate-200 shadow-sm flex flex-col justify-center bg-slate-900 text-white">
             <p className="text-[10px] font-black uppercase tracking-[0.2em] opacity-60">Net Monthly Salary</p>
             <h3 className="text-4xl font-black tracking-tighter mt-2">{formatINR(netSalary)}</h3>
             <div className="mt-6 pt-6 border-t border-white/10">
                <p className="text-[10px] font-black uppercase tracking-[0.2em] opacity-60">Annual CTC</p>
                <h4 className="text-2xl font-black tracking-tighter mt-1">{formatINR(annualCTC)}</h4>
             </div>
             <div className="mt-6 pt-6 border-t border-white/10 space-y-3">
                <p className="text-[9px] font-black uppercase tracking-widest opacity-40">Employer Contributions</p>
                <div className="flex justify-between items-center text-[10px] font-black uppercase">
                   <span className="opacity-60">Employer ESIC @ 3.25%</span>
                   <span className="text-[9px]">{esicApplicable ? formatINR(employerESIC) : 'N/A'}</span>
                </div>
                <div className="flex justify-between items-center text-[10px] font-black uppercase">
                   <span className="opacity-60">Employer PF @ 13%</span>
                   <span className="text-[9px]">{formatINR(employerPF)}</span>
                </div>
             </div>
             <div className="mt-6 pt-6 border-t border-white/10 space-y-3">
                <div className="flex justify-between items-center text-[10px] font-black uppercase">
                   <span className="opacity-60">Bank Account</span>
                   <span className="text-[9px]">{emp.bank_account || "Not Set"}</span>
                </div>
                <div className="flex justify-between items-center text-[10px] font-black uppercase">
                   <span className="opacity-60">PAN Number</span>
                   <span className="text-[9px]">{emp.pan_number || "Not Set"}</span>
                </div>
             </div>
          </Card>
       </div>
    </div>
  );
};

// ─── Employee Confirmation ───────────────────────────────────
const ConfirmationCard = ({ emp, onConfirmed }: { emp: any; onConfirmed: () => void }) => {
  const [confirmDate, setConfirmDate] = useState<string>(
    emp.confirmation_date || new Date().toISOString().split('T')[0]
  );
  const [probationDate, setProbationDate] = useState<string>(emp.probation_end_date || '');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const isConfirmed = !!emp.confirmation_date;

  const handleConfirm = async () => {
    setIsSubmitting(true);
    try {
      await client.post(ENDPOINTS.HR.EMPLOYEE_CONFIRM(emp.id), {
        confirmation_date: confirmDate,
        probation_end_date: probationDate || null,
      });
      toast.success('Employee confirmed successfully');
      onConfirmed();
    } catch (err: any) {
      toast.error(errMsg(err, 'Confirmation failed'));
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Card className="p-10 border-slate-200 shadow-sm bg-white">
      <div className="flex items-center justify-between mb-6">
        <h4 className="text-[10px] font-black text-slate-400 uppercase tracking-[0.2em] flex items-center gap-2">
          <UserCheck size={12} /> Employment Confirmation
        </h4>
        {isConfirmed && (
          <span className="text-[9px] font-black uppercase tracking-widest px-3 py-1 rounded-full bg-green-50 text-green-700 border border-green-200">
            Confirmed
          </span>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 items-end">
        <div className="space-y-2">
          <label className="text-[9px] font-black text-slate-400 uppercase tracking-widest">
            Probation End Date
          </label>
          <input
            type="date"
            value={probationDate}
            onChange={e => setProbationDate(e.target.value)}
            className="w-full h-11 px-3 rounded-xl border border-slate-200 bg-white text-sm font-bold text-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
        <div className="space-y-2">
          <label className="text-[9px] font-black text-slate-400 uppercase tracking-widest">
            Confirmation Date
          </label>
          <input
            type="date"
            value={confirmDate}
            onChange={e => setConfirmDate(e.target.value)}
            className="w-full h-11 px-3 rounded-xl border border-slate-200 bg-white text-sm font-bold text-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
        <div>
          <Button
            className="h-11 px-6 font-black uppercase text-[9px] tracking-widest bg-green-600 hover:bg-green-700 shadow-lg shadow-green-600/20 w-full"
            onClick={handleConfirm}
            disabled={isSubmitting || !confirmDate}
          >
            {isSubmitting ? <><Loader2 size={14} className="animate-spin mr-2" />Confirming...</> : (isConfirmed ? 'Update Confirmation' : 'Confirm Employee')}
          </Button>
        </div>
      </div>

      {isConfirmed && (
        <p className="text-[10px] font-bold text-green-600 mt-4">
          Confirmed on {new Date(emp.confirmation_date).toLocaleDateString('en-IN', { day: 'numeric', month: 'long', year: 'numeric' })}
          {emp.probation_end_date ? ` · Probation ended ${new Date(emp.probation_end_date).toLocaleDateString('en-IN', { day: 'numeric', month: 'long', year: 'numeric' })}` : ''}
        </p>
      )}
    </Card>
  );
};

const DOC_TYPES = ['Legal', 'KYC', 'Education', 'Experience', 'Finance', 'Other'] as const;

const DocumentsTab = ({ emp }: { emp: any }) => {
  const [docs, setDocs] = useState<any[]>([]);
  const [requiredStatus, setRequiredStatus] = useState<any>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isUploading, setIsUploading] = useState(false);
  const [showUploadForm, setShowUploadForm] = useState(false);
  const [docType, setDocType] = useState<string>('Legal');
  const [docRemark, setDocRemark] = useState('');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [actioningId, setActioningId] = useState<number | null>(null);
  const [rejectDoc, setRejectDoc] = useState<any | null>(null);
  const [rejectReason, setRejectReason] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);

  const empId = emp?.id || emp?.employee_id_num;

  useEffect(() => {
    if (empId) fetchDocs();
  }, [empId]);

  const fetchDocs = async () => {
    setIsLoading(true);
    try {
      const [docsRes, statusRes] = await Promise.allSettled([
        client.get(ENDPOINTS.HR.EMPLOYEE_DOCUMENTS(empId)),
        client.get(ENDPOINTS.HR.EMPLOYEE_REQUIRED_STATUS(empId)),
      ]);
      if (docsRes.status === 'fulfilled') setDocs(docsRes.value.data || []);
      else setDocs([]);
      if (statusRes.status === 'fulfilled') setRequiredStatus(statusRes.value.data);
      else setRequiredStatus(null);
    } finally {
      setIsLoading(false);
    }
  };

  const handleVerify = async (doc: any) => {
    setActioningId(doc.id);
    try {
      await client.post(ENDPOINTS.HR.EMPLOYEE_DOCUMENT_VERIFY(empId, doc.id));
      toast.success('Document verified');
      fetchDocs();
    } catch (err: any) {
      toast.error(errMsg(err, 'Verification failed'));
    } finally {
      setActioningId(null);
    }
  };

  const handleReject = async () => {
    if (!rejectDoc) return;
    if (!rejectReason.trim()) { toast.error('Rejection reason is required'); return; }
    setActioningId(rejectDoc.id);
    try {
      await client.post(
        ENDPOINTS.HR.EMPLOYEE_DOCUMENT_REJECT(empId, rejectDoc.id),
        { reason: rejectReason.trim() },
      );
      toast.success('Document rejected');
      setRejectDoc(null);
      setRejectReason('');
      fetchDocs();
    } catch (err: any) {
      toast.error(errMsg(err, 'Rejection failed'));
    } finally {
      setActioningId(null);
    }
  };

  const handleUpload = async () => {
    if (!selectedFile) { toast.error('Please select a file'); return; }
    setIsUploading(true);
    try {
      const form = new FormData();
      form.append('file', selectedFile);
      form.append('doc_type', docType);
      form.append('remark', docRemark);
      await client.post(ENDPOINTS.HR.EMPLOYEE_DOCUMENT_UPLOAD(empId), form);
      toast.success('Document uploaded successfully');
      setShowUploadForm(false);
      setSelectedFile(null);
      setDocRemark('');
      setDocType('Legal');
      fetchDocs();
    } catch (err: any) {
      toast.error(errMsg(err, 'Upload failed'));
    } finally {
      setIsUploading(false);
    }
  };

  const handleDelete = async (docId: number, docName: string) => {
    if (!confirm(`Delete "${docName}"?`)) return;
    try {
      await client.delete(ENDPOINTS.HR.EMPLOYEE_DOCUMENT_DELETE(empId, docId));
      toast.success('Document removed');
      fetchDocs();
    } catch {
      toast.error('Failed to delete document');
    }
  };

  const handleDownload = async (doc: any) => {
    try {
      const url = ENDPOINTS.HR.EMPLOYEE_DOCUMENT_DOWNLOAD(empId, doc.id);
      const res = await client.get(url, { responseType: 'blob' });
      const blobUrl = window.URL.createObjectURL(res.data as Blob);
      const a = document.createElement('a');
      a.href = blobUrl;
      a.download = doc.original_filename || doc.name || 'document';
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => window.URL.revokeObjectURL(blobUrl), 60000);
    } catch (err: any) {
      toast.error(errMsg(err, 'Failed to download'));
    }
  };

  const totalRequired = requiredStatus?.total_required || 0;
  const verifiedSatisfied = requiredStatus?.verified_satisfied || 0;
  const uploadedSatisfied = requiredStatus?.satisfied || 0;
  const allVerified = totalRequired > 0 && verifiedSatisfied === totalRequired;
  const allUploaded = totalRequired > 0 && uploadedSatisfied === totalRequired;

  return (
    <div className="space-y-6 animate-in fade-in">
      {totalRequired > 0 && (
        <Card className={cn(
          'p-6 border shadow-sm',
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
                {allVerified ? <CheckCircle2 size={20} /> : <AlertCircle size={20} />}
              </div>
              <div>
                <p className="text-[10px] font-black uppercase tracking-widest text-slate-500">Required document compliance</p>
                <p className="text-sm font-black text-[#0F172A] mt-1">
                  {verifiedSatisfied} of {totalRequired} verified
                  {' • '}
                  <span className="text-slate-500 font-bold">{uploadedSatisfied} uploaded</span>
                </p>
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
                  {t.doc_type} · {t.is_verified ? 'verified' : t.is_uploaded ? 'pending verify' : 'missing'}
                </span>
              ))}
            </div>
          </div>
        </Card>
      )}

      <Card className="p-0 border-slate-200 shadow-sm overflow-hidden bg-white">
        <div className="p-8 border-b border-slate-100 flex items-center justify-between bg-slate-50/50">
           <div>
             <h4 className="text-xl font-black text-[#0F172A] tracking-tight uppercase">Artifact Repository</h4>
             <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mt-1">Joining Documents, KYC & Certificates</p>
           </div>
           <Button className="font-black h-11 px-6 uppercase text-[10px] tracking-widest bg-blue-600 shadow-lg shadow-blue-600/10" onClick={() => setShowUploadForm(!showUploadForm)}>
              <FileUp className="w-4 h-4 mr-2" /> Upload Artifact
           </Button>
        </div>

        {/* Upload Form */}
        {showUploadForm && (
          <div className="p-8 border-b border-slate-100 bg-blue-50/30 space-y-5 animate-in slide-in-from-top duration-300">
            <h5 className="text-[10px] font-black text-blue-600 uppercase tracking-[0.2em]">New Document Upload</h5>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
              <div className="space-y-2">
                <label className="text-[9px] font-black text-slate-400 uppercase tracking-widest">Document Type</label>
                <select
                  value={docType}
                  onChange={e => setDocType(e.target.value)}
                  className="w-full h-11 px-3 rounded-xl border border-slate-200 bg-white text-sm font-bold text-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  {DOC_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
                </select>
              </div>
              <div className="space-y-2">
                <label className="text-[9px] font-black text-slate-400 uppercase tracking-widest">Remarks</label>
                <Input placeholder="e.g. Aadhar card, scanned copy" className="h-11 font-bold" value={docRemark} onChange={e => setDocRemark(e.target.value)} />
              </div>
              <div className="space-y-2">
                <label className="text-[9px] font-black text-slate-400 uppercase tracking-widest">File</label>
                <div
                  className="h-11 flex items-center gap-3 px-4 rounded-xl border border-dashed border-slate-300 bg-white cursor-pointer hover:border-blue-400 transition-colors"
                  onClick={() => fileInputRef.current?.click()}
                >
                  <input ref={fileInputRef} type="file" className="hidden" onChange={e => setSelectedFile(e.target.files?.[0] || null)} />
                  {selectedFile ? (
                    <span className="text-xs font-black text-blue-600 truncate">{selectedFile.name}</span>
                  ) : (
                    <span className="text-xs font-bold text-slate-400">Click to select file…</span>
                  )}
                </div>
              </div>
            </div>
            <div className="flex justify-end gap-3">
              <Button variant="outline" className="h-10 px-6 font-black uppercase text-[9px] tracking-widest border-slate-200" onClick={() => { setShowUploadForm(false); setSelectedFile(null); }}>Cancel</Button>
              <Button className="h-10 px-8 font-black uppercase text-[9px] tracking-widest bg-blue-600 shadow-lg shadow-blue-600/10" onClick={handleUpload} disabled={isUploading || !selectedFile}>
                {isUploading ? <><Loader2 size={14} className="animate-spin mr-2" />Uploading...</> : 'Upload Document'}
              </Button>
            </div>
          </div>
        )}

        <div className="overflow-x-auto">
          {isLoading ? (
            <div className="p-12 flex justify-center">
              <Loader2 size={28} className="text-blue-600 animate-spin" />
            </div>
          ) : docs.length === 0 ? (
            <div className="p-16 flex flex-col items-center gap-4">
              <div className="w-16 h-16 bg-slate-50 rounded-2xl flex items-center justify-center border border-slate-100">
                <FileText size={28} className="text-slate-300" />
              </div>
              <p className="text-sm font-black text-slate-400 uppercase tracking-widest">No documents uploaded yet</p>
              <p className="text-xs font-bold text-slate-300">Click "Upload Artifact" to add joining documents, KYC, or certificates</p>
            </div>
          ) : (
            <table className="w-full text-left">
              <thead>
                <tr className="bg-white border-b border-slate-50">
                  <th className="px-8 py-5 text-[10px] font-black text-slate-400 uppercase tracking-widest">Description</th>
                  <th className="px-8 py-5 text-[10px] font-black text-slate-400 uppercase tracking-widest">Class</th>
                  <th className="px-8 py-5 text-[10px] font-black text-slate-400 uppercase tracking-widest">Status</th>
                  <th className="px-8 py-5 text-[10px] font-black text-slate-400 uppercase tracking-widest">Uploaded By</th>
                  <th className="px-8 py-5 text-[10px] font-black text-slate-400 uppercase tracking-widest">Uploaded On</th>
                  <th className="px-8 py-5 text-[10px] font-black text-slate-400 uppercase tracking-widest">Remarks</th>
                  <th className="px-8 py-5 text-[10px] font-black text-slate-400 uppercase tracking-widest text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {docs.map((doc: any) => {
                  const uploaderName = doc.uploaded_by_name || '—';
                  const isEmpUploaded = doc.uploaded_by_id && emp?.user?.id && doc.uploaded_by_id === emp.user.id;
                  const status = doc.verification_status || (doc.verified_at ? 'verified' : doc.rejection_reason ? 'rejected' : 'pending');
                  const isBusy = actioningId === doc.id;
                  return (
                  <tr key={doc.id} className="hover:bg-slate-50/50 transition-colors group">
                    <td className="px-8 py-5 text-sm font-black text-[#0F172A]">{doc.name || doc.original_filename}</td>
                    <td className="px-8 py-5 text-[10px] font-black text-slate-400 uppercase">{doc.doc_type || doc.type}</td>
                    <td className="px-8 py-5">
                      {status === 'verified' ? (
                        <span className="inline-flex items-center gap-1 text-[9px] font-black uppercase tracking-widest px-2 py-1 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200">
                          <CheckCircle2 size={10} /> Verified
                        </span>
                      ) : status === 'rejected' ? (
                        <div className="flex flex-col gap-1 max-w-[200px]">
                          <span className="inline-flex items-center gap-1 self-start text-[9px] font-black uppercase tracking-widest px-2 py-1 rounded-full bg-red-50 text-red-700 border border-red-200">
                            <XCircle size={10} /> Rejected
                          </span>
                          {doc.rejection_reason && (
                            <span className="text-[10px] font-medium text-red-600 italic line-clamp-2" title={doc.rejection_reason}>
                              {doc.rejection_reason}
                            </span>
                          )}
                        </div>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-[9px] font-black uppercase tracking-widest px-2 py-1 rounded-full bg-amber-50 text-amber-700 border border-amber-200">
                          <Clock size={10} /> Pending
                        </span>
                      )}
                    </td>
                    <td className="px-8 py-5 text-[11px] font-bold text-slate-600">
                      <div className="flex flex-col gap-1">
                        <span>{uploaderName}</span>
                        {isEmpUploaded && (
                          <span className="inline-flex items-center self-start text-[8px] font-black uppercase tracking-widest px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200">
                            Self-uploaded
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-8 py-5 text-[11px] font-bold text-slate-500">
                      {doc.uploaded_at ? new Date(doc.uploaded_at).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' }) : '—'}
                    </td>
                    <td className="px-8 py-5 text-[10px] font-bold text-slate-400 italic max-w-xs truncate">{doc.remark || '—'}</td>
                    <td className="px-8 py-5 text-right">
                      <div className="flex justify-end gap-2">
                        <Button
                          variant="outline"
                          size="sm"
                          className="h-8 w-8 p-0"
                          onClick={() => handleDownload(doc)}
                          aria-label={`Download ${doc.original_filename}`}
                          title="Download"
                          disabled={isBusy}
                        >
                          <Download size={12} />
                        </Button>
                        {status !== 'verified' && (
                          <Button
                            variant="outline"
                            size="sm"
                            className="h-8 px-2 text-[9px] font-black uppercase tracking-widest text-emerald-700 border-emerald-200 hover:bg-emerald-50"
                            onClick={() => handleVerify(doc)}
                            disabled={isBusy}
                            title="Mark verified"
                          >
                            <CheckCircle2 size={12} className="mr-1" />Verify
                          </Button>
                        )}
                        {status !== 'rejected' && (
                          <Button
                            variant="outline"
                            size="sm"
                            className="h-8 px-2 text-[9px] font-black uppercase tracking-widest text-amber-700 border-amber-200 hover:bg-amber-50"
                            onClick={() => { setRejectDoc(doc); setRejectReason(doc.rejection_reason || ''); }}
                            disabled={isBusy}
                            title="Reject document"
                          >
                            <XCircle size={12} className="mr-1" />Reject
                          </Button>
                        )}
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-8 w-8 p-0 text-red-500 hover:bg-red-50"
                          onClick={() => handleDelete(doc.id, doc.name || doc.original_filename)}
                          aria-label={`Delete ${doc.original_filename}`}
                          title="Delete"
                          disabled={isBusy}
                        >
                          <Trash2 size={12} />
                        </Button>
                      </div>
                    </td>
                  </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </Card>

      <Dialog open={!!rejectDoc} onOpenChange={(o) => { if (!o) { setRejectDoc(null); setRejectReason(''); } }}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Reject document</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <p className="text-sm text-slate-600">
              Provide a reason — the employee will see it and can re-upload a corrected version.
            </p>
            <div className="space-y-2">
              <label className="text-[9px] font-black text-slate-400 uppercase tracking-widest">Reason</label>
              <textarea
                value={rejectReason}
                onChange={e => setRejectReason(e.target.value)}
                rows={4}
                placeholder="e.g. Document is blurry — please upload a clearer scan."
                className="w-full px-4 py-3 rounded-xl border border-slate-200 bg-white text-sm font-medium text-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-500/30 resize-none"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => { setRejectDoc(null); setRejectReason(''); }} disabled={actioningId !== null}>
              Cancel
            </Button>
            <Button
              className="bg-red-600 text-white hover:bg-red-700"
              onClick={handleReject}
              disabled={!rejectReason.trim() || actioningId !== null}
            >
              {actioningId !== null ? <><Loader2 size={14} className="animate-spin mr-2" />Rejecting…</> : 'Confirm reject'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

const ASSET_TYPE_ICON: Record<string, React.ComponentType<any>> = {
  Laptop: Laptop,
  Monitor: Monitor,
  Phone: Phone,
  Storage: HardDrive,
};

const assetIcon = (type: string) => {
  const key = (type || '').trim();
  for (const k of Object.keys(ASSET_TYPE_ICON)) {
    if (key.toLowerCase().includes(k.toLowerCase())) return ASSET_TYPE_ICON[k];
  }
  return HardDrive;
};

const ASSET_STATUS_TONE: Record<string, string> = {
  allocated: 'bg-blue-50 text-blue-700 border-blue-200',
  returned: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  lost: 'bg-red-50 text-red-700 border-red-200',
};

const AssetsTab = ({ emp }: { emp: any }) => {
  const empId = emp?.id || emp?.employee_id_num;
  const [assets, setAssets] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [actioningId, setActioningId] = useState<number | null>(null);
  const [form, setForm] = useState({
    asset_type: '',
    model: '',
    identifier: '',
    serial_no: '',
    condition: '',
    remarks: '',
    issued_date: new Date().toISOString().slice(0, 10),
  });

  const fetchAssets = async () => {
    if (!empId) return;
    setLoading(true);
    try {
      const res = await client.get(ENDPOINTS.HR.EMPLOYEE_ASSETS(empId));
      setAssets(res.data || []);
    } catch (err: any) {
      toast.error(errMsg(err, 'Failed to load assets'));
      setAssets([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchAssets(); }, [empId]);

  const resetForm = () => setForm({
    asset_type: '', model: '', identifier: '', serial_no: '',
    condition: '', remarks: '',
    issued_date: new Date().toISOString().slice(0, 10),
  });

  const handleCreate = async () => {
    if (!form.asset_type.trim() || !form.model.trim()) {
      toast.error('Asset type and model are required');
      return;
    }
    setSubmitting(true);
    try {
      await client.post(ENDPOINTS.HR.EMPLOYEE_ASSETS(empId), {
        asset_type: form.asset_type.trim(),
        model: form.model.trim(),
        identifier: form.identifier.trim() || null,
        serial_no: form.serial_no.trim() || null,
        condition: form.condition.trim() || null,
        remarks: form.remarks.trim() || null,
        issued_date: form.issued_date || null,
      });
      toast.success('Asset assigned');
      setShowForm(false);
      resetForm();
      fetchAssets();
    } catch (err: any) {
      toast.error(errMsg(err, 'Failed to assign asset'));
    } finally {
      setSubmitting(false);
    }
  };

  const handleReturn = async (asset: any) => {
    if (!confirm(`Mark "${asset.model}" as returned?`)) return;
    setActioningId(asset.id);
    try {
      await client.patch(ENDPOINTS.HR.ASSET_UPDATE(asset.id), {
        status: 'returned',
        returned_date: new Date().toISOString().slice(0, 10),
      });
      toast.success('Asset returned');
      fetchAssets();
    } catch (err: any) {
      toast.error(errMsg(err, 'Failed to update asset'));
    } finally {
      setActioningId(null);
    }
  };

  const handleMarkLost = async (asset: any) => {
    if (!confirm(`Mark "${asset.model}" as lost? This is recorded in the audit log.`)) return;
    setActioningId(asset.id);
    try {
      await client.patch(ENDPOINTS.HR.ASSET_UPDATE(asset.id), { status: 'lost' });
      toast.success('Asset marked as lost');
      fetchAssets();
    } catch (err: any) {
      toast.error(errMsg(err, 'Failed to update asset'));
    } finally {
      setActioningId(null);
    }
  };

  const handleDelete = async (asset: any) => {
    if (!confirm(`Permanently remove "${asset.model}" from records?`)) return;
    setActioningId(asset.id);
    try {
      await client.delete(ENDPOINTS.HR.ASSET_DELETE(asset.id));
      toast.success('Asset removed');
      fetchAssets();
    } catch (err: any) {
      toast.error(errMsg(err, 'Failed to remove asset'));
    } finally {
      setActioningId(null);
    }
  };

  return (
    <div className="space-y-8 animate-in fade-in">
       <Card className="p-8 border-slate-200 shadow-sm bg-white flex items-center justify-between">
          <div>
             <h4 className="text-xl font-black text-[#0F172A] tracking-tight uppercase">Assigned Corporate Assets</h4>
             <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mt-1">
               {assets.length} record{assets.length === 1 ? '' : 's'} • Inventory & resource tracking
             </p>
          </div>
          <Button className="bg-blue-600 font-black uppercase text-[10px] tracking-widest h-11 px-8" onClick={() => setShowForm(s => !s)}>
            <Plus className="mr-2" size={14} /> Assign Asset
          </Button>
       </Card>

       {showForm && (
         <Card className="p-8 border-blue-600 border-2 shadow-xl animate-in slide-in-from-top duration-300">
            <h5 className="text-[10px] font-black text-blue-600 uppercase tracking-[0.2em] mb-6">New Asset Provisioning</h5>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
               <div className="space-y-2">
                  <label className="text-[9px] font-black text-slate-400 uppercase">Asset Type *</label>
                  <Input value={form.asset_type} onChange={e => setForm(f => ({ ...f, asset_type: e.target.value }))} placeholder="Laptop, Phone, Monitor…" className="h-11 font-black" />
               </div>
               <div className="space-y-2">
                  <label className="text-[9px] font-black text-slate-400 uppercase">Model / Name *</label>
                  <Input value={form.model} onChange={e => setForm(f => ({ ...f, model: e.target.value }))} placeholder="e.g. iPhone 15 Pro" className="h-11 font-black" />
               </div>
               <div className="space-y-2">
                  <label className="text-[9px] font-black text-slate-400 uppercase">Internal ID</label>
                  <Input value={form.identifier} onChange={e => setForm(f => ({ ...f, identifier: e.target.value }))} placeholder="e.g. AST-PH-001" className="h-11 font-black" />
               </div>
               <div className="space-y-2">
                  <label className="text-[9px] font-black text-slate-400 uppercase">Serial Number</label>
                  <Input value={form.serial_no} onChange={e => setForm(f => ({ ...f, serial_no: e.target.value }))} placeholder="Required for warranty" className="h-11 font-black" />
               </div>
               <div className="space-y-2">
                  <label className="text-[9px] font-black text-slate-400 uppercase">Condition on Issue</label>
                  <Input value={form.condition} onChange={e => setForm(f => ({ ...f, condition: e.target.value }))} placeholder="e.g. Brand New" className="h-11 font-black" />
               </div>
               <div className="space-y-2">
                  <label className="text-[9px] font-black text-slate-400 uppercase">Issued Date</label>
                  <Input type="date" value={form.issued_date} onChange={e => setForm(f => ({ ...f, issued_date: e.target.value }))} className="h-11 font-black" />
               </div>
               <div className="md:col-span-3 space-y-2">
                  <label className="text-[9px] font-black text-slate-400 uppercase">Remarks</label>
                  <Input value={form.remarks} onChange={e => setForm(f => ({ ...f, remarks: e.target.value }))} placeholder="Anything HR or finance should know" className="h-11 font-black" />
               </div>
               <div className="md:col-span-3 flex justify-end gap-3">
                  <Button variant="outline" className="h-11 px-6 font-black uppercase text-[10px]" onClick={() => { setShowForm(false); resetForm(); }} disabled={submitting}>Cancel</Button>
                  <Button className="h-11 px-8 bg-blue-600 font-black uppercase text-[10px]" onClick={handleCreate} disabled={submitting}>
                    {submitting ? <><Loader2 size={14} className="animate-spin mr-2" />Assigning…</> : 'Issue Asset'}
                  </Button>
               </div>
            </div>
         </Card>
       )}

       {loading ? (
         <div className="p-12 flex justify-center"><Loader2 size={28} className="text-blue-600 animate-spin" /></div>
       ) : assets.length === 0 ? (
         <Card className="p-16 border-slate-200 bg-white text-center">
           <HardDrive size={36} className="mx-auto text-slate-300 mb-3" />
           <p className="text-sm font-black text-slate-500 uppercase tracking-widest">No assets assigned</p>
           <p className="text-xs font-bold text-slate-400 mt-1">Use "Assign Asset" to issue a laptop, phone, or other corporate hardware.</p>
         </Card>
       ) : (
         <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
           {assets.map(asset => {
             const Icon = assetIcon(asset.asset_type);
             const tone = ASSET_STATUS_TONE[asset.status] || 'bg-slate-50 text-slate-700 border-slate-200';
             const busy = actioningId === asset.id;
             return (
               <Card key={asset.id} className="p-6 border-slate-200 shadow-sm bg-white hover:border-blue-600 transition-all group">
                 <div className="flex justify-between items-start mb-6">
                   <div className="p-3 bg-blue-50 text-blue-600 rounded-xl group-hover:bg-blue-600 group-hover:text-white transition-colors">
                     <Icon size={22} />
                   </div>
                   <span className={cn('text-[8px] font-black uppercase tracking-widest px-2 py-1 rounded-full border', tone)}>
                     {asset.status}
                   </span>
                 </div>
                 <h5 className="text-lg font-black text-[#0F172A] tracking-tight">{asset.model}</h5>
                 <p className="text-[10px] font-bold text-blue-600 uppercase tracking-widest mt-1">
                   {asset.asset_type}{asset.identifier ? ` · ${asset.identifier}` : ''}
                 </p>
                 <div className="mt-6 pt-6 border-t border-slate-50 grid grid-cols-2 gap-4">
                   <InfoItem label="Serial #" value={asset.serial_no || '—'} />
                   <InfoItem label="Issued" value={asset.issued_date ? new Date(asset.issued_date).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' }) : '—'} />
                   {asset.condition && <InfoItem label="Condition" value={asset.condition} />}
                   {asset.returned_date && <InfoItem label="Returned" value={new Date(asset.returned_date).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })} />}
                 </div>
                 {asset.remarks && (
                   <p className="mt-4 text-[10px] text-slate-500 italic line-clamp-2" title={asset.remarks}>{asset.remarks}</p>
                 )}
                 <div className="mt-6 flex flex-col gap-2">
                   {asset.status === 'allocated' && (
                     <>
                       <Button
                         variant="ghost"
                         className="w-full h-10 text-[9px] font-black uppercase tracking-widest text-emerald-700 hover:bg-emerald-50"
                         onClick={() => handleReturn(asset)}
                         disabled={busy}
                       >
                         <Undo2 size={12} className="mr-2" /> Mark Returned
                       </Button>
                       <Button
                         variant="ghost"
                         className="w-full h-9 text-[9px] font-black uppercase tracking-widest text-amber-700 hover:bg-amber-50"
                         onClick={() => handleMarkLost(asset)}
                         disabled={busy}
                       >
                         <AlertCircle size={12} className="mr-2" /> Mark Lost
                       </Button>
                     </>
                   )}
                   <Button
                     variant="ghost"
                     className="w-full h-9 text-[9px] font-black uppercase tracking-widest text-red-500 hover:bg-red-50"
                     onClick={() => handleDelete(asset)}
                     disabled={busy}
                   >
                     <Trash2 size={12} className="mr-2" /> Remove Record
                   </Button>
                 </div>
               </Card>
             );
           })}
         </div>
       )}
    </div>
  );
};

const AttendanceTab = () => {
  const logs = [
    { date: 'Feb 08, 2026', in: '09:12 AM', out: '06:45 PM', mode: 'Office', geo: 'HQ-Kolkata', status: 'On Time' },
    { date: 'Feb 07, 2026', in: '10:45 AM', out: '07:30 PM', mode: 'Home', geo: 'Salt Lake', status: 'Late Punch', edit: 'Corrected by Sarah Johnson • Reason: System Glitch' },
    { date: 'Feb 06, 2026', in: '09:05 AM', out: '06:15 PM', mode: 'Office', geo: 'HQ-Kolkata', status: 'On Time' },
  ];

  return (
    <div className="space-y-8 animate-in fade-in">
       <Card className="p-8 border-slate-200 shadow-sm bg-white flex items-center justify-between">
          <div>
             <h4 className="text-xl font-black text-[#0F172A] tracking-tight uppercase">Attendance & Geo-Control Audit</h4>
             <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mt-1">Punch Lifecycle & Remote Mode Verification</p>
          </div>
          <Button variant="outline" className="h-11 border-slate-200 font-black uppercase text-[10px] tracking-widest"><Calendar size={14} className="mr-2" /> View Monthly Statement</Button>
       </Card>

       <div className="space-y-4">
          {logs.map((log, i) => (
             <Card key={i} className="p-6 border-slate-200 shadow-sm bg-white hover:shadow-md transition-all">
                <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6">
                   <div className="flex items-center gap-6">
                      <div className="w-14 h-14 bg-slate-50 border border-slate-100 rounded-2xl flex flex-col items-center justify-center">
                         <span className="text-[9px] font-black text-slate-400 uppercase">Feb</span>
                         <span className="text-lg font-black text-[#0F172A]">{log.date.split(' ')[1].replace(',', '')}</span>
                      </div>
                      <div className="space-y-1">
                         <div className="flex items-center gap-2">
                           <p className="text-sm font-black text-[#0F172A]">{log.in} - {log.out}</p>
                           <Badge variant={log.status === 'On Time' ? 'success' : 'warning'} className="text-[8px] uppercase">{log.status}</Badge>
                         </div>
                         <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest flex items-center gap-2">
                            <MapPin size={10}/> {log.geo} • <ShieldCheck size={10}/> {log.mode} Mode
                         </p>
                      </div>
                   </div>
                   
                   {log.edit && (
                     <div className="flex-1 lg:max-w-md p-3 bg-amber-50 border border-amber-100 rounded-xl text-[9px] font-bold text-amber-700 uppercase tracking-wider flex items-center gap-2">
                        <AlertCircle size={14}/> {log.edit}
                     </div>
                   )}

                   <div className="flex gap-2">
                      <Button variant="ghost" size="sm" className="h-9 font-black uppercase text-[9px] tracking-widest text-blue-600 hover:bg-blue-50">Correction</Button>
                      <Button variant="ghost" size="sm" className="h-9 w-9 p-0 rounded-lg"><MoreVertical size={16}/></Button>
                   </div>
                </div>
             </Card>
          ))}
       </div>
    </div>
  );
};

const WorklogTab = () => {
  const logs = [
    { project: 'HR Strategic Planning', task: 'Appraisal Cycle Definition', duration: '4h 20m', date: 'Feb 08, 2026', status: 'Completed' },
    { project: 'Internal Operations', task: 'Policy Compliance Review', duration: '2h 15m', date: 'Feb 08, 2026', status: 'In Review' },
    { project: 'Admin Task', task: 'Email Communication', duration: '1h 05m', date: 'Feb 08, 2026', status: 'Completed' },
  ];

  return (
    <div className="space-y-8 animate-in fade-in">
       <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
          <Card className="p-6 border-slate-200 shadow-sm bg-blue-600 text-white flex flex-col justify-center">
             <p className="text-[10px] font-black uppercase tracking-[0.2em] opacity-80">Today's Logged Time</p>
             <h3 className="text-3xl font-black tracking-tighter mt-1">07h 40m</h3>
          </Card>
          <Card className="p-6 border-slate-200 shadow-sm bg-white flex flex-col justify-center">
             <p className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-400">Project Hours</p>
             <h3 className="text-3xl font-black tracking-tighter mt-1">06h 35m</h3>
          </Card>
          <Card className="p-6 border-slate-200 shadow-sm bg-white flex flex-col justify-center">
             <p className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-400">Idle / Admin Time</p>
             <h3 className="text-3xl font-black tracking-tighter mt-1 text-amber-500">01h 05m</h3>
          </Card>
          <Card className="p-6 border-slate-200 shadow-sm bg-green-50 text-green-700 flex flex-col justify-center border-green-100">
             <p className="text-[10px] font-black uppercase tracking-[0.2em]">Productivity Index</p>
             <h3 className="text-3xl font-black tracking-tighter mt-1">94.2%</h3>
          </Card>
       </div>

       <Card className="p-0 border-slate-200 shadow-sm overflow-hidden bg-white">
          <div className="p-8 border-b border-slate-100 flex items-center justify-between">
             <h4 className="text-xl font-black text-[#0F172A] tracking-tight uppercase">Activity Stream (Management View)</h4>
             <Button variant="outline" className="h-11 border-slate-200 font-black uppercase text-[10px] tracking-widest"><Search size={14} className="mr-2" /> Query Logs</Button>
          </div>
          <div className="overflow-x-auto">
             <table className="w-full text-left">
                <thead>
                   <tr className="bg-slate-50/50 border-b border-slate-100">
                      <th className="px-8 py-5 text-[10px] font-black text-slate-400 uppercase tracking-widest">Enterprise Project</th>
                      <th className="px-8 py-5 text-[10px] font-black text-slate-400 uppercase tracking-widest">Task Description</th>
                      <th className="px-8 py-5 text-[10px] font-black text-slate-400 uppercase tracking-widest">Artifact (Time)</th>
                      <th className="px-8 py-5 text-[10px] font-black text-slate-400 uppercase tracking-widest">Lifecycle</th>
                   </tr>
                </thead>
                <tbody className="divide-y divide-slate-50">
                   {logs.map((log, i) => (
                      <tr key={i} className="hover:bg-slate-50/30 transition-colors">
                         <td className="px-8 py-5">
                            <span className="text-xs font-black text-blue-600 bg-blue-50 px-2.5 py-1.5 rounded-lg border border-blue-100 uppercase">{log.project}</span>
                         </td>
                         <td className="px-8 py-5 text-sm font-black text-[#0F172A]">{log.task}</td>
                         <td className="px-8 py-5">
                            <div className="flex items-center gap-2">
                               <Clock size={14} className="text-slate-400" />
                               <span className="text-sm font-black text-[#0F172A]">{log.duration}</span>
                            </div>
                         </td>
                         <td className="px-8 py-5">
                            <Badge variant={log.status === 'Completed' ? 'success' : 'info'} className="text-[9px] font-black uppercase">{log.status}</Badge>
                         </td>
                      </tr>
                   ))}
                </tbody>
             </table>
          </div>
       </Card>
    </div>
  );
};

const SalaryRow = ({ label, value, color = "text-[#0F172A]", bold = false }: { label: string, value: string, color?: string, bold?: boolean }) => (
  <div className="flex justify-between items-center">
    <span className={cn("text-[11px] font-bold uppercase tracking-wider text-slate-500", bold && "font-black text-slate-700")}>{label}</span>
    <span className={cn("text-sm font-black", color)}>{value}</span>
  </div>
);

const BulkUploadModal = ({ isOpen, onClose, onSuccess }: any) => {
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<any>(null);

  // Reset state when dialog closes
  useEffect(() => {
    if (!isOpen) {
      setFile(null);
      setLoading(false);
      setResults(null);
    }
  }, [isOpen]);

  const handleDownloadTemplate = async () => {
    try {
      await downloadEmployeeTemplate();
    } catch (error: any) {
      const msg = error?.response?.data?.error?.message || 'Failed to download template';
      toast.error(msg);
    }
  };

  const handleUpload = async () => {
    if (!file) return toast.error("Please select a file");
    
    try {
      setLoading(true);
      const formData = new FormData();
      formData.append('file', file);
      
      const response = await client.post(ENDPOINTS.HR.BULK_UPLOAD, formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      
      const data = response.data;
      if (data.failed > 0) {
        // Show results with errors so user can review
        setResults(data);
        if (data.success > 0) {
          toast.success(`Created ${data.success} employee(s), ${data.failed} failed — see errors below`);
          onSuccess();
        } else {
          toast.error(`All ${data.failed} row(s) failed. Check errors below.`);
        }
      } else if (data.success > 0) {
        // All succeeded — close dialog and refresh
        toast.success(`Successfully created ${data.success} employee(s)`);
        onSuccess();
        onClose();
      } else {
        toast.error("No rows were processed. Check your file.");
      }
    } catch (error: any) {
      toast.error(error.response?.data?.error?.message || "Upload failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="max-w-xl p-0 overflow-hidden rounded-3xl border-none max-h-[90vh] min-h-[240px] flex flex-col">
        <DialogHeader className="p-8 bg-blue-600 text-white">
          <DialogTitle className="text-2xl font-black tracking-tighter uppercase flex items-center gap-3">
            <FileUp size={24} /> Bulk Employee Onboarding
          </DialogTitle>
          <p className="text-blue-100 text-[10px] font-bold uppercase tracking-widest mt-1">
            Standardize your workforce data imports
          </p>
        </DialogHeader>
        
        <div className="p-8 space-y-6 flex-1 overflow-y-auto min-h-0">
          <div className="flex items-center justify-between p-6 bg-slate-50 rounded-2xl border border-dashed border-slate-200">
            <div>
              <p className="text-xs font-black text-slate-700 uppercase tracking-tight">Need the structure?</p>
              <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mt-1">Download the pre-formatted Excel template</p>
            </div>
            <Button onClick={handleDownloadTemplate} variant="outline" className="h-10 font-black uppercase text-[10px] tracking-widest bg-white border-slate-200">
              <Download size={14} className="mr-2" /> Template
            </Button>
          </div>

          <div className="space-y-4">
             <label className="text-[10px] font-black text-[#64748B] uppercase tracking-widest">Select Import File</label>
             <div className="relative group">
                <Input 
                   type="file" 
                   accept=".xlsx,.xls"
                   onChange={(e: any) => setFile(e.target.files[0])}
                   className="h-20 pt-8 pb-2 px-10 border-2 border-dashed border-slate-200 rounded-2xl bg-slate-50 transition-all hover:bg-white hover:border-blue-400 font-bold text-slate-500 cursor-pointer"
                />
                <div className="absolute inset-0 flex items-center justify-center pointer-events-none opacity-50 font-black uppercase text-[10px] tracking-widest group-hover:text-blue-600">
                   {file ? file.name : "Drag and drop or click to select Excel file"}
                </div>
             </div>
          </div>

          {results && (
            <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 space-y-3">
               <div className="flex justify-between items-center text-[10px] font-black uppercase">
                  <span className="text-green-600">Successfully Processed: {results.success}</span>
                  <span className="text-red-600">Failed: {results.failed}</span>
               </div>
              {results.errors.length > 0 && (
                <div className="max-h-32 overflow-y-auto text-[9px] font-bold text-red-500 space-y-1 pr-2">
                     {results.errors.map((err: string, i: number) => <p key={i}>• {err}</p>)}
                  </div>
               )}
            </div>
          )}
        </div>
        
        <DialogFooter className="p-8 bg-slate-50 border-t border-slate-100 flex gap-3">
          <Button variant="outline" className="flex-1 h-12 font-black uppercase text-[10px] tracking-widest" onClick={onClose}>Close</Button>
          {!results && (
            <Button 
               disabled={loading || !file}
               className="flex-1 h-12 font-black uppercase text-[10px] tracking-widest bg-blue-600 hover:bg-blue-700 shadow-lg shadow-blue-600/20" 
               onClick={handleUpload}
            >
               {loading ? "Processing..." : "Start Import"}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

const EmployeeModal = ({ isOpen, onClose, onSuccess, editingEmp, departments = [] }: any) => {
  const [loading, setLoading] = useState(false);
  const [users, setUsers] = useState<any[]>([]);
  const [usersState, setUsersState] = useState<'idle' | 'loading' | 'loaded' | 'error'>('idle');
  const [usersError, setUsersError] = useState<string | null>(null);
  const [userLinkMode, setUserLinkMode] = useState<'existing' | 'new'>('existing');
  const [formData, setFormData] = useState<any>({
    user_id: '',
    manager_id: '',
    user_full_name: '',
    user_email: '',
    user_password: '',
    employee_id: '',
    department: '',
    designation: '',
    grade: '',
    level: '',
    employment_type: 'permanent',
    date_of_joining: '',
    status: 'active',
    salary: '',
    bank_account: '',
    bank_name: '',
    voluntary_pf: '',
    pf_number: '',
    pan_number: '',
    notice_period_days: '30'
  });

  useEffect(() => {
    if (isOpen) {
      fetchUsers();
      if (editingEmp) {
        setUserLinkMode('existing');
        setFormData({
          user_id: editingEmp.user_id.toString(),
          manager_id: editingEmp.user?.manager_id?.toString() || '',
          user_full_name: '',
          user_email: '',
          user_password: '',
          employee_id: editingEmp.employee_id,
          department: editingEmp.department,
          designation: editingEmp.designation,
          grade: editingEmp.grade || '',
          level: editingEmp.level || '',
          employment_type: editingEmp.employment_type || 'permanent',
          date_of_joining: editingEmp.date_of_joining,
          status: editingEmp.status,
          salary: editingEmp.salary || '',
          bank_account: editingEmp.bank_account || '',
          bank_name: editingEmp.bank_name || '',
          voluntary_pf: editingEmp.voluntary_pf || '',
          pf_number: editingEmp.pf_number || '',
          pan_number: editingEmp.pan_number || '',
          notice_period_days: editingEmp.notice_period_days?.toString() || '30'
        });
      } else {
        setUserLinkMode('existing');
        setFormData({
          user_id: '',
          manager_id: '',
          user_full_name: '',
          user_email: '',
          user_password: '',
          employee_id: '',
          department: '',
          designation: '',
          grade: '',
          level: '',
          employment_type: 'permanent',
          date_of_joining: '',
          status: 'active',
          salary: '',
          bank_account: '',
          bank_name: '',
          voluntary_pf: '',
          pf_number: '',
          pan_number: ''
        });
      }
    }
  }, [isOpen, editingEmp]);

  const fetchUsers = async () => {
    try {
      setUsersState('loading');
      setUsersError(null);
      const response = await client.get(ENDPOINTS.HR.USERS);
      const items = Array.isArray((response as any).data) ? (response as any).data : [];
      setUsers(items);
      setUsersState('loaded');
    } catch (error: any) {
      const status = error?.response?.status;
      const msg = status >= 500
        ? "Server error while loading users."
        : (error?.response?.data?.error?.message || "Failed to fetch users");
      setUsers([]);
      setUsersState('error');
      setUsersError(msg);
      toast.error(msg);
    }
  };

  const handleSubmit = async () => {
    try {
      setLoading(true);
      if (!formData.employee_id || !formData.department || !formData.designation || !formData.date_of_joining) {
        toast.error('Please complete all required fields.');
        return;
      }

      const baseData: any = {
        employee_id: formData.employee_id,
        department: formData.department,
        designation: formData.designation,
        grade: formData.grade || null,
        level: formData.level || null,
        employment_type: formData.employment_type || 'permanent',
        date_of_joining: formData.date_of_joining,
        status: formData.status,
        salary: formData.salary,
        bank_account: formData.bank_account,
        bank_name: formData.bank_name || null,
        voluntary_pf: formData.voluntary_pf || null,
        pf_number: formData.pf_number,
        pan_number: formData.pan_number,
        notice_period_days: formData.notice_period_days ? parseInt(formData.notice_period_days) : 30,
      };
      if (baseData.salary) baseData.salary = parseFloat(baseData.salary);
      if (baseData.voluntary_pf) baseData.voluntary_pf = parseFloat(baseData.voluntary_pf);
      
      if (editingEmp) {
        const data = { 
          ...baseData, 
          user_id: parseInt(formData.user_id),
          manager_id: (formData.manager_id && formData.manager_id !== 'none') ? parseInt(formData.manager_id) : null
        };
        await client.patch(ENDPOINTS.HR.EMPLOYEE_DETAIL(editingEmp.id), data);
        toast.success("Employee updated successfully");
      } else {
        if (userLinkMode === 'new') {
          if (!formData.user_full_name || !formData.user_email || !formData.user_password) {
            toast.error('Please enter name, email, and password for the new user.');
            return;
          }
          const payload = {
            ...baseData,
            user: {
              full_name: formData.user_full_name,
              email: formData.user_email,
              password: formData.user_password,
              manager_id: (formData.manager_id && formData.manager_id !== 'none') ? parseInt(formData.manager_id) : null
            },
          };
          await client.post(ENDPOINTS.HR.EMPLOYEES_WITH_USER, payload);
          toast.success('User + employee created successfully');
        } else {
          if (!formData.user_id) {
            toast.error('Please select a linked user account.');
            return;
          }
          const data = { 
            ...baseData, 
            user_id: parseInt(formData.user_id),
            manager_id: (formData.manager_id && formData.manager_id !== 'none') ? parseInt(formData.manager_id) : null
          };
          await client.post(ENDPOINTS.HR.EMPLOYEES, data);
          toast.success("Employee created successfully");
        }
      }
      onSuccess();
      onClose();
    } catch (error: any) {
      toast.error(error.response?.data?.error?.message || "Action failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="max-w-2xl p-0 overflow-hidden rounded-3xl border-none max-h-[90vh] min-h-[240px] flex flex-col">
        <DialogHeader className="p-8 bg-[#0F172A] text-white">
          <DialogTitle className="text-2xl font-black tracking-tighter uppercase">
            {editingEmp ? "Update Employee Master" : "Onboard New Employee"}
          </DialogTitle>
          <p className="text-slate-400 text-[10px] font-bold uppercase tracking-widest mt-1">
            Ensure all legal and payroll data is accurate
          </p>
        </DialogHeader>
        
        <div className="p-8 space-y-6 flex-1 overflow-y-auto min-h-0">
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <label className="text-[10px] font-black text-[#64748B] uppercase tracking-widest">Linked User Account</label>
              {!editingEmp && (
                <div className="flex gap-2">
                  <Button
                    type="button"
                    variant={userLinkMode === 'existing' ? 'default' : 'outline'}
                    className="h-9 px-3 text-[10px] font-black uppercase tracking-widest"
                    onClick={() => setUserLinkMode('existing')}
                    disabled={loading}
                  >
                    Existing
                  </Button>
                  <Button
                    type="button"
                    variant={userLinkMode === 'new' ? 'default' : 'outline'}
                    className="h-9 px-3 text-[10px] font-black uppercase tracking-widest"
                    onClick={() => setUserLinkMode('new')}
                    disabled={loading}
                  >
                    New
                  </Button>
                </div>
              )}

              {!editingEmp && userLinkMode === 'new' ? (
                <div className="space-y-3">
                  <Input
                    value={formData.user_full_name}
                    onChange={(e) => setFormData({ ...formData, user_full_name: e.target.value })}
                    placeholder="Full name"
                    className="h-12 font-bold rounded-xl bg-slate-50 border-slate-200"
                  />
                  <Input
                    value={formData.user_email}
                    onChange={(e) => setFormData({ ...formData, user_email: e.target.value })}
                    placeholder="name@company.com"
                    className="h-12 font-bold rounded-xl bg-slate-50 border-slate-200"
                  />
                  <Input
                    type="password"
                    value={formData.user_password}
                    onChange={(e) => setFormData({ ...formData, user_password: e.target.value })}
                    placeholder="Password"
                    className="h-12 font-bold rounded-xl bg-slate-50 border-slate-200"
                  />
                </div>
              ) : (
              <Select 
                value={formData.user_id} 
                onValueChange={(val) => setFormData({...formData, user_id: val})}
                disabled={!!editingEmp}
              >
                <SelectTrigger className="h-12 font-bold rounded-xl bg-slate-50 border-slate-200">
                  <SelectValue placeholder="Select User" />
                </SelectTrigger>
                <SelectContent>
                  {usersState === 'loading' && (
                    <SelectItem value="__loading" disabled>Loading users...</SelectItem>
                  )}
                  {usersState === 'error' && (
                    <SelectItem value="__error" disabled>{usersError || 'Server error loading users'}</SelectItem>
                  )}
                  {usersState === 'loaded' && users.length === 0 && (
                    <SelectItem value="__empty" disabled>No users found</SelectItem>
                  )}
                  {usersState === 'loaded' && users.map(u => (
                    <SelectItem key={u.id} value={u.id.toString()}>{u.full_name} ({u.email})</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              )}
            </div>
            <div className="space-y-2">
              <label className="text-[10px] font-black text-[#64748B] uppercase tracking-widest">Employee ID</label>
              <Input 
                value={formData.employee_id}
                onChange={(e) => setFormData({...formData, employee_id: e.target.value})}
                placeholder="e.g. EMP-001" 
                className="h-12 font-bold rounded-xl bg-slate-50 border-slate-200" 
              />
            </div>
          </div>

          <div className="grid grid-cols-1 gap-4">
             <div className="space-y-2">
                <label className="text-[10px] font-black text-[#64748B] uppercase tracking-widest">Reporting Manager</label>
                <Select 
                  value={formData.manager_id} 
                  onValueChange={(val) => setFormData({...formData, manager_id: val})}
                >
                  <SelectTrigger className="h-12 font-bold rounded-xl bg-slate-50 border-slate-200">
                    <SelectValue placeholder="Select Manager" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">No Manager</SelectItem>
                    {usersState === 'loaded' && users.map(u => (
                      <SelectItem key={u.id} value={u.id.toString()}>{u.full_name} ({u.email})</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
             </div>
          </div>
          
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <label className="text-[10px] font-black text-[#64748B] uppercase tracking-widest">Department</label>
              <Select
                value={formData.department}
                onValueChange={(val) => setFormData({...formData, department: val})}
                disabled={departments.length === 0}
              >
                <SelectTrigger className="h-12 font-bold rounded-xl bg-slate-50 border-slate-200">
                  <SelectValue placeholder={departments.length === 0 ? 'No departments — add one in System Administration' : 'Select Dept'} />
                </SelectTrigger>
                <SelectContent>
                  {departments.map(d => (
                    <SelectItem key={d.id} value={d.name}>{d.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {departments.length === 0 && (
                <p className="text-[10px] font-bold text-amber-600 mt-1">
                  No departments configured. Ask an admin to add departments in System Administration first.
                </p>
              )}
            </div>
            <div className="space-y-2">
              <label className="text-[10px] font-black text-[#64748B] uppercase tracking-widest">Designation</label>
              <Input 
                value={formData.designation}
                onChange={(e) => setFormData({...formData, designation: e.target.value})}
                placeholder="e.g. Software Engineer" 
                className="h-12 font-bold rounded-xl bg-slate-50 border-slate-200" 
              />
            </div>
          </div>
          
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <label className="text-[10px] font-black text-[#64748B] uppercase tracking-widest">Date of Joining</label>
              <Input 
                type="date"
                value={formData.date_of_joining}
                onChange={(e) => setFormData({...formData, date_of_joining: e.target.value})}
                className="h-12 font-bold rounded-xl bg-slate-50 border-slate-200" 
              />
            </div>
            <div className="space-y-2">
              <label className="text-[10px] font-black text-[#64748B] uppercase tracking-widest">Status</label>
              <Select value={formData.status} onValueChange={(val) => setFormData({...formData, status: val})}>
                <SelectTrigger className="h-12 font-bold rounded-xl bg-slate-50 border-slate-200">
                  <SelectValue placeholder="Select Status" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="active">Active</SelectItem>
                  <SelectItem value="inactive">Inactive</SelectItem>
                  <SelectItem value="on_leave">On Leave</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <label className="text-[10px] font-black text-[#64748B] uppercase tracking-widest">Notice Period (Days)</label>
              <Input
                type="number"
                value={formData.notice_period_days}
                onChange={(e) => setFormData({...formData, notice_period_days: e.target.value})}
                placeholder="30"
                className="h-12 font-bold rounded-xl bg-slate-50 border-slate-200"
              />
            </div>
          </div>

          <div className="pt-4 border-t border-slate-100">
            <h4 className="text-[10px] font-black text-blue-600 uppercase tracking-[0.2em] mb-4">Grade & Level</h4>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <label className="text-[10px] font-black text-[#64748B] uppercase tracking-widest">Grade</label>
                <Input
                  value={formData.grade}
                  onChange={(e) => setFormData({...formData, grade: e.target.value})}
                  placeholder="e.g. A, B, NA"
                  className="h-12 font-bold rounded-xl bg-slate-50 border-slate-200"
                />
              </div>
              <div className="space-y-2">
                <label className="text-[10px] font-black text-[#64748B] uppercase tracking-widest">Level</label>
                <Input
                  value={formData.level}
                  onChange={(e) => setFormData({...formData, level: e.target.value})}
                  placeholder="e.g. 1, 2, 3, NA"
                  className="h-12 font-bold rounded-xl bg-slate-50 border-slate-200"
                />
              </div>
            </div>
          </div>

          <div className="pt-4 border-t border-slate-100">
            <h4 className="text-[10px] font-black text-blue-600 uppercase tracking-[0.2em] mb-4">Payroll & Sensitive Data</h4>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2 col-span-2">
                <label className="text-[10px] font-black text-[#64748B] uppercase tracking-widest">Employment Type</label>
                <Select
                  value={formData.employment_type || 'permanent'}
                  onValueChange={(v) => setFormData({...formData, employment_type: v})}
                >
                  <SelectTrigger className="h-12 font-bold rounded-xl bg-slate-50 border-slate-200">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="permanent">Permanent</SelectItem>
                    <SelectItem value="contractual">Contractual</SelectItem>
                    <SelectItem value="advisor">Advisor</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <label className="text-[10px] font-black text-[#64748B] uppercase tracking-widest">Monthly Salary (Basic)</label>
                <Input
                  type="number"
                  value={formData.salary}
                  onChange={(e) => setFormData({...formData, salary: e.target.value})}
                  placeholder="0.00"
                  className="h-12 font-bold rounded-xl bg-slate-50 border-slate-200"
                />
              </div>
              <div className="space-y-2">
                <label className="text-[10px] font-black text-[#64748B] uppercase tracking-widest">Voluntary PF (₹/month)</label>
                <Input
                  type="number"
                  value={formData.voluntary_pf}
                  onChange={(e) => setFormData({...formData, voluntary_pf: e.target.value})}
                  placeholder="0.00"
                  className="h-12 font-bold rounded-xl bg-slate-50 border-slate-200"
                />
              </div>
              <div className="space-y-2">
                <label className="text-[10px] font-black text-[#64748B] uppercase tracking-widest">Bank Name</label>
                <Input
                  value={formData.bank_name}
                  onChange={(e) => setFormData({...formData, bank_name: e.target.value})}
                  placeholder="e.g. HDFC, SBI"
                  className="h-12 font-bold rounded-xl bg-slate-50 border-slate-200"
                />
              </div>
              <div className="space-y-2">
                <label className="text-[10px] font-black text-[#64748B] uppercase tracking-widest">Bank Account</label>
                <Input
                  value={formData.bank_account}
                  onChange={(e) => setFormData({...formData, bank_account: e.target.value})}
                  placeholder="AC-XXXXXXXXXX"
                  className="h-12 font-bold rounded-xl bg-slate-50 border-slate-200"
                />
              </div>
            </div>
          </div>
        </div>
        
        <DialogFooter className="p-8 bg-slate-50 border-t border-slate-100 flex gap-3">
          <Button variant="outline" className="flex-1 h-12 font-black uppercase text-[10px] tracking-widest" onClick={onClose}>Cancel</Button>
          <Button 
            disabled={loading}
            className="flex-1 h-12 font-black uppercase text-[10px] tracking-widest bg-blue-600 hover:bg-blue-700 shadow-lg shadow-blue-600/20" 
            onClick={handleSubmit}
          >
            {loading ? "Processing..." : (editingEmp ? "Update Record" : "Create Record")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};


// ─── Exit Management Tab (HR) ───────────────────────────────

const CLEARANCE_TEMPLATES: Record<string, string[]> = {
  'Information Technology': ['Email ID Blocked', 'Laptop/Desktop Returned', 'Pen Drive Returned', 'Software Access Revoked'],
  'Administration': ['Identity Card Returned', 'Biometric Card Returned', 'Mobile Handset/SIM Returned', 'Office Keys Returned'],
  'Accounts': ['Loans/Advances Settled', 'Expense Claims Settled', 'Credit Card Returned'],
  'Human Resources': ['Exit Interview Completed', 'All Documents Signed', 'Final Settlement Prepared'],
};

const ExitManagementTab = ({ emp }: { emp: any }) => {
  const [exitData, setExitData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [users, setUsers] = useState<any[]>([]);
  const [showClearanceModal, setShowClearanceModal] = useState(false);
  const [actionLoading, setActionLoading] = useState('');
  const [hrActionMode, setHrActionMode] = useState<'cancel' | 'expedite' | null>(null);
  const [hrNote, setHrNote] = useState('');
  const [expediteDate, setExpediteDate] = useState('');

  const fetchExitData = async () => {
    setLoading(true);
    try {
      const res = await client.get(ENDPOINTS.EXIT.RESIGNATIONS);
      const match = res.data.find((r: any) => r.employee_id === emp.id);
      if (match) {
        const detail = await client.get(ENDPOINTS.EXIT.RESIGNATION_DETAIL(match.id));
        setExitData(detail.data);
      } else {
        setExitData(null);
      }
    } catch {
      setExitData(null);
    } finally {
      setLoading(false);
    }
  };

  const fetchUsers = async () => {
    try {
      const res = await client.get(ENDPOINTS.HR.USERS);
      setUsers(res.data);
    } catch {}
  };

  useEffect(() => { fetchExitData(); fetchUsers(); }, [emp.id]);

  const handleAccept = async () => {
    if (!exitData?.resignation) return;
    setActionLoading('accept');
    try {
      await client.post(ENDPOINTS.EXIT.ACCEPT(exitData.resignation.id), {});
      toast.success('Resignation accepted');
      fetchExitData();
    } catch (e: any) {
      toast.error(errMsg(e, 'Failed'));
    } finally {
      setActionLoading('');
    }
  };

  const handleReject = async () => {
    if (!exitData?.resignation) return;
    setActionLoading('reject');
    try {
      await client.post(ENDPOINTS.EXIT.REJECT(exitData.resignation.id));
      toast.success('Resignation rejected');
      fetchExitData();
    } catch (e: any) {
      toast.error(errMsg(e, 'Failed'));
    } finally {
      setActionLoading('');
    }
  };

  const handleRequestExitInterview = async () => {
    if (!exitData?.resignation) return;
    setActionLoading('exit_interview');
    try {
      await client.post(ENDPOINTS.EXIT.REQUEST_EXIT_INTERVIEW(exitData.resignation.id));
      toast.success('Exit interview requested');
      fetchExitData();
    } catch (e: any) {
      toast.error(errMsg(e, 'Failed'));
    } finally {
      setActionLoading('');
    }
  };

  const handleRelease = async () => {
    if (!exitData?.resignation) return;
    if (!confirm('Are you sure? This will deactivate the employee account.')) return;
    setActionLoading('release');
    try {
      await client.post(ENDPOINTS.EXIT.RELEASE(exitData.resignation.id));
      toast.success('Employee released and deactivated');
      fetchExitData();
    } catch (e: any) {
      toast.error(errMsg(e, 'Failed'));
    } finally {
      setActionLoading('');
    }
  };

  const openHrActionDialog = (mode: 'cancel' | 'expedite') => {
    setHrActionMode(mode);
    setHrNote('');
    if (mode === 'expedite' && exitData?.resignation?.last_working_day) {
      const today = new Date();
      const lwd = new Date(exitData.resignation.last_working_day);
      // Default to halfway between today and the current LWD as a sane starting suggestion.
      const suggested = new Date(today.getTime() + (lwd.getTime() - today.getTime()) / 2);
      setExpediteDate(suggested.toISOString().slice(0, 10));
    } else {
      setExpediteDate('');
    }
  };

  const closeHrActionDialog = () => {
    setHrActionMode(null);
    setHrNote('');
    setExpediteDate('');
  };

  const submitHrAction = async () => {
    if (!exitData?.resignation || !hrActionMode) return;
    const note = hrNote.trim();
    if (!note) { toast.error('A note is required'); return; }
    setActionLoading(hrActionMode);
    try {
      if (hrActionMode === 'cancel') {
        await client.post(ENDPOINTS.EXIT.CANCEL(exitData.resignation.id), { note });
        toast.success('Resignation cancelled');
      } else {
        if (!expediteDate) { toast.error('Pick a new last working day'); setActionLoading(''); return; }
        await client.post(ENDPOINTS.EXIT.EXPEDITE(exitData.resignation.id), {
          note,
          last_working_day: expediteDate,
        });
        toast.success('Resignation expedited');
      }
      closeHrActionDialog();
      fetchExitData();
    } catch (e: any) {
      toast.error(errMsg(e, 'Action failed'));
    } finally {
      setActionLoading('');
    }
  };

  if (loading) {
    return <div className="p-12 text-center text-slate-400 font-bold uppercase tracking-widest animate-pulse">Loading exit data...</div>;
  }

  if (!exitData || !exitData.resignation) {
    return (
      <Card className="p-12 border-2 border-dashed border-slate-200 flex flex-col items-center justify-center bg-slate-50/50">
        <LogOut size={48} className="text-slate-300 mb-4" />
        <h4 className="text-lg font-black text-slate-400 uppercase tracking-tight">No Resignation Filed</h4>
        <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mt-2">This employee has not submitted a resignation</p>
      </Card>
    );
  }

  const r = exitData.resignation;
  const statusColors: Record<string, string> = {
    submitted: 'bg-amber-100 text-amber-800', accepted: 'bg-blue-100 text-blue-800',
    notice_period: 'bg-orange-100 text-orange-800', exit_interview: 'bg-purple-100 text-purple-800',
    clearance: 'bg-cyan-100 text-cyan-800', released: 'bg-green-100 text-green-800',
    withdrawn: 'bg-slate-100 text-slate-600', rejected: 'bg-red-100 text-red-800',
  };
  const REASON_MAP: Record<string, string> = {
    better_opportunity: 'Better Career Opportunity', higher_studies: 'Higher Studies',
    personal: 'Personal Reasons', relocation: 'Relocation', health: 'Health Reasons',
    work_environment: 'Work Environment', compensation: 'Compensation & Benefits',
    relationship: 'Manager/Team Relationship', role_mismatch: 'Role Mismatch', other: 'Other',
  };

  const noticePeriodElapsed =
    ['notice_period', 'accepted'].includes(r.status) &&
    new Date(r.last_working_day) < new Date(new Date().toDateString());

  return (
    <div className="space-y-8 animate-in fade-in">
      {/* Notice period elapsed alert */}
      {noticePeriodElapsed && (
        <div className="flex items-start gap-4 p-5 bg-orange-50 border border-orange-200 rounded-2xl">
          <AlertCircle size={20} className="text-orange-500 shrink-0 mt-0.5" />
          <div className="flex-1">
            <p className="text-sm font-black text-orange-800">Notice Period Ended — Action Required</p>
            <p className="text-xs font-bold text-orange-600 mt-0.5">
              Last working day was {new Date(r.last_working_day).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })}. Request the exit interview and initiate clearance to proceed.
            </p>
          </div>
          <Button
            className="h-9 px-5 font-black uppercase text-[9px] tracking-widest bg-orange-500 hover:bg-orange-600 text-white shrink-0"
            onClick={handleRequestExitInterview}
            disabled={!!actionLoading}
          >
            Start Exit Interview
          </Button>
        </div>
      )}

      {/* Status Header */}
      <Card className="p-8 border-slate-200 shadow-sm bg-white">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-4">
            <div className="p-3 bg-red-50 rounded-xl"><LogOut size={24} className="text-red-600" /></div>
            <div>
              <h4 className="text-xl font-black text-[#0F172A] uppercase tracking-tight">Resignation Details</h4>
              <Badge className={`${statusColors[r.status] || 'bg-slate-100'} text-[9px] font-black uppercase mt-1`}>{r.status.replace(/_/g, ' ')}</Badge>
            </div>
          </div>
          {exitData.days_remaining !== null && !['released', 'withdrawn', 'rejected'].includes(r.status) && (
            <div className="text-right">
              <p className="text-3xl font-black text-[#0F172A]">{exitData.days_remaining}</p>
              <p className="text-[9px] font-black text-slate-400 uppercase tracking-widest">Days Remaining</p>
            </div>
          )}
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="p-4 bg-slate-50 rounded-xl"><p className="text-[9px] font-black text-slate-400 uppercase">Reason</p><p className="text-sm font-bold mt-1">{REASON_MAP[r.reason] || r.reason}</p></div>
          <div className="p-4 bg-slate-50 rounded-xl"><p className="text-[9px] font-black text-slate-400 uppercase">Resignation Date</p><p className="text-sm font-bold mt-1">{new Date(r.resignation_date).toLocaleDateString()}</p></div>
          <div className="p-4 bg-slate-50 rounded-xl"><p className="text-[9px] font-black text-slate-400 uppercase">Last Working Day</p><p className="text-sm font-bold mt-1">{new Date(r.last_working_day).toLocaleDateString()}</p></div>
          <div className="p-4 bg-slate-50 rounded-xl"><p className="text-[9px] font-black text-slate-400 uppercase">Notice Period</p><p className="text-sm font-bold mt-1">{r.notice_period_days} days</p></div>
        </div>
        {r.reason_details && (
          <div className="mt-4 p-4 bg-slate-50 rounded-xl">
            <p className="text-[9px] font-black text-slate-400 uppercase mb-1">Details</p>
            <p className="text-sm text-slate-600">{r.reason_details}</p>
          </div>
        )}
      </Card>

      {/* HR Actions */}
      <Card className="p-8 border-slate-200 shadow-sm bg-white">
        <h5 className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-4">HR Actions</h5>
        <div className="flex flex-wrap gap-3">
          {r.status === 'submitted' && (
            <>
              <Button onClick={handleAccept} disabled={!!actionLoading} className="h-10 px-6 bg-green-600 text-white rounded-xl text-[10px] font-black uppercase hover:bg-green-700 disabled:opacity-50">
                <CheckCircle size={16} className="mr-2" /> Accept
              </Button>
              <Button onClick={handleReject} disabled={!!actionLoading} className="h-10 px-6 bg-red-600 text-white rounded-xl text-[10px] font-black uppercase hover:bg-red-700 disabled:opacity-50">
                <XCircle size={16} className="mr-2" /> Reject
              </Button>
            </>
          )}
          {['accepted', 'notice_period'].includes(r.status) && (
            <Button onClick={handleRequestExitInterview} disabled={!!actionLoading} className="h-10 px-6 bg-purple-600 text-white rounded-xl text-[10px] font-black uppercase hover:bg-purple-700 disabled:opacity-50">
              <FileText size={16} className="mr-2" /> Request Exit Interview
            </Button>
          )}
          {['accepted', 'notice_period', 'exit_interview', 'clearance'].includes(r.status) && (
            <Button onClick={() => setShowClearanceModal(true)} disabled={!!actionLoading} className="h-10 px-6 bg-cyan-600 text-white rounded-xl text-[10px] font-black uppercase hover:bg-cyan-700 disabled:opacity-50">
              <ShieldCheck size={16} className="mr-2" /> Initiate Clearance
            </Button>
          )}
          {r.status === 'clearance' && exitData.all_cleared && (
            <Button onClick={handleRelease} disabled={!!actionLoading} className="h-10 px-6 bg-slate-900 text-white rounded-xl text-[10px] font-black uppercase hover:bg-slate-800 disabled:opacity-50">
              <LogOut size={16} className="mr-2" /> Final Release
            </Button>
          )}
          {['accepted', 'notice_period', 'exit_interview'].includes(r.status) && (
            <Button onClick={() => openHrActionDialog('expedite')} disabled={!!actionLoading} className="h-10 px-6 bg-amber-600 text-white rounded-xl text-[10px] font-black uppercase hover:bg-amber-700 disabled:opacity-50">
              <Clock size={16} className="mr-2" /> Expedite
            </Button>
          )}
          {['submitted', 'accepted', 'notice_period', 'exit_interview', 'clearance'].includes(r.status) && (
            <Button onClick={() => openHrActionDialog('cancel')} disabled={!!actionLoading} className="h-10 px-6 bg-slate-100 text-slate-700 border border-slate-200 rounded-xl text-[10px] font-black uppercase hover:bg-slate-200 disabled:opacity-50">
              <Undo2 size={16} className="mr-2" /> Cancel Resignation
            </Button>
          )}
        </div>
        {r.hr_note && (
          <div className="mt-6 p-4 rounded-xl border border-slate-200 bg-slate-50">
            <p className="text-[9px] font-black text-slate-400 uppercase tracking-widest mb-1">Latest HR note</p>
            <p className="text-sm text-slate-700 italic">"{r.hr_note}"</p>
          </div>
        )}
      </Card>

      {/* Exit Interview */}
      {exitData.exit_interview && (
        <Card className="p-8 border-slate-200 shadow-sm bg-white">
          <h5 className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-6">Exit Interview Responses</h5>
          <ExitInterviewDisplay interview={exitData.exit_interview} resignationId={r.id} onUpdate={fetchExitData} />
        </Card>
      )}

      {/* Clearance */}
      {exitData.clearance_requests?.length > 0 && (
        <Card className="p-8 border-slate-200 shadow-sm bg-white">
          <h5 className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-6">Clearance Status</h5>
          <div className="space-y-3">
            {exitData.clearance_requests.map((c: any) => (
              <div key={c.id} className={`p-4 rounded-xl border ${c.status === 'cleared' ? 'bg-green-50 border-green-200' : c.status === 'flagged' ? 'bg-red-50 border-red-200' : 'bg-amber-50 border-amber-200'}`}>
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-3">
                    {c.status === 'cleared' ? <CheckCircle size={18} className="text-green-600" /> : c.status === 'flagged' ? <AlertCircle size={18} className="text-red-600" /> : <Clock size={18} className="text-amber-600" />}
                    <div>
                      <p className="text-sm font-black text-[#0F172A] uppercase">{c.department}</p>
                      <p className="text-[9px] text-slate-500">Assigned to: {c.assigned_to_name || 'Unknown'}</p>
                    </div>
                  </div>
                  <Badge className={`text-[8px] font-black uppercase ${c.status === 'cleared' ? 'bg-green-100 text-green-700' : c.status === 'flagged' ? 'bg-red-100 text-red-700' : 'bg-amber-100 text-amber-700'}`}>{c.status}</Badge>
                </div>
                {c.items?.length > 0 && (
                  <div className="mt-3 space-y-1 pl-9">
                    {c.items.map((item: any) => (
                      <div key={item.id} className="flex items-center gap-2 text-xs">
                        {item.is_cleared ? <CheckCircle2 size={12} className="text-green-500" /> : <XCircle size={12} className="text-slate-300" />}
                        <span className={item.is_cleared ? 'text-green-700 line-through' : 'text-slate-600'}>{item.item_name}</span>
                      </div>
                    ))}
                  </div>
                )}
                {c.remarks && <p className="text-xs text-slate-500 mt-2 pl-9 italic">{c.remarks}</p>}
              </div>
            ))}
          </div>
        </Card>
      )}

      {showClearanceModal && (
        <ClearanceModal resignationId={r.id} users={users} onClose={() => setShowClearanceModal(false)} onSuccess={() => { setShowClearanceModal(false); fetchExitData(); }} />
      )}

      <Dialog open={hrActionMode !== null} onOpenChange={(o) => { if (!o) closeHrActionDialog(); }}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>
              {hrActionMode === 'expedite' ? 'Expedite Resignation' : 'Cancel Resignation'}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <p className="text-sm text-slate-600">
              {hrActionMode === 'expedite'
                ? `Move the last working day forward. Currently ${new Date(r.last_working_day).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })}. The employee and their manager will be notified.`
                : `Reverse the resignation entirely. ${r.status === 'notice_period' ? "The employee's status will return to active." : ''} The employee and their manager will be notified.`}
            </p>

            {hrActionMode === 'expedite' && (
              <div className="space-y-2">
                <label className="text-[9px] font-black text-slate-400 uppercase tracking-widest">New last working day</label>
                <Input
                  type="date"
                  value={expediteDate}
                  onChange={e => setExpediteDate(e.target.value)}
                  min={new Date().toISOString().slice(0, 10)}
                  max={new Date(new Date(r.last_working_day).getTime() - 86400000).toISOString().slice(0, 10)}
                  className="h-11 font-bold"
                />
              </div>
            )}

            <div className="space-y-2">
              <label className="text-[9px] font-black text-slate-400 uppercase tracking-widest">Note (required)</label>
              <textarea
                value={hrNote}
                onChange={e => setHrNote(e.target.value)}
                rows={4}
                placeholder={hrActionMode === 'expedite'
                  ? 'e.g. Project handover completed early; releasing per mutual agreement.'
                  : 'e.g. Employee retracted resignation after counter-offer.'}
                className="w-full px-4 py-3 rounded-xl border border-slate-200 bg-white text-sm font-medium text-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-500/30 resize-none"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={closeHrActionDialog} disabled={!!actionLoading}>
              Cancel
            </Button>
            <Button
              className={cn(
                'text-white',
                hrActionMode === 'expedite' ? 'bg-amber-600 hover:bg-amber-700' : 'bg-slate-900 hover:bg-slate-800',
              )}
              onClick={submitHrAction}
              disabled={!hrNote.trim() || !!actionLoading || (hrActionMode === 'expedite' && !expediteDate)}
            >
              {actionLoading ? <><Loader2 size={14} className="animate-spin mr-2" />Saving…</> :
                hrActionMode === 'expedite' ? 'Confirm expedite' : 'Confirm cancel'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

const ExitInterviewDisplay = ({ interview, resignationId, onUpdate }: { interview: any; resignationId: number; onUpdate: () => void }) => {
  const [hrRemarks, setHrRemarks] = useState(interview.hr_remarks || '');
  const [saving, setSaving] = useState(false);

  const reasons = [
    { key: 'reason_career', label: 'Better Career Opportunity' },
    { key: 'reason_studies', label: 'Higher Studies' },
    { key: 'reason_personal', label: 'Personal Reasons' },
    { key: 'reason_relocation', label: 'Relocation' },
    { key: 'reason_health', label: 'Health Reasons' },
    { key: 'reason_work_environment', label: 'Work Environment' },
    { key: 'reason_compensation', label: 'Compensation & Benefits' },
    { key: 'reason_relationship', label: 'Manager/Team Relationship' },
    { key: 'reason_role_mismatch', label: 'Role Mismatch' },
  ].filter(r => interview[r.key]);

  const ratingFields = [
    { key: 'rating_job_satisfaction', label: 'Job Satisfaction' },
    { key: 'rating_work_life_balance', label: 'Work-Life Balance' },
    { key: 'rating_team_cooperation', label: 'Team Cooperation' },
    { key: 'rating_management_communication', label: 'Mgmt Communication' },
    { key: 'rating_training_development', label: 'Training & Dev' },
    { key: 'rating_career_growth', label: 'Career Growth' },
    { key: 'rating_compensation', label: 'Compensation' },
    { key: 'rating_company_culture', label: 'Company Culture' },
  ];

  const handleSaveRemarks = async () => {
    setSaving(true);
    try {
      await client.post(ENDPOINTS.EXIT.EXIT_INTERVIEW_REMARKS(resignationId), { hr_remarks: hrRemarks });
      toast.success('Remarks saved');
      onUpdate();
    } catch { toast.error('Failed to save'); }
    finally { setSaving(false); }
  };

  return (
    <div className="space-y-6">
      {reasons.length > 0 && (
        <div>
          <p className="text-[9px] font-black text-slate-400 uppercase tracking-widest mb-2">Reasons for Leaving</p>
          <div className="flex flex-wrap gap-2">
            {reasons.map(r => <Badge key={r.key} className="bg-purple-100 text-purple-700 text-[9px] font-black uppercase">{r.label}</Badge>)}
          </div>
          {interview.reason_other && <p className="text-xs text-slate-500 mt-2">Other: {interview.reason_other}</p>}
          {interview.reason_explanation && <p className="text-xs text-slate-600 mt-2 italic">"{interview.reason_explanation}"</p>}
        </div>
      )}
      <div>
        <p className="text-[9px] font-black text-slate-400 uppercase tracking-widest mb-3">Work Experience Ratings</p>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {ratingFields.map(rf => {
            const val = interview[rf.key];
            if (!val) return null;
            return (
              <div key={rf.key} className="p-3 bg-slate-50 rounded-xl border border-slate-100">
                <p className="text-[9px] font-black text-slate-400 uppercase">{rf.label}</p>
                <div className="flex items-center gap-1 mt-1">
                  {[1, 2, 3, 4, 5].map(n => <Star key={n} size={14} className={n <= val ? 'text-amber-500 fill-amber-500' : 'text-slate-200'} />)}
                  <span className="text-xs font-black text-slate-600 ml-1">{val}/5</span>
                </div>
              </div>
            );
          })}
        </div>
      </div>
      {(interview.feedback_liked_most || interview.feedback_liked_least || interview.feedback_suggestions) && (
        <div className="space-y-3">
          <p className="text-[9px] font-black text-slate-400 uppercase tracking-widest">Open Feedback</p>
          {interview.feedback_liked_most && <div className="p-3 bg-green-50 rounded-xl border border-green-100"><p className="text-[9px] font-black text-green-600 uppercase mb-1">Liked Most</p><p className="text-sm text-green-800">{interview.feedback_liked_most}</p></div>}
          {interview.feedback_liked_least && <div className="p-3 bg-red-50 rounded-xl border border-red-100"><p className="text-[9px] font-black text-red-600 uppercase mb-1">Liked Least</p><p className="text-sm text-red-800">{interview.feedback_liked_least}</p></div>}
          {interview.feedback_suggestions && <div className="p-3 bg-blue-50 rounded-xl border border-blue-100"><p className="text-[9px] font-black text-blue-600 uppercase mb-1">Suggestions</p><p className="text-sm text-blue-800">{interview.feedback_suggestions}</p></div>}
        </div>
      )}
      <div className="p-4 bg-slate-50 rounded-xl border border-slate-200">
        <p className="text-[9px] font-black text-slate-400 uppercase tracking-widest mb-2">HR Remarks</p>
        <textarea value={hrRemarks} onChange={e => setHrRemarks(e.target.value)} rows={3} placeholder="Add HR remarks..." className="w-full bg-white border border-slate-200 rounded-xl px-4 py-3 text-sm outline-none resize-none mb-3" />
        <Button onClick={handleSaveRemarks} disabled={saving} className="h-9 px-5 bg-blue-600 text-white rounded-lg text-[9px] font-black uppercase hover:bg-blue-700 disabled:opacity-50">
          {saving ? 'Saving...' : 'Save Remarks'}
        </Button>
      </div>
    </div>
  );
};

const ClearanceModal = ({ resignationId, users, onClose, onSuccess }: {
  resignationId: number; users: any[]; onClose: () => void; onSuccess: () => void;
}) => {
  const [clearances, setClearances] = useState<{ department: string; assigned_to_id: number | ''; items: string[] }[]>([
    { department: '', assigned_to_id: '', items: [] },
  ]);
  const [deptOptions, setDeptOptions] = useState<any[]>([]);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    const loadDepartments = async () => {
      try {
        const res = await client.get(ENDPOINTS.ADMIN.DEPARTMENTS);
        setDeptOptions((res as any).data || []);
      } catch (err) {
        console.error('Failed to load departments', err);
      }
    };
    loadDepartments();
  }, []);

  const removeDept = (idx: number) => setClearances(prev => prev.filter((_, i) => i !== idx));

  const updateClearance = (idx: number, field: string, value: any) => {
    setClearances(prev => prev.map((c, i) => {
      if (i !== idx) return c;
      const updated = { ...c, [field]: value };
      if (field === 'department' && CLEARANCE_TEMPLATES[value]) updated.items = [...CLEARANCE_TEMPLATES[value]];
      return updated;
    }));
  };

  const handleSubmit = async () => {
    const valid = clearances.filter(c => c.department && c.assigned_to_id);
    if (!valid.length) { toast.error('Add at least one department with assigned user'); return; }
    setSubmitting(true);
    try {
      await client.post(ENDPOINTS.EXIT.INITIATE_CLEARANCE(resignationId), {
        clearances: valid.map(c => ({
          department: c.department,
          assigned_to_id: Number(c.assigned_to_id),
          items: c.items.map(i => ({ item_name: i })),
        })),
      });
      toast.success('Clearance initiated');
      onSuccess();
    } catch (e: any) {
      toast.error(errMsg(e, 'Failed'));
    } finally { setSubmitting(false); }
  };

  return (
    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[90vh] overflow-y-auto animate-in zoom-in-95 duration-200" onClick={e => e.stopPropagation()}>
        <div className="sticky top-0 z-10 p-6 border-b border-slate-100 bg-white flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2.5 bg-cyan-50 rounded-xl"><ShieldCheck size={20} className="text-cyan-600" /></div>
            <div>
              <h3 className="text-lg font-black text-[#0F172A] uppercase tracking-tight">Initiate Clearance</h3>
              <p className="text-[10px] text-slate-400 font-bold uppercase tracking-widest">Assign departments for clearance</p>
            </div>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-slate-100 rounded-lg"><XCircle size={20} className="text-slate-400" /></button>
        </div>
        <div className="p-6 space-y-4">
          {clearances.map((c, idx) => (
            <div key={idx} className="p-4 bg-slate-50 rounded-xl border border-slate-200 space-y-3">
              <div className="flex items-center justify-between">
                <p className="text-[10px] font-black text-slate-500 uppercase tracking-widest">Department {idx + 1}</p>
                <button onClick={() => removeDept(idx)} className="text-slate-400 hover:text-red-500"><Trash2 size={14} /></button>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-[9px] font-black text-slate-400 uppercase block mb-1">Department</label>
                  <select
                    value={c.department}
                    onChange={e => updateClearance(idx, 'department', e.target.value)}
                    disabled={deptOptions.length === 0}
                    className="w-full h-10 bg-white border border-slate-200 rounded-lg px-3 text-sm font-bold outline-none disabled:opacity-60"
                  >
                    <option value="">
                      {deptOptions.length === 0 ? 'No departments configured' : 'Select...'}
                    </option>
                    {deptOptions.map((d: any) => <option key={d.id} value={d.name}>{d.name}</option>)}
                  </select>
                </div>
                <div>
                  <label className="text-[9px] font-black text-slate-400 uppercase block mb-1">Assign To</label>
                  <select value={c.assigned_to_id} onChange={e => updateClearance(idx, 'assigned_to_id', e.target.value)} className="w-full h-10 bg-white border border-slate-200 rounded-lg px-3 text-sm font-bold outline-none">
                    <option value="">Select user...</option>
                    {users.map((u: any) => <option key={u.id} value={u.id}>{u.full_name} ({u.email})</option>)}
                  </select>
                </div>
              </div>
              {c.items.length > 0 && (
                <div className="space-y-1">
                  <p className="text-[9px] font-black text-slate-400 uppercase">Checklist Items</p>
                  {c.items.map((item, i) => (
                    <div key={i} className="flex items-center gap-2 text-xs text-slate-600">
                      <CheckCircle2 size={12} className="text-slate-300" /><span>{item}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
          <button onClick={() => setClearances(p => [...p, { department: '', assigned_to_id: '', items: [] }])} className="w-full p-3 border-2 border-dashed border-slate-200 rounded-xl text-xs font-black text-slate-400 uppercase hover:border-slate-300">+ Add Department</button>
        </div>
        <div className="sticky bottom-0 p-6 border-t border-slate-100 bg-white flex gap-3">
          <Button onClick={onClose} className="flex-1 h-11 bg-slate-100 text-slate-700 rounded-xl text-xs font-black uppercase hover:bg-slate-200">Cancel</Button>
          <Button onClick={handleSubmit} disabled={submitting} className="flex-1 h-11 bg-cyan-600 text-white rounded-xl text-xs font-black uppercase hover:bg-cyan-700 disabled:opacity-50">
            {submitting ? 'Submitting...' : 'Initiate Clearance'}
          </Button>
        </div>
      </div>
    </div>
  );
};
