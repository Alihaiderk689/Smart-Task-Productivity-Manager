import { useState, useEffect } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import DateTimePicker from '@/components/ui/datetime-picker';
import { base44 } from '../api/base44Client';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import {
  TITLE_MAX_WORDS,
  DESCRIPTION_MAX_WORDS,
  wordCount,
  validateTaskTitle,
  validateTaskDescription,
  validateCategorySelected,
  validatePrioritySelected,
  validateStartTimeNotPast,
  validateEndAfterStart,
} from '@/lib/taskValidation';

// <input type="datetime-local"> needs "yyyy-MM-ddTHH:mm" in local time.
function toDatetimeLocal(isoString) {
  if (!isoString) return '';
  const date = new Date(isoString);
  const offsetMs = date.getTimezoneOffset() * 60000;
  return new Date(date.getTime() - offsetMs).toISOString().slice(0, 16);
}

const emptyForm = { title: '', description: '', category: '', priority: 'Medium', start_time: '', end_time: '' };

function FieldError({ message }) {
  if (!message) return null;
  return <p className="text-xs text-destructive mt-1">{message}</p>;
}

export default function TaskForm({ open, onClose, task, categories, onSaved }) {
  const [formData, setFormData] = useState(emptyForm);
  const [saving, setSaving] = useState(false);
  const [touched, setTouched] = useState({});

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
    setTouched({});
  }, [task, open]);

  // Editing an already-started/overdue task keeps its original start_time
  // in the payload unchanged -- the backend allows that through even though
  // it's technically "in the past" (see tasks/serializers.py), so the
  // client-side past-time check only applies when it's actually different
  // from what the task already had (or when creating a brand new task).
  const startTimeUnchanged = Boolean(task) && formData.start_time === toDatetimeLocal(task?.start_time);

  const errors = {
    title: validateTaskTitle(formData.title),
    description: validateTaskDescription(formData.description),
    category: validateCategorySelected(formData.category),
    priority: validatePrioritySelected(formData.priority),
    start_time: startTimeUnchanged ? '' : validateStartTimeNotPast(formData.start_time),
    end_time: validateEndAfterStart(formData.start_time, formData.end_time),
  };
  const isValid = Object.values(errors).every((message) => !message);

  const errorFor = (field) => (touched[field] ? errors[field] : '');
  const markTouched = (field) => setTouched((prev) => ({ ...prev, [field]: true }));

  const handleSubmit = async (e) => {
    e.preventDefault();
    setTouched({ title: true, description: true, category: true, priority: true, start_time: true, end_time: true });
    if (!isValid) return;

    setSaving(true);
    try {
      const payload = {
        title: formData.title.trim(),
        description: formData.description.trim(),
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

  const titleWords = wordCount(formData.title);
  const descriptionWords = wordCount(formData.description);
  const startDate = formData.start_time ? new Date(formData.start_time) : null;

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{task ? 'Edit Task' : 'New Task'}</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} noValidate className="space-y-4">
          <div className="space-y-2">
            <div className="flex items-baseline justify-between">
              <Label htmlFor="title">Title</Label>
              <span className={cn("text-xs text-muted-foreground", titleWords > TITLE_MAX_WORDS && "text-destructive")}>
                {titleWords}/{TITLE_MAX_WORDS} words
              </span>
            </div>
            <Input
              id="title"
              value={formData.title}
              onChange={e => { setFormData({ ...formData, title: e.target.value }); markTouched('title'); }}
              onBlur={() => markTouched('title')}
              placeholder="What needs to be done?"
              className={cn(errorFor('title') && "border-destructive focus-visible:ring-destructive")}
            />
            <FieldError message={errorFor('title')} />
          </div>
          <div className="space-y-2">
            <div className="flex items-baseline justify-between">
              <Label htmlFor="description">Description</Label>
              <span className={cn("text-xs text-muted-foreground", descriptionWords > DESCRIPTION_MAX_WORDS && "text-destructive")}>
                {descriptionWords}/{DESCRIPTION_MAX_WORDS} words
              </span>
            </div>
            <Textarea
              id="description"
              value={formData.description}
              onChange={e => { setFormData({ ...formData, description: e.target.value }); markTouched('description'); }}
              onBlur={() => markTouched('description')}
              placeholder="Add details..."
              rows={3}
              className={cn(errorFor('description') && "border-destructive focus-visible:ring-destructive")}
            />
            <FieldError message={errorFor('description')} />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label>Category</Label>
              <Select
                value={formData.category}
                onValueChange={v => { setFormData({ ...formData, category: v }); markTouched('category'); }}
              >
                <SelectTrigger
                  onBlur={() => markTouched('category')}
                  className={cn(errorFor('category') && "border-destructive focus-visible:ring-destructive")}
                >
                  <SelectValue placeholder="Select..." />
                </SelectTrigger>
                <SelectContent>
                  {categories.map(cat => <SelectItem key={cat.id} value={String(cat.id)}>{cat.name}</SelectItem>)}
                </SelectContent>
              </Select>
              <FieldError message={errorFor('category')} />
            </div>
            <div className="space-y-2">
              <Label>Priority</Label>
              <Select
                value={formData.priority}
                onValueChange={v => { setFormData({ ...formData, priority: v }); markTouched('priority'); }}
              >
                <SelectTrigger
                  onBlur={() => markTouched('priority')}
                  className={cn(errorFor('priority') && "border-destructive focus-visible:ring-destructive")}
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="Low">Low</SelectItem>
                  <SelectItem value="Medium">Medium</SelectItem>
                  <SelectItem value="High">High</SelectItem>
                </SelectContent>
              </Select>
              <FieldError message={errorFor('priority')} />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="start_time">Start</Label>
              <DateTimePicker
                id="start_time"
                value={formData.start_time}
                onChange={v => { setFormData({ ...formData, start_time: v }); markTouched('start_time'); }}
                placeholder="Pick start"
                minDate={new Date()}
                required
              />
              <FieldError message={errorFor('start_time')} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="end_time">Due</Label>
              <DateTimePicker
                id="end_time"
                value={formData.end_time}
                onChange={v => { setFormData({ ...formData, end_time: v }); markTouched('end_time'); }}
                placeholder="Pick due date"
                minDate={startDate || new Date()}
                required
              />
              <FieldError message={errorFor('end_time')} />
            </div>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
            <Button type="submit" disabled={saving || !isValid}>
              {saving ? 'Saving...' : task ? 'Update' : 'Create'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
