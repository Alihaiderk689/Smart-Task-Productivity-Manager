import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Play, Pause, Square, MoreVertical, Calendar, Pencil, Trash2, ChevronDown, ChevronUp, Repeat } from 'lucide-react';
import { statusConfig, priorityConfig, colorBgMap, getAvailableActions, getCategoryColor } from '../lib/taskUtils';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';

const actionButtons = {
  start: { label: 'Start', icon: Play, class: 'bg-indigo-600 hover:bg-indigo-700' },
  pause: { label: 'Pause', icon: Pause, class: 'bg-orange-500 hover:bg-orange-600' },
  resume: { label: 'Resume', icon: Play, class: 'bg-indigo-600 hover:bg-indigo-700' },
  stop: { label: 'Stop', icon: Square, class: 'bg-red-500 hover:bg-red-600' },
};

// Collapses one "repeat" series (see tasks/views.py::create_repeating_tasks)
// into a single card. Every occurrence is still a fully independent Task
// underneath -- its own status, its own reminders -- this component just
// presents them as one unit until expanded, so a 7-day repeat doesn't turn
// into 7 separate cards in the list.
export default function TaskSeriesCard({ tasks, category, onAction, onEdit, onDelete, onDeleteSeries }) {
  const [expanded, setExpanded] = useState(false);
  const first = tasks[0];
  const last = tasks[tasks.length - 1];
  const completedCount = tasks.filter(t => t.status === 'Completed').length;
  const priority = priorityConfig[first.priority] || priorityConfig.Medium;
  const catColor = category ? colorBgMap[getCategoryColor(category.id)] : 'bg-slate-400';
  const dateRange = `${new Date(first.start_time).toLocaleDateString('en', { month: 'short', day: 'numeric' })} – ${new Date(last.end_time).toLocaleDateString('en', { month: 'short', day: 'numeric' })}`;

  return (
    <div className="bg-white dark:bg-slate-900 rounded-2xl p-5 border border-slate-100 dark:border-slate-800 shadow-sm hover:shadow-md transition-shadow group">
      <div className="flex items-start justify-between gap-2 mb-3">
        <button type="button" onClick={() => setExpanded(e => !e)} className="flex-1 flex items-center gap-2 text-left min-w-0">
          {expanded ? <ChevronUp className="w-4 h-4 text-slate-400 shrink-0" /> : <ChevronDown className="w-4 h-4 text-slate-400 shrink-0" />}
          <h3 className="font-semibold text-slate-900 dark:text-slate-100 truncate">{first.title}</h3>
        </button>
        <DropdownMenu>
          <DropdownMenuTrigger className="p-1 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 opacity-0 group-hover:opacity-100 transition-opacity">
            <MoreVertical className="w-4 h-4 text-slate-400" />
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={() => onDeleteSeries(tasks)} className="text-red-600">
              <Trash2 className="w-4 h-4 mr-2" /> Delete entire series
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      {first.description && <p className="text-sm text-slate-500 dark:text-slate-400 line-clamp-2 mb-3">{first.description}</p>}

      <div className="flex items-center gap-2 flex-wrap mb-4">
        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-indigo-100 dark:bg-indigo-500/10 text-indigo-700 dark:text-indigo-400">
          <Repeat className="w-3 h-3" /> {tasks.length}-day series
        </span>
        <span className="px-2.5 py-1 rounded-full text-xs font-medium bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300">
          {completedCount}/{tasks.length} done
        </span>
        <span className={`px-2.5 py-1 rounded-full text-xs font-medium ${priority.badge}`}>{priority.label}</span>
        {category && (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300">
            <span className={`w-2 h-2 rounded-full ${catColor}`} />
            {category.name}
          </span>
        )}
        <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400">
          <Calendar className="w-3 h-3" /> {dateRange}
        </span>
      </div>

      {!expanded ? (
        <button type="button" onClick={() => setExpanded(true)} className="text-xs font-medium text-indigo-600 dark:text-indigo-400 hover:underline">
          Show all {tasks.length} days
        </button>
      ) : (
        <div className="space-y-2">
          {tasks.map(task => {
            const status = statusConfig[task.status] || statusConfig.Pending;
            const actions = getAvailableActions(task.status);
            return (
              <div key={task.id} className="flex items-center justify-between gap-2 p-2.5 rounded-xl bg-slate-50 dark:bg-slate-800/60 flex-wrap">
                <div className="flex items-center gap-2 min-w-0">
                  <Link to={`/tasks/${task.id}`} className="text-sm font-medium text-slate-700 dark:text-slate-200 hover:text-indigo-600 dark:hover:text-indigo-400 shrink-0">
                    Day {task.repeat_index}
                  </Link>
                  <span className="text-xs text-slate-400 shrink-0">
                    {new Date(task.start_time).toLocaleDateString('en', { month: 'short', day: 'numeric' })}
                  </span>
                  <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium ${status.badge}`}>
                    <span className={`w-1.5 h-1.5 rounded-full ${status.dot}`} />
                    {status.label}
                  </span>
                </div>
                <div className="flex items-center gap-1.5 shrink-0">
                  {actions.map(action => {
                    const btn = actionButtons[action];
                    const Icon = btn.icon;
                    return (
                      <button
                        key={action}
                        type="button"
                        onClick={() => onAction(action, task)}
                        className={`flex items-center gap-1 px-2 py-1 rounded-lg text-[11px] font-medium text-white transition-colors ${btn.class}`}
                      >
                        <Icon className="w-3 h-3" /> {btn.label}
                      </button>
                    );
                  })}
                  <button
                    type="button"
                    onClick={() => onEdit(task)}
                    className="p-1.5 rounded-lg text-slate-400 hover:text-indigo-600 hover:bg-white dark:hover:bg-slate-700 transition-colors"
                    aria-label={`Edit day ${task.repeat_index}`}
                  >
                    <Pencil className="w-3.5 h-3.5" />
                  </button>
                  <button
                    type="button"
                    onClick={() => onDelete(task)}
                    className="p-1.5 rounded-lg text-slate-400 hover:text-red-600 hover:bg-white dark:hover:bg-slate-700 transition-colors"
                    aria-label={`Delete day ${task.repeat_index}`}
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
