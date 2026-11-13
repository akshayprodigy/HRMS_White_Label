import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { fetchMe, loginRequest, setLogoutHandler, setTokens, type Me } from '../api/client';
import { tokenStorage } from './tokenStorage';

type AuthState = {
  user: Me | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
};

const AuthContext = createContext<AuthState | null>(null);

/** Hook point: Task 10 registers push-token unregistration here (runs before tokens are cleared). */
const beforeLogoutHooks: (() => Promise<void> | void)[] = [];
export function onBeforeLogout(fn: () => Promise<void> | void) {
  beforeLogoutHooks.push(fn);
  return () => {
    const i = beforeLogoutHooks.indexOf(fn);
    if (i >= 0) beforeLogoutHooks.splice(i, 1);
  };
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);

  const clearSession = useCallback(async () => {
    setTokens(null);
    await tokenStorage.clear().catch(() => undefined);
    setUser(null);
  }, []);

  const logout = useCallback(async () => {
    for (const fn of [...beforeLogoutHooks]) {
      try {
        await fn();
      } catch {
        /* best effort */
      }
    }
    await clearSession();
  }, [clearSession]);

  useEffect(() => {
    // Refresh failure inside the API client lands here.
    setLogoutHandler(() => setUser(null));
    let alive = true;
    (async () => {
      try {
        const stored = await tokenStorage.load();
        if (stored) {
          setTokens(stored);
          const me = await fetchMe();
          if (alive) setUser(me);
        }
      } catch {
        if (alive) setUser(null);
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => {
      alive = false;
      setLogoutHandler(null);
    };
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    const res = await loginRequest(username.trim(), password);
    const tokens = { accessToken: res.access_token, refreshToken: res.refresh_token };
    setTokens(tokens);
    try {
      const me = await fetchMe();
      await tokenStorage.save(tokens);
      setUser(me);
    } catch (e) {
      setTokens(null);
      throw e;
    }
  }, []);

  const value = useMemo(() => ({ user, loading, login, logout }), [user, loading, login, logout]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>');
  return ctx;
}
