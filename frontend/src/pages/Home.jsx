import { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { base44 } from '../api/base44Client';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, PieChart, Pie, Cell, LineChart, Line, CartesianGrid } from 'recharts';
import { CheckCircle2, Clock, PlayCircle, ListTodo, Plus, ArrowRight, AlertTriangle, CalendarClock, Bell } from 'lucide-react';
import StatCard from '@/components/statcard';
import TaskForm from '@/components/taskform';
import { statusConfig, colorMap, priorityConfig, getCategoryColor } from '../lib/taskUtils';

export default function Home() {
  const navigate = useNavigate();
  const [tasks, setTasks] = useState([]);
  const [categories, setCategories] = useState([]);
  const [loading, setLoading] = useState(true);
  const [formOpen, setFormOpen] = useState(false);

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

  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const tomorrow = new Date(today);
  tomorrow.setDate(tomorrow.getDate() + 1);

  const isSameDay = (d1, d2) => {
    return d1.getFullYear() === d2.getFullYear() && d1.getMonth() === d2.getMonth() && d1.getDate() === d2.getDate();
  };

  const stats = {
    total: tasks.length,
    completed: tasks.filter(t => t.status === 'Completed').length,
    inProgress: tasks.filter(t => t.status === 'In Progress').length,
    pending: tasks.filter(t => t.status === 'Pending').length,
    overdue: tasks.filter(t => {
      if (!t.end_time || t.status === 'Completed') return false;
      return new Date(t.end_time) < today;
    }).length,
    dueToday: tasks.filter(t => {
      if (!t.end_time || t.status === 'Completed') return false;
      return isSameDay(new Date(t.end_time), today);
    }).length,
  };
  const completionRate = stats.total > 0 ? Math.round((stats.completed / stats.total) * 100) : 0;

  const weeklyData = Array.from({ length: 7 }, (_, i) => {
    const date = new Date();
    date.setDate(date.getDate() - (6 - i));
    const dayName = date.toLocaleDateString('en', { weekday: 'short' });
    const count = tasks.filter(t => {
      if (t.status !== 'Completed' || !t.completed_at) return false;
      return new Date(t.completed_at).toDateString() === date.toDateString();
    }).length;
    return { day: dayName, completed: count };
  });

  const monthlyData = Array.from({ length: 4 }, (_, i) => {
    const weekStart = new Date();
    weekStart.setDate(weekStart.getDate() - (3 - i) * 7 - 6);
    const weekEnd = new Date(weekStart);
    weekEnd.setDate(weekEnd.getDate() + 6);
    const count = tasks.filter(t => {
      if (t.status !== 'Completed' || !t.completed_at) return false;
      const d = new Date(t.completed_at);
      return d >= weekStart && d <= weekEnd;
    }).length;
    return { week: `Week ${i + 1}`, tasks: count };
  });

  const categoryData = categories.map(cat => ({
    name: cat.name,
    value: tasks.filter(t => t.category === cat.id).length,
    color: colorMap[getCategoryColor(cat.id)]
  })).filter(c => c.value > 0);

  const priorityData = ['High', 'Medium', 'Low'].map(p => ({
    name: priorityConfig[p].label,
    value: tasks.filter(t => t.priority === p).length,
    color: p === 'High' ? '#ef4444' : p === 'Medium' ? '#3b82f6' : '#94a3b8'
  })).filter(p => p.value > 0);

  // Due date reminders
  const reminders = {
    overdue: tasks.filter(t => t.end_time && t.status !== 'Completed' && new Date(t.end_time) < today),
    dueToday: tasks.filter(t => t.end_time && t.status !== 'Completed' && isSameDay(new Date(t.end_time), today)),
    dueTomorrow: tasks.filter(t => {
      if (!t.end_time || t.status === 'Completed') return false;
      return isSameDay(new Date(t.end_time), tomorrow);
    }),
  };

  const recentTasks = [...tasks].sort((a, b) => new Date(b.created_at) - new Date(a.created_at)).slice(0, 5);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="w-8 h-8 border-4 border-slate-200 border-t-indigo-600 rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="p-6 lg:p-8 max-w-7xl mx-auto">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Dashboard</h1>
          <p className="text-slate-500 mt-1">{new Date().toLocaleDateString('en', { weekday: 'long', month: 'long', day: 'numeric' })}</p>
        </div>
        <button onClick={() => setFormOpen(true)} className="hidden sm:flex items-center gap-2 px-4 py-2.5 bg-indigo-600 text-white rounded-xl text-sm font-medium hover:bg-indigo-700 transition-colors">
          <Plus className="w-4 h-4" /> New Task
        </button>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-4 mb-8">
        <StatCard icon={ListTodo} label="Total Tasks" value={stats.total} color="bg-indigo-500" />
        <StatCard icon={CheckCircle2} label="Completed" value={stats.completed} color="bg-emerald-500" subtitle={`${completionRate}% rate`} />
        <StatCard icon={PlayCircle} label="In Progress" value={stats.inProgress} color="bg-blue-500" />
        <StatCard icon={Clock} label="Pending" value={stats.pending} color="bg-amber-500" />
        <StatCard icon={CalendarClock} label="Due Today" value={stats.dueToday} color="bg-purple-500" />
        <StatCard icon={AlertTriangle} label="Overdue" value={stats.overdue} color="bg-red-500" />
      </div>

      {/* Due Date Reminders */}
      {(reminders.overdue.length > 0 || reminders.dueToday.length > 0 || reminders.dueTomorrow.length > 0) && (
        <div className="bg-white rounded-2xl p-6 border border-slate-100 shadow-sm mb-8">
          <div className="flex items-center gap-2 mb-4">
            <Bell className="w-5 h-5 text-indigo-600" />
            <h2 className="text-lg font-semibold text-slate-900">Due Date Reminders</h2>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <ReminderColumn title="Overdue" tasks={reminders.overdue} color="red" />
            <ReminderColumn title="Due Today" tasks={reminders.dueToday} color="amber" />
            <ReminderColumn title="Due Tomorrow" tasks={reminders.dueTomorrow} color="blue" />
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
        <div className="bg-white rounded-2xl p-6 border border-slate-100 shadow-sm">
          <h2 className="text-lg font-semibold text-slate-900 mb-1">Weekly Summary</h2>
          <p className="text-sm text-slate-500 mb-6">Tasks completed in the last 7 days</p>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={weeklyData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
              <XAxis dataKey="day" tick={{ fontSize: 12, fill: '#94a3b8' }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 12, fill: '#94a3b8' }} axisLine={false} tickLine={false} allowDecimals={false} />
              <Tooltip contentStyle={{ borderRadius: '12px', border: '1px solid #f1f5f9', fontSize: '13px' }} />
              <Bar dataKey="completed" fill="#6366f1" radius={[8, 8, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="bg-white rounded-2xl p-6 border border-slate-100 shadow-sm">
          <h2 className="text-lg font-semibold text-slate-900 mb-1">Monthly Report</h2>
          <p className="text-sm text-slate-500 mb-6">Productivity trend over 4 weeks</p>
          <ResponsiveContainer width="100%" height={250}>
            <LineChart data={monthlyData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
              <XAxis dataKey="week" tick={{ fontSize: 12, fill: '#94a3b8' }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 12, fill: '#94a3b8' }} axisLine={false} tickLine={false} allowDecimals={false} />
              <Tooltip contentStyle={{ borderRadius: '12px', border: '1px solid #f1f5f9', fontSize: '13px' }} />
              <Line type="monotone" dataKey="tasks" stroke="#8b5cf6" strokeWidth={3} dot={{ fill: '#8b5cf6', r: 5 }} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
        {categoryData.length > 0 && (
          <div className="bg-white rounded-2xl p-6 border border-slate-100 shadow-sm">
            <h2 className="text-lg font-semibold text-slate-900 mb-6">Category Distribution</h2>
            <div className="flex items-center gap-6">
              <ResponsiveContainer width={180} height={180}>
                <PieChart>
                  <Pie data={categoryData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={70} innerRadius={45}>
                    {categoryData.map((entry, i) => <Cell key={i} fill={entry.color} />)}
                  </Pie>
                  <Tooltip contentStyle={{ borderRadius: '12px', border: '1px solid #f1f5f9', fontSize: '13px' }} />
                </PieChart>
              </ResponsiveContainer>
              <div className="space-y-2 flex-1">
                {categoryData.map((cat, i) => (
                  <div key={i} className="flex items-center justify-between text-sm">
                    <div className="flex items-center gap-2">
                      <span className="w-3 h-3 rounded-full" style={{ background: cat.color }} />
                      <span className="text-slate-600">{cat.name}</span>
                    </div>
                    <span className="font-medium text-slate-900">{cat.value}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {priorityData.length > 0 && (
          <div className="bg-white rounded-2xl p-6 border border-slate-100 shadow-sm">
            <h2 className="text-lg font-semibold text-slate-900 mb-6">Priority Distribution</h2>
            <div className="flex items-center gap-6">
              <ResponsiveContainer width={180} height={180}>
                <PieChart>
                  <Pie data={priorityData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={70} innerRadius={45}>
                    {priorityData.map((entry, i) => <Cell key={i} fill={entry.color} />)}
                  </Pie>
                  <Tooltip contentStyle={{ borderRadius: '12px', border: '1px solid #f1f5f9', fontSize: '13px' }} />
                </PieChart>
              </ResponsiveContainer>
              <div className="space-y-2 flex-1">
                {priorityData.map((p, i) => (
                  <div key={i} className="flex items-center justify-between text-sm">
                    <div className="flex items-center gap-2">
                      <span className="w-3 h-3 rounded-full" style={{ background: p.color }} />
                      <span className="text-slate-600">{p.name}</span>
                    </div>
                    <span className="font-medium text-slate-900">{p.value}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>

      <div className="bg-white rounded-2xl p-6 border border-slate-100 shadow-sm">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-slate-900">Recent Tasks</h2>
          <Link to="/tasks" className="text-sm text-indigo-600 hover:text-indigo-700 font-medium flex items-center gap-1">
            View all <ArrowRight className="w-3.5 h-3.5" />
          </Link>
        </div>
        {recentTasks.length === 0 ? (
          <p className="text-sm text-slate-400 py-8 text-center">No tasks yet. Create your first task!</p>
        ) : (
          <div className="space-y-1">
            {recentTasks.map(task => {
              const st = statusConfig[task.status] || statusConfig.Pending;
              return (
                <Link key={task.id} to={`/tasks/${task.id}`} className="flex items-center justify-between py-2.5 px-3 rounded-lg hover:bg-slate-50 transition-colors">
                  <span className="text-sm font-medium text-slate-700 truncate mr-2">{task.title}</span>
                  <span className={`text-xs px-2 py-0.5 rounded-full ${st.badge}`}>{st.label}</span>
                </Link>
              );
            })}
          </div>
        )}
      </div>

      <TaskForm
        open={formOpen}
        onClose={() => setFormOpen(false)}
        task={null}
        categories={categories}
        onSaved={(savedTask) => navigate(`/tasks/${savedTask.id}`)}
      />
    </div>
  );
}

function ReminderColumn({ title, tasks, color }) {
  const colorMap = {
    red: { bg: 'bg-red-50', text: 'text-red-700', border: 'border-red-200', dot: 'bg-red-500' },
    amber: { bg: 'bg-amber-50', text: 'text-amber-700', border: 'border-amber-200', dot: 'bg-amber-500' },
    blue: { bg: 'bg-blue-50', text: 'text-blue-700', border: 'border-blue-200', dot: 'bg-blue-500' },
  };
  const c = colorMap[color];
  return (
    <div className={`rounded-xl ${c.bg} ${c.border} border p-4`}>
      <div className="flex items-center gap-2 mb-2">
        <span className={`w-2 h-2 rounded-full ${c.dot}`} />
        <span className={`text-sm font-semibold ${c.text}`}>{title}</span>
        <span className={`text-xs ${c.text} opacity-70`}>({tasks.length})</span>
      </div>
      {tasks.length === 0 ? (
        <p className="text-xs text-slate-400">Nothing here</p>
      ) : (
        <div className="space-y-1.5">
          {tasks.slice(0, 4).map(task => (
            <Link key={task.id} to={`/tasks/${task.id}`} className="block text-sm text-slate-700 hover:underline truncate">
              {task.title}
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}