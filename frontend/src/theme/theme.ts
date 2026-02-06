import { createTheme } from '@mui/material';

import { tokens } from './tokens';

export const theme = createTheme({
  palette: {
    mode: 'light',
    primary: tokens.palette.primary,
    secondary: tokens.palette.secondary,
    background: tokens.palette.background,
  },
  shape: tokens.shape,
  typography: tokens.typography,
});
