/* eslint-disable import/no-named-as-default-member */
import axios, { type AxiosAdapter, type AxiosError, type InternalAxiosRequestConfig } from 'axios';
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

export const api = axios.create({ timeout: 20000, headers: { Accept: 'application/json' } });
/** Separate bare instance for /auth/refresh so it never re-enters the 401 interceptor. */
const refreshClient = axios.create({ timeout: 20000 });

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
  if (!tokens?.refreshToken) throw new ApiError('Session expired', 401, 'no_refresh_token');
  const res = await refreshClient.post<{ access_token: string; refresh_token?: string }>(
    '/auth/refresh',
    { refresh_token: tokens.refreshToken },
    { baseURL: getApiBaseUrl() },
  );
  const next: Tokens = {
    accessToken: res.data.access_token,
    refreshToken: res.data.refresh_token ?? tokens.refreshToken,
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

async function forceLogout() {
  tokens = null;
  await tokenStorage.clear().catch(() => undefined);
  onLogout?.();
}

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
    let access: string;
    try {
      access = await refreshAccessToken();
    } catch (e) {
      const refreshErr = normalizeError(e);
      // A network failure during refresh is not proof the session is dead; keep the tokens.
      if (refreshErr.status !== 0) await forceLogout();
      throw refreshErr.status === 0 ? refreshErr : normalizeError(error);
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
