import React, { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { CalendarPlus } from 'lucide-react';
import { Button } from '../ui-elements';
import {
  Dialog, DialogContent, DialogTitle, DialogDescription, DialogFooter,
} from '../ui/dialog';
import { errMsg, todayIso } from '../schedule-delegations-utils';
import { addDays } from './roster-api';
import { OPEN_SHIFT_HORIZON_DAYS } from './use-requests';
import { inputCls, labelCls } from '../my-schedule/my-schedule-api';
import { schedulerApi, type ShiftTemplateLite } from './roster-api';

export interface OpenShiftPrefill {
  date?: string;
  templateId?: number | null;
  department?: string | null;
  location?: string | null;
}

interface Props {
  open: boolean;
  templates: ShiftTemplateLite[];
  prefill?: OpenShiftPrefill | null;
  defaultDepartment?: string;
  onClose: () => void;
  onCreated: () => void;
}

export const OpenShiftDialog: React.FC<Props> = ({
  open, templates, prefill, defaultDepartment = '', onClose, onCreated,
}) => {
  const [date, setDate] = useState(todayIso());
  const [tpl, setTpl] = useState('');
  const [dept, setDept] = useState('');
  const [loc, setLoc] = useState('');
  const [slots, setSlots] = useState('1');
  const [note, setNote] = useState('');
  const [auto, setAuto] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    setDate(prefill?.date || todayIso());
    const pid = prefill?.templateId;
    setTpl(pid && templates.some((t) => t.id === pid) ? String(pid) : '');
    // a prefill carries its own scope verbatim (null = all departments)
    setDept(prefill ? prefill.department ?? '' : defaultDepartment);
    setLoc(prefill?.location ?? '');
    setSlots('1');
    setNote('');
    setAuto(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, prefill]);

  const n = Number(slots);
  const maxDate = addDays(todayIso(), OPEN_SHIFT_HORIZON_DAYS);
  const valid = !!date && date >= todayIso() && date <= maxDate && !!tpl && Number.isInteger(n) && n >= 1 && n <= 50;

  const submit = async () => {
    if (!valid) return;
    setBusy(true);
    try {
      const r = await schedulerApi.createOpenShift({
        work_date: date,
        shift_template_id: Number(tpl),
        department: dept.trim() || null,
        location: loc.trim() || null,
        slots: n,
        note: note.trim() || null,
        auto_confirm: auto,
      });
      toast.success('Open shift posted — eligible employees were notified');
      (r.warnings || []).forEach((w) => toast.warning(w));
      onCreated();
      onClose();
    } catch (e: any) {
      toast.error(errMsg(e, 'Failed to post open shift'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o: boolean) => !o && !busy && onClose()}>
      <DialogContent className="max-w-md">
        <DialogTitle className="flex items-center gap-2 text-base font-black uppercase tracking-tight text-[#0F172A]">
          <CalendarPlus size={15} className="text-indigo-600" /> Post open shift
        </DialogTitle>
        <DialogDescription className="text-[10px] font-bold text-slate-500 -mt-1">
          Eligible employees can claim it; you confirm the claim unless auto-confirm is on.
        </DialogDescription>
        <div className="grid grid-cols-2 gap-3 pt-1">
          <div className="space-y-1">
            <label htmlFor="os-date" className={labelCls}>Date</label>
            <input id="os-date" type="date" className={inputCls} min={todayIso()} max={maxDate} value={date}
              onChange={(e) => setDate(e.target.value)} />
          </div>
          <div className="space-y-1">
            <label htmlFor="os-shift" className={labelCls}>Shift</label>
            <select id="os-shift" className={inputCls} value={tpl} onChange={(e) => setTpl(e.target.value)}>
              <option value="" disabled>Select a shift…</option>
              {templates.map((t) => (
                <option key={t.id} value={t.id}>{t.name}</option>
              ))}
            </select>
          </div>
          <div className="space-y-1">
            <label htmlFor="os-dept" className={labelCls}>Department (optional)</label>
            <input id="os-dept" className={inputCls} maxLength={100} value={dept}
              onChange={(e) => setDept(e.target.value)} placeholder="All departments" />
          </div>
          <div className="space-y-1">
            <label htmlFor="os-loc" className={labelCls}>Location (optional)</label>
            <input id="os-loc" className={inputCls} maxLength={100} value={loc}
              onChange={(e) => setLoc(e.target.value)} placeholder="Any location" />
          </div>
          <div className="space-y-1">
            <label htmlFor="os-slots" className={labelCls}>Slots</label>
            <input id="os-slots" type="number" min={1} max={50} className={inputCls} value={slots}
              onChange={(e) => setSlots(e.target.value)} />
          </div>
          <div className="space-y-1 flex flex-col justify-end">
            <label className="flex items-center gap-2 text-[11px] font-bold text-slate-700 h-10">
              <input type="checkbox" checked={auto} onChange={(e) => setAuto(e.target.checked)} />
              Auto-confirm first eligible claim
            </label>
          </div>
          <div className="space-y-1 col-span-2">
            <label htmlFor="os-note" className={labelCls}>Note (optional)</label>
            <input id="os-note" className={inputCls} maxLength={255} value={note}
              onChange={(e) => setNote(e.target.value)} />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={busy}>Cancel</Button>
          <Button onClick={submit} isLoading={busy} disabled={!valid}>Post open shift</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
