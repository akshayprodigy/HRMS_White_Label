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
import type { Project } from '../api/core/projects';
import { createProject, listProjects } from '../api/core/projects';

export function ProjectsPage() {
  const qc = useQueryClient();

  const projectsQuery = useQuery({
    queryKey: ['core', 'projects'],
    queryFn: listProjects,
  });

  const [organizationId, setOrganizationId] = useState('');
  const [siteId, setSiteId] = useState('');
  const [code, setCode] = useState('');
  const [name, setName] = useState('');

  const orgIdNum = useMemo(() => {
    const n = Number(organizationId);
    return Number.isFinite(n) ? n : NaN;
  }, [organizationId]);

  const siteIdNumOrNull = useMemo(() => {
    if (!siteId) return null;
    const n = Number(siteId);
    return Number.isFinite(n) ? n : null;
  }, [siteId]);

  const createMut = useMutation<Project, ApiError, void>({
    mutationFn: () =>
      createProject({
        organization_id: orgIdNum,
        site_id: siteIdNumOrNull,
        code,
        name,
      }),
    onSuccess: async () => {
      setCode('');
      setName('');
      await qc.invalidateQueries({ queryKey: ['core', 'projects'] });
    },
  });

  const errorText = createMut.error?.message;

  return (
    <Stack spacing={2}>
      <Typography variant="h5">Core • Projects</Typography>

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
            label="Site ID (optional)"
            value={siteId}
            onChange={(e: ChangeEvent<HTMLInputElement>) => setSiteId(e.target.value)}
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
                <TableCell>Site</TableCell>
                <TableCell>Code</TableCell>
                <TableCell>Name</TableCell>
                <TableCell>Status</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {(projectsQuery.data ?? []).map((p: Project) => (
                <TableRow key={p.id} hover>
                  <TableCell>{p.id}</TableCell>
                  <TableCell>{p.organization_id}</TableCell>
                  <TableCell>{p.site_id ?? '-'}</TableCell>
                  <TableCell>{p.code}</TableCell>
                  <TableCell>{p.name}</TableCell>
                  <TableCell>{p.is_active ? 'Active' : 'Inactive'}</TableCell>
                </TableRow>
              ))}
              {projectsQuery.isLoading ? (
                <TableRow>
                  <TableCell colSpan={6}>Loading…</TableCell>
                </TableRow>
              ) : null}
            </TableBody>
          </Table>
        </Box>
      </Paper>
    </Stack>
  );
}
