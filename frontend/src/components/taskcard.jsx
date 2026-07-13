import { Link } from 'react-router-dom';
import { Play, Pause, CheckCircle2, Square, MoreVertical, Calendar, Pencil, Trash2 } from 'lucide-react';
import { statusConfig, priorityConfig, colorBgMap, getAvailableActions, getCategoryColor } from '../lib/taskUtils';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';

export default function TaskCard({ task, category, onAction, onEdit, onDelete }) {
  const status = statusConfig[task.status] || statusConfig.Pending;
  const priority = priorityConfig[task.priority] || priorityConfig.Medium;
  const actions = getAvailableActions(task.status);
  const catColor = category ? colorBgMap[getCategoryColor(category.id)] : 'bg-slate-400';

  const actionButtons = {
    start: { label: 'Start', icon: Play, class: 'bg-indigo-600 hover:bg-indigo-700' },
    pause: { label: 'Pause', icon: Pause, class: 'bg-orange-500 hover:bg-orange-600' },
    resume: { label: 'Resume', icon: Play, class: 'bg-indigo-600 hover:bg-indigo-700' },
    stop: { label: 'Stop', icon: Square, class: 'bg-red-500 hover:bg-red-600' },
    complete: { label: 'Complete', icon: CheckCircle2, class: 'bg-emerald-600 hover:bg-emerald-700' },
  };

  return (
    <div className="bg-white rounded-2xl p-5 border border-slate-100 shadow-sm hover:shadow-md transition-shadow group">
      <div className="flex items-start justify-between gap-2 mb-3">
        <Link to={`/tasks/${task.id}`} className="flex-1">
          <h3 className="font-semibold text-slate-900 hover:text-indigo-600 transition-colors">{task.title}</h3>
        </Link>
        <DropdownMenu>
          <DropdownMenuTrigger className="p-1 rounded-lg hover:bg-slate-100 opacity-0 group-hover:opacity-100 transition-opacity">
            <MoreVertical className="w-4 h-4 text-slate-400" />
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={() => onEdit(task)}>
              <Pencil className="w-4 h-4 mr-2" /> Edit
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => onDelete(task)} className="text-red-600">
              <Trash2 className="w-4 h-4 mr-2" /> Delete
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      {task.description && <p className="text-sm text-slate-500 line-clamp-2 mb-3">{task.description}</p>}

      <div className="flex items-center gap-2 flex-wrap mb-4">
        <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${status.badge}`}>
          <span className={`w-1.5 h-1.5 rounded-full ${status.dot}`} />
          {status.label}
        </span>
        <span className={`px-2.5 py-1 rounded-full text-xs font-medium ${priority.badge}`}>{priority.label}</span>
        {category && (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-slate-100 text-slate-600">
            <span className={`w-2 h-2 rounded-full ${catColor}`} />
            {category.name}
          </span>
        )}
        {task.end_time && (
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium bg-slate-100 text-slate-500">
            <Calendar className="w-3 h-3" />
            {new Date(task.end_time).toLocaleDateString('en', { month: 'short', day: 'numeric' })}
          </span>
        )}
      </div>

      {actions.length > 0 && (
        <div className="flex items-center gap-2 flex-wrap">
          {actions.map(action => {
            const btn = actionButtons[action];
            const Icon = btn.icon;
            return (
              <button key={action} onClick={() => onAction(action)} className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-white transition-colors ${btn.class}`}>
                <Icon className="w-3.5 h-3.5" /> {btn.label}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}