import React, { useEffect, useMemo, useState } from 'react';
import { Calendar, Clock, Moon, Sun } from 'lucide-react';
import { Button } from './ui-elements';
import { toast } from 'sonner@2.0.3';
import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';
import { Dialog, DialogContent, DialogTitle, DialogFooter } from './ui/dialog';
import { Input } from './ui/input';

interface ShiftTemplate {
  id: number;
  name: string;
  start_time: string;
  end_time: string;
  is_overnight: boolean;
  is_active: boolean;
  full_day_hours: number;
}

interface CurrentShift {
  employee_id: number;
  on_date: string;
  assignment_id: number | null;
  shift: ShiftTemplate | null;
}

interface AssignShiftDialogProps {
  open: boolean;
  onClose: () => void;
  employeeId: number;
  employeeName?: string;
  onAssigned?: () => void;
}

const errMsg = (err: any, fallback: string): string => {
  const detail = err?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail))
    return detail.map((d: any) => d?.msg || JSON.stringify(d)).join('; ');
  return err?.message || fallback;
};

const toHHMM = (t: string | undefined): string => {
  if (!t) return '';
  const parts = t.split(':');
  return parts.length >= 2 ? `${parts[0]}:${parts[1]}` : t;
};

const todayISO = () => new Date().toISOString().slice(0, 10);

export const AssignShiftDialog: React.FC<AssignShiftDialogProps> = ({
  open,
  onClose,
  employeeId,
  employeeName,
  onAssigned,
}) => {
  const [templates, setTemplates] = useState<ShiftTemplate[]>([]);
  const [current, setCurrent] = useState<CurrentShift | null>(null);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const [shiftTemplateId, setShiftTemplateId] = useState<number | ''>('');
  const [effectiveFrom, setEffectiveFrom] = useState<string>(todayISO());
  const [effectiveTo, setEffectiveTo] = useState<string>('');
  const [note, setNote] = useState('');

  const selectedTemplate = useMemo(
    () => templates.find((t) => t.id === shiftTemplateId) ?? null,
    [templates, shiftTemplateId],
  );

  useEffect(() => {
    if (!open) return;
    setShiftTemplateId('');
    setEffectiveFrom(todayISO());
    setEffectiveTo('');
    setNote('');

    let cancelled = false;
    const load = async () => {
      setLoading(true);
      try {
        const [tplRes, curRes] = await Promise.all([
          client.get(ENDPOINTS.SHIFTS.TEMPLATES),
          client.get(ENDPOINTS.SHIFTS.EFFECTIVE, {
            params: { employee_id: employeeId, on_date: todayISO() },
          }),
        ]);
        if (cancelled) return;
        setTemplates(
          (tplRes.data || []).filter((t: ShiftTemplate) => t.is_active),
        );
        setCurrent(curRes.data || null);
      } catch (e: any) {
        if (!cancelled) toast.error(errMsg(e, 'Failed to load shift data'));
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    load();
    return () => {
      cancelled = true;
    };
  }, [open, employeeId]);

  const submit = async () => {
    if (!shiftTemplateId) {
      toast.error('Pick a shift template');
      return;
    }
    if (!effectiveFrom) {
      toast.error('Effective From is required');
      return;
    }
    if (effectiveTo && effectiveTo < effectiveFrom) {
      toast.error('Effective To cannot be before Effective From');
      return;
    }
    setSubmitting(true);
    try {
      await client.post(
        ENDPOINTS.SHIFTS.ASSIGNMENTS,
        {
          employee_id: employeeId,
          shift_template_id: shiftTemplateId,
          effective_from: effectiveFrom,
          effective_to: effectiveTo || null,
          note: note || null,
        },
        { params: { close_previous: true } },
      );
      toast.success('Shift assigned');
      onAssigned?.();
      onClose();
    } catch (e: any) {
      toast.error(errMsg(e, 'Assignment failed'));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => (o ? null : onClose())}>
      <DialogContent className="max-w-lg p-0 overflow-hidden">
        <div className="bg-blue-600 px-6 py-5 text-white">
          <DialogTitle className="text-lg font-black uppercase tracking-tight flex items-center gap-2">
            <Calendar size={18} />
            Assign Shift{employeeName ? ` · ${employeeName}` : ''}
          </DialogTitle>
        </div>
        <div className="p-6 space-y-5 max-h-[70vh] overflow-y-auto">
          <div className="rounded-xl border border-slate-100 bg-slate-50/60 px-4 py-3">
            <div className="text-[10px] font-black uppercase tracking-widest text-slate-500">
              Current Shift (Today)
            </div>
            {loading ? (
              <div className="text-sm font-bold text-slate-400 mt-1 animate-pulse">
                Loading…
              </div>
            ) : current?.shift ? (
              <div className="flex items-center gap-2 mt-1.5">
                {current.shift.is_overnight ? (
                  <Moon size={14} className="text-indigo-500" />
                ) : (
                  <Sun size={14} className="text-amber-500" />
                )}
                <span className="text-sm font-black text-[#0F172A]">
                  {current.shift.name}
                </span>
                <span className="text-xs font-bold text-slate-500 tabular-nums">
                  · {toHHMM(current.shift.start_time)} →{' '}
                  {toHHMM(current.shift.end_time)}
                </span>
              </div>
            ) : (
              <div className="text-sm font-bold text-slate-400 mt-1">
                None assigned
              </div>
            )}
          </div>

          <div>
            <label className="text-[10px] font-black uppercase tracking-widest text-[#0F172A]">
              New Shift Template
            </label>
            <select
              value={shiftTemplateId}
              onChange={(e) =>
                setShiftTemplateId(
                  e.target.value === '' ? '' : Number(e.target.value),
                )
              }
              className="mt-1.5 w-full h-10 px-3 bg-white border border-slate-200 rounded-xl text-sm font-bold text-[#0F172A] focus:ring-2 focus:ring-blue-600/10 outline-none"
            >
              <option value="">— Choose a template —</option>
              {templates.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name} ({toHHMM(t.start_time)}→{toHHMM(t.end_time)}
                  {t.is_overnight ? ', overnight' : ''})
                </option>
              ))}
            </select>
            {selectedTemplate && (
              <p className="text-[10px] font-bold text-slate-500 mt-1 flex items-center gap-1">
                <Clock size={10} />
                Full day = {selectedTemplate.full_day_hours}h
              </p>
            )}
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-[10px] font-black uppercase tracking-widest text-[#0F172A]">
                Effective From
              </label>
              <Input
                type="date"
                value={effectiveFrom}
                onChange={(e: any) => setEffectiveFrom(e.target.value)}
                className="mt-1.5"
              />
            </div>
            <div>
              <label className="text-[10px] font-black uppercase tracking-widest text-[#0F172A]">
                Effective To{' '}
                <span className="text-slate-400 font-bold normal-case">
                  (blank = ongoing)
                </span>
              </label>
              <Input
                type="date"
                value={effectiveTo}
                onChange={(e: any) => setEffectiveTo(e.target.value)}
                className="mt-1.5"
              />
            </div>
          </div>

          <div>
            <label className="text-[10px] font-black uppercase tracking-widest text-[#0F172A]">
              Note <span className="text-slate-400 font-bold normal-case">(optional)</span>
            </label>
            <Input
              value={note}
              onChange={(e: any) => setNote(e.target.value)}
              placeholder="e.g. Rotation A, project rollout, temporary cover"
              maxLength={255}
              className="mt-1.5"
            />
          </div>

          {current?.shift && (
            <div className="rounded-xl border border-amber-100 bg-amber-50/60 px-4 py-3 text-[11px] text-amber-900">
              The current assignment will be auto-closed the day before the new
              one starts. To prevent that, manage the prior assignment manually
              in the Shift Assignments page.
            </div>
          )}
        </div>
        <DialogFooter className="px-6 py-4 bg-slate-50 border-t border-slate-100">
          <Button
            variant="ghost"
            onClick={onClose}
            className="text-[10px] font-black uppercase tracking-widest"
          >
            Cancel
          </Button>
          <Button
            onClick={submit}
            isLoading={submitting}
            disabled={!shiftTemplateId}
            className="bg-blue-600 hover:bg-blue-700 text-white text-[10px] font-black uppercase tracking-widest"
          >
            Assign
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
