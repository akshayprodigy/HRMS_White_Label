import { Outlet, useNavigate } from 'react-router-dom';
import {
  AppBar,
  Box,
  Button,
  Drawer,
  List,
  ListItem,
  ListItemButton,
  ListItemText,
  Toolbar,
  Typography,
} from '@mui/material';

import { useAuth } from '../auth/AuthContext';

const drawerWidth = 260;

export function AppShell() {
  const navigate = useNavigate();
  const auth = useAuth();

  const onLogout = async () => {
    await auth.logout();
    navigate('/login', { replace: true });
  };

  return (
    <Box sx={{ display: 'flex' }}>
      <AppBar position="fixed" sx={{ zIndex: (theme) => theme.zIndex.drawer + 1 }}>
        <Toolbar>
          <Typography variant="h6" sx={{ flexGrow: 1 }}>
            United Exploration ERP
          </Typography>
          {auth.userEmail ? (
            <Typography variant="body2" sx={{ mr: 2, opacity: 0.9 }}>
              {auth.userEmail}
            </Typography>
          ) : null}
          <Button color="inherit" onClick={onLogout}>
            Logout
          </Button>
        </Toolbar>
      </AppBar>

      <Drawer
        variant="permanent"
        sx={{
          width: drawerWidth,
          flexShrink: 0,
          [`& .MuiDrawer-paper`]: { width: drawerWidth, boxSizing: 'border-box' },
        }}
      >
        <Toolbar />
        <List>
          <ListItem disablePadding>
            <ListItemButton onClick={() => navigate('/')}>
              <ListItemText primary="Dashboard" />
            </ListItemButton>
          </ListItem>

          {auth.hasPermission('core.sites.read') ? (
            <ListItem disablePadding>
              <ListItemButton onClick={() => navigate('/core/sites')}>
                <ListItemText primary="Core • Sites" />
              </ListItemButton>
            </ListItem>
          ) : null}

          {auth.hasPermission('core.projects.read') ? (
            <ListItem disablePadding>
              <ListItemButton onClick={() => navigate('/core/projects')}>
                <ListItemText primary="Core • Projects" />
              </ListItemButton>
            </ListItem>
          ) : null}

          {auth.hasPermission('projects.dprs.write') ? (
            <ListItem disablePadding>
              <ListItemButton onClick={() => navigate('/projects/dprs/entry')}>
                <ListItemText primary="Projects • DPR • Entry" />
              </ListItemButton>
            </ListItem>
          ) : null}

          {auth.hasPermission('projects.profitability.read') ? (
            <ListItem disablePadding>
              <ListItemButton onClick={() => navigate('/projects/profitability')}>
                <ListItemText primary="Projects • Profitability" />
              </ListItemButton>
            </ListItem>
          ) : null}

          {auth.hasPermission('core.cost_centers.read') ? (
            <ListItem disablePadding>
              <ListItemButton onClick={() => navigate('/core/cost-centers')}>
                <ListItemText primary="Core • Cost Centers" />
              </ListItemButton>
            </ListItem>
          ) : null}

          {auth.hasPermission('hr.employees.read') ? (
            <ListItem disablePadding>
              <ListItemButton onClick={() => navigate('/hr/employees')}>
                <ListItemText primary="HR • Employees" />
              </ListItemButton>
            </ListItem>
          ) : null}

          {auth.hasPermission('hr.leave_requests.apply') ? (
            <ListItem disablePadding>
              <ListItemButton onClick={() => navigate('/hr/leave/apply')}>
                <ListItemText primary="HR • Leave • Apply" />
              </ListItemButton>
            </ListItem>
          ) : null}

          {auth.hasPermission('hr.leave_requests.approve') ? (
            <ListItem disablePadding>
              <ListItemButton onClick={() => navigate('/hr/leave/approvals')}>
                <ListItemText primary="HR • Leave • Approvals" />
              </ListItemButton>
            </ListItem>
          ) : null}

          {auth.hasPermission('hr.leave_balances.read') ? (
            <ListItem disablePadding>
              <ListItemButton onClick={() => navigate('/hr/leave/balances')}>
                <ListItemText primary="HR • Leave • Balances" />
              </ListItemButton>
            </ListItem>
          ) : null}

          {auth.hasPermission('inventory.uoms.read') ? (
            <ListItem disablePadding>
              <ListItemButton onClick={() => navigate('/inventory/uoms')}>
                <ListItemText primary="Inventory • UOMs" />
              </ListItemButton>
            </ListItem>
          ) : null}

          {auth.hasPermission('inventory.warehouses.read') ? (
            <ListItem disablePadding>
              <ListItemButton onClick={() => navigate('/inventory/warehouses')}>
                <ListItemText primary="Inventory • Warehouses" />
              </ListItemButton>
            </ListItem>
          ) : null}

          {auth.hasPermission('inventory.items.read') ? (
            <ListItem disablePadding>
              <ListItemButton onClick={() => navigate('/inventory/items')}>
                <ListItemText primary="Inventory • Items" />
              </ListItemButton>
            </ListItem>
          ) : null}

          {auth.hasPermission('inventory.grns.read') ? (
            <ListItem disablePadding>
              <ListItemButton onClick={() => navigate('/inventory/grns')}>
                <ListItemText primary="Inventory • GRNs" />
              </ListItemButton>
            </ListItem>
          ) : null}

          {auth.hasPermission('inventory.issues.read') ? (
            <ListItem disablePadding>
              <ListItemButton onClick={() => navigate('/inventory/issues')}>
                <ListItemText primary="Inventory • Issues" />
              </ListItemButton>
            </ListItem>
          ) : null}

          {auth.hasPermission('inventory.reports.project_consumption.read') ? (
            <ListItem disablePadding>
              <ListItemButton onClick={() => navigate('/inventory/reports/project-consumption')}>
                <ListItemText primary="Inventory • Reports • Consumption" />
              </ListItemButton>
            </ListItem>
          ) : null}

          {auth.hasPermission('admin.users.read') ? (
            <ListItem disablePadding>
              <ListItemButton onClick={() => navigate('/admin/users')}>
                <ListItemText primary="Admin • Users" />
              </ListItemButton>
            </ListItem>
          ) : null}

          {auth.hasPermission('admin.audit_logs.read') ? (
            <ListItem disablePadding>
              <ListItemButton onClick={() => navigate('/admin/audit-logs')}>
                <ListItemText primary="Admin • Audit Logs" />
              </ListItemButton>
            </ListItem>
          ) : null}
        </List>
      </Drawer>

      <Box component="main" sx={{ flexGrow: 1, p: 3 }}>
        <Toolbar />
        <Outlet />
      </Box>
    </Box>
  );
}
