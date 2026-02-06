import type { ChangeEvent } from 'react';
import { useMemo, useState } from 'react';
import {
  Box,
  Button,
  Dialog,
  DialogContent,
  DialogTitle,
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

import type { AuditLog, AuditLogFilters } from '../api/admin/auditLogs';
import { queryAuditLogs } from '../api/admin/auditLogs';

export function AuditLogsPage() {
  const [filters, setFilters] = useState({
    entity_type: '',
    entity_id: '',
    action: '',
    actor_user_id: '',
    request_id: '',
    created_from: '',
    created_to: '',
  });
  const [applied, setApplied] = useState<AuditLogFilters>({});
  const [selected, setSelected] = useState<AuditLog | null>(null);

  const appliedKey = useMemo(() => JSON.stringify(applied), [applied]);

  const logsQuery = useQuery({
    queryKey: ['admin', 'audit-logs', appliedKey],
    queryFn: () => queryAuditLogs(applied),
  });

  const onApply = () => {
    const actorId = filters.actor_user_id ? Number(filters.actor_user_id) : undefined;
    setApplied({
      entity_type: filters.entity_type || undefined,
      entity_id: filters.entity_id || undefined,
      action: filters.action || undefined,
      actor_user_id: Number.isFinite(actorId ?? NaN) ? actorId : undefined,
      request_id: filters.request_id || undefined,
      created_from: filters.created_from || undefined,
      created_to: filters.created_to || undefined,
      limit: 100,
      offset: 0,
    });
  };

  const onReset = () => {
    setFilters({
      entity_type: '',
      entity_id: '',
      action: '',
      actor_user_id: '',
      request_id: '',
      created_from: '',
      created_to: '',
    });
    setApplied({});
  };

  const onChange = (key: keyof typeof filters) => (e: ChangeEvent<HTMLInputElement>) => {
    setFilters((prev) => ({ ...prev, [key]: e.target.value }));
  };

  return (
    <Stack spacing={2}>
      <Typography variant="h5">Admin • Audit Logs</Typography>

      <Paper sx={{ p: 2 }}>
        <Stack spacing={2} direction={{ xs: 'column', md: 'row' }} flexWrap="wrap">
          <TextField
            label="Entity Type"
            value={filters.entity_type}
            onChange={onChange('entity_type')}
            size="small"
          />
          <TextField
            label="Entity ID"
            value={filters.entity_id}
            onChange={onChange('entity_id')}
            size="small"
          />
          <TextField
            label="Action"
            value={filters.action}
            onChange={onChange('action')}
            size="small"
          />
          <TextField
            label="Actor User ID"
            value={filters.actor_user_id}
            onChange={onChange('actor_user_id')}
            size="small"
            type="number"
          />
          <TextField
            label="Request ID"
            value={filters.request_id}
            onChange={onChange('request_id')}
            size="small"
          />
          <TextField
            label="Created From"
            value={filters.created_from}
            onChange={onChange('created_from')}
            size="small"
            placeholder="2026-02-05T12:00:00"
          />
          <TextField
            label="Created To"
            value={filters.created_to}
            onChange={onChange('created_to')}
            size="small"
            placeholder="2026-02-05T23:59:59"
          />
          <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
            <Button variant="contained" onClick={onApply}>
              Apply
            </Button>
            <Button variant="text" onClick={onReset}>
              Reset
            </Button>
          </Box>
        </Stack>
      </Paper>

      <Paper sx={{ p: 2 }}>
        <Box sx={{ overflowX: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Time</TableCell>
                <TableCell>Actor</TableCell>
                <TableCell>Entity</TableCell>
                <TableCell>Action</TableCell>
                <TableCell>Request</TableCell>
                <TableCell />
              </TableRow>
            </TableHead>
            <TableBody>
              {(logsQuery.data ?? []).map((row) => (
                <TableRow key={row.id} hover>
                  <TableCell sx={{ whiteSpace: 'nowrap' }}>{row.created_at}</TableCell>
                  <TableCell>{row.actor_user_id ?? '-'}</TableCell>
                  <TableCell>
                    {row.entity_type}#{row.entity_id}
                  </TableCell>
                  <TableCell>{row.action}</TableCell>
                  <TableCell sx={{ fontFamily: 'monospace' }}>{row.request_id ?? '-'}</TableCell>
                  <TableCell align="right">
                    <Button size="small" onClick={() => setSelected(row)}>
                      View
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
              {logsQuery.isLoading ? (
                <TableRow>
                  <TableCell colSpan={6}>Loading…</TableCell>
                </TableRow>
              ) : null}
            </TableBody>
          </Table>
        </Box>
      </Paper>

      <Dialog open={!!selected} onClose={() => setSelected(null)} maxWidth="md" fullWidth>
        <DialogTitle>Audit Log Detail</DialogTitle>
        <DialogContent>
          {selected ? (
            <Stack spacing={2}>
              <Typography variant="body2" color="text.secondary">
                {selected.created_at} • {selected.entity_type}#{selected.entity_id} •{' '}
                {selected.action}
              </Typography>

              <Paper variant="outlined" sx={{ p: 2 }}>
                <Typography variant="subtitle2" gutterBottom>
                  Before
                </Typography>
                <pre style={{ margin: 0, overflowX: 'auto' }}>
                  {JSON.stringify(selected.before_json, null, 2)}
                </pre>
              </Paper>

              <Paper variant="outlined" sx={{ p: 2 }}>
                <Typography variant="subtitle2" gutterBottom>
                  After
                </Typography>
                <pre style={{ margin: 0, overflowX: 'auto' }}>
                  {JSON.stringify(selected.after_json, null, 2)}
                </pre>
              </Paper>
            </Stack>
          ) : null}
        </DialogContent>
      </Dialog>
    </Stack>
  );
}
