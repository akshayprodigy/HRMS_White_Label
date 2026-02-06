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
import type { Item } from '../api/inventory/items';
import { createItem, listItems } from '../api/inventory/items';
import { listUoms } from '../api/inventory/uoms';

export function InventoryItemsPage() {
  const qc = useQueryClient();

  const itemsQuery = useQuery({
    queryKey: ['inventory', 'items'],
    queryFn: listItems,
  });

  const uomsQuery = useQuery({
    queryKey: ['inventory', 'uoms'],
    queryFn: listUoms,
  });

  const uomById = useMemo(() => {
    const out = new Map<number, { code: string; name: string }>();
    for (const u of uomsQuery.data ?? []) out.set(u.id, { code: u.code, name: u.name });
    return out;
  }, [uomsQuery.data]);

  const [sku, setSku] = useState('');
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [baseUomId, setBaseUomId] = useState('');

  const baseUomIdNum = useMemo(() => Number(baseUomId), [baseUomId]);

  const canCreate = useMemo(() => {
    return Boolean(sku) && Boolean(name) && Number.isFinite(baseUomIdNum) && baseUomIdNum > 0;
  }, [sku, name, baseUomIdNum]);

  const createMut = useMutation<Item, ApiError, void>({
    mutationFn: () =>
      createItem({
        sku,
        name,
        description: description || null,
        base_uom_id: baseUomIdNum,
      }),
    onSuccess: async () => {
      setSku('');
      setName('');
      setDescription('');
      setBaseUomId('');
      await qc.invalidateQueries({ queryKey: ['inventory', 'items'] });
    },
  });

  const helperUoms = useMemo(() => {
    const rows = uomsQuery.data ?? [];
    if (!rows.length) return 'Tip: create UOMs first';
    return `Available: ${rows
      .slice(0, 8)
      .map((u) => `${u.id}:${u.code}`)
      .join(', ')}${rows.length > 8 ? '…' : ''}`;
  }, [uomsQuery.data]);

  return (
    <Stack spacing={2}>
      <Typography variant="h5">Inventory • Item Master</Typography>

      <Paper sx={{ p: 2 }}>
        <Stack spacing={2} direction={{ xs: 'column', md: 'row' }} alignItems={{ md: 'end' }}>
          <TextField
            label="SKU"
            value={sku}
            onChange={(e: ChangeEvent<HTMLInputElement>) => setSku(e.target.value)}
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
          <TextField
            label="Base UOM ID"
            value={baseUomId}
            onChange={(e: ChangeEvent<HTMLInputElement>) => setBaseUomId(e.target.value)}
            type="number"
            size="small"
            sx={{ width: 180 }}
            helperText={helperUoms}
          />
          <TextField
            label="Description (optional)"
            value={description}
            onChange={(e: ChangeEvent<HTMLInputElement>) => setDescription(e.target.value)}
            size="small"
            sx={{ flex: 1, minWidth: 260 }}
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
          <Typography variant="body2" color="error" sx={{ mt: 1 }}>
            {createMut.error.message}
          </Typography>
        ) : null}
      </Paper>

      <Paper sx={{ p: 2 }}>
        <Box sx={{ overflowX: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>ID</TableCell>
                <TableCell>SKU</TableCell>
                <TableCell>Name</TableCell>
                <TableCell>Base UOM</TableCell>
                <TableCell>Status</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {(itemsQuery.data ?? []).map((it: Item) => {
                const u = uomById.get(it.base_uom_id);
                const uomText = u ? `${it.base_uom_id} (${u.code})` : String(it.base_uom_id);
                return (
                  <TableRow key={it.id} hover>
                    <TableCell>{it.id}</TableCell>
                    <TableCell>{it.sku}</TableCell>
                    <TableCell>{it.name}</TableCell>
                    <TableCell>{uomText}</TableCell>
                    <TableCell>{it.is_active ? 'Active' : 'Inactive'}</TableCell>
                  </TableRow>
                );
              })}
              {itemsQuery.isLoading ? (
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
