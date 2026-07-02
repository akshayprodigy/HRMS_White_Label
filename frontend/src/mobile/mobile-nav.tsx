import React from 'react';
import { Home, MapPin, CalendarDays, FileText, Inbox } from 'lucide-react';
import { cn } from '../components/ui-elements';
import type { MobileTab } from './mobile-types';

interface TabDef {
  id: MobileTab;
  label: string;
  icon: React.ComponentType<{ size?: number; className?: string }>;
}

const BASE_TABS: TabDef[] = [
  { id: 'home', label: 'Home', icon: Home },
  { id: 'attendance', label: 'Punch', icon: MapPin },
  { id: 'leave', label: 'Leave', icon: CalendarDays },
  { id: 'payslip', label: 'Payslip', icon: FileText },
];

const APPROVAL_TAB: TabDef = { id: 'approvals', label: 'Approvals', icon: Inbox };

interface MobileNavProps {
  active: MobileTab;
  onChange: (tab: MobileTab) => void;
  showApprovals: boolean;
  badges?: Partial<Record<MobileTab, number>>;
}

export const MobileNav: React.FC<MobileNavProps> = ({
  active,
  onChange,
  showApprovals,
  badges = {},
}) => {
  const tabs = showApprovals ? [...BASE_TABS, APPROVAL_TAB] : BASE_TABS;
  return (
    <nav
      aria-label="Primary"
      className="fixed bottom-0 left-0 right-0 z-40 bg-white border-t border-slate-200"
      style={{ paddingBottom: 'env(safe-area-inset-bottom)' }}
    >
      <ul className={cn('grid', tabs.length === 5 ? 'grid-cols-5' : 'grid-cols-4')}>
        {tabs.map((t) => {
          const Icon = t.icon;
          const isActive = active === t.id;
          const badge = badges[t.id];
          return (
            <li key={t.id}>
              <button
                type="button"
                aria-current={isActive ? 'page' : undefined}
                onClick={() => onChange(t.id)}
                className={cn(
                  'w-full h-16 flex flex-col items-center justify-center gap-0.5 text-[11px] font-semibold transition-colors relative',
                  isActive ? 'text-[#2563EB]' : 'text-slate-500 active:text-slate-700'
                )}
              >
                <span className="relative">
                  <Icon size={22} className={isActive ? 'text-[#2563EB]' : 'text-slate-500'} />
                  {badge && badge > 0 ? (
                    <span
                      aria-label={`${badge} pending`}
                      className="absolute -top-1 -right-2 min-w-[16px] h-4 px-1 rounded-full bg-[#DC2626] text-white text-[10px] font-bold flex items-center justify-center leading-none"
                    >
                      {badge > 99 ? '99+' : badge}
                    </span>
                  ) : null}
                </span>
                <span>{t.label}</span>
                {isActive && (
                  <span className="absolute top-0 left-1/2 -translate-x-1/2 w-8 h-0.5 bg-[#2563EB] rounded-b-full" />
                )}
              </button>
            </li>
          );
        })}
      </ul>
    </nav>
  );
};
