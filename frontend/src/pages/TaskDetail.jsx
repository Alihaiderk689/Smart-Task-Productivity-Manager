import { useState, useEffect } from 'react';
import { useParams, useNavigate, useSearchParams, Link } from 'react-router-dom';
import { base44 } from '../api/base44Client';
import { toast } from 'sonner';
import { ArrowLeft, Play, Pause, CheckCircle2, Square, CalendarClock, Pencil, Trash2, Calendar, Tag, Flag } from 'lucide-react';
import { statusConfig, priorityConfig, getAvailableActions, formatDateTime } from '../lib/taskUtils';
import TaskForm from '@/components/taskform';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { AlertDialog, AlertDialogContent, AlertDialogHeader, AlertDialogTitle, AlertDialogDescription, AlertDialogFooter, AlertDialogCancel, AlertDialogAction } from '@/components/ui/alert-dialog';

// <input type="datetime-local"> needs "yyyy-MM-ddTHH:mm" in local time.
function toDatetimeLocal(isoString) {
  if (!isoString) return '';
  const date = new Date(isoString);
  const offsetMs = date.getTimezoneOffset() * 60000;
  return new Date(date.getTime() - offsetMs).toISOString().slice(0, 16);
}

export default function TaskDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [task, setTask] = useState(null);
  const [categories, setCategories] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editOpen, setEditOpen] = useState(false);
  const [rescheduleOpen, setRescheduleOpen] = useState(false);
  const [newStartTime, setNewStartTime] = useState('');
  const [newEndTime, setNewEndTime] = useState('');
  const [deleteOpen, setDeleteOpen] = useState(false);

  useEffect(() => { loadData(); }, [id]);

  // Coming from an email reminder link (?reschedule=1): open the dialog
  // as soon as the task has loaded, then drop the param from the URL.
  useEffect(() => {
    if (task && searchParams.get('reschedule') === '1') {
      setNewStartTime(toDatetimeLocal(task.start_time));
      setNewEndTime(toDatetimeLocal(task.end_time));
      setRescheduleOpen(true);
      setSearchParams({}, { replace: true });
    }
  }, [task, searchParams, setSearchParams]);

  const loadData = async () => {
    try {
      const [taskData, catData] = await Promise.all([
        base44.entities.Task.get(id),
        base44.entities.Category.list()
      ]);
      setTask(taskData);
      setCategories(catData);
    } finally {
      setLoading(false);
    }
  };

  const handleAction = async (action) => {
    try {
      await base44.entities.Task[action](task.id);
      toast.success(`Task ${action}ed`);
      loadData();
    } catch (err) {
      toast.error(err.response?.data?.message || err.response?.data?.error || 'Failed to update task');
    }
  };

  const handleReschedule = async () => {
    try {
      await base44.entities.Task.reschedule(task.id, {
        start_time: new Date(newStartTime).toISOString(),
        end_time: new Date(newEndTime).toISOString(),
      });
      toast.success('Task rescheduled');
      setRescheduleOpen(false);
      loadData();
    } catch (err) {
      toast.error(err.response?.data?.error || 'Failed to reschedule');
    }
  };

  const handleDelete = async () => {
    try {
      await base44.entities.Task.delete(task.id);
      toast.success('Task deleted');
      navigate('/tasks');
    } catch (err) {
      toast.error('Failed to delete task');
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="w-8 h-8 border-4 border-slate-200 border-t-indigo-600 rounded-full animate-spin" />
      </div>
    );
  }

  if (!task) {
    return (
      <div className="p-8 text-center">
        <p className="text-slate-500">Task not found.</p>
        <Link to="/tasks" className="text-indigo-600 hover:underline">Back to tasks</Link>
      </div>
    );
  }

  const status = statusConfig[task.status] || statusConfig.Pending;
  const priority = priorityConfig[task.priority] || priorityConfig.Medium;
  const category = categories.find(c => c.id === task.category);
  const actions = getAvailableActions(task.status);

  const actionButtons = {
    start: { label: 'Start', icon: Play, class: 'bg-indigo-600 hover:bg-indigo-700' },
    pause: { label: 'Pause', icon: Pause, class: 'bg-orange-500 hover:bg-orange-600' },
    resume: { label: 'Resume', icon: Play, class: 'bg-indigo-600 hover:bg-indigo-700' },
    stop: { label: 'Stop', icon: Square, class: 'bg-red-500 hover:bg-red-600' },
    complete: { label: 'Complete', icon: CheckCircle2, class: 'bg-emerald-600 hover:bg-emerald-700' },
  };

  return (
    <div className="p-6 lg:p-8 max-w-4xl mx-auto">
      <Link to="/tasks" className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-700 mb-6">
        <ArrowLeft className="w-4 h-4" /> Back to Tasks
      </Link>

      <div className="bg-white rounded-2xl border border-slate-100 shadow-sm overflow-hidden">
        <div className="p-6 lg:p-8">
          <div className="flex items-start justify-between gap-4 mb-4">
            <h1 className="text-2xl font-bold text-slate-900">{task.title}</h1>
            <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium ${status.badge} whitespace-nowrap`}>
              <span className={`w-1.5 h-1.5 rounded-full ${status.dot}`} />
              {status.label}
            </span>
          </div>

          {task.description && <p className="text-slate-600 mb-6 whitespace-pre-wrap">{task.description}</p>}

          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
            <div className="flex items-center gap-2.5">
              <div className="w-9 h-9 rounded-lg bg-slate-100 flex items-center justify-center">
                <Flag className="w-4 h-4 text-slate-500" />
              </div>
              <div>
                <p className="text-xs text-slate-400">Priority</p>
                <p className="text-sm font-medium text-slate-700">{priority.label}</p>
              </div>
            </div>
            {category && (
              <div className="flex items-center gap-2.5">
                <div className="w-9 h-9 rounded-lg bg-slate-100 flex items-center justify-center">
                  <Tag className="w-4 h-4 text-slate-500" />
                </div>
                <div>
                  <p className="text-xs text-slate-400">Category</p>
                  <p className="text-sm font-medium text-slate-700">{category.name}</p>
                </div>
              </div>
            )}
            <div className="flex items-center gap-2.5">
              <div className="w-9 h-9 rounded-lg bg-slate-100 flex items-center justify-center">
                <Calendar className="w-4 h-4 text-slate-500" />
              </div>
              <div>
                <p className="text-xs text-slate-400">Due</p>
                <p className="text-sm font-medium text-slate-700">{task.end_time ? new Date(task.end_time).toLocaleDateString('en', { month: 'short', day: 'numeric', year: 'numeric' }) : '—'}</p>
              </div>
            </div>
          </div>

          {task.status !== 'Completed' && (
            <div className="flex flex-wrap gap-2 mb-6">
              {actions.map(action => {
                const btn = actionButtons[action];
                const Icon = btn.icon;
                return (
                  <button key={action} onClick={() => handleAction(action)} className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium text-white transition-colors ${btn.class}`}>
                    <Icon className="w-4 h-4" /> {btn.label}
                  </button>
                );
              })}
              <button onClick={() => { setNewStartTime(toDatetimeLocal(task.start_time)); setNewEndTime(toDatetimeLocal(task.end_time)); setRescheduleOpen(true); }} className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium bg-slate-100 text-slate-700 hover:bg-slate-200 transition-colors">
                <CalendarClock className="w-4 h-4" /> Reschedule
              </button>
            </div>
          )}

          <div className="flex gap-2 pt-6 border-t border-slate-100">
            <button onClick={() => setEditOpen(true)} className="flex items-center gap-2 px-3 py-2 text-sm text-slate-600 hover:bg-slate-100 rounded-lg transition-colors">
              <Pencil className="w-4 h-4" /> Edit
            </button>
            <button onClick={() => setDeleteOpen(true)} className="flex items-center gap-2 px-3 py-2 text-sm text-red-600 hover:bg-red-50 rounded-lg transition-colors">
              <Trash2 className="w-4 h-4" /> Delete
            </button>
          </div>
        </div>

        <div className="bg-slate-50 border-t border-slate-100 p-6 lg:p-8">
          <h3 className="text-sm font-semibold text-slate-700 mb-4">Activity Timeline</h3>
          <div className="space-y-3">
            <TimelineItem label="Created" date={task.created_at} />
            {task.started_at && <TimelineItem label="Started" date={task.started_at} />}
            {task.completed_at && <TimelineItem label="Completed" date={task.completed_at} />}
            {task.rescheduled_count > 0 && <div className="text-sm text-slate-500 pl-4">Rescheduled {task.rescheduled_count} time(s)</div>}
          </div>
        </div>
      </div>

      <TaskForm open={editOpen} onClose={() => setEditOpen(false)} task={task} categories={categories} onSaved={loadData} />

      <Dialog open={rescheduleOpen} onOpenChange={setRescheduleOpen}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Reschedule Task</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-2">
              <Label>New Start</Label>
              <Input type="datetime-local" value={newStartTime} onChange={e => setNewStartTime(e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label>New Due</Label>
              <Input type="datetime-local" value={newEndTime} onChange={e => setNewEndTime(e.target.value)} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRescheduleOpen(false)}>Cancel</Button>
            <Button onClick={handleReschedule} disabled={!newStartTime || !newEndTime}>Reschedule</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AlertDialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete task?</AlertDialogTitle>
            <AlertDialogDescription>This action cannot be undone. The task "{task.title}" will be permanently deleted.</AlertDialogDescription>
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

function TimelineItem({ label, date }) {
  return (
    <div className="flex items-center gap-2 text-sm">
      <span className="w-2 h-2 rounded-full bg-indigo-400" />
      <span className="text-slate-600 font-medium">{label}</span>
      <span className="text-slate-400">{formatDateTime(date)}</span>
    </div>
  );
}
