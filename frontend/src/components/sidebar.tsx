import React, { useEffect, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
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
  ChevronDown,
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
  Bell,
  Network,
  ScrollText,
  MapPin,
  Timer,
} from "lucide-react";
import { cn } from "./ui-elements";
import logoImg from "../assets/veliora-logo.png";
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

// Section P IA: every menu item carries an explicit `group` tag (the old
// id-prefix bucketing heuristic got crufty as ids multiplied). Sibling
// admin screens are consolidated into tabbed workspaces (see
// tabbed-workspaces.tsx), so one entry here can cover several screens.
const GROUP_ORDER = [
  "Overview",
  "My Work",
  "People",
  "Time & Attendance",
  "Payroll & Compensation",
  "Compliance",
  "Performance",
  "Approvals & Spend",
  "Reports & Analytics",
  "Business",
  "Administration",
] as const;
type GroupName = (typeof GROUP_ORDER)[number];

// Self-service audience: every human role. "admin" is a pure system
// account and "dop" is approvals-only by convention, so both stay out.
const EVERYONE: string[] = [
  "employee", "pm", "hr", "recruiter", "super admin", "bd", "bd manager",
  "dept head", "ceo", "coo", "client manager", "finance",
];

interface MenuItem {
  id: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  roles: string[];
  group: GroupName;
}

const menuItems: MenuItem[] = [
  // ---- Overview ---------------------------------------------------------
  {
    id: "role-dashboard",
    label: "My Cockpit",
    icon: LayoutDashboard,
    roles: [...EVERYONE, "admin"],
    group: "Overview",
  },
  {
    id: "dashboard",
    label: "My Workspace",
    icon: LayoutDashboard,
    roles: EVERYONE,
    group: "Overview",
  },

  // ---- My Work (self-service) ------------------------------------------
  {
    id: "timesheet",
    label: "My Timesheet",
    icon: CalendarDays,
    roles: EVERYONE,
    group: "My Work",
  },
  {
    id: "tasks",
    label: "My Tasks",
    icon: CheckSquare,
    roles: EVERYONE,
    group: "My Work",
  },
  {
    id: "leave",
    label: "My Leave",
    icon: FileText,
    roles: EVERYONE,
    group: "My Work",
  },
  {
    id: "my-shift",
    label: "My Shift",
    icon: Clock,
    roles: EVERYONE,
    group: "My Work",
  },
  {
    id: "my-overtime",
    label: "My Overtime",
    icon: Timer,
    roles: EVERYONE,
    group: "My Work",
  },
  {
    id: "my-pay",
    label: "My Pay",
    icon: Banknote,
    roles: EVERYONE,
    group: "My Work",
  },
  {
    id: "policies",
    label: "Policy Center",
    icon: BookOpen,
    roles: EVERYONE,
    group: "My Work",
  },
  {
    id: "profile",
    label: "Profile",
    icon: UserCircle,
    roles: EVERYONE,
    group: "My Work",
  },

  // ---- People (HR core) --------------------------------------------------
  {
    id: "hr-directory",
    label: "Employee Management",
    icon: Users,
    roles: ["hr", "super admin", "ceo"],
    group: "People",
  },
  {
    id: "hr-org-chart",
    label: "Org Chart",
    icon: Network,
    roles: ["hr", "super admin", "ceo", "coo"],
    group: "People",
  },
  {
    id: "hr-recruitment",
    label: "Recruitment",
    icon: Briefcase,
    roles: ["hr", "recruiter", "super admin", "ceo"],
    group: "People",
  },
  {
    id: "hr-onboarding",
    label: "Onboarding",
    icon: UserPlus,
    roles: ["hr", "recruiter", "super admin", "ceo"],
    group: "People",
  },
  {
    id: "hr-letters",
    label: "Employee Letters",
    icon: FileSignature,
    roles: ["hr", "super admin", "ceo"],
    group: "People",
  },

  // ---- Time & Attendance --------------------------------------------------
  {
    id: "hr-attendance",
    label: "Attendance Control",
    icon: Clock,
    roles: ["hr", "super admin", "ceo"],
    group: "Time & Attendance",
  },
  {
    id: "hr-leave",
    label: "Leave Approvals",
    icon: CalendarDays,
    roles: ["pm", "dept head"],
    group: "Time & Attendance",
  },
  {
    id: "shifts-workspace",
    label: "Shifts",
    icon: CalendarDays,
    roles: ["hr", "pm", "dept head", "admin", "super admin"],
    group: "Time & Attendance",
  },
  {
    id: "geo-workspace",
    label: "Geo Attendance",
    icon: MapPin,
    roles: ["hr", "admin", "super admin"],
    group: "Time & Attendance",
  },
  {
    id: "overtime-admin",
    label: "Overtime Admin",
    icon: Timer,
    roles: ["hr", "pm", "dept head", "admin", "super admin"],
    group: "Time & Attendance",
  },
  {
    id: "hr-holidays",
    label: "Holiday Calendar",
    icon: CalendarDays,
    roles: ["hr", "super admin", "ceo"],
    group: "Time & Attendance",
  },

  // ---- Payroll & Compensation ---------------------------------------------
  {
    id: "hr-payroll",
    label: "Payroll Bureau",
    icon: CreditCard,
    roles: ["hr", "super admin", "ceo"],
    group: "Payroll & Compensation",
  },
  {
    id: "hr-advances",
    label: "Salary Advances",
    icon: Banknote,
    roles: ["hr", "super admin", "ceo"],
    group: "Payroll & Compensation",
  },
  {
    id: "revisions-workspace",
    label: "Salary Revisions",
    icon: Trophy,
    roles: ["hr", "pm", "dept head", "admin", "super admin", "ceo"],
    group: "Payroll & Compensation",
  },
  {
    id: "designations",
    label: "Designations & Grades",
    icon: Network,
    roles: ["hr", "admin", "super admin"],
    group: "Payroll & Compensation",
  },

  // ---- Compliance ----------------------------------------------------------
  {
    id: "compliance-dashboard",
    label: "Compliance Dashboard",
    icon: ShieldCheck,
    roles: ["hr", "admin", "super admin", "ceo"],
    group: "Compliance",
  },
  {
    id: "statutory-workspace",
    label: "Statutory (PF / ESIC / PT)",
    icon: ScrollText,
    roles: ["hr", "admin", "super admin"],
    group: "Compliance",
  },
  {
    id: "tax-workspace",
    label: "Tax & TDS",
    icon: FileCheck,
    roles: ["hr", "admin", "super admin", "ceo"],
    group: "Compliance",
  },

  // ---- Performance ----------------------------------------------------------
  {
    id: "performance-workspace",
    label: "Performance",
    icon: Trophy,
    roles: EVERYONE,
    group: "Performance",
  },

  // ---- Approvals & Spend -----------------------------------------------------
  {
    id: "approvals",
    label: "Approvals Center",
    icon: FileCheck,
    roles: [
      "pm", "hr", "recruiter", "bd", "bd manager", "dept head",
      "dop", "coo", "admin", "super admin", "ceo",
    ],
    group: "Approvals & Spend",
  },
  {
    id: "expenses-workspace",
    label: "Expenses & Travel",
    icon: Banknote,
    roles: EVERYONE,
    group: "Approvals & Spend",
  },
  {
    id: "cost-approvals",
    label: "Cost Adjudication",
    icon: ShieldCheck,
    roles: ["pm", "dop", "coo", "super admin", "ceo"],
    group: "Approvals & Spend",
  },

  // ---- Reports & Analytics -----------------------------------------------------
  {
    id: "hr-dashboard",
    label: "HR Intelligence",
    icon: LayoutDashboard,
    roles: ["hr", "recruiter", "super admin", "ceo"],
    group: "Reports & Analytics",
  },
  {
    id: "enriched-dashboard",
    label: "HR Insights",
    icon: BarChart3,
    roles: ["hr", "admin", "super admin", "ceo", "coo", "pm", "dept head"],
    group: "Reports & Analytics",
  },
  {
    id: "coo-dashboard",
    label: "COO Operations Hub",
    icon: Activity,
    roles: ["coo", "super admin", "ceo", "dop"],
    group: "Reports & Analytics",
  },
  {
    id: "hr-reports",
    label: "Enterprise Analytics",
    icon: BarChart3,
    roles: ["hr", "super admin", "ceo", "coo"],
    group: "Reports & Analytics",
  },
  {
    id: "reports-workspace",
    label: "Reports Catalog",
    icon: FileText,
    roles: [
      "hr", "admin", "super admin", "ceo", "coo",
      "pm", "dept head", "recruiter",
    ],
    group: "Reports & Analytics",
  },

  // ---- Business ------------------------------------------------------------------
  {
    id: "bd",
    label: "Business Development",
    icon: Target,
    roles: ["bd", "bd manager", "super admin", "ceo", "coo"],
    group: "Business",
  },
  {
    id: "projects",
    label: "Project Deliverables",
    icon: Briefcase,
    roles: [
      "pm", "dop", "coo", "super admin", "dept head", "ceo",
      "client manager",
    ],
    group: "Business",
  },
  {
    id: "pm-bids",
    label: "Bid Requests",
    icon: ClipboardList,
    roles: ["pm", "super admin", "ceo", "coo"],
    group: "Business",
  },
  {
    id: "client-details",
    label: "Client Details",
    icon: Building2,
    roles: ["client manager", "super admin", "bd", "bd manager"],
    group: "Business",
  },

  // ---- Administration ----------------------------------------------------------------
  {
    id: "admin",
    label: "System Administration",
    icon: Shield,
    roles: ["admin", "super admin", "ceo"],
    group: "Administration",
  },
  {
    id: "functional-areas",
    label: "Functional Areas",
    icon: Settings,
    roles: ["admin", "super admin"],
    group: "Administration",
  },
  {
    id: "plumbing-admin",
    label: "Bank / DQ / Jobs",
    icon: CreditCard,
    roles: [
      "employee", "pm", "hr", "recruiter", "super admin",
      "admin", "dept head", "finance", "ceo", "coo",
    ],
    group: "Administration",
  },
  {
    id: "notifications-workspace",
    label: "Notifications",
    icon: Bell,
    roles: [...EVERYONE, "admin"],
    group: "Administration",
  },
  {
    id: "hr-audit-log",
    label: "Audit Log",
    icon: ScrollText,
    roles: ["super admin", "ceo"],
    group: "Administration",
  },
];

export const Sidebar = ({
  activeTab,
  setActiveTab,
  collapsed,
  setCollapsed,
  role,
  onLogout,
  badges = {},
}: SidebarProps) => {
  const filteredItems = menuItems.filter((item) =>
    item.roles.includes(role),
  );

  const groupedItems = GROUP_ORDER.map((gn) => ({
    name: gn,
    items: filteredItems.filter((it) => it.group === gn),
  })).filter((g) => g.items.length > 0);

  const activeGroup = groupedItems.find((g) =>
    g.items.some((it) => it.id === activeTab),
  )?.name;

  // Expanded groups persist per browser; the group holding the active
  // tab is always forced open so navigation never hides the current
  // page. First visit: only the active group (or the first) is open.
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>(
    () => {
      try {
        const saved = localStorage.getItem("hr_sidebar_groups");
        if (saved) return JSON.parse(saved);
      } catch { /* corrupted state -> defaults */ }
      return {};
    },
  );

  useEffect(() => {
    if (activeGroup && !openGroups[activeGroup]) {
      setOpenGroups((prev) => ({ ...prev, [activeGroup]: true }));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeGroup]);

  const toggleGroup = (name: string) => {
    setOpenGroups((prev) => {
      const next = { ...prev, [name]: !prev[name] };
      try {
        localStorage.setItem("hr_sidebar_groups", JSON.stringify(next));
      } catch { /* storage full/blocked -> non-fatal */ }
      return next;
    });
  };

  const isOpen = (name: string) =>
    openGroups[name] ?? (name === (activeGroup ?? groupedItems[0]?.name));

  // "Overview" items stay pinned above the collapsible sections — the
  // daily-driver pages shouldn't hide behind a toggle.
  const pinnedItems =
    groupedItems.find((g) => g.name === "Overview")?.items ?? [];
  const sections = groupedItems.filter((g) => g.name !== "Overview");

  const renderItem = (item: (typeof menuItems)[number], tree = false) => (
    <button
      key={item.id}
      onClick={() => setActiveTab(item.id)}
      aria-label={item.label}
      className={cn(
        "relative w-full flex items-center rounded-lg transition-all duration-200 group text-left",
        tree && !collapsed ? "px-2 py-1.5" : "p-2.5",
        activeTab === item.id
          ? "bg-[#2563EB]/10 text-[#2563EB]"
          : "text-[#64748B] hover:bg-slate-50 hover:text-[#0F172A]",
      )}
    >
      <item.icon
        className={cn(
          "flex-shrink-0 transition-colors",
          tree && !collapsed ? "sb-icon-sm" : "w-5 h-5",
          activeTab === item.id
            ? "text-[#2563EB]"
            : "text-slate-400 group-hover:text-[#0F172A]",
        )}
      />
      {!collapsed && (
        <span
          className={cn(
            "ml-2 whitespace-nowrap overflow-hidden text-ellipsis flex-1",
            tree ? "sb-item-sm" : "text-sm",
            activeTab === item.id ? "font-semibold" : "font-medium",
          )}
        >
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
          <div className="w-8 h-8 bg-[#2563EB] rounded-lg flex items-center justify-center font-bold text-white text-sm">
            V
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

      <nav className="flex-1 px-3 mt-2 pb-4 overflow-y-auto scrollbar-none">
        {pinnedItems.length > 0 && (
          <div className="space-y-1">
            {pinnedItems.map((item) => renderItem(item))}
          </div>
        )}
        {pinnedItems.length > 0 && sections.length > 0 && (
          <div className={cn("border-t border-slate-100", collapsed ? "mx-3 my-2" : "mx-2 my-2")} />
        )}

        {collapsed ? (
          sections.map((g, gi) => (
            <div key={g.name}>
              {gi > 0 && <div className="mx-3 my-2 border-t border-slate-100" />}
              {g.items.map((item) => renderItem(item))}
            </div>
          ))
        ) : (
          <div className="space-y-1">
            {sections.map((g) => {
              const open = isOpen(g.name);
              const groupBadgeCount = g.items.reduce(
                (sum, it) => sum + (badges[it.id] || 0), 0,
              );
              return (
                <div key={g.name}>
                  <button
                    onClick={() => toggleGroup(g.name)}
                    aria-label={`${g.name} section`}
                    aria-expanded={open}
                    className={cn(
                      "w-full flex items-center gap-2 px-2.5 py-1.5 rounded-lg transition-colors hover:bg-slate-100",
                      open ? "text-slate-700" : "text-slate-500 hover:text-slate-600",
                    )}
                  >
                    <span className="flex-1 text-left sb-group-label font-bold uppercase whitespace-nowrap overflow-hidden text-ellipsis">
                      {g.name}
                    </span>
                    {!open && groupBadgeCount > 0 && (
                      <span className="min-w-[16px] h-[16px] rounded-full bg-red-500 text-white text-[9px] font-black flex items-center justify-center px-1">
                        {groupBadgeCount}
                      </span>
                    )}
                    <ChevronDown
                      size={13}
                      className={cn(
                        "flex-shrink-0 text-slate-400 transition-transform duration-200",
                        !open && "sb-rot-closed",
                      )}
                    />
                  </button>
                  <AnimatePresence initial={false}>
                    {open && (
                      <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: "auto", opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        transition={{ duration: 0.18, ease: "easeOut" }}
                        className="overflow-hidden"
                      >
                        <div className="ml-3 mt-0.5 mb-1 pl-2 border-l border-slate-200 space-y-1">
                          {g.items.map((item) => renderItem(item, true))}
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
              );
            })}
          </div>
        )}
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
