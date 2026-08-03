import { useState, useEffect } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Checkbox } from '@/components/ui/checkbox';
import DateTimePicker from '@/components/ui/datetime-picker';
import { base44 } from '../api/base44Client';
import { getErrorMessage } from '@/services/api';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import {
  TITLE_MAX_WORDS,
  TITLE_MAX_CHARS,
  DESCRIPTION_MAX_WORDS,
  REPEAT_MIN_DAYS,
  REPEAT_MAX_DAYS,
  wordCount,
  validateTaskTitle,
  validateTaskDescription,
  validateCategorySelected,
  validatePrioritySelected,
  validateStartTimeNotPast,
  validateEndAfterStart,
  validateRepeatDays,
} from '@/lib/taskValidation';

// <input type="datetime-local"> needs "yyyy-MM-ddTHH:mm" in local time.
function toDatetimeLocal(isoString) {
  if (!isoString) return '';
  const date = new Date(isoString);
  const offsetMs = date.getTimezoneOffset() * 60000;
  return new Date(date.getTime() - offsetMs).toISOString().slice(0, 16);
}

// formData.start_time/end_time are already plain "yyyy-MM-ddTHH:mm" local
// wall-clock strings (that's what DateTimePicker emits), so this adds
// minutes without any timezone math -- just wall-clock arithmetic.
function addMinutesToLocal(localDatetimeValue, minutes) {
  const [datePart, timePart] = localDatetimeValue.split('T');
  const [y, m, d] = datePart.split('-').map(Number);
  const [h, min] = timePart.split(':').map(Number);
  const date = new Date(y, m - 1, d, h, min + minutes);
  const pad = (n) => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

const DEFAULT_DUE_OFFSET_MINUTES = 30;

const emptyForm = { title: '', description: '', category: '', priority: 'Medium', start_time: '', end_time: '' };

function FieldError({ message }) {
  if (!message) return null;
  return <p className="text-xs text-destructive mt-1">{message}</p>;
}

export default function TaskForm({ open, onClose, task, categories, onSaved }) {
  const [formData, setFormData] = useState(emptyForm);
  const [saving, setSaving] = useState(false);
  // Errors only ever show up after a real Create/Update attempt -- not
  // just from clicking into a field and back out, which used to reveal
  // e.g. "Task name is required." before the user had even finished
  // filling in the rest of the form.
  const [attemptedSubmit, setAttemptedSubmit] = useState(false);
  // Repeat only applies to creating a brand new task, never to editing an
  // existing one -- always reset alongside the rest of the form below.
  const [repeatEnabled, setRepeatEnabled] = useState(false);
  const [repeatDays, setRepeatDays] = useState('7');
  // Until the user touches Due themselves, it auto-follows Start (same day,
  // +30 min) so a same-day task never needs its date picked twice. The
  // instant they set Due directly -- including to a different day, for a
  // multi-day task -- we stop touching it, even if Start changes again
  // afterward. Editing an existing task starts with this already "set":
  // its Due is a deliberate, already-saved value, never something to
  // silently override just because Start gets nudged.
  const [dueManuallySet, setDueManuallySet] = useState(false);

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
    setAttemptedSubmit(false);
    setRepeatEnabled(false);
    setRepeatDays('7');
    setDueManuallySet(Boolean(task));
  }, [task, open]);

  // Editing an already-started/overdue task keeps its original start_time
  // in the payload unchanged -- the backend allows that through even though
  // it's technically "in the past" (see tasks/serializers.py), so the
  // client-side past-time check only applies when it's actually different
  // from what the task already had (or when creating a brand new task).
  const startTimeUnchanged = Boolean(task) && formData.start_time === toDatetimeLocal(task?.start_time);

  const handleStartChange = (value) => {
    setFormData((prev) => ({
      ...prev,
      start_time: value,
      end_time: !dueManuallySet && value ? addMinutesToLocal(value, DEFAULT_DUE_OFFSET_MINUTES) : prev.end_time,
    }));
  };

  const handleEndChange = (value) => {
    setDueManuallySet(true);
    setFormData((prev) => ({ ...prev, end_time: value }));
  };

  const errors = {
    title: validateTaskTitle(formData.title),
    description: validateTaskDescription(formData.description),
    category: validateCategorySelected(formData.category),
    priority: validatePrioritySelected(formData.priority),
    start_time: startTimeUnchanged ? '' : validateStartTimeNotPast(formData.start_time),
    end_time: validateEndAfterStart(formData.start_time, formData.end_time),
    repeat_days: validateRepeatDays(!task && repeatEnabled, repeatDays),
  };
  const isValid = Object.values(errors).every((message) => !message);

  const errorFor = (field) => (attemptedSubmit ? errors[field] : '');

  const handleSubmit = async (e) => {
    e.preventDefault();
    setAttemptedSubmit(true);
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
      } else if (repeatEnabled) {
        const result = await base44.entities.Task.createRepeating({ ...payload, repeat_days: Number(repeatDays) });
        toast.success(`${result.created.length} tasks created`);
        savedTask = result.created[0];
      } else {
        savedTask = await base44.entities.Task.create(payload);
        toast.success('Task created');
      }
      onSaved(savedTask);
      onClose();
    } catch (err) {
      toast.error(getErrorMessage(err, 'Something went wrong'));
    } finally {
      setSaving(false);
    }
  };

  const titleWords = wordCount(formData.title);
  const titleChars = formData.title.trim().length;
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
              <span className="text-xs text-muted-foreground space-x-1.5">
                <span className={cn(titleWords > TITLE_MAX_WORDS && "text-destructive")}>{titleWords}/{TITLE_MAX_WORDS} words</span>
                {titleChars > TITLE_MAX_CHARS * 0.8 && (
                  <span className={cn(titleChars > TITLE_MAX_CHARS && "text-destructive")}>· {titleChars}/{TITLE_MAX_CHARS} chars</span>
                )}
              </span>
            </div>
            <Input
              id="title"
              value={formData.title}
              onChange={e => setFormData({ ...formData, title: e.target.value })}
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
              onChange={e => setFormData({ ...formData, description: e.target.value })}
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
                onValueChange={v => setFormData({ ...formData, category: v })}
              >
                <SelectTrigger
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
                onValueChange={v => setFormData({ ...formData, priority: v })}
              >
                <SelectTrigger
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
                onChange={handleStartChange}
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
                onChange={handleEndChange}
                placeholder="Pick due date"
                minDate={startDate || new Date()}
                required
              />
              {!dueManuallySet && formData.start_time && (
                <p className="text-xs text-muted-foreground">Defaults to the same day as Start.</p>
              )}
              <FieldError message={errorFor('end_time')} />
            </div>
          </div>
          {!task && (
            <div className="space-y-2 rounded-lg border border-input p-3">
              <div className="flex items-center gap-2">
                <Checkbox
                  id="repeat_enabled"
                  checked={repeatEnabled}
                  onCheckedChange={(checked) => setRepeatEnabled(Boolean(checked))}
                />
                <Label htmlFor="repeat_enabled" className="font-normal cursor-pointer">Repeat this task daily</Label>
              </div>
              {repeatEnabled && (
                <div className="flex items-center gap-2 pl-6">
                  <span className="text-sm text-muted-foreground shrink-0">for</span>
                  <Input
                    id="repeat_days"
                    type="number"
                    min={REPEAT_MIN_DAYS}
                    max={REPEAT_MAX_DAYS}
                    value={repeatDays}
                    onChange={e => setRepeatDays(e.target.value)}
                    className={cn("w-20", errorFor('repeat_days') && "border-destructive focus-visible:ring-destructive")}
                  />
                  <span className="text-sm text-muted-foreground">days, same time each day</span>
                </div>
              )}
              <FieldError message={errorFor('repeat_days')} />
            </div>
          )}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
            <Button type="submit" disabled={saving}>
              {saving
                ? 'Saving...'
                : task
                ? 'Update'
                : repeatEnabled && !errors.repeat_days
                ? `Create ${repeatDays} Tasks`
                : 'Create'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
