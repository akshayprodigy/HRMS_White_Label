import React, { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Button } from '../ui-elements';
import { Dialog, DialogContent, DialogHeader, DialogDescription, DialogTitle } from '../ui/dialog';
import { errMsg } from '../schedule-delegations-utils';
import { onCallApi, type OnCallRule } from './on-call-api';

const fieldCls =
  'w-full px-3 py-1.5 border rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500';

interface Form {
  name: string;
  model: 'flat_per_day' | 'hourly';
  amount: string;
}
const EMPTY: Form = { name: '', model: 'flat_per_day', amount: '' };

interface Props {
  open: boolean;
  onClose: () => void;
  onChanged: () => void;
}

/** Roster-admin CRUD for on-call payout rules. */
export const OnCallRulesDialog = ({ open, onClose, onChanged }: Props) => {
  const [rules, setRules] = useState<OnCallRule[]>([]);
  const [loadErr, setLoadErr] = useState<string | null>(null);
  const [form, setForm] = useState<Form>(EMPTY);
  const [editId, setEditId] = useState<number | null>(null);
  const [formErr, setFormErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoadErr(null);
    try {
      setRules(await onCallApi.rules());
    } catch (e: any) {
      setLoadErr(errMsg(e, 'Failed to load on-call rules'));
    }
  }, []);
  useEffect(() => {
    if (!open) return;
    setForm(EMPTY);
    setEditId(null);
    setFormErr(null);
    load();
  }, [open, load]);

  const edit = (r: OnCallRule) => {
    setEditId(r.id);
    setFormErr(null);
    setForm({
      name: r.name,
      model: r.payout_model,
      amount: String(r.payout_model === 'hourly' ? r.hourly_rate : r.flat_amount),
    });
  };

  const save = async () => {
    const amount = Number(form.amount);
    if (!form.name.trim()) return setFormErr('Enter a name');
    if (form.amount.trim() === '' || !Number.isFinite(amount) || amount <= 0)
      return setFormErr('Enter an amount above zero');
    const body = {
      name: form.name.trim(),
      payout_model: form.model,
      flat_amount: form.model === 'flat_per_day' ? amount : 0,
      hourly_rate: form.model === 'hourly' ? amount : 0,
    };
    setBusy(true);
    setFormErr(null);
    try {
      if (editId == null) await onCallApi.createRule({ ...body, is_active: true });
      else await onCallApi.updateRule(editId, body);
      toast.success('On-call rule saved');
      setForm(EMPTY);
      setEditId(null);
      await load();
      onChanged();
    } catch (e: any) {
      setFormErr(errMsg(e, 'Failed to save rule'));
    } finally {
      setBusy(false);
    }
  };

  const toggle = async (r: OnCallRule) => {
    setBusy(true);
    try {
      await onCallApi.updateRule(r.id, { is_active: !r.is_active });
      await load();
      onChanged();
    } catch (e: any) {
      toast.error(errMsg(e, 'Failed to update rule'));
    } finally {
      setBusy(false);
    }
  };

  const remove = async (r: OnCallRule) => {
    setBusy(true);
    try {
      await onCallApi.deleteRule(r.id);
      toast.success('Rule deleted');
      await load();
      onChanged();
    } catch (e: any) {
      toast.error(errMsg(e, 'Failed to delete rule'));
    } finally {
      setBusy(false);
    }
  };

  const money = (r: OnCallRule) =>
    r.payout_model === 'hourly' ? `₹${r.hourly_rate}/hour` : `₹${r.flat_amount}/day`;

  return (
    <Dialog open={open} onOpenChange={(o: boolean) => !o && onClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>On-call pay rules</DialogTitle>
          <DialogDescription>
            How standby days are paid. Paid days flow into payroll as the on-call allowance.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          {loadErr && (
            <div role="alert" className="text-sm text-red-700">
              {loadErr}
            </div>
          )}
          <ul className="divide-y border rounded-lg">
            {rules.length === 0 && !loadErr && (
              <li className="p-3 text-sm text-gray-500">No rules yet.</li>
            )}
            {rules.map((r) => (
              <li key={r.id} className="p-3 flex flex-wrap items-center gap-2 text-sm">
                <span className="font-medium text-gray-900">{r.name}</span>
                <span className="text-gray-600">{money(r)}</span>
                {!r.is_active && <span className="text-xs text-gray-500">(inactive)</span>}
                <span className="flex-1" />
                <Button size="sm" variant="outline" disabled={busy} onClick={() => edit(r)}
                  aria-label={`Edit rule ${r.name}`}>Edit</Button>
                <Button size="sm" variant="outline" disabled={busy} onClick={() => toggle(r)}
                  aria-label={`${r.is_active ? 'Deactivate' : 'Activate'} rule ${r.name}`}>
                  {r.is_active ? 'Deactivate' : 'Activate'}
                </Button>
                <Button size="sm" variant="outline" disabled={busy} onClick={() => remove(r)}
                  aria-label={`Delete rule ${r.name}`}>Delete</Button>
              </li>
            ))}
          </ul>
          <div className="border rounded-lg p-3 space-y-3 bg-gray-50">
            <div className="text-sm font-medium text-gray-800">
              {editId == null ? 'New rule' : 'Edit rule'}
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div className="space-y-1">
                <label htmlFor="ocr-name" className="text-xs text-gray-600">Name</label>
                <input id="ocr-name" className={fieldCls} maxLength={120} value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })} />
              </div>
              <div className="space-y-1">
                <label htmlFor="ocr-model" className="text-xs text-gray-600">Pay model</label>
                <select id="ocr-model" className={fieldCls} value={form.model}
                  onChange={(e) => setForm({ ...form, model: e.target.value as Form['model'] })}>
                  <option value="flat_per_day">Flat per day</option>
                  <option value="hourly">Hourly</option>
                </select>
              </div>
              <div className="space-y-1">
                <label htmlFor="ocr-amount" className="text-xs text-gray-600">
                  {form.model === 'hourly' ? 'Rate per hour' : 'Amount per day'}
                </label>
                <input id="ocr-amount" type="number" min={0} className={fieldCls} value={form.amount}
                  onChange={(e) => setForm({ ...form, amount: e.target.value })} />
              </div>
            </div>
            {formErr && (
              <div role="alert" className="text-sm text-red-700">
                {formErr}
              </div>
            )}
            <div className="flex justify-end gap-2">
              {editId != null && (
                <Button size="sm" variant="outline" disabled={busy}
                  onClick={() => { setEditId(null); setForm(EMPTY); setFormErr(null); }}>
                  Cancel
                </Button>
              )}
              <Button size="sm" disabled={busy} onClick={save}
                className="bg-indigo-600 hover:bg-indigo-700 text-white">
                {busy ? 'Saving…' : 'Save rule'}
              </Button>
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
};
