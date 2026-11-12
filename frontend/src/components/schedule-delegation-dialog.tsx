import React, { useState, useEffect, useMemo } from 'react';
import { Button } from './ui-elements';
import { toast } from 'sonner';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogDescription,
  DialogTitle,
  DialogFooter,
} from './ui/dialog';
import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';
import {
  Delegation,
  UserLite,
  errMsg,
  scopeLabel,
  todayIso,
} from './schedule-delegations-utils';

interface PreviewRow {
  user_id: number;
  full_name: string | null;
  department: string | null;
}

const fieldCls =
  'px-3 py-1.5 border rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500';

interface Props {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  editing: Delegation | null;
  users: UserLite[];
  departments: any[];
  onSaved: () => void;
}

export const ScheduleDelegationDialog = ({
  open,
  onOpenChange,
  editing,
  users,
  departments,
  onSaved,
}: Props) => {
  const [granteeId, setGranteeId] = useState<number | ''>('');
  const [granteeSearch, setGranteeSearch] = useState('');
  const [scopeType, setScopeType] = useState<Delegation['scope_type']>('department');
  const [scopeValue, setScopeValue] = useState('');
  const [empIds, setEmpIds] = useState<number[]>([]);
  const [empSearch, setEmpSearch] = useState('');
  const [canPublish, setCanPublish] = useState(false);
  const [canApprove, setCanApprove] = useState(false);
  const [canOverride, setCanOverride] = useState(false);
  const [validFrom, setValidFrom] = useState(todayIso());
  const [validTo, setValidTo] = useState('');
  const [note, setNote] = useState('');
  const [saving, setSaving] = useState(false);
  const [preview, setPreview] = useState<PreviewRow[] | null>(null);
  const [previewError, setPreviewError] = useState(false);

  // Reset / hydrate whenever the dialog opens.
  useEffect(() => {
    if (!open) return;
    const d = editing;
    setGranteeId(d ? d.grantee_id : '');
    setGranteeSearch('');
    setScopeType(d ? d.scope_type : 'department');
    setScopeValue(d?.scope_value || '');
    setEmpIds(d ? d.employee_ids || [] : []);
    setEmpSearch('');
    setCanPublish(d ? d.can_publish : false);
    setCanApprove(d ? d.can_approve_changes : false);
    setCanOverride(d ? !!d.can_emergency_override : false);
    setValidFrom(d ? d.valid_from : todayIso());
    setValidTo(d?.valid_to || '');
    setNote(d?.note || '');
    setPreview(null);
    setPreviewError(false);
  }, [open, editing]);

  const scopeReady =
    scopeType === 'team' ||
    (scopeType === 'employees' ? empIds.length > 0 : scopeValue.trim() !== '');

  // Debounced live preview (create mode only)
  useEffect(() => {
    setPreview(null);
    setPreviewError(false);
    if (!open || editing || !scopeReady) return;
    if (scopeType === 'team' && granteeId === '') return;
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
        if (!cancelled) setPreviewError(true);
      }
    }, 350);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [open, editing, scopeType, scopeValue, empIds, granteeId, scopeReady]);

  const save = async () => {
    if (validTo && validTo < validFrom) {
      toast.error('"Valid to" must not be before "valid from"');
      return;
    }
    if (!editing && granteeId === '') {
      toast.error('Choose who to grant access to');
      return;
    }
    setSaving(true);
    try {
      if (editing) {
        await client.patch(ENDPOINTS.ROSTER.DELEGATION_DETAIL(editing.id), {
          can_publish: canPublish,
          can_approve_changes: canApprove,
          can_emergency_override: canOverride,
          valid_from: validFrom,
          valid_to: validTo || null,
          note: note.trim() || null,
        });
        toast.success('Delegation updated');
      } else {
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
          can_emergency_override: canOverride,
          valid_from: validFrom,
          valid_to: validTo || null,
          note: note.trim() || null,
        });
        toast.success('Scheduling access granted');
      }
      onOpenChange(false);
      onSaved();
    } catch (err: any) {
      toast.error(errMsg(err, 'Failed to save delegation'));
    } finally {
      setSaving(false);
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

  const changeGrantee = (v: number | '') => {
    setGranteeId(v);
    // A delegate never covers themselves: drop them from the employee list.
    if (v !== '') setEmpIds((cur) => cur.filter((x) => x !== v));
  };

  const granteeName = editing
    ? editing.grantee_name || `User #${editing.grantee_id}`
    : '';

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>
            {editing ? `Edit access for ${granteeName}` : 'Grant scheduling access'}
          </DialogTitle>
          <DialogDescription className="sr-only">Choose who can schedule or approve changes for which employees.</DialogDescription>
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
                <label htmlFor="dlg-grantee" className="text-gray-700 font-medium">
                  Grantee
                </label>
                <input
                  type="text"
                  aria-label="Search users"
                  placeholder="Search users"
                  value={granteeSearch}
                  onChange={(e) => setGranteeSearch(e.target.value)}
                  className={fieldCls + ' w-full'}
                />
                <select
                  id="dlg-grantee"
                  value={granteeId}
                  onChange={(e) =>
                    changeGrantee(e.target.value ? Number(e.target.value) : '')
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
                <label htmlFor="dlg-scope" className="text-gray-700 font-medium">
                  Scope
                </label>
                <select
                  id="dlg-scope"
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
                    aria-label="Department"
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
                    aria-label="Location"
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
                      aria-label="Search employees"
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
            <label className="flex items-start gap-2 text-gray-700">
              <input
                type="checkbox"
                checked={canOverride}
                onChange={(e) => setCanOverride(e.target.checked)}
                className="mt-1"
              />
              <span>
                <b>Can make emergency changes</b> inside the schedule lock
                window (with a reason; the employee must acknowledge).
              </span>
            </label>
          </div>

          <div className="flex flex-wrap gap-3">
            <div className="space-y-1">
              <label htmlFor="dlg-from" className="text-gray-700 font-medium">
                Valid from
              </label>
              <input
                id="dlg-from"
                type="date"
                value={validFrom}
                onChange={(e) => setValidFrom(e.target.value)}
                className={fieldCls + ' block'}
              />
            </div>
            <div className="space-y-1">
              <label htmlFor="dlg-to" className="text-gray-700 font-medium">
                Valid to (optional)
              </label>
              <input
                id="dlg-to"
                type="date"
                value={validTo}
                onChange={(e) => setValidTo(e.target.value)}
                className={fieldCls + ' block'}
              />
            </div>
          </div>

          <div className="space-y-1">
            <label htmlFor="dlg-note" className="text-gray-700 font-medium">
              Note
            </label>
            <input
              id="dlg-note"
              type="text"
              maxLength={255}
              value={note}
              onChange={(e) => setNote(e.target.value)}
              className={fieldCls + ' w-full'}
            />
          </div>

          {!editing && (
            <div
              className="p-3 bg-blue-50 border border-blue-200 rounded-lg text-xs text-blue-800"
              aria-live="polite"
            >
              {previewError ? (
                "Couldn't load preview."
              ) : preview === null ? (
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
          <Button variant="outline" onClick={() => onOpenChange(false)}>
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
  );
};
