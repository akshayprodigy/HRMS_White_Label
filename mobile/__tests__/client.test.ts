import MockAdapter from 'axios-mock-adapter';
import axios from 'axios';
import { api, ApiError, getTokens, setAdapter, setLogoutHandler, setTokens } from '../src/api/client';
import { tokenStorage } from '../src/auth/tokenStorage';

jest.mock('../src/config/tenant', () => ({ getApiBaseUrl: () => 'http://test/api/v1' }));

let mock: MockAdapter;
beforeEach(() => {
  mock = new MockAdapter(axios);
  setAdapter(mock.adapter());
  setTokens({ accessToken: 'old', refreshToken: 'r1' });
});
afterEach(() => {
  setLogoutHandler(null);
  setAdapter(undefined);
});

describe('api client', () => {
  it('attaches the bearer token', async () => {
    mock.onGet('/auth/me').reply((cfg) => [200, { auth: cfg.headers?.Authorization }]);
    const res = await api.get('/auth/me');
    expect(res.data.auth).toBe('Bearer old');
  });

  it('refreshes once on 401 (single-flight across concurrent calls) and retries', async () => {
    mock.onGet('/a').reply((cfg) => (cfg.headers?.Authorization === 'Bearer new' ? [200, 'a-ok'] : [401, {}]));
    mock.onGet('/b').reply((cfg) => (cfg.headers?.Authorization === 'Bearer new' ? [200, 'b-ok'] : [401, {}]));
    let refreshCalls = 0;
    mock.onPost('/auth/refresh').reply((cfg) => {
      refreshCalls++;
      expect(JSON.parse(cfg.data)).toEqual({ refresh_token: 'r1' });
      return [200, { access_token: 'new', refresh_token: 'r2', token_type: 'bearer' }];
    });
    const [a, b] = await Promise.all([api.get('/a'), api.get('/b')]);
    expect([a.data, b.data]).toEqual(['a-ok', 'b-ok']);
    expect(refreshCalls).toBe(1);
    expect(getTokens()).toEqual({ accessToken: 'new', refreshToken: 'r2' });
    expect(await tokenStorage.load()).toEqual({ accessToken: 'new', refreshToken: 'r2' });
  });

  it('logs out and rejects with ApiError when refresh fails', async () => {
    const onLogout = jest.fn();
    setLogoutHandler(onLogout);
    mock.onGet('/a').reply(401, { error: { code: 'expired', message: 'Token expired' } });
    mock.onPost('/auth/refresh').reply(401, { detail: 'bad refresh' });
    await expect(api.get('/a')).rejects.toMatchObject({ name: 'ApiError', status: 401 });
    expect(onLogout).toHaveBeenCalledTimes(1);
    expect(getTokens()).toBeNull();
    expect(await tokenStorage.load()).toBeNull();
  });

  it('retries only once when the retried request is still 401', async () => {
    mock.onGet('/a').reply(401, {});
    mock.onPost('/auth/refresh').reply(200, { access_token: 'new', refresh_token: 'r2' });
    await expect(api.get('/a')).rejects.toBeInstanceOf(ApiError);
    expect(mock.history.get.length).toBe(2);
    expect(mock.history.post.length).toBe(1);
  });

  it('does not try to refresh on login failure', async () => {
    mock.onPost('/auth/login').reply(401, { detail: 'Incorrect email or password' });
    await expect(api.post('/auth/login', 'x')).rejects.toMatchObject({ message: 'Incorrect email or password' });
    expect(mock.history.post.some((r) => r.url === '/auth/refresh')).toBe(false);
  });
});
