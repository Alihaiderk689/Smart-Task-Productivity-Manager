export const statusConfig = {
  Pending: { label: 'Pending', badge: 'bg-amber-100 text-amber-700 border-amber-200', dot: 'bg-amber-500' },
  'In Progress': { label: 'In Progress', badge: 'bg-blue-100 text-blue-700 border-blue-200', dot: 'bg-blue-500' },
  Paused: { label: 'Paused', badge: 'bg-orange-100 text-orange-700 border-orange-200', dot: 'bg-orange-500' },
  Completed: { label: 'Completed', badge: 'bg-emerald-100 text-emerald-700 border-emerald-200', dot: 'bg-emerald-500' },
  Stopped: { label: 'Stopped', badge: 'bg-red-100 text-red-700 border-red-200', dot: 'bg-red-500' },
  Missed: { label: 'Missed', badge: 'bg-slate-200 text-slate-700 border-slate-300', dot: 'bg-slate-500' },
};

export const priorityConfig = {
  Low: { label: 'Low', badge: 'bg-slate-100 text-slate-600' },
  Medium: { label: 'Medium', badge: 'bg-blue-100 text-blue-600' },
  High: { label: 'High', badge: 'bg-red-100 text-red-600' },
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

export const getAvailableActions = (status) => {
  switch (status) {
    case 'Pending': return ['start'];
    case 'In Progress': return ['pause', 'complete', 'stop'];
    case 'Paused': return ['resume', 'complete', 'stop'];
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
