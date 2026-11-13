import MockAdapter from 'axios-mock-adapter';
import axios from 'axios';
import { api, ApiError, loginRequest, getTokens, setAdapter, setLogoutHandler, setTokens } from '../src/api/client';
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

  it('keeps tokens and does not log out when refresh fails with network/5xx', async () => {
    const onLogout = jest.fn();
    setLogoutHandler(onLogout);
    mock.onGet('/a').reply(401, {});
    mock.onPost('/auth/refresh').replyOnce(503, {}).onPost('/auth/refresh').networkErrorOnce();
    await expect(api.get('/a')).rejects.toMatchObject({ status: 503 });
    await expect(api.get('/a')).rejects.toMatchObject({ status: 0, code: 'network_error' });
    expect(onLogout).not.toHaveBeenCalled();
    expect(getTokens()).toEqual({ accessToken: 'old', refreshToken: 'r1' });
  });

  it.each([400, 403])('logs out when refresh fails with %i', async (status) => {
    const onLogout = jest.fn();
    setLogoutHandler(onLogout);
    mock.onGet('/a').reply(401, {});
    mock.onPost('/auth/refresh').reply(status, {});
    await expect(api.get('/a')).rejects.toMatchObject({ status: 401 });
    expect(onLogout).toHaveBeenCalledTimes(1);
  });

  it('does not resurrect the session when logout happens during an in-flight refresh', async () => {
    mock.onGet('/a').reply(401, {});
    let release!: () => void;
    const gate = new Promise<void>((r) => (release = r));
    mock.onPost('/auth/refresh').reply(async () => {
      await gate;
      return [200, { access_token: 'new', refresh_token: 'r2' }];
    });
    const pending = api.get('/a');
    await new Promise((r) => setTimeout(r, 10));
    setTokens(null); // user logged out
    release();
    await expect(pending).rejects.toMatchObject({ status: 401, code: 'session_changed', message: 'Session changed' });
    expect(getTokens()).toBeNull();
    expect(await tokenStorage.load()).toBeNull();
  });

  it('retries a late 401 (sent with a rotated token) with the current token, no refresh', async () => {
    let release!: () => void;
    const gate = new Promise<void>((r) => (release = r));
    mock.onGet('/a').reply(async (cfg) => {
      if (cfg.headers?.Authorization === 'Bearer current') return [200, 'ok'];
      await gate; // response arrives after the token was rotated
      return [401, {}];
    });
    mock.onPost('/auth/refresh').reply(500);
    const pending = api.get('/a');
    await new Promise((r) => setTimeout(r, 10));
    expect(mock.history.get[0].headers?.Authorization).toBe('Bearer old');
    setTokens({ accessToken: 'current', refreshToken: 'r9' });
    release();
    expect((await pending).data).toBe('ok');
    expect(mock.history.post.length).toBe(0);
  });

  it('logs in with form-urlencoded username/password (not JSON)', async () => {
    mock.onPost('/auth/login').reply((cfg) => {
      expect(cfg.headers?.['Content-Type']).toBe('application/x-www-form-urlencoded');
      expect(cfg.data).toBe('username=employee%40gmail.com&password=test%4012345');
      return [200, { access_token: 'a', refresh_token: 'r', token_type: 'bearer' }];
    });
    expect((await loginRequest('employee@gmail.com', 'test@12345')).access_token).toBe('a');
  });

  it('does not try to refresh on login failure', async () => {
    mock.onPost('/auth/login').reply(401, { detail: 'Incorrect email or password' });
    await expect(api.post('/auth/login', 'x')).rejects.toMatchObject({ message: 'Incorrect email or password' });
    expect(mock.history.post.some((r) => r.url === '/auth/refresh')).toBe(false);
  });
});
