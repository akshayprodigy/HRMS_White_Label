import { useQuery } from '@tanstack/react-query';
import { Alert, Box, CircularProgress, Paper, Stack, Typography } from '@mui/material';

import { apiFetch } from '../api/client';

type UserPublic = {
  id: number;
  email: string;
  is_active: boolean;
};

export function AdminUsersPage() {
  const usersQuery = useQuery({
    queryKey: ['admin', 'users'],
    queryFn: () => apiFetch<UserPublic[]>('/api/v1/admin/users'),
  });

  return (
    <Stack spacing={2}>
      <Typography variant="h5">Admin • Users</Typography>

      {usersQuery.isLoading ? (
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
          <CircularProgress size={20} />
          <Typography variant="body2" color="text.secondary">
            Loading users…
          </Typography>
        </Box>
      ) : null}

      {usersQuery.isError ? <Alert severity="error">Failed to load users.</Alert> : null}

      {usersQuery.data ? (
        <Paper variant="outlined" sx={{ p: 2 }}>
          <Stack spacing={1}>
            {usersQuery.data.map((u: UserPublic) => (
              <Box key={u.id} sx={{ display: 'flex', justifyContent: 'space-between' }}>
                <Typography>{u.email}</Typography>
                <Typography variant="body2" color="text.secondary">
                  {u.is_active ? 'active' : 'inactive'}
                </Typography>
              </Box>
            ))}
          </Stack>
        </Paper>
      ) : null}
    </Stack>
  );
}
