import { useState, useEffect } from 'react';
import { base44 } from '../api/base44Client';
import { toast } from 'sonner';
import { Plus, Pencil, Trash2, CheckSquare } from 'lucide-react';
import { colorBgMap, getCategoryColor } from '../lib/taskUtils';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { AlertDialog, AlertDialogContent, AlertDialogHeader, AlertDialogTitle, AlertDialogDescription, AlertDialogFooter, AlertDialogCancel, AlertDialogAction } from '@/components/ui/alert-dialog';

export default function Categories() {
  const [categories, setCategories] = useState([]);
  const [tasks, setTasks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [deleteCat, setDeleteCat] = useState(null);
  const [formData, setFormData] = useState({ name: '' });

  useEffect(() => { loadData(); }, []);

  const loadData = async () => {
    try {
      const [catData, taskData] = await Promise.all([
        base44.entities.Category.list(),
        base44.entities.Task.list()
      ]);
      setCategories(catData);
      setTasks(taskData);
    } finally {
      setLoading(false);
    }
  };

  const openCreate = () => {
    setEditing(null);
    setFormData({ name: '' });
    setFormOpen(true);
  };

  const openEdit = (cat) => {
    setEditing(cat);
    setFormData({ name: cat.name });
    setFormOpen(true);
  };

  const handleSave = async (e) => {
    e.preventDefault();
    if (!formData.name.trim()) return;
    try {
      if (editing) {
        await base44.entities.Category.update(editing.id, formData);
        toast.success('Category updated');
      } else {
        await base44.entities.Category.create(formData);
        toast.success('Category created');
      }
      setFormOpen(false);
      loadData();
    } catch (err) {
      toast.error(err.response?.data?.name?.[0] || 'Something went wrong');
    }
  };

  const handleDelete = async () => {
    if (!deleteCat) return;
    try {
      await base44.entities.Category.delete(deleteCat.id);
      toast.success('Category deleted');
      setDeleteCat(null);
      loadData();
    } catch (err) {
      toast.error('Failed to delete category');
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="w-8 h-8 border-4 border-slate-200 border-t-indigo-600 rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="p-6 lg:p-8 max-w-5xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Categories</h1>
          <p className="text-slate-500 text-sm mt-1">Organize your tasks with categories</p>
        </div>
        <button onClick={openCreate} className="flex items-center gap-2 px-4 py-2.5 bg-indigo-600 text-white rounded-xl text-sm font-medium hover:bg-indigo-700 transition-colors">
          <Plus className="w-4 h-4" /> New Category
        </button>
      </div>

      {categories.length === 0 ? (
        <div className="text-center py-20">
          <div className="w-16 h-16 rounded-2xl bg-slate-100 flex items-center justify-center mx-auto mb-4">
            <CheckSquare className="w-8 h-8 text-slate-300" />
          </div>
          <p className="text-slate-400">No categories yet. Create one to organize your tasks!</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {categories.map(cat => {
            const count = tasks.filter(t => t.category === cat.id).length;
            return (
              <div key={cat.id} className="bg-white rounded-2xl p-5 border border-slate-100 shadow-sm group">
                <div className="flex items-start justify-between mb-3">
                  <div className={`w-10 h-10 rounded-xl ${colorBgMap[getCategoryColor(cat.id)]} flex items-center justify-center`}>
                    <CheckSquare className="w-5 h-5 text-white" />
                  </div>
                  <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                    <button onClick={() => openEdit(cat)} className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-400 hover:text-slate-600">
                      <Pencil className="w-4 h-4" />
                    </button>
                    <button onClick={() => setDeleteCat(cat)} className="p-1.5 rounded-lg hover:bg-red-50 text-slate-400 hover:text-red-600">
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>
                <h3 className="font-semibold text-slate-900">{cat.name}</h3>
                <p className="text-sm text-slate-400">{count} {count === 1 ? 'task' : 'tasks'}</p>
              </div>
            );
          })}
        </div>
      )}

      <Dialog open={formOpen} onOpenChange={setFormOpen}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>{editing ? 'Edit Category' : 'New Category'}</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleSave} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="cat-name">Name</Label>
              <Input id="cat-name" value={formData.name} onChange={e => setFormData({ ...formData, name: e.target.value })} placeholder="e.g. Work, Personal, Health" required autoFocus />
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setFormOpen(false)}>Cancel</Button>
              <Button type="submit">{editing ? 'Update' : 'Create'}</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <AlertDialog open={!!deleteCat} onOpenChange={(open) => !open && setDeleteCat(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete category?</AlertDialogTitle>
            <AlertDialogDescription>This will delete "{deleteCat?.name}" and all tasks in this category. This action cannot be undone.</AlertDialogDescription>
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
