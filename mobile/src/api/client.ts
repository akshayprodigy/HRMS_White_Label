import { create as createAxios, type AxiosAdapter, type AxiosError, type InternalAxiosRequestConfig } from 'axios';
import { getApiBaseUrl } from '../config/tenant';
import { tokenStorage, type Tokens } from '../auth/tokenStorage';
import { ApiError, normalizeError } from './errors';

export { ApiError, normalizeError } from './errors';

type Retryable = InternalAxiosRequestConfig & { _retried?: boolean };

let tokens: Tokens | null = null;
let onLogout: (() => void) | null = null;
let refreshInFlight: Promise<string> | null = null;

export function setTokens(t: Tokens | null) {
  tokens = t;
}
export function getTokens() {
  return tokens;
}
/** AuthProvider registers this so a failed refresh logs the user out. */
export function setLogoutHandler(fn: (() => void) | null) {
  onLogout = fn;
}

export const api = createAxios({ timeout: 20000, headers: { Accept: 'application/json' } });
/** Separate bare instance for /auth/refresh so it never re-enters the 401 interceptor. */
const refreshClient = createAxios({ timeout: 20000 });

/** Test hook: route both instances through a mock adapter. */
export function setAdapter(adapter: AxiosAdapter | undefined) {
  api.defaults.adapter = adapter;
  refreshClient.defaults.adapter = adapter;
}

// Base URL is resolved per request so the Android emulator override applies at call time.
api.interceptors.request.use((config) => {
  if (!config.baseURL) config.baseURL = getApiBaseUrl();
  if (tokens?.accessToken && !config.headers.Authorization) {
    config.headers.Authorization = `Bearer ${tokens.accessToken}`;
  }
  return config;
});

async function doRefresh(): Promise<string> {
  const sent = tokens;
  if (!sent?.refreshToken) throw new ApiError('Session expired', 401, 'no_refresh_token');
  const res = await refreshClient.post<{ access_token: string; refresh_token?: string }>(
    '/auth/refresh',
    { refresh_token: sent.refreshToken },
    { baseURL: getApiBaseUrl() },
  );
  // Logout / re-login while the refresh was in flight must not resurrect the old session.
  if (!tokens || tokens.refreshToken !== sent.refreshToken) {
    throw new ApiError('Session changed', 401, 'session_changed');
  }
  const next: Tokens = {
    accessToken: res.data.access_token,
    refreshToken: res.data.refresh_token ?? sent.refreshToken,
  };
  tokens = next;
  await tokenStorage.save(next);
  return next.accessToken;
}

/** Single-flight: concurrent 401s share one refresh request. */
export function refreshAccessToken(): Promise<string> {
  if (!refreshInFlight) {
    refreshInFlight = doRefresh().finally(() => {
      refreshInFlight = null;
    });
  }
  return refreshInFlight;
}

/** Clears the in-memory + stored session and tells the AuthProvider (which also clears query cache). */
export async function forceLogout() {
  tokens = null;
  await tokenStorage.clear().catch(() => undefined);
  onLogout?.();
}

/** Refresh statuses that prove the refresh token is dead (vs. transient network/5xx failures). */
export const SESSION_DEAD = new Set([400, 401, 403]);

api.interceptors.response.use(
  (r) => r,
  async (error: AxiosError) => {
    const cfg = error.config as Retryable | undefined;
    const url = cfg?.url ?? '';
    const isAuthCall = url.includes('/auth/login') || url.includes('/auth/refresh');
    if (error.response?.status !== 401 || !cfg || cfg._retried || isAuthCall || !tokens) {
      throw normalizeError(error);
    }
    cfg._retried = true;

    // Late 401 for a request sent with an already-rotated token: retry with the current one.
    const sentAuth = cfg.headers.Authorization;
    if (sentAuth && sentAuth !== `Bearer ${tokens.accessToken}`) {
      cfg.headers.Authorization = `Bearer ${tokens.accessToken}`;
      return api.request(cfg);
    }

    let access: string;
    try {
      access = await refreshAccessToken();
    } catch (e) {
      const refreshErr = normalizeError(e);
      if (refreshErr.code === 'session_changed') throw refreshErr;
      if (SESSION_DEAD.has(refreshErr.status)) {
        await forceLogout();
        throw normalizeError(error);
      }
      throw refreshErr; // network / 5xx: keep tokens, let the caller retry later
    }
    cfg.headers.Authorization = `Bearer ${access}`;
    return api.request(cfg); // a second 401 propagates as a normalised ApiError (no further retry)
  },
);

export type LoginResult = { access_token: string; refresh_token: string; token_type: string };

export async function loginRequest(username: string, password: string): Promise<LoginResult> {
  const body = new URLSearchParams({ username, password }).toString();
  const res = await api.post<LoginResult>('/auth/login', body, {
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  });
  return res.data;
}

export type Me = { id: number; email: string; full_name?: string | null; is_superuser?: boolean; [k: string]: unknown };

export async function fetchMe(): Promise<Me> {
  const res = await api.get<Me>('/auth/me');
  return res.data;
}
