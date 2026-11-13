import React, { createContext, useContext, useMemo } from 'react';
import { useColorScheme } from 'react-native';
import { getTenant } from '../config/tenant';
import type { TenantColors } from '../../tenants/validate';

export type Theme = {
  dark: boolean;
  colors: TenantColors;
  spacing: { xs: number; sm: number; md: number; lg: number; xl: number };
  radius: number;
};

export function buildTheme(colors: TenantColors, colorsDark: Partial<TenantColors> | undefined, dark: boolean): Theme {
  return {
    dark,
    colors: dark ? { ...colors, ...colorsDark } : colors,
    spacing: { xs: 4, sm: 8, md: 16, lg: 24, xl: 32 },
    radius: 12,
  };
}

const ThemeContext = createContext<Theme | null>(null);

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const scheme = useColorScheme();
  const theme = useMemo(() => {
    const t = getTenant();
    return buildTheme(t.colors, t.colorsDark, scheme === 'dark');
  }, [scheme]);
  return <ThemeContext.Provider value={theme}>{children}</ThemeContext.Provider>;
}

export function useTheme(): Theme {
  const t = useContext(ThemeContext);
  if (!t) throw new Error('useTheme must be used inside <ThemeProvider>');
  return t;
}
