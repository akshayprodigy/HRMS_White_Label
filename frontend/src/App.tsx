import React, { useState, useEffect } from 'react';
import { Toaster, toast } from 'sonner';
import { Sidebar } from './components/sidebar';
import { Header } from './components/header';
import { AuthView } from './components/auth-view';
import { DashboardView } from './components/dashboard-view';
import { WorklogView } from './components/worklog-view';
import { TimesheetView } from './components/timesheet-view';
import { TasksView } from './components/tasks-view';
import { LeaveView } from './components/leave-view';
import { ProfileView } from './components/profile-view';
import { AttendanceModal } from './components/attendance-modal';
import { ProjectsView } from './components/projects-view';
import { COODashboardView } from './components/coo-dashboard-view';
import { CostApprovalsView } from './components/cost-approvals-view';
import { BDView } from './components/bd-view';
import { ClientDetailsView } from './components/client-details-view';
import { PMBidRequestsView } from './components/pm-bid-requests-view';

import { ApprovalsView } from './components/approvals-view';
// New HR Redesign Imports
import { HRDashboard } from './components/hr-dashboard';
import { EmployeeManagement } from './components/employee-management';
import { LeaveHR } from './components/leave-hr';
import { PayrollHR } from './components/payroll-hr';
import { SalaryAdvanceManagement } from './components/salary-advance';
import { MyPayslips } from './components/my-payslips';
import { RecruitmentHR } from './components/recruitment-hr';
import { OnboardingHR, PolicyCenter } from './components/onboarding-hr';
import { HRReports } from './components/hr-reports';
import { LettersHR } from './components/letters-hr';
import { ExecutiveReports } from './components/executive-reports';
import { AdminView } from './components/admin-view';
import { OrgChartView } from './components/org-chart-view';
import { AuditLogView } from './components/audit-log-view';
import { PolicyView } from './components/policy-view';
import { HolidayManagement } from './components/holiday-management';
import { FunctionalAreasAdmin } from './components/functional-areas-admin';
import { ShiftTemplatesAdmin } from './components/shift-templates-admin';
import { EmployeeShiftAssignmentsView } from './components/employee-shift-assignments';
import { AttendanceFlaggedReview } from './components/attendance-flagged-review';
import { GeoFenceLocationsAdmin } from './components/geofence-locations-admin';
import { EmployeeGeoAssignments } from './components/employee-geo-assignments';
import { OvertimeRulesAdmin } from './components/overtime-rules-admin';
import { NightAllowanceRulesAdmin } from './components/night-allowance-rules-admin';
import { OvertimeApprovalQueue } from './components/overtime-approval-queue';
import { MyOvertimeView } from './components/my-overtime';
import { MyShiftView } from './components/my-shift-view';
import { DesignationGradeAdmin } from './components/designation-grade-admin';
import { SalaryRevisionsView } from './components/salary-revisions';
import { RevisionCyclesView } from './components/revision-cycles';
import { MyRevisionsView } from './components/my-revisions';
import { StatutoryConfigAdmin } from './components/statutory-config-admin';
import { StatutoryFilingsView } from './components/statutory-filings';
import { StatutoryReconciliationView } from './components/statutory-reconciliation';
import { ComplianceDashboardView } from './components/compliance-dashboard';
import { TaxConfigAdmin } from './components/tax-config-admin';
import { MyTaxDeclarationView } from './components/my-tax-declaration';
import { TaxDeclarationQueue } from './components/tax-declaration-queue';
import { TDSReconciliationView } from './components/tds-reconciliation';
import { Form16Workspace } from './components/form16-workspace';
import { GratuityDashboardView } from './components/gratuity-dashboard';
import { ReportsWorkspace } from './components/reports-workspace';
import { EnrichedDashboardView } from './components/enriched-dashboard';
import { PerformanceWorkspace } from './components/performance-workspace';
import { ExpensesWorkspace } from './components/expenses-workspace';
import { PlumbingAdmin } from './components/plumbing-admin';
import { NotificationsWorkspace } from './components/notifications-workspace';
import {
  AttendanceWorkspace,
  ShiftsWorkspace,
  GeoWorkspace,
  OvertimeAdminWorkspace,
  RevisionsWorkspace,
  StatutoryWorkspace,
  TaxWorkspace,
  MyPayWorkspace,
} from './components/tabbed-workspaces';

import { cn } from './components/ui-elements';
import { UserRole } from './types/erp';
import { client, setAccessToken } from './api/client';
import { ENDPOINTS } from './api/endpoints';
import { TimerProvider } from './contexts/timer-context';
import { pickPrimaryRole } from './utils/roles';
import { useIsMobile } from './mobile/use-is-mobile';
import { MobileShell } from './mobile/mobile-shell';

const App = () => {
  const isMobileViewport = useIsMobile();
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [userRole, setUserRole] = useState<UserRole>('employee');
  const [userInfo, setUserInfo] = useState<{name: string, avatar?: string} | null>(null);
  // Single landing page: My Workspace embeds the role Command Center
  // (the old separate "My Cockpit" tab is aliased below).
  const [activeTab, setActiveTab] = useState('dashboard');
  const handleSetActiveTab = (tab: string) => {
    setActiveTab(tab);
    if (tab === 'tasks') setSidebarBadges((prev) => ({ ...prev, tasks: 0 }));
  };
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [loginLoading, setLoginLoading] = useState(false);
  const [loginError, setLoginError] = useState('');
  const [hasMarkedAttendance, setHasMarkedAttendance] = useState(false);
  const [hasPunchedOut, setHasPunchedOut] = useState(false);
  const [isImpersonated, setIsImpersonated] = useState(false);
  const [sidebarBadges, setSidebarBadges] = useState<Record<string, number>>({});

  const userData = {
    name: userInfo?.name || 'Loading...',
    role: userRole,
    avatar: userInfo?.avatar || 'https://images.unsplash.com/photo-1494790108377-be9c29b29330?auto=format&fit=crop&q=80&w=200'
  };

  // Fetch the current user's uploaded avatar and store it as a blob object URL.
  // Returns null if the user has no avatar on file.
  const fetchAvatarBlob = async (): Promise<string | null> => {
    try {
      const res = await client.get(ENDPOINTS.HR.MY_AVATAR, { responseType: 'blob' });
      return URL.createObjectURL(res.data);
    } catch {
      return null;
    }
  };

  // Called from ProfileView after a successful upload so the header updates instantly.
  const handleAvatarUpdated = (url: string) => {
    setUserInfo(prev => {
      if (prev?.avatar && prev.avatar.startsWith('blob:')) {
        URL.revokeObjectURL(prev.avatar);
      }
      return { name: prev?.name || '', avatar: url };
    });
  };

  useEffect(() => {
    const initApp = async () => {
      const auth = localStorage.getItem('hr_auth');
      const role = localStorage.getItem('hr_role') as UserRole;
      if (auth === 'true' && role) {
        setIsLoggedIn(true);
        setUserRole(role);
        
        // Initial attendance check from API
        try {
          const refreshToken = localStorage.getItem('refresh_token');
          if (!refreshToken) {
            handleLogout();
            setIsLoading(false);
            return;
          }

          try {
            const refreshRes = await client.post(ENDPOINTS.AUTH.REFRESH, {
              refresh_token: refreshToken,
            });
            const { access_token, refresh_token } = refreshRes.data || {};
            if (access_token) setAccessToken(access_token);
            if (refresh_token) localStorage.setItem('refresh_token', refresh_token);
          } catch (refreshErr: any) {
            console.warn('Token refresh failed during init', refreshErr);
            handleLogout();
            setIsLoading(false);
            return;
          }

          const userResponse = await client.get(ENDPOINTS.AUTH.ME);
          const userData = userResponse.data;

          // Update role from server to ensure accuracy
          const serverRoleNames = (userData.roles || []).map((r: any) => r?.name).filter(Boolean);
          const currentRole: UserRole = pickPrimaryRole({
            isSuperuser: Boolean(userData.is_superuser),
            roleNames: serverRoleNames,
          });

          setUserRole(currentRole);
          localStorage.setItem('hr_role', currentRole);
          setIsImpersonated(userData.is_impersonated);

          const avatarBlobUrl = await fetchAvatarBlob();
          setUserInfo({
            name: userData.full_name,
            avatar: avatarBlobUrl || 'https://images.unsplash.com/photo-1494790108377-be9c29b29330?auto=format&fit=crop&q=80&w=200'
          });

          const response = await client.get(ENDPOINTS.ATTENDANCE.TODAY);
          setHasMarkedAttendance(response.data.is_marked);
          setHasPunchedOut(Boolean(response.data?.attendance?.punch_out_time));

          // Everyone lands on My Workspace — the embedded Command
          // Center adapts it to the user's role(s).
          setActiveTab('dashboard');
        } catch (error: any) {
          console.error("Failed to fetch initial session data", error);
          
          // Only force logout on 401 Unauthorized. 
          // 403 is often due to attendance gating and should be handled by the UI.
          if (error.response?.status === 401) {
            handleLogout();
          } else {
            // API failed for a non-auth reason — still land on the
            // unified workspace.
            setActiveTab('dashboard');
          }
        }
      }
      setIsLoading(false);
    };
    
    initApp();
  }, []);

  const handleLogin = async (email: string, password: string) => {
    try {
      setLoginLoading(true);
      setLoginError('');
      const formData = new FormData();
      formData.append('username', email);
      formData.append('password', password);
      
      const response = await client.post(ENDPOINTS.AUTH.LOGIN, formData);
      const { access_token, refresh_token } = response.data;
      
      setAccessToken(access_token);
      localStorage.setItem('refresh_token', refresh_token);
      
      // Get user info to determine role
      const userResponse = await client.get(ENDPOINTS.AUTH.ME);
      const userData = userResponse.data;

      const serverRoleNames = (userData.roles || []).map((r: any) => r?.name).filter(Boolean);
      const role: UserRole = pickPrimaryRole({
        isSuperuser: Boolean(userData.is_superuser),
        roleNames: serverRoleNames,
      });
      
      setUserRole(role);
      localStorage.setItem('hr_role', role);
      setIsLoggedIn(true);
      setIsImpersonated(userData.is_impersonated);

      const avatarBlobUrl = await fetchAvatarBlob();
      setUserInfo({
        name: userData.full_name,
        avatar: avatarBlobUrl || 'https://images.unsplash.com/photo-1494790108377-be9c29b29330?auto=format&fit=crop&q=80&w=200'
      });
      localStorage.setItem('hr_auth', 'true');
      
      // Check attendance status via API instead of localStorage
      try {
        const attendResponse = await client.get(ENDPOINTS.ATTENDANCE.TODAY);
        setHasMarkedAttendance(attendResponse.data.is_marked);
        setHasPunchedOut(Boolean(attendResponse.data?.attendance?.punch_out_time));
      } catch (error) {
        console.warn("Attendance status check skipped", error);
        setHasMarkedAttendance(false);
        setHasPunchedOut(false);
      }

      // Everyone lands on My Workspace — the embedded Command Center
      // adapts it to the user's role(s).
      setActiveTab('dashboard');

      toast.success(`Welcome back, ${userData.full_name}!`);
    } catch (error: any) {
      console.error('Login failed:', error);
      let errorMsg = 'Invalid credentials. Please check your email and password.';
      if (error.response?.status === 401) {
        errorMsg = 'Incorrect email or password. Please try again.';
      } else if (error.response?.status === 400) {
        errorMsg = error.response?.data?.detail || 'Your account is inactive. Please contact HR.';
      } else if (error.response?.status === 422) {
        errorMsg = 'Please enter both email and password.';
      } else if (!error.response) {
        errorMsg = 'Unable to connect to server. Please check your internet connection.';
      } else {
        errorMsg = error.response?.data?.detail || errorMsg;
      }
      setLoginError(errorMsg);
      toast.error('Login failed', { description: errorMsg });
    } finally {
      setLoginLoading(false);
    }
  };

  const handleAttendanceSuccess = () => {
    const today = new Date().toISOString().split('T')[0];
    localStorage.setItem(`attendance_${today}`, 'true');
    setHasMarkedAttendance(true);
    toast.success("Attendance marked successfully");
  };

  const handleLogout = () => {
    setIsLoggedIn(false);
    localStorage.removeItem('hr_auth');
    localStorage.removeItem('hr_role');
    localStorage.removeItem('refresh_token');
    setAccessToken(null);
    setHasMarkedAttendance(false);
    setHasPunchedOut(false);
    toast.info("You have been logged out.");
  };

  // Global response interceptor to handle session expiration
  useEffect(() => {
    const interceptor = client.interceptors.response.use(
      (response) => response,
      (error) => {
        // Only logout on 401 (Unauthorized). 
        // 403 (Forbidden) is used for the Attendance Gate and should be handled by UI guards.
        if (error.response?.status === 401) {
          if (isLoggedIn) {
            handleLogout();
            toast.error("Session expired", {
              description: "Please log in again to continue."
            });
          }
        }
        return Promise.reject(error);
      }
    );
    
    return () => {
      client.interceptors.response.eject(interceptor);
    };
  }, [isLoggedIn]);

  // Lightweight navigation bridge for modules that don't receive onNavigate.
  useEffect(() => {
    const handler: EventListener = (event) => {
      const detail = (event as CustomEvent<{ tab?: string }>).detail;
      const tab = detail?.tab;
      if (typeof tab === 'string' && tab) {
        setActiveTab(tab);
      }
    };

    window.addEventListener('erp:navigate', handler);
    return () => {
      window.removeEventListener('erp:navigate', handler);
    };
  }, []);

  // Poll for pending badges. Combines the legacy PM tasks count with
  // the Section J dashboard-wide pending count (approvals + reviews +
  // self-actions the user owes) so the cockpit entry shows a single
  // total.
  useEffect(() => {
    if (!isLoggedIn) return;
    const fetchBadges = async () => {
      try {
        const [tasksR, cockpitR] = await Promise.all([
          client.get(ENDPOINTS.TASKS.MY_PENDING_ACTIONS_COUNT)
            .catch(() => ({ data: { count: 0 } })),
          client.get(ENDPOINTS.DASHBOARD.PENDING_COUNT)
            .catch(() => ({ data: { count: 0 } })),
        ]);
        const next: Record<string, number> = {};
        const taskCount = tasksR.data?.count ?? 0;
        if (taskCount > 0) next.tasks = taskCount;
        const cockpitCount = cockpitR.data?.count ?? 0;
        if (cockpitCount > 0) next['dashboard'] = cockpitCount;
        setSidebarBadges(next);
      } catch {
        // silently ignore
      }
    };
    fetchBadges();
    const interval = setInterval(fetchBadges, 30000);
    return () => clearInterval(interval);
  }, [isLoggedIn]);

  if (isLoading) {
    return (
      <div className="min-h-screen bg-[#F8FAFC] flex items-center justify-center">
        <div className="w-12 h-12 border-4 border-[#2563EB] border-t-transparent rounded-full animate-spin"></div>
      </div>
    );
  }

  if (!isLoggedIn) {
    return (
      <>
        <AuthView onLogin={handleLogin} isLoading={loginLoading} loginError={loginError} />
        <Toaster position="top-right" richColors />
      </>
    );
  }

  const renderContent = () => {
    switch (activeTab) {
      case 'dashboard':
        return <DashboardView attendanceMarked={hasMarkedAttendance} alreadyPunchedOut={hasPunchedOut} onPunchedOut={() => setHasPunchedOut(true)} onNavigate={setActiveTab} onLogout={handleLogout} userRole={userRole} />;
      case 'worklog':
        return <WorklogView />;
      case 'timesheet':
        return <TimesheetView />;
      case 'tasks':
        return <TasksView />;
      case 'leave':
        return <LeaveView />;

      // HR Module Redesign Content
      case 'hr-dashboard':
        return <HRDashboard onNavigate={setActiveTab} />;
      case 'hr-directory':
        return <EmployeeManagement userRole={userRole} />;
      case 'hr-attendance':
      case 'attendance-hr': // legacy drill route emitted by the dashboard service
        return <AttendanceWorkspace role={userRole} />;
      case 'shifts-workspace':
        return <ShiftsWorkspace role={userRole} />;
      case 'geo-workspace':
        return <GeoWorkspace role={userRole} />;
      case 'overtime-admin':
        return <OvertimeAdminWorkspace role={userRole} />;
      case 'revisions-workspace':
        return <RevisionsWorkspace role={userRole} />;
      case 'statutory-workspace':
        return <StatutoryWorkspace role={userRole} />;
      case 'tax-workspace':
        return <TaxWorkspace role={userRole} />;
      case 'my-pay':
        return <MyPayWorkspace />;
      case 'hr-leave':
        return <LeaveHR />;
      case 'approvals':
      case 'approvals-view': // legacy drill route emitted by the dashboard service
        return <ApprovalsView />;
      case 'hr-payroll':
        return <PayrollHR />;
      case 'hr-advances':
        return <SalaryAdvanceManagement />;
      case 'my-payslips':
        return <MyPayslips />;
      case 'hr-recruitment':
        return <RecruitmentHR />;
      case 'hr-onboarding':
        return <OnboardingHR />;
      case 'hr-holidays':
        return <HolidayManagement />;
      case 'hr-letters':
        return <LettersHR />;
      case 'policies':
        return <PolicyView />;
      case 'admin':
        return <AdminView />;
      case 'functional-areas':
        return <FunctionalAreasAdmin />;
      case 'shift-templates':
        return <ShiftTemplatesAdmin />;
      case 'shift-assignments':
        return <EmployeeShiftAssignmentsView />;
      case 'hr-attendance-review':
        return <AttendanceFlaggedReview />;
      case 'geo-fences':
        return <GeoFenceLocationsAdmin />;
      case 'employee-geo':
        return <EmployeeGeoAssignments />;
      case 'overtime-rules':
        return <OvertimeRulesAdmin />;
      case 'night-allowance-rules':
        return <NightAllowanceRulesAdmin />;
      case 'overtime-approvals':
        return <OvertimeApprovalQueue />;
      case 'my-overtime':
        return <MyOvertimeView />;
      case 'my-shift':
        return <MyShiftView />;
      case 'designations':
        return <DesignationGradeAdmin />;
      case 'salary-revisions':
        return <SalaryRevisionsView />;
      case 'revision-cycles':
        return <RevisionCyclesView />;
      case 'my-revisions':
        return <MyRevisionsView />;
      case 'statutory-config':
        return <StatutoryConfigAdmin />;
      case 'statutory-filings':
        return <StatutoryFilingsView />;
      case 'statutory-reconciliation':
        return <StatutoryReconciliationView />;
      case 'compliance-dashboard':
        return <ComplianceDashboardView />;
      case 'tax-config':
        return <TaxConfigAdmin />;
      case 'my-tax-declaration':
        return <MyTaxDeclarationView />;
      case 'tax-declaration-queue':
        return <TaxDeclarationQueue />;
      case 'tds-reconciliation':
        return <TDSReconciliationView />;
      case 'form16-workspace':
        return <Form16Workspace />;
      case 'gratuity-dashboard':
        return <GratuityDashboardView />;
      case 'reports-workspace':
        return <ReportsWorkspace />;
      case 'enriched-dashboard':
        return <EnrichedDashboardView />;
      case 'performance-workspace':
        return <PerformanceWorkspace />;
      case 'expenses-workspace':
        return <ExpensesWorkspace />;
      case 'role-dashboard':
        // Legacy alias — the cockpit now lives inside My Workspace.
        return <DashboardView attendanceMarked={hasMarkedAttendance} alreadyPunchedOut={hasPunchedOut} onPunchedOut={() => setHasPunchedOut(true)} onNavigate={setActiveTab} onLogout={handleLogout} userRole={userRole} />;
      case 'plumbing-admin':
        return <PlumbingAdmin />;
      case 'notifications-workspace':
        return <NotificationsWorkspace />;
      case 'hr-reports':
        return userRole === 'ceo' || userRole === 'super admin' || userRole === 'coo' ? <ExecutiveReports /> : <HRReports />;
      case 'hr-org-chart':
        return <OrgChartView />;
      case 'hr-audit-log':
        return <AuditLogView />;

      case 'coo-dashboard':
        return <COODashboardView />;
      case 'projects':
        return <ProjectsView userRole={userRole} />;
      case 'cost-approvals':
        return <CostApprovalsView />;
      case 'pm-bids':
        return <PMBidRequestsView />;
      case 'bd':
        return <BDView userRole={userRole} />;
      case 'client-details':
        return <ClientDetailsView userRole={userRole} />;
      case 'profile':
        return <ProfileView avatarUrl={userData.avatar} userName={userData.name} userRole={userData.role} onAvatarUpdated={handleAvatarUpdated} />;
      default:
        return <DashboardView attendanceMarked={hasMarkedAttendance} alreadyPunchedOut={hasPunchedOut} onPunchedOut={() => setHasPunchedOut(true)} onNavigate={setActiveTab} onLogout={handleLogout} userRole={userRole} />;
    }
  };

  const getPageTitle = () => {
    const titles: Record<string, string> = {
      dashboard: 'My Workspace',
      worklog: 'Daily Worklog',
      timesheet: 'Weekly Timesheets',
      tasks: 'My Tasks & Subtasks',
      leave: 'Leave & Attendance',
      'hr-dashboard': 'HR Intelligence Dashboard',
      'hr-directory': 'Employee Management System',
      'hr-attendance': 'Attendance Control',
      'attendance-hr': 'Attendance Control',
      'shifts-workspace': 'Shift Management',
      'geo-workspace': 'Geo Attendance',
      'overtime-admin': 'Overtime Administration',
      'revisions-workspace': 'Salary Revisions',
      'statutory-workspace': 'Statutory Compliance',
      'tax-workspace': 'Tax & TDS',
      'my-pay': 'My Pay',
      'approvals-view': 'Approvals Center',
      'hr-leave': 'Leave Approval Bureau',
      'hr-payroll': 'Payroll & Compensation',
      'hr-advances': 'Salary Advances',
      'my-payslips': 'My Payslips',
      'hr-recruitment': 'Talent Acquisition Pipeline',
      'hr-onboarding': 'New Joiner Tracker',
      'hr-holidays': 'Holiday Calendar Management',
      'hr-letters': 'Employee Letter Generation',
      'policies': 'Policy Center',
      'admin': 'Admin Panel',
      'functional-areas': 'Functional Areas',
      'shift-templates': 'Shift Templates',
      'shift-assignments': 'Shift Assignments',
      'hr-attendance-review': 'Attendance Review Queue',
      'geo-fences': 'Geo-Fence Locations',
      'employee-geo': 'Employee Geo-Fence Assignment',
      'overtime-rules': 'Overtime Rules',
      'night-allowance-rules': 'Night-Shift Allowance Rules',
      'overtime-approvals': 'Overtime Approvals',
      'my-overtime': 'My Overtime & Allowance',
      'my-shift': 'My Shift',
      'designations': 'Designations & Grades',
      'salary-revisions': 'Salary Revisions',
      'revision-cycles': 'Revision Cycles',
      'my-revisions': 'My Revisions',
      'statutory-config': 'Statutory Configuration',
      'statutory-filings': 'Statutory Filings',
      'statutory-reconciliation': 'Statutory Reconciliation',
      'compliance-dashboard': 'Compliance Dashboard',
      'tax-config': 'Tax Configuration',
      'my-tax-declaration': 'My Tax Declaration',
      'tax-declaration-queue': 'Tax Declaration Queue',
      'tds-reconciliation': 'TDS Reconciliation',
      'form16-workspace': 'Form 16 + Form 24Q',
      'gratuity-dashboard': 'Gratuity Liability',
      'reports-workspace': 'Reports Catalog',
      'enriched-dashboard': 'HR Insights',
      'performance-workspace': 'Performance Management',
      'expenses-workspace': 'Expenses, Travel & Approvals',
      'role-dashboard': 'My Workspace',
      'plumbing-admin': 'Bank / Data-Quality / Jobs',
      'notifications-workspace': 'Notifications',
      'hr-reports': 'HR Analytics & Reports',
      'hr-org-chart': 'Organisation Chart',
      'hr-audit-log': 'Audit Log',
      'coo-dashboard': 'COO Operations Hub',
      projects: 'Project Portfolio',
      'cost-approvals': 'Financial Adjudication',
      'pm-bids': 'My Bid Requests',
      bd: 'Business Development Pipeline',
      'client-details': 'Client Details',
      profile: 'User Profile',
    };
    return titles[activeTab] || 'ERP System';
  };

  // On mobile viewports (or when ?mobile=1 is set) hand control to the
  // PWA shell. The shell has its own dedicated attendance screen, so we
  // skip the desktop AttendanceModal there.
  if (isMobileViewport) {
    return (
      <TimerProvider>
        <MobileShell
          userRole={userRole}
          userName={userData.name}
          avatarUrl={userData.avatar}
          hasMarkedAttendance={hasMarkedAttendance}
          hasPunchedOut={hasPunchedOut}
          onAttendanceSuccess={handleAttendanceSuccess}
          onPunchedOut={() => setHasPunchedOut(true)}
          onLogout={handleLogout}
        />
      </TimerProvider>
    );
  }

  return (
    <TimerProvider>
      <div className="min-h-screen bg-[#F8FAFC] flex">
        {/* Attendance Modal is now mandatory for ALL roles (including HR) after login */}
        {!hasMarkedAttendance && userRole !== 'super admin' && userRole !== 'admin' && (
          <AttendanceModal onSuccess={handleAttendanceSuccess} />
        )}

        <Sidebar
          activeTab={activeTab}
          setActiveTab={handleSetActiveTab}
          collapsed={sidebarCollapsed}
          setCollapsed={setSidebarCollapsed}
          role={userRole}
          onLogout={handleLogout}
          badges={sidebarBadges}
        />

        <main className={cn(
          "flex-1 flex flex-col min-w-0 transition-all duration-300",
          sidebarCollapsed ? "ml-20" : "ml-0 lg:ml-[280px]"
        )}>
          <Header 
            title={getPageTitle()} 
            userName={userData.name}
            userRole={userData.role}
            avatarUrl={userData.avatar}
            onLogout={handleLogout}
            onNavigate={setActiveTab}
            isImpersonated={isImpersonated}
          />

          <div className="flex-1 overflow-y-auto scrollbar-none">
            {(hasMarkedAttendance || userRole === 'super admin' || userRole === 'admin') ? renderContent() : (
              <div className="flex flex-col items-center justify-center min-h-[60vh] text-center p-8">
                <div className="w-16 h-16 bg-blue-50 rounded-full flex items-center justify-center mb-4 transition-all animate-pulse">
                  <span className="text-2xl">🕒</span>
                </div>
                <h2 className="text-xl font-semibold text-[#1E293B] mb-2">Attendance Required</h2>
                <p className="text-[#64748B] max-w-md"> Please complete your daily check-in to unlock the business dashboard and operational modules. </p>
              </div>
            )}
          </div>

          <footer className="py-4 px-8 text-center text-xs text-[#94A3B8] border-t border-[#E5E7EB] bg-white">
            &copy; 2026 Veliora • Intelligent Workforce Management • All Rights Reserved.
          </footer>
        </main>

        <Toaster position="top-right" richColors />
      </div>
    </TimerProvider>
  );
};

export default App;
