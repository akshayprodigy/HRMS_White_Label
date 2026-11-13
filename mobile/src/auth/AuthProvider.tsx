import { useQueryClient } from '@tanstack/react-query';
import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { fetchMe, loginRequest, normalizeError, setLogoutHandler, setTokens, type Me } from '../api/client';
import { tokenStorage } from './tokenStorage';

export type AuthState = {
  user: Me | null;
  loading: boolean;
  /** True when the session was restored from cache because the server could not be reached. */
  unverified: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  /** Re-validate a restored (unverified) session against the server. */
  verify: () => Promise<void>;
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
  const queryClient = useQueryClient();
  const [user, setUser] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);
  const [unverified, setUnverified] = useState(false);

  /** The single teardown path for both user logout and forced (refresh-failed) logout. */
  const clearSession = useCallback(async () => {
    setTokens(null);
    await tokenStorage.clear().catch(() => undefined);
    queryClient.clear();
    setUser(null);
    setUnverified(false);
  }, [queryClient]);

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

  const verify = useCallback(async () => {
    const me = await fetchMe();
    await tokenStorage.saveMe(me);
    setUser(me);
    setUnverified(false);
  }, []);

  useEffect(() => {
    setLogoutHandler(() => {
      void clearSession();
    });
    let alive = true;
    (async () => {
      try {
        const stored = await tokenStorage.load();
        if (!stored) return;
        setTokens(stored);
        try {
          const me = await fetchMe();
          await tokenStorage.saveMe(me);
          if (alive) setUser(me);
        } catch (e) {
          const err = normalizeError(e);
          if (err.status === 401 || err.status === 403) {
            await clearSession(); // refresh already failed: session is dead
          } else {
            // Offline / server trouble: keep tokens, restore the cached profile as unverified.
            const cached = await tokenStorage.loadMe<Me>();
            if (alive && cached) {
              setUser(cached);
              setUnverified(true);
            }
          }
        }
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => {
      alive = false;
      setLogoutHandler(null);
    };
  }, [clearSession]);

  const login = useCallback(async (username: string, password: string) => {
    const res = await loginRequest(username.trim(), password);
    const tokens = { accessToken: res.access_token, refreshToken: res.refresh_token };
    setTokens(tokens);
    try {
      const me = await fetchMe();
      await tokenStorage.save(tokens);
      await tokenStorage.saveMe(me);
      setUser(me);
      setUnverified(false);
    } catch (e) {
      setTokens(null);
      throw e;
    }
  }, []);

  const value = useMemo(
    () => ({ user, loading, unverified, login, logout, verify }),
    [user, loading, unverified, login, logout, verify],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>');
  return ctx;
}
