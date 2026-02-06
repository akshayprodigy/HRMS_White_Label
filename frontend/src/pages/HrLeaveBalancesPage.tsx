import type { ChangeEvent } from 'react';
import { useMemo, useState } from 'react';
import {
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
import { useQuery } from '@tanstack/react-query';

import { listLeaveBalances } from '../api/hr/leaves';

export function HrLeaveBalancesPage() {
  const [employeeId, setEmployeeId] = useState('');
  const employeeIdNum = useMemo(() => Number(employeeId), [employeeId]);

  const balancesQuery = useQuery({
    queryKey: ['hr', 'leave-balances', employeeIdNum],
    queryFn: () => listLeaveBalances(employeeIdNum),
    enabled: Number.isFinite(employeeIdNum) && employeeIdNum > 0,
  });

  return (
    <Stack spacing={2}>
      <Typography variant="h5">HR • Leave • Balances</Typography>

      <Paper sx={{ p: 2 }}>
        <Stack spacing={2} direction={{ xs: 'column', md: 'row' }} alignItems={{ md: 'end' }}>
          <TextField
            label="Employee ID"
            value={employeeId}
            onChange={(e: ChangeEvent<HTMLInputElement>) => setEmployeeId(e.target.value)}
            type="number"
            size="small"
            sx={{ width: 220 }}
          />
          <Button variant="outlined" disabled>
            Auto refresh
          </Button>
        </Stack>
      </Paper>

      <Paper sx={{ p: 2 }}>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>ID</TableCell>
              <TableCell>Leave Type</TableCell>
              <TableCell>Balance (days)</TableCell>
              <TableCell>Updated</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {(balancesQuery.data ?? []).map((b) => (
              <TableRow key={b.id}>
                <TableCell>{b.id}</TableCell>
                <TableCell>{b.leave_type_id}</TableCell>
                <TableCell>{b.balance_days}</TableCell>
                <TableCell>{b.updated_at}</TableCell>
              </TableRow>
            ))}
            {balancesQuery.isLoading ? (
              <TableRow>
                <TableCell colSpan={4}>Loading…</TableCell>
              </TableRow>
            ) : null}
            {balancesQuery.isError ? (
              <TableRow>
                <TableCell colSpan={4}>Failed to load balances.</TableCell>
              </TableRow>
            ) : null}
          </TableBody>
        </Table>
      </Paper>
    </Stack>
  );
}
