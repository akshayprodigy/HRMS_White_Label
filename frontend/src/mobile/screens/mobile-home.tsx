import React, { useEffect, useState } from 'react';
import {
  Inbox,
  FileText,
  CalendarDays,
  ChevronRight,
  MapPin,
  Loader2,
} from 'lucide-react';
import { client } from '../../api/client';
import { ENDPOINTS } from '../../api/endpoints';
import { cn, fmtInr, fmtDate, StatusChip } from '../../components/ui-elements';
import { APPROVER_ROLES, type MobileTab } from '../mobile-types';
import type { UserRole } from '../../types/erp';

interface MobileHomeProps {
  userName: string;
  userRole: UserRole;
  hasMarkedAttendance: boolean;
  hasPunchedOut: boolean;
  onGoto: (tab: MobileTab) => void;
}

interface PayslipRecord {
  id: number;
  month: number;
  year: number;
  net_pay: number;
  published_at: string;
}

interface LeaveRow {
  id: number;
  status: 'submitted' | 'approved' | 'rejected' | 'cancelled';
  start_date: string;
  end_date: string;
  leave_type?: { name: string };
}

interface TodayRow {
  captured_at: string;
  punch_out_time: string | null;
}

function greeting() {
  const h = new Date().getHours();
  if (h < 12) return 'Good morning';
  if (h < 17) return 'Good afternoon';
  return 'Good evening';
}

function fmtTime(iso: string | null | undefined) {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleTimeString('en-IN', {
      hour: '2-digit',
      minute: '2-digit',
      hour12: true,
    });
  } catch {
    return '—';
  }
}

export const MobileHome: React.FC<MobileHomeProps> = ({
  userName,
  userRole,
  hasMarkedAttendance,
  hasPunchedOut,
  onGoto,
}) => {
  const isApprover = APPROVER_ROLES.includes(userRole);
  const [pending, setPending] = useState<number>(0);
  const [approvalQ, setApprovalQ] = useState<number>(0);
  const [today, setToday] = useState<TodayRow | null>(null);
  const [payslip, setPayslip] = useState<PayslipRecord | null>(null);
  const [leave, setLeave] = useState<LeaveRow | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setLoading(true);
      try {
        const [pR, aR, tR, sR, lR] = await Promise.all([
          client
            .get(ENDPOINTS.DASHBOARD.PENDING_COUNT)
            .catch(() => ({ data: { count: 0 } })),
          isApprover
            ? client
                .get(ENDPOINTS.APPROVAL_CHAINS.MY_QUEUE)
                .catch(() => ({ data: [] }))
            : Promise.resolve({ data: [] }),
          client.get(ENDPOINTS.ATTENDANCE.TODAY).catch(() => ({ data: {} })),
          client
            .get(ENDPOINTS.HR.PAYROLL.MY_PAYSLIPS)
            .catch(() => ({ data: [] })),
          client.get(ENDPOINTS.LEAVE.MY).catch(() => ({ data: [] })),
        ]);
        if (cancelled) return;
        setPending(pR.data?.count ?? 0);
        setApprovalQ(Array.isArray(aR.data) ? aR.data.length : 0);
        setToday(tR.data?.attendance ?? null);
        const slips: PayslipRecord[] = Array.isArray(sR.data) ? sR.data : [];
        setPayslip(slips[0] ?? null);
        const lv: LeaveRow[] = Array.isArray(lR.data) ? lR.data : [];
        // Latest submitted/approved that's active or upcoming.
        const relevant = lv
          .filter(
            (r) => r.status === 'submitted' || r.status === 'approved'
          )
          .sort((a, b) => (a.start_date < b.start_date ? 1 : -1));
        setLeave(relevant[0] ?? null);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [isApprover]);

  return (
    <div className="p-4 space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-[11px] font-bold uppercase tracking-widest text-slate-400">
            {greeting()}
          </p>
          <h1 className="text-xl font-black text-[#0F172A]">{userName}</h1>
        </div>
        {pending > 0 && (
          <span
            className="inline-flex items-center gap-1 h-8 px-3 rounded-full bg-[#DC2626] text-white text-[12px] font-black"
            aria-label={`${pending} pending actions`}
          >
            {pending} pending
          </span>
        )}
      </div>

      <ActionRow
        icon={MapPin}
        title="Attendance"
        subtitle={
          hasMarkedAttendance
            ? hasPunchedOut
              ? `Done · out ${fmtTime(today?.punch_out_time)}`
              : `Punched in ${fmtTime(today?.captured_at)}`
            : 'Not punched in yet'
        }
        cta={hasMarkedAttendance ? (hasPunchedOut ? 'View' : 'Punch out') : 'Punch in'}
        tone={hasMarkedAttendance ? (hasPunchedOut ? 'ok' : 'active') : 'urgent'}
        onClick={() => onGoto('attendance')}
      />

      {isApprover && (
        <ActionRow
          icon={Inbox}
          title="Approvals"
          subtitle={
            approvalQ > 0
              ? `${approvalQ} waiting on you`
              : 'Nothing pending — good work'
          }
          cta={approvalQ > 0 ? 'Review' : 'Open'}
          tone={approvalQ > 0 ? 'urgent' : 'ok'}
          onClick={() => onGoto('approvals')}
        />
      )}

      <ActionRow
        icon={CalendarDays}
        title="Leave"
        subtitle={
          leave
            ? `${leave.leave_type?.name || 'Leave'} · ${fmtDate(leave.start_date)}`
            : 'No pending leave'
        }
        cta="Manage"
        rightSlot={leave ? <StatusChip status={leave.status} /> : undefined}
        onClick={() => onGoto('leave')}
      />

      <ActionRow
        icon={FileText}
        title="Latest payslip"
        subtitle={
          payslip
            ? `${new Date(payslip.year, payslip.month - 1).toLocaleString('en-IN', {
                month: 'long',
              })} ${payslip.year} · Net ${fmtInr(Math.round(payslip.net_pay * 100))}`
            : 'No payslips yet'
        }
        cta={payslip ? 'Open' : 'Later'}
        onClick={() => onGoto('payslip')}
      />

      {loading && (
        <div className="flex items-center gap-2 text-slate-400 text-xs justify-center py-2">
          <Loader2 size={12} className="animate-spin" /> Refreshing…
        </div>
      )}
    </div>
  );
};

const ActionRow: React.FC<{
  icon: React.ComponentType<{ size?: number; className?: string }>;
  title: string;
  subtitle: string;
  cta: string;
  tone?: 'ok' | 'active' | 'urgent';
  rightSlot?: React.ReactNode;
  onClick: () => void;
}> = ({ icon: Icon, title, subtitle, cta, tone, rightSlot, onClick }) => {
  const dot =
    tone === 'urgent'
      ? 'bg-red-500'
      : tone === 'active'
        ? 'bg-emerald-500'
        : tone === 'ok'
          ? 'bg-slate-300'
          : 'bg-slate-300';
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'w-full bg-white border border-slate-200 rounded-2xl p-4 flex items-center gap-3 text-left active:bg-slate-50'
      )}
    >
      <div className="relative w-10 h-10 rounded-xl bg-blue-50 flex items-center justify-center text-[#2563EB]">
        <Icon size={20} />
        {tone && <span className={cn('absolute -top-0.5 -right-0.5 w-2.5 h-2.5 rounded-full', dot)} />}
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-black text-[#0F172A]">{title}</p>
        <p className="text-[12px] text-slate-500 truncate">{subtitle}</p>
      </div>
      {rightSlot}
      <span className="text-[12px] font-bold text-[#2563EB] flex items-center gap-0.5">
        {cta} <ChevronRight size={14} />
      </span>
    </button>
  );
};

