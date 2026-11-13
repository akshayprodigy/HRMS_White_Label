import { AuthRedirect } from '../src/components/AuthRedirect';

// Deep links to routes hidden by Stack.Protected (e.g. a tab while logged out) end up here.
export default function NotFound() {
  return <AuthRedirect />;
}
