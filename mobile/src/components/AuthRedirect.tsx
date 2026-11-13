import { Redirect, usePathname } from 'expo-router';
import { useAuth } from '../auth/AuthProvider';
import { decideRedirect, getPendingRoute, setPendingRoute } from '../auth/redirect';

/** Used by `/` and the not-found route so every entry point resolves by auth state. */
export function AuthRedirect({ path }: { path?: string }) {
  const { user } = useAuth();
  const current = usePathname();
  const d = decideRedirect({ loggedIn: !!user, path: path ?? current, pending: getPendingRoute() });
  setPendingRoute(d.pending);
  return <Redirect href={d.href as never} />;
}
