import React, { useEffect, useState } from 'react';
import { Toaster } from 'sonner';
import { LogOut, ChevronRight } from 'lucide-react';
import { cn } from '../components/ui-elements';
import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';
import { UserRole } from '../types/erp';
import { MobileNav } from './mobile-nav';
import { APPROVER_ROLES, type MobileTab } from './mobile-types';
import { MobileHome } from './screens/mobile-home';
import { MobileAttendance } from './screens/mobile-attendance';
import { MobileLeave } from './screens/mobile-leave';
import { MobilePayslip } from './screens/mobile-payslip';
import { MobileApprovals } from './screens/mobile-approvals';

interface MobileShellProps {
  userRole: UserRole;
  userName: string;
  avatarUrl?: string;
  hasMarkedAttendance: boolean;
  hasPunchedOut: boolean;
  onAttendanceSuccess: () => void;
  onPunchedOut: () => void;
  onLogout: () => void;
}

const TAB_TITLES: Record<MobileTab, string> = {
  home: 'Home',
  attendance: 'Attendance',
  leave: 'Leave',
  payslip: 'Payslip',
  approvals: 'Approvals',
};

export const MobileShell: React.FC<MobileShellProps> = ({
  userRole,
  userName,
  avatarUrl,
  hasMarkedAttendance,
  hasPunchedOut,
  onAttendanceSuccess,
  onPunchedOut,
  onLogout,
}) => {
  const isAdmin = userRole === 'super admin' || userRole === 'admin';
  const showApprovals = APPROVER_ROLES.includes(userRole);

  const [active, setActive] = useState<MobileTab>(() => {
    if (isAdmin || hasMarkedAttendance) return 'home';
    return 'attendance';
  });
  const [badges, setBadges] = useState<Partial<Record<MobileTab, number>>>({});

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const [pending, queue] = await Promise.all([
          client.get(ENDPOINTS.DASHBOARD.PENDING_COUNT).catch(() => ({
            data: { count: 0 },
          })),
          showApprovals
            ? client.get(ENDPOINTS.APPROVAL_CHAINS.MY_QUEUE).catch(() => ({
                data: [],
              }))
            : Promise.resolve({ data: [] }),
        ]);
        if (cancelled) return;
        const next: Partial<Record<MobileTab, number>> = {};
        const pc = pending.data?.count ?? 0;
        if (pc > 0) next.home = pc;
        const qc = Array.isArray(queue.data) ? queue.data.length : 0;
        if (qc > 0) next.approvals = qc;
        setBadges(next);
      } catch {
        // ignore
      }
    };
    load();
    const t = setInterval(load, 60000);
    return () => {
      cancelled = true;
      clearInterval(t);
    };
  }, [showApprovals]);

  const unlocked = isAdmin || hasMarkedAttendance;

  // Gate everything except Attendance until punched-in — same rule as
  // desktop. Admins bypass the gate.
  const renderContent = () => {
    if (active === 'attendance') {
      return (
        <MobileAttendance
          hasMarkedAttendance={hasMarkedAttendance}
          hasPunchedOut={hasPunchedOut}
          onAttendanceSuccess={onAttendanceSuccess}
          onPunchedOut={onPunchedOut}
        />
      );
    }
    if (!unlocked) return <AttendanceGate onGo={() => setActive('attendance')} />;
    switch (active) {
      case 'home':
        return (
          <MobileHome
            userName={userName}
            userRole={userRole}
            hasMarkedAttendance={hasMarkedAttendance}
            hasPunchedOut={hasPunchedOut}
            onGoto={setActive}
          />
        );
      case 'leave':
        return <MobileLeave />;
      case 'payslip':
        return <MobilePayslip />;
      case 'approvals':
        return <MobileApprovals />;
      default:
        return null;
    }
  };

  return (
    <div className="min-h-[100dvh] bg-[#F8FAFC] flex flex-col">
      <MobileHeader
        title={TAB_TITLES[active]}
        userName={userName}
        avatarUrl={avatarUrl}
        onLogout={onLogout}
      />
      <main
        className="flex-1 overflow-y-auto"
        style={{
          paddingBottom: `calc(env(safe-area-inset-bottom) + 72px)`,
        }}
      >
        {renderContent()}
      </main>
      <MobileNav
        active={active}
        onChange={setActive}
        showApprovals={showApprovals}
        badges={badges}
      />
      <Toaster position="top-center" richColors />
    </div>
  );
};

// ----------------------------------------------------------------------
// Header + gate

const MobileHeader: React.FC<{
  title: string;
  userName: string;
  avatarUrl?: string;
  onLogout: () => void;
}> = ({ title, userName, avatarUrl, onLogout }) => {
  const [open, setOpen] = useState(false);
  return (
    <header
      className="sticky top-0 z-30 bg-white border-b border-slate-200"
      style={{ paddingTop: 'env(safe-area-inset-top)' }}
    >
      <div className="h-14 flex items-center justify-between px-4">
        <div>
          <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest leading-none">
            UE ERP
          </p>
          <h1 className="text-base font-black text-[#0F172A] leading-tight">
            {title}
          </h1>
        </div>
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="w-9 h-9 rounded-full overflow-hidden border border-slate-200 bg-slate-100 flex items-center justify-center"
          aria-label="Account menu"
          aria-haspopup="menu"
          aria-expanded={open}
        >
          {avatarUrl ? (
            <img src={avatarUrl} alt="" className="w-full h-full object-cover" />
          ) : (
            <span className="text-xs font-black text-slate-500">
              {userName.charAt(0).toUpperCase()}
            </span>
          )}
        </button>
      </div>
      {open && (
        <div
          role="menu"
          className="absolute right-3 top-14 w-56 bg-white border border-slate-200 rounded-xl shadow-lg overflow-hidden"
        >
          <div className="px-4 py-3 border-b border-slate-100">
            <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">
              Signed in as
            </p>
            <p className="text-sm font-black text-[#0F172A] truncate">{userName}</p>
          </div>
          <button
            type="button"
            onClick={() => {
              setOpen(false);
              onLogout();
            }}
            className="w-full px-4 py-3 flex items-center gap-2 text-sm font-semibold text-red-600 active:bg-red-50"
          >
            <LogOut size={16} /> Log out
          </button>
        </div>
      )}
    </header>
  );
};

const AttendanceGate: React.FC<{ onGo: () => void }> = ({ onGo }) => (
  <div className="p-6">
    <div className="mt-8 bg-white border border-slate-200 rounded-2xl p-6 text-center shadow-sm">
      <div className="w-16 h-16 mx-auto rounded-2xl bg-blue-50 flex items-center justify-center mb-4">
        <span className="text-3xl">🕒</span>
      </div>
      <h2 className="text-lg font-black text-[#0F172A] mb-2">Punch in to unlock</h2>
      <p className="text-sm text-slate-500 mb-5">
        Mark today's attendance to open the rest of the app.
      </p>
      <button
        type="button"
        onClick={onGo}
        className={cn(
          'w-full h-12 rounded-xl bg-[#2563EB] text-white font-bold',
          'active:bg-[#1D4ED8] flex items-center justify-center gap-2'
        )}
      >
        Go to attendance <ChevronRight size={16} />
      </button>
    </div>
  </div>
);
