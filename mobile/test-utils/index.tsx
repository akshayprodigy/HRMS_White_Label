import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render } from '@testing-library/react-native';
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
export function teardownApiMock() {
  setAdapter(undefined);
  setTokens(null);
}

export async function renderWithProviders(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } });
  const r = await render(
    <ThemeProvider>
      <QueryClientProvider client={client}>{ui}</QueryClientProvider>
    </ThemeProvider>,
  );
  return { client, ...r };
}

export const GATE_BODY = { error: { code: 'ATTENDANCE_REQUIRED', message: 'Please mark your attendance first.' } };
