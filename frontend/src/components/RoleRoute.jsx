import { Navigate, Outlet } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';

// Keeps the admin and regular-user areas of the app fully separate: a staff
// account can only ever reach /admin, and a regular account can never reach
// it. Sits inside ProtectedRoute, so `user` is already known to be loaded.
export default function RoleRoute({ allow }) {
  const { user } = useAuth();
  const isStaff = Boolean(user?.is_staff);

  if (allow === 'staff' && !isStaff) {
    return <Navigate to="/" replace />;
  }
  if (allow === 'user' && isStaff) {
    return <Navigate to="/admin" replace />;
  }

  return <Outlet />;
}
