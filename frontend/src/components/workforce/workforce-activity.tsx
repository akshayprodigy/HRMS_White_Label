import React, { useEffect, useState, useCallback } from 'react';
import { Users, CalendarDays, CalendarRange, type LucideIcon } from 'lucide-react';
import { cn } from '../ui-elements';
import { AttendanceTab } from './attendance-tab';
import { CombinedCalendarTab } from './combined-calendar-tab';
import { LeaveHR } from '../leave-hr';

type TabId = 'attendance' | 'leave' | 'combined';

const TABS: { id: TabId; label: string; icon: LucideIcon }[] = [
  { id: 'attendance', label: 'Attendance', icon: Users },
  { id: 'leave', label: 'Leave', icon: CalendarDays },
  { id: 'combined', label: 'Combined Calendar', icon: CalendarRange },
];

function readUrlState(): { tab: TabId; employee: number | null } {
  if (typeof window === 'undefined') return { tab: 'attendance', employee: null };
  const params = new URLSearchParams(window.location.search);
  const t = params.get('tab');
  const tab: TabId = t === 'leave' || t === 'combined' || t === 'attendance' ? t : 'attendance';
  const empRaw = params.get('employee');
  const employee = empRaw && /^\d+$/.test(empRaw) ? parseInt(empRaw, 10) : null;
  return { tab, employee };
}

function writeUrlState(tab: TabId, employee: number | null) {
  if (typeof window === 'undefined') return;
  const params = new URLSearchParams(window.location.search);
  params.set('tab', tab);
  if (employee !== null) params.set('employee', employee.toString());
  else params.delete('employee');
  const next = `${window.location.pathname}?${params.toString()}${window.location.hash}`;
  window.history.replaceState({}, '', next);
}

export const WorkforceActivity: React.FC = () => {
  const initial = React.useMemo(readUrlState, []);
  const [tab, setTab] = useState<TabId>(initial.tab);
  const [drillEmployee, setDrillEmployee] = useState<number | null>(initial.employee);

  useEffect(() => {
    writeUrlState(tab, drillEmployee);
  }, [tab, drillEmployee]);

  useEffect(() => {
    const onPop = () => {
      const s = readUrlState();
      setTab(s.tab);
      setDrillEmployee(s.employee);
    };
    window.addEventListener('popstate', onPop);
    return () => window.removeEventListener('popstate', onPop);
  }, []);

  const handleEmployeeChange = useCallback((id: number | null) => {
    setDrillEmployee(id);
  }, []);

  return (
    <div className="animate-in fade-in duration-300">
      <div className="px-8 pt-8 pb-2 max-w-[1600px] mx-auto">
        <div className="flex items-end justify-between gap-4 flex-wrap">
          <div>
            <h2 className="text-3xl font-black text-[#0F172A] tracking-tighter uppercase">
              Workforce Activity
            </h2>
            <p className="text-[#64748B] font-bold uppercase tracking-widest text-[10px] mt-1">
              Attendance, Leave & Combined Workforce Intelligence
            </p>
          </div>
          <nav className="inline-flex bg-white border border-slate-200 rounded-2xl p-1 gap-1">
            {TABS.map(t => {
              const Icon = t.icon;
              const active = tab === t.id;
              return (
                <button
                  key={t.id}
                  type="button"
                  onClick={() => setTab(t.id)}
                  className={cn(
                    'inline-flex items-center gap-2 px-5 h-10 rounded-xl text-[10px] font-black uppercase tracking-widest transition-all',
                    active
                      ? 'bg-blue-600 text-white shadow-lg shadow-blue-600/20'
                      : 'text-slate-500 hover:text-[#0F172A]',
                  )}
                  aria-pressed={active}
                >
                  <Icon size={13} />
                  {t.label}
                </button>
              );
            })}
          </nav>
        </div>
      </div>

      <div className="pb-12">
        {tab === 'attendance' && (
          <div className="px-8 pt-6 max-w-[1600px] mx-auto">
            <AttendanceTab
              initialEmployeeId={drillEmployee ?? undefined}
              onEmployeeChange={handleEmployeeChange}
            />
          </div>
        )}
        {tab === 'leave' && (
          <div className="-mt-2">
            <LeaveHR />
          </div>
        )}
        {tab === 'combined' && (
          <div className="px-8 pt-6 max-w-[1600px] mx-auto">
            <CombinedCalendarTab />
          </div>
        )}
      </div>
    </div>
  );
};
