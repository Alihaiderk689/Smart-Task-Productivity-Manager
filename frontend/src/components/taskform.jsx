import { useState, useEffect } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { base44 } from '../api/base44Client';
import { toast } from 'sonner';

// <input type="datetime-local"> needs "yyyy-MM-ddTHH:mm" in local time.
function toDatetimeLocal(isoString) {
  if (!isoString) return '';
  const date = new Date(isoString);
  const offsetMs = date.getTimezoneOffset() * 60000;
  return new Date(date.getTime() - offsetMs).toISOString().slice(0, 16);
}

const emptyForm = { title: '', description: '', category: '', priority: 'Medium', start_time: '', end_time: '' };

export default function TaskForm({ open, onClose, task, categories, onSaved }) {
  const [formData, setFormData] = useState(emptyForm);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (task) {
      setFormData({
        title: task.title || '',
        description: task.description || '',
        category: task.category != null ? String(task.category) : '',
        priority: task.priority || 'Medium',
        start_time: toDatetimeLocal(task.start_time),
        end_time: toDatetimeLocal(task.end_time),
      });
    } else {
      setFormData(emptyForm);
    }
  }, [task, open]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!formData.title.trim() || !formData.category || !formData.start_time || !formData.end_time) return;
    setSaving(true);
    try {
      const payload = {
        title: formData.title,
        description: formData.description,
        category: Number(formData.category),
        priority: formData.priority,
        start_time: new Date(formData.start_time).toISOString(),
        end_time: new Date(formData.end_time).toISOString(),
      };
      let savedTask;
      if (task) {
        savedTask = await base44.entities.Task.update(task.id, payload);
        toast.success('Task updated');
      } else {
        savedTask = await base44.entities.Task.create(payload);
        toast.success('Task created');
      }
      onSaved(savedTask);
      onClose();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Something went wrong');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{task ? 'Edit Task' : 'New Task'}</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="title">Title</Label>
            <Input id="title" value={formData.title} onChange={e => setFormData({ ...formData, title: e.target.value })} placeholder="What needs to be done?" required />
          </div>
          <div className="space-y-2">
            <Label htmlFor="description">Description</Label>
            <Textarea id="description" value={formData.description} onChange={e => setFormData({ ...formData, description: e.target.value })} placeholder="Add details..." rows={3} />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label>Category</Label>
              <Select value={formData.category} onValueChange={v => setFormData({ ...formData, category: v })}>
                <SelectTrigger><SelectValue placeholder="Select..." /></SelectTrigger>
                <SelectContent>
                  {categories.map(cat => <SelectItem key={cat.id} value={String(cat.id)}>{cat.name}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>Priority</Label>
              <Select value={formData.priority} onValueChange={v => setFormData({ ...formData, priority: v })}>
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
              <Label htmlFor="start_time">Start</Label>
              <Input id="start_time" type="datetime-local" value={formData.start_time} onChange={e => setFormData({ ...formData, start_time: e.target.value })} required />
            </div>
            <div className="space-y-2">
              <Label htmlFor="end_time">Due</Label>
              <Input id="end_time" type="datetime-local" value={formData.end_time} onChange={e => setFormData({ ...formData, end_time: e.target.value })} required />
            </div>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
            <Button type="submit" disabled={saving || !formData.title.trim() || !formData.category || !formData.start_time || !formData.end_time}>
              {saving ? 'Saving...' : task ? 'Update' : 'Create'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
