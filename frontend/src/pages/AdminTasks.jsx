import { useState, useEffect, useCallback } from 'react';
import { toast } from 'sonner';
import { Search, Trash2, Pencil, Bell } from 'lucide-react';
import { adminApi } from '@/services/api';
import { statusConfig, priorityConfig } from '@/lib/taskUtils';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import {
  AlertDialog, AlertDialogContent, AlertDialogHeader, AlertDialogTitle,
  AlertDialogDescription, AlertDialogFooter, AlertDialogCancel, AlertDialogAction,
} from '@/components/ui/alert-dialog';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';

const STATUS_OPTIONS = ['Pending', 'In Progress', 'Paused', 'Completed', 'Stopped', 'Missed'];
const REMINDER_TYPES = [
  { type: '30min', label: '30 min', field: 'reminder_30_sent' },
  { type: '5min', label: '5 min', field: 'reminder_5_sent' },
  { type: 'progress', label: 'Progress', field: 'reminder_progress_sent' },
  { type: 'overdue', label: 'Overdue', field: 'reminder_overdue_sent' },
];

function toDatetimeLocal(isoString) {
  if (!isoString) return '';
  const date = new Date(isoString);
  const offsetMs = date.getTimezoneOffset() * 60000;
  return new Date(date.getTime() - offsetMs).toISOString().slice(0, 16);
}

function formatDateTime(isoString) {
  if (!isoString) return '—';
  return new Date(isoString).toLocaleString('en', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
}

export default function AdminTasks() {
  const [tasks, setTasks] = useState([]);
  const [categoryNames, setCategoryNames] = useState([]);
  const [loading, setLoading] = useState(true);

  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [categoryFilter, setCategoryFilter] = useState('all');
  const [overdueOnly, setOverdueOnly] = useState(false);

  const [editingTask, setEditingTask] = useState(null);
  const [editForm, setEditForm] = useState(null);
  const [saving, setSaving] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [reminderBusyKey, setReminderBusyKey] = useState(null);

  const loadTasks = useCallback(async () => {
    const params = {};
    if (search) params.search = search;
    if (statusFilter !== 'all') params.status = statusFilter;
    if (categoryFilter !== 'all') params.category_name = categoryFilter;
    if (overdueOnly) params.overdue = 'true';

    const { data } = await adminApi.tasks(params);
    setTasks(data);
  }, [search, statusFilter, categoryFilter, overdueOnly]);

  useEffect(() => {
    Promise.all([loadTasks(), adminApi.categoryNames().then((r) => setCategoryNames(r.data))]).finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => { loadTasks(); }, 300);
    return () => clearTimeout(timer);
  }, [loadTasks]);

  const openEdit = (task) => {
    setEditingTask(task);
    setEditForm({
      title: task.title,
      description: task.description || '',
      status: task.status,
      priority: task.priority,
      start_time: toDatetimeLocal(task.start_time),
      end_time: toDatetimeLocal(task.end_time),
    });
  };

  const handleSaveEdit = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      await adminApi.updateTask(editingTask.id, {
        title: editForm.title,
        description: editForm.description,
        status: editForm.status,
        priority: editForm.priority,
        start_time: new Date(editForm.start_time).toISOString(),
        end_time: new Date(editForm.end_time).toISOString(),
      });
      toast.success('Task updated');
      setEditingTask(null);
      loadTasks();
    } catch (err) {
      toast.error(err.response?.data?.detail || Object.values(err.response?.data || {})[0]?.[0] || 'Failed to update task');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    try {
      await adminApi.deleteTask(deleteTarget.id);
      toast.success('Task deleted');
      loadTasks();
    } catch {
      toast.error('Failed to delete task');
    } finally {
      setDeleteTarget(null);
    }
  };

  const handleTriggerReminder = async (task, reminderType) => {
    const key = `${task.id}-${reminderType}`;
    setReminderBusyKey(key);
    try {
      const { data } = await adminApi.triggerReminder(task.id, reminderType);
      if (data.sent) {
        toast.success(data.message);
      } else {
        toast.info(data.message);
      }
      loadTasks();
    } catch (err) {
      toast.error(err.response?.data?.error || 'Failed to trigger reminder');
    } finally {
      setReminderBusyKey(null);
    }
  };

  const hasActiveFilters = search || statusFilter !== 'all' || categoryFilter !== 'all' || overdueOnly;

  return (
    <div className="p-6 lg:p-8 max-w-7xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">All Tasks</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">Every task across every user.</p>
      </div>

      <div className="flex flex-col sm:flex-row gap-3 mb-4">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search title, description, or owner email..."
            className="w-full pl-10 pr-4 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-900 dark:text-slate-100 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400"
          />
        </div>
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className="px-4 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 text-sm bg-white dark:bg-slate-900 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400">
          <option value="all">All Statuses</option>
          {STATUS_OPTIONS.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <select value={categoryFilter} onChange={(e) => setCategoryFilter(e.target.value)} className="px-4 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 text-sm bg-white dark:bg-slate-900 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400">
          <option value="all">All Categories</option>
          {categoryNames.map((name) => <option key={name} value={name}>{name}</option>)}
        </select>
        <label className="flex items-center gap-2 px-4 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 text-sm bg-white dark:bg-slate-900 text-slate-700 dark:text-slate-300 cursor-pointer whitespace-nowrap">
          <input type="checkbox" checked={overdueOnly} onChange={(e) => setOverdueOnly(e.target.checked)} className="rounded" />
          Overdue only
        </label>
        {hasActiveFilters && (
          <button onClick={() => { setSearch(''); setStatusFilter('all'); setCategoryFilter('all'); setOverdueOnly(false); }} className="px-4 py-2.5 text-sm text-indigo-600 dark:text-indigo-400 hover:bg-indigo-50 dark:hover:bg-indigo-500/10 rounded-xl transition-colors">
            Clear all
          </button>
        )}
      </div>

      <p className="text-sm text-slate-500 dark:text-slate-400 mb-4">{tasks.length} {tasks.length === 1 ? 'task' : 'tasks'} found</p>

      <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-100 dark:border-slate-800 shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-slate-500 dark:text-slate-400 uppercase tracking-wide border-b border-slate-100 dark:border-slate-800">
                <th className="px-4 py-3 font-medium">Task</th>
                <th className="px-4 py-3 font-medium">Owner</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">Priority</th>
                <th className="px-4 py-3 font-medium">Window</th>
                <th className="px-4 py-3 font-medium">Reminders</th>
                <th className="px-4 py-3 font-medium text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={7} className="px-4 py-10 text-center text-slate-400">Loading...</td></tr>
              ) : tasks.length === 0 ? (
                <tr><td colSpan={7} className="px-4 py-10 text-center text-slate-400">No tasks found.</td></tr>
              ) : (
                tasks.map((task) => {
                  const st = statusConfig[task.status] || statusConfig.Pending;
                  const pr = priorityConfig[task.priority] || priorityConfig.Medium;
                  return (
                    <tr key={task.id} className="border-b border-slate-50 dark:border-slate-800/60 last:border-0 align-top">
                      <td className="px-4 py-3 max-w-[220px]">
                        <p className="font-medium text-slate-900 dark:text-slate-100 truncate">{task.title}</p>
                        {task.category_name && <p className="text-xs text-slate-400">{task.category_name}</p>}
                      </td>
                      <td className="px-4 py-3 text-slate-500 dark:text-slate-400 max-w-[180px] truncate">{task.user_email}</td>
                      <td className="px-4 py-3">
                        <span className={cn('inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium', st.badge)}>
                          <span className={cn('w-1.5 h-1.5 rounded-full', st.dot)} />
                          {st.label}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <span className={cn('px-2.5 py-1 rounded-full text-xs font-medium', pr.badge)}>{pr.label}</span>
                      </td>
                      <td className="px-4 py-3 text-xs text-slate-500 dark:text-slate-400 whitespace-nowrap">
                        {formatDateTime(task.start_time)} → {formatDateTime(task.end_time)}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-1 flex-wrap">
                          {REMINDER_TYPES.map((r) => {
                            const sent = task[r.field];
                            const key = `${task.id}-${r.type}`;
                            return (
                              <button
                                key={r.type}
                                onClick={() => handleTriggerReminder(task, r.type)}
                                disabled={reminderBusyKey === key}
                                title={sent ? `${r.label} reminder already sent -- click to re-check` : `${r.label} reminder not sent yet -- click to trigger now`}
                                className={cn(
                                  'flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium border transition-colors disabled:opacity-50',
                                  sent
                                    ? 'bg-emerald-50 dark:bg-emerald-500/10 border-emerald-200 dark:border-emerald-500/20 text-emerald-700 dark:text-emerald-400'
                                    : 'bg-slate-50 dark:bg-slate-800 border-slate-200 dark:border-slate-700 text-slate-500 dark:text-slate-400 hover:border-indigo-300'
                                )}
                              >
                                <Bell className="w-2.5 h-2.5" /> {r.label}
                              </button>
                            );
                          })}
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center justify-end gap-1">
                          <button onClick={() => openEdit(task)} className="p-2 rounded-lg text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 dark:hover:bg-indigo-500/10 transition-colors" aria-label="Edit task">
                            <Pencil className="w-4 h-4" />
                          </button>
                          <button onClick={() => setDeleteTarget(task)} className="p-2 rounded-lg text-slate-400 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-500/10 transition-colors" aria-label="Delete task">
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Edit task */}
      <Dialog open={!!editingTask} onOpenChange={(open) => !open && setEditingTask(null)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Edit Task</DialogTitle>
          </DialogHeader>
          {editForm && (
            <form onSubmit={handleSaveEdit} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="edit_title">Title</Label>
                <Input id="edit_title" value={editForm.title} onChange={(e) => setEditForm({ ...editForm, title: e.target.value })} required />
              </div>
              <div className="space-y-2">
                <Label htmlFor="edit_description">Description</Label>
                <Textarea id="edit_description" value={editForm.description} onChange={(e) => setEditForm({ ...editForm, description: e.target.value })} rows={3} />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label>Status</Label>
                  <Select value={editForm.status} onValueChange={(v) => setEditForm({ ...editForm, status: v })}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {STATUS_OPTIONS.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label>Priority</Label>
                  <Select value={editForm.priority} onValueChange={(v) => setEditForm({ ...editForm, priority: v })}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="Low">Low</SelectItem>
                      <SelectItem value="Medium">Medium</SelectItem>
                      <SelectItem value="High">High</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="edit_start">Start</Label>
                  <Input id="edit_start" type="datetime-local" value={editForm.start_time} onChange={(e) => setEditForm({ ...editForm, start_time: e.target.value })} required />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="edit_end">Due</Label>
                  <Input id="edit_end" type="datetime-local" value={editForm.end_time} onChange={(e) => setEditForm({ ...editForm, end_time: e.target.value })} required />
                </div>
              </div>
              <p className="text-xs text-slate-400">Owner: {editingTask?.user_email} · Category: {editingTask?.category_name || '—'} (not editable here)</p>
              <DialogFooter>
                <Button type="button" variant="outline" onClick={() => setEditingTask(null)}>Cancel</Button>
                <Button type="submit" disabled={saving}>{saving ? 'Saving...' : 'Save'}</Button>
              </DialogFooter>
            </form>
          )}
        </DialogContent>
      </Dialog>

      <AlertDialog open={!!deleteTarget} onOpenChange={(open) => !open && setDeleteTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete this task?</AlertDialogTitle>
            <AlertDialogDescription>This action cannot be undone. "{deleteTarget?.title}" (owned by {deleteTarget?.user_email}) will be permanently deleted.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={handleDelete} className="bg-red-600 hover:bg-red-700">Delete</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
