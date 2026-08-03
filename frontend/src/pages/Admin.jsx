import { useState, useEffect, useCallback } from 'react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Cell } from 'recharts';
import { toast } from 'sonner';
import {
  Users, UserCheck, UserX, UserPlus, ListTodo, Tags, Search, Trash2, X,
  AlertTriangle, Download, Database, Server, Activity, RefreshCw, TrendingUp, TrendingDown,
} from 'lucide-react';
import { useAuth } from '@/context/AuthContext';
import { useTheme } from '@/context/ThemeContext';
import { adminApi } from '@/services/api';
import { statusConfig } from '@/lib/taskUtils';
import { cn } from '@/lib/utils';
import StatCard from '@/components/statcard';
import CopilotQueryBox from '@/components/CopilotQueryBox';
import {
  AlertDialog, AlertDialogContent, AlertDialogHeader, AlertDialogTitle,
  AlertDialogDescription, AlertDialogFooter, AlertDialogCancel, AlertDialogAction,
} from '@/components/ui/alert-dialog';

// Matches the dot/badge colors statusConfig already uses elsewhere in the
// app (taskcard.jsx, Calendar.jsx) -- the chart should agree with every
// other place a task's status is shown, not invent its own palette.
const STATUS_BAR_COLOR = {
  Pending: '#f59e0b',
  'In Progress': '#3b82f6',
  Paused: '#f97316',
  Completed: '#10b981',
  Stopped: '#ef4444',
  Missed: '#64748b',
};
const STATUS_ORDER = ['Pending', 'In Progress', 'Paused', 'Completed', 'Stopped', 'Missed'];

function formatDate(dateStr) {
  if (!dateStr) return '—';
  return new Date(dateStr).toLocaleDateString('en', { month: 'short', day: 'numeric', year: 'numeric' });
}

function TrendBadge({ current, previous }) {
  const diff = current - previous;
  if (diff === 0) return <span className="text-xs text-slate-400">No change vs. prior 7 days</span>;
  const up = diff > 0;
  const Icon = up ? TrendingUp : TrendingDown;
  return (
    <span className={cn('inline-flex items-center gap-1 text-xs font-medium', up ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-600 dark:text-red-400')}>
      <Icon className="w-3 h-3" /> {up ? '+' : ''}{diff} vs. prior 7 days
    </span>
  );
}

function StatusDot({ ok }) {
  return <span className={cn('w-2 h-2 rounded-full shrink-0', ok ? 'bg-emerald-500' : 'bg-red-500')} />;
}

export default function Admin() {
  const { user } = useAuth();
  const { isDark } = useTheme();

  const [overview, setOverview] = useState(null);
  const [users, setUsers] = useState([]);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [actionUserId, setActionUserId] = useState(null);

  const [taskDrawerUser, setTaskDrawerUser] = useState(null);
  const [userTasks, setUserTasks] = useState([]);
  const [tasksLoading, setTasksLoading] = useState(false);
  const [deleteTaskTarget, setDeleteTaskTarget] = useState(null);
  const [deleteUserTarget, setDeleteUserTarget] = useState(null);

  const [systemStatus, setSystemStatus] = useState(null);
  const [statusLoading, setStatusLoading] = useState(true);

  const loadOverview = useCallback(async () => {
    const { data } = await adminApi.overview();
    setOverview(data);
  }, []);

  const loadUsers = useCallback(async (searchTerm) => {
    const { data } = await adminApi.users(searchTerm ? { search: searchTerm } : undefined);
    setUsers(data);
  }, []);

  const loadSystemStatus = useCallback(async () => {
    setStatusLoading(true);
    try {
      const { data } = await adminApi.systemStatus();
      setSystemStatus(data);
    } catch {
      setSystemStatus(null);
    } finally {
      setStatusLoading(false);
    }
  }, []);

  useEffect(() => {
    Promise.all([loadOverview(), loadUsers(), loadSystemStatus()]).finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Debounced live search -- no need to wait for a form submit.
  useEffect(() => {
    const timer = setTimeout(() => { loadUsers(search); }, 300);
    return () => clearTimeout(timer);
  }, [search, loadUsers]);

  const toggleActive = async (target) => {
    setActionUserId(target.id);
    try {
      if (target.is_active) {
        await adminApi.deactivateUser(target.id);
        toast.success(`${target.email} deactivated`);
      } else {
        await adminApi.activateUser(target.id);
        toast.success(`${target.email} activated`);
      }
      await loadUsers(search);
    } catch (err) {
      toast.error(err.response?.data?.error || 'Failed to update user');
    } finally {
      setActionUserId(null);
    }
  };

  const handleDeleteUser = async () => {
    if (!deleteUserTarget) return;
    try {
      await adminApi.deleteUser(deleteUserTarget.id);
      toast.success(`${deleteUserTarget.email} deleted`);
      loadUsers(search);
      loadOverview();
    } catch (err) {
      toast.error(err.response?.data?.error || 'Failed to delete user');
    } finally {
      setDeleteUserTarget(null);
    }
  };

  const openUserTasks = async (target) => {
    setTaskDrawerUser(target);
    setTasksLoading(true);
    try {
      const { data } = await adminApi.userTasks(target.id);
      setUserTasks(data);
    } catch {
      toast.error('Failed to load tasks');
      setUserTasks([]);
    } finally {
      setTasksLoading(false);
    }
  };

  const handleDeleteTask = async () => {
    if (!deleteTaskTarget) return;
    try {
      await adminApi.deleteTask(deleteTaskTarget.id);
      setUserTasks((prev) => prev.filter((t) => t.id !== deleteTaskTarget.id));
      toast.success('Task deleted');
      loadOverview();
      loadUsers(search);
    } catch {
      toast.error('Failed to delete task');
    } finally {
      setDeleteTaskTarget(null);
    }
  };

  const handleDownload = async (kind) => {
    try {
      await adminApi.downloadReport(kind);
    } catch {
      toast.error('Failed to download report');
    }
  };

  const chartData = STATUS_ORDER.map((status) => ({
    status,
    count: overview?.tasks_by_status?.[status] || 0,
  }));

  const chartGridColor = isDark ? '#1e293b' : '#f1f5f9';
  const chartTickColor = isDark ? '#64748b' : '#94a3b8';
  const chartTooltipStyle = {
    borderRadius: '12px',
    border: `1px solid ${isDark ? '#1e293b' : '#f1f5f9'}`,
    fontSize: '13px',
    background: isDark ? '#0f172a' : '#ffffff',
    color: isDark ? '#f1f5f9' : '#0f172a',
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="w-8 h-8 border-4 border-slate-200 dark:border-slate-800 border-t-indigo-600 rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="p-6 lg:p-8 max-w-7xl mx-auto">
      <div className="flex items-start justify-between gap-4 mb-6 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">Admin Dashboard</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">Users, their tasks, and overall activity.</p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => handleDownload('users')} className="flex items-center gap-2 px-3 py-2 rounded-xl text-sm font-medium bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors">
            <Download className="w-4 h-4" /> Users CSV
          </button>
          <button onClick={() => handleDownload('tasks')} className="flex items-center gap-2 px-3 py-2 rounded-xl text-sm font-medium bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors">
            <Download className="w-4 h-4" /> Tasks CSV
          </button>
        </div>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 xl:grid-cols-7 gap-4 mb-6">
        <StatCard icon={Users} label="Total Users" value={overview.total_users} color="bg-indigo-500" />
        <StatCard icon={UserCheck} label="Active" value={overview.active_users} color="bg-emerald-500" />
        <StatCard icon={UserX} label="Inactive" value={overview.inactive_users} color="bg-slate-400" />
        <StatCard icon={UserPlus} label="New (7d)" value={overview.new_users_last_7_days} color="bg-blue-500" />
        <StatCard icon={ListTodo} label="Total Tasks" value={overview.total_tasks} color="bg-purple-500" />
        <StatCard icon={AlertTriangle} label="Overdue" value={overview.overdue_tasks} color="bg-red-500" />
        <StatCard icon={Tags} label="Categories" value={overview.total_categories} color="bg-amber-500" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
        <div className="bg-white dark:bg-slate-900 rounded-2xl p-5 border border-slate-100 dark:border-slate-800 shadow-sm">
          <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300 mb-1">New Users, Week over Week</h2>
          <div className="flex items-baseline gap-3 mt-2">
            <span className="text-2xl font-bold text-slate-900 dark:text-slate-100">{overview.new_users_last_7_days}</span>
            <TrendBadge current={overview.new_users_last_7_days} previous={overview.new_users_previous_7_days} />
          </div>
          <p className="text-xs text-slate-400 mt-1">Prior 7 days: {overview.new_users_previous_7_days}</p>
        </div>
        <div className="bg-white dark:bg-slate-900 rounded-2xl p-5 border border-slate-100 dark:border-slate-800 shadow-sm">
          <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300 mb-1">Tasks Completed, Week over Week</h2>
          <div className="flex items-baseline gap-3 mt-2">
            <span className="text-2xl font-bold text-slate-900 dark:text-slate-100">{overview.tasks_completed_last_7_days}</span>
            <TrendBadge current={overview.tasks_completed_last_7_days} previous={overview.tasks_completed_previous_7_days} />
          </div>
          <p className="text-xs text-slate-400 mt-1">Prior 7 days: {overview.tasks_completed_previous_7_days}</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6">
        <div className="lg:col-span-2 bg-white dark:bg-slate-900 rounded-2xl p-5 border border-slate-100 dark:border-slate-800 shadow-sm">
          <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300 mb-4">Tasks by Status</h2>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={chartData} layout="vertical" margin={{ left: 8, right: 16 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={chartGridColor} horizontal={false} />
              <XAxis type="number" allowDecimals={false} tick={{ fill: chartTickColor, fontSize: 12 }} axisLine={false} tickLine={false} />
              <YAxis type="category" dataKey="status" tick={{ fill: chartTickColor, fontSize: 12 }} axisLine={false} tickLine={false} width={80} />
              <Tooltip contentStyle={chartTooltipStyle} cursor={{ fill: isDark ? 'rgba(255,255,255,0.04)' : 'rgba(0,0,0,0.03)' }} />
              <Bar dataKey="count" radius={[0, 4, 4, 0]} maxBarSize={22}>
                {chartData.map((entry) => (
                  <Cell key={entry.status} fill={STATUS_BAR_COLOR[entry.status]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="bg-white dark:bg-slate-900 rounded-2xl p-5 border border-slate-100 dark:border-slate-800 shadow-sm">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300">System Status</h2>
            <button onClick={loadSystemStatus} disabled={statusLoading} className="p-1.5 rounded-lg text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 dark:hover:bg-indigo-500/10 transition-colors disabled:opacity-50" aria-label="Refresh status">
              <RefreshCw className={cn('w-3.5 h-3.5', statusLoading && 'animate-spin')} />
            </button>
          </div>
          {systemStatus ? (
            <div className="space-y-3 text-sm">
              <div className="flex items-center justify-between">
                <span className="flex items-center gap-2 text-slate-600 dark:text-slate-300"><Activity className="w-4 h-4" /> API</span>
                <span className="flex items-center gap-1.5"><StatusDot ok={systemStatus.api.ok} /> {systemStatus.api.ok ? 'Online' : 'Offline'}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="flex items-center gap-2 text-slate-600 dark:text-slate-300"><Database className="w-4 h-4" /> Database</span>
                <span className="flex items-center gap-1.5"><StatusDot ok={systemStatus.database.ok} /> {systemStatus.database.ok ? 'Connected' : 'Down'}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="flex items-center gap-2 text-slate-600 dark:text-slate-300"><Server className="w-4 h-4" /> Redis</span>
                <span className="flex items-center gap-1.5"><StatusDot ok={systemStatus.redis.ok} /> {systemStatus.redis.ok ? 'Connected' : 'Down'}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="flex items-center gap-2 text-slate-600 dark:text-slate-300"><Users className="w-4 h-4" /> Celery Workers</span>
                <span className="flex items-center gap-1.5"><StatusDot ok={systemStatus.celery.ok} /> {systemStatus.celery.workers.length} online</span>
              </div>
              {systemStatus.celery.workers.length > 0 && (
                <p className="text-xs text-slate-400 truncate" title={systemStatus.celery.workers.join(', ')}>{systemStatus.celery.workers.join(', ')}</p>
              )}
            </div>
          ) : (
            <p className="text-sm text-slate-400">Unable to load system status.</p>
          )}
        </div>
      </div>

      <CopilotQueryBox
        sessionId="admin-dashboard"
        title="Ask the Copilot"
        placeholder="e.g. How many tasks are overdue right now?"
        emptyHint="Ask anything about your users or tasks -- the copilot queries the live database and answers only from what it finds there."
        className="mb-6"
      />

      <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-100 dark:border-slate-800 shadow-sm overflow-hidden">
        <div className="p-4 border-b border-slate-100 dark:border-slate-800">
          <div className="relative max-w-sm">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search by name or email..."
              className="w-full pl-10 pr-4 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-900 dark:text-slate-100 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400"
            />
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-slate-500 dark:text-slate-400 uppercase tracking-wide border-b border-slate-100 dark:border-slate-800">
                <th className="px-4 py-3 font-medium">User</th>
                <th className="px-4 py-3 font-medium">Joined</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">Tasks</th>
                <th className="px-4 py-3 font-medium text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {users.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-4 py-10 text-center text-slate-400">No users found.</td>
                </tr>
              ) : (
                users.map((row) => (
                  <tr key={row.id} className="border-b border-slate-50 dark:border-slate-800/60 last:border-0">
                    <td className="px-4 py-3">
                      <p className="font-medium text-slate-900 dark:text-slate-100">{row.first_name || '—'}</p>
                      <p className="text-xs text-slate-400">{row.email}</p>
                    </td>
                    <td className="px-4 py-3 text-slate-500 dark:text-slate-400">{formatDate(row.date_joined)}</td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${row.is_active ? 'bg-emerald-100 dark:bg-emerald-500/10 text-emerald-700 dark:text-emerald-400' : 'bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400'}`}>
                        <span className={`w-1.5 h-1.5 rounded-full ${row.is_active ? 'bg-emerald-500' : 'bg-slate-400'}`} />
                        {row.is_active ? 'Active' : 'Inactive'}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <button
                        onClick={() => openUserTasks(row)}
                        className="text-indigo-600 dark:text-indigo-400 hover:underline font-medium"
                      >
                        {row.task_count} {row.task_count === 1 ? 'task' : 'tasks'}
                      </button>
                    </td>
                    <td className="px-4 py-3 text-right">
                      {row.id === user.id ? (
                        <span className="text-xs text-slate-400">You</span>
                      ) : (
                        <div className="flex items-center justify-end gap-2">
                          <button
                            onClick={() => toggleActive(row)}
                            disabled={actionUserId === row.id}
                            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors disabled:opacity-50 ${row.is_active ? 'bg-red-50 dark:bg-red-500/10 text-red-600 dark:text-red-400 hover:bg-red-100 dark:hover:bg-red-500/20' : 'bg-emerald-50 dark:bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 hover:bg-emerald-100 dark:hover:bg-emerald-500/20'}`}
                          >
                            {actionUserId === row.id ? 'Working...' : row.is_active ? 'Deactivate' : 'Activate'}
                          </button>
                          <button
                            onClick={() => setDeleteUserTarget(row)}
                            className="p-1.5 rounded-lg text-slate-400 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-500/10 transition-colors"
                            aria-label={`Delete ${row.email}`}
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Per-user task list */}
      {taskDrawerUser && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/30" onClick={() => setTaskDrawerUser(null)}>
          <div
            className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-100 dark:border-slate-800 shadow-xl w-full max-w-2xl max-h-[80vh] overflow-hidden flex flex-col"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between p-5 border-b border-slate-100 dark:border-slate-800">
              <div>
                <h3 className="font-semibold text-slate-900 dark:text-slate-100">{taskDrawerUser.first_name || taskDrawerUser.email}</h3>
                <p className="text-xs text-slate-400">{taskDrawerUser.email}</p>
              </div>
              <button onClick={() => setTaskDrawerUser(null)} className="p-2 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-400">
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="overflow-y-auto p-5 space-y-2">
              {tasksLoading ? (
                <div className="flex justify-center py-10">
                  <div className="w-6 h-6 border-4 border-slate-200 dark:border-slate-800 border-t-indigo-600 rounded-full animate-spin" />
                </div>
              ) : userTasks.length === 0 ? (
                <p className="text-center text-sm text-slate-400 py-10">This user has no tasks.</p>
              ) : (
                userTasks.map((task) => {
                  const st = statusConfig[task.status] || statusConfig.Pending;
                  return (
                    <div key={task.id} className="flex items-center justify-between gap-3 p-3 rounded-xl border border-slate-100 dark:border-slate-800">
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-slate-900 dark:text-slate-100 truncate">{task.title}</p>
                        <div className="flex items-center gap-2 mt-1">
                          <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium ${st.badge}`}>
                            <span className={`w-1.5 h-1.5 rounded-full ${st.dot}`} />
                            {st.label}
                          </span>
                          {task.category_name && <span className="text-xs text-slate-400">{task.category_name}</span>}
                        </div>
                      </div>
                      <button
                        onClick={() => setDeleteTaskTarget(task)}
                        className="shrink-0 p-2 rounded-lg text-slate-400 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-500/10 transition-colors"
                        aria-label="Delete task"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </div>
      )}

      <AlertDialog open={!!deleteTaskTarget} onOpenChange={(open) => !open && setDeleteTaskTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete this task?</AlertDialogTitle>
            <AlertDialogDescription>This action cannot be undone. "{deleteTaskTarget?.title}" will be permanently deleted.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={handleDeleteTask} className="bg-red-600 hover:bg-red-700">Delete</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={!!deleteUserTarget} onOpenChange={(open) => !open && setDeleteUserTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete this user?</AlertDialogTitle>
            <AlertDialogDescription>
              This action cannot be undone. "{deleteUserTarget?.email}" and all {deleteUserTarget?.task_count ?? 0} of their tasks will be permanently deleted.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={handleDeleteUser} className="bg-red-600 hover:bg-red-700">Delete</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
