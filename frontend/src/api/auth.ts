export type AuthUser = {
  id: number;
  email: string;
};

export type AuthResponse = {
  access_token: string;
  expires_in: number;
  user: AuthUser;
  permissions: string[];
};

export type LoginRequest = {
  email: string;
  password: string;
};

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(path, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
    credentials: 'include',
  });

  if (!resp.ok) {
    throw new Error(await resp.text());
  }

  return (await resp.json()) as T;
}

export async function login(request: LoginRequest): Promise<AuthResponse> {
  return fetchJson<AuthResponse>('/api/v1/auth/login', {
    method: 'POST',
    body: JSON.stringify(request),
  });
}

export async function refresh(): Promise<AuthResponse> {
  return fetchJson<AuthResponse>('/api/v1/auth/refresh', {
    method: 'POST',
  });
}

export async function logout(): Promise<void> {
  await fetchJson('/api/v1/auth/logout', {
    method: 'POST',
  });
}
