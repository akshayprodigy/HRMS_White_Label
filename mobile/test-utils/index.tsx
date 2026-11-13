import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render } from '@testing-library/react-native';
import axios from 'axios';
import MockAdapter from 'axios-mock-adapter';
import { setAdapter, setTokens } from '../src/api/client';
import { ThemeProvider } from '../src/theme';

export function setupApiMock() {
  const mock = new MockAdapter(axios);
  setAdapter(mock.adapter());
  setTokens({ accessToken: 't', refreshToken: 'r' });
  return mock;
}
const clients: QueryClient[] = [];

export async function teardownApiMock() {
  // Cancel in-flight queries and drop caches so react-query leaves no timers behind (jest open-handle warning).
  await cleanup(); // unmount first so VirtualizedList batching timers are cancelled
  for (const c of clients.splice(0)) {
    await c.cancelQueries();
    c.clear();
  }
  setAdapter(undefined);
  setTokens(null);
}

export async function renderWithProviders(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, retryDelay: 0, gcTime: Infinity }, mutations: { gcTime: Infinity } } });
  clients.push(client);
  const r = await render(
    <ThemeProvider>
      <QueryClientProvider client={client}>{ui}</QueryClientProvider>
    </ThemeProvider>,
  );
  return { client, ...r };
}

export const GATE_BODY = { error: { code: 'ATTENDANCE_REQUIRED', message: 'Please mark your attendance first.' } };
