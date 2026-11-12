import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { Plus, RefreshCw, Users } from 'lucide-react';
import { Card, Button, Badge } from './ui-elements';
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

interface Delegation {
  id: number;
  grantee_id: number;
  grantee_name: string | null;
  scope_type: 'employees' | 'department' | 'location' | 'team';
  scope_value: string | null;
  employee_ids: number[];
  can_publish: boolean;
  can_approve_changes: boolean;
  valid_from: string;
  valid_to: string | null;
  revoked_at: string | null;
  granted_by_name: string | null;
  note: string | null;
  covered_count: number;
}
interface UserLite {
  id: number;
  email: string;
  full_name: string | null;
}
interface PreviewRow {
  user_id: number;
  full_name: string | null;
  department: string | null;
}

const todayIso = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(
    d.getDate()
  ).padStart(2, '0')}`;
};

export const errMsg = (err: any, fallback: string) => {
  const data = err?.response?.data;
  if (typeof data?.detail === 'string') return data.detail;
  if (typeof data?.error?.message === 'string') return data.error.message;
  return fallback;
};

export const scopeLabel = (d: {
  scope_type: string;
  scope_value: string | null;
  employee_ids: number[];
}) => {
  switch (d.scope_type) {
    case 'department':
      return `Department: ${d.scope_value}`;
    case 'location':
      return `Location: ${d.scope_value}`;
    case 'team':
      return 'Their reporting team';
    default:
      return `${d.employee_ids.length} selected employee${
        d.employee_ids.length === 1 ? '' : 's'
      }`;
  }
};

const statusOf = (d: Delegation): 'active' | 'expired' | 'revoked' | 'upcoming' => {
  if (d.revoked_at) return 'revoked';
  const t = todayIso();
  if (d.valid_to && d.valid_to < t) return 'expired';
  if (d.valid_from > t) return 'upcoming';
  return 'active';
};

const fieldCls =
  'px-3 py-1.5 border rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500';

export const ScheduleDelegations = () => {
  const [rows, setRows] = useState<Delegation[]>([]);
  const [loading, setLoading] = useState(false);
  const [showInactive, setShowInactive] = useState(false);
  const [confirmRevoke, setConfirmRevoke] = useState<number | null>(null);

  const [users, setUsers] = useState<UserLite[]>([]);
  const [departments, setDepartments] = useState<any[]>([]);

  // dialog (create + edit)
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<Delegation | null>(null);
  const [granteeId, setGranteeId] = useState<number | ''>('');
  const [granteeSearch, setGranteeSearch] = useState('');
  const [scopeType, setScopeType] = useState<Delegation['scope_type']>('department');
  const [scopeValue, setScopeValue] = useState('');
  const [empIds, setEmpIds] = useState<number[]>([]);
  const [empSearch, setEmpSearch] = useState('');
  const [canPublish, setCanPublish] = useState(false);
  const [canApprove, setCanApprove] = useState(false);
  const [validFrom, setValidFrom] = useState(todayIso());
  const [validTo, setValidTo] = useState('');
  const [note, setNote] = useState('');
  const [saving, setSaving] = useState(false);
  const [preview, setPreview] = useState<PreviewRow[] | null>(null);

  const fetchRows = useCallback(async () => {
    setLoading(true);
    try {
      const res = await client.get<Delegation[]>(
        `${ENDPOINTS.ROSTER.DELEGATIONS}?include_inactive=${showInactive}`
      );
      setRows(res.data || []);
    } catch (err: any) {
      toast.error(errMsg(err, 'Failed to load delegations'));
    } finally {
      setLoading(false);
    }
  }, [showInactive]);

  useEffect(() => {
    fetchRows();
  }, [fetchRows]);

  useEffect(() => {
    (async () => {
      try {
        const [u, d] = await Promise.all([
          client.get(ENDPOINTS.HR.USERS),
          client.get(ENDPOINTS.HR.DEPARTMENTS),
        ]);
        setUsers((u as any).data || []);
        setDepartments((d as any).data || []);
      } catch (err) {
        console.error('Failed to load users/departments', err);
      }
    })();
  }, []);

  const userName = useCallback(
    (id: number) => {
      const u = users.find((x) => x.id === id);
      return u ? u.full_name || u.email : `User #${id}`;
    },
    [users]
  );

  const openCreate = () => {
    setEditing(null);
    setGranteeId('');
    setGranteeSearch('');
    setScopeType('department');
    setScopeValue('');
    setEmpIds([]);
    setEmpSearch('');
    setCanPublish(false);
    setCanApprove(false);
    setValidFrom(todayIso());
    setValidTo('');
    setNote('');
    setPreview(null);
    setDialogOpen(true);
  };

  const openEdit = (d: Delegation) => {
    setEditing(d);
    setGranteeId(d.grantee_id);
    setScopeType(d.scope_type);
    setScopeValue(d.scope_value || '');
    setEmpIds(d.employee_ids || []);
    setCanPublish(d.can_publish);
    setCanApprove(d.can_approve_changes);
    setValidFrom(d.valid_from);
    setValidTo(d.valid_to || '');
    setNote(d.note || '');
    setPreview(null);
    setDialogOpen(true);
  };

  const scopeReady =
    scopeType === 'team' ||
    (scopeType === 'employees' ? empIds.length > 0 : scopeValue.trim() !== '');

  // Debounced live preview (create mode only)
  useEffect(() => {
    if (!dialogOpen || editing || !scopeReady) {
      setPreview(null);
      return;
    }
    if (scopeType === 'team' && granteeId === '') {
      setPreview(null);
      return;
    }
    let cancelled = false;
    const t = setTimeout(async () => {
      try {
        const params = new URLSearchParams({ scope_type: scopeType });
        if (scopeType === 'department' || scopeType === 'location') {
          params.set('scope_value', scopeValue.trim());
        }
        if (scopeType === 'employees') {
          empIds.forEach((id) => params.append('employee_ids', String(id)));
        }
        if (granteeId !== '') params.set('grantee_id', String(granteeId));
        const res = await client.get<PreviewRow[]>(
          `${ENDPOINTS.ROSTER.DELEGATION_PREVIEW}?${params.toString()}`
        );
        if (!cancelled) setPreview(res.data || []);
      } catch {
        if (!cancelled) setPreview(null);
      }
    }, 350);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [dialogOpen, editing, scopeType, scopeValue, empIds, granteeId, scopeReady]);

  const save = async () => {
    if (validTo && validTo < validFrom) {
      toast.error('"Valid to" must not be before "valid from"');
      return;
    }
    setSaving(true);
    try {
      if (editing) {
        await client.patch(ENDPOINTS.ROSTER.DELEGATION_DETAIL(editing.id), {
          can_publish: canPublish,
          can_approve_changes: canApprove,
          valid_from: validFrom,
          valid_to: validTo || null,
          note: note.trim() || null,
        });
        toast.success('Delegation updated');
      } else {
        if (granteeId === '') {
          toast.error('Choose who to grant access to');
          setSaving(false);
          return;
        }
        await client.post(ENDPOINTS.ROSTER.DELEGATIONS, {
          grantee_id: granteeId,
          scope_type: scopeType,
          scope_value:
            scopeType === 'department' || scopeType === 'location'
              ? scopeValue.trim()
              : null,
          employee_ids: scopeType === 'employees' ? empIds : [],
          can_publish: canPublish,
          can_approve_changes: canApprove,
          valid_from: validFrom,
          valid_to: validTo || null,
          note: note.trim() || null,
        });
        toast.success('Scheduling access granted');
      }
      setDialogOpen(false);
      fetchRows();
    } catch (err: any) {
      toast.error(errMsg(err, 'Failed to save delegation'));
    } finally {
      setSaving(false);
    }
  };

  const revoke = async (id: number) => {
    try {
      await client.post(ENDPOINTS.ROSTER.DELEGATION_REVOKE(id));
      toast.success('Delegation revoked');
      setConfirmRevoke(null);
      fetchRows();
    } catch (err: any) {
      toast.error(errMsg(err, 'Failed to revoke'));
      setConfirmRevoke(null);
      fetchRows();
    }
  };

  const filteredGrantees = useMemo(() => {
    const q = granteeSearch.trim().toLowerCase();
    return users.filter(
      (u) =>
        !q ||
        (u.full_name || '').toLowerCase().includes(q) ||
        u.email.toLowerCase().includes(q)
    );
  }, [users, granteeSearch]);

  const filteredEmps = useMemo(() => {
    const q = empSearch.trim().toLowerCase();
    return users.filter(
      (u) =>
        u.id !== granteeId &&
        (!q ||
          (u.full_name || '').toLowerCase().includes(q) ||
          u.email.toLowerCase().includes(q))
    );
  }, [users, empSearch, granteeId]);

  const toggleEmp = (id: number) =>
    setEmpIds((cur) =>
      cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id]
    );

  return (
    <div className="space-y-4">
      <Card className="p-3">
        <div className="flex flex-wrap items-center gap-3">
          <div className="text-sm text-gray-600">
            Let a manager or coordinator schedule a defined group of employees.
          </div>
          <div className="flex-1" />
          <label className="text-xs text-gray-600 flex items-center gap-2">
            <input
              type="checkbox"
              checked={showInactive}
              onChange={(e) => setShowInactive(e.target.checked)}
            />
            Show inactive
          </label>
          <Button variant="outline" size="sm" onClick={fetchRows}>
            <RefreshCw className="w-4 h-4" />
          </Button>
          <Button
            size="sm"
            onClick={openCreate}
            className="bg-indigo-600 hover:bg-indigo-700 text-white gap-1.5"
          >
            <Plus className="w-4 h-4" />
            Grant scheduling access
          </Button>
        </div>
      </Card>

      <Card className="overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="bg-gray-50 border-b">
                {['Grantee', 'Scope', 'Permissions', 'Validity', 'Status', 'Covers', ''].map(
                  (h, i) => (
                    <th
                      key={i}
                      className="text-left px-3 py-2 font-medium text-gray-600"
                    >
                      {h}
                    </th>
                  )
                )}
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={7} className="px-3 py-8 text-center text-gray-400">
                    Loading…
                  </td>
                </tr>
              ) : rows.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-3 py-8 text-center text-gray-400">
                    No delegations yet.
                  </td>
                </tr>
              ) : (
                rows.map((d) => {
                  const st = statusOf(d);
                  const inactive = st === 'revoked' || st === 'expired';
                  return (
                    <tr key={d.id} className="border-b">
                      <td className="px-3 py-2 text-gray-900">
                        {d.grantee_name || `User #${d.grantee_id}`}
                        {d.note && (
                          <div className="text-[11px] text-gray-400">{d.note}</div>
                        )}
                      </td>
                      <td className="px-3 py-2 text-gray-700">{scopeLabel(d)}</td>
                      <td className="px-3 py-2">
                        <div className="flex flex-wrap gap-1">
                          <Badge variant={d.can_publish ? 'success' : 'neutral'}>
                            {d.can_publish ? 'Can publish' : 'Drafts only'}
                          </Badge>
                          {d.can_approve_changes && (
                            <Badge variant="info">Approves changes</Badge>
                          )}
                        </div>
                      </td>
                      <td className="px-3 py-2 text-gray-600">
                        {d.valid_from} → {d.valid_to || 'open-ended'}
                      </td>
                      <td className="px-3 py-2">
                        <Badge
                          variant={
                            st === 'active'
                              ? 'success'
                              : st === 'upcoming'
                              ? 'info'
                              : st === 'expired'
                              ? 'warning'
                              : 'error'
                          }
                        >
                          {st}
                        </Badge>
                      </td>
                      <td className="px-3 py-2 text-gray-700">
                        <span className="inline-flex items-center gap-1">
                          <Users className="w-3.5 h-3.5 text-gray-400" />
                          {d.covered_count}
                        </span>
                      </td>
                      <td className="px-3 py-2 text-right whitespace-nowrap">
                        {!d.revoked_at && !inactive && (
                          confirmRevoke === d.id ? (
                            <span className="inline-flex items-center gap-2 text-xs text-gray-600">
                              Revoke access?
                              <Button
                                size="sm"
                                variant="outline"
                                className="text-red-600"
                                onClick={() => revoke(d.id)}
                              >
                                Yes, revoke
                              </Button>
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={() => setConfirmRevoke(null)}
                              >
                                Cancel
                              </Button>
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-2">
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={() => openEdit(d)}
                              >
                                Edit
                              </Button>
                              <Button
                                size="sm"
                                variant="outline"
                                className="text-red-600"
                                onClick={() => setConfirmRevoke(d.id)}
                              >
                                Revoke
                              </Button>
                            </span>
                          )
                        )}
                        {!d.revoked_at && inactive && (
                          <Button size="sm" variant="outline" onClick={() => openEdit(d)}>
                            Edit
                          </Button>
                        )}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </Card>

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="max-w-xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>
              {editing
                ? `Edit access for ${editing.grantee_name || userName(editing.grantee_id)}`
                : 'Grant scheduling access'}
            </DialogTitle>
          </DialogHeader>

          <div className="space-y-4 text-sm">
            {editing ? (
              <div className="text-gray-600">
                Scope: <b>{scopeLabel(editing)}</b> (scope can't be changed —
                revoke and grant again)
              </div>
            ) : (
              <>
                <div className="space-y-1">
                  <label className="text-gray-700 font-medium">Grantee</label>
                  <input
                    type="text"
                    placeholder="Search users"
                    value={granteeSearch}
                    onChange={(e) => setGranteeSearch(e.target.value)}
                    className={fieldCls + ' w-full'}
                  />
                  <select
                    value={granteeId}
                    onChange={(e) =>
                      setGranteeId(e.target.value ? Number(e.target.value) : '')
                    }
                    className={fieldCls + ' w-full'}
                  >
                    <option value="">Select user…</option>
                    {filteredGrantees.map((u) => (
                      <option key={u.id} value={u.id}>
                        {u.full_name || u.email} ({u.email})
                      </option>
                    ))}
                  </select>
                </div>

                <div className="space-y-1">
                  <label className="text-gray-700 font-medium">Scope</label>
                  <select
                    value={scopeType}
                    onChange={(e) => {
                      setScopeType(e.target.value as Delegation['scope_type']);
                      setScopeValue('');
                      setEmpIds([]);
                    }}
                    className={fieldCls + ' w-full'}
                  >
                    <option value="department">A department</option>
                    <option value="location">A location</option>
                    <option value="team">Their reporting team</option>
                    <option value="employees">Specific employees</option>
                  </select>

                  {scopeType === 'department' && (
                    <select
                      value={scopeValue}
                      onChange={(e) => setScopeValue(e.target.value)}
                      className={fieldCls + ' w-full'}
                    >
                      <option value="">Select department…</option>
                      {departments.map((d: any) => (
                        <option key={d.id} value={d.name}>
                          {d.name}
                        </option>
                      ))}
                    </select>
                  )}
                  {scopeType === 'location' && (
                    <input
                      type="text"
                      placeholder="Location (as on employee records)"
                      value={scopeValue}
                      onChange={(e) => setScopeValue(e.target.value)}
                      className={fieldCls + ' w-full'}
                    />
                  )}
                  {scopeType === 'employees' && (
                    <div className="space-y-1">
                      <input
                        type="text"
                        placeholder="Search employees"
                        value={empSearch}
                        onChange={(e) => setEmpSearch(e.target.value)}
                        className={fieldCls + ' w-full'}
                      />
                      <div
                        className="border rounded-lg p-2 overflow-y-auto"
                        style={{ maxHeight: 160 }}
                      >
                        {filteredEmps.map((u) => (
                          <label
                            key={u.id}
                            className="flex items-center gap-2 py-0.5 text-gray-700"
                          >
                            <input
                              type="checkbox"
                              checked={empIds.includes(u.id)}
                              onChange={() => toggleEmp(u.id)}
                            />
                            {u.full_name || u.email}
                          </label>
                        ))}
                      </div>
                      <div className="text-xs text-gray-500">
                        {empIds.length} selected
                      </div>
                    </div>
                  )}
                  <div className="text-xs text-gray-500">
                    The grantee never schedules themselves.
                  </div>
                </div>
              </>
            )}

            <div className="space-y-2">
              <label className="flex items-start gap-2 text-gray-700">
                <input
                  type="checkbox"
                  checked={canPublish}
                  onChange={(e) => setCanPublish(e.target.checked)}
                  className="mt-1"
                />
                <span>
                  <b>Can publish</b> — without this, their changes stay drafts
                  and need HR approval before employees see them.
                </span>
              </label>
              <label className="flex items-start gap-2 text-gray-700">
                <input
                  type="checkbox"
                  checked={canApprove}
                  onChange={(e) => setCanApprove(e.target.checked)}
                  className="mt-1"
                />
                <span>
                  <b>Can approve change requests</b> from employees in scope.
                </span>
              </label>
            </div>

            <div className="flex flex-wrap gap-3">
              <div className="space-y-1">
                <label className="text-gray-700 font-medium">Valid from</label>
                <input
                  type="date"
                  value={validFrom}
                  onChange={(e) => setValidFrom(e.target.value)}
                  className={fieldCls}
                />
              </div>
              <div className="space-y-1">
                <label className="text-gray-700 font-medium">
                  Valid to (optional)
                </label>
                <input
                  type="date"
                  value={validTo}
                  onChange={(e) => setValidTo(e.target.value)}
                  className={fieldCls}
                />
              </div>
            </div>

            <div className="space-y-1">
              <label className="text-gray-700 font-medium">Note</label>
              <input
                type="text"
                maxLength={255}
                value={note}
                onChange={(e) => setNote(e.target.value)}
                className={fieldCls + ' w-full'}
              />
            </div>

            {!editing && (
              <div className="p-3 bg-blue-50 border border-blue-200 rounded-lg text-xs text-blue-800">
                {preview === null ? (
                  'Pick a scope to see how many employees it covers.'
                ) : (
                  <>
                    Covers <b>{preview.length}</b> employee
                    {preview.length === 1 ? '' : 's'}
                    {preview.length > 0 && (
                      <>
                        :{' '}
                        {preview
                          .slice(0, 6)
                          .map((p) => p.full_name)
                          .join(', ')}
                        {preview.length > 6 && ` +${preview.length - 6} more`}
                      </>
                    )}
                  </>
                )}
              </div>
            )}
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogOpen(false)}>
              Cancel
            </Button>
            <Button
              onClick={save}
              disabled={saving || (!editing && (granteeId === '' || !scopeReady))}
              className="bg-indigo-600 hover:bg-indigo-700 text-white"
            >
              {saving ? 'Saving…' : editing ? 'Save changes' : 'Grant access'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};
