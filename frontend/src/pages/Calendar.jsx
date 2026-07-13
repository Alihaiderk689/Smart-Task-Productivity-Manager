import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { base44 } from '../api/base44Client';
import { ChevronLeft, ChevronRight, Plus } from 'lucide-react';
import { statusConfig } from '../lib/taskUtils';

const WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

export default function Calendar() {
  const [tasks, setTasks] = useState([]);
  const [categories, setCategories] = useState([]);
  const [loading, setLoading] = useState(true);
  const [currentMonth, setCurrentMonth] = useState(new Date());

  useEffect(() => { loadData(); }, []);

  const loadData = async () => {
    try {
      const [taskData, catData] = await Promise.all([
        base44.entities.Task.list(),
        base44.entities.Category.list()
      ]);
      setTasks(taskData);
      setCategories(catData);
    } finally {
      setLoading(false);
    }
  };

  const year = currentMonth.getFullYear();
  const month = currentMonth.getMonth();
  const firstDay = new Date(year, month, 1).getDay();
  const daysInMonth = new Date(year, month + 1, 0).getDate();

  const today = new Date();
  today.setHours(0, 0, 0, 0);

  const cells = [];
  for (let i = 0; i < firstDay; i++) cells.push(null);
  for (let d = 1; d <= daysInMonth; d++) cells.push(new Date(year, month, d));

  const tasksForDay = (date) => {
    if (!date) return [];
    return tasks.filter(t => {
      if (!t.end_time) return false;
      const due = new Date(t.end_time);
      return due.getFullYear() === date.getFullYear() && due.getMonth() === date.getMonth() && due.getDate() === date.getDate();
    });
  };

  const prevMonth = () => setCurrentMonth(new Date(year, month - 1, 1));
  const nextMonth = () => setCurrentMonth(new Date(year, month + 1, 1));
  const goToday = () => setCurrentMonth(new Date());

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="w-8 h-8 border-4 border-slate-200 border-t-indigo-600 rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="p-6 lg:p-8 max-w-6xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-slate-900">Calendar</h1>
        <Link to="/tasks" className="flex items-center gap-2 px-4 py-2.5 bg-indigo-600 text-white rounded-xl text-sm font-medium hover:bg-indigo-700 transition-colors">
          <Plus className="w-4 h-4" /> New Task
        </Link>
      </div>

      <div className="bg-white rounded-2xl border border-slate-100 shadow-sm overflow-hidden">
        <div className="flex items-center justify-between p-4 border-b border-slate-100">
          <button onClick={prevMonth} className="p-2 rounded-lg hover:bg-slate-100 transition-colors">
            <ChevronLeft className="w-5 h-5 text-slate-600" />
          </button>
          <div className="flex items-center gap-3">
            <h2 className="text-lg font-semibold text-slate-900">
              {currentMonth.toLocaleDateString('en', { month: 'long', year: 'numeric' })}
            </h2>
            <button onClick={goToday} className="text-xs px-3 py-1 rounded-lg bg-indigo-50 text-indigo-600 font-medium hover:bg-indigo-100 transition-colors">
              Today
            </button>
          </div>
          <button onClick={nextMonth} className="p-2 rounded-lg hover:bg-slate-100 transition-colors">
            <ChevronRight className="w-5 h-5 text-slate-600" />
          </button>
        </div>

        <div className="grid grid-cols-7 border-b border-slate-100">
          {WEEKDAYS.map(day => (
            <div key={day} className="text-center text-xs font-semibold text-slate-500 py-3 uppercase tracking-wide">
              {day}
            </div>
          ))}
        </div>

        <div className="grid grid-cols-7">
          {cells.map((date, i) => {
            if (!date) return <div key={i} className="min-h-[100px] border-r border-b border-slate-50 bg-slate-50/50" />;
            const dayTasks = tasksForDay(date);
            const isToday = date.getTime() === today.getTime();
            const isPast = date < today && !isToday;

            return (
              <div key={i} className={`min-h-[100px] border-r border-b border-slate-50 p-2 ${isToday ? 'bg-indigo-50/50' : ''}`}>
                <div className={`text-sm font-medium mb-1 ${isToday ? 'w-6 h-6 rounded-full bg-indigo-600 text-white flex items-center justify-center' : isPast ? 'text-slate-300' : 'text-slate-700'}`}>
                  {date.getDate()}
                </div>
                <div className="space-y-1">
                  {dayTasks.slice(0, 3).map(task => {
                    const st = statusConfig[task.status] || statusConfig.Pending;
                    const cat = categories.find(c => c.id === task.category);
                    return (
                      <Link key={task.id} to={`/tasks/${task.id}`} className={`block text-xs px-2 py-1 rounded-md truncate ${st.badge} hover:opacity-80 transition-opacity`}>
                        {task.title}
                      </Link>
                    );
                  })}
                  {dayTasks.length > 3 && (
                    <p className="text-xs text-slate-400 px-2">+{dayTasks.length - 3} more</p>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Upcoming deadlines */}
      <div className="bg-white rounded-2xl border border-slate-100 shadow-sm p-6 mt-6">
        <h2 className="text-lg font-semibold text-slate-900 mb-4">Upcoming Deadlines</h2>
        {(() => {
          const upcoming = tasks
            .filter(t => t.end_time && t.status !== 'Completed')
            .sort((a, b) => new Date(a.end_time) - new Date(b.end_time))
            .slice(0, 8);
          if (upcoming.length === 0) return <p className="text-sm text-slate-400">No upcoming deadlines.</p>;
          return (
            <div className="space-y-2">
              {upcoming.map(task => {
                const due = new Date(task.end_time);
                const daysAway = Math.ceil((due - today) / (1000 * 60 * 60 * 24));
                const isOverdue = daysAway < 0;
                const isToday = daysAway === 0;
                return (
                  <Link key={task.id} to={`/tasks/${task.id}`} className="flex items-center justify-between py-2 px-3 rounded-lg hover:bg-slate-50 transition-colors">
                    <span className="text-sm font-medium text-slate-700 truncate mr-2">{task.title}</span>
                    <span className={`text-xs font-medium whitespace-nowrap ${isOverdue ? 'text-red-600' : isToday ? 'text-amber-600' : 'text-slate-500'}`}>
                      {isOverdue ? `${Math.abs(daysAway)}d overdue` : isToday ? 'Due today' : `In ${daysAway}d`}
                    </span>
                  </Link>
                );
              })}
            </div>
          );
        })()}
      </div>
    </div>
  );
}