import type { ChangeEvent } from 'react';
import { useMemo, useState } from 'react';
import {
  Box,
  Button,
  Divider,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Bar,
  BarChart,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import type { ApiError } from '../api/client';
import { listProjects } from '../api/core/projects';
import { createAttendanceEntry } from '../api/hr/attendance';
import { listEmployees } from '../api/hr/employees';
import { listItems } from '../api/inventory/items';
import { createProjectDirectExpense, createProjectRevenue } from '../api/projects/finance';
import type { ProjectProfitability } from '../api/projects/profitability';
import { getProjectProfitability } from '../api/projects/profitability';
import { useAuth } from '../auth/AuthContext';

function helperFromRows(rows: Array<{ id: number; code?: string; sku?: string }>, label: string) {
  if (!rows.length) return `Tip: create ${label} first`;
  const parts = rows.slice(0, 8).map((r) => `${r.id}:${r.code ?? r.sku ?? ''}`.replace(/:$/, ''));
  return `Available: ${parts.join(', ')}${rows.length > 8 ? '…' : ''}`;
}

function fmtMoney(n: number) {
  const x = Number.isFinite(n) ? n : 0;
  return x.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

const PIE_COLORS = ['#1976d2', '#2e7d32', '#ed6c02', '#9c27b0', '#d32f2f'];

export function ProjectsProfitabilityPage() {
  const auth = useAuth();
  const qc = useQueryClient();

  const projectsQuery = useQuery({ queryKey: ['core', 'projects'], queryFn: listProjects });
  const employeesQuery = useQuery({ queryKey: ['hr', 'employees'], queryFn: listEmployees });
  const itemsQuery = useQuery({ queryKey: ['inventory', 'items'], queryFn: listItems });

  const [projectId, setProjectId] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');

  const projectIdNum = useMemo(() => {
    const n = Number(projectId);
    return Number.isFinite(n) && n > 0 ? n : undefined;
  }, [projectId]);

  const canRun = useMemo(
    () => Boolean(projectIdNum) && Boolean(dateFrom) && Boolean(dateTo),
    [projectIdNum, dateFrom, dateTo],
  );

  const projectHelp = useMemo(() => {
    const rows = (projectsQuery.data ?? []).map((p) => ({ id: p.id, code: p.code }));
    return helperFromRows(rows, 'projects');
  }, [projectsQuery.data]);

  const employeeById = useMemo(() => {
    const out = new Map<number, string>();
    for (const e of employeesQuery.data ?? []) {
      const name = [e.first_name, e.last_name].filter(Boolean).join(' ');
      out.set(e.id, e.employee_code ? `${name} (${e.employee_code})` : name);
    }
    return out;
  }, [employeesQuery.data]);

  const itemById = useMemo(() => {
    const out = new Map<number, string>();
    for (const it of itemsQuery.data ?? []) out.set(it.id, it.sku);
    return out;
  }, [itemsQuery.data]);

  const runMut = useMutation<ProjectProfitability, ApiError, void>({
    mutationFn: async () => {
      if (!projectIdNum) throw new Error('Project ID required');
      return getProjectProfitability(projectIdNum, { date_from: dateFrom, date_to: dateTo });
    },
  });

  // Quick posting forms (optional)
  const canPostAttendance = auth.hasPermission('hr.attendance.write');
  const canPostFinance = auth.hasPermission('projects.finance.write');

  const [attEmployeeId, setAttEmployeeId] = useState('');
  const [attWorkDate, setAttWorkDate] = useState('');
  const [attHours, setAttHours] = useState('');
  const [attRate, setAttRate] = useState('');

  const postAttendanceMut = useMutation<unknown, ApiError, void>({
    mutationFn: async () => {
      if (!projectIdNum) throw new Error('Project ID required');
      const emp = Number(attEmployeeId);
      const hours = Number(attHours);
      const rate = Number(attRate);
      if (!Number.isFinite(emp) || emp <= 0) throw new Error('Employee ID required');
      if (!attWorkDate) throw new Error('Work date required');
      if (!Number.isFinite(hours) || hours <= 0) throw new Error('Hours must be > 0');
      if (!Number.isFinite(rate) || rate < 0) throw new Error('Hourly rate must be >= 0');

      await createAttendanceEntry({
        employee_id: emp,
        project_id: projectIdNum,
        work_date: attWorkDate,
        hours,
        hourly_rate: rate,
      });
    },
    onSuccess: async () => {
      setAttHours('');
      setAttRate('');
      await runMut.mutateAsync();
    },
  });

  const [expDate, setExpDate] = useState('');
  const [expCategory, setExpCategory] = useState('');
  const [expAmount, setExpAmount] = useState('');
  const postExpenseMut = useMutation<unknown, ApiError, void>({
    mutationFn: async () => {
      if (!projectIdNum) throw new Error('Project ID required');
      const amount = Number(expAmount);
      if (!expDate) throw new Error('Expense date required');
      if (!expCategory.trim()) throw new Error('Category required');
      if (!Number.isFinite(amount) || amount <= 0) throw new Error('Amount must be > 0');
      await createProjectDirectExpense(projectIdNum, {
        expense_date: expDate,
        category: expCategory.trim(),
        amount,
      });
    },
    onSuccess: async () => {
      setExpAmount('');
      await runMut.mutateAsync();
      qc.invalidateQueries({ queryKey: ['projects', projectIdNum, 'profitability'] });
    },
  });

  const [revDate, setRevDate] = useState('');
  const [revCategory, setRevCategory] = useState('');
  const [revAmount, setRevAmount] = useState('');
  const postRevenueMut = useMutation<unknown, ApiError, void>({
    mutationFn: async () => {
      if (!projectIdNum) throw new Error('Project ID required');
      const amount = Number(revAmount);
      if (!revDate) throw new Error('Revenue date required');
      if (!revCategory.trim()) throw new Error('Category required');
      if (!Number.isFinite(amount) || amount <= 0) throw new Error('Amount must be > 0');
      await createProjectRevenue(projectIdNum, {
        revenue_date: revDate,
        category: revCategory.trim(),
        amount,
      });
    },
    onSuccess: async () => {
      setRevAmount('');
      await runMut.mutateAsync();
      qc.invalidateQueries({ queryKey: ['projects', projectIdNum, 'profitability'] });
    },
  });

  const data = runMut.data;

  const kpis = useMemo(() => {
    if (!data) return null;
    return [
      { label: 'Revenue', value: data.revenue_total },
      { label: 'Total Cost', value: data.total_cost },
      { label: 'Gross Profit', value: data.gross_profit },
      { label: 'Gross Margin %', value: data.gross_margin_percent },
    ];
  }, [data]);

  const barData = useMemo(() => {
    if (!data) return [];
    return [
      {
        name: 'Totals',
        Revenue: data.revenue_total,
        'Total Cost': data.total_cost,
        'Gross Profit': data.gross_profit,
      },
    ];
  }, [data]);

  const pieData = useMemo(() => {
    if (!data) return [];
    return [
      { name: 'Labor', value: data.labor_cost_total },
      { name: 'Materials', value: data.materials_cost_total },
      { name: 'Direct Expenses', value: data.direct_expenses_total },
    ].filter((x) => x.value > 0);
  }, [data]);

  const employeesHelp = useMemo(() => {
    const rows = (employeesQuery.data ?? []).map((e) => ({
      id: e.id,
      code: e.employee_code ?? '',
    }));
    return helperFromRows(rows, 'employees');
  }, [employeesQuery.data]);

  return (
    <Stack spacing={2}>
      <Typography variant="h5">Projects • Profitability</Typography>

      <Paper sx={{ p: 2 }}>
        <Stack spacing={2} direction={{ xs: 'column', md: 'row' }} alignItems={{ md: 'end' }}>
          <TextField
            label="Project ID"
            value={projectId}
            onChange={(e: ChangeEvent<HTMLInputElement>) => setProjectId(e.target.value)}
            type="number"
            size="small"
            sx={{ width: 200 }}
            helperText={projectHelp}
          />
          <TextField
            label="From"
            value={dateFrom}
            onChange={(e: ChangeEvent<HTMLInputElement>) => setDateFrom(e.target.value)}
            type="date"
            size="small"
            InputLabelProps={{ shrink: true }}
            sx={{ width: 170 }}
          />
          <TextField
            label="To"
            value={dateTo}
            onChange={(e: ChangeEvent<HTMLInputElement>) => setDateTo(e.target.value)}
            type="date"
            size="small"
            InputLabelProps={{ shrink: true }}
            sx={{ width: 170 }}
          />
          <Button
            variant="contained"
            disabled={!canRun || runMut.isPending}
            onClick={() => runMut.mutate()}
          >
            Run
          </Button>
        </Stack>

        {runMut.error ? (
          <Typography color="error" variant="body2" sx={{ mt: 1 }}>
            {runMut.error.message}
          </Typography>
        ) : null}
      </Paper>

      {kpis ? (
        <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
          {kpis.map((k) => (
            <Paper key={k.label} sx={{ p: 2, flex: 1 }}>
              <Typography variant="caption" sx={{ opacity: 0.8 }}>
                {k.label}
              </Typography>
              <Typography variant="h6">
                {k.label.endsWith('%') ? `${fmtMoney(k.value)}%` : fmtMoney(k.value)}
              </Typography>
            </Paper>
          ))}
        </Stack>
      ) : null}

      {data ? (
        <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
          <Paper sx={{ p: 2, flex: 1, minHeight: 320 }}>
            <Typography variant="subtitle1" sx={{ mb: 1 }}>
              Revenue vs Cost
            </Typography>
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={barData} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
                <XAxis dataKey="name" />
                <YAxis />
                <Tooltip formatter={(v) => fmtMoney(Number(v))} />
                <Legend />
                <Bar dataKey="Revenue" fill="#1976d2" />
                <Bar dataKey="Total Cost" fill="#ed6c02" />
                <Bar dataKey="Gross Profit" fill="#2e7d32" />
              </BarChart>
            </ResponsiveContainer>
          </Paper>

          <Paper sx={{ p: 2, flex: 1, minHeight: 320 }}>
            <Typography variant="subtitle1" sx={{ mb: 1 }}>
              Cost Composition
            </Typography>
            <ResponsiveContainer width="100%" height={260}>
              <PieChart>
                <Tooltip formatter={(v) => fmtMoney(Number(v))} />
                <Legend />
                <Pie data={pieData} dataKey="value" nameKey="name" outerRadius={90}>
                  {pieData.map((_, idx) => (
                    <Cell key={idx} fill={PIE_COLORS[idx % PIE_COLORS.length]} />
                  ))}
                </Pie>
              </PieChart>
            </ResponsiveContainer>
          </Paper>
        </Stack>
      ) : null}

      {data ? (
        <Paper sx={{ p: 2 }}>
          <Typography variant="subtitle1">Breakdown</Typography>
          <Typography variant="body2" sx={{ opacity: 0.8 }}>
            Window: {data.date_from} → {data.date_to}
          </Typography>
          <Divider sx={{ my: 2 }} />

          <Stack spacing={2} direction={{ xs: 'column', md: 'row' }}>
            <Box sx={{ flex: 1, overflowX: 'auto' }}>
              <Typography variant="subtitle2" sx={{ mb: 1 }}>
                Labor by Employee
              </Typography>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Employee</TableCell>
                    <TableCell align="right">Hours</TableCell>
                    <TableCell align="right">Cost</TableCell>
                    <TableCell align="right">Avg Rate</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {data.labor_by_employee.map((r) => (
                    <TableRow key={r.employee_id} hover>
                      <TableCell>
                        {employeeById.get(r.employee_id)
                          ? `${r.employee_id} (${employeeById.get(r.employee_id)})`
                          : String(r.employee_id)}
                      </TableCell>
                      <TableCell align="right">{fmtMoney(r.hours)}</TableCell>
                      <TableCell align="right">{fmtMoney(r.cost)}</TableCell>
                      <TableCell align="right">{fmtMoney(r.avg_rate)}</TableCell>
                    </TableRow>
                  ))}
                  {!data.labor_by_employee.length ? (
                    <TableRow>
                      <TableCell colSpan={4}>No labor entries.</TableCell>
                    </TableRow>
                  ) : null}
                </TableBody>
              </Table>
            </Box>

            <Box sx={{ flex: 1, overflowX: 'auto' }}>
              <Typography variant="subtitle2" sx={{ mb: 1 }}>
                Materials by Item
              </Typography>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Item</TableCell>
                    <TableCell align="right">Qty Issued</TableCell>
                    <TableCell align="right">Cost</TableCell>
                    <TableCell align="right">Avg Unit Cost</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {data.materials_by_item.map((r) => {
                    const sku = itemById.get(r.item_id);
                    const itemText = sku ? `${r.item_id} (${sku})` : String(r.item_id);
                    return (
                      <TableRow key={r.item_id} hover>
                        <TableCell>{itemText}</TableCell>
                        <TableCell align="right">{fmtMoney(r.qty_issued)}</TableCell>
                        <TableCell align="right">{fmtMoney(r.cost)}</TableCell>
                        <TableCell align="right">{fmtMoney(r.avg_unit_cost)}</TableCell>
                      </TableRow>
                    );
                  })}
                  {!data.materials_by_item.length ? (
                    <TableRow>
                      <TableCell colSpan={4}>No material issues.</TableCell>
                    </TableRow>
                  ) : null}
                </TableBody>
              </Table>
            </Box>
          </Stack>

          <Divider sx={{ my: 2 }} />

          <Stack spacing={2} direction={{ xs: 'column', md: 'row' }}>
            <Box sx={{ flex: 1, overflowX: 'auto' }}>
              <Typography variant="subtitle2" sx={{ mb: 1 }}>
                Revenue by Category
              </Typography>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Category</TableCell>
                    <TableCell align="right">Amount</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {data.revenue_by_category.map((r) => (
                    <TableRow key={r.category} hover>
                      <TableCell>{r.category}</TableCell>
                      <TableCell align="right">{fmtMoney(r.amount)}</TableCell>
                    </TableRow>
                  ))}
                  {!data.revenue_by_category.length ? (
                    <TableRow>
                      <TableCell colSpan={2}>No revenue postings.</TableCell>
                    </TableRow>
                  ) : null}
                </TableBody>
              </Table>
            </Box>

            <Box sx={{ flex: 1, overflowX: 'auto' }}>
              <Typography variant="subtitle2" sx={{ mb: 1 }}>
                Direct Expenses by Category
              </Typography>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Category</TableCell>
                    <TableCell align="right">Amount</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {data.direct_expenses_by_category.map((r) => (
                    <TableRow key={r.category} hover>
                      <TableCell>{r.category}</TableCell>
                      <TableCell align="right">{fmtMoney(r.amount)}</TableCell>
                    </TableRow>
                  ))}
                  {!data.direct_expenses_by_category.length ? (
                    <TableRow>
                      <TableCell colSpan={2}>No expense postings.</TableCell>
                    </TableRow>
                  ) : null}
                </TableBody>
              </Table>
            </Box>
          </Stack>
        </Paper>
      ) : null}

      {canPostAttendance || canPostFinance ? (
        <Paper sx={{ p: 2 }}>
          <Typography variant="subtitle1" sx={{ mb: 1 }}>
            Quick Post (optional)
          </Typography>
          <Typography variant="body2" sx={{ opacity: 0.8, mb: 2 }}>
            Posts manual entries and refreshes profitability.
          </Typography>

          <Stack spacing={2}>
            {canPostAttendance ? (
              <Paper variant="outlined" sx={{ p: 2 }}>
                <Typography variant="subtitle2" sx={{ mb: 1 }}>
                  Attendance
                </Typography>
                <Stack
                  direction={{ xs: 'column', md: 'row' }}
                  spacing={2}
                  alignItems={{ md: 'end' }}
                >
                  <TextField
                    label="Employee ID"
                    value={attEmployeeId}
                    onChange={(e: ChangeEvent<HTMLInputElement>) =>
                      setAttEmployeeId(e.target.value)
                    }
                    type="number"
                    size="small"
                    sx={{ width: 200 }}
                    helperText={employeesHelp}
                  />
                  <TextField
                    label="Work date"
                    value={attWorkDate}
                    onChange={(e: ChangeEvent<HTMLInputElement>) => setAttWorkDate(e.target.value)}
                    type="date"
                    size="small"
                    InputLabelProps={{ shrink: true }}
                    sx={{ width: 170 }}
                  />
                  <TextField
                    label="Hours"
                    value={attHours}
                    onChange={(e: ChangeEvent<HTMLInputElement>) => setAttHours(e.target.value)}
                    type="number"
                    size="small"
                    sx={{ width: 140 }}
                  />
                  <TextField
                    label="Hourly rate"
                    value={attRate}
                    onChange={(e: ChangeEvent<HTMLInputElement>) => setAttRate(e.target.value)}
                    type="number"
                    size="small"
                    sx={{ width: 160 }}
                  />
                  <Button
                    variant="contained"
                    disabled={!canRun || postAttendanceMut.isPending}
                    onClick={() => postAttendanceMut.mutate()}
                  >
                    Post
                  </Button>
                </Stack>
                {postAttendanceMut.error ? (
                  <Typography color="error" variant="body2" sx={{ mt: 1 }}>
                    {postAttendanceMut.error.message}
                  </Typography>
                ) : null}
              </Paper>
            ) : null}

            {canPostFinance ? (
              <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
                <Paper variant="outlined" sx={{ p: 2, flex: 1 }}>
                  <Typography variant="subtitle2" sx={{ mb: 1 }}>
                    Direct Expense
                  </Typography>
                  <Stack
                    direction={{ xs: 'column', md: 'row' }}
                    spacing={2}
                    alignItems={{ md: 'end' }}
                  >
                    <TextField
                      label="Date"
                      value={expDate}
                      onChange={(e: ChangeEvent<HTMLInputElement>) => setExpDate(e.target.value)}
                      type="date"
                      size="small"
                      InputLabelProps={{ shrink: true }}
                      sx={{ width: 170 }}
                    />
                    <TextField
                      label="Category"
                      value={expCategory}
                      onChange={(e: ChangeEvent<HTMLInputElement>) =>
                        setExpCategory(e.target.value)
                      }
                      size="small"
                      sx={{ width: 220 }}
                    />
                    <TextField
                      label="Amount"
                      value={expAmount}
                      onChange={(e: ChangeEvent<HTMLInputElement>) => setExpAmount(e.target.value)}
                      type="number"
                      size="small"
                      sx={{ width: 160 }}
                    />
                    <Button
                      variant="contained"
                      disabled={!canRun || postExpenseMut.isPending}
                      onClick={() => postExpenseMut.mutate()}
                    >
                      Post
                    </Button>
                  </Stack>
                  {postExpenseMut.error ? (
                    <Typography color="error" variant="body2" sx={{ mt: 1 }}>
                      {postExpenseMut.error.message}
                    </Typography>
                  ) : null}
                </Paper>

                <Paper variant="outlined" sx={{ p: 2, flex: 1 }}>
                  <Typography variant="subtitle2" sx={{ mb: 1 }}>
                    Revenue
                  </Typography>
                  <Stack
                    direction={{ xs: 'column', md: 'row' }}
                    spacing={2}
                    alignItems={{ md: 'end' }}
                  >
                    <TextField
                      label="Date"
                      value={revDate}
                      onChange={(e: ChangeEvent<HTMLInputElement>) => setRevDate(e.target.value)}
                      type="date"
                      size="small"
                      InputLabelProps={{ shrink: true }}
                      sx={{ width: 170 }}
                    />
                    <TextField
                      label="Category"
                      value={revCategory}
                      onChange={(e: ChangeEvent<HTMLInputElement>) =>
                        setRevCategory(e.target.value)
                      }
                      size="small"
                      sx={{ width: 220 }}
                    />
                    <TextField
                      label="Amount"
                      value={revAmount}
                      onChange={(e: ChangeEvent<HTMLInputElement>) => setRevAmount(e.target.value)}
                      type="number"
                      size="small"
                      sx={{ width: 160 }}
                    />
                    <Button
                      variant="contained"
                      disabled={!canRun || postRevenueMut.isPending}
                      onClick={() => postRevenueMut.mutate()}
                    >
                      Post
                    </Button>
                  </Stack>
                  {postRevenueMut.error ? (
                    <Typography color="error" variant="body2" sx={{ mt: 1 }}>
                      {postRevenueMut.error.message}
                    </Typography>
                  ) : null}
                </Paper>
              </Stack>
            ) : null}
          </Stack>
        </Paper>
      ) : null}
    </Stack>
  );
}
