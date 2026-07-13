import { useState, useEffect, useMemo } from 'react';
import { base44 } from '../api/base44Client';
import { Plus, Search, ChevronLeft, ChevronRight, Filter } from 'lucide-react';
import { toast } from 'sonner';
import TaskCard from '@/components/taskcard';
import TaskForm from '@/components/taskform';
import { AlertDialog, AlertDialogContent, AlertDialogHeader, AlertDialogTitle, AlertDialogDescription, AlertDialogFooter, AlertDialogCancel, AlertDialogAction } from '@/components/ui/alert-dialog';

const PAGE_SIZE = 9;

export default function Tasks() {
  const [tasks, setTasks] = useState([]);
  const [categories, setCategories] = useState([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState('all');
  const [categoryFilter, setCategoryFilter] = useState('all');
  const [priorityFilter, setPriorityFilter] = useState('all');
  const [dueDateFilter, setDueDateFilter] = useState('all');
  const [search, setSearch] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const [formOpen, setFormOpen] = useState(false);
  const [editingTask, setEditingTask] = useState(null);
  const [deleteTask, setDeleteTask] = useState(null);

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

  const handleAction = async (action, task) => {
    try {
      await base44.entities.Task[action](task.id);
      toast.success(`Task ${action}ed`);
      loadData();
    } catch (err) {
      toast.error(err.response?.data?.message || err.response?.data?.error || 'Failed to update task');
    }
  };

  const handleTaskSaved = () => {
    if (!editingTask) {
      setCurrentPage(1);
    }
    loadData();
  };

  const handleEdit = (task) => {
    setEditingTask(task);
    setFormOpen(true);
  };

  const handleDelete = async () => {
    if (!deleteTask) return;
    try {
      await base44.entities.Task.delete(deleteTask.id);
      toast.success('Task deleted');
      setDeleteTask(null);
      loadData();
    } catch (err) {
      toast.error('Failed to delete task');
    }
  };

  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const tomorrow = new Date(today);
  tomorrow.setDate(tomorrow.getDate() + 1);
  const nextWeek = new Date(today);
  nextWeek.setDate(nextWeek.getDate() + 7);

  const filtered = useMemo(() => {
    return tasks.filter(t => {
      if (statusFilter !== 'all' && t.status !== statusFilter) return false;
      if (categoryFilter !== 'all' && String(t.category) !== categoryFilter) return false;
      if (priorityFilter !== 'all' && t.priority !== priorityFilter) return false;
      if (dueDateFilter !== 'all') {
        if (!t.end_time) return false;
        const due = new Date(t.end_time);
        due.setHours(0, 0, 0, 0);
        if (dueDateFilter === 'today' && due.getTime() !== today.getTime()) return false;
        if (dueDateFilter === 'tomorrow' && due.getTime() !== tomorrow.getTime()) return false;
        if (dueDateFilter === 'overdue' && (due >= today || t.status === 'Completed')) return false;
        if (dueDateFilter === 'week' && (due < today || due > nextWeek)) return false;
      }
      if (search) {
        const q = search.toLowerCase();
        const cat = categories.find(c => c.id === t.category);
        const matches = t.title?.toLowerCase().includes(q) ||
          t.description?.toLowerCase().includes(q) ||
          cat?.name?.toLowerCase().includes(q);
        if (!matches) return false;
      }
      return true;
    });
  }, [tasks, statusFilter, categoryFilter, priorityFilter, dueDateFilter, search, categories]);

  // Reset to page 1 when filters change
  useEffect(() => { setCurrentPage(1); }, [statusFilter, categoryFilter, priorityFilter, dueDateFilter, search]);

  const totalPages = Math.ceil(filtered.length / PAGE_SIZE);
  const paginated = filtered.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);

  const statusTabs = ['all', 'Pending', 'In Progress', 'Paused', 'Completed', 'Stopped', 'Missed'];

  const hasActiveFilters = statusFilter !== 'all' || categoryFilter !== 'all' || priorityFilter !== 'all' || dueDateFilter !== 'all' || search;

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="w-8 h-8 border-4 border-slate-200 border-t-indigo-600 rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="p-6 lg:p-8 max-w-7xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-slate-900">My Tasks</h1>
        <button onClick={() => { setEditingTask(null); setFormOpen(true); }} className="flex items-center gap-2 px-4 py-2.5 bg-indigo-600 text-white rounded-xl text-sm font-medium hover:bg-indigo-700 transition-colors">
          <Plus className="w-4 h-4" /> New Task
        </button>
      </div>

      {/* Search */}
      <div className="relative mb-4">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
        <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search by title, description, or category..." className="w-full pl-10 pr-4 py-2.5 rounded-xl border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400" />
      </div>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-3 mb-4">
        <div className="flex items-center gap-1.5 text-sm text-slate-500 sm:self-center">
          <Filter className="w-4 h-4" /> Filters:
        </div>
        <select value={categoryFilter} onChange={e => setCategoryFilter(e.target.value)} className="px-4 py-2.5 rounded-xl border border-slate-200 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400">
          <option value="all">All Categories</option>
          {categories.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
        <select value={priorityFilter} onChange={e => setPriorityFilter(e.target.value)} className="px-4 py-2.5 rounded-xl border border-slate-200 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400">
          <option value="all">All Priorities</option>
          <option value="High">High</option>
          <option value="Medium">Medium</option>
          <option value="Low">Low</option>
        </select>
        <select value={dueDateFilter} onChange={e => setDueDateFilter(e.target.value)} className="px-4 py-2.5 rounded-xl border border-slate-200 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400">
          <option value="all">All Dates</option>
          <option value="today">Due Today</option>
          <option value="tomorrow">Due Tomorrow</option>
          <option value="week">Due This Week</option>
          <option value="overdue">Overdue</option>
        </select>
        {hasActiveFilters && (
          <button onClick={() => { setCategoryFilter('all'); setPriorityFilter('all'); setDueDateFilter('all'); setStatusFilter('all'); setSearch(''); }} className="px-4 py-2.5 text-sm text-indigo-600 hover:bg-indigo-50 rounded-xl transition-colors self-start sm:self-auto">
            Clear all
          </button>
        )}
      </div>

      {/* Status tabs */}
      <div className="flex gap-1 mb-6 overflow-x-auto pb-1">
        {statusTabs.map(tab => (
          <button key={tab} onClick={() => setStatusFilter(tab)} className={`px-4 py-2 rounded-lg text-sm font-medium whitespace-nowrap transition-colors ${statusFilter === tab ? 'bg-indigo-600 text-white' : 'bg-white text-slate-600 hover:bg-slate-100 border border-slate-200'}`}>
            {tab === 'all' ? 'All' : tab}
          </button>
        ))}
      </div>

      {/* Results count */}
      <p className="text-sm text-slate-500 mb-4">{filtered.length} {filtered.length === 1 ? 'task' : 'tasks'} found</p>

      {filtered.length === 0 ? (
        <div className="text-center py-20">
          <p className="text-slate-400">No tasks found. {hasActiveFilters ? 'Try adjusting your filters.' : 'Create one to get started!'}</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {paginated.map(task => (
            <TaskCard key={task.id} task={task} category={categories.find(c => c.id === task.category)} onAction={(action) => handleAction(action, task)} onEdit={handleEdit} onDelete={setDeleteTask} />
          ))}
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-2 mt-8">
          <button onClick={() => setCurrentPage(p => Math.max(1, p - 1))} disabled={currentPage === 1} className="p-2 rounded-lg border border-slate-200 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-slate-50 transition-colors">
            <ChevronLeft className="w-4 h-4 text-slate-600" />
          </button>
          {Array.from({ length: totalPages }, (_, i) => i + 1).map(page => (
            <button key={page} onClick={() => setCurrentPage(page)} className={`w-9 h-9 rounded-lg text-sm font-medium transition-colors ${currentPage === page ? 'bg-indigo-600 text-white' : 'border border-slate-200 text-slate-600 hover:bg-slate-50'}`}>
              {page}
            </button>
          ))}
          <button onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))} disabled={currentPage === totalPages} className="p-2 rounded-lg border border-slate-200 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-slate-50 transition-colors">
            <ChevronRight className="w-4 h-4 text-slate-600" />
          </button>
        </div>
      )}

      <TaskForm open={formOpen} onClose={() => setFormOpen(false)} task={editingTask} categories={categories} onSaved={handleTaskSaved} />

      <AlertDialog open={!!deleteTask} onOpenChange={(open) => !open && setDeleteTask(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete task?</AlertDialogTitle>
            <AlertDialogDescription>This action cannot be undone. The task "{deleteTask?.title}" will be permanently deleted.</AlertDialogDescription>
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