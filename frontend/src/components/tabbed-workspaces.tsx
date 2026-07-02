import React, { useState } from 'react';
import {
  CalendarDays,
  Clock,
  FileCheck,
  FileSignature,
  FileText,
  Flag,
  MapPin,
  Moon,
  Banknote,
  BarChart3,
  ScrollText,
  Settings,
  Shield,
  Timer,
  Trophy,
  Users,
} from 'lucide-react';
import { cn } from './ui-elements';
import type { UserRole } from '../types/erp';

import { WorkforceActivity } from './workforce/workforce-activity';
import { AttendanceFlaggedReview } from './attendance-flagged-review';
import { ShiftTemplatesAdmin } from './shift-templates-admin';
import { EmployeeShiftAssignmentsView } from './employee-shift-assignments';
import { ShiftChangeRequestsTab } from './shift-change-requests-tab';
import { GeoFenceLocationsAdmin } from './geofence-locations-admin';
import { EmployeeGeoAssignments } from './employee-geo-assignments';
import { OvertimeRulesAdmin } from './overtime-rules-admin';
import { NightAllowanceRulesAdmin } from './night-allowance-rules-admin';
import { OvertimeApprovalQueue } from './overtime-approval-queue';
import { SalaryRevisionsView } from './salary-revisions';
import { RevisionCyclesView } from './revision-cycles';
import { MyPayslips } from './my-payslips';
import { MyRevisionsView } from './my-revisions';
import { MyTaxDeclarationView } from './my-tax-declaration';
import { StatutoryFilingsView } from './statutory-filings';
import { StatutoryReconciliationView } from './statutory-reconciliation';
import { StatutoryConfigAdmin } from './statutory-config-admin';
import { TaxDeclarationQueue } from './tax-declaration-queue';
import { TDSReconciliationView } from './tds-reconciliation';
import { Form16Workspace } from './form16-workspace';
import { GratuityDashboardView } from './gratuity-dashboard';
import { TaxConfigAdmin } from './tax-config-admin';

// ===========================================================================
// Section P IA: consolidated tabbed workspaces.
//
// Each workspace merges sibling admin screens that used to be separate
// sidebar entries into one entry with an internal tab bar (same tab idiom
// as ExpensesWorkspace). The wrapped screens are unchanged — they render
// exactly as they did as standalone pages. Tabs can be role-gated so a
// workspace stays visible to a broader audience than its most sensitive
// tab (e.g. PMs see Overtime Approvals but not Overtime Rules).
// ===========================================================================

interface WorkspaceTab {
  id: string;
  label: string;
  icon: React.ComponentType<{ size?: number | string; className?: string }>;
  /** Visible to everyone who can open the workspace when omitted. */
  roles?: UserRole[];
  render: () => React.ReactNode;
}

const TabbedWorkspace: React.FC<{ tabs: WorkspaceTab[]; role?: UserRole }> = ({
  tabs,
  role,
}) => {
  const visible = tabs.filter(
    (t) => !t.roles || !role || t.roles.includes(role),
  );
  const [tab, setTab] = useState<string>(visible[0]?.id ?? '');
  const active = visible.find((t) => t.id === tab) ?? visible[0];

  if (!active) return null;

  return (
    <div>
      <div className="flex gap-1 border-b border-slate-200 bg-white px-6 pt-3 overflow-x-auto">
        {visible.map((t) => {
          const Icon = t.icon;
          const isActive = active.id === t.id;
          return (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={cn(
                'px-4 py-2 flex items-center gap-2 text-sm border-b-2 -mb-px whitespace-nowrap transition-colors',
                isActive
                  ? 'border-blue-600 text-blue-700 font-medium'
                  : 'border-transparent text-slate-500 hover:text-slate-700',
              )}
            >
              <Icon size={14} />
              {t.label}
            </button>
          );
        })}
      </div>
      {active.render()}
    </div>
  );
};

const ADMIN_ONLY: UserRole[] = ['hr', 'admin', 'super admin'];

export const AttendanceWorkspace: React.FC<{ role?: UserRole }> = ({ role }) => (
  <TabbedWorkspace
    role={role}
    tabs={[
      {
        id: 'activity',
        label: 'Workforce Activity',
        icon: Clock,
        render: () => <WorkforceActivity />,
      },
      {
        id: 'flagged',
        label: 'Flagged Review',
        icon: Flag,
        roles: ['hr', 'super admin'],
        render: () => <AttendanceFlaggedReview />,
      },
    ]}
  />
);

export const ShiftsWorkspace: React.FC<{ role?: UserRole }> = ({ role }) => (
  <TabbedWorkspace
    role={role}
    tabs={[
      {
        id: 'assignments',
        label: 'Assignments',
        icon: Users,
        render: () => <EmployeeShiftAssignmentsView />,
      },
      {
        id: 'templates',
        label: 'Templates',
        icon: CalendarDays,
        roles: ADMIN_ONLY,
        render: () => <ShiftTemplatesAdmin />,
      },
      {
        id: 'change-requests',
        label: 'Change Requests',
        icon: FileCheck,
        roles: ADMIN_ONLY,
        render: () => <ShiftChangeRequestsTab />,
      },
    ]}
  />
);

export const GeoWorkspace: React.FC<{ role?: UserRole }> = ({ role }) => (
  <TabbedWorkspace
    role={role}
    tabs={[
      {
        id: 'locations',
        label: 'Fence Locations',
        icon: MapPin,
        render: () => <GeoFenceLocationsAdmin />,
      },
      {
        id: 'assignments',
        label: 'Employee Assignments',
        icon: Shield,
        render: () => <EmployeeGeoAssignments />,
      },
    ]}
  />
);

export const OvertimeAdminWorkspace: React.FC<{ role?: UserRole }> = ({
  role,
}) => (
  <TabbedWorkspace
    role={role}
    tabs={[
      {
        id: 'approvals',
        label: 'Approvals',
        icon: FileCheck,
        render: () => <OvertimeApprovalQueue />,
      },
      {
        id: 'rules',
        label: 'Overtime Rules',
        icon: Timer,
        roles: ADMIN_ONLY,
        render: () => <OvertimeRulesAdmin />,
      },
      {
        id: 'night',
        label: 'Night Allowance',
        icon: Moon,
        roles: ADMIN_ONLY,
        render: () => <NightAllowanceRulesAdmin />,
      },
    ]}
  />
);

export const RevisionsWorkspace: React.FC<{ role?: UserRole }> = ({ role }) => (
  <TabbedWorkspace
    role={role}
    tabs={[
      {
        id: 'revisions',
        label: 'Revisions',
        icon: Trophy,
        render: () => <SalaryRevisionsView />,
      },
      {
        id: 'cycles',
        label: 'Cycles',
        icon: BarChart3,
        roles: ADMIN_ONLY,
        render: () => <RevisionCyclesView />,
      },
    ]}
  />
);

export const StatutoryWorkspace: React.FC<{ role?: UserRole }> = ({ role }) => (
  <TabbedWorkspace
    role={role}
    tabs={[
      {
        id: 'filings',
        label: 'Filings',
        icon: ScrollText,
        render: () => <StatutoryFilingsView />,
      },
      {
        id: 'reconciliation',
        label: 'Reconciliation',
        icon: FileCheck,
        render: () => <StatutoryReconciliationView />,
      },
      {
        id: 'config',
        label: 'Configuration',
        icon: Settings,
        render: () => <StatutoryConfigAdmin />,
      },
    ]}
  />
);

export const TaxWorkspace: React.FC<{ role?: UserRole }> = ({ role }) => (
  <TabbedWorkspace
    role={role}
    tabs={[
      {
        id: 'queue',
        label: 'Declaration Queue',
        icon: FileCheck,
        roles: ADMIN_ONLY,
        render: () => <TaxDeclarationQueue />,
      },
      {
        id: 'tds',
        label: 'TDS Reconciliation',
        icon: BarChart3,
        render: () => <TDSReconciliationView />,
      },
      {
        id: 'form16',
        label: 'Form 16 + 24Q',
        icon: FileSignature,
        roles: ADMIN_ONLY,
        render: () => <Form16Workspace />,
      },
      {
        id: 'gratuity',
        label: 'Gratuity',
        icon: Banknote,
        render: () => <GratuityDashboardView />,
      },
      {
        id: 'config',
        label: 'Configuration',
        icon: Settings,
        roles: ADMIN_ONLY,
        render: () => <TaxConfigAdmin />,
      },
    ]}
  />
);

export const MyPayWorkspace: React.FC = () => (
  <TabbedWorkspace
    tabs={[
      {
        id: 'payslips',
        label: 'Payslips',
        icon: FileText,
        render: () => <MyPayslips />,
      },
      {
        id: 'revisions',
        label: 'My Revisions',
        icon: Trophy,
        render: () => <MyRevisionsView />,
      },
      {
        id: 'tax',
        label: 'Tax Declaration',
        icon: FileCheck,
        render: () => <MyTaxDeclarationView />,
      },
    ]}
  />
);
