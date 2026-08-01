// Mirrors backend/tasks/serializers.py's rules. Keep the two in sync; the
// backend is always the real enforcement point, this is just for real-time
// UX (word counters, disabling submit, past-date calendar restrictions).

export const TITLE_MAX_WORDS = 20;
export const DESCRIPTION_MAX_WORDS = 200;

function wordCount(value) {
  const trimmed = (value || "").trim();
  return trimmed ? trimmed.split(/\s+/).length : 0;
}

export function validateTaskTitle(value) {
  const trimmed = (value || "").trim();
  if (!trimmed) return "Task name is required.";
  if (wordCount(trimmed) > TITLE_MAX_WORDS) return `Task name cannot exceed ${TITLE_MAX_WORDS} words.`;
  return "";
}

export function validateTaskDescription(value) {
  const trimmed = (value || "").trim();
  if (trimmed && wordCount(trimmed) > DESCRIPTION_MAX_WORDS) return `Description cannot exceed ${DESCRIPTION_MAX_WORDS} words.`;
  return "";
}

export function validateCategorySelected(value) {
  return value ? "" : "Please select a category.";
}

export function validatePrioritySelected(value) {
  return value ? "" : "Please select a priority.";
}

export function validateStartTimeNotPast(localDatetimeValue) {
  if (!localDatetimeValue) return "Start time is required.";
  const start = new Date(localDatetimeValue);
  if (start <= new Date()) return "Start time cannot be in the past.";
  return "";
}

export function validateEndAfterStart(startLocalDatetimeValue, endLocalDatetimeValue) {
  if (!endLocalDatetimeValue) return "Due time is required.";
  if (!startLocalDatetimeValue) return "";
  const start = new Date(startLocalDatetimeValue);
  const end = new Date(endLocalDatetimeValue);
  if (end <= start) return "Due time must be after the start time.";
  return "";
}

export { wordCount };
