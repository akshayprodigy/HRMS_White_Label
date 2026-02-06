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
import { listCostCenters } from '../api/core/costCenters';
import { listProjects } from '../api/core/projects';
import type { MaterialIssue } from '../api/inventory/issues';
import { createIssue, listIssues } from '../api/inventory/issues';
import { listItems } from '../api/inventory/items';
import { listUoms } from '../api/inventory/uoms';
import { listWarehouses } from '../api/inventory/warehouses';

function helperFromRows(rows: Array<{ id: number; code?: string; sku?: string }>, label: string) {
  if (!rows.length) return `Tip: create ${label} first`;
  const parts = rows.slice(0, 8).map((r) => `${r.id}:${r.code ?? r.sku ?? ''}`.replace(/:$/, ''));
  return `Available: ${parts.join(', ')}${rows.length > 8 ? '…' : ''}`;
}

export function InventoryIssuesPage() {
  const qc = useQueryClient();

  const issuesQuery = useQuery({
    queryKey: ['inventory', 'issues'],
    queryFn: listIssues,
  });

  const projectsQuery = useQuery({
    queryKey: ['core', 'projects'],
    queryFn: listProjects,
  });

  const costCentersQuery = useQuery({
    queryKey: ['core', 'cost-centers'],
    queryFn: listCostCenters,
  });

  const warehousesQuery = useQuery({
    queryKey: ['inventory', 'warehouses'],
    queryFn: listWarehouses,
  });

  const itemsQuery = useQuery({
    queryKey: ['inventory', 'items'],
    queryFn: listItems,
  });

  const uomsQuery = useQuery({
    queryKey: ['inventory', 'uoms'],
    queryFn: listUoms,
  });

  const [issueNumber, setIssueNumber] = useState('');
  const [issueDate, setIssueDate] = useState('');
  const [projectId, setProjectId] = useState('');
  const [costCenterId, setCostCenterId] = useState('');
  const [warehouseId, setWarehouseId] = useState('');
  const [itemId, setItemId] = useState('');
  const [uomId, setUomId] = useState('');
  const [qtyIssued, setQtyIssued] = useState('');
  const [unitCost, setUnitCost] = useState('');
  const [remarks, setRemarks] = useState('');

  const projectIdNum = useMemo(() => Number(projectId), [projectId]);
  const costCenterIdNum = useMemo(() => Number(costCenterId), [costCenterId]);
  const warehouseIdNum = useMemo(() => Number(warehouseId), [warehouseId]);
  const itemIdNum = useMemo(() => Number(itemId), [itemId]);
  const uomIdNum = useMemo(() => Number(uomId), [uomId]);
  const qtyIssuedNum = useMemo(() => Number(qtyIssued), [qtyIssued]);

  const unitCostNumOrNull = useMemo(() => {
    if (!unitCost) return null;
    const n = Number(unitCost);
    return Number.isFinite(n) ? n : null;
  }, [unitCost]);

  const canCreate = useMemo(() => {
    return (
      Boolean(issueNumber) &&
      Boolean(issueDate) &&
      Number.isFinite(projectIdNum) &&
      projectIdNum > 0 &&
      Number.isFinite(costCenterIdNum) &&
      costCenterIdNum > 0 &&
      Number.isFinite(warehouseIdNum) &&
      warehouseIdNum > 0 &&
      Number.isFinite(itemIdNum) &&
      itemIdNum > 0 &&
      Number.isFinite(uomIdNum) &&
      uomIdNum > 0 &&
      Number.isFinite(qtyIssuedNum) &&
      qtyIssuedNum > 0
    );
  }, [
    issueNumber,
    issueDate,
    projectIdNum,
    costCenterIdNum,
    warehouseIdNum,
    itemIdNum,
    uomIdNum,
    qtyIssuedNum,
  ]);

  const createMut = useMutation<MaterialIssue, ApiError, void>({
    mutationFn: () =>
      createIssue({
        issue_number: issueNumber,
        issue_date: issueDate,
        project_id: projectIdNum,
        cost_center_id: costCenterIdNum,
        warehouse_id: warehouseIdNum,
        item_id: itemIdNum,
        uom_id: uomIdNum,
        qty_issued: qtyIssuedNum,
        unit_cost: unitCostNumOrNull,
        remarks: remarks || null,
      }),
    onSuccess: async () => {
      setIssueNumber('');
      setProjectId('');
      setCostCenterId('');
      setWarehouseId('');
      setItemId('');
      setUomId('');
      setQtyIssued('');
      setUnitCost('');
      setRemarks('');
      await qc.invalidateQueries({ queryKey: ['inventory', 'issues'] });
    },
  });

  const projectHelp = useMemo(() => {
    const rows = (projectsQuery.data ?? []).map((p) => ({ id: p.id, code: p.code }));
    return helperFromRows(rows, 'projects');
  }, [projectsQuery.data]);

  const costCenterHelp = useMemo(() => {
    const rows = (costCentersQuery.data ?? []).map((c) => ({ id: c.id, code: c.code }));
    return helperFromRows(rows, 'cost centers');
  }, [costCentersQuery.data]);

  const warehouseHelp = useMemo(() => {
    return helperFromRows(warehousesQuery.data ?? [], 'warehouses');
  }, [warehousesQuery.data]);

  const itemHelp = useMemo(() => {
    return helperFromRows(itemsQuery.data ?? [], 'items');
  }, [itemsQuery.data]);

  const uomHelp = useMemo(() => {
    return helperFromRows(uomsQuery.data ?? [], 'uoms');
  }, [uomsQuery.data]);

  return (
    <Stack spacing={2}>
      <Typography variant="h5">Inventory • Issue Entry</Typography>

      <Paper sx={{ p: 2 }}>
        <Stack spacing={2} direction={{ xs: 'column', md: 'row' }} alignItems={{ md: 'end' }}>
          <TextField
            label="Issue Number"
            value={issueNumber}
            onChange={(e: ChangeEvent<HTMLInputElement>) => setIssueNumber(e.target.value)}
            size="small"
            sx={{ width: 220 }}
          />
          <TextField
            label="Issue Date"
            value={issueDate}
            onChange={(e: ChangeEvent<HTMLInputElement>) => setIssueDate(e.target.value)}
            type="date"
            size="small"
            InputLabelProps={{ shrink: true }}
            sx={{ width: 170 }}
          />
          <TextField
            label="Project ID"
            value={projectId}
            onChange={(e: ChangeEvent<HTMLInputElement>) => setProjectId(e.target.value)}
            type="number"
            size="small"
            sx={{ width: 180 }}
            helperText={projectHelp}
          />
          <TextField
            label="Cost Center ID"
            value={costCenterId}
            onChange={(e: ChangeEvent<HTMLInputElement>) => setCostCenterId(e.target.value)}
            type="number"
            size="small"
            sx={{ width: 180 }}
            helperText={costCenterHelp}
          />
        </Stack>

        <Stack
          spacing={2}
          direction={{ xs: 'column', md: 'row' }}
          alignItems={{ md: 'end' }}
          sx={{ mt: 2 }}
        >
          <TextField
            label="Warehouse ID"
            value={warehouseId}
            onChange={(e: ChangeEvent<HTMLInputElement>) => setWarehouseId(e.target.value)}
            type="number"
            size="small"
            sx={{ width: 180 }}
            helperText={warehouseHelp}
          />
          <TextField
            label="Item ID"
            value={itemId}
            onChange={(e: ChangeEvent<HTMLInputElement>) => setItemId(e.target.value)}
            type="number"
            size="small"
            sx={{ width: 180 }}
            helperText={itemHelp}
          />
          <TextField
            label="UOM ID"
            value={uomId}
            onChange={(e: ChangeEvent<HTMLInputElement>) => setUomId(e.target.value)}
            type="number"
            size="small"
            sx={{ width: 180 }}
            helperText={uomHelp}
          />
          <TextField
            label="Qty Issued"
            value={qtyIssued}
            onChange={(e: ChangeEvent<HTMLInputElement>) => setQtyIssued(e.target.value)}
            type="number"
            size="small"
            sx={{ width: 170 }}
          />
          <TextField
            label="Unit Cost (optional)"
            value={unitCost}
            onChange={(e: ChangeEvent<HTMLInputElement>) => setUnitCost(e.target.value)}
            type="number"
            size="small"
            sx={{ width: 170 }}
          />
          <TextField
            label="Remarks (optional)"
            value={remarks}
            onChange={(e: ChangeEvent<HTMLInputElement>) => setRemarks(e.target.value)}
            size="small"
            sx={{ flex: 1, minWidth: 240 }}
          />
          <Button
            variant="contained"
            disabled={!canCreate || createMut.isPending}
            onClick={() => createMut.mutate()}
          >
            Create
          </Button>
        </Stack>

        {createMut.error ? (
          <Typography color="error" variant="body2" sx={{ mt: 1 }}>
            {createMut.error.message}
          </Typography>
        ) : null}

        {createMut.isSuccess ? (
          <Typography variant="body2" sx={{ mt: 1 }}>
            Issue created.
          </Typography>
        ) : null}
      </Paper>

      <Paper sx={{ p: 2 }}>
        <Box sx={{ overflowX: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>ID</TableCell>
                <TableCell>Issue #</TableCell>
                <TableCell>Date</TableCell>
                <TableCell>Project</TableCell>
                <TableCell>Cost Center</TableCell>
                <TableCell>Item</TableCell>
                <TableCell>Qty</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {(issuesQuery.data ?? []).map((r: MaterialIssue) => (
                <TableRow key={r.id} hover>
                  <TableCell>{r.id}</TableCell>
                  <TableCell>{r.issue_number}</TableCell>
                  <TableCell>{r.issue_date}</TableCell>
                  <TableCell>{r.project_id}</TableCell>
                  <TableCell>{r.cost_center_id}</TableCell>
                  <TableCell>{r.item_id}</TableCell>
                  <TableCell>{r.qty_issued}</TableCell>
                </TableRow>
              ))}
              {issuesQuery.isLoading ? (
                <TableRow>
                  <TableCell colSpan={7}>Loading…</TableCell>
                </TableRow>
              ) : null}
            </TableBody>
          </Table>
        </Box>
      </Paper>
    </Stack>
  );
}
