import type { ChangeEvent } from 'react';
import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Box,
  Button,
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

import type { ApiError } from '../api/client';
import type { Employee } from '../api/hr/employees';
import { createEmployee, listEmployees } from '../api/hr/employees';

export function HrEmployeesPage() {
  const navigate = useNavigate();
  const qc = useQueryClient();

  const employeesQuery = useQuery({
    queryKey: ['hr', 'employees'],
    queryFn: listEmployees,
  });

  const [employeeCode, setEmployeeCode] = useState('');
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [employmentType, setEmploymentType] = useState('full_time');
  const [employmentStatus, setEmploymentStatus] = useState('active');
  const [joiningDate, setJoiningDate] = useState('');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');

  const canCreate = useMemo(() => {
    return Boolean(firstName && employmentType && employmentStatus && joiningDate);
  }, [firstName, employmentType, employmentStatus, joiningDate]);

  const createMut = useMutation<Employee, ApiError, void>({
    mutationFn: () =>
      createEmployee({
        employee_code: employeeCode || null,
        first_name: firstName,
        last_name: lastName || null,
        email: email || null,
        phone: phone || null,
        employment_type: employmentType,
        employment_status: employmentStatus,
        joining_date: joiningDate,
      }),
    onSuccess: async () => {
      setEmployeeCode('');
      setFirstName('');
      setLastName('');
      setEmail('');
      setPhone('');
      setJoiningDate('');
      await qc.invalidateQueries({ queryKey: ['hr', 'employees'] });
    },
  });

  const errorText = createMut.error?.message;

  return (
    <Stack spacing={2}>
      <Typography variant="h5">HR • Employees</Typography>

      <Paper sx={{ p: 2 }}>
        <Stack spacing={2} direction={{ xs: 'column', md: 'row' }} alignItems={{ md: 'end' }}>
          <TextField
            label="Employee Code"
            value={employeeCode}
            onChange={(e: ChangeEvent<HTMLInputElement>) => setEmployeeCode(e.target.value)}
            size="small"
            sx={{ width: 200 }}
          />
          <TextField
            label="First Name"
            value={firstName}
            onChange={(e: ChangeEvent<HTMLInputElement>) => setFirstName(e.target.value)}
            size="small"
            sx={{ width: 220 }}
          />
          <TextField
            label="Last Name"
            value={lastName}
            onChange={(e: ChangeEvent<HTMLInputElement>) => setLastName(e.target.value)}
            size="small"
            sx={{ width: 220 }}
          />
          <TextField
            label="Employment Type"
            value={employmentType}
            onChange={(e: ChangeEvent<HTMLInputElement>) => setEmploymentType(e.target.value)}
            size="small"
            sx={{ width: 180 }}
          />
          <TextField
            label="Status"
            value={employmentStatus}
            onChange={(e: ChangeEvent<HTMLInputElement>) => setEmploymentStatus(e.target.value)}
            size="small"
            sx={{ width: 160 }}
          />
          <TextField
            label="Joining Date"
            value={joiningDate}
            onChange={(e: ChangeEvent<HTMLInputElement>) => setJoiningDate(e.target.value)}
            type="date"
            size="small"
            InputLabelProps={{ shrink: true }}
            sx={{ width: 180 }}
          />
          <TextField
            label="Email"
            value={email}
            onChange={(e: ChangeEvent<HTMLInputElement>) => setEmail(e.target.value)}
            size="small"
            sx={{ width: 240 }}
          />
          <TextField
            label="Phone"
            value={phone}
            onChange={(e: ChangeEvent<HTMLInputElement>) => setPhone(e.target.value)}
            size="small"
            sx={{ width: 180 }}
          />
          <Button
            variant="contained"
            disabled={!canCreate || createMut.isPending}
            onClick={() => createMut.mutate()}
          >
            Create
          </Button>
        </Stack>

        {errorText ? (
          <Typography variant="body2" color="error" sx={{ mt: 1 }}>
            {errorText}
          </Typography>
        ) : null}
      </Paper>

      <Paper sx={{ p: 2 }}>
        <Box sx={{ overflowX: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>ID</TableCell>
                <TableCell>Code</TableCell>
                <TableCell>Name</TableCell>
                <TableCell>Status</TableCell>
                <TableCell>Joining</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {(employeesQuery.data ?? []).map((e: Employee) => (
                <TableRow
                  key={e.id}
                  hover
                  sx={{ cursor: 'pointer' }}
                  onClick={() => navigate(`/hr/employees/${e.id}`)}
                >
                  <TableCell>{e.id}</TableCell>
                  <TableCell>{e.employee_code ?? '—'}</TableCell>
                  <TableCell>
                    {e.first_name}
                    {e.last_name ? ` ${e.last_name}` : ''}
                  </TableCell>
                  <TableCell>{e.employment_status}</TableCell>
                  <TableCell>{e.joining_date}</TableCell>
                </TableRow>
              ))}
              {employeesQuery.isLoading ? (
                <TableRow>
                  <TableCell colSpan={5}>Loading…</TableCell>
                </TableRow>
              ) : null}
            </TableBody>
          </Table>
        </Box>
      </Paper>
    </Stack>
  );
}
