import { ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router-dom';

import { useAuth } from '../auth/AuthContext';

export function ProtectedRoute({ children }: { children: ReactNode }) {
  const location = useLocation();
  const auth = useAuth();

  if (auth.loading) {
    return null;
  }

  if (!auth.accessToken) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }

  return <>{children}</>;
}
