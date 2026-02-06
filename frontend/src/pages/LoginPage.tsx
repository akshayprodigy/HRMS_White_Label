import { useMemo, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Box, Button, Container, Alert, Paper, Stack, TextField, Typography } from '@mui/material';

import { useAuth } from '../auth/AuthContext';

export function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const auth = useAuth();

  const from = useMemo(() => {
    const state = location.state as { from?: string } | null;
    return state?.from ?? '/';
  }, [location.state]);

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await auth.login({ email, password });
      navigate(from, { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Container maxWidth="sm">
      <Box sx={{ minHeight: '100vh', display: 'flex', alignItems: 'center' }}>
        <Paper sx={{ width: '100%', p: 4 }} elevation={2}>
          <Stack spacing={2} component="form" onSubmit={onSubmit}>
            <Typography variant="h5">Login</Typography>

            {error ? <Alert severity="error">{error}</Alert> : null}

            <TextField
              label="Email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="email"
              disabled={submitting}
              fullWidth
            />
            <TextField
              label="Password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              disabled={submitting}
              fullWidth
            />
            <Button type="submit" variant="contained" disabled={submitting}>
              Sign in
            </Button>
            <Typography variant="body2" color="text.secondary">
              Uses JWT access token + httpOnly refresh cookie.
            </Typography>
          </Stack>
        </Paper>
      </Box>
    </Container>
  );
}
