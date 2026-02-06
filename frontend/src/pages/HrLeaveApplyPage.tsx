import type { ChangeEvent } from 'react';
import { useMemo, useState } from 'react';
import { Button, Paper, Stack, TextField, Typography } from '@mui/material';
import { useMutation, useQuery } from '@tanstack/react-query';

import type { ApiError } from '../api/client';
import { applyLeave, listLeaveTypes } from '../api/hr/leaves';

export function HrLeaveApplyPage() {
  const leaveTypesQuery = useQuery({
    queryKey: ['hr', 'leave-types'],
    queryFn: listLeaveTypes,
  });

  const [employeeId, setEmployeeId] = useState('');
  const [leaveTypeId, setLeaveTypeId] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [reason, setReason] = useState('');

  const employeeIdNum = useMemo(() => Number(employeeId), [employeeId]);
  const leaveTypeIdNum = useMemo(() => Number(leaveTypeId), [leaveTypeId]);

  const canSubmit = useMemo(() => {
    return (
      Number.isFinite(employeeIdNum) &&
      employeeIdNum > 0 &&
      Number.isFinite(leaveTypeIdNum) &&
      leaveTypeIdNum > 0 &&
      Boolean(dateFrom) &&
      Boolean(dateTo)
    );
  }, [employeeIdNum, leaveTypeIdNum, dateFrom, dateTo]);

  const applyMut = useMutation<void, ApiError, void>({
    mutationFn: async () => {
      await applyLeave({
        employee_id: employeeIdNum,
        leave_type_id: leaveTypeIdNum,
        date_from: dateFrom,
        date_to: dateTo,
        reason: reason || null,
      });
    },
    onSuccess: () => {
      setReason('');
    },
  });

  return (
    <Stack spacing={2}>
      <Typography variant="h5">HR • Leave • Apply</Typography>

      <Paper sx={{ p: 2 }}>
        <Stack spacing={2} direction={{ xs: 'column', md: 'row' }} alignItems={{ md: 'end' }}>
          <TextField
            label="Employee ID"
            value={employeeId}
            onChange={(e: ChangeEvent<HTMLInputElement>) => setEmployeeId(e.target.value)}
            type="number"
            size="small"
            sx={{ width: 200 }}
          />
          <TextField
            label="Leave Type ID"
            value={leaveTypeId}
            onChange={(e: ChangeEvent<HTMLInputElement>) => setLeaveTypeId(e.target.value)}
            type="number"
            size="small"
            sx={{ width: 200 }}
            helperText={
              leaveTypesQuery.data?.length
                ? `Available: ${leaveTypesQuery.data.map((x) => `${x.id}:${x.code}`).join(', ')}`
                : 'Tip: ask admin to create leave types'
            }
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
          <TextField
            label="Reason (optional)"
            value={reason}
            onChange={(e: ChangeEvent<HTMLInputElement>) => setReason(e.target.value)}
            size="small"
            sx={{ flex: 1, minWidth: 240 }}
          />
          <Button
            variant="contained"
            disabled={!canSubmit || applyMut.isPending}
            onClick={() => applyMut.mutate()}
          >
            Apply
          </Button>
        </Stack>

        {applyMut.error ? (
          <Typography color="error" variant="body2" sx={{ mt: 1 }}>
            {applyMut.error.message}
          </Typography>
        ) : null}

        {applyMut.isSuccess ? (
          <Typography variant="body2" sx={{ mt: 1 }}>
            Applied successfully.
          </Typography>
        ) : null}
      </Paper>
    </Stack>
  );
}
