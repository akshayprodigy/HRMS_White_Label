import React, { useMemo, useState, useEffect } from 'react';
import { Shield, Loader2 } from 'lucide-react';
import { Card, Button, Badge, cn } from './ui-elements';
import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';
import { toast } from 'sonner';
import { Dialog, DialogContent, DialogTitle, DialogFooter } from './ui/dialog';
import { Input } from './ui/input';

export const AdminView = () => {
  const [activeSubTab, setActiveSubTab] = useState<
    'users' | 'roles' | 'leave-types' | 'departments' | 'bid-line-items'
  >('users');
  const [users, setUsers] = useState<any[]>([]);
  const [roles, setRoles] = useState<any[]>([]);
  const [permissions, setPermissions] = useState<any[]>([]);
  const [leaveTypes, setLeaveTypes] = useState<any[]>([]);
  const [departments, setDepartments] = useState<any[]>([]);
  const [bidLineItems, setBidLineItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const [isUserModalOpen, setIsUserModalOpen] = useState(false);
  const [editingUser, setEditingUser] = useState<any>(null);
  const [userFormData, setUserFormData] = useState({ email: '', full_name: '', password: '', role_ids: [] as number[] });

  const [isLeaveTypeModalOpen, setIsLeaveTypeModalOpen] = useState(false);
  const [editingLeaveType, setEditingLeaveType] = useState<any>(null);
  const [leaveTypeFormData, setLeaveTypeFormData] = useState({ name: '', is_unpaid: false });

  const [isDeptModalOpen, setIsDeptModalOpen] = useState(false);
  const [editingDept, setEditingDept] = useState<any>(null);
  const [deptFormData, setDeptFormData] = useState({ name: '', description: '', is_active: true });

  const [isRoleModalOpen, setIsRoleModalOpen] = useState(false);
  const [editingRole, setEditingRole] = useState<any>(null);
  const [roleFormData, setRoleFormData] = useState({
    name: '',
    description: '',
    permission_ids: [] as number[],
  });

  const [isBidLineItemModalOpen, setIsBidLineItemModalOpen] = useState(false);
  const [editingBidLineItem, setEditingBidLineItem] = useState<any>(null);
  const [bidLineItemFormData, setBidLineItemFormData] = useState({
    title: '',
    description: '',
    is_active: true,
  });

  useEffect(() => { fetchData(); }, [activeSubTab]);

  const tabs = useMemo(
    () =>
      [
        { key: 'users' as const, label: 'Users', count: users.length },
        { key: 'roles' as const, label: 'Roles', count: roles.length },
        { key: 'leave-types' as const, label: 'Leave Types', count: leaveTypes.length },
        { key: 'departments' as const, label: 'Departments', count: departments.length },
        { key: 'bid-line-items' as const, label: 'Bid Line Items', count: bidLineItems.length },
      ],
    [users.length, roles.length, leaveTypes.length, departments.length, bidLineItems.length],
  );

  const resetUserModal = () => {
    setEditingUser(null);
    setUserFormData({ email: '', full_name: '', password: '', role_ids: [] });
  };

  const resetRoleModal = () => {
    setEditingRole(null);
    setRoleFormData({ name: '', description: '', permission_ids: [] });
  };

  const resetLeaveTypeModal = () => {
    setEditingLeaveType(null);
    setLeaveTypeFormData({ name: '', is_unpaid: false });
  };

  const resetDeptModal = () => {
    setEditingDept(null);
    setDeptFormData({ name: '', description: '', is_active: true });
  };

  const resetBidLineItemModal = () => {
    setEditingBidLineItem(null);
    setBidLineItemFormData({ title: '', description: '', is_active: true });
  };

  const fetchData = async () => {
    setLoading(true);
    setErrorMessage(null);
    try {
      if (activeSubTab === 'users') {
        const res = await client.get(ENDPOINTS.ADMIN.USERS);
        setUsers((res as any).data?.items || (res as any).data || []);
      } else if (activeSubTab === 'roles') {
        const [rolesRes, permsRes] = await Promise.all([
          client.get(ENDPOINTS.ADMIN.ROLES),
          client.get(ENDPOINTS.ADMIN.PERMISSIONS),
        ]);
        setRoles((rolesRes as any).data?.items || (rolesRes as any).data || []);
        setPermissions((permsRes as any).data?.items || (permsRes as any).data || []);
      } else if (activeSubTab === 'leave-types') {
        const res = await client.get(ENDPOINTS.ADMIN.LEAVE_TYPES);
        setLeaveTypes((res as any).data || []);
      } else if (activeSubTab === 'departments') {
        const res = await client.get(ENDPOINTS.ADMIN.DEPARTMENTS);
        setDepartments((res as any).data || []);
      } else if (activeSubTab === 'bid-line-items') {
        const res = await client.get(ENDPOINTS.ADMIN.BID_LINE_ITEMS);
        setBidLineItems((res as any).data || []);
      }
    } catch (e: any) {
      const msg = e?.response?.data?.error?.message || 'Load failed';
      setErrorMessage(msg);
      toast.error(msg);
    } finally { setLoading(false); }
  };

  const handleSaveUser = async () => {
    try {
      if (editingUser) await client.patch(ENDPOINTS.ADMIN.USER_DETAIL(editingUser.id), userFormData);
      else await client.post(ENDPOINTS.ADMIN.USERS, userFormData);
      setIsUserModalOpen(false); fetchData();
      toast.success('User updated');
    } catch (e) { toast.error('Save failed'); }
  };

  const handleSaveLeaveType = async () => {
    try {
      if (editingLeaveType) await client.patch(ENDPOINTS.ADMIN.LEAVE_TYPE_DETAIL(editingLeaveType.id), leaveTypeFormData);
      else await client.post(ENDPOINTS.ADMIN.LEAVE_TYPES, leaveTypeFormData);
      setIsLeaveTypeModalOpen(false);
      fetchData();
      toast.success('Leave type saved');
    } catch (e) {
      toast.error('Save failed');
    }
  };

  const handleDeleteLeaveType = async (id: number) => {
    if (!confirm('Are you sure you want to delete this leave type?')) return;
    try {
      await client.delete(ENDPOINTS.ADMIN.LEAVE_TYPE_DETAIL(id));
      fetchData();
      toast.success('Leave type deleted');
    } catch (e) {
      toast.error('Delete failed');
    }
  };

  const handleSaveDept = async () => {
    try {
      if (editingDept) await client.patch(ENDPOINTS.ADMIN.DEPARTMENT_DETAIL(editingDept.id), deptFormData);
      else await client.post(ENDPOINTS.ADMIN.DEPARTMENTS, deptFormData);
      setIsDeptModalOpen(false);
      fetchData();
      toast.success('Department saved');
    } catch (e) {
      toast.error('Save failed');
    }
  };

  const handleDeleteDept = async (id: number) => {
    if (!confirm('Are you sure you want to delete this department?')) return;
    try {
      await client.delete(ENDPOINTS.ADMIN.DEPARTMENT_DETAIL(id));
      fetchData();
      toast.success('Department deleted');
    } catch (e) {
      toast.error('Delete failed');
    }
  };

  const handleSaveRole = async () => {
    try {
      if (editingRole) {
        await client.patch(
          ENDPOINTS.ADMIN.ROLE_DETAIL(editingRole.id),
          roleFormData
        );
      } else {
        await client.post(ENDPOINTS.ADMIN.ROLES, roleFormData);
      }
      setIsRoleModalOpen(false);
      fetchData();
      toast.success('Role saved');
    } catch (e: any) {
      toast.error(e.response?.data?.error?.message || 'Save failed');
    }
  };

  const handleDeleteRole = async (id: number) => {
    if (!confirm('Are you sure you want to delete this role?')) return;
    try {
      await client.delete(ENDPOINTS.ADMIN.ROLE_DETAIL(id));
      fetchData();
      toast.success('Role deleted');
    } catch (e: any) {
      toast.error(e.response?.data?.error?.message || 'Delete failed');
    }
  };

  const handleSaveBidLineItem = async () => {
    try {
      const payload = {
        title: bidLineItemFormData.title.trim(),
        description: bidLineItemFormData.description?.trim() || null,
        is_active: !!bidLineItemFormData.is_active,
      };

      if (!payload.title) {
        toast.error('Title is required');
        return;
      }

      if (editingBidLineItem) {
        await client.patch(
          ENDPOINTS.ADMIN.BID_LINE_ITEM_DETAIL(editingBidLineItem.id),
          payload,
        );
      } else {
        await client.post(ENDPOINTS.ADMIN.BID_LINE_ITEMS, payload);
      }

      setIsBidLineItemModalOpen(false);
      resetBidLineItemModal();
      fetchData();
      toast.success('Bid line item saved');
    } catch (e: any) {
      toast.error(e.response?.data?.error?.message || 'Save failed');
    }
  };

  const handleDeleteBidLineItem = async (id: number) => {
    if (!confirm('Delete this bid line item?')) return;
    try {
      await client.delete(ENDPOINTS.ADMIN.BID_LINE_ITEM_DETAIL(id));
      fetchData();
      toast.success('Bid line item deleted');
    } catch (e: any) {
      toast.error(e.response?.data?.error?.message || 'Delete failed');
    }
  };

  return (
    <div className="flex-1 overflow-auto bg-slate-50/50">
      <div className="p-8 max-w-[1600px] mx-auto space-y-8">
        <div className="flex flex-col gap-4 sm:flex-row sm:justify-between sm:items-center">
          <div>
            <h1 className="text-2xl font-black text-slate-900 flex items-center gap-3 tracking-tight">
              <Shield className="text-indigo-600" /> Administrative Controls
            </h1>
            <p className="text-xs font-bold text-slate-400 uppercase tracking-widest mt-1">
              Manage users, roles, leave policies, and departments
            </p>
          </div>
          {activeSubTab === 'users' && (
            <Button
              onClick={() => {
                resetUserModal();
                setIsUserModalOpen(true);
              }}
              className="bg-indigo-600 text-white rounded-xl"
            >
              Add User
            </Button>
          )}
          {activeSubTab === 'roles' && (
            <Button
              onClick={() => {
                resetRoleModal();
                setIsRoleModalOpen(true);
              }}
              className="bg-indigo-600 text-white rounded-xl"
            >
              Add Role
            </Button>
          )}
          {activeSubTab === 'leave-types' && (
            <Button
              onClick={() => {
                resetLeaveTypeModal();
                setIsLeaveTypeModalOpen(true);
              }}
              className="bg-indigo-600 text-white rounded-xl"
            >
              Add Leave Type
            </Button>
          )}
          {activeSubTab === 'departments' && (
            <Button
              onClick={() => {
                resetDeptModal();
                setIsDeptModalOpen(true);
              }}
              className="bg-indigo-600 text-white rounded-xl"
            >
              Add Department
            </Button>
          )}
          {activeSubTab === 'bid-line-items' && (
            <Button
              onClick={() => {
                resetBidLineItemModal();
                setIsBidLineItemModalOpen(true);
              }}
              className="bg-indigo-600 text-white rounded-xl"
            >
              Add Bid Line Item
            </Button>
          )}
        </div>

        <div className="w-full max-w-full overflow-x-auto scrollbar-none">
          <div className="flex gap-1 p-1 bg-slate-200/50 rounded-2xl w-max min-w-max">
            {tabs.map((tab) => (
              <button
                key={tab.key}
                onClick={() => setActiveSubTab(tab.key)}
                className={cn(
                  "px-5 py-2 rounded-xl text-xs font-bold uppercase transition-all whitespace-nowrap",
                  activeSubTab === tab.key
                    ? "bg-white text-indigo-600 shadow-sm"
                    : "text-slate-500",
                  "focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-600 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-100",
                )}
              >
                <span className="flex items-center gap-2">
                  <span>{tab.label}</span>
                  <span
                    className={cn(
                      "text-[10px] font-black px-2 py-0.5 rounded-lg",
                      activeSubTab === tab.key
                        ? "bg-indigo-50 text-indigo-600"
                        : "bg-slate-100 text-slate-500",
                    )}
                  >
                    {tab.count}
                  </span>
                </span>
              </button>
            ))}
          </div>
        </div>

        {loading ? (
          <div className="py-20 flex flex-col items-center justify-center gap-3">
            <Loader2 className="animate-spin text-indigo-600" />
            <p className="text-xs font-bold text-slate-400 uppercase tracking-widest">Loading</p>
          </div>
        ) : (
          <Card className="bg-white border-slate-200 rounded-2xl overflow-hidden shadow-sm">
            {errorMessage ? (
              <div className="p-8">
                <div className="rounded-2xl border border-amber-200 bg-amber-50 p-6">
                  <p className="text-sm font-black text-amber-800 tracking-tight">Unable to load data</p>
                  <p className="text-xs font-bold text-amber-700 uppercase tracking-widest mt-2">
                    {errorMessage}
                  </p>
                  <div className="mt-4">
                    <Button variant="outline" className="rounded-xl" onClick={fetchData}>Retry</Button>
                  </div>
                </div>
              </div>
            ) : (
              <div className="w-full overflow-x-auto">
                <table className="w-full min-w-[720px] text-left">
                  <thead className="bg-slate-50 border-b border-slate-100 text-[11px] font-black text-slate-400 uppercase tracking-widest">
                    {activeSubTab === 'users' && (
                      <tr>
                        <th className="px-8 py-5">User</th>
                        <th className="px-8 py-5">Email</th>
                        <th className="px-8 py-5">Roles</th>
                        <th className="px-8 py-5 text-right">Actions</th>
                      </tr>
                    )}
                    {activeSubTab === 'roles' && (
                      <tr>
                        <th className="px-8 py-5">Role</th>
                        <th className="px-8 py-5">Description</th>
                        <th className="px-8 py-5">Permissions</th>
                        <th className="px-8 py-5 text-right">Actions</th>
                      </tr>
                    )}
                    {activeSubTab === 'leave-types' && (
                      <tr>
                        <th className="px-8 py-5">Leave Type</th>
                        <th className="px-8 py-5">Policy</th>
                        <th className="px-8 py-5 text-right">Actions</th>
                      </tr>
                    )}
                    {activeSubTab === 'departments' && (
                      <tr>
                        <th className="px-8 py-5">Department</th>
                        <th className="px-8 py-5">Description</th>
                        <th className="px-8 py-5">Status</th>
                        <th className="px-8 py-5 text-right">Actions</th>
                      </tr>
                    )}
                    {activeSubTab === 'bid-line-items' && (
                      <tr>
                        <th className="px-8 py-5">Title</th>
                        <th className="px-8 py-5">Description</th>
                        <th className="px-8 py-5">Status</th>
                        <th className="px-8 py-5 text-right">Actions</th>
                      </tr>
                    )}
                  </thead>

                  <tbody className="divide-y divide-slate-50">
                {activeSubTab === 'users' && users.map((user) => (
                  <tr key={user.id} className="group hover:bg-slate-50/50">
                    <td className="px-8 py-6 font-black text-slate-900 tracking-tight">{user.full_name}</td>
                    <td className="px-8 py-6 text-slate-500 text-sm">{user.email}</td>
                    <td className="px-8 py-6">
                      <div className="flex flex-wrap gap-2">
                        {(user.roles || []).slice(0, 3).map((r: any) => (
                          <Badge key={r.id} variant="neutral">{r.name}</Badge>
                        ))}
                        {(user.roles || []).length > 3 ? (
                          <Badge variant="neutral">+{(user.roles || []).length - 3}</Badge>
                        ) : null}
                        {(user.roles || []).length === 0 ? (
                          <span className="text-xs font-bold text-slate-400 uppercase tracking-widest">No roles</span>
                        ) : null}
                      </div>
                    </td>
                    <td className="px-8 py-6 text-right whitespace-nowrap">
                      <Button size="sm" variant="outline" onClick={() => {
                        setEditingUser(user);
                        setUserFormData({email:user.email, full_name:user.full_name, password:'', role_ids:user.roles?.map((r:any)=>r.id)||[]});
                        setIsUserModalOpen(true);
                      }} className="text-indigo-600">Edit</Button>
                    </td>
                  </tr>
                ))}
                {activeSubTab === 'users' && users.length === 0 ? (
                  <tr>
                    <td colSpan={4} className="px-8 py-14 text-center">
                      <p className="text-sm font-black text-slate-900 tracking-tight">No users found</p>
                      <p className="text-xs font-bold text-slate-400 uppercase tracking-widest mt-2">Create your first user to get started</p>
                    </td>
                  </tr>
                ) : null}
                {activeSubTab === 'leave-types' && leaveTypes.map((type) => (
                  <tr key={type.id} className="group hover:bg-slate-50/50">
                    <td className="px-8 py-6 font-black text-slate-900 tracking-tight">{type.name}</td>
                    <td className="px-8 py-6 text-slate-500 text-sm">{type.unpaid_allowed ? 'Unpaid' : 'Standard policy'}</td>
                    <td className="px-8 py-6 text-right space-x-2 whitespace-nowrap">
                      <Button size="sm" variant="outline" onClick={() => {
                        setEditingLeaveType(type);
                        setLeaveTypeFormData({name: type.name, is_unpaid: type.unpaid_allowed});
                        setIsLeaveTypeModalOpen(true);
                      }} className="text-indigo-600">Edit</Button>
                      <Button size="sm" variant="outline" onClick={() => handleDeleteLeaveType(type.id)} className="text-red-600">Delete</Button>
                    </td>
                  </tr>
                ))}
                {activeSubTab === 'leave-types' && leaveTypes.length === 0 ? (
                  <tr>
                    <td colSpan={3} className="px-8 py-14 text-center">
                      <p className="text-sm font-black text-slate-900 tracking-tight">No leave types configured</p>
                      <p className="text-xs font-bold text-slate-400 uppercase tracking-widest mt-2">Create a leave type to define policies</p>
                    </td>
                  </tr>
                ) : null}
                {activeSubTab === 'roles' && roles.map((role) => (
                  <tr key={role.id} className="group hover:bg-slate-50/50">
                    <td className="px-8 py-6 font-black text-slate-900 tracking-tight">{role.name}</td>
                    <td className="px-8 py-6 text-slate-500 text-sm">{role.description || '—'}</td>
                    <td className="px-8 py-6">
                      <Badge variant="neutral">{(role.permissions || []).length} permissions</Badge>
                    </td>
                    <td className="px-8 py-6 text-right space-x-2 whitespace-nowrap">
                      <Button size="sm" variant="outline" onClick={() => {
                        setEditingRole(role);
                        setRoleFormData({
                          name: role.name || '',
                          description: role.description || '',
                          permission_ids: (role.permissions || []).map((p: any) => p.id),
                        });
                        setIsRoleModalOpen(true);
                      }} className="text-indigo-600">Edit</Button>
                      <Button size="sm" variant="outline" onClick={() => handleDeleteRole(role.id)} className="text-red-600">Delete</Button>
                    </td>
                  </tr>
                ))}
                {activeSubTab === 'roles' && roles.length === 0 ? (
                  <tr>
                    <td colSpan={4} className="px-8 py-14 text-center">
                      <p className="text-sm font-black text-slate-900 tracking-tight">No roles created</p>
                      <p className="text-xs font-bold text-slate-400 uppercase tracking-widest mt-2">Add roles to control permissions</p>
                    </td>
                  </tr>
                ) : null}
                {activeSubTab === 'departments' && departments.map((dept) => (
                  <tr key={dept.id} className="group hover:bg-slate-50/50">
                    <td className="px-8 py-6 font-black text-slate-900 tracking-tight">{dept.name}</td>
                    <td className="px-8 py-6 text-slate-500 text-sm">{dept.description || '—'}</td>
                    <td className="px-8 py-6">
                      <Badge variant={dept.is_active ? 'success' : 'neutral'}>
                        {dept.is_active ? 'Active' : 'Inactive'}
                      </Badge>
                    </td>
                    <td className="px-8 py-6 text-right space-x-2 whitespace-nowrap">
                      <Button size="sm" variant="outline" onClick={() => {
                        setEditingDept(dept);
                        setDeptFormData({name: dept.name, description: dept.description || '', is_active: dept.is_active});
                        setIsDeptModalOpen(true);
                      }} className="text-indigo-600">Edit</Button>
                      <Button size="sm" variant="outline" onClick={() => handleDeleteDept(dept.id)} className="text-red-600">Delete</Button>
                    </td>
                  </tr>
                ))}
                {activeSubTab === 'departments' && departments.length === 0 ? (
                  <tr>
                    <td colSpan={4} className="px-8 py-14 text-center">
                      <p className="text-sm font-black text-slate-900 tracking-tight">No departments found</p>
                      <p className="text-xs font-bold text-slate-400 uppercase tracking-widest mt-2">Create departments to organize teams</p>
                    </td>
                  </tr>
                ) : null}
                {activeSubTab === 'bid-line-items' && bidLineItems.map((item) => (
                  <tr key={item.id} className="group hover:bg-slate-50/50">
                    <td className="px-8 py-6 font-black text-slate-900 tracking-tight">
                      {item.title}
                    </td>
                    <td className="px-8 py-6 text-slate-500 text-sm">
                      {item.description || '—'}
                    </td>
                    <td className="px-8 py-6">
                      <Badge variant={item.is_active ? 'success' : 'neutral'}>
                        {item.is_active ? 'Active' : 'Inactive'}
                      </Badge>
                    </td>
                    <td className="px-8 py-6 text-right space-x-2 whitespace-nowrap">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => {
                          setEditingBidLineItem(item);
                          setBidLineItemFormData({
                            title: item.title || '',
                            description: item.description || '',
                            is_active: !!item.is_active,
                          });
                          setIsBidLineItemModalOpen(true);
                        }}
                        className="text-indigo-600"
                      >
                        Edit
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => handleDeleteBidLineItem(item.id)}
                        className="text-red-600"
                      >
                        Delete
                      </Button>
                    </td>
                  </tr>
                ))}
                {activeSubTab === 'bid-line-items' && bidLineItems.length === 0 ? (
                  <tr>
                    <td colSpan={4} className="px-8 py-14 text-center">
                      <p className="text-sm font-black text-slate-900 tracking-tight">No bid line items</p>
                      <p className="text-xs font-bold text-slate-400 uppercase tracking-widest mt-2">Add templates for BD bid tasks</p>
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
            </div>
            )}
          </Card>
        )}

        <Dialog open={isUserModalOpen} onOpenChange={setIsUserModalOpen}>
          <DialogContent className="max-w-md p-0 overflow-hidden rounded-3xl border-none">
            <div className="bg-indigo-600 p-8 text-white"><DialogTitle className="text-2xl font-bold">User Identity</DialogTitle></div>
            <div className="p-8 space-y-4">
              <div className="space-y-2">
                <label className="text-sm font-semibold text-slate-700">Full Name</label>
                <Input placeholder="e.g. Alex Smith" value={userFormData.full_name} onChange={(e) => setUserFormData({...userFormData, full_name: e.target.value})} className="h-11 rounded-xl bg-slate-50" />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-semibold text-slate-700">Email</label>
                <Input placeholder="e.g. alex@company.com" value={userFormData.email} onChange={(e) => setUserFormData({...userFormData, email: e.target.value})} className="h-11 rounded-xl bg-slate-50" />
              </div>
            </div>
            <DialogFooter className="p-8 pt-0"><Button onClick={handleSaveUser} className="bg-indigo-600 text-white rounded-xl w-full h-11">Save Settings</Button></DialogFooter>
          </DialogContent>
        </Dialog>

        <Dialog open={isLeaveTypeModalOpen} onOpenChange={setIsLeaveTypeModalOpen}>
          <DialogContent className="max-w-md p-0 overflow-hidden rounded-3xl border-none">
            <div className="bg-indigo-600 p-8 text-white"><DialogTitle className="text-2xl font-bold">Leave Type Definition</DialogTitle></div>
            <div className="p-8 space-y-6">
              <div className="space-y-2">
                <label className="text-sm font-semibold text-slate-700">Type Name</label>
                <Input 
                  placeholder="e.g. Annual Leave" 
                  value={leaveTypeFormData.name} 
                  onChange={(e) => setLeaveTypeFormData({...leaveTypeFormData, name: e.target.value})} 
                  className="h-11 rounded-xl bg-slate-50" 
                />
              </div>
              <div className="flex items-center gap-3 p-4 bg-slate-50 rounded-2xl">
                <input 
                  type="checkbox" 
                  id="is_unpaid"
                  checked={leaveTypeFormData.is_unpaid} 
                  onChange={(e) => setLeaveTypeFormData({...leaveTypeFormData, is_unpaid: e.target.checked})}
                  className="w-5 h-5 rounded border-slate-300 text-indigo-600 focus:ring-indigo-600"
                />
                <label htmlFor="is_unpaid" className="text-sm font-medium text-slate-700 cursor-pointer">Unpaid Leave Type</label>
              </div>
            </div>
            <DialogFooter className="p-8 pt-0">
              <Button onClick={handleSaveLeaveType} className="bg-indigo-600 text-white rounded-xl w-full h-11">
                {editingLeaveType ? 'Update Type' : 'Create Leave Type'}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        <Dialog open={isDeptModalOpen} onOpenChange={setIsDeptModalOpen}>
          <DialogContent className="max-w-md p-0 overflow-hidden rounded-3xl border-none">
            <div className="bg-indigo-600 p-8 text-white"><DialogTitle className="text-2xl font-bold">Department Configuration</DialogTitle></div>
            <div className="p-8 space-y-6">
              <div className="space-y-2">
                <label className="text-sm font-semibold text-slate-700">Department Name</label>
                <Input 
                  placeholder="e.g. Engineering" 
                  value={deptFormData.name} 
                  onChange={(e) => setDeptFormData({...deptFormData, name: e.target.value})} 
                  className="h-11 rounded-xl bg-slate-50" 
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-semibold text-slate-700">Description</label>
                <Input 
                  placeholder="Core software development team" 
                  value={deptFormData.description} 
                  onChange={(e) => setDeptFormData({...deptFormData, description: e.target.value})} 
                  className="h-11 rounded-xl bg-slate-50" 
                />
              </div>
            </div>
            <DialogFooter className="p-8 pt-0">
              <Button onClick={handleSaveDept} className="bg-indigo-600 text-white rounded-xl w-full h-11">
                {editingDept ? 'Update Department' : 'Create Department'}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        <Dialog open={isRoleModalOpen} onOpenChange={setIsRoleModalOpen}>
          <DialogContent
            className="w-full max-w-md p-0 rounded-3xl border-none overflow-y-auto overflow-x-hidden"
            style={{ maxHeight: "70vh" }}
          >
            <div className="bg-indigo-600 p-8 text-white">
              <DialogTitle className="text-2xl font-bold">Role Management</DialogTitle>
            </div>
            <div className="p-8 space-y-6">
              <div className="space-y-2">
                <label className="text-sm font-semibold text-slate-700">Role Name</label>
                <Input
                  placeholder="e.g. Client Manager"
                  value={roleFormData.name}
                  onChange={(e) => setRoleFormData({ ...roleFormData, name: e.target.value })}
                  className="h-11 rounded-xl bg-slate-50"
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-semibold text-slate-700">Description</label>
                <Input
                  placeholder="Optional"
                  value={roleFormData.description}
                  onChange={(e) => setRoleFormData({ ...roleFormData, description: e.target.value })}
                  className="h-11 rounded-xl bg-slate-50"
                />
              </div>

              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <label className="text-sm font-semibold text-slate-700">Permissions</label>
                  <Badge variant="neutral">{roleFormData.permission_ids.length} selected</Badge>
                </div>
                <div className="rounded-2xl border border-slate-200 bg-white">
                  {(permissions || []).map((perm) => {
                    const checked = roleFormData.permission_ids.includes(perm.id);
                    return (
                      <label
                        key={perm.id}
                        className="flex items-center gap-3 px-4 py-3 text-sm border-b border-slate-100 last:border-b-0 cursor-pointer hover:bg-slate-50"
                      >
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={(e) => {
                            const next = new Set(roleFormData.permission_ids);
                            if (e.target.checked) next.add(perm.id);
                            else next.delete(perm.id);
                            setRoleFormData({
                              ...roleFormData,
                              permission_ids: Array.from(next),
                            });
                          }}
                          className="w-4 h-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-600"
                        />
                        <span className="text-slate-800 font-medium">{perm.name}</span>
                      </label>
                    );
                  })}
                  {(permissions || []).length === 0 ? (
                    <div className="px-4 py-6 text-sm text-slate-500">No permissions found.</div>
                  ) : null}
                </div>
              </div>
            </div>
            <DialogFooter className="p-8 pt-0 shrink-0">
              <Button onClick={handleSaveRole} className="bg-indigo-600 text-white rounded-xl w-full h-11">
                {editingRole ? 'Update Role' : 'Create Role'}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        <Dialog
          open={isBidLineItemModalOpen}
          onOpenChange={(open: boolean) => {
            setIsBidLineItemModalOpen(open);
            if (!open) resetBidLineItemModal();
          }}
        >
          <DialogContent className="max-w-md p-0 overflow-hidden rounded-3xl border-none">
            <div className="bg-indigo-600 p-8 text-white">
              <DialogTitle className="text-2xl font-bold">
                {editingBidLineItem ? 'Edit Bid Line Item' : 'Add Bid Line Item'}
              </DialogTitle>
            </div>
            <div className="p-8 space-y-6">
              <div className="space-y-2">
                <label className="text-sm font-semibold text-slate-700">Title</label>
                <Input
                  placeholder="e.g. Scope clarification"
                  value={bidLineItemFormData.title}
                  onChange={(e) =>
                    setBidLineItemFormData({
                      ...bidLineItemFormData,
                      title: e.target.value,
                    })
                  }
                  className="h-11 rounded-xl bg-slate-50"
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-semibold text-slate-700">Description</label>
                <Input
                  placeholder="Optional"
                  value={bidLineItemFormData.description}
                  onChange={(e) =>
                    setBidLineItemFormData({
                      ...bidLineItemFormData,
                      description: e.target.value,
                    })
                  }
                  className="h-11 rounded-xl bg-slate-50"
                />
              </div>
              <div className="flex items-center gap-3 p-4 bg-slate-50 rounded-2xl">
                <input
                  id="bid_line_item_active"
                  type="checkbox"
                  checked={bidLineItemFormData.is_active}
                  onChange={(e) =>
                    setBidLineItemFormData({
                      ...bidLineItemFormData,
                      is_active: e.target.checked,
                    })
                  }
                  className="w-5 h-5 rounded border-slate-300 text-indigo-600 focus:ring-indigo-600"
                />
                <label
                  htmlFor="bid_line_item_active"
                  className="text-sm font-medium text-slate-700 cursor-pointer"
                >
                  Active
                </label>
              </div>
            </div>
            <DialogFooter className="p-8 pt-0">
              <Button
                onClick={handleSaveBidLineItem}
                className="bg-indigo-600 text-white rounded-xl w-full h-11"
              >
                {editingBidLineItem ? 'Update Item' : 'Create Item'}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    </div>
  );
};
