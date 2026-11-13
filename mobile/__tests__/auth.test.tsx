import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render, waitFor } from '@testing-library/react-native';
import axios from 'axios';
import MockAdapter from 'axios-mock-adapter';
import { setAdapter, setTokens, getTokens } from '../src/api/client';
import { AuthProvider, useAuth, type AuthState } from '../src/auth/AuthProvider';
import { tokenStorage } from '../src/auth/tokenStorage';

jest.mock('../src/config/tenant', () => ({ getApiBaseUrl: () => 'http://test/api/v1' }));

const ME = { id: 1, email: 'employee@gmail.com', full_name: 'Emp' };
let mock: MockAdapter;
let auth: AuthState;
let qc: QueryClient;

function Probe() {
  auth = useAuth();
  return null;
}
const mount = () =>
  render(
    <QueryClientProvider client={qc}>
      <AuthProvider>
        <Probe />
      </AuthProvider>
    </QueryClientProvider>,
  );

beforeEach(async () => {
  mock = new MockAdapter(axios);
  setAdapter(mock.adapter());
  qc = new QueryClient();
  await tokenStorage.clear();
  setTokens(null);
});
afterEach(() => setAdapter(undefined));

describe('AuthProvider session restore', () => {
  it('keeps tokens and the cached user ("unverified") when the server is unreachable', async () => {
    await tokenStorage.save({ accessToken: 'a', refreshToken: 'r' });
    await tokenStorage.saveMe(ME);
    mock.onGet('/auth/me').networkError();
    await mount();
    await waitFor(() => expect(auth.loading).toBe(false));
    expect(auth.user).toMatchObject({ email: ME.email });
    expect(auth.unverified).toBe(true);
    expect(await tokenStorage.load()).toEqual({ accessToken: 'a', refreshToken: 'r' });
  });

  it('keeps the session on a 5xx too', async () => {
    await tokenStorage.save({ accessToken: 'a', refreshToken: 'r' });
    await tokenStorage.saveMe(ME);
    mock.onGet('/auth/me').reply(503);
    await mount();
    await waitFor(() => expect(auth.loading).toBe(false));
    expect(auth.unverified).toBe(true);
    expect(auth.user).not.toBeNull();
  });

  it('goes to login (and wipes storage) only when /me is 401 and refresh is rejected', async () => {
    await tokenStorage.save({ accessToken: 'a', refreshToken: 'r' });
    await tokenStorage.saveMe(ME);
    mock.onGet('/auth/me').reply(401, {});
    mock.onPost('/auth/refresh').reply(401, {});
    await mount();
    await waitFor(() => expect(auth.loading).toBe(false));
    expect(auth.user).toBeNull();
    expect(await tokenStorage.load()).toBeNull();
    expect(await tokenStorage.loadMe()).toBeNull();
  });

  it('verified restore clears the unverified flag and refreshes the cache', async () => {
    await tokenStorage.save({ accessToken: 'a', refreshToken: 'r' });
    mock.onGet('/auth/me').reply(200, ME);
    await mount();
    await waitFor(() => expect(auth.loading).toBe(false));
    expect(auth.unverified).toBe(false);
    expect(await tokenStorage.loadMe()).toMatchObject({ email: ME.email });
  });
});

describe('query cache is cleared on logout', () => {
  async function loggedIn() {
    await tokenStorage.save({ accessToken: 'a', refreshToken: 'r' });
    mock.onGet('/auth/me').reply(200, ME);
    await mount();
    await waitFor(() => expect(auth.user).not.toBeNull());
    qc.setQueryData(['payslips'], [1, 2, 3]);
  }

  it('on user logout', async () => {
    await loggedIn();
    await act(async () => {
      await auth.logout();
    });
    expect(qc.getQueryData(['payslips'])).toBeUndefined();
    expect(auth.user).toBeNull();
    expect(getTokens()).toBeNull();
  });

  it('on forced logout after a dead refresh', async () => {
    await loggedIn();
    mock.onGet('/boom').reply(401, {});
    mock.onPost('/auth/refresh').reply(401, {});
    const { api } = require('../src/api/client');
    await act(async () => {
      await api.get('/boom').catch(() => undefined);
    });
    await waitFor(() => expect(auth.user).toBeNull());
    expect(qc.getQueryData(['payslips'])).toBeUndefined();
  });
});
