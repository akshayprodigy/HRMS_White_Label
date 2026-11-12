import React, { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Plus, Trash2 } from 'lucide-react';
import { Card, Button, Badge } from '../ui-elements';
import {
  Dialog, DialogContent, DialogTitle, DialogDescription, DialogFooter,
} from '../ui/dialog';
import { errMsg, todayIso } from '../schedule-delegations-utils';
import {
  AvailabilityRule, ShiftOption, WEEKDAYS, fmtDateShort, inputCls, labelCls, mySchedule,
} from './my-schedule-api';

export const ruleText = (r: AvailabilityRule, shifts: ShiftOption[]): string => {
  const shiftName = r.shift_template_id
    ? shifts.find((s) => s.id === r.shift_template_id)?.name || `shift #${r.shift_template_id}`
    : null;
  const when = r.weekday !== null && r.weekday !== undefined
    ? `every ${WEEKDAYS[r.weekday].slice(0, 3)}`
    : r.specific_date ? `on ${fmtDateShort(r.specific_date)}` : '';
  const bounds = [
    r.valid_from ? `from ${fmtDateShort(r.valid_from)}` : '',
    r.valid_to ? `until ${fmtDateShort(r.valid_to)}` : '',
  ].filter(Boolean).join(' ');
  if (r.kind === 'unavailable') {
    return `Unavailable${shiftName ? ` for ${shiftName}` : ''} ${when}${bounds ? ` (${bounds})` : ''}`;
  }
  const onWhen = when.startsWith('every ') ? `on ${when.slice(6)}` : when;
  return `Prefers ${shiftName || 'a shift'} ${onWhen}${bounds ? ` (${bounds})` : ''}`;
};

const EMPTY = {
  kind: 'unavailable' as 'unavailable' | 'preferred',
  mode: 'weekday' as 'weekday' | 'date',
  weekday: 0,
  specific_date: '',
  shift_template_id: '' as number | '',
  valid_from: '',
  valid_to: '',
  note: '',
};

export const AvailabilityPanel: React.FC<{ shifts: ShiftOption[] }> = ({ shifts }) => {
  const [rules, setRules] = useState<AvailabilityRule[]>([]);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(EMPTY);
  const [busy, setBusy] = useState(false);
  const [confirmId, setConfirmId] = useState<number | null>(null);
  const [deleting, setDeleting] = useState(false);

  const load = useCallback(async () => {
    try {
      setRules(await mySchedule.listAvailability());
    } catch (e: any) {
      toast.error(errMsg(e, 'Failed to load availability'));
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => { load(); }, [load]);

  const submit = async () => {
    if (form.kind === 'preferred' && !form.shift_template_id) {
      toast.error('Pick the shift you prefer.');
      return;
    }
    if (form.mode === 'date' && !form.specific_date) {
      toast.error('Pick the date.');
      return;
    }
    setBusy(true);
    try {
      await mySchedule.createAvailability({
        kind: form.kind,
        weekday: form.mode === 'weekday' ? form.weekday : null,
        specific_date: form.mode === 'date' ? form.specific_date : null,
        shift_template_id: form.shift_template_id || null,
        valid_from: form.mode === 'weekday' && form.valid_from ? form.valid_from : null,
        valid_to: form.mode === 'weekday' && form.valid_to ? form.valid_to : null,
        note: form.note.trim() || null,
      });
      toast.success('Availability rule added');
      setOpen(false);
      await load();
    } catch (e: any) {
      toast.error(errMsg(e, 'Failed to add rule'));
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (confirmId === null) return;
    setDeleting(true);
    try {
      await mySchedule.deleteAvailability(confirmId);
      toast.success('Rule deleted');
      setConfirmId(null);
      await load();
    } catch (e: any) {
      toast.error(errMsg(e, 'Failed to delete rule'));
    } finally {
      setDeleting(false);
    }
  };

  return (
    <Card className="p-5 border-slate-200 bg-white">
      <div className="flex items-center justify-between gap-3 mb-3 flex-wrap">
        <div>
          <p className="text-[10px] font-black uppercase tracking-widest text-[#0F172A]">
            My Availability
          </p>
          <p className="text-[10px] text-slate-500 mt-0.5">
            Tell your scheduler when you cannot work or which shifts you prefer.
          </p>
        </div>
        <Button onClick={() => { setForm(EMPTY); setOpen(true); }} className="h-9">
          <Plus size={14} className="mr-1.5" /> Add rule
        </Button>
      </div>
      {loading ? (
        <p className="text-[10px] font-black uppercase tracking-widest text-slate-400 py-6 text-center">Loading…</p>
      ) : rules.length === 0 ? (
        <p className="text-[10px] font-black uppercase tracking-widest text-slate-400 py-6 text-center">
          No availability rules yet
        </p>
      ) : (
        <ul className="space-y-2">
          {rules.map((r) => (
            <li key={r.id} className="flex items-center justify-between gap-3 border border-slate-100 rounded-xl p-3">
              <div className="min-w-0">
                <p className="text-[12px] font-black text-[#0F172A]">{ruleText(r, shifts)}</p>
                {r.note && <p className="text-[10px] text-slate-500 italic truncate">"{r.note}"</p>}
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <Badge variant={r.kind === 'unavailable' ? 'error' : 'info'} className="text-[8px] uppercase">
                  {r.kind}
                </Badge>
                <button
                  type="button"
                  aria-label={`Delete rule: ${ruleText(r, shifts)}`}
                  onClick={() => setConfirmId(r.id)}
                  className="text-rose-500 hover:text-rose-700"
                >
                  <Trash2 size={14} />
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}

      {open && (
        <Dialog open onOpenChange={(o: boolean) => !o && !busy && setOpen(false)}>
          <DialogContent className="max-w-md">
            <DialogTitle className="text-base font-black uppercase tracking-tight text-[#0F172A]">
              Add availability rule
            </DialogTitle>
            <DialogDescription className="text-[10px] font-bold text-slate-500 -mt-1">
              Schedulers see this when planning your roster.
            </DialogDescription>
            <div className="space-y-3 pt-1">
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <label htmlFor="av-kind" className={labelCls}>Type</label>
                  <select id="av-kind" className={inputCls} value={form.kind}
                    onChange={(e) => setForm({ ...form, kind: e.target.value as any })}>
                    <option value="unavailable">Unavailable</option>
                    <option value="preferred">Preferred shift</option>
                  </select>
                </div>
                <div className="space-y-1">
                  <label htmlFor="av-mode" className={labelCls}>Applies to</label>
                  <select id="av-mode" className={inputCls} value={form.mode}
                    onChange={(e) => setForm({ ...form, mode: e.target.value as any })}>
                    <option value="weekday">Every weekday</option>
                    <option value="date">A specific date</option>
                  </select>
                </div>
              </div>
              {form.mode === 'weekday' ? (
                <div className="space-y-1">
                  <label htmlFor="av-weekday" className={labelCls}>Weekday</label>
                  <select id="av-weekday" className={inputCls} value={form.weekday}
                    onChange={(e) => setForm({ ...form, weekday: Number(e.target.value) })}>
                    {WEEKDAYS.map((w, i) => <option key={w} value={i}>{w}</option>)}
                  </select>
                </div>
              ) : (
                <div className="space-y-1">
                  <label htmlFor="av-date" className={labelCls}>Date</label>
                  <input id="av-date" type="date" className={inputCls} min={todayIso()}
                    value={form.specific_date}
                    onChange={(e) => setForm({ ...form, specific_date: e.target.value })} />
                </div>
              )}
              <div className="space-y-1">
                <label htmlFor="av-shift" className={labelCls}>
                  Shift {form.kind === 'preferred' ? '(required)' : '(optional, blank = whole day)'}
                </label>
                <select id="av-shift" className={inputCls} value={form.shift_template_id}
                  onChange={(e) => setForm({
                    ...form, shift_template_id: e.target.value ? Number(e.target.value) : '',
                  })}>
                  <option value="">{form.kind === 'preferred' ? 'Select a shift…' : 'Any shift'}</option>
                  {shifts.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                </select>
              </div>
              {form.mode === 'weekday' && (
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1">
                    <label htmlFor="av-from" className={labelCls}>From (optional)</label>
                    <input id="av-from" type="date" className={inputCls} value={form.valid_from}
                      onChange={(e) => setForm({ ...form, valid_from: e.target.value })} />
                  </div>
                  <div className="space-y-1">
                    <label htmlFor="av-to" className={labelCls}>Until (optional)</label>
                    <input id="av-to" type="date" className={inputCls} value={form.valid_to}
                      onChange={(e) => setForm({ ...form, valid_to: e.target.value })} />
                  </div>
                </div>
              )}
              <div className="space-y-1">
                <label htmlFor="av-note" className={labelCls}>Note (optional)</label>
                <input id="av-note" className={inputCls} maxLength={255} value={form.note}
                  placeholder="e.g. Evening classes"
                  onChange={(e) => setForm({ ...form, note: e.target.value })} />
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setOpen(false)} disabled={busy}>Cancel</Button>
              <Button onClick={submit} isLoading={busy}>Add rule</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}

      {confirmId !== null && (
        <Dialog open onOpenChange={(o: boolean) => !o && !deleting && setConfirmId(null)}>
          <DialogContent className="max-w-sm">
            <DialogTitle className="text-base font-black uppercase tracking-tight text-[#0F172A]">
              Delete this rule?
            </DialogTitle>
            <DialogDescription className="text-[11px] text-slate-600">
              {(() => { const r = rules.find((x) => x.id === confirmId); return r ? ruleText(r, shifts) : ''; })()}
            </DialogDescription>
            <DialogFooter>
              <Button variant="outline" onClick={() => setConfirmId(null)} disabled={deleting}>Keep</Button>
              <Button variant="danger" onClick={remove} isLoading={deleting}>Delete</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
    </Card>
  );
};
