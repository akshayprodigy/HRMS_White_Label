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
import { useMutation, useQuery } from '@tanstack/react-query';

import type { ApiError } from '../api/client';
import { listProjects } from '../api/core/projects';
import { listItems } from '../api/inventory/items';
import type { ProjectConsumptionRow } from '../api/inventory/reports';
import { getProjectConsumption } from '../api/inventory/reports';

function helperFromRows(rows: Array<{ id: number; code?: string; sku?: string }>, label: string) {
  if (!rows.length) return `Tip: create ${label} first`;
  const parts = rows.slice(0, 8).map((r) => `${r.id}:${r.code ?? r.sku ?? ''}`.replace(/:$/, ''));
  return `Available: ${parts.join(', ')}${rows.length > 8 ? '…' : ''}`;
}

export function InventoryProjectConsumptionPage() {
  const projectsQuery = useQuery({
    queryKey: ['core', 'projects'],
    queryFn: listProjects,
  });

  const itemsQuery = useQuery({
    queryKey: ['inventory', 'items'],
    queryFn: listItems,
  });

  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [projectId, setProjectId] = useState('');
  const [itemId, setItemId] = useState('');

  const projectIdNumOrUndefined = useMemo(() => {
    if (!projectId) return undefined;
    const n = Number(projectId);
    return Number.isFinite(n) ? n : undefined;
  }, [projectId]);

  const itemIdNumOrUndefined = useMemo(() => {
    if (!itemId) return undefined;
    const n = Number(itemId);
    return Number.isFinite(n) ? n : undefined;
  }, [itemId]);

  const canRun = useMemo(() => Boolean(dateFrom) && Boolean(dateTo), [dateFrom, dateTo]);

  const projectById = useMemo(() => {
    const out = new Map<number, string>();
    for (const p of projectsQuery.data ?? []) out.set(p.id, p.code);
    return out;
  }, [projectsQuery.data]);

  const itemById = useMemo(() => {
    const out = new Map<number, string>();
    for (const it of itemsQuery.data ?? []) out.set(it.id, it.sku);
    return out;
  }, [itemsQuery.data]);

  const runMut = useMutation<ProjectConsumptionRow[], ApiError, void>({
    mutationFn: () =>
      getProjectConsumption({
        date_from: dateFrom,
        date_to: dateTo,
        project_id: projectIdNumOrUndefined,
        item_id: itemIdNumOrUndefined,
      }),
  });

  const rows = runMut.data ?? [];

  const projectHelp = useMemo(() => {
    const p = (projectsQuery.data ?? []).map((x) => ({ id: x.id, code: x.code }));
    return helperFromRows(p, 'projects');
  }, [projectsQuery.data]);

  const itemHelp = useMemo(() => {
    const it = (itemsQuery.data ?? []).map((x) => ({ id: x.id, sku: x.sku }));
    return helperFromRows(it, 'items');
  }, [itemsQuery.data]);

  return (
    <Stack spacing={2}>
      <Typography variant="h5">Inventory • Project-wise Consumption</Typography>

      <Paper sx={{ p: 2 }}>
        <Stack spacing={2} direction={{ xs: 'column', md: 'row' }} alignItems={{ md: 'end' }}>
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
            label="Project ID (optional)"
            value={projectId}
            onChange={(e: ChangeEvent<HTMLInputElement>) => setProjectId(e.target.value)}
            type="number"
            size="small"
            sx={{ width: 200 }}
            helperText={projectHelp}
          />
          <TextField
            label="Item ID (optional)"
            value={itemId}
            onChange={(e: ChangeEvent<HTMLInputElement>) => setItemId(e.target.value)}
            type="number"
            size="small"
            sx={{ width: 200 }}
            helperText={itemHelp}
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

        {runMut.isSuccess ? (
          <Typography variant="body2" sx={{ mt: 1 }}>
            {rows.length} row(s)
          </Typography>
        ) : null}
      </Paper>

      <Paper sx={{ p: 2 }}>
        <Box sx={{ overflowX: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Project</TableCell>
                <TableCell>Item</TableCell>
                <TableCell align="right">Qty Issued</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {rows.map((r: ProjectConsumptionRow) => {
                const prj = projectById.get(r.project_id);
                const it = itemById.get(r.item_id);
                const projectText = prj ? `${r.project_id} (${prj})` : String(r.project_id);
                const itemText = it ? `${r.item_id} (${it})` : String(r.item_id);
                return (
                  <TableRow key={`${r.project_id}-${r.item_id}`} hover>
                    <TableCell>{projectText}</TableCell>
                    <TableCell>{itemText}</TableCell>
                    <TableCell align="right">{r.qty_issued}</TableCell>
                  </TableRow>
                );
              })}
              {!rows.length && runMut.isSuccess ? (
                <TableRow>
                  <TableCell colSpan={3}>No data.</TableCell>
                </TableRow>
              ) : null}
            </TableBody>
          </Table>
        </Box>
      </Paper>
    </Stack>
  );
}
