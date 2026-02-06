import { createContext, useContext, useEffect, useMemo, useState } from 'react';

import type { AuthResponse, LoginRequest } from '../api/auth';
import * as authApi from '../api/auth';
import { clearAccessToken, getAccessToken, setAccessToken } from './token';

export type AuthState = {
  accessToken: string | null;
  userEmail: string | null;
  permissions: string[];
  loading: boolean;
};

type AuthContextValue = AuthState & {
  login: (req: LoginRequest) => Promise<void>;
  logout: () => Promise<void>;
  hasPermission: (perm: string) => boolean;
};

const AuthContext = createContext<AuthContextValue | null>(null);

function applyAuthResponse(
  resp: AuthResponse,
): Pick<AuthState, 'accessToken' | 'userEmail' | 'permissions'> {
  setAccessToken(resp.access_token);
  return {
    accessToken: resp.access_token,
    userEmail: resp.user.email,
    permissions: resp.permissions,
  };
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<AuthState>({
    accessToken: getAccessToken(),
    userEmail: null,
    permissions: [],
    loading: true,
  });

  useEffect(() => {
    let cancelled = false;

    (async () => {
      try {
        const resp = await authApi.refresh();
        if (cancelled) return;
        setState((prev: AuthState) => ({
          ...prev,
          ...applyAuthResponse(resp),
          loading: false,
        }));
      } catch {
        if (cancelled) return;
        clearAccessToken();
        setState((prev: AuthState) => ({
          ...prev,
          accessToken: null,
          userEmail: null,
          permissions: [],
          loading: false,
        }));
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  const value = useMemo<AuthContextValue>(() => {
    return {
      ...state,
      login: async (req: LoginRequest) => {
        const resp = await authApi.login(req);
        setState((prev: AuthState) => ({
          ...prev,
          ...applyAuthResponse(resp),
          loading: false,
        }));
      },
      logout: async () => {
        try {
          await authApi.logout();
        } finally {
          clearAccessToken();
          setState((prev: AuthState) => ({
            ...prev,
            accessToken: null,
            userEmail: null,
            permissions: [],
          }));
        }
      },
      hasPermission: (perm: string) => state.permissions.includes(perm),
    };
  }, [state]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
