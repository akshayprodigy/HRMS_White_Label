import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Plus, RefreshCw, Users } from 'lucide-react';
import { Card, Button, Badge } from './ui-elements';
import { toast } from 'sonner';
import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';
import { ScheduleDelegationDialog } from './schedule-delegation-dialog';
import {
  Delegation,
  UserLite,
  errMsg,
  scopeLabel,
  todayIso,
} from './schedule-delegations-utils';

const statusOf = (d: Delegation): 'active' | 'expired' | 'revoked' | 'upcoming' => {
  if (d.revoked_at) return 'revoked';
  const t = todayIso();
  if (d.valid_to && d.valid_to < t) return 'expired';
  if (d.valid_from > t) return 'upcoming';
  return 'active';
};

export const ScheduleDelegations = () => {
  const [rows, setRows] = useState<Delegation[]>([]);
  const [loading, setLoading] = useState(false);
  const [showInactive, setShowInactive] = useState(false);
  const [confirmRevoke, setConfirmRevoke] = useState<number | null>(null);

  const [users, setUsers] = useState<UserLite[]>([]);
  const [departments, setDepartments] = useState<any[]>([]);

  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<Delegation | null>(null);
  const [revoking, setRevoking] = useState<number | null>(null);
  const reqId = useRef(0);

  const fetchRows = useCallback(async () => {
    const id = ++reqId.current; // drop responses from superseded requests
    setLoading(true);
    try {
      const res = await client.get<Delegation[]>(
        `${ENDPOINTS.ROSTER.DELEGATIONS}?include_inactive=${showInactive}`
      );
      if (id === reqId.current) setRows(res.data || []);
    } catch (err: any) {
      if (id === reqId.current)
        toast.error(errMsg(err, 'Failed to load delegations'));
    } finally {
      if (id === reqId.current) setLoading(false);
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
        toast.error(errMsg(err, 'Failed to load users or departments'));
      }
    })();
  }, []);

  const openCreate = () => {
    setEditing(null);
    setDialogOpen(true);
  };
  const openEdit = (d: Delegation) => {
    setEditing(d);
    setDialogOpen(true);
  };

  const revoke = async (id: number) => {
    setRevoking(id);
    try {
      await client.post(ENDPOINTS.ROSTER.DELEGATION_REVOKE(id));
      toast.success('Delegation revoked');
    } catch (err: any) {
      toast.error(errMsg(err, 'Failed to revoke'));
    } finally {
      setRevoking(null);
      setConfirmRevoke(null);
      fetchRows();
    }
  };

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
          <Button variant="outline" size="sm" onClick={fetchRows} aria-label="Refresh delegations">
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
                {['Grantee', 'Scope', 'Permissions', 'Validity', 'Status', 'Covers', 'Actions'].map(
                  (h, i) => (
                    <th
                      key={i}
                      className="text-left px-3 py-2 font-medium text-gray-600"
                    >
                      {i === 6 ? <span className="sr-only">{h}</span> : h}
                    </th>
                  )
                )}
              </tr>
            </thead>
            <tbody>
              {loading && rows.length === 0 ? (
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
                          {d.can_emergency_override && (
                            <Badge variant="warning">Emergency override</Badge>
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
                                disabled={revoking === d.id}
                                onClick={() => revoke(d.id)}
                              >
                                {revoking === d.id ? 'Revoking…' : 'Yes, revoke'}
                              </Button>
                              <Button
                                size="sm"
                                variant="outline"
                                disabled={revoking === d.id}
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

      <ScheduleDelegationDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        editing={editing}
        users={users}
        departments={departments}
        onSaved={fetchRows}
      />
    </div>
  );
};
