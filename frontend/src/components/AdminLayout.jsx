import { Outlet, Link, useLocation, useNavigate } from 'react-router-dom';
import { ShieldCheck, LogOut, LayoutDashboard, ListChecks, UserCog, Bot, FlaskConical } from 'lucide-react';
import { base44 } from '../api/base44Client';
import ThemeToggle from './theme-toggle';
import { cn } from '@/lib/utils';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger, DropdownMenuSeparator } from '@/components/ui/dropdown-menu';
import logo from '../assets/logo.png';

// Deliberately separate from Layout.jsx -- an admin account never sees the
// regular task/category navigation (RoleRoute keeps it off those routes
// entirely), so this only ever needs a small nav of its own admin pages.
// Profile lives in the dropdown below, not as its own tab here.
const NAV_ITEMS = [
  { label: 'Overview', path: '/admin', icon: LayoutDashboard, exact: true },
  { label: 'Tasks', path: '/admin/tasks', icon: ListChecks },
  { label: 'Copilot', path: '/admin/copilot', icon: Bot },
  { label: 'Evaluation', path: '/admin/evaluation', icon: FlaskConical },
];

export default function AdminLayout() {
  const location = useLocation();
  const navigate = useNavigate();
  const profileActive = location.pathname.startsWith('/admin/profile');

  const handleLogout = async () => {
    await base44.auth.logout('/login');
  };

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950">
      <header className="sticky top-0 z-30 bg-white/80 dark:bg-slate-900/80 backdrop-blur-md border-b border-slate-200 dark:border-slate-800 px-4 sm:px-6 h-16 flex items-center justify-between gap-4">
        <Link to="/admin" className="flex items-center gap-2.5 min-w-0 shrink-0">
          <img src={logo} alt="TaskFlow" className="w-9 h-9 shrink-0 object-contain" />
          <span className="font-bold text-lg text-slate-900 dark:text-slate-100 truncate">TaskFlow</span>
          <span className="hidden sm:flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-indigo-50 dark:bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 shrink-0">
            <ShieldCheck className="w-3 h-3" /> Admin
          </span>
        </Link>

        <nav className="hidden md:flex items-center gap-1">
          {NAV_ITEMS.map((item) => {
            const active = item.exact ? location.pathname === item.path : location.pathname.startsWith(item.path);
            const Icon = item.icon;
            return (
              <Link
                key={item.path}
                to={item.path}
                className={cn(
                  'flex items-center gap-2 px-3 py-2 rounded-xl text-sm font-medium transition-colors',
                  active ? 'bg-indigo-50 dark:bg-indigo-500/10 text-indigo-600 dark:text-indigo-400' : 'text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800'
                )}
              >
                <Icon className="w-4 h-4" /> {item.label}
              </Link>
            );
          })}
        </nav>

        <div className="flex items-center gap-2 sm:gap-3 shrink-0">
          <DropdownMenu>
            <DropdownMenuTrigger
              className={cn(
                'flex items-center gap-2 px-3 py-2 rounded-xl text-sm font-medium transition-colors outline-none',
                profileActive ? 'bg-indigo-50 dark:bg-indigo-500/10 text-indigo-600 dark:text-indigo-400' : 'text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800'
              )}
            >
              <UserCog className="w-4 h-4" /> Profile
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-52">
              <DropdownMenuItem onClick={() => navigate('/admin/profile')} className="cursor-pointer">
                <UserCog className="w-4 h-4 mr-2" /> View Profile
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <div className="flex items-center justify-between px-2 py-1.5">
                <span className="text-sm text-slate-600 dark:text-slate-300">Theme</span>
                <ThemeToggle />
              </div>
            </DropdownMenuContent>
          </DropdownMenu>

          <button
            onClick={handleLogout}
            className="flex items-center gap-2 px-3 py-2 text-sm font-medium text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-xl transition-colors"
          >
            <LogOut className="w-4 h-4" />
            <span className="hidden sm:inline">Logout</span>
          </button>
        </div>
      </header>

      {/* Mobile nav (below md) -- the header's nav is hidden there for space */}
      <nav className="md:hidden flex items-center gap-1 px-4 py-2 border-b border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 overflow-x-auto">
        {NAV_ITEMS.map((item) => {
          const active = item.exact ? location.pathname === item.path : location.pathname.startsWith(item.path);
          const Icon = item.icon;
          return (
            <Link
              key={item.path}
              to={item.path}
              className={cn(
                'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium whitespace-nowrap transition-colors',
                active ? 'bg-indigo-50 dark:bg-indigo-500/10 text-indigo-600 dark:text-indigo-400' : 'text-slate-600 dark:text-slate-300'
              )}
            >
              <Icon className="w-3.5 h-3.5" /> {item.label}
            </Link>
          );
        })}
      </nav>

      <main>
        <Outlet />
      </main>
    </div>
  );
}
