import { lazy, Suspense } from 'react'
import { Toaster } from "./components/ui/sonner"
import { QueryClientProvider } from '@tanstack/react-query'
import { queryClientInstance } from './lib/query-client.jsx'
import { BrowserRouter as Router, Route, Routes } from 'react-router-dom';
import PageNotFound from './lib/PageNotFound';
import { AuthProvider, useAuth } from './context/AuthContext';
import { ThemeProvider } from './context/ThemeContext';
import ErrorBoundary from './components/ErrorBoundary';
import UserNotRegisteredError from './components/UserNotRegisteredError';
import ScrollToTop from './components/scrolltotop';
// Add page imports here
import Login from './pages/Login';
import Register from './pages/register';
import ForgotPassword from './pages/ForgotPassword';
import ResetPassword from './pages/Resetpassword';
import VerifyEmail from './pages/VerifyEmail';
import ProtectedRoute from './components/Protectedroute';
import PublicOnlyRoute from './components/PublicOnlyRoute';
import RoleRoute from './components/RoleRoute';
import Layout from './components/layout';
import AdminLayout from './components/AdminLayout';
import Home from './pages/Home';
import Tasks from './pages/Tasks';
import TaskDetail from './pages/TaskDetail';
import Categories from './pages/Categories';
import CalendarPage from './pages/Calendar';
import Profile from './pages/Profile';
// Admin/copilot pages are staff-only (RoleRoute allow="staff" below) and
// noticeably heavy (copilot chat UI, charts, evaluation dashboard) -- lazy
// loading them keeps that weight out of the bundle every regular user
// downloads, without changing behavior for either role.
const Admin = lazy(() => import('./pages/Admin'));
const AdminTasks = lazy(() => import('./pages/AdminTasks'));
const AdminProfile = lazy(() => import('./pages/AdminProfile'));
const AdminCopilot = lazy(() => import('./pages/AdminCopilot'));
const AdminEvaluation = lazy(() => import('./pages/AdminEvaluation'));

const RouteFallback = () => (
  <div className="fixed inset-0 flex items-center justify-center bg-background">
    <div className="w-8 h-8 border-4 border-muted border-t-foreground rounded-full animate-spin"></div>
  </div>
);

const AuthenticatedApp = () => {
  const { isLoadingAuth, isLoadingPublicSettings, authError, navigateToLogin } = useAuth();

  // Show loading spinner while checking app public settings or auth
  if (isLoadingPublicSettings || isLoadingAuth) {
    return (
      <div className="fixed inset-0 flex items-center justify-center bg-background">
        <div className="w-8 h-8 border-4 border-muted border-t-foreground rounded-full animate-spin"></div>
      </div>
    );
  }

  // Handle authentication errors
  if (authError) {
    if (authError.type === 'user_not_registered') {
      return <UserNotRegisteredError />;
    } else if (authError.type === 'auth_required') {
      // Redirect to login automatically
      navigateToLogin();
      return null;
    }
  }

  // Render the main app
  return (
    <Routes>
      <Route element={<PublicOnlyRoute />}>
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
      </Route>
      <Route path="/forgot-password" element={<ForgotPassword />} />
      <Route path="/reset-password" element={<ResetPassword />} />
      <Route path="/verify-email" element={<VerifyEmail />} />
      <Route element={<ProtectedRoute />}>
        <Route element={<RoleRoute allow="staff" />}>
          <Route element={<AdminLayout />}>
            <Route
              path="/admin"
              element={<Suspense fallback={<RouteFallback />}><Admin /></Suspense>}
            />
            <Route
              path="/admin/tasks"
              element={<Suspense fallback={<RouteFallback />}><AdminTasks /></Suspense>}
            />
            <Route
              path="/admin/copilot"
              element={<Suspense fallback={<RouteFallback />}><AdminCopilot /></Suspense>}
            />
            <Route
              path="/admin/evaluation"
              element={<Suspense fallback={<RouteFallback />}><AdminEvaluation /></Suspense>}
            />
            <Route
              path="/admin/profile"
              element={<Suspense fallback={<RouteFallback />}><AdminProfile /></Suspense>}
            />
          </Route>
        </Route>
        <Route element={<RoleRoute allow="user" />}>
          <Route element={<Layout />}>
            <Route path="/" element={<Home />} />
            <Route path="/tasks" element={<Tasks />} />
            <Route path="/tasks/:id" element={<TaskDetail />} />
            <Route path="/categories" element={<Categories />} />
            <Route path="/calendar" element={<CalendarPage />} />
            <Route path="/profile" element={<Profile />} />
          </Route>
        </Route>
      </Route>
      <Route path="*" element={<PageNotFound />} />
    </Routes>
  );
};


function App() {

  return (
    <ErrorBoundary>
      <ThemeProvider>
        <AuthProvider>
          <QueryClientProvider client={queryClientInstance}>
            <Router>
              <ScrollToTop />
              <AuthenticatedApp />
            </Router>
            <Toaster />
          </QueryClientProvider>
        </AuthProvider>
      </ThemeProvider>
    </ErrorBoundary>
  )
}

export default App