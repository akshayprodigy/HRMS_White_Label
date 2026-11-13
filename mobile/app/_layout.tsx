import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Stack } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { StatusBar } from 'expo-status-bar';
import { useEffect, useState } from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { ErrorBoundary } from '../src/components/ErrorBoundary';
import { AuthProvider, useAuth } from '../src/auth/AuthProvider';
import { usePunchQueueSyncLoop } from '../src/features/punch/hooks';
import { useAppStateFocus } from '../src/lib/appFocus';
import { sweepDownloads } from '../src/lib/download';
import { ThemeProvider, useTheme } from '../src/theme';

void SplashScreen.preventAutoHideAsync().catch(() => undefined);

function AuthGate() {
  const { user, loading } = useAuth();
  const { dark } = useTheme();
  usePunchQueueSyncLoop();

  useEffect(() => {
    if (!loading) void SplashScreen.hideAsync().catch(() => undefined);
  }, [loading]);

  // Keep the native splash up until the stored session has been resolved: no login-screen flicker.
  if (loading) return null;
  return (
    <>
      <StatusBar style={dark ? 'light' : 'dark'} />
      <Stack screenOptions={{ headerShown: false }}>
        <Stack.Protected guard={!!user}>
          <Stack.Screen name="(tabs)" />
          <Stack.Screen name="approval/[key]" options={{ headerShown: true, title: 'Approval' }} />
          <Stack.Screen name="payslips" options={{ headerShown: true, title: 'Payslips' }} />
          <Stack.Screen name="documents" options={{ headerShown: true, title: 'Documents' }} />
        </Stack.Protected>
        <Stack.Protected guard={!user}>
          <Stack.Screen name="(auth)" />
        </Stack.Protected>
      </Stack>
    </>
  );
}

export default function RootLayout() {
  useAppStateFocus();
  useEffect(() => sweepDownloads(), []); // drop sensitive downloads left by a killed session
  const [queryClient] = useState(() => new QueryClient({ defaultOptions: { queries: { retry: 1, staleTime: 30_000 } } }));
  return (
    <ErrorBoundary>
      <SafeAreaProvider>
        <ThemeProvider>
          <QueryClientProvider client={queryClient}>
            <AuthProvider>
              <AuthGate />
            </AuthProvider>
          </QueryClientProvider>
        </ThemeProvider>
      </SafeAreaProvider>
    </ErrorBoundary>
  );
}
