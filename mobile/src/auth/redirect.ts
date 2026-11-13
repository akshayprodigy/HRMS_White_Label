export const HOME = '/home';
export const LOGIN = '/login';

let pending: string | null = null;
export const getPendingRoute = () => pending;
export const setPendingRoute = (p: string | null) => {
  pending = p;
};

const isAuthPath = (p: string) => p === LOGIN || p.startsWith('/login/');
const isRoot = (p: string) => p === '' || p === '/';

/**
 * Where an unmatched / root route should go.
 * Logged out: login, remembering the intended deep link. Logged in: the remembered deep link, else home.
 */
export function decideRedirect(input: { loggedIn: boolean; path: string; pending: string | null }): {
  href: string;
  pending: string | null;
} {
  const { loggedIn, path, pending: prev } = input;
  if (!loggedIn) {
    const intended = !isRoot(path) && !isAuthPath(path) ? path : prev;
    return { href: LOGIN, pending: intended };
  }
  const target = prev && !isAuthPath(prev) ? prev : !isRoot(path) && !isAuthPath(path) && path !== '/+not-found' ? path : HOME;
  return { href: target, pending: null };
}
