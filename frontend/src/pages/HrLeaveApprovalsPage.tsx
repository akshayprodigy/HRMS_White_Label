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
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import type { ApiError } from '../api/client';
import { approveLeave, listLeaveRequests, rejectLeave } from '../api/hr/leaves';

export function HrLeaveApprovalsPage() {
  const qc = useQueryClient();
  const [comment, setComment] = useState('');

  const pendingQuery = useQuery({
    queryKey: ['hr', 'leave-requests', 'pending'],
    queryFn: () => listLeaveRequests({ status: 'applied' }),
  });

  const approveMut = useMutation<void, ApiError, { requestId: number }>({
    mutationFn: async ({ requestId }) => {
      await approveLeave(requestId, { comment: comment || null });
    },
    onSuccess: async () => {
      setComment('');
      await qc.invalidateQueries({ queryKey: ['hr', 'leave-requests', 'pending'] });
    },
  });

  const rejectMut = useMutation<void, ApiError, { requestId: number }>({
    mutationFn: async ({ requestId }) => {
      await rejectLeave(requestId, { comment: comment || null });
    },
    onSuccess: async () => {
      setComment('');
      await qc.invalidateQueries({ queryKey: ['hr', 'leave-requests', 'pending'] });
    },
  });

  const errorText = approveMut.error?.message || rejectMut.error?.message;

  const rows = useMemo(() => pendingQuery.data ?? [], [pendingQuery.data]);

  return (
    <Stack spacing={2}>
      <Typography variant="h5">HR • Leave • Approvals</Typography>

      <Paper sx={{ p: 2 }}>
        <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} alignItems={{ md: 'end' }}>
          <TextField
            label="Decision comment (optional)"
            value={comment}
            onChange={(e: ChangeEvent<HTMLInputElement>) => setComment(e.target.value)}
            size="small"
            sx={{ flex: 1, minWidth: 260 }}
          />
        </Stack>
        {errorText ? (
          <Typography color="error" variant="body2" sx={{ mt: 1 }}>
            {errorText}
          </Typography>
        ) : null}
      </Paper>

      <Paper sx={{ p: 2 }}>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>ID</TableCell>
              <TableCell>Employee</TableCell>
              <TableCell>Leave Type</TableCell>
              <TableCell>From</TableCell>
              <TableCell>To</TableCell>
              <TableCell>Days</TableCell>
              <TableCell>Status</TableCell>
              <TableCell>Actions</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.map((r) => (
              <TableRow key={r.id}>
                <TableCell>{r.id}</TableCell>
                <TableCell>{r.employee_id}</TableCell>
                <TableCell>{r.leave_type_id}</TableCell>
                <TableCell>{r.date_from}</TableCell>
                <TableCell>{r.date_to}</TableCell>
                <TableCell>{r.days}</TableCell>
                <TableCell>{r.status}</TableCell>
                <TableCell>
                  <Stack direction="row" spacing={1}>
                    <Button
                      size="small"
                      variant="contained"
                      disabled={approveMut.isPending || rejectMut.isPending}
                      onClick={() => approveMut.mutate({ requestId: r.id })}
                    >
                      Approve
                    </Button>
                    <Button
                      size="small"
                      variant="outlined"
                      color="error"
                      disabled={approveMut.isPending || rejectMut.isPending}
                      onClick={() => rejectMut.mutate({ requestId: r.id })}
                    >
                      Reject
                    </Button>
                  </Stack>
                </TableCell>
              </TableRow>
            ))}
            {pendingQuery.isLoading ? (
              <TableRow>
                <TableCell colSpan={8}>Loading…</TableCell>
              </TableRow>
            ) : null}
          </TableBody>
        </Table>
      </Paper>
    </Stack>
  );
}
