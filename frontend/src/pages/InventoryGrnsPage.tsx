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
import type { Grn } from '../api/inventory/grns';
import { createGrn, listGrns } from '../api/inventory/grns';
import { listItems } from '../api/inventory/items';
import { listUoms } from '../api/inventory/uoms';
import { listWarehouses } from '../api/inventory/warehouses';

function helperFromRows(rows: Array<{ id: number; code?: string; sku?: string }>, label: string) {
  if (!rows.length) return `Tip: create ${label} first`;
  const parts = rows.slice(0, 8).map((r) => `${r.id}:${r.code ?? r.sku ?? ''}`.replace(/:$/, ''));
  return `Available: ${parts.join(', ')}${rows.length > 8 ? '…' : ''}`;
}

export function InventoryGrnsPage() {
  const qc = useQueryClient();

  const grnsQuery = useQuery({
    queryKey: ['inventory', 'grns'],
    queryFn: listGrns,
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

  const [grnNumber, setGrnNumber] = useState('');
  const [grnDate, setGrnDate] = useState('');
  const [purchaseOrderId, setPurchaseOrderId] = useState('');
  const [vendorName, setVendorName] = useState('');
  const [warehouseId, setWarehouseId] = useState('');
  const [itemId, setItemId] = useState('');
  const [uomId, setUomId] = useState('');
  const [qtyReceived, setQtyReceived] = useState('');
  const [unitCost, setUnitCost] = useState('');
  const [notes, setNotes] = useState('');

  const warehouseIdNum = useMemo(() => Number(warehouseId), [warehouseId]);
  const itemIdNum = useMemo(() => Number(itemId), [itemId]);
  const uomIdNum = useMemo(() => Number(uomId), [uomId]);
  const qtyReceivedNum = useMemo(() => Number(qtyReceived), [qtyReceived]);

  const poIdNumOrNull = useMemo(() => {
    if (!purchaseOrderId) return null;
    const n = Number(purchaseOrderId);
    return Number.isFinite(n) ? n : null;
  }, [purchaseOrderId]);

  const unitCostNumOrNull = useMemo(() => {
    if (!unitCost) return null;
    const n = Number(unitCost);
    return Number.isFinite(n) ? n : null;
  }, [unitCost]);

  const canCreate = useMemo(() => {
    return (
      Boolean(grnNumber) &&
      Boolean(grnDate) &&
      Number.isFinite(warehouseIdNum) &&
      warehouseIdNum > 0 &&
      Number.isFinite(itemIdNum) &&
      itemIdNum > 0 &&
      Number.isFinite(uomIdNum) &&
      uomIdNum > 0 &&
      Number.isFinite(qtyReceivedNum) &&
      qtyReceivedNum > 0
    );
  }, [grnNumber, grnDate, warehouseIdNum, itemIdNum, uomIdNum, qtyReceivedNum]);

  const createMut = useMutation<Grn, ApiError, void>({
    mutationFn: () =>
      createGrn({
        grn_number: grnNumber,
        grn_date: grnDate,
        purchase_order_id: poIdNumOrNull,
        vendor_name: vendorName || null,
        warehouse_id: warehouseIdNum,
        item_id: itemIdNum,
        uom_id: uomIdNum,
        qty_received: qtyReceivedNum,
        unit_cost: unitCostNumOrNull,
        notes: notes || null,
      }),
    onSuccess: async () => {
      setGrnNumber('');
      setPurchaseOrderId('');
      setVendorName('');
      setWarehouseId('');
      setItemId('');
      setUomId('');
      setQtyReceived('');
      setUnitCost('');
      setNotes('');
      await qc.invalidateQueries({ queryKey: ['inventory', 'grns'] });
    },
  });

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
      <Typography variant="h5">Inventory • GRN Entry</Typography>

      <Paper sx={{ p: 2 }}>
        <Stack spacing={2} direction={{ xs: 'column', md: 'row' }} alignItems={{ md: 'end' }}>
          <TextField
            label="GRN Number"
            value={grnNumber}
            onChange={(e: ChangeEvent<HTMLInputElement>) => setGrnNumber(e.target.value)}
            size="small"
            sx={{ width: 220 }}
          />
          <TextField
            label="GRN Date"
            value={grnDate}
            onChange={(e: ChangeEvent<HTMLInputElement>) => setGrnDate(e.target.value)}
            type="date"
            size="small"
            InputLabelProps={{ shrink: true }}
            sx={{ width: 170 }}
          />
          <TextField
            label="PO ID (optional)"
            value={purchaseOrderId}
            onChange={(e: ChangeEvent<HTMLInputElement>) => setPurchaseOrderId(e.target.value)}
            type="number"
            size="small"
            sx={{ width: 170 }}
          />
          <TextField
            label="Vendor (optional)"
            value={vendorName}
            onChange={(e: ChangeEvent<HTMLInputElement>) => setVendorName(e.target.value)}
            size="small"
            sx={{ width: 220 }}
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
            label="Qty Received"
            value={qtyReceived}
            onChange={(e: ChangeEvent<HTMLInputElement>) => setQtyReceived(e.target.value)}
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
            label="Notes (optional)"
            value={notes}
            onChange={(e: ChangeEvent<HTMLInputElement>) => setNotes(e.target.value)}
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
            GRN created.
          </Typography>
        ) : null}
      </Paper>

      <Paper sx={{ p: 2 }}>
        <Box sx={{ overflowX: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>ID</TableCell>
                <TableCell>GRN #</TableCell>
                <TableCell>Date</TableCell>
                <TableCell>Warehouse</TableCell>
                <TableCell>Item</TableCell>
                <TableCell>Qty</TableCell>
                <TableCell>Cost</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {(grnsQuery.data ?? []).map((g: Grn) => (
                <TableRow key={g.id} hover>
                  <TableCell>{g.id}</TableCell>
                  <TableCell>{g.grn_number}</TableCell>
                  <TableCell>{g.grn_date}</TableCell>
                  <TableCell>{g.warehouse_id}</TableCell>
                  <TableCell>{g.item_id}</TableCell>
                  <TableCell>{g.qty_received}</TableCell>
                  <TableCell>{g.unit_cost ?? '-'}</TableCell>
                </TableRow>
              ))}
              {grnsQuery.isLoading ? (
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
