import { refresh } from './auth';
import { getAccessToken, setAccessToken } from '../auth/token';

export type ApiError = {
  status: number;
  message: string;
};

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const doFetch = async (): Promise<Response> => {
    const token = getAccessToken();
    return fetch(path, {
      ...init,
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(init?.headers ?? {}),
      },
    });
  };

  let resp = await doFetch();

  if (resp.status === 401) {
    try {
      const refreshed = await refresh();
      setAccessToken(refreshed.access_token);
      resp = await doFetch();
    } catch {
      // fall through and raise the original 401 below
    }
  }

  if (!resp.ok) {
    throw {
      status: resp.status,
      message: await resp.text(),
    } satisfies ApiError;
  }

  return (await resp.json()) as T;
}
