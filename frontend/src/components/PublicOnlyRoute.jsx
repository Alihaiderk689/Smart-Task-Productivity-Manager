import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { getAuthedRedirectDestination } from '@/lib/authRedirect';

// Reverse of ProtectedRoute -- keeps an already-authenticated user off the
// login/register pages (a stale tab, a bookmark, hitting back after
// signing in) by bouncing them straight back into the app instead of
// showing the form again. By the time this renders, AuthenticatedApp (see
// App.jsx) has already resolved isLoadingAuth, so isAuthenticated is
// reliable here without needing its own loading state.
export default function PublicOnlyRoute() {
  const { isAuthenticated, user } = useAuth();
  const location = useLocation();

  if (isAuthenticated) {
    return <Navigate to={getAuthedRedirectDestination(location, Boolean(user?.is_staff))} replace />;
  }

  return <Outlet />;
}
