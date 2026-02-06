import type { ChangeEvent } from 'react';
import { useMemo, useState } from 'react';
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
import type { Site } from '../api/core/sites';
import { createSite, listSites } from '../api/core/sites';

export function SitesPage() {
  const qc = useQueryClient();

  const sitesQuery = useQuery({
    queryKey: ['core', 'sites'],
    queryFn: listSites,
  });

  const [organizationId, setOrganizationId] = useState('');
  const [code, setCode] = useState('');
  const [name, setName] = useState('');

  const orgIdNum = useMemo(() => {
    const n = Number(organizationId);
    return Number.isFinite(n) ? n : NaN;
  }, [organizationId]);

  const createMut = useMutation<Site, ApiError, void>({
    mutationFn: () =>
      createSite({
        organization_id: orgIdNum,
        code,
        name,
      }),
    onSuccess: async () => {
      setCode('');
      setName('');
      await qc.invalidateQueries({ queryKey: ['core', 'sites'] });
    },
  });

  const errorText = createMut.error?.message;

  return (
    <Stack spacing={2}>
      <Typography variant="h5">Core • Sites</Typography>

      <Paper sx={{ p: 2 }}>
        <Stack spacing={2} direction={{ xs: 'column', md: 'row' }} alignItems={{ md: 'end' }}>
          <TextField
            label="Organization ID"
            value={organizationId}
            onChange={(e: ChangeEvent<HTMLInputElement>) => setOrganizationId(e.target.value)}
            type="number"
            size="small"
            sx={{ width: 200 }}
          />
          <TextField
            label="Code"
            value={code}
            onChange={(e: ChangeEvent<HTMLInputElement>) => setCode(e.target.value)}
            size="small"
            sx={{ width: 220 }}
          />
          <TextField
            label="Name"
            value={name}
            onChange={(e: ChangeEvent<HTMLInputElement>) => setName(e.target.value)}
            size="small"
            sx={{ flex: 1, minWidth: 260 }}
          />
          <Button
            variant="contained"
            disabled={!organizationId || !code || !name || createMut.isPending}
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
                <TableCell>Org</TableCell>
                <TableCell>Code</TableCell>
                <TableCell>Name</TableCell>
                <TableCell>Status</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {(sitesQuery.data ?? []).map((s: Site) => (
                <TableRow key={s.id} hover>
                  <TableCell>{s.id}</TableCell>
                  <TableCell>{s.organization_id}</TableCell>
                  <TableCell>{s.code}</TableCell>
                  <TableCell>{s.name}</TableCell>
                  <TableCell>{s.is_active ? 'Active' : 'Inactive'}</TableCell>
                </TableRow>
              ))}
              {sitesQuery.isLoading ? (
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
