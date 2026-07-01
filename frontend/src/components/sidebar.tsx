import React from "react";
import { motion } from "motion/react";
import {
  LayoutDashboard,
  Clock,
  CalendarDays,
  CheckSquare,
  FileText,
  UserCircle,
  Settings,
  LogOut,
  ChevronLeft,
  ChevronRight,
  ShieldCheck,
  BarChart3,
  Users,
  Briefcase,
  Building2,
  Target,
  Trophy,
  Shield,
  CreditCard,
  UserPlus,
  FileCheck,
  ClipboardList,
  BookOpen,
  Activity,
  FileSignature,
  Banknote,
  Network,
  ScrollText,
  Moon,
  Timer,
} from "lucide-react";
import { cn } from "./ui-elements";
import logoImg from "figma:asset/cffb70cda3aa408edd2d37bc7e7cdc4b08a0118e.png";
import { ImageWithFallback } from "./figma/ImageWithFallback";
import { UserRole } from "../types/erp";

interface SidebarProps {
  activeTab: string;
  setActiveTab: (tab: string) => void;
  collapsed: boolean;
  setCollapsed: (collapsed: boolean) => void;
  role: UserRole;
  onLogout: () => void;
  badges?: Record<string, number>;
}

export const Sidebar = ({
  activeTab,
  setActiveTab,
  collapsed,
  setCollapsed,
  role,
  onLogout,
  badges = {},
}: SidebarProps) => {
  // Dashboard items
  const menuItems = [
    {
      id: "role-dashboard",
      label: "My Cockpit",
      icon: LayoutDashboard,
      roles: [
        "employee", "pm", "hr", "recruiter", "bd", "bd manager",
        "dept head", "ceo", "coo", "client manager",
        "super admin", "admin", "finance",
      ],
    },
    {
      id: "dashboard",
      label: "My Workspace",
      icon: LayoutDashboard,
      roles: [
        "employee",
        "pm",
        "hr",
        "recruiter",
        "bd",
        "bd manager",
        "dept head",
        "ceo",
        "coo",
        "client manager",
      ],
    },
    {
      id: "hr-dashboard",
      label: "HR Intelligence",
      icon: LayoutDashboard,
      roles: ["hr", "recruiter", "super admin", "ceo"],
    },

    // Core Modules - Employee Management (Primary for HR)
    {
      id: "hr-directory",
      label: "Employee Management",
      icon: Users,
      roles: ["hr", "super admin", "ceo"],
    },

    // HR Operational Modules (HR Only)
    {
      id: "hr-attendance",
      label: "Workforce Activity",
      icon: Clock,
      roles: ["hr", "super admin", "ceo"],
    },
    {
      id: "hr-leave",
      label: "Leave Approvals",
      icon: CalendarDays,
      roles: ["pm", "dept head"],
    },
    {
      id: "hr-payroll",
      label: "Payroll Bureau",
      icon: CreditCard,
      roles: ["hr", "super admin", "ceo"],
    },
    {
      id: "hr-advances",
      label: "Salary Advances",
      icon: Banknote,
      roles: ["hr", "super admin", "ceo"],
    },
    {
      id: "hr-recruitment",
      label: "Recruitment",
      icon: Briefcase,
      roles: ["hr", "recruiter", "super admin", "ceo"],
    },
    {
      id: "hr-onboarding",
      label: "Onboarding",
      icon: UserPlus,
      roles: ["hr", "recruiter", "super admin", "ceo"],
    },
    {
      id: "hr-holidays",
      label: "Holiday Calendar",
      icon: CalendarDays,
      roles: ["hr", "super admin", "ceo"],
    },
    {
      id: "hr-letters",
      label: "Employee Letters",
      icon: FileSignature,
      roles: ["hr", "super admin", "ceo"],
    },
    {
      id: "hr-org-chart",
      label: "Org Chart",
      icon: Network,
      roles: ["hr", "super admin", "ceo", "coo"],
    },
    {
      id: "hr-audit-log",
      label: "Audit Log",
      icon: ScrollText,
      roles: ["super admin", "ceo"],
    },
    {
      id: "hr-attendance-review",
      label: "Attendance Review",
      icon: Clock,
      roles: ["hr", "super admin"],
    },
    {
      id: "geo-fences",
      label: "Geo Fences",
      icon: Shield,
      roles: ["hr", "admin", "super admin"],
    },
    {
      id: "employee-geo",
      label: "Employee Geo Assign",
      icon: Shield,
      roles: ["hr", "admin", "super admin"],
    },
    {
      id: "hr-reports",
      label: "Enterprise Analytics",
      icon: BarChart3,
      roles: ["hr", "super admin", "ceo", "coo"],
    },

    // Work Tools Section for everyone
    {
      id: "worklog",
      label: "My Worklog",
      icon: Clock,
      roles: [
        "employee",
        "pm",
        "hr",
        "recruiter",
        "super admin",
        "bd",
        "bd manager",
        "dept head",
        "ceo",
        "coo",
        "client manager",
      ],
    },
    {
      id: "timesheet",
      label: "My Timesheet",
      icon: CalendarDays,
      roles: [
        "employee",
        "pm",
        "hr",
        "recruiter",
        "super admin",
        "bd",
        "bd manager",
        "dept head",
        "ceo",
        "coo",
        "client manager",
      ],
    },
    {
      id: "tasks",
      label: "My Tasks",
      icon: CheckSquare,
      roles: [
        "employee",
        "pm",
        "hr",
        "recruiter",
        "super admin",
        "bd",
        "bd manager",
        "dept head",
        "ceo",
        "coo",
        "client manager",
      ],
    },
    {
      id: "leave",
      label: "My Leave",
      icon: FileText,
      roles: [
        "employee",
        "pm",
        "hr",
        "recruiter",
        "super admin",
        "bd",
        "bd manager",
        "dept head",
        "ceo",
        "coo",
        "client manager",
      ],
    },
    {
      id: "my-payslips",
      label: "My Payslips",
      icon: FileCheck,
      roles: [
        "employee",
        "pm",
        "hr",
        "recruiter",
        "super admin",
        "bd",
        "bd manager",
        "dept head",
        "ceo",
        "coo",
        "client manager",
      ],
    },
    {
      id: "policies",
      label: "Policy Center",
      icon: BookOpen,
      roles: [
        "employee",
        "pm",
        "hr",
        "recruiter",
        "super admin",
        "bd",
        "bd manager",
        "dept head",
        "ceo",
        "coo",
        "client manager",
      ],
    },

    // PM Module
    {
      id: "projects",
      label: "Project Deliverables",
      icon: Briefcase,
      roles: [
        "pm",
        "dop",
        "coo",
        "super admin",
        "dept head",
        "ceo",
        "client manager",
      ],
    },

    {
      id: "pm-bids",
      label: "Bid Requests",
      icon: ClipboardList,
      roles: ["pm", "super admin", "ceo", "coo"],
    },
    {
      id: "cost-approvals",
      label: "Cost Adjudication",
      icon: ShieldCheck,
      roles: ["pm", "dop", "coo", "super admin", "ceo"],
    },
    {
      id: "coo-dashboard",
      label: "COO Operations Hub",
      icon: Activity,
      roles: ["coo", "super admin", "ceo", "dop"],
    },

    {
      id: "approvals",
      label: "Approvals Center",
      icon: FileCheck,
      roles: [
        "pm",
        "hr",
        "recruiter",
        "bd",
        "bd manager",
        "dept head",
        "dop",
        "coo",
        "admin",
        "super admin",
        "ceo",
      ],
    },

    {
      id: "bd",
      label: "Business Development",
      icon: Target,
      roles: ["bd", "bd manager", "super admin", "ceo", "coo"],
    },

    {
      id: "client-details",
      label: "Client Details",
      icon: Building2,
      roles: ["client manager", "super admin", "bd", "bd manager"],
    },

    {
      id: "profile",
      label: "Profile",
      icon: UserCircle,
      roles: [
        "employee",
        "hr",
        "recruiter",
        "pm",
        "super admin",
        "bd",
        "bd manager",
        "dept head",
        "ceo",
        "coo",
        "client manager",
      ],
    },

    // Admin Module
    {
      id: "admin",
      label: "System Administration",
      icon: Shield,
      roles: ["admin", "super admin", "ceo"],
    },
    {
      id: "functional-areas",
      label: "Functional Areas",
      icon: Shield,
      roles: ["admin", "super admin"],
    },
    {
      id: "shift-templates",
      label: "Shift Templates",
      icon: Shield,
      roles: ["hr", "admin", "super admin"],
    },
    {
      id: "shift-assignments",
      label: "Shift Assignments",
      icon: Shield,
      roles: ["hr", "pm", "dept_head", "admin", "super admin"],
    },
    {
      id: "overtime-rules",
      label: "Overtime Rules",
      icon: Timer,
      roles: ["hr", "admin", "super admin"],
    },
    {
      id: "night-allowance-rules",
      label: "Night Allowance Rules",
      icon: Moon,
      roles: ["hr", "admin", "super admin"],
    },
    {
      id: "overtime-approvals",
      label: "Overtime Approvals",
      icon: Timer,
      roles: ["hr", "pm", "dept_head", "admin", "super admin"],
    },
    {
      id: "my-overtime",
      label: "My Overtime",
      icon: Timer,
      roles: [
        "employee", "pm", "hr", "recruiter", "super admin",
        "bd", "bd manager", "dept head", "ceo", "coo", "client manager",
      ],
    },
    {
      id: "designations",
      label: "Designations & Grades",
      icon: Network,
      roles: ["hr", "admin", "super admin"],
    },
    {
      id: "salary-revisions",
      label: "Salary Revisions",
      icon: Trophy,
      roles: ["hr", "pm", "dept head", "admin", "super admin", "ceo"],
    },
    {
      id: "revision-cycles",
      label: "Revision Cycles",
      icon: BarChart3,
      roles: ["hr", "admin", "super admin"],
    },
    {
      id: "my-revisions",
      label: "My Revisions",
      icon: Trophy,
      roles: [
        "employee", "pm", "hr", "recruiter", "super admin",
        "bd", "bd manager", "dept head", "ceo", "coo", "client manager",
      ],
    },
    {
      id: "compliance-dashboard",
      label: "Compliance Dashboard",
      icon: ShieldCheck,
      roles: ["hr", "admin", "super admin", "ceo"],
    },
    {
      id: "statutory-filings",
      label: "Statutory Filings",
      icon: ScrollText,
      roles: ["hr", "admin", "super admin"],
    },
    {
      id: "statutory-reconciliation",
      label: "Statutory Reconciliation",
      icon: FileCheck,
      roles: ["hr", "admin", "super admin"],
    },
    {
      id: "statutory-config",
      label: "Statutory Configuration",
      icon: Shield,
      roles: ["hr", "admin", "super admin"],
    },
    {
      id: "my-tax-declaration",
      label: "My Tax Declaration",
      icon: FileText,
      roles: [
        "employee", "pm", "hr", "recruiter", "super admin",
        "bd", "bd manager", "dept head", "ceo", "coo", "client manager",
      ],
    },
    {
      id: "tax-declaration-queue",
      label: "Tax Declaration Queue",
      icon: FileCheck,
      roles: ["hr", "admin", "super admin"],
    },
    {
      id: "tds-reconciliation",
      label: "TDS Reconciliation",
      icon: BarChart3,
      roles: ["hr", "admin", "super admin", "ceo"],
    },
    {
      id: "form16-workspace",
      label: "Form 16 + 24Q",
      icon: FileSignature,
      roles: ["hr", "admin", "super admin"],
    },
    {
      id: "gratuity-dashboard",
      label: "Gratuity Liability",
      icon: Banknote,
      roles: ["hr", "admin", "super admin", "ceo"],
    },
    {
      id: "tax-config",
      label: "Tax Configuration",
      icon: Settings,
      roles: ["hr", "admin", "super admin"],
    },
    {
      id: "enriched-dashboard",
      label: "HR Insights",
      icon: BarChart3,
      roles: [
        "hr", "admin", "super admin", "ceo", "coo",
        "pm", "dept head",
      ],
    },
    {
      id: "reports-workspace",
      label: "Reports Catalog",
      icon: FileText,
      roles: [
        "hr", "admin", "super admin", "ceo", "coo",
        "pm", "dept head", "recruiter",
      ],
    },
    {
      id: "performance-workspace",
      label: "Performance",
      icon: Trophy,
      roles: [
        "employee", "pm", "hr", "recruiter", "super admin",
        "bd", "bd manager", "dept head", "ceo", "coo", "client manager",
      ],
    },
    {
      id: "expenses-workspace",
      label: "Expenses & Approvals",
      icon: Banknote,
      roles: [
        "employee", "pm", "hr", "recruiter", "super admin",
        "bd", "bd manager", "dept head", "ceo", "coo",
        "finance",
      ],
    },
  ];

  const filteredItems = menuItems.filter((item) =>
    item.roles.includes(role),
  );

  return (
    <motion.aside
      initial={false}
      animate={{ width: collapsed ? 80 : 280 }}
      className="bg-white border-r border-slate-200 text-[#64748B] flex flex-col h-screen fixed left-0 top-0 z-50 transition-all"
    >
      <div className="p-6 flex items-center justify-between overflow-hidden">
        {!collapsed && (
          <ImageWithFallback
            src={logoImg}
            alt="Logo"
            className="h-8 object-contain"
          />
        )}
        {collapsed && (
          <div className="w-8 h-8 bg-[#2563EB] rounded-lg flex items-center justify-center font-bold text-white text-xs">
            U E
          </div>
        )}
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="p-1.5 rounded-lg hover:bg-slate-100 transition-colors"
        >
          {collapsed ? (
            <ChevronRight
              size={18}
              className="text-[#64748B]"
            />
          ) : (
            <ChevronLeft size={18} className="text-[#64748B]" />
          )}
        </button>
      </div>

      <nav className="flex-1 px-4 space-y-1 mt-4 overflow-y-auto scrollbar-none">
        {filteredItems.map((item) => (
          <button
            key={item.id}
            onClick={() => setActiveTab(item.id)}
            className={cn(
              "relative w-full flex items-center p-3 rounded-xl transition-all duration-200 group text-left",
              activeTab === item.id
                ? "bg-[#2563EB]/10 text-[#2563EB]"
                : "hover:bg-slate-50 hover:text-[#0F172A]",
            )}
          >
            <item.icon
              className={cn(
                "w-5 h-5 flex-shrink-0 transition-colors",
                activeTab === item.id
                  ? "text-[#2563EB]"
                  : "text-[#64748B] group-hover:text-[#0F172A]",
              )}
            />
            {!collapsed && (
              <span className="ml-3 font-medium whitespace-nowrap overflow-hidden text-ellipsis flex-1">
                {item.label}
              </span>
            )}
            {badges[item.id] > 0 && (
              collapsed ? (
                <span className="absolute top-1.5 right-1.5 w-2 h-2 rounded-full bg-red-500" />
              ) : (
                <span className="ml-auto flex-shrink-0 min-w-[18px] h-[18px] rounded-full bg-red-500 text-white text-[9px] font-black flex items-center justify-center px-1">
                  {badges[item.id]}
                </span>
              )
            )}
            {!collapsed && activeTab === item.id && !(badges[item.id] > 0) && (
              <motion.div
                layoutId="active-indicator"
                className="ml-auto w-1.5 h-1.5 rounded-full bg-[#2563EB]"
              />
            )}
          </button>
        ))}
      </nav>

      <div className="p-4 mt-auto border-t border-slate-100">
        <button
          onClick={onLogout}
          className="w-full flex items-center p-3 rounded-xl text-[#64748B] hover:bg-red-50 hover:text-red-600 transition-all duration-200"
        >
          <LogOut className="w-5 h-5 flex-shrink-0" />
          {!collapsed && (
            <span className="ml-3 font-medium">Logout</span>
          )}
        </button>
      </div>
    </motion.aside>
  );
};