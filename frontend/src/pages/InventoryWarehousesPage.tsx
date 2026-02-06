import type { ChangeEvent } from 'react';
import { useState } from 'react';
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
import type { Warehouse } from '../api/inventory/warehouses';
import { createWarehouse, listWarehouses } from '../api/inventory/warehouses';

export function InventoryWarehousesPage() {
  const qc = useQueryClient();

  const warehousesQuery = useQuery({
    queryKey: ['inventory', 'warehouses'],
    queryFn: listWarehouses,
  });

  const [code, setCode] = useState('');
  const [name, setName] = useState('');
  const [location, setLocation] = useState('');

  const createMut = useMutation<Warehouse, ApiError, void>({
    mutationFn: () =>
      createWarehouse({
        code,
        name,
        location: location || null,
      }),
    onSuccess: async () => {
      setCode('');
      setName('');
      setLocation('');
      await qc.invalidateQueries({ queryKey: ['inventory', 'warehouses'] });
    },
  });

  const errorText = createMut.error?.message;

  return (
    <Stack spacing={2}>
      <Typography variant="h5">Inventory • Warehouses</Typography>

      <Paper sx={{ p: 2 }}>
        <Stack spacing={2} direction={{ xs: 'column', md: 'row' }} alignItems={{ md: 'end' }}>
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
          <TextField
            label="Location (optional)"
            value={location}
            onChange={(e: ChangeEvent<HTMLInputElement>) => setLocation(e.target.value)}
            size="small"
            sx={{ width: 260 }}
          />
          <Button
            variant="contained"
            disabled={!code || !name || createMut.isPending}
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
                <TableCell>Code</TableCell>
                <TableCell>Name</TableCell>
                <TableCell>Location</TableCell>
                <TableCell>Status</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {(warehousesQuery.data ?? []).map((w: Warehouse) => (
                <TableRow key={w.id} hover>
                  <TableCell>{w.id}</TableCell>
                  <TableCell>{w.code}</TableCell>
                  <TableCell>{w.name}</TableCell>
                  <TableCell>{w.location ?? '-'}</TableCell>
                  <TableCell>{w.is_active ? 'Active' : 'Inactive'}</TableCell>
                </TableRow>
              ))}
              {warehousesQuery.isLoading ? (
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
