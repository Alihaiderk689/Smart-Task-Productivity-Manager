export const statusConfig = {
  Pending: { label: 'Pending', badge: 'bg-amber-100 dark:bg-amber-500/10 text-amber-700 dark:text-amber-400 border-amber-200 dark:border-amber-500/20', dot: 'bg-amber-500' },
  'In Progress': { label: 'In Progress', badge: 'bg-blue-100 dark:bg-blue-500/10 text-blue-700 dark:text-blue-400 border-blue-200 dark:border-blue-500/20', dot: 'bg-blue-500' },
  Paused: { label: 'Paused', badge: 'bg-orange-100 dark:bg-orange-500/10 text-orange-700 dark:text-orange-400 border-orange-200 dark:border-orange-500/20', dot: 'bg-orange-500' },
  Completed: { label: 'Completed', badge: 'bg-emerald-100 dark:bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border-emerald-200 dark:border-emerald-500/20', dot: 'bg-emerald-500' },
  Stopped: { label: 'Stopped', badge: 'bg-red-100 dark:bg-red-500/10 text-red-700 dark:text-red-400 border-red-200 dark:border-red-500/20', dot: 'bg-red-500' },
  Missed: { label: 'Missed', badge: 'bg-slate-200 dark:bg-slate-700/40 text-slate-700 dark:text-slate-300 border-slate-300 dark:border-slate-600', dot: 'bg-slate-500' },
};

export const priorityConfig = {
  Low: { label: 'Low', badge: 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300' },
  Medium: { label: 'Medium', badge: 'bg-blue-100 dark:bg-blue-500/10 text-blue-600 dark:text-blue-400' },
  High: { label: 'High', badge: 'bg-red-100 dark:bg-red-500/10 text-red-600 dark:text-red-400' },
};

export const colorMap = {
  indigo: '#6366f1', blue: '#3b82f6', green: '#10b981', red: '#ef4444',
  amber: '#f59e0b', purple: '#a855f7', pink: '#ec4899', teal: '#14b8a6',
};

export const colorBgMap = {
  indigo: 'bg-indigo-500', blue: 'bg-blue-500', green: 'bg-green-500',
  red: 'bg-red-500', amber: 'bg-amber-500', purple: 'bg-purple-500',
  pink: 'bg-pink-500', teal: 'bg-teal-500',
};

export const colorOptions = ['indigo', 'blue', 'green', 'red', 'amber', 'purple', 'pink', 'teal'];

// The backend doesn't store a color for categories, so derive a stable one from the id.
export const getCategoryColor = (categoryId) => {
  if (categoryId === null || categoryId === undefined) return colorOptions[0];
  const index = Number(categoryId) % colorOptions.length;
  return colorOptions[index];
};

// "Task " + action + "ed" reads fine for started/paused/resumed but breaks
// down for "stop" ("stoped") -- and now that Stop marks the task Completed
// (see backend/tasks/views.py's stop_task), the toast should say so.
export const actionSuccessMessages = {
  start: 'Task started',
  pause: 'Task paused',
  resume: 'Task resumed',
  stop: 'Task completed',
};

export const getAvailableActions = (status) => {
  switch (status) {
    case 'Pending': return ['start'];
    case 'In Progress': return ['pause', 'stop'];
    case 'Paused': return ['resume', 'stop'];
    default: return [];
  }
};

export const formatDuration = (seconds) => {
  if (!seconds) return '0m';
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
};

export const formatDateTime = (dateStr) => {
  if (!dateStr) return '—';
  const date = new Date(dateStr);
  return date.toLocaleDateString('en', { month: 'short', day: 'numeric' }) + ' at ' +
    date.toLocaleTimeString('en', { hour: 'numeric', minute: '2-digit' });
};

// Collapses same-repeat_group_id tasks into one series entry for display
// (see tasks/views.py::create_repeating_tasks) -- everything else stays a
// standalone entry. A group only collapses when every one of its
// occurrences is present in `taskList` (repeat_total tells us the expected
// size); if a filter has narrowed a series down to a subset, showing those
// remaining ones individually is less confusing than a partial "series".
// Returns a list of { type: 'task', task } | { type: 'series', tasks },
// sorted by each item's earliest start_time.
export function groupTasksForDisplay(taskList) {
  const byGroup = new Map();
  const items = [];

  for (const task of taskList) {
    if (task.repeat_group_id) {
      if (!byGroup.has(task.repeat_group_id)) byGroup.set(task.repeat_group_id, []);
      byGroup.get(task.repeat_group_id).push(task);
    } else {
      items.push({ type: 'task', task, sortKey: task.start_time });
    }
  }

  for (const groupTasks of byGroup.values()) {
    const sorted = [...groupTasks].sort((a, b) => (a.repeat_index ?? 0) - (b.repeat_index ?? 0));
    const expectedTotal = sorted[0]?.repeat_total ?? sorted.length;
    if (sorted.length === expectedTotal) {
      items.push({ type: 'series', tasks: sorted, sortKey: sorted[0].start_time });
    } else {
      for (const task of sorted) items.push({ type: 'task', task, sortKey: task.start_time });
    }
  }

  items.sort((a, b) => new Date(a.sortKey) - new Date(b.sortKey));
  return items;
}
