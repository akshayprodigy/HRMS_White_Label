import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';

import { AppShell } from './components/AppShell';
import { ProtectedRoute } from './components/ProtectedRoute';
import { AdminUsersPage } from './pages/AdminUsersPage';
import { AuditLogsPage } from './pages/AuditLogsPage';
import { CostCentersPage } from './pages/CostCentersPage';
import { DashboardPage } from './pages/DashboardPage';
import { HrEmployeeDetailPage } from './pages/HrEmployeeDetailPage';
import { HrEmployeesPage } from './pages/HrEmployeesPage';
import { HrLeaveApprovalsPage } from './pages/HrLeaveApprovalsPage';
import { HrLeaveApplyPage } from './pages/HrLeaveApplyPage';
import { HrLeaveBalancesPage } from './pages/HrLeaveBalancesPage';
import { InventoryGrnsPage } from './pages/InventoryGrnsPage';
import { InventoryIssuesPage } from './pages/InventoryIssuesPage';
import { InventoryItemsPage } from './pages/InventoryItemsPage';
import { InventoryProjectConsumptionPage } from './pages/InventoryProjectConsumptionPage';
import { InventoryUomsPage } from './pages/InventoryUomsPage';
import { InventoryWarehousesPage } from './pages/InventoryWarehousesPage';
import { LoginPage } from './pages/LoginPage';
import { ProjectsPage } from './pages/ProjectsPage';
import { ProjectsDprEntryPage } from './pages/ProjectsDprEntryPage';
import { ProjectsProfitabilityPage } from './pages/ProjectsProfitabilityPage';
import { SitesPage } from './pages/SitesPage';

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />

        <Route
          path="/"
          element={
            <ProtectedRoute>
              <AppShell />
            </ProtectedRoute>
          }
        >
          <Route index element={<DashboardPage />} />
          <Route path="core/sites" element={<SitesPage />} />
          <Route path="core/projects" element={<ProjectsPage />} />
          <Route path="projects/dprs/entry" element={<ProjectsDprEntryPage />} />
          <Route path="projects/profitability" element={<ProjectsProfitabilityPage />} />
          <Route path="core/cost-centers" element={<CostCentersPage />} />
          <Route path="hr/employees" element={<HrEmployeesPage />} />
          <Route path="hr/employees/:employeeId" element={<HrEmployeeDetailPage />} />
          <Route path="hr/leave/apply" element={<HrLeaveApplyPage />} />
          <Route path="hr/leave/approvals" element={<HrLeaveApprovalsPage />} />
          <Route path="hr/leave/balances" element={<HrLeaveBalancesPage />} />

          <Route path="inventory/uoms" element={<InventoryUomsPage />} />
          <Route path="inventory/warehouses" element={<InventoryWarehousesPage />} />
          <Route path="inventory/items" element={<InventoryItemsPage />} />
          <Route path="inventory/grns" element={<InventoryGrnsPage />} />
          <Route path="inventory/issues" element={<InventoryIssuesPage />} />
          <Route
            path="inventory/reports/project-consumption"
            element={<InventoryProjectConsumptionPage />}
          />

          <Route path="admin/users" element={<AdminUsersPage />} />
          <Route path="admin/audit-logs" element={<AuditLogsPage />} />
        </Route>

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
