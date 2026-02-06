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
import type { Uom } from '../api/inventory/uoms';
import { createUom, listUoms } from '../api/inventory/uoms';

export function InventoryUomsPage() {
  const qc = useQueryClient();

  const uomsQuery = useQuery({
    queryKey: ['inventory', 'uoms'],
    queryFn: listUoms,
  });

  const [code, setCode] = useState('');
  const [name, setName] = useState('');
  const [symbol, setSymbol] = useState('');

  const createMut = useMutation<Uom, ApiError, void>({
    mutationFn: () =>
      createUom({
        code,
        name,
        symbol: symbol || null,
      }),
    onSuccess: async () => {
      setCode('');
      setName('');
      setSymbol('');
      await qc.invalidateQueries({ queryKey: ['inventory', 'uoms'] });
    },
  });

  const errorText = createMut.error?.message;

  return (
    <Stack spacing={2}>
      <Typography variant="h5">Inventory • UOMs</Typography>

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
            label="Symbol (optional)"
            value={symbol}
            onChange={(e: ChangeEvent<HTMLInputElement>) => setSymbol(e.target.value)}
            size="small"
            sx={{ width: 220 }}
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
                <TableCell>Symbol</TableCell>
                <TableCell>Status</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {(uomsQuery.data ?? []).map((u: Uom) => (
                <TableRow key={u.id} hover>
                  <TableCell>{u.id}</TableCell>
                  <TableCell>{u.code}</TableCell>
                  <TableCell>{u.name}</TableCell>
                  <TableCell>{u.symbol ?? '-'}</TableCell>
                  <TableCell>{u.is_active ? 'Active' : 'Inactive'}</TableCell>
                </TableRow>
              ))}
              {uomsQuery.isLoading ? (
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
